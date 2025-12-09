"""
PSDL - Patient Scenario Definition Language
Python Reference Implementation v0.2

A declarative language for expressing clinical scenarios.

Structure:
- parser.py: YAML parsing and validation
- operators.py: Temporal operator implementations
- execution/: Execution backends (batch, streaming)
- adapters/: Data source adapters (OMOP, FHIR)
"""

__version__ = "0.2.0"

# Core components
try:
    from .operators import DataPoint, TemporalOperators
    from .parser import PSDLParser, PSDLScenario
except ImportError:
    from operators import DataPoint, TemporalOperators
    from parser import PSDLParser, PSDLScenario

# Execution backends
try:
    from .execution import BatchEvaluator, PSDLEvaluator
    from .execution.batch import InMemoryBackend
except ImportError:
    from execution import BatchEvaluator, PSDLEvaluator
    from execution.batch import InMemoryBackend

# Streaming (optional)
try:
    from .execution import STREAMING_AVAILABLE, StreamingEvaluator
except ImportError:
    STREAMING_AVAILABLE = False
    StreamingEvaluator = None

__all__ = [
    # Core
    "PSDLParser",
    "PSDLScenario",
    "DataPoint",
    "TemporalOperators",
    # Execution
    "PSDLEvaluator",
    "BatchEvaluator",
    "InMemoryBackend",
    # Streaming (optional)
    "StreamingEvaluator",
    "STREAMING_AVAILABLE",
]
