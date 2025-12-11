"""
PSDL Streaming Operators - Flink Window and Process Functions

Implements PSDL temporal operators as Flink streaming primitives:
- delta(signal, window, [slide]) -> SlidingEventTimeWindow + ProcessWindowFunction
- slope(signal, window, [slide]) -> SlidingEventTimeWindow + ProcessWindowFunction
- ema(signal, window) -> KeyedProcessFunction (stateful)
- last(signal) -> KeyedProcessFunction
- min/max(signal, window, [slide]) -> SlidingEventTimeWindow + AggregateFunction
- count(signal, window, [slide]) -> SlidingEventTimeWindow + count()

These classes are designed for PyFlink but can be tested in isolation.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import ClinicalEvent, TrendResult


class WindowFunction(ABC):
    """Base class for window-based operators."""

    def __init__(
        self,
        trend_name: str,
        threshold: Optional[float] = None,
        comparison: str = ">",
        description: Optional[str] = None,
    ):
        """
        Initialize window function.

        Args:
            trend_name: Name of the PSDL trend
            threshold: Value to compare against (for boolean result)
            comparison: Comparison operator (>, <, >=, <=, ==, !=)
            description: Human-readable description
        """
        self.trend_name = trend_name
        self.threshold = threshold
        self.comparison = comparison
        self.description = description

    @abstractmethod
    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute the operator value from windowed events."""
        pass

    def evaluate(self, value: float) -> bool:
        """Evaluate the threshold condition."""
        if self.threshold is None:
            return True  # No threshold means always true if value exists

        if self.comparison == ">":
            return value > self.threshold
        elif self.comparison == "<":
            return value < self.threshold
        elif self.comparison == ">=":
            return value >= self.threshold
        elif self.comparison == "<=":
            return value <= self.threshold
        elif self.comparison == "==":
            return value == self.threshold
        elif self.comparison == "!=":
            return value != self.threshold
        else:
            raise ValueError(f"Unknown comparison operator: {self.comparison}")

    def process(
        self,
        patient_id: str,
        events: List[ClinicalEvent],
        window_start: datetime,
        window_end: datetime,
    ) -> TrendResult:
        """
        Process a window of events and produce a TrendResult.

        This method matches Flink's ProcessWindowFunction.process() signature.
        """
        if not events:
            return TrendResult(
                patient_id=patient_id,
                trend_name=self.trend_name,
                value=float("nan"),
                result=False,
                timestamp=window_end,
                window_start=window_start,
                window_end=window_end,
                input_count=0,
                description=self.description,
            )

        value = self.compute(events)
        result = self.evaluate(value)

        return TrendResult(
            patient_id=patient_id,
            trend_name=self.trend_name,
            value=value,
            result=result,
            timestamp=window_end,
            window_start=window_start,
            window_end=window_end,
            input_count=len(events),
            description=self.description,
        )


class DeltaWindowFunction(WindowFunction):
    """
    Compute delta (change) over a window.

    delta(signal, window) = last_value - first_value

    Example PSDL:
        hr_rise:
          expr: delta(HR, 1h) > 20
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute delta as last - first value in window."""
        if len(events) < 2:
            return 0.0

        sorted_events = sorted(events, key=lambda e: e.timestamp)
        first_value = sorted_events[0].value
        last_value = sorted_events[-1].value

        return last_value - first_value


class SlopeWindowFunction(WindowFunction):
    """
    Compute slope (linear trend) over a window.

    Uses simple linear regression: slope = Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²
    where x is time (in minutes) and y is the signal value.

    Example PSDL:
        hr_trend_up:
          expr: slope(HR, 2h) > 5
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute slope using linear regression."""
        if len(events) < 2:
            return 0.0

        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # Convert timestamps to minutes from first event
        base_time = sorted_events[0].timestamp
        x_values = [(e.timestamp - base_time).total_seconds() / 60.0 for e in sorted_events]
        y_values = [e.value for e in sorted_events]

        # Calculate means
        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)

        # Calculate slope: Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)

        if denominator == 0:
            return 0.0

        # Slope in units per hour
        slope_per_minute = numerator / denominator
        slope_per_hour = slope_per_minute * 60.0

        return slope_per_hour


