"""
PSDL Runtimes - Execution environments for PSDL scenarios.

This module provides different runtime implementations for executing
PSDL scenarios:

| Runtime | Purpose | Implementation | Use Case |
|---------|---------|----------------|----------|
| Single  | ONE patient evaluation | Python | Real-time alerting |
| Cohort  | MANY patients (batch) | SQL | Research, population health |
| Streaming | Continuous evaluation | Flink | ICU monitoring |

Usage:
    # Single patient evaluation
    from psdl.runtimes.single import SinglePatientEvaluator, InMemoryBackend

    evaluator = SinglePatientEvaluator(scenario, backend)
    result = evaluator.evaluate(patient_id=123)

    # Cohort analysis (SQL)
    from psdl.runtimes.cohort import CohortCompiler

    compiler = CohortCompiler(schema="cdm", use_source_values=True)
    sql = compiler.compile(scenario)

    # Streaming (requires PyFlink)
    from psdl.runtimes.streaming import StreamingCompiler

    compiler = StreamingCompiler(scenario)
    flink_job = compiler.compile()
"""

# Cohort runtime
from .cohort import CohortCompiler, CompiledSQL, compile_scenario_to_sql

# Single patient runtime
from .single import (
    DataBackend,
    EvaluationContext,
    EvaluationResult,
    InMemoryBackend,
    SinglePatientEvaluator,
)

# Legacy aliases for backward compatibility
PSDLEvaluator = SinglePatientEvaluator
SQLCompiler = CohortCompiler

# Streaming imports - optional, requires PyFlink
try:
    from ..execution.streaming import (
        FLINK_AVAILABLE,
        ClinicalEvent,
        FlinkJob,
        FlinkRuntime,
        LogicResult,
        StreamingCompiler,
        StreamingConfig,
        StreamingEvaluator,
        TrendResult,
    )

    STREAMING_AVAILABLE = True
except ImportError:
    FLINK_AVAILABLE = False
    STREAMING_AVAILABLE = False
    ClinicalEvent = None
    FlinkJob = None
    FlinkRuntime = None
    LogicResult = None
    StreamingCompiler = None
    StreamingConfig = None
    StreamingEvaluator = None
    TrendResult = None

__all__ = [
    # Single patient runtime
    "SinglePatientEvaluator",
    "InMemoryBackend",
    "DataBackend",
    "EvaluationResult",
    "EvaluationContext",
    # Cohort runtime
    "CohortCompiler",
    "CompiledSQL",
    "compile_scenario_to_sql",
    # Legacy aliases
    "PSDLEvaluator",
    "SQLCompiler",
    # Streaming runtime
    "StreamingEvaluator",
    "StreamingCompiler",
    "StreamingConfig",
    "FlinkRuntime",
    "FlinkJob",
    "ClinicalEvent",
    "TrendResult",
    "LogicResult",
    # Availability flags
    "FLINK_AVAILABLE",
    "STREAMING_AVAILABLE",
]
