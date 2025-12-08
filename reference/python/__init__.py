"""
PSDL - Patient Scenario Definition Language
Python Reference Implementation v0.1

A declarative language for expressing clinical scenarios.
"""

__version__ = "0.1.0"

try:
    from .evaluator import InMemoryBackend, PSDLEvaluator
    from .operators import DataPoint, TemporalOperators
    from .parser import PSDLParser, PSDLScenario
except ImportError:
    from evaluator import InMemoryBackend, PSDLEvaluator
    from operators import DataPoint, TemporalOperators
    from parser import PSDLParser, PSDLScenario

__all__ = [
    "PSDLParser",
    "PSDLScenario",
    "PSDLEvaluator",
    "InMemoryBackend",
    "DataPoint",
    "TemporalOperators",
]
