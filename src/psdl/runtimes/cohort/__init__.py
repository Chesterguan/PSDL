"""
PSDL Cohort Runtime - SQL-based batch evaluation.

This runtime compiles PSDL scenarios to SQL queries for efficient
evaluation across large patient populations. It's optimized for:
- Population health analytics
- Research cohort studies
- Algorithm validation at scale

Features:
- Batch processing for large datasets
- Population pre-filtering optimization
- Query cost estimation
- Parallel query hints (PostgreSQL)

Usage:
    from psdl.runtimes.cohort import CohortCompiler

    compiler = CohortCompiler(schema="cdm", use_source_values=True)
    result = compiler.compile(scenario)

    # Execute with SQLAlchemy
    with engine.connect() as conn:
        rows = conn.execute(text(result.sql), result.parameters)

    # For large datasets, use batch processing:
    for batch in compiler.compile_batched(scenario, total_patients=1000000):
        print(f"Batch {batch.batch_info['batch_number']}")
        conn.execute(text(batch.sql))

    # Get query cost estimate:
    cost = compiler.estimate_cost(scenario)
    if cost.should_batch(cohort_size=1000000):
        batch_size = cost.recommended_batch_size()
"""

from .compiler import (
    CohortCompiler,
    CompiledSQL,
    QueryComplexity,
    QueryCostEstimate,
    QueryOptimizationConfig,
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
    "QueryComplexity",
    "QueryCostEstimate",
    "QueryOptimizationConfig",
    "compile_scenario_to_sql",
    "parse_window",
    "parse_trend_expression",
]
