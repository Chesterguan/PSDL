"""
PSDL - Patient Scenario Definition Language
Python Reference Implementation v0.2

A declarative language for expressing clinical scenarios.

Usage:
    from psdl import PSDLParser, PSDLEvaluator, InMemoryBackend

    # Parse a scenario
    parser = PSDLParser()
    scenario = parser.parse_file("my_scenario.yaml")

    # Evaluate with in-memory data
    backend = InMemoryBackend()
    backend.add_patient_data("patient_1", {"Cr": [...], "HR": [...]})

    evaluator = PSDLEvaluator(scenario, backend)
    results = evaluator.evaluate("patient_1")

Structure:
- parser.py: YAML parsing and validation
- operators.py: Temporal operator implementations
- execution/: Execution backends (batch, streaming)
- adapters/: Data source adapters (OMOP, FHIR)
"""

__version__ = "0.2.0"

# Execution backends
from .execution import BatchEvaluator, PSDLEvaluator
from .execution.batch import InMemoryBackend

# Core components
from .operators import DataPoint, TemporalOperators
from .parser import PSDLParser, PSDLScenario

# Streaming (optional - requires apache-flink)
try:
    from .execution import STREAMING_AVAILABLE, StreamingEvaluator
except ImportError:
    STREAMING_AVAILABLE = False
    StreamingEvaluator = None

# Built-in example scenarios
from . import examples


# Adapters (optional - lazy loaded)
def get_omop_adapter():
    """Get OMOP CDM adapter (requires sqlalchemy)."""
    from .adapters.omop import OMOPAdapter

    return OMOPAdapter


def get_fhir_adapter():
    """Get FHIR R4 adapter (requires requests)."""
    from .adapters.fhir import FHIRAdapter

    return FHIRAdapter


__all__ = [
    # Version
    "__version__",
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
    # Adapter factories
    "get_omop_adapter",
    "get_fhir_adapter",
    # Examples
    "examples",
]
