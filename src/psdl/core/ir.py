"""
PSDL Intermediate Representation (IR) - Core data types.

This module defines the data structures representing a parsed PSDL scenario.
These types form the interface between the parser and the execution runtimes.

Version 0.3.0 Changes (RFC-0005):
- Trends produce NUMERIC values only (no boolean comparisons)
- Logic layer handles all comparisons
- New Output types (Decision, Feature, Evidence)
- Standardized EvaluationResult
- AST types generated from spec/ast-nodes.yaml
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Import AST types from generated code (consolidation)
from psdl._generated.ast_types import LogicNode, WindowSpec


class Domain(Enum):
    """OMOP CDM domains for signals."""

    MEASUREMENT = "measurement"
    CONDITION = "condition"
    DRUG = "drug"
    PROCEDURE = "procedure"
    OBSERVATION = "observation"


class Severity(Enum):
    """Clinical severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrendType(Enum):
    """Return type of trend expressions (v0.3: NO boolean)."""

    FLOAT = "float"
    INT = "int"
    TIMESTAMP = "timestamp"


class OutputType(Enum):
    """Output value types."""

    BOOLEAN = "boolean"
    ENUM = "enum"
    FLOAT = "float"
    INT = "int"
    TIMESTAMP = "timestamp"
    INTERVAL = "interval"
    STRING = "string"
    STRING_ARRAY = "string[]"


@dataclass
class Signal:
    """A signal binding - maps logical name to data source."""

    name: str
    ref: str  # v0.3: renamed from 'source' to 'ref'
    concept_id: Optional[int] = None
    unit: Optional[str] = None
    domain: Domain = Domain.MEASUREMENT

    # v0.2 compatibility
    @property
    def source(self) -> str:
        """v0.2 compatibility: 'source' is now 'ref'."""
        return self.ref


# WindowSpec is imported from psdl._generated.ast_types


@dataclass
class TrendExpr:
    """
    A parsed trend expression.

    v0.3 Changes:
    - type: explicit return type (float, int, timestamp)
    - unit: unit of computed value
    - comparator/threshold: REMOVED (comparisons belong in Logic layer)
    - ast: Full AST for complex expressions (ArithExpr, etc.)
    """

    name: str
    operator: str  # delta, slope, ema, sma, min, max, count, last, first, or 'arith' for compound
    signal: str  # Primary signal (may be empty for compound expressions)
    window: Optional[WindowSpec] = None
    type: TrendType = TrendType.FLOAT  # v0.3: explicit type
    unit: Optional[str] = None  # v0.3: unit of computed value
    description: Optional[str] = None
    raw_expr: str = ""
    ast: Optional[Any] = None  # v0.3: Full AST for complex expressions (ArithExpr, etc.)
    # v0.2 compatibility (deprecated in v0.3)
    comparator: Optional[str] = None  # <, <=, >, >=, ==, !=
    threshold: Optional[float] = None


@dataclass
class LogicExpr:
    """
    A parsed logic expression.

    v0.3 Changes:
    - when: preferred syntax (instead of expr)
    - Logic now handles ALL comparisons (trend >= threshold)
    - ast: Full AST tree for accurate DAG visualization (Issue #6)
    """

    name: str
    expr: str  # The boolean expression (v0.3: may include comparisons)
    terms: List[str]  # Referenced trend/logic names
    operators: List[str]  # AND, OR, NOT, comparison operators
    severity: Optional[Severity] = None
    description: Optional[str] = None
    ast: Optional["LogicNode"] = None  # v0.3: Full AST tree for DAG visualization


@dataclass
class PopulationFilter:
    """Population inclusion/exclusion criteria."""

    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


@dataclass
class AuditBlock:
    """Required audit information for regulatory compliance."""

    intent: str  # What this scenario detects
    rationale: str  # Why this detection matters
    provenance: str  # Source (guidelines, literature)


@dataclass
class StateTransition:
    """A state transition rule triggered by logic conditions."""

    from_state: str
    to_state: str
    when: str  # Logic condition name


@dataclass
class StateMachine:
    """Simple state machine for tracking clinical state transitions."""

    initial: str
    states: List[str]
    transitions: List[StateTransition] = field(default_factory=list)


# v0.3: Output types (RFC-0005)


@dataclass
class DecisionOutput:
    """Boolean decision output."""

    name: str
    type: OutputType  # boolean or enum
    from_ref: Optional[str] = None  # e.g., 'logic.aki_stage1'
    values: Optional[List[str]] = None  # for enum type
    description: Optional[str] = None


@dataclass
class FeatureOutput:
    """Numeric feature output for ML/stats."""

    name: str
    type: OutputType  # float or int
    from_ref: Optional[str] = None  # e.g., 'trends.cr_delta_48h'
    expr: Optional[str] = None  # computed expression
    unit: Optional[str] = None
    description: Optional[str] = None


