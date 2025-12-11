"""
PSDL Cohort Runtime - SQL-based batch evaluation.

This runtime compiles PSDL scenarios to SQL queries for efficient
evaluation across large patient populations. It's optimized for:
- Population health analytics
- Research cohort studies
- Algorithm validation at scale

Usage:
    from psdl.runtimes.cohort import CohortCompiler

    compiler = CohortCompiler(schema="cdm", use_source_values=True)
    result = compiler.compile(scenario)

    # Execute with SQLAlchemy
    with engine.connect() as conn:
        rows = conn.execute(text(result.sql), result.parameters)
"""

from .compiler import (
    CohortCompiler,
    CompiledSQL,
    compile_scenario_to_sql,
    parse_trend_expression,
    parse_window,
)

# Legacy alias
SQLCompiler = CohortCompiler

__all__ = [
    "CohortCompiler",
    "SQLCompiler",
    "CompiledSQL",
    "compile_scenario_to_sql",
    "parse_window",
    "parse_trend_expression",
]
