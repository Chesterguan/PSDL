"""
Auto-generated operator metadata from spec/operators.yaml
Generated: 2025-12-15T12:01:47.781774

DO NOT EDIT - Regenerate with: python tools/codegen.py --operators
"""

from typing import Dict, List, Literal, Optional, TypedDict

SPEC_VERSION = "0.3.0"


class OperatorMeta(TypedDict, total=False):
    """Metadata for a PSDL operator."""

    name: str
    category: Literal["windowed", "pointwise"]
    signature: str
    description: str
    null_handling: Literal["filter", "include", "passthrough"]
    min_points: int
    aliases: List[str]
    runtimes: List[str]


# Windowed operators (require time window)
WINDOWED_OPERATORS: Dict[str, OperatorMeta] = {
    "delta": {
        "name": "delta",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Compute absolute change: last_value - first_value in window""",
        "null_handling": "filter",
        "min_points": 2,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "slope": {
        "name": "slope",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Compute linear regression slope over window (units per second)""",
        "null_handling": "filter",
        "min_points": 2,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "sma": {
        "name": "sma",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Compute simple moving average over window""",
        "null_handling": "filter",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "ema": {
        "name": "ema",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Compute exponential moving average over window""",
        "null_handling": "filter",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "min": {
        "name": "min",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Find minimum value in window""",
        "null_handling": "filter",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "max": {
        "name": "max",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Find maximum value in window""",
        "null_handling": "filter",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "count": {
        "name": "count",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> int",
        "description": """Count observations in window (includes null values)""",
        "null_handling": "include",
        "min_points": 0,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "first": {
        "name": "first",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Get the earliest value in window""",
        "null_handling": "passthrough",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "std": {
        "name": "std",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window) -> float | null",
        "description": """Compute sample standard deviation in window""",
        "null_handling": "filter",
        "min_points": 2,
        "aliases": ["stddev"],
        "runtimes": ["flink", "postgresql"],
    },
    "percentile": {
        "name": "percentile",
        "category": "windowed",
        "signature": "(signal: Signal, window: Window, p: float) -> float | null",
        "description": """Compute percentile value in window""",
        "null_handling": "filter",
        "min_points": 1,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
}


# Pointwise operators (no time window)
POINTWISE_OPERATORS: Dict[str, OperatorMeta] = {
    "last": {
        "name": "last",
        "category": "pointwise",
        "signature": "(signal: Signal) -> float | null",
        "description": """Get the most recent value for signal""",
        "null_handling": "passthrough",
        "min_points": 0,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "exists": {
        "name": "exists",
        "category": "pointwise",
        "signature": "(signal: Signal) -> bool",
        "description": """Check if any data exists for signal""",
        "null_handling": "include",
        "min_points": 0,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
    "missing": {
        "name": "missing",
        "category": "pointwise",
        "signature": "(signal: Signal) -> bool",
        "description": """Check if no data exists for signal (inverse of exists)""",
        "null_handling": "include",
        "min_points": 0,
        "aliases": [],
        "runtimes": ["flink", "postgresql"],
    },
}


# All operators combined
ALL_OPERATORS: Dict[str, OperatorMeta] = {
    **WINDOWED_OPERATORS,
    **POINTWISE_OPERATORS,
}


# Operator name to canonical name (handles aliases)
OPERATOR_ALIASES: Dict[str, str] = {
    "delta": "delta",
    "slope": "slope",
    "sma": "sma",
    "ema": "ema",
    "min": "min",
    "max": "max",
    "count": "count",
    "first": "first",
    "std": "std",
    "stddev": "std",
    "percentile": "percentile",
    "last": "last",
    "exists": "exists",
    "missing": "missing",
}


def get_operator(name: str) -> Optional[OperatorMeta]:
    """Get operator metadata by name or alias."""
    canonical = OPERATOR_ALIASES.get(name)
    if canonical:
        return ALL_OPERATORS.get(canonical)
    return None


def is_windowed(name: str) -> bool:
    """Check if operator requires a time window."""
    canonical = OPERATOR_ALIASES.get(name, name)
    return canonical in WINDOWED_OPERATORS
