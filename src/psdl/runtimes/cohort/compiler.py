"""
PSDL Cohort Compiler - Generate SQL queries from PSDL scenarios.

This module compiles PSDL scenarios into SQL queries that can be executed
on OMOP CDM databases for cohort-level evaluation.

Architecture:
    The SQL compiler follows a spec-driven approach:
    1. Parse PSDL scenario (signals, trends, logic)
    2. Generate CTEs for each trend using templates from operators.yaml
    3. Combine CTEs into a single query with logic evaluation

Features:
    - Batch processing for large datasets
    - Population pre-filtering optimization
    - Query cost estimation
    - Parallel query hints (PostgreSQL)

Usage:
    from psdl.core import parse_scenario
    from psdl.runtimes.cohort import CohortCompiler

    scenario = parse_scenario("scenarios/aki_detection.yaml")
    compiler = CohortCompiler(schema="public", use_source_values=True)
    sql = compiler.compile(scenario)
    print(sql.sql)

    # For large datasets, use batch processing:
    for batch_sql in compiler.compile_batched(scenario, batch_size=10000):
        execute(batch_sql.sql)
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from ..._generated.sql_templates import (
        POSTGRESQL_POINTWISE_TEMPLATES,
        POSTGRESQL_TEMPLATES,
        TEMPLATE_ALIASES,
        get_sql_template,
        is_windowed_operator,
    )
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from _generated.sql_templates import (  # noqa: F401
        POSTGRESQL_POINTWISE_TEMPLATES,
        POSTGRESQL_TEMPLATES,
        TEMPLATE_ALIASES,
        get_sql_template,
        is_windowed_operator,
    )


# Window unit to seconds mapping
WINDOW_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


class QueryComplexity(Enum):
    """Estimated query complexity level."""

    LOW = "low"  # < 10 signals, small windows
    MEDIUM = "medium"  # 10-50 signals, moderate windows
    HIGH = "high"  # > 50 signals, large windows, complex logic
    VERY_HIGH = "very_high"  # Requires batching


@dataclass
class QueryCostEstimate:
    """Estimated query cost for optimization decisions."""

    complexity: QueryComplexity
    estimated_cte_count: int
    estimated_join_count: int
    largest_window_seconds: int
    logic_depth: int
    recommendations: List[str] = field(default_factory=list)

    def should_batch(self, cohort_size: int = 0) -> bool:
        """Determine if batching is recommended."""
        if cohort_size > 100000:
            return True
        if self.complexity in (QueryComplexity.HIGH, QueryComplexity.VERY_HIGH):
            return True
        if self.estimated_cte_count > 10 and cohort_size > 10000:
            return True
        return False

    def recommended_batch_size(self, cohort_size: int = 0) -> int:
        """Get recommended batch size for the query."""
        if self.complexity == QueryComplexity.VERY_HIGH:
            return 1000
        elif self.complexity == QueryComplexity.HIGH:
            return 5000
        elif self.complexity == QueryComplexity.MEDIUM:
            return 10000
        else:
            return 50000


@dataclass
class QueryOptimizationConfig:
    """Configuration for query optimization."""

    # Batch processing
    enable_batching: bool = False
    batch_size: int = 10000

    # Population pre-filtering
    apply_population_filter_early: bool = True

    # PostgreSQL-specific optimizations
    enable_parallel_query: bool = True
    parallel_workers_per_gather: int = 4

    # Index hints
    include_index_hints: bool = False

    # Query cost estimation
    estimate_cost: bool = True


@dataclass
class CompiledSQL:
    """Result of SQL compilation."""

    sql: str
    parameters: Dict[str, Any]
    trend_columns: List[str]
    logic_columns: List[str]
    cost_estimate: Optional[QueryCostEstimate] = None
    batch_info: Optional[Dict[str, Any]] = None  # batch_number, total_batches, offset, limit


def parse_window(window_str: str) -> int:
    """Parse window string like '48h' into seconds."""
    match = re.match(r"(\d+)([smhdw])", window_str)
    if not match:
        raise ValueError(f"Invalid window format: {window_str}")
    value = int(match.group(1))
    unit = match.group(2)
    return value * WINDOW_UNITS[unit]


def parse_trend_expression(
    expr: str,
) -> Tuple[str, str, Optional[str], Optional[float], str]:
    """
    Parse a trend expression into components.

    Args:
        expr: Expression like "delta(Cr, 48h) >= 0.3" or "last(HR) > 100"

    Returns:
        Tuple of (operator, signal, window, threshold, comparison_op)
        For pointwise operators, window is None.
        For expressions without threshold, threshold and comparison_op are None.
    """
    # Pattern for windowed operators with comparison: op(signal, window) cmp value
    windowed_pattern = (
        r"(\w+)\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*\)\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    )
    match = re.match(windowed_pattern, expr.strip())
    if match:
        op, signal, window, cmp_op, threshold = match.groups()
        return (op, signal, window, float(threshold), cmp_op)

    # Pattern for windowed operators without comparison: op(signal, window)
    windowed_no_cmp = r"(\w+)\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*\)"
    match = re.match(windowed_no_cmp, expr.strip())
    if match:
        op, signal, window = match.groups()
        return (op, signal, window, None, None)

    # Pattern for percentile: percentile(signal, window, p) cmp value
    percentile_pattern = (
        r"percentile\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*,\s*([\d.]+)\s*\)"
        r"\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    )
    match = re.match(percentile_pattern, expr.strip())
    if match:
        signal, window, p_value, cmp_op, threshold = match.groups()
        # Store percentile value in operator name for later extraction
        return (f"percentile:{p_value}", signal, window, float(threshold), cmp_op)

    # Pattern for pointwise operators with comparison: op(signal) cmp value
    pointwise_pattern = r"(\w+)\s*\(\s*(\w+)\s*\)\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    match = re.match(pointwise_pattern, expr.strip())
    if match:
        op, signal, cmp_op, threshold = match.groups()
        return (op, signal, None, float(threshold), cmp_op)

    # Pattern for pointwise operators without comparison: op(signal)
    pointwise_no_cmp = r"(\w+)\s*\(\s*(\w+)\s*\)"
    match = re.match(pointwise_no_cmp, expr.strip())
    if match:
        op, signal = match.groups()
        return (op, signal, None, None, None)

    raise ValueError(f"Cannot parse trend expression: {expr}")


class CohortCompiler:
    """
    Compile PSDL scenarios to SQL queries.

    The compiler generates PostgreSQL CTEs using templates from the
    specification, ensuring consistency across runtimes.

    Features:
        - Batch processing for large datasets
        - Population pre-filtering optimization
        - Query cost estimation
        - Parallel query hints (PostgreSQL)
    """

    def __init__(
        self,
        schema: str = "public",
        use_source_values: bool = False,
        source_value_mappings: Optional[Dict[str, str]] = None,
        dialect: str = "postgresql",
        optimization: Optional[QueryOptimizationConfig] = None,
    ):
        """
        Initialize SQL compiler.

        Args:
            schema: Database schema containing OMOP CDM tables
            use_source_values: Use source_value instead of concept_id
            source_value_mappings: Map signal names to source values
            dialect: SQL dialect (currently only "postgresql" supported)
            optimization: Query optimization configuration
        """
        self.schema = schema
        self.use_source_values = use_source_values
        self.source_value_mappings = source_value_mappings or {}
        self.dialect = dialect
        self.optimization = optimization or QueryOptimizationConfig()

    def _get_table(self, domain: str = "measurement") -> str:
        """Get fully qualified table name."""
        domain_map = {
            "measurement": "measurement",
            "observation": "observation",
            "condition": "condition_occurrence",
            "drug": "drug_exposure",
            "procedure": "procedure_occurrence",
        }
        table = domain_map.get(domain, "measurement")
        return f"{self.schema}.{table}"

    def _get_filter_condition(self, signal_name: str, signal_def: Any) -> str:
        """Generate filter condition for a signal."""
        if self.use_source_values:
            source_value = self.source_value_mappings.get(signal_name)
            if source_value is None:
                # Use signal source or name
                if hasattr(signal_def, "source") and signal_def.source:
                    source_value = signal_def.source
                else:
                    source_value = signal_name
            return f"measurement_source_value = '{source_value}'"
        else:
            # Use concept_id
            if hasattr(signal_def, "concept_id") and signal_def.concept_id:
                return f"measurement_concept_id = {signal_def.concept_id}"
            raise ValueError(f"No concept_id for signal {signal_name}")

    def _compile_trend(
        self,
        trend_name: str,
        trend_expr: str,
        signals: Dict[str, Any],
    ) -> Tuple[str, Optional[Tuple[str, float]]]:
        """
        Compile a single trend expression to CTE SQL.

        Returns:
            Tuple of (cte_sql, comparison_tuple)
            comparison_tuple is (comparison_op, threshold) or None
        """
        op, signal_name, window_str, threshold, cmp_op = parse_trend_expression(trend_expr)

        # Handle percentile special case
        percentile_value = None
        if op.startswith("percentile:"):
            percentile_value = float(op.split(":")[1])
            op = "percentile"

        # Get canonical operator name
        canonical_op = TEMPLATE_ALIASES.get(op, op)

        # Get template
        template = get_sql_template(canonical_op, self.dialect)
        if template is None:
            raise ValueError(f"No SQL template for operator: {op}")

        # Get signal definition
        signal_def = signals.get(signal_name)
        if signal_def is None:
            raise ValueError(f"Unknown signal: {signal_name}")

        # Build template parameters
        table = self._get_table("measurement")
        filter_cond = self._get_filter_condition(signal_name, signal_def)

        params = {
            "trend_name": trend_name,
            "table": table,
            "filter_cond": filter_cond,
            "value_col": "value_as_number",
            "datetime_col": "measurement_datetime",
        }

        if window_str:
            params["window_seconds"] = parse_window(window_str)

        if percentile_value is not None:
            params["percentile_value"] = percentile_value

        # Format template
        cte_sql = template["cte_template"].format(**params)

        # Return comparison info if present
        comparison = (cmp_op, threshold) if cmp_op and threshold is not None else None
        return (cte_sql, comparison)

    def _compile_logic(
        self,
        logic_name: str,
        logic_expr: str,
        trend_comparisons: Dict[str, Tuple[str, float]],
    ) -> str:
        """
        Compile a logic expression to SQL CASE expression.

        Args:
            logic_name: Name of the logic rule
            logic_expr: Boolean expression like "cr_rising AND lactate_high"
            trend_comparisons: Map of trend_name -> (comparison_op, threshold)

        Returns:
            SQL CASE expression
        """
        # Replace trend references with SQL conditions
        sql_expr = logic_expr

        # Handle AND/OR/NOT (case-insensitive)
        sql_expr = re.sub(r"\bAND\b", "AND", sql_expr, flags=re.IGNORECASE)
        sql_expr = re.sub(r"\bOR\b", "OR", sql_expr, flags=re.IGNORECASE)
        sql_expr = re.sub(r"\bNOT\b", "NOT", sql_expr, flags=re.IGNORECASE)

        # Replace trend references with their SQL conditions
        for trend_name, comparison in trend_comparisons.items():
            if comparison:
                cmp_op, threshold = comparison
                # SQL comparison
                sql_cmp = f"{trend_name}.{trend_name}_value {cmp_op} {threshold}"
                sql_expr = re.sub(rf"\b{trend_name}\b", f"({sql_cmp})", sql_expr)
            else:
                # Just check if value exists (not null)
                sql_expr = re.sub(
                    rf"\b{trend_name}\b",
                    f"({trend_name}.{trend_name}_value IS NOT NULL)",
                    sql_expr,
                )

        return f"CASE WHEN {sql_expr} THEN TRUE ELSE FALSE END AS {logic_name}"

    def compile(self, scenario: Any) -> CompiledSQL:
        """
        Compile a PSDL scenario to SQL.

        Args:
            scenario: Parsed PSDL scenario object

        Returns:
            CompiledSQL with the generated query and metadata
        """
        ctes: List[str] = []
        trend_comparisons: Dict[str, Tuple[str, float]] = {}
        trend_columns: List[str] = []
        logic_columns: List[str] = []

        # Compile trends
        if hasattr(scenario, "trends") and scenario.trends:
            for trend_name, trend_def in scenario.trends.items():
                # Get expression from trend definition (TrendExpr has raw_expr)
                if hasattr(trend_def, "raw_expr"):
                    expr = trend_def.raw_expr
                elif hasattr(trend_def, "expr"):
                    expr = trend_def.expr
                elif isinstance(trend_def, str):
                    expr = trend_def
                else:
                    expr = str(trend_def)

                cte_sql, comparison = self._compile_trend(trend_name, expr, scenario.signals)
                ctes.append(cte_sql)
                if comparison:
                    trend_comparisons[trend_name] = comparison
                trend_columns.append(f"{trend_name}.{trend_name}_value AS {trend_name}")

        # Build SELECT columns for logic
        logic_selects: List[str] = []
        if hasattr(scenario, "logic") and scenario.logic:
            for logic_name, logic_def in scenario.logic.items():
                # Get expression from logic definition
                if hasattr(logic_def, "expr"):
                    expr = logic_def.expr
                elif isinstance(logic_def, str):
                    expr = logic_def
                else:
                    expr = str(logic_def)

                logic_sql = self._compile_logic(logic_name, expr, trend_comparisons)
                logic_selects.append(logic_sql)
                logic_columns.append(logic_name)

        # Build final query
        cte_block = ",\n".join(ctes)

        # Get list of all trend names (order matters for JOINs)
        all_trend_names = list(scenario.trends.keys()) if scenario.trends else []

        # Join all trend CTEs
        trend_joins = ""
        first_trend_name = all_trend_names[0] if all_trend_names else None
        for trend_name in all_trend_names[1:]:
            trend_joins += (
                f"\nLEFT JOIN {trend_name} ON {first_trend_name}.person_id = {trend_name}.person_id"
            )

        # Build SELECT - use first trend CTE for person_id reference
        if first_trend_name:
            select_cols = [f"{first_trend_name}.person_id"]
        else:
            select_cols = ["person_id"]
        select_cols.extend(trend_columns)
        select_cols.extend(logic_selects)

        # Build FROM clause
        if first_trend_name:
            from_clause = f"{first_trend_name}"
        else:
            from_clause = f"{self.schema}.person"

        sql = f"""WITH {cte_block}

