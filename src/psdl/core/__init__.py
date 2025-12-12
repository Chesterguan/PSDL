"""
PSDL Core Library - Parser, IR, and Validation.

This module provides the core functionality for parsing and validating
PSDL scenario definitions.

Public API:
    - parse_scenario(source) - Parse a YAML file or string
    - PSDLScenario - The main scenario type
    - Signal, TrendExpr, LogicExpr - IR components
"""

from .ir import (
    AuditBlock,
    Domain,
    LogicExpr,
    PopulationFilter,
    PSDLScenario,
    Severity,
    Signal,
    StateMachine,
    StateTransition,
    TrendExpr,
    WindowSpec,
)
from .loader import load_yaml, load_yaml_file
from .parser import PSDLParseError, PSDLParser, parse_scenario

__all__ = [
    # IR Types
    "AuditBlock",
    "Domain",
    "LogicExpr",
    "PopulationFilter",
    "PSDLScenario",
    "Severity",
    "Signal",
    "StateMachine",
    "StateTransition",
    "TrendExpr",
    "WindowSpec",
    # Parser
    "PSDLParser",
    "PSDLParseError",
    "parse_scenario",
    # Loader
    "load_yaml",
    "load_yaml_file",
]
