"""
PSDL Execution Module - Unified interface for batch and streaming execution.

This module provides execution backends for PSDL scenarios:
- Batch: Evaluate scenarios against historical data
- Streaming: Deploy scenarios as real-time streaming jobs (Flink)

Usage:
    # Batch execution
    from reference.python.execution import BatchEvaluator

    evaluator = BatchEvaluator()
    result = evaluator.evaluate(scenario, patient_data)

    # Streaming execution (requires PyFlink)
    from reference.python.execution import StreamingEvaluator

    evaluator = StreamingEvaluator(runtime="flink")
    job = evaluator.deploy(scenario, kafka_config)

The same clinical scenario (signals, trends, logic) works in both modes.
Execution mode is a deployment concern, not part of the clinical specification.
"""

from .batch import DataPoint, InMemoryBackend, PSDLEvaluator

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
    "DataPoint",
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