@dataclass
class EvidenceOutput:
    """Evidence output for audit trail."""

    name: str
    type: OutputType  # timestamp, interval, string, string[]
    from_ref: Optional[str] = None
    expr: Optional[str] = None
    description: Optional[str] = None


@dataclass
class OutputDefinitions:
    """
    v0.3: Output schema defining what the scenario produces.

    Three categories:
    - decision: boolean judgments (in_cohort, aki_stage)
    - features: numeric values for ML/stats
    - evidence: audit trail (index_time, matched_rules)
    """

    decision: Dict[str, DecisionOutput] = field(default_factory=dict)
    features: Dict[str, FeatureOutput] = field(default_factory=dict)
    evidence: Dict[str, EvidenceOutput] = field(default_factory=dict)


@dataclass
class PSDLScenario:
    """A complete parsed PSDL scenario."""

    name: str
    version: str
    description: Optional[str]
    population: Optional[PopulationFilter]
    signals: Dict[str, Signal]
    trends: Dict[str, TrendExpr]
    logic: Dict[str, LogicExpr]
    audit: Optional[AuditBlock] = None
    state: Optional[StateMachine] = None
    outputs: Optional[OutputDefinitions] = None  # v0.3: new
    mapping: Optional[Dict[str, Any]] = None

    def get_signal(self, name: str) -> Optional[Signal]:
        """Get a signal by name."""
        return self.signals.get(name)

    def get_trend(self, name: str) -> Optional[TrendExpr]:
        """Get a trend by name."""
        return self.trends.get(name)

    def get_logic(self, name: str) -> Optional[LogicExpr]:
        """Get a logic expression by name."""
        return self.logic.get(name)

    def _extract_signals_from_ast(self, ast_node: Any) -> List[str]:
        """Extract all signal references from an AST node (for compound expressions)."""
        from psdl._generated.ast_types import ArithExpr, TemporalCall, TrendExpression

        signals = []

        def visit(node):
            if isinstance(node, TrendExpression):
                if node.temporal:
                    signals.append(node.temporal.signal)
            elif isinstance(node, TemporalCall):
                signals.append(node.signal)
            elif isinstance(node, ArithExpr):
                visit(node.left)
                visit(node.right)
            # NumberLiteral and float don't have signals

        visit(ast_node)
        return signals

    def validate(self) -> List[str]:
        """Validate the scenario for semantic correctness. Returns list of errors."""
        errors = []

        # Check trend expressions reference valid signals
        for trend_name, trend in self.trends.items():
            # For compound arithmetic expressions, extract all signals from AST
            if trend.operator == "arith" and trend.ast is not None:
                signals_in_expr = self._extract_signals_from_ast(trend.ast)
                for sig in signals_in_expr:
                    if sig not in self.signals:
                        errors.append(f"Trend '{trend_name}' references unknown signal '{sig}'")
            elif trend.signal and trend.signal not in self.signals:
                errors.append(f"Trend '{trend_name}' references unknown signal '{trend.signal}'")

        # Check logic expressions reference valid trends
        for logic_name, logic in self.logic.items():
            for term in logic.terms:
                if term not in self.trends and term not in self.logic:
                    errors.append(f"Logic '{logic_name}' references unknown term '{term}'")

        return errors


# v0.3: Standardized Runtime Output (RFC-0005)


@dataclass
class EvaluationResult:
    """
    Standardized output from PSDL runtime evaluation.

    Core (required):
    - patient_id: Patient identifier
    - triggered: Whether any logic condition was triggered

    Decision (optional):
    - triggered_logic: List of triggered logic names
    - current_state: Current state machine state

    Features (optional):
    - trend_values: Computed trend values

    Evidence (optional):
    - logic_results: Boolean results for each logic
    - index_time: When the trigger occurred
    """

    # Core (required)
    patient_id: str
    triggered: bool

    # Decision (optional)
    triggered_logic: List[str] = field(default_factory=list)
    current_state: Optional[str] = None

    # Features (optional)
    trend_values: Dict[str, float] = field(default_factory=dict)

    # Evidence (optional)
    logic_results: Dict[str, bool] = field(default_factory=dict)
    index_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "patient_id": self.patient_id,
            "triggered": self.triggered,
        }

        if self.triggered_logic:
            result["triggered_logic"] = self.triggered_logic

        if self.current_state:
            result["current_state"] = self.current_state

        if self.trend_values:
            result["trend_values"] = self.trend_values

        if self.logic_results:
            result["logic_results"] = self.logic_results

        if self.index_time:
            result["index_time"] = self.index_time.isoformat()

        return result
