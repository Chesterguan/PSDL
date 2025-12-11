"""
PSDL Intermediate Representation (IR) - Core data types.

This module defines the data structures representing a parsed PSDL scenario.
These types form the interface between the parser and the execution runtimes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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


@dataclass
class Signal:
    """A signal binding - maps logical name to data source."""

    name: str
    source: str
    concept_id: Optional[int] = None
    unit: Optional[str] = None
    domain: Domain = Domain.MEASUREMENT


@dataclass
class WindowSpec:
    """Time window specification (e.g., 6h, 30m, 1d)."""

    value: int
    unit: str  # s, m, h, d

    @property
    def seconds(self) -> int:
        """Convert window to seconds."""
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return self.value * multipliers.get(self.unit, 1)

    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


@dataclass
class TrendExpr:
    """A parsed trend expression."""

    name: str
    operator: str  # delta, slope, ema, sma, min, max, count, last, first
    signal: str
    window: Optional[WindowSpec] = None
    comparator: Optional[str] = None  # <, <=, >, >=, ==, !=
    threshold: Optional[float] = None
    description: Optional[str] = None
    raw_expr: str = ""


@dataclass
class LogicExpr:
    """A parsed logic expression."""

    name: str
    expr: str
    terms: List[str]  # Referenced trend names
    operators: List[str]  # AND, OR, NOT
    severity: Optional[Severity] = None
    description: Optional[str] = None


@dataclass
class PopulationFilter:
    """Population inclusion/exclusion criteria."""

    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


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

    def validate(self) -> List[str]:
        """Validate the scenario for semantic correctness. Returns list of errors."""
        errors = []

        # Check trend expressions reference valid signals
        for trend_name, trend in self.trends.items():
            if trend.signal not in self.signals:
                errors.append(f"Trend '{trend_name}' references unknown signal '{trend.signal}'")

        # Check logic expressions reference valid trends
        for logic_name, logic in self.logic.items():
            for term in logic.terms:
                if term not in self.trends and term not in self.logic:
                    errors.append(f"Logic '{logic_name}' references unknown term '{term}'")

        return errors