SELECT {', '.join(select_cols)}
FROM {from_clause}{trend_joins}
"""

        return CompiledSQL(
            sql=sql.strip(),
            parameters={"reference_time": "NOW()"},  # Default parameter
            trend_columns=trend_columns,
            logic_columns=logic_columns,
        )

    def compile_to_string(self, scenario: Any) -> str:
        """Compile scenario to SQL string."""
        result = self.compile(scenario)
        return result.sql

    def estimate_cost(self, scenario: Any) -> QueryCostEstimate:
        """
        Estimate query cost for a PSDL scenario.

        This helps users understand query complexity and decide on
        optimization strategies like batching.

        Args:
            scenario: Parsed PSDL scenario object

        Returns:
            QueryCostEstimate with complexity analysis and recommendations
        """
        # Count trends and extract window sizes
        trend_count = len(scenario.trends) if hasattr(scenario, "trends") and scenario.trends else 0
        _ = len(scenario.logic) if hasattr(scenario, "logic") and scenario.logic else 0  # Reserved

        # Analyze windows
        largest_window = 0
        for trend_name, trend_def in (scenario.trends or {}).items():
            if hasattr(trend_def, "raw_expr"):
                expr = trend_def.raw_expr
            elif hasattr(trend_def, "expr"):
                expr = trend_def.expr
            else:
                continue

            try:
                _, _, window_str, _, _ = parse_trend_expression(expr)
                if window_str:
                    window_seconds = parse_window(window_str)
                    largest_window = max(largest_window, window_seconds)
            except ValueError:
                pass

        # Estimate logic depth (nested AND/OR)
        logic_depth = 0
        for logic_def in (scenario.logic or {}).values():
            if hasattr(logic_def, "expr"):
                expr = logic_def.expr
            elif isinstance(logic_def, str):
                expr = logic_def
            else:
                continue

            # Count parentheses depth as proxy for complexity
            depth = max(expr.count("("), 1)
            logic_depth = max(logic_depth, depth)

        # Determine complexity
        if trend_count > 50 or logic_depth > 5:
            complexity = QueryComplexity.VERY_HIGH
        elif trend_count > 20 or logic_depth > 3 or largest_window > 604800:  # > 1 week
            complexity = QueryComplexity.HIGH
        elif trend_count > 10 or logic_depth > 2 or largest_window > 86400:  # > 1 day
            complexity = QueryComplexity.MEDIUM
        else:
            complexity = QueryComplexity.LOW

        # Build recommendations
        recommendations = []
        if complexity in (QueryComplexity.HIGH, QueryComplexity.VERY_HIGH):
            recommendations.append("Consider using batch processing for large cohorts")
        if largest_window > 604800:
            recommendations.append(
                f"Large window ({largest_window // 86400} days) may impact performance"
            )
        if trend_count > 20:
            recommendations.append(
                f"High trend count ({trend_count}) - consider splitting into multiple queries"
            )
        if logic_depth > 3:
            recommendations.append("Complex logic expression - verify query plan")

        return QueryCostEstimate(
            complexity=complexity,
            estimated_cte_count=trend_count,
            estimated_join_count=max(0, trend_count - 1),
            largest_window_seconds=largest_window,
            logic_depth=logic_depth,
            recommendations=recommendations,
        )

    def compile_batched(
        self,
        scenario: Any,
        batch_size: Optional[int] = None,
        total_patients: Optional[int] = None,
    ) -> Generator[CompiledSQL, None, None]:
        """
        Compile scenario to batched SQL queries for large datasets.

        Generates multiple queries, each processing a subset of patients.
        This is useful for cohorts with millions of patients where a
        single query would be too expensive.

        Args:
            scenario: Parsed PSDL scenario object
            batch_size: Number of patients per batch (default from config)
            total_patients: Total number of patients (for batch count calculation)

        Yields:
            CompiledSQL for each batch with batch_info populated
        """
        batch_size = batch_size or self.optimization.batch_size
        cost_estimate = self.estimate_cost(scenario) if self.optimization.estimate_cost else None

        # If total_patients is not provided, yield a single parameterized query
        if total_patients is None:
            base_sql = self.compile(scenario)
            # Add OFFSET/LIMIT parameters for manual batching
            batched_sql = base_sql.sql + "\nOFFSET :batch_offset LIMIT :batch_limit"
            yield CompiledSQL(
                sql=batched_sql,
                parameters={
                    **base_sql.parameters,
                    "batch_offset": 0,
                    "batch_limit": batch_size,
                },
                trend_columns=base_sql.trend_columns,
                logic_columns=base_sql.logic_columns,
                cost_estimate=cost_estimate,
                batch_info={
                    "batch_number": 0,
                    "total_batches": None,  # Unknown
                    "offset": 0,
                    "limit": batch_size,
                    "parameterized": True,
                },
            )
            return

        # Calculate number of batches
        total_batches = (total_patients + batch_size - 1) // batch_size
        logger.info(
            f"Compiling {total_batches} batches for {total_patients} patients "
            f"(batch_size={batch_size})"
        )

        for batch_num in range(total_batches):
            offset = batch_num * batch_size
            limit = min(batch_size, total_patients - offset)

            base_sql = self.compile(scenario)
            batched_sql = base_sql.sql + f"\nOFFSET {offset} LIMIT {limit}"

            yield CompiledSQL(
                sql=batched_sql,
                parameters=base_sql.parameters,
                trend_columns=base_sql.trend_columns,
                logic_columns=base_sql.logic_columns,
                cost_estimate=cost_estimate,
                batch_info={
                    "batch_number": batch_num,
                    "total_batches": total_batches,
                    "offset": offset,
                    "limit": limit,
                    "parameterized": False,
                },
            )

    def compile_with_population_filter(
        self,
        scenario: Any,
        population_cte: Optional[str] = None,
    ) -> CompiledSQL:
        """
        Compile scenario with population pre-filtering.

        This optimizes queries by filtering patients early in the query
        plan, reducing the amount of data processed by trend CTEs.

        Args:
            scenario: Parsed PSDL scenario object
            population_cte: Optional custom CTE for population filtering

        Returns:
            CompiledSQL with population filter applied early
        """
        # Build population filter from scenario.population if present
        if population_cte is None and hasattr(scenario, "population") and scenario.population:
            pop = scenario.population
            conditions = []

            # Handle include conditions
            if hasattr(pop, "include") and pop.include:
                for cond in pop.include:
                    conditions.append(f"({cond})")

            # Handle exclude conditions
            if hasattr(pop, "exclude") and pop.exclude:
                for cond in pop.exclude:
                    conditions.append(f"NOT ({cond})")

            if conditions:
                where_clause = " AND ".join(conditions)
                population_cte = f"""eligible_population AS (
    SELECT DISTINCT person_id
    FROM {self.schema}.person
    WHERE {where_clause}
)"""

        # Compile base query
        base_result = self.compile(scenario)

        if population_cte:
            # Prepend population CTE and add filter to main query
            sql_with_filter = f"WITH {population_cte},\n{base_result.sql[5:]}"  # Skip 'WITH '

            # Add population filter to FROM clause
            # This is a simplified approach - more sophisticated would require
            # parsing and modifying the SQL AST
            sql_with_filter = sql_with_filter.replace(
                "FROM ",
                "FROM eligible_population ep\nINNER JOIN ",
                1,
            )
            # Add join condition (simplified - assumes first CTE has person_id)
            lines = sql_with_filter.split("\n")
            for i, line in enumerate(lines):
                if "INNER JOIN" in line and i + 1 < len(lines):
                    # Find the table/CTE being joined
                    parts = line.split("INNER JOIN")
                    if len(parts) > 1:
                        joined_table = parts[1].strip().split()[0]
                        lines[i] = f"{line} ON ep.person_id = {joined_table}.person_id"
                        break
            sql_with_filter = "\n".join(lines)

            return CompiledSQL(
                sql=sql_with_filter,
                parameters=base_result.parameters,
                trend_columns=base_result.trend_columns,
                logic_columns=base_result.logic_columns,
                cost_estimate=(
                    self.estimate_cost(scenario) if self.optimization.estimate_cost else None
                ),
            )

        return base_result

    def add_parallel_hints(self, sql: str, workers: Optional[int] = None) -> str:
        """
        Add PostgreSQL parallel query hints to SQL.

        Args:
            sql: Base SQL query
            workers: Number of parallel workers (default from config)

        Returns:
            SQL with parallel query hints
        """
        if self.dialect != "postgresql":
            return sql

        workers = workers or self.optimization.parallel_workers_per_gather

        # Add SET statements for parallel query configuration
        hints = f"""-- Parallel query hints for large cohort processing
SET max_parallel_workers_per_gather = {workers};
SET parallel_tuple_cost = 0.001;
SET parallel_setup_cost = 100;

"""
        return hints + sql


# Legacy alias
SQLCompiler = CohortCompiler


# Convenience function
def compile_scenario_to_sql(
    scenario: Any,
    schema: str = "public",
    use_source_values: bool = False,
    source_value_mappings: Optional[Dict[str, str]] = None,
) -> str:
    """
    Compile a PSDL scenario to PostgreSQL SQL.

    Args:
        scenario: Parsed PSDL scenario
        schema: Database schema
        use_source_values: Use source_value instead of concept_id
        source_value_mappings: Map signal names to source values

    Returns:
        SQL query string
    """
    compiler = CohortCompiler(
        schema=schema,
        use_source_values=use_source_values,
        source_value_mappings=source_value_mappings,
    )
    return compiler.compile_to_string(scenario)
