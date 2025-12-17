"""
PSDL Core Library - Parser, IR, Dataset Spec, and Validation.

This module provides the core functionality for parsing and validating
PSDL scenario definitions and dataset specifications.

Public API:
    - parse_scenario(source) - Parse a YAML file or string
    - PSDLScenario - The main scenario type
    - Signal, TrendExpr, LogicExpr - IR components
    - load_dataset_spec(path) - Load a dataset specification
    - DatasetSpec - Dataset specification type
"""

from .dataset import (
    Binding,
    BindingResolutionError,
    Conventions,
    DatasetAdapter,
    DatasetSpec,
    DatasetSpecError,
    DatasetValidationError,
    ElementSpec,
    Event,
    FilterSpec,
    UnitConversion,
    ValuesetSpec,
    load_dataset_spec,
    validate_dataset_spec,
)
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
    # Dataset Spec (RFC-0004)
    "DatasetSpec",
    "ElementSpec",
    "FilterSpec",
    "Conventions",
    "ValuesetSpec",
    "UnitConversion",
    "Binding",
    "Event",
    "DatasetAdapter",
    "load_dataset_spec",
    "validate_dataset_spec",
    "DatasetSpecError",
    "DatasetValidationError",
    "BindingResolutionError",
]
