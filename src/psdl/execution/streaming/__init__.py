"""
PSDL Streaming Execution - Apache Flink (PyFlink) Implementation

This module provides streaming execution for PSDL scenarios using Apache Flink.
It compiles PSDL operators to Flink streaming primitives for real-time clinical
event processing.

See RFC-0002 for full specification:
https://github.com/Chesterguan/PSDL/blob/main/rfcs/0002-streaming-execution.md

Usage:
    # Basic compilation (no PyFlink required)
    from psdl.execution.streaming import StreamingCompiler, StreamingEvaluator

    compiler = StreamingCompiler()
    compiled = compiler.compile(scenario_dict)

    # Full Flink deployment (requires PyFlink)
    from psdl.execution.streaming import FlinkRuntime, FlinkJob

    runtime = FlinkRuntime()
    job = runtime.create_job(scenario_dict, kafka_config={...})
    job.execute()
"""

from .compiler import StreamingCompiler, StreamingEvaluator
from .config import StreamingConfig
from .models import ClinicalEvent, LogicResult, TrendResult
from .operators import (
    CountWindowFunction,
    DeltaWindowFunction,
    EMAProcessFunction,
    LastProcessFunction,
    MaxWindowFunction,
    MinWindowFunction,
    SlopeWindowFunction,
)

# Flink runtime - optional, requires PyFlink
try:
    from .flink_runtime import FlinkJob, FlinkRuntime, create_kafka_sink, run_scenario

    FLINK_AVAILABLE = True
except ImportError:
    FlinkJob = None
    FlinkRuntime = None
    create_kafka_sink = None
    run_scenario = None
    FLINK_AVAILABLE = False

__all__ = [
    # Core compilation (always available)
    "StreamingCompiler",
    "StreamingEvaluator",
    "StreamingConfig",
    "ClinicalEvent",
    "TrendResult",
    "LogicResult",
    # Operators
    "DeltaWindowFunction",
    "SlopeWindowFunction",
    "EMAProcessFunction",
    "LastProcessFunction",
    "MinWindowFunction",
    "MaxWindowFunction",
    "CountWindowFunction",
    # Flink runtime (optional)
    "FlinkRuntime",
    "FlinkJob",
    "create_kafka_sink",
    "run_scenario",
    "FLINK_AVAILABLE",
]