class MinWindowFunction(WindowFunction):
    """
    Compute minimum value over a window.

    Example PSDL:
        hr_low:
          expr: min(HR, 1h) < 50
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute minimum value in window."""
        if not events:
            return float("inf")
        return min(e.value for e in events)


class MaxWindowFunction(WindowFunction):
    """
    Compute maximum value over a window.

    Example PSDL:
        hr_high:
          expr: max(HR, 1h) > 120
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute maximum value in window."""
        if not events:
            return float("-inf")
        return max(e.value for e in events)


class CountWindowFunction(WindowFunction):
    """
    Count observations in a window.

    Example PSDL:
        enough_data:
          expr: count(HR, 1h) >= 6
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Count events in window."""
        return float(len(events))


class SMAWindowFunction(WindowFunction):
    """
    Compute Simple Moving Average over a window.

    Example PSDL:
        hr_avg_high:
          expr: sma(HR, 1h) > 100
    """

    def compute(self, events: List[ClinicalEvent]) -> float:
        """Compute simple moving average."""
        if not events:
            return 0.0
        return sum(e.value for e in events) / len(events)


class ProcessFunction(ABC):
    """Base class for stateful process functions."""

    def __init__(
        self,
        trend_name: str,
        threshold: Optional[float] = None,
        comparison: str = ">",
        description: Optional[str] = None,
    ):
        """Initialize process function."""
        self.trend_name = trend_name
        self.threshold = threshold
        self.comparison = comparison
        self.description = description

    @abstractmethod
    def process_element(
        self, event: ClinicalEvent, state: Dict[str, Any]
    ) -> Tuple[TrendResult, Dict[str, Any]]:
        """
        Process a single event with state.

        Args:
            event: Incoming clinical event
            state: Current state for this patient

        Returns:
            Tuple of (result, new_state)
        """
        pass

    def evaluate(self, value: float) -> bool:
        """Evaluate the threshold condition."""
        if self.threshold is None:
            return True

        if self.comparison == ">":
            return value > self.threshold
        elif self.comparison == "<":
            return value < self.threshold
        elif self.comparison == ">=":
            return value >= self.threshold
        elif self.comparison == "<=":
            return value <= self.threshold
        elif self.comparison == "==":
            return value == self.threshold
        elif self.comparison == "!=":
            return value != self.threshold
        else:
            raise ValueError(f"Unknown comparison operator: {self.comparison}")


class LastProcessFunction(ProcessFunction):
    """
    Return the most recent value.

    Stateless in terms of computation, but tracked for consistency.

    Example PSDL:
        hypoxia:
          expr: last(SpO2) < 92
    """

    def process_element(
        self, event: ClinicalEvent, state: Dict[str, Any]
    ) -> Tuple[TrendResult, Dict[str, Any]]:
        """Process event and return the current value."""
        value = event.value
        result = self.evaluate(value)

        # Update state with last seen value
        new_state = {
            "last_value": value,
            "last_timestamp": event.timestamp,
        }

        trend_result = TrendResult(
            patient_id=event.patient_id,
            trend_name=self.trend_name,
            value=value,
            result=result,
            timestamp=event.timestamp,
            input_count=1,
            description=self.description,
        )

        return trend_result, new_state


