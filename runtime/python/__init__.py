"""
DEPRECATED: This module has been renamed to 'reference.python'.

Please update your imports:
    OLD: from runtime.python import ...
    NEW: from reference.python import ...

This compatibility shim will be removed in v0.2.0.
"""

import warnings

warnings.warn(
    "The 'runtime.python' module is deprecated and will be removed in v0.2.0. "
    "Please use 'reference.python' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from reference.python
from reference.python import *
from reference.python import (
    PSDLParser,
    PSDLScenario,
    PSDLEvaluator,
    InMemoryBackend,
    DataPoint,
    TemporalOperators,
)

__all__ = [
    "PSDLParser",
    "PSDLScenario",
    "PSDLEvaluator",
    "InMemoryBackend",
    "DataPoint",
    "TemporalOperators",
]
