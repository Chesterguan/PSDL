"""
Auto-generated SQL templates from spec/operators.yaml
Generated: 2025-12-15T12:01:47.799507

DO NOT EDIT - Regenerate with: python tools/codegen.py --sql
"""

from typing import Dict, List, Optional, TypedDict


class SQLTemplate(TypedDict, total=False):
    """SQL template for an operator."""

    name: str
    cte_template: str
    description: str
    placeholders: List[str]


# PostgreSQL CTE templates for windowed operators
POSTGRESQL_TEMPLATES: Dict[str, SQLTemplate] = {
    "delta": {
        "name": "delta",
        "description": "Compute absolute change: last_value - first_value in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """-- Delta computation using CTEs
{trend_name}_first AS (
    SELECT person_id, {value_col} as value,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} ASC) as rn
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
),
{trend_name}_last AS (
    SELECT person_id, {value_col} as value,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} DESC) as rn
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
),
{trend_name} AS (
    SELECT l.person_id,
           (l.value - f.value) as {trend_name}_value
    FROM {trend_name}_last l
    JOIN {trend_name}_first f ON l.person_id = f.person_id
    WHERE l.rn = 1 AND f.rn = 1
)""",
    },
    "slope": {
        "name": "slope",
        "description": "Compute linear regression slope over window (units per second)",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """-- PostgreSQL REGR_SLOPE for linear regression
{trend_name} AS (
    SELECT person_id,
           REGR_SLOPE(
               {value_col},
               EXTRACT(EPOCH FROM {datetime_col})
           ) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
    HAVING COUNT(*) >= 2
)""",
    },
    "sma": {
        "name": "sma",
        "description": "Compute simple moving average over window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           AVG({value_col}) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
)""",
    },
    "min": {
        "name": "min",
        "description": "Find minimum value in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           MIN({value_col}) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
)""",
    },
    "max": {
        "name": "max",
        "description": "Find maximum value in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           MAX({value_col}) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
)""",
    },
    "count": {
        "name": "count",
        "description": "Count observations in window (includes null values)",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """-- IMPORTANT: count ALL observations including nulls
-- Use COUNT(*) not COUNT(value_col) to include nulls
{trend_name} AS (
    SELECT person_id,
           COUNT(*) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
    GROUP BY person_id
)""",
    },
    "first": {
        "name": "first",
        "description": "Get the earliest value in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """{trend_name}_data AS (
    SELECT person_id,
           {value_col} as value,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} ASC) as rn
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
),
{trend_name} AS (
    SELECT person_id, value as {trend_name}_value
    FROM {trend_name}_data WHERE rn = 1
)""",
    },
    "std": {
        "name": "std",
        "description": "Compute sample standard deviation in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           STDDEV_SAMP({value_col}) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
    HAVING COUNT(*) >= 2
)""",
    },
    "percentile": {
        "name": "percentile",
        "description": "Compute percentile value in window",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
            "window_seconds",
            "percentile_value",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           PERCENTILE_CONT({p} / 100.0) WITHIN GROUP (ORDER BY {value_col}) as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
      AND {datetime_col} <= :reference_time
      AND {value_col} IS NOT NULL
    GROUP BY person_id
)""",
    },
}

# PostgreSQL templates for pointwise operators
POSTGRESQL_POINTWISE_TEMPLATES: Dict[str, SQLTemplate] = {
    "last": {
        "name": "last",
        "description": "Get the most recent value for signal",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "value_col",
            "datetime_col",
        ],
        "cte_template": """{trend_name}_data AS (
    SELECT person_id,
           {value_col} as value,
           ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} DESC) as rn
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} <= :reference_time
),
{trend_name} AS (
    SELECT person_id, value as {trend_name}_value
    FROM {trend_name}_data WHERE rn = 1
)""",
    },
    "exists": {
        "name": "exists",
        "description": "Check if any data exists for signal",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "datetime_col",
        ],
        "cte_template": """{trend_name} AS (
    SELECT person_id,
           CASE WHEN COUNT(*) > 0 THEN true ELSE false END as {trend_name}_value
    FROM {table}
    WHERE {filter_cond}
      AND {datetime_col} <= :reference_time
    GROUP BY person_id
)""",
    },
    "missing": {
        "name": "missing",
        "description": "Check if no data exists for signal (inverse of exists)",
        "placeholders": [
            "trend_name",
            "table",
            "filter_cond",
            "datetime_col",
        ],
        "cte_template": """-- missing is computed as NOT EXISTS
-- For patients with no data, use LEFT JOIN and check for NULL
{trend_name} AS (
    SELECT p.person_id,
           CASE WHEN s.person_id IS NULL THEN true ELSE false END as {trend_name}_value
    FROM {schema}.person p
    LEFT JOIN (
        SELECT DISTINCT person_id
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} <= :reference_time
    ) s ON p.person_id = s.person_id
)""",
    },
}

# Alias mapping
TEMPLATE_ALIASES: Dict[str, str] = {
    "stddev": "std",
}


def get_sql_template(operator: str, dialect: str = "postgresql") -> Optional[SQLTemplate]:
    """Get SQL template for an operator."""
    # Handle aliases
    canonical = TEMPLATE_ALIASES.get(operator, operator)

    if dialect == "postgresql":
        template = POSTGRESQL_TEMPLATES.get(canonical)
        if template:
            return template
        return POSTGRESQL_POINTWISE_TEMPLATES.get(canonical)

    return None


def is_windowed_operator(operator: str) -> bool:
    """Check if operator requires a time window."""
    canonical = TEMPLATE_ALIASES.get(operator, operator)
    return canonical in POSTGRESQL_TEMPLATES
