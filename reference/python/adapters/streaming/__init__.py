"""
PSDL Streaming Adapter - Apache Flink (PyFlink) Implementation

This module provides streaming execution for PSDL scenarios using Apache Flink.
It compiles PSDL operators to Flink streaming primitives for real-time clinical
event processing.

See RFC-0002 for full specification:
https://github.com/Chesterguan/PSDL/blob/main/rfcs/0002-streaming-execution.md

Usage:
    from reference.python.adapters.streaming import StreamingCompiler, StreamingEvaluator

    compiler = StreamingCompiler()
    job = compiler.compile("scenarios/icu_deterioration.yaml")
    job.execute()
"""

from .compiler import StreamingCompiler
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

__all__ = [
    "StreamingCompiler",
    "StreamingConfig",
    "ClinicalEvent",
    "TrendResult",
    "LogicResult",
    "DeltaWindowFunction",
    "SlopeWindowFunction",
    "EMAProcessFunction",
    "LastProcessFunction",
    "MinWindowFunction",
    "MaxWindowFunction",
    "CountWindowFunction",
]
