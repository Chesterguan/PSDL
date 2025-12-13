"""
PSDL - Patient Scenario Definition Language
Python Reference Implementation v0.3

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
    result = evaluator.evaluate("patient_1")

    # v0.3: Get standardized output
    standard_result = result.to_standard_result()

Structure:
- core/: Parser, IR types, expression parsing
- operators.py: Temporal operator implementations
- runtimes/: Execution backends (single, cohort, streaming)
- adapters/: Data source adapters (OMOP, FHIR)
"""

__version__ = "0.3.0"

# Core components
from .core import PSDLParser, PSDLScenario
from .core.ir import (
    DecisionOutput,
    EvaluationResult,
    EvidenceOutput,
    FeatureOutput,
    LogicExpr,
    OutputDefinitions,
    OutputType,
    Signal,
    TrendExpr,
)
from .operators import DataPoint, TemporalOperators

# Runtimes
from .runtimes.single import InMemoryBackend, SinglePatientEvaluator

# Legacy aliases
PSDLEvaluator = SinglePatientEvaluator
BatchEvaluator = SinglePatientEvaluator

# Streaming (optional - requires apache-flink)
try:
    from .execution import STREAMING_AVAILABLE, StreamingEvaluator
except ImportError:
    STREAMING_AVAILABLE = False
    StreamingEvaluator = None

# Built-in example scenarios
from . import examples  # noqa: E402


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
    # v0.3 IR types
    "Signal",
    "TrendExpr",
    "LogicExpr",
    "EvaluationResult",
    "OutputType",
    "OutputDefinitions",
    "DecisionOutput",
    "FeatureOutput",
    "EvidenceOutput",
    # Execution
    "PSDLEvaluator",
    "BatchEvaluator",
    "InMemoryBackend",
    "SinglePatientEvaluator",
    # Streaming (optional)
    "StreamingEvaluator",
    "STREAMING_AVAILABLE",
    # Adapter factories
    "get_omop_adapter",
    "get_fhir_adapter",
    # Examples
    "examples",
]
