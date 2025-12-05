"""
PSDL - Patient Scenario Definition Language
Python Runtime v0.1

A declarative language for expressing clinical scenarios.
"""

__version__ = "0.1.0"

try:
    from .parser import PSDLParser, PSDLScenario
    from .evaluator import PSDLEvaluator
    from .operators import TemporalOperators
except ImportError:
    from parser import PSDLParser, PSDLScenario
    from evaluator import PSDLEvaluator
    from operators import TemporalOperators

__all__ = [
    "PSDLParser",
    "PSDLScenario",
    "PSDLEvaluator",
    "TemporalOperators",
]
