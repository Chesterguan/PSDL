"""
PSDL Parser - Parses YAML scenario definitions into IR objects.

This module handles:
1. YAML parsing and validation
2. Expression parsing for trends and logic
3. Semantic validation (signal references, etc.)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

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
        r"^(delta|slope|ema|sma|min|max|count|last|first|std|stddev|percentile)\s*\(\s*(\w+)"
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

        # Parse audit (optional - for backwards compatibility)
        audit = self._parse_audit(data.get("audit"))

        # Parse state machine (optional)
        state = self._parse_state(data.get("state"))

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
            audit=audit,
            state=state,
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

    def _parse_audit(self, data: Optional[dict]) -> Optional[AuditBlock]:
        """Parse audit block."""
        if data is None:
            return None

        intent = data.get("intent")
        rationale = data.get("rationale")
        provenance = data.get("provenance")

        if not all([intent, rationale, provenance]):
            raise PSDLParseError("Audit block requires 'intent', 'rationale', and 'provenance'")

        return AuditBlock(intent=intent, rationale=rationale, provenance=provenance)

    def _parse_state(self, data: Optional[dict]) -> Optional[StateMachine]:
        """Parse state machine definition."""
        if data is None:
            return None

        initial = data.get("initial")
        states = data.get("states", [])
        transitions_data = data.get("transitions", [])

        transitions = []
        for t in transitions_data:
            if not all(k in t for k in ["from", "to", "when"]):
                raise PSDLParseError("State transition requires 'from', 'to', and 'when'")
            transitions.append(
                StateTransition(from_state=t["from"], to_state=t["to"], when=t["when"])
            )

        return StateMachine(initial=initial, states=states, transitions=transitions)

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
            ops = r"delta|slope|ema|sma|min|max|count|last|first|std|stddev|percentile"
            simple_pattern = re.compile(rf"^({ops})\s*\(\s*(\w+)(?:\s*,\s*(\d+[smhd]))?\s*\)$")
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
