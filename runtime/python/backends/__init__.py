"""
DEPRECATED: This module has been renamed to 'reference.python.adapters'.

Please update your imports:
    OLD: from runtime.python.backends import ...
    NEW: from reference.python.adapters import ...

This compatibility shim will be removed in v0.2.0.
"""

import warnings

warnings.warn(
    "The 'runtime.python.backends' module is deprecated and will be removed in v0.2.0. "
    "Please use 'reference.python.adapters' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from reference.python.adapters
from reference.python.adapters import (
    OMOPBackend,
    OMOPConfig,
    FHIRBackend,
    FHIRConfig,
    create_fhir_backend,
)

__all__ = [
    "OMOPBackend",
    "OMOPConfig",
    "FHIRBackend",
    "FHIRConfig",
    "create_fhir_backend",
]