class EMAProcessFunction(ProcessFunction):
    """
    Compute Exponential Moving Average.

    EMA = α * current_value + (1 - α) * previous_EMA

    The alpha (decay factor) is derived from the window size:
    α = 2 / (N + 1) where N is the number of periods in the window.

    Example PSDL:
        hr_smoothed:
          expr: ema(HR, 1h) > 100
    """

    def __init__(
        self,
        trend_name: str,
        window_ms: int,
        threshold: Optional[float] = None,
        comparison: str = ">",
        description: Optional[str] = None,
    ):
        """
        Initialize EMA process function.

        Args:
            trend_name: Name of the PSDL trend
            window_ms: Window size in milliseconds (for alpha calculation)
            threshold: Value to compare against
            comparison: Comparison operator
            description: Human-readable description
        """
        super().__init__(trend_name, threshold, comparison, description)
        self.window_ms = window_ms

        # Calculate alpha based on window size
        # Assume observations every minute, so N = window_minutes
        window_minutes = window_ms / (60 * 1000)
        self.alpha = 2.0 / (window_minutes + 1)

    def process_element(
        self, event: ClinicalEvent, state: Dict[str, Any]
    ) -> Tuple[TrendResult, Dict[str, Any]]:
        """Process event and update EMA."""
        current_value = event.value

        # Get previous EMA from state
        previous_ema = state.get("ema")

        if previous_ema is None:
            # First value initializes the EMA
            new_ema = current_value
        else:
            # EMA formula: α * current + (1 - α) * previous
            new_ema = self.alpha * current_value + (1 - self.alpha) * previous_ema

        result = self.evaluate(new_ema)

        new_state = {
            "ema": new_ema,
            "last_timestamp": event.timestamp,
            "count": state.get("count", 0) + 1,
        }

        trend_result = TrendResult(
            patient_id=event.patient_id,
            trend_name=self.trend_name,
            value=new_ema,
            result=result,
            timestamp=event.timestamp,
            input_count=new_state["count"],
            description=self.description,
        )

        return trend_result, new_state


# Factory functions for creating operators from PSDL expressions


def create_window_function(
    operator_name: str,
    trend_name: str,
    threshold: Optional[float] = None,
    comparison: str = ">",
    description: Optional[str] = None,
) -> WindowFunction:
    """
    Create appropriate window function for a PSDL operator.

    Args:
        operator_name: Name of the operator (delta, slope, min, max, count, sma)
        trend_name: Name of the PSDL trend
        threshold: Threshold value for comparison
        comparison: Comparison operator
        description: Description of the trend

    Returns:
        WindowFunction subclass instance
    """
    operators = {
        "delta": DeltaWindowFunction,
        "slope": SlopeWindowFunction,
        "min": MinWindowFunction,
        "max": MaxWindowFunction,
        "count": CountWindowFunction,
        "sma": SMAWindowFunction,
    }

    if operator_name not in operators:
        raise ValueError(f"Unknown window operator: {operator_name}")

    return operators[operator_name](
        trend_name=trend_name,
        threshold=threshold,
        comparison=comparison,
        description=description,
    )


def create_process_function(
    operator_name: str,
    trend_name: str,
    window_ms: Optional[int] = None,
    threshold: Optional[float] = None,
    comparison: str = ">",
    description: Optional[str] = None,
) -> ProcessFunction:
    """
    Create appropriate process function for a PSDL operator.

    Args:
        operator_name: Name of the operator (last, ema)
        trend_name: Name of the PSDL trend
        window_ms: Window size in ms (required for ema)
        threshold: Threshold value for comparison
        comparison: Comparison operator
        description: Description of the trend

    Returns:
        ProcessFunction subclass instance
    """
    if operator_name == "last":
        return LastProcessFunction(
            trend_name=trend_name,
            threshold=threshold,
            comparison=comparison,
            description=description,
        )
    elif operator_name == "ema":
        if window_ms is None:
            raise ValueError("EMA operator requires window_ms parameter")
        return EMAProcessFunction(
            trend_name=trend_name,
            window_ms=window_ms,
            threshold=threshold,
            comparison=comparison,
            description=description,
        )
    else:
        raise ValueError(f"Unknown process operator: {operator_name}")
