"""
DEPRECATED: This module has been renamed to 'reference'.

The runtime/ directory has been renamed to reference/ to better reflect
the industry-standard separation between Specification and Reference Implementation.

Please update your imports:
    OLD: from runtime.python import ...
    NEW: from reference.python import ...

This compatibility shim will be removed in v0.2.0.
"""

import warnings

warnings.warn(
    "The 'runtime' module is deprecated and will be removed in v0.2.0. "
    "Please use 'reference' instead. "
    "Example: 'from reference.python import PSDLParser'",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from reference
from reference import *
