"""
PSDL Parser - Parses YAML scenario definitions into structured objects.

This module handles:
1. YAML parsing and validation
2. Schema validation
3. Expression parsing for trends and logic
4. Semantic validation (signal references, etc.)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml


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


class PSDLParseError(Exception):
    """Exception raised for PSDL parsing errors."""

    def __init__(self, message: str, line: Optional[int] = None):
        self.message = message
        self.line = line
        super().__init__(f"PSDL Parse Error{f' (line {line})' if line else ''}: {message}")


class PSDLParser:
    """
    Parser for PSDL scenario definitions.

    Usage:
        parser = PSDLParser()
        scenario = parser.parse_file("scenarios/icu_deterioration.yaml")
        # or
        scenario = parser.parse_string(yaml_content)
    """

    # Regex patterns for parsing expressions
    WINDOW_PATTERN = re.compile(r"^(\d+)(s|m|h|d)$")
    TREND_PATTERN = re.compile(
        r"^(delta|slope|ema|sma|min|max|count|last|first)\s*\(\s*(\w+)"
        r"(?:\s*,\s*(\d+[smhd]))?\s*\)\s*([<>=!]+)\s*(-?\d+\.?\d*)$"
    )
    LOGIC_TERM_PATTERN = re.compile(r"\b(\w+)\b")
    LOGIC_OPERATOR_PATTERN = re.compile(r"\b(AND|OR|NOT)\b", re.IGNORECASE)

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def parse_file(self, filepath: str) -> PSDLScenario:
        """Parse a PSDL scenario from a YAML file."""
        with open(filepath, "r") as f:
            content = f.read()
        return self.parse_string(content, source=filepath)

    def parse_string(self, content: str, source: str = "<string>") -> PSDLScenario:
        """Parse a PSDL scenario from a YAML string."""
        self.errors = []
        self.warnings = []

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise PSDLParseError(f"Invalid YAML: {e}")

        if not isinstance(data, dict):
            raise PSDLParseError("PSDL document must be a YAML mapping")

        # Parse required fields
        name = self._require_field(data, "scenario", str)
        version = self._require_field(data, "version", str)

        # Parse optional fields
        description = data.get("description")

        # Parse population
        population = self._parse_population(data.get("population"))

        # Parse signals (required)
        signals_data = self._require_field(data, "signals", dict)
        signals = self._parse_signals(signals_data)

        # Parse trends (optional)
        trends_data = data.get("trends", {})
        trends = self._parse_trends(trends_data)

        # Parse logic (required)
        logic_data = self._require_field(data, "logic", dict)
        logic = self._parse_logic(logic_data)

        # Parse mapping (optional)
        mapping = data.get("mapping")

        scenario = PSDLScenario(
            name=name,
            version=version,
            description=description,
            population=population,
            signals=signals,
            trends=trends,
            logic=logic,
            mapping=mapping,
        )

        # Validate semantic correctness
        validation_errors = scenario.validate()
        if validation_errors:
            self.errors.extend(validation_errors)

        if self.errors:
            raise PSDLParseError(f"Validation errors: {'; '.join(self.errors)}")

        return scenario

    def _require_field(self, data: dict, field: str, expected_type: type) -> Any:
        """Require a field to exist and be of expected type."""
        if field not in data:
            raise PSDLParseError(f"Missing required field: '{field}'")
        value = data[field]
        if not isinstance(value, expected_type):
            raise PSDLParseError(
                f"Field '{field}' must be {expected_type.__name__}, got {type(value).__name__}"
            )
        return value

    def _parse_population(self, data: Optional[dict]) -> Optional[PopulationFilter]:
        """Parse population filter."""
        if data is None:
            return None

        return PopulationFilter(include=data.get("include", []), exclude=data.get("exclude", []))

    def _parse_signals(self, data: dict) -> Dict[str, Signal]:
        """Parse signal bindings."""
        signals = {}

        for name, spec in data.items():
            if isinstance(spec, str):
                # Shorthand: just the source
                signals[name] = Signal(name=name, source=spec)
            elif isinstance(spec, dict):
                source = spec.get("source")
                if not source:
                    raise PSDLParseError(f"Signal '{name}' missing 'source'")

                domain = Domain.MEASUREMENT
                if "domain" in spec:
                    try:
                        domain = Domain(spec["domain"])
                    except ValueError:
                        self.warnings.append(
                            f"Unknown domain '{spec['domain']}' for signal '{name}'"
                        )

                signals[name] = Signal(
                    name=name,
                    source=source,
                    concept_id=spec.get("concept_id"),
                    unit=spec.get("unit"),
                    domain=domain,
                )
            else:
                raise PSDLParseError(f"Invalid signal specification for '{name}'")

        return signals

    def _parse_window(self, window_str: str) -> WindowSpec:
        """Parse a window specification like '6h' or '30m'."""
        match = self.WINDOW_PATTERN.match(window_str)
        if not match:
            raise PSDLParseError(f"Invalid window specification: '{window_str}'")
        return WindowSpec(value=int(match.group(1)), unit=match.group(2))

    def _parse_trend_expr(self, name: str, expr: str) -> TrendExpr:
        """Parse a trend expression like 'delta(Cr, 6h) > 0.3'."""
        expr = expr.strip()

        match = self.TREND_PATTERN.match(expr)
        if not match:
            # Try simpler pattern without comparison (for boolean trends)
            simple_pattern = re.compile(
                r"^(delta|slope|ema|sma|min|max|count|last|first)\s*\(\s*(\w+)"
                r"(?:\s*,\s*(\d+[smhd]))?\s*\)$"
            )
            simple_match = simple_pattern.match(expr)
            if simple_match:
                operator, signal, window_str = simple_match.groups()
                window = self._parse_window(window_str) if window_str else None
                return TrendExpr(
                    name=name,
                    operator=operator,
                    signal=signal,
                    window=window,
                    raw_expr=expr,
                )
            raise PSDLParseError(f"Invalid trend expression: '{expr}'")

        operator, signal, window_str, comparator, threshold = match.groups()
        window = self._parse_window(window_str) if window_str else None

        return TrendExpr(
            name=name,
            operator=operator,
            signal=signal,
            window=window,
            comparator=comparator,
            threshold=float(threshold),
            raw_expr=expr,
        )

    def _parse_trends(self, data: dict) -> Dict[str, TrendExpr]:
        """Parse trend definitions."""
        trends = {}

        for name, spec in data.items():
            if isinstance(spec, str):
                # Shorthand: just the expression
                trends[name] = self._parse_trend_expr(name, spec)
            elif isinstance(spec, dict):
                expr = spec.get("expr")
                if not expr:
                    raise PSDLParseError(f"Trend '{name}' missing 'expr'")

                trend = self._parse_trend_expr(name, expr)
                trend.description = spec.get("description")
                trends[name] = trend
            else:
                raise PSDLParseError(f"Invalid trend specification for '{name}'")

        return trends

    def _parse_logic_expr(self, name: str, expr: str) -> Tuple[List[str], List[str]]:
        """Extract terms and operators from a logic expression."""
        # Find all operators
        operators = self.LOGIC_OPERATOR_PATTERN.findall(expr)
        operators = [op.upper() for op in operators]

        # Find all terms (excluding operators)
        expr_without_ops = self.LOGIC_OPERATOR_PATTERN.sub(" ", expr)
        terms = self.LOGIC_TERM_PATTERN.findall(expr_without_ops)

        return terms, operators

    def _parse_logic(self, data: dict) -> Dict[str, LogicExpr]:
        """Parse logic definitions."""
        logic = {}

        for name, spec in data.items():
            if isinstance(spec, str):
                # Shorthand: just the expression
                terms, operators = self._parse_logic_expr(name, spec)
                logic[name] = LogicExpr(name=name, expr=spec, terms=terms, operators=operators)
            elif isinstance(spec, dict):
                expr = spec.get("expr")
                if not expr:
                    raise PSDLParseError(f"Logic '{name}' missing 'expr'")

                terms, operators = self._parse_logic_expr(name, expr)

                severity = None
                if "severity" in spec:
                    try:
                        severity = Severity(spec["severity"])
                    except ValueError:
                        self.warnings.append(
                            f"Unknown severity '{spec['severity']}' for logic '{name}'"
                        )

                logic[name] = LogicExpr(
                    name=name,
                    expr=expr,
                    terms=terms,
                    operators=operators,
                    severity=severity,
                    description=spec.get("description"),
                )
            else:
                raise PSDLParseError(f"Invalid logic specification for '{name}'")

        return logic


def parse_scenario(source: str) -> PSDLScenario:
    """
    Convenience function to parse a PSDL scenario.

    Args:
        source: Either a file path (ending in .yaml/.yml) or YAML content string

    Returns:
        Parsed PSDLScenario object
    """
    parser = PSDLParser()

    if source.endswith(".yaml") or source.endswith(".yml"):
        return parser.parse_file(source)
    else:
        return parser.parse_string(source)
