"""
PSDL to Flink Compiler

Compiles PSDL scenarios into Flink DataStream jobs. This is the core
component that transforms declarative PSDL into executable streaming logic.

Architecture:
    PSDL Scenario (YAML)
         │
         ▼
    StreamingCompiler.compile()
         │
         ├── Parse scenario
         ├── Build operator DAG
         ├── Generate Flink operations
         │
         ▼
    FlinkJob (executable)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .config import StreamingConfig
from .models import ClinicalEvent, LogicResult, Severity, StreamingWindowSpec, TrendResult
from .operators import (
    ProcessFunction,
    WindowFunction,
    create_process_function,
    create_window_function,
)


class OperatorType(Enum):
    """Type of temporal operator."""

    WINDOW = "window"  # Requires windowing (delta, slope, min, max, count, sma)
    PROCESS = "process"  # Stateful process (last, ema)


@dataclass
class ParsedOperator:
    """Parsed PSDL operator from an expression."""

    name: str  # Operator name (delta, slope, ema, last, etc.)
    signal: str  # Signal name (HR, SpO2, etc.)
    window: Optional[str] = None  # Window size (1h, 30m, etc.)
    slide: Optional[str] = None  # Slide interval (optional)
    operator_type: OperatorType = OperatorType.WINDOW

    # Comparison
    threshold: Optional[float] = None
    comparison: str = ">"


@dataclass
class ParsedTrend:
    """Parsed PSDL trend definition."""

    name: str
    expr: str
    operator: ParsedOperator
    description: Optional[str] = None


@dataclass
class ParsedLogic:
    """Parsed PSDL logic definition."""

    name: str
    expr: str
    trend_refs: List[str]  # Trends referenced in expression
    severity: Severity = Severity.MEDIUM
    description: Optional[str] = None


@dataclass
class CompiledTrend:
    """Compiled trend ready for Flink execution."""

    name: str
    signal: str
    operator_type: OperatorType
    window_function: Optional[WindowFunction] = None
    process_function: Optional[ProcessFunction] = None
    window_spec: Optional[StreamingWindowSpec] = None


@dataclass
class CompiledLogic:
    """Compiled logic ready for Flink execution."""

    name: str
    expr: str
    trend_refs: List[str]
    severity: Severity
    description: Optional[str] = None


@dataclass
class CompiledScenario:
    """Fully compiled PSDL scenario."""

    name: str
    version: str
    config: StreamingConfig
    signals: Dict[str, Dict[str, Any]]
    trends: Dict[str, CompiledTrend]
    logic: Dict[str, CompiledLogic]


class ExpressionParser:
    """Parse PSDL expressions into operator components."""

    # Pattern: operator(signal, window, [slide]) comparison threshold
    OPERATOR_PATTERN = re.compile(
        r"(\w+)\s*\(\s*(\w+)\s*(?:,\s*(\d+[smhd])\s*)?"
        r"(?:,\s*(\d+[smhd]))?\s*\)\s*([><=!]+)\s*(-?[\d.]+)"
    )

    # Pattern: last(signal) comparison threshold
    SIMPLE_PATTERN = re.compile(r"(\w+)\s*\(\s*(\w+)\s*\)\s*([><=!]+)\s*(-?[\d.]+)")

    # Operators that require windowing
    WINDOW_OPERATORS = {"delta", "slope", "min", "max", "count", "sma"}

    # Operators that use stateful processing
    PROCESS_OPERATORS = {"last", "ema"}

    @classmethod
    def parse_trend_expr(cls, expr: str) -> ParsedOperator:
        """
        Parse a PSDL trend expression.

        Examples:
            delta(HR, 1h) > 20
            delta(HR, 1h, 30s) > 20
            slope(HR, 2h) > 5
            last(SpO2) < 92
            ema(HR, 1h) > 100

        Returns:
            ParsedOperator with extracted components
        """
        expr = expr.strip()

        # Try full pattern first (with window)
        match = cls.OPERATOR_PATTERN.match(expr)
        if match:
            op_name, signal, window, slide, comparison, threshold = match.groups()

            op_type = (
                OperatorType.WINDOW if op_name in cls.WINDOW_OPERATORS else OperatorType.PROCESS
            )

            return ParsedOperator(
                name=op_name,
                signal=signal,
                window=window,
                slide=slide,
                operator_type=op_type,
                threshold=float(threshold),
                comparison=comparison,
            )

        # Try simple pattern (no window, e.g., last(signal))
        match = cls.SIMPLE_PATTERN.match(expr)
        if match:
            op_name, signal, comparison, threshold = match.groups()

            op_type = (
                OperatorType.WINDOW if op_name in cls.WINDOW_OPERATORS else OperatorType.PROCESS
            )

            return ParsedOperator(
                name=op_name,
                signal=signal,
                window=None,
                slide=None,
                operator_type=op_type,
                threshold=float(threshold),
                comparison=comparison,
            )

        raise ValueError(f"Could not parse expression: {expr}")

    @classmethod
    def parse_logic_expr(cls, expr: str) -> List[str]:
        """
        Extract trend references from a logic expression.

        Examples:
            hr_rising AND bp_dropping -> ["hr_rising", "bp_dropping"]
            (a AND b) OR c -> ["a", "b", "c"]

        Returns:
            List of trend names referenced in the expression
        """
        # Remove boolean operators and parentheses
        cleaned = re.sub(r"\b(AND|OR|NOT)\b", " ", expr, flags=re.IGNORECASE)
        cleaned = re.sub(r"[()]", " ", cleaned)

        # Extract identifiers (trend names)
        identifiers = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", cleaned)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for ident in identifiers:
            if ident not in seen:
                seen.add(ident)
                unique.append(ident)

        return unique


class LogicEvaluator:
    """Evaluate PSDL logic expressions."""

    @staticmethod
    def evaluate(expr: str, trend_values: Dict[str, bool]) -> bool:
        """
        Evaluate a logic expression given trend values.

        Args:
            expr: Logic expression (e.g., "a AND b OR c")
            trend_values: Dict mapping trend names to boolean values

        Returns:
            Boolean result of evaluating the expression
        """
        # Replace trend names with their boolean values
        eval_expr = expr

        # Sort by length descending to avoid partial replacements
        for trend_name in sorted(trend_values.keys(), key=len, reverse=True):
            value = "True" if trend_values[trend_name] else "False"
            eval_expr = re.sub(rf"\b{trend_name}\b", value, eval_expr)

        # Replace PSDL operators with Python operators
        eval_expr = re.sub(r"\bAND\b", "and", eval_expr, flags=re.IGNORECASE)
        eval_expr = re.sub(r"\bOR\b", "or", eval_expr, flags=re.IGNORECASE)
        eval_expr = re.sub(r"\bNOT\b", "not", eval_expr, flags=re.IGNORECASE)

        # Safely evaluate
        try:
            return eval(eval_expr, {"__builtins__": {}}, {})
        except Exception as e:
            raise ValueError(f"Could not evaluate logic expression: {expr} -> {eval_expr}: {e}")


class StreamingCompiler:
    """
    Compile PSDL scenarios to Flink streaming jobs.

    This is the main entry point for transforming PSDL into executable
    streaming logic.
    """

    def __init__(self):
        """Initialize the compiler."""
        self.expression_parser = ExpressionParser()
        self.logic_evaluator = LogicEvaluator()

    def compile(self, scenario: Dict[str, Any]) -> CompiledScenario:
        """
        Compile a PSDL scenario to a Flink-ready representation.

        Args:
            scenario: Parsed PSDL scenario dict

        Returns:
            CompiledScenario ready for Flink execution
        """
        # Extract basic info
        name = scenario.get("scenario", "unnamed")
        version = scenario.get("version", "0.1.0")

        # Parse streaming config
        config = StreamingConfig.from_scenario(scenario)

        # Extract signals
        signals = scenario.get("signals", {})

        # Compile trends
        compiled_trends = {}
        for trend_name, trend_def in scenario.get("trends", {}).items():
            compiled_trend = self._compile_trend(trend_name, trend_def)
            compiled_trends[trend_name] = compiled_trend

        # Compile logic
        compiled_logic = {}
        for logic_name, logic_def in scenario.get("logic", {}).items():
            compiled_log = self._compile_logic(logic_name, logic_def)
            compiled_logic[logic_name] = compiled_log

        return CompiledScenario(
            name=name,
            version=version,
            config=config,
            signals=signals,
            trends=compiled_trends,
            logic=compiled_logic,
        )

    def _compile_trend(self, name: str, trend_def: Dict[str, Any]) -> CompiledTrend:
        """Compile a single trend definition."""
        expr = trend_def.get("expr", "")
        description = trend_def.get("description")

        # Parse the expression
        parsed_op = self.expression_parser.parse_trend_expr(expr)

        # Create window spec if needed
        window_spec = None
        if parsed_op.window:
            window_spec = StreamingWindowSpec.from_psdl(parsed_op.window, parsed_op.slide)

        # Create the appropriate function
        if parsed_op.operator_type == OperatorType.WINDOW:
            window_fn = create_window_function(
                operator_name=parsed_op.name,
                trend_name=name,
                threshold=parsed_op.threshold,
                comparison=parsed_op.comparison,
                description=description,
            )
            return CompiledTrend(
                name=name,
                signal=parsed_op.signal,
                operator_type=OperatorType.WINDOW,
                window_function=window_fn,
                window_spec=window_spec,
            )
        else:
            process_fn = create_process_function(
                operator_name=parsed_op.name,
                trend_name=name,
                window_ms=window_spec.size_ms if window_spec else None,
                threshold=parsed_op.threshold,
                comparison=parsed_op.comparison,
                description=description,
            )
            return CompiledTrend(
                name=name,
                signal=parsed_op.signal,
                operator_type=OperatorType.PROCESS,
                process_function=process_fn,
                window_spec=window_spec,
            )

    def _compile_logic(self, name: str, logic_def: Dict[str, Any]) -> CompiledLogic:
        """Compile a single logic definition."""
        expr = logic_def.get("expr", "")
        severity_str = logic_def.get("severity", "medium")
        description = logic_def.get("description")

        # Parse trend references
        trend_refs = self.expression_parser.parse_logic_expr(expr)

        # Parse severity
        severity = Severity(severity_str.lower())

        return CompiledLogic(
            name=name,
            expr=expr,
            trend_refs=trend_refs,
            severity=severity,
            description=description,
        )


class LogicJoinFunction:
    """
    Join multiple trend streams and evaluate logic expressions.

    In Flink, this would be implemented as a CoProcessFunction or
    a multi-way join using connected streams.
    """

    def __init__(self, logic: CompiledLogic, scenario_name: str, scenario_version: str):
        """
        Initialize logic join function.

        Args:
            logic: Compiled logic definition
            scenario_name: Name of the scenario
            scenario_version: Version of the scenario
        """
        self.logic = logic
        self.scenario_name = scenario_name
        self.scenario_version = scenario_version
        self.evaluator = LogicEvaluator()

    def process(
        self,
        patient_id: str,
        trend_results: Dict[str, TrendResult],
        timestamp: datetime,
    ) -> Optional[LogicResult]:
        """
        Evaluate logic expression given trend results.

        Args:
            patient_id: Patient identifier
            trend_results: Dict mapping trend names to their latest results
            timestamp: Event timestamp

        Returns:
            LogicResult if all required trends are present, None otherwise
        """
        # Check if all required trends are present
        missing = set(self.logic.trend_refs) - set(trend_results.keys())
        if missing:
            return None

        # Extract boolean values from trend results
        trend_values = {
            name: result.result
            for name, result in trend_results.items()
            if name in self.logic.trend_refs
        }

        # Evaluate the logic expression
        result = self.evaluator.evaluate(self.logic.expr, trend_values)

        return LogicResult(
            patient_id=patient_id,
            logic_name=self.logic.name,
            result=result,
            severity=self.logic.severity,
            timestamp=timestamp,
            trend_inputs=trend_values,
            description=self.logic.description,
            scenario_name=self.scenario_name,
            scenario_version=self.scenario_version,
        )


class StreamingEvaluator:
    """
    Evaluate PSDL scenarios in streaming mode.

    This class provides a high-level interface for streaming evaluation,
    handling state management and result collection.

    For production Flink deployment, use the compiled operators directly
    with PyFlink APIs.
    """

    def __init__(self):
        """Initialize the streaming evaluator."""
        self.compiler = StreamingCompiler()

    def compile(self, scenario: Dict[str, Any]) -> CompiledScenario:
        """Compile a scenario for streaming execution."""
        return self.compiler.compile(scenario)

    def evaluate_event(
        self, compiled: CompiledScenario, event: ClinicalEvent, state: Dict[str, Any]
    ) -> Tuple[List[TrendResult], List[LogicResult], Dict[str, Any]]:
        """
        Evaluate a single event against a compiled scenario.

        This method is for testing and simulation. In production Flink,
        events flow through the compiled operators.

        Args:
            compiled: Compiled scenario
            event: Incoming clinical event
            state: Current state (per-patient)

        Returns:
            Tuple of (trend_results, logic_results, new_state)
        """
        patient_id = event.patient_id
        signal_type = event.signal_type

        # Initialize state if needed
        if patient_id not in state:
            state[patient_id] = {
                "trends": {},  # Trend states
                "windows": {},  # Windowed events
                "trend_results": {},  # Latest trend results
            }

        patient_state = state[patient_id]
        trend_results = []
        logic_results = []

        # Process relevant trends
        for trend_name, trend in compiled.trends.items():
            if trend.signal != signal_type:
                continue

            if trend.operator_type == OperatorType.PROCESS:
                # Stateful processing (last, ema)
                trend_state = patient_state["trends"].get(trend_name, {})
                result, new_trend_state = trend.process_function.process_element(event, trend_state)
                patient_state["trends"][trend_name] = new_trend_state
                trend_results.append(result)
                patient_state["trend_results"][trend_name] = result

            elif trend.operator_type == OperatorType.WINDOW:
                # Window processing (delta, slope, etc.)
                window_key = f"{trend_name}_{signal_type}"
                if window_key not in patient_state["windows"]:
                    patient_state["windows"][window_key] = []

                # Add event to window
                patient_state["windows"][window_key].append(event)

                # Trim old events outside window
                if trend.window_spec:
                    cutoff = event.timestamp.timestamp() * 1000 - trend.window_spec.size_ms
                    patient_state["windows"][window_key] = [
                        e
                        for e in patient_state["windows"][window_key]
                        if e.timestamp.timestamp() * 1000 >= cutoff
                    ]

                # Compute window result
                window_events = patient_state["windows"][window_key]
                if window_events:
                    window_start = min(e.timestamp for e in window_events)
                    window_end = max(e.timestamp for e in window_events)
                    result = trend.window_function.process(
                        patient_id, window_events, window_start, window_end
                    )
                    trend_results.append(result)
                    patient_state["trend_results"][trend_name] = result

        # Evaluate logic expressions
        for logic_name, logic in compiled.logic.items():
            join_fn = LogicJoinFunction(logic, compiled.name, compiled.version)
            result = join_fn.process(patient_id, patient_state["trend_results"], event.timestamp)
            if result:
                logic_results.append(result)

        return trend_results, logic_results, state
