"""
PSDL Execution Module - Unified interface for batch and streaming execution.

DEPRECATED: This module is maintained for backward compatibility.
New code should import from psdl.runtimes instead:

    # New imports (recommended)
    from psdl.runtimes.single import SinglePatientEvaluator, InMemoryBackend
    from psdl.runtimes.cohort import CohortCompiler

    # Old imports (deprecated, still work)
    from psdl.execution import PSDLEvaluator, InMemoryBackend

PSDL supports two execution modes based on timing:

1. **Batch (Retrospective)** - For research and historical analysis
   - Data source: OMOP CDM databases
   - Auto-optimization: SQL push-down for large cohorts
   - Use case: Cohort studies, algorithm validation, research

2. **Streaming (Real-time)** - For live patient monitoring
   - Data source: FHIR events, Kafka streams
   - Runtime: Apache Flink (PyFlink)
   - Use case: ICU monitoring, clinical alerts

The same clinical scenario (signals, trends, logic) works in both modes.
Execution mode is a deployment concern, not part of the clinical specification.

Usage:
    # Batch execution (auto-selects best strategy)
    from psdl.execution import PSDLEvaluator

    evaluator = PSDLEvaluator(scenario, backend)
    results = evaluator.evaluate_cohort()  # Auto-optimized

    # Single patient
    result = evaluator.evaluate_patient(patient_id=123)

    # Streaming execution (requires PyFlink)
    from psdl.execution import StreamingEvaluator

    evaluator = StreamingEvaluator(runtime="flink")
    job = evaluator.deploy(scenario, kafka_config)
"""

# Import DataPoint from operators (needed by many users of this module)
from ..operators import DataPoint

# Re-export from batch.py for backward compatibility
# Note: batch.py still exists and works, so existing code continues to work
from .batch import (
    DataBackend,
    EvaluationContext,
    EvaluationResult,
    InMemoryBackend,
    PSDLEvaluator,
    SQLCompiler,
)

# Batch evaluator aliases
BatchEvaluator = PSDLEvaluator

# Streaming imports - optional, requires PyFlink
try:
    from .streaming import (
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
    # Batch execution
    "BatchEvaluator",
    "PSDLEvaluator",
    "InMemoryBackend",
    "DataBackend",
    "DataPoint",
    "EvaluationContext",
    "EvaluationResult",
    "SQLCompiler",
    # Streaming execution
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
