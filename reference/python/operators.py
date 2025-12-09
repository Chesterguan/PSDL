"""
PSDL Temporal Operators - Time-series computation functions.

These operators form the computational core of PSDL trend expressions:
- delta(signal, window) - Absolute change over window
- slope(signal, window) - Linear regression slope
- ema(signal, window)   - Exponential moving average
- sma(signal, window)   - Simple moving average
- min(signal, window)   - Minimum value in window
- max(signal, window)   - Maximum value in window
- count(signal, window) - Observation count in window
- last(signal)          - Most recent value
- first(signal, window) - First value in window
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class DataPoint:
    """A single time-series data point."""

    timestamp: datetime
    value: float


class TemporalOperators:
    """
    Temporal operators for PSDL trend computation.

    These operators work on lists of DataPoint objects sorted by timestamp.
    All window-based operators filter data to the specified time window
    before computing.
    """

    @staticmethod
    def filter_by_window(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> List[DataPoint]:
        """
        Filter data points to those within the time window.

        Args:
            data: List of DataPoints sorted by timestamp (ascending)
            window_seconds: Window size in seconds
            reference_time: End of window (defaults to now)

        Returns:
            Filtered list of DataPoints within the window
        """
        if not data:
            return []

        ref_time = reference_time or datetime.now()
        window_start = ref_time - timedelta(seconds=window_seconds)

        return [dp for dp in data if window_start <= dp.timestamp <= ref_time]

    @staticmethod
    def last(data: List[DataPoint]) -> Optional[float]:
        """
        Get the most recent value.

        Args:
            data: List of DataPoints sorted by timestamp

        Returns:
            Most recent value, or None if no data
        """
        if not data:
            return None
        return data[-1].value

    @staticmethod
    def first(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Get the first value within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            First value in window, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None
        return filtered[0].value

    @staticmethod
    def delta(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate absolute change over the window.
        delta = last_value - first_value_in_window

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Absolute change, or None if insufficient data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if len(filtered) < 2:
            return None

        first_val = filtered[0].value
        last_val = filtered[-1].value
        return last_val - first_val

    @staticmethod
    def slope(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate linear regression slope over the window.
        Uses least squares regression.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Slope (units per second), or None if insufficient data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if len(filtered) < 2:
            return None

        # Convert timestamps to seconds from first point
        t0 = filtered[0].timestamp
        x = [(dp.timestamp - t0).total_seconds() for dp in filtered]
        y = [dp.value for dp in filtered]

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        denominator = n * sum_x2 - sum_x * sum_x
        if abs(denominator) < 1e-10:
            return 0.0  # Vertical line or single point

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return slope

    @staticmethod
    def sma(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate Simple Moving Average over the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Simple moving average, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None

        return sum(dp.value for dp in filtered) / len(filtered)

    @staticmethod
    def ema(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate Exponential Moving Average over the window.
        Uses span = window_seconds / average_interval for smoothing factor.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Exponential moving average, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None

        if len(filtered) == 1:
            return filtered[0].value

        # Calculate span based on number of points
        span = len(filtered)
        alpha = 2.0 / (span + 1)

        # Calculate EMA
        ema = filtered[0].value
        for dp in filtered[1:]:
            ema = alpha * dp.value + (1 - alpha) * ema

        return ema

    @staticmethod
    def min_val(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Get minimum value within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Minimum value, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None
        return min(dp.value for dp in filtered)

    @staticmethod
    def max_val(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Get maximum value within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Maximum value, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None
        return max(dp.value for dp in filtered)

    @staticmethod
    def count(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> int:
        """
        Count observations within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Number of observations in window
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        return len(filtered)

    @staticmethod
    def std(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate standard deviation within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Standard deviation, or None if insufficient data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if len(filtered) < 2:
            return None

        mean = sum(dp.value for dp in filtered) / len(filtered)
        variance = sum((dp.value - mean) ** 2 for dp in filtered) / (len(filtered) - 1)
        return math.sqrt(variance)

    @staticmethod
    def percentile(
        data: List[DataPoint],
        window_seconds: int,
        p: float,
        reference_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Calculate percentile within the window.

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            p: Percentile (0-100)
            reference_time: End of window

        Returns:
            Percentile value, or None if no data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        if not filtered:
            return None

        values = sorted(dp.value for dp in filtered)
        n = len(values)

        if n == 1:
            return values[0]

        # Linear interpolation
        k = (p / 100) * (n - 1)
        f = math.floor(k)
        c = math.ceil(k)

        if f == c:
            return values[int(k)]

        return values[int(f)] * (c - k) + values[int(c)] * (k - f)


# Operator registry for dynamic lookup
OPERATORS = {
    "delta": TemporalOperators.delta,
    "slope": TemporalOperators.slope,
    "ema": TemporalOperators.ema,
    "sma": TemporalOperators.sma,
    "min": TemporalOperators.min_val,
    "max": TemporalOperators.max_val,
    "count": TemporalOperators.count,
    "last": lambda data, *args: TemporalOperators.last(data),
    "first": TemporalOperators.first,
    "std": TemporalOperators.std,
}


def apply_operator(
    operator: str,
    data: List[DataPoint],
    window_seconds: Optional[int] = None,
    reference_time: Optional[datetime] = None,
) -> Optional[float]:
    """
    Apply a named operator to data.

    Args:
        operator: Operator name (delta, slope, ema, etc.)
        data: List of DataPoints
        window_seconds: Window size (required for windowed operators)
        reference_time: Reference time for window

    Returns:
        Computed value, or None if computation fails
    """
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator: {operator}")

    op_func = OPERATORS[operator]

    if operator == "last":
        return op_func(data)
    elif window_seconds is None:
        raise ValueError(f"Operator '{operator}' requires a window specification")
    else:
        return op_func(data, window_seconds, reference_time)
