"""
PSDL SQL Compiler - Generate SQL queries from PSDL scenarios.

This module compiles PSDL scenarios into SQL queries that can be executed
on OMOP CDM databases for cohort-level evaluation.

Architecture:
    The SQL compiler follows a spec-driven approach:
    1. Parse PSDL scenario (signals, trends, logic)
    2. Generate CTEs for each trend using templates from operators.yaml
    3. Combine CTEs into a single query with logic evaluation

Usage:
    from psdl.parser import parse_scenario
    from psdl.execution.sql_compiler import SQLCompiler

    scenario = parse_scenario("scenarios/aki_detection.yaml")
    compiler = SQLCompiler(schema="public", use_source_values=True)
    sql = compiler.compile(scenario)
    print(sql)
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from .._generated.sql_templates import (
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

    sys.path.insert(0, str(Path(__file__).parent.parent))
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


@dataclass
class CompiledSQL:
    """Result of SQL compilation."""

    sql: str
    parameters: Dict[str, Any]
    trend_columns: List[str]
    logic_columns: List[str]


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


class SQLCompiler:
    """
    Compile PSDL scenarios to SQL queries.

    The compiler generates PostgreSQL CTEs using templates from the
    specification, ensuring consistency across runtimes.
    """

    def __init__(
        self,
        schema: str = "public",
        use_source_values: bool = False,
        source_value_mappings: Optional[Dict[str, str]] = None,
        dialect: str = "postgresql",
    ):
        """
        Initialize SQL compiler.

        Args:
            schema: Database schema containing OMOP CDM tables
            use_source_values: Use source_value instead of concept_id
            source_value_mappings: Map signal names to source values
            dialect: SQL dialect (currently only "postgresql" supported)
        """
        self.schema = schema
        self.use_source_values = use_source_values
        self.source_value_mappings = source_value_mappings or {}
        self.dialect = dialect

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
    compiler = SQLCompiler(
        schema=schema,
        use_source_values=use_source_values,
        source_value_mappings=source_value_mappings,
    )
    return compiler.compile_to_string(scenario)
