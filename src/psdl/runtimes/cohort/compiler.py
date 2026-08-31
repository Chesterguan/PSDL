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
from typing import Any, Dict, Generator, Iterator, List, Optional, Set, Tuple

from ..batch import BatchResult, SQLBatchRuntime

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
    # NOTE: all patterns use re.fullmatch. re.match only anchors the start,
    # which silently swallowed compound expressions like
    # "last(Cr) / min(Cr, 7d)" as plain "last(Cr)" — a wrong-values bug.
    # Compound arithmetic expressions are handled by the AST path in
    # CohortCompiler._compile_trend, not here.

    # Pattern for percentile: percentile(signal, window, p) cmp value
    # (checked first: the generic windowed pattern would misread it)
    percentile_pattern = (
        r"percentile\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*,\s*([\d.]+)\s*\)"
        r"\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    )
    match = re.fullmatch(percentile_pattern, expr.strip())
    if match:
        signal, window, p_value, cmp_op, threshold = match.groups()
        # Store percentile value in operator name for later extraction
        return (f"percentile:{p_value}", signal, window, float(threshold), cmp_op)

    # Pattern for windowed operators with comparison: op(signal, window) cmp value
    windowed_pattern = (
        r"(\w+)\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*\)\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    )
    match = re.fullmatch(windowed_pattern, expr.strip())
    if match:
        op, signal, window, cmp_op, threshold = match.groups()
        return (op, signal, window, float(threshold), cmp_op)

    # Pattern for windowed operators without comparison: op(signal, window)
    windowed_no_cmp = r"(\w+)\s*\(\s*(\w+)\s*,\s*(\d+[smhdw])\s*\)"
    match = re.fullmatch(windowed_no_cmp, expr.strip())
    if match:
        op, signal, window = match.groups()
        return (op, signal, window, None, None)

    # Pattern for pointwise operators with comparison: op(signal) cmp value
    pointwise_pattern = r"(\w+)\s*\(\s*(\w+)\s*\)\s*(>=|<=|>|<|==|!=)\s*([\d.\-]+)"
    match = re.fullmatch(pointwise_pattern, expr.strip())
    if match:
        op, signal, cmp_op, threshold = match.groups()
        return (op, signal, None, float(threshold), cmp_op)

    # Pattern for pointwise operators without comparison: op(signal)
    pointwise_no_cmp = r"(\w+)\s*\(\s*(\w+)\s*\)"
    match = re.fullmatch(pointwise_no_cmp, expr.strip())
    if match:
        op, signal = match.groups()
        return (op, signal, None, None, None)

    raise ValueError(f"Cannot parse trend expression: {expr}")


class CohortCompiler(SQLBatchRuntime):
    """
    Compile PSDL scenarios to SQL queries.

    The compiler generates PostgreSQL CTEs using templates from the
    specification, ensuring consistency across runtimes.

    v0.4 (RFC-0008): Implements SQLBatchRuntime interface. When a
    dataset_spec is provided, uses it for table/column resolution
    instead of hardcoded OMOP names.

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
        dataset_spec: Any = None,
    ):
        """
        Initialize SQL compiler.

        Args:
            schema: Database schema containing OMOP CDM tables
            use_source_values: Use source_value instead of concept_id
            source_value_mappings: Map signal names to source values
            dialect: SQL dialect (currently only "postgresql" supported)
            optimization: Query optimization configuration
            dataset_spec: Optional DatasetSpec for binding resolution (RFC-0008)
        """
        self.schema = schema
        self.use_source_values = use_source_values
        self.source_value_mappings = source_value_mappings or {}
        self.dialect = dialect
        self.optimization = optimization or QueryOptimizationConfig()
        self.dataset_spec = dataset_spec

    # v0.4 (RFC-0008): SQLBatchRuntime interface methods

    @property
    def capabilities(self) -> Set[str]:
        """Declare runtime capabilities."""
        return {"sql", "parallel"}

    def get_sql_dialect(self) -> str:
        """Return the SQL dialect name."""
        return self.dialect

    def render_interval(self, seconds: int) -> str:
        """Render a time interval in PostgreSQL SQL."""
        return f"INTERVAL '{seconds} seconds'"

    def execute(
        self,
        scenario: Any,
        dataset_spec: Any = None,
        patient_ids: Optional[List[str]] = None,
    ) -> Iterator[BatchResult]:
        """Not implemented — CohortCompiler only compiles, not executes."""
        raise NotImplementedError(
            "CohortCompiler only compiles SQL queries. "
            "Execute the compiled SQL against your database directly."
        )

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
        """Generate filter condition for a signal (legacy OMOP fallback)."""
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

    def _resolve_signal_binding(self, signal_name: str, signal_def: Any) -> Dict[str, str]:
        """Resolve table/columns/filter for a signal (RFC-0008).

        When dataset_spec is available, uses it for vendor-neutral resolution.
        Falls through to legacy hardcoded OMOP resolution otherwise.

        Returns:
            Dict with keys: table, filter_cond, value_col, datetime_col
        """
        if self.dataset_spec is not None:
            # Get the signal's semantic ref for dataset_spec lookup
            signal_ref = getattr(signal_def, "ref", None) or signal_name
            try:
                binding = self.dataset_spec.resolve(signal_ref)
                filter_sql = (
                    binding.filter_predicates.to_sql()
                    if binding.filter_predicates
                    else binding.filter_expr
                )
                return {
                    "table": binding.table,
                    "filter_cond": filter_sql,
                    "value_col": binding.value_field,
                    "datetime_col": binding.time_field,
                }
            except (KeyError, Exception):
                pass  # Fall through to legacy resolution

        # Legacy: hardcoded OMOP resolution
        domain = getattr(signal_def, "domain", None)
        domain_str = domain.value if hasattr(domain, "value") else "measurement"
        return {
            "table": self._get_table(domain_str),
            "filter_cond": self._get_filter_condition(signal_name, signal_def),
            "value_col": "value_as_number",
            "datetime_col": "measurement_datetime",
        }

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
        try:
            op, signal_name, window_str, threshold, cmp_op = parse_trend_expression(trend_expr)
        except ValueError:
            # Not a simple operator call — try the full AST path
            # (compound arithmetic like "last(Cr) / min(Cr, 7d)").
            return (self._compile_arith_trend(trend_name, trend_expr, signals), None)

        window_seconds = parse_window(window_str) if window_str else None
        cte_sql = self._render_operator_cte(
            trend_name, op, signal_name, signals, window_seconds=window_seconds
        )

        # Return comparison info if present
        comparison = (cmp_op, threshold) if cmp_op and threshold is not None else None
        return (cte_sql, comparison)

    def _render_operator_cte(
        self,
        cte_name: str,
        op: str,
        signal_name: str,
        signals: Dict[str, Any],
        window_seconds: Optional[int] = None,
    ) -> str:
        """Render one temporal operator call as a CTE named {cte_name}
        exposing (person_id, {cte_name}_value)."""
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

        # Build template parameters — use dataset_spec if available (RFC-0008)
        resolved = self._resolve_signal_binding(signal_name, signal_def)

        params = {
            "trend_name": cte_name,
            **resolved,
        }

        if window_seconds is not None:
            params["window_seconds"] = window_seconds

        if percentile_value is not None:
            params["percentile_value"] = percentile_value

        return template["cte_template"].format(**params)

    def _compile_arith_trend(
        self, trend_name: str, trend_expr: str, signals: Dict[str, Any]
    ) -> str:
        """Compile a compound arithmetic trend expression.

        Each temporal operator call becomes its own component CTE
        ({trend_name}__cN); a combining CTE joins them per person_id and
        computes the arithmetic. Division guards zero with NULLIF, so SQL
        NULL mirrors the Python runtime's None semantics.
        """
        from psdl._generated.ast_types import (
            ArithExpr,
            NumberLiteral,
            TemporalCall,
            TrendExpression,
        )
        from psdl.expression_parser import PSDLExpressionError
        from psdl.expression_parser import parse_trend_expression as parse_trend_ast

        try:
            ast = parse_trend_ast(trend_expr)
        except PSDLExpressionError as e:
            raise ValueError(f"Cannot parse trend expression: {trend_expr}") from e
        if not isinstance(ast, ArithExpr):
            raise ValueError(f"Cannot compile trend expression: {trend_expr}")

        # Collect temporal calls left-to-right (deterministic component order)
        calls: List[Any] = []

        def collect(node: Any) -> None:
            if isinstance(node, TrendExpression):
                collect(node.temporal)
            elif isinstance(node, TemporalCall):
                calls.append(node)
            elif isinstance(node, ArithExpr):
                collect(node.left)
                collect(node.right)

        collect(ast)
        if not calls:
            raise ValueError(f"No temporal operator calls in trend expression: {trend_expr}")

        component_ctes: List[str] = []
        names: Dict[int, str] = {}
        for i, call in enumerate(calls):
            comp_name = f"{trend_name}__c{i}"
            names[id(call)] = comp_name
            window_seconds = call.window.seconds if call.window else None
            op = call.operator
            if call.percentile is not None:
                op = f"percentile:{call.percentile}"
            component_ctes.append(
                self._render_operator_cte(
                    comp_name, op, call.signal, signals, window_seconds=window_seconds
                )
            )

        def render(node: Any) -> str:
            if isinstance(node, TrendExpression):
                return render(node.temporal)
            if isinstance(node, TemporalCall):
                n = names[id(node)]
                return f"{n}.{n}_value"
            if isinstance(node, NumberLiteral):
                return repr(float(node.value))
            if isinstance(node, (int, float)):
                return repr(float(node))
            if isinstance(node, ArithExpr):
                left, right = render(node.left), render(node.right)
                if node.operator == "/":
                    return f"({left} / NULLIF({right}, 0))"
                return f"({left} {node.operator} {right})"
            raise ValueError(f"Cannot compile trend AST node: {type(node).__name__}")

        first = names[id(calls[0])]
        joins = "".join(
            f"\n    LEFT JOIN {names[id(c)]} ON {first}.person_id = {names[id(c)]}.person_id"
            for c in calls[1:]
        )
        combining = (
            f"{trend_name} AS (\n"
            f"    SELECT {first}.person_id, {render(ast)} AS {trend_name}_value\n"
            f"    FROM {first}{joins}\n"
            f")"
        )
        return ",\n".join(component_ctes + [combining])

    def _compile_logic(
        self,
        logic_name: str,
        logic_exprs: Dict[str, str],
        trend_names: Set[str],
        trend_comparisons: Dict[str, Tuple[str, float]],
        memo: Dict[str, str],
    ) -> str:
        """
        Compile a logic expression to a SQL CASE expression over the
        trend_values relation (where each trend is a plain column).

        Logic-to-logic references are inlined recursively (the logic layer
        is a DAG), because SQL cannot reference a SELECT alias from the
        same SELECT. Comparisons are wrapped in COALESCE(..., FALSE) so
        NULL trend values behave exactly like the Python runtime's
        None -> False semantics.
        """
        sql_expr = self._logic_node_sql(
            logic_name, logic_exprs, trend_names, trend_comparisons, memo, set()
        )
        return f"CASE WHEN {sql_expr} THEN TRUE ELSE FALSE END AS {logic_name}"

    def _logic_node_sql(
        self,
        name: str,
        logic_exprs: Dict[str, str],
        trend_names: Set[str],
        trend_comparisons: Dict[str, Tuple[str, float]],
        memo: Dict[str, str],
        stack: Set[str],
    ) -> str:
        """SQL boolean expression for one named logic node (memoized)."""
        if name in memo:
            return memo[name]
        if name in stack:
            raise ValueError(f"Circular logic reference involving '{name}'")
        stack.add(name)

        from psdl.expression_parser import parse_logic_expression

        ast = parse_logic_expression(logic_exprs[name])
        sql = self._logic_ast_sql(ast, logic_exprs, trend_names, trend_comparisons, memo, stack)

        stack.discard(name)
        memo[name] = sql
        return sql

    def _logic_ast_sql(
        self,
        node: Any,
        logic_exprs: Dict[str, str],
        trend_names: Set[str],
        trend_comparisons: Dict[str, Tuple[str, float]],
        memo: Dict[str, str],
        stack: Set[str],
    ) -> str:
        """Render a logic AST node as a SQL boolean expression."""
        from psdl._generated.ast_types import (
            AndExpr,
            ComparisonExpr,
            NotExpr,
            NumberLiteral,
            OrExpr,
            TermRef,
        )

        cmp_ops = {"==": "=", "!=": "<>"}

        def operand_sql(operand: Any) -> str:
            if isinstance(operand, TermRef):
                if operand.name in trend_names:
                    return operand.name
                raise ValueError(f"Comparison references unknown trend: {operand.name}")
            if isinstance(operand, NumberLiteral):
                return repr(float(operand.value))
            if isinstance(operand, (int, float)):
                return repr(float(operand))
            raise ValueError(f"Unsupported comparison operand: {type(operand).__name__}")

        if isinstance(node, TermRef):
            if node.name in logic_exprs:
                inner = self._logic_node_sql(
                    node.name, logic_exprs, trend_names, trend_comparisons, memo, stack
                )
                return f"({inner})"
            if node.name in trend_comparisons:
                cmp_op, threshold = trend_comparisons[node.name]
                cmp_op = cmp_ops.get(cmp_op, cmp_op)
                return f"COALESCE(({node.name} {cmp_op} {threshold}), FALSE)"
            if node.name in trend_names:
                # Bare trend reference: truthy iff present and non-zero
                # (matches Python bool(value) with None -> False)
                return f"COALESCE(({node.name} <> 0), FALSE)"
            raise ValueError(f"Unknown reference in logic expression: {node.name}")
        if isinstance(node, ComparisonExpr):
            op = cmp_ops.get(node.operator, node.operator)
            left = operand_sql(node.left)
            right = operand_sql(node.right)
            return f"COALESCE(({left} {op} {right}), FALSE)"
        if isinstance(node, NotExpr):
            inner = self._logic_ast_sql(
                node.operand, logic_exprs, trend_names, trend_comparisons, memo, stack
            )
            return f"(NOT {inner})"
        if isinstance(node, AndExpr):
            parts = [
                self._logic_ast_sql(op, logic_exprs, trend_names, trend_comparisons, memo, stack)
                for op in node.operands
            ]
            return "(" + " AND ".join(parts) + ")"
        if isinstance(node, OrExpr):
            parts = [
                self._logic_ast_sql(op, logic_exprs, trend_names, trend_comparisons, memo, stack)
                for op in node.operands
            ]
            return "(" + " OR ".join(parts) + ")"
        raise ValueError(f"Cannot compile logic AST node: {type(node).__name__}")

    def compile(self, scenario: Any, dataset_spec: Any = None) -> CompiledSQL:
        """
        Compile a PSDL scenario to SQL.

        Args:
            scenario: Parsed PSDL scenario object
            dataset_spec: Optional DatasetSpec override for binding resolution

        Returns:
            CompiledSQL with the generated query and metadata
        """
        # Allow dataset_spec override per-call
        if dataset_spec is not None:
            prev = self.dataset_spec
            self.dataset_spec = dataset_spec
            try:
                return self._compile_impl(scenario)
            finally:
                self.dataset_spec = prev
        return self._compile_impl(scenario)

    def _compile_impl(self, scenario: Any) -> CompiledSQL:
        """Internal compile implementation."""
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
                trend_columns.append(trend_name)

        # Collect logic expressions (compiled below, over trend_values)
        logic_exprs: Dict[str, str] = {}
        if hasattr(scenario, "logic") and scenario.logic:
            for logic_name, logic_def in scenario.logic.items():
                # Get expression from logic definition
                if hasattr(logic_def, "expr"):
                    expr = logic_def.expr
                elif isinstance(logic_def, str):
                    expr = logic_def
                else:
                    expr = str(logic_def)
                logic_exprs[logic_name] = expr

        # Get list of all trend names (order matters for JOINs)
        all_trend_names = list(scenario.trends.keys()) if scenario.trends else []
        first_trend_name = all_trend_names[0] if all_trend_names else None

        # trend_values CTE: one row per person, one plain column per trend.
        # Logic is computed over these columns in the final SELECT — SQL
        # cannot compare CTE names or reference same-SELECT aliases.
        if first_trend_name:
            trend_joins = ""
            for trend_name in all_trend_names[1:]:
                trend_joins += (
                    f"\n    LEFT JOIN {trend_name}"
                    f" ON {first_trend_name}.person_id = {trend_name}.person_id"
                )
            value_cols = "".join(f",\n           {t}.{t}_value AS {t}" for t in all_trend_names)
            ctes.append(
                f"trend_values AS (\n"
                f"    SELECT {first_trend_name}.person_id{value_cols}\n"
                f"    FROM {first_trend_name}{trend_joins}\n"
                f")"
            )

        # Compile logic over trend_values columns
        logic_selects: List[str] = []
        memo: Dict[str, str] = {}
        trend_name_set = set(all_trend_names)
        for logic_name in logic_exprs:
            logic_sql = self._compile_logic(
                logic_name, logic_exprs, trend_name_set, trend_comparisons, memo
            )
            logic_selects.append(logic_sql)
            logic_columns.append(logic_name)

        # Build final query
        select_cols = ["person_id"]
        select_cols.extend(all_trend_names)
        select_cols.extend(logic_selects)

        if first_trend_name:
            from_clause = "trend_values"
            cte_block = ",\n".join(ctes)
            sql = f"""WITH {cte_block}

SELECT {', '.join(select_cols)}
FROM {from_clause}
"""
        else:
            # No trends: nothing to join; logic (if any) has nothing to
            # reference, so this is a bare person scan.
            sql = f"""SELECT {', '.join(select_cols)}
FROM {self.schema}.person
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
