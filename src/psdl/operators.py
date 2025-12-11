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

Null Handling (per PSDL spec):
- DataPoint.value can be None (null observation)
- count() includes null values (counts observations)
- Other operators filter out null values before computing
- last()/first() return null if most recent/first value is null
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class DataPoint:
    """A single time-series data point with optional null value."""

    timestamp: datetime
    value: Optional[float]  # Can be None per PSDL spec


class TemporalOperators:
    """
    Temporal operators for PSDL trend computation.

    These operators work on lists of DataPoint objects sorted by timestamp.
    All window-based operators filter data to the specified time window
    before computing.

    Null Handling:
    - count() includes all observations (even nulls)
    - last()/first() return the value as-is (may be null)
    - Other operators filter out null values before computing
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
            Filtered list of DataPoints within the window (includes nulls)
        """
        if not data:
            return []

        ref_time = reference_time or datetime.now()
        window_start = ref_time - timedelta(seconds=window_seconds)

        return [dp for dp in data if window_start <= dp.timestamp <= ref_time]

    @staticmethod
    def filter_non_null(data: List[DataPoint]) -> List[DataPoint]:
        """
        Filter out data points with null values.

        Args:
            data: List of DataPoints

        Returns:
            List of DataPoints with non-null values only
        """
        return [dp for dp in data if dp.value is not None]

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
    def exists(data: List[DataPoint]) -> bool:
        """
        Check if any data exists for the signal.

        Args:
            data: List of DataPoints sorted by timestamp

        Returns:
            True if any data points exist, False otherwise
        """
        return len(data) > 0

    @staticmethod
    def missing(data: List[DataPoint]) -> bool:
        """
        Check if no data exists for the signal (inverse of exists).

        Args:
            data: List of DataPoints sorted by timestamp

        Returns:
            True if no data points exist, False otherwise
        """
        return len(data) == 0

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
            Absolute change, or None if insufficient data (< 2 non-null values)
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if len(non_null) < 2:
            return None

        first_val = non_null[0].value
        last_val = non_null[-1].value
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
            Slope (units per second), or None if insufficient data (< 2 non-null values)
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if len(non_null) < 2:
            return None

        # Convert timestamps to seconds from first point
        t0 = non_null[0].timestamp
        x = [(dp.timestamp - t0).total_seconds() for dp in non_null]
        y = [dp.value for dp in non_null]

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
            Simple moving average, or None if no non-null data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if not non_null:
            return None

        return sum(dp.value for dp in non_null) / len(non_null)

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
            Exponential moving average, or None if no non-null data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if not non_null:
            return None

        if len(non_null) == 1:
            return non_null[0].value

        # Calculate span based on number of points
        span = len(non_null)
        alpha = 2.0 / (span + 1)

        # Calculate EMA
        ema = non_null[0].value
        for dp in non_null[1:]:
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
            Minimum value, or None if no non-null data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if not non_null:
            return None
        return min(dp.value for dp in non_null)

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
            Maximum value, or None if no non-null data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if not non_null:
            return None
        return max(dp.value for dp in non_null)

    @staticmethod
    def count(
        data: List[DataPoint],
        window_seconds: int,
        reference_time: Optional[datetime] = None,
    ) -> int:
        """
        Count observations within the window.

        Note: Per PSDL spec, count() includes ALL observations,
        even those with null values (counts observations, not valid values).

        Args:
            data: List of DataPoints sorted by timestamp
            window_seconds: Window size in seconds
            reference_time: End of window

        Returns:
            Number of observations in window (including nulls)
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
            Standard deviation, or None if insufficient non-null data (< 2 values)
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if len(non_null) < 2:
            return None

        mean = sum(dp.value for dp in non_null) / len(non_null)
        variance = sum((dp.value - mean) ** 2 for dp in non_null) / (len(non_null) - 1)
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
            Percentile value, or None if no non-null data
        """
        filtered = TemporalOperators.filter_by_window(data, window_seconds, reference_time)
        # Filter out null values per spec
        non_null = TemporalOperators.filter_non_null(filtered)
        if not non_null:
            return None

        values = sorted(dp.value for dp in non_null)
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
    # Windowed operators
    "delta": TemporalOperators.delta,
    "slope": TemporalOperators.slope,
    "ema": TemporalOperators.ema,
    "sma": TemporalOperators.sma,
    "min": TemporalOperators.min_val,
    "max": TemporalOperators.max_val,
    "count": TemporalOperators.count,
    "first": TemporalOperators.first,
    "std": TemporalOperators.std,
    "stddev": TemporalOperators.std,  # Alias for std
    "percentile": TemporalOperators.percentile,
    # Pointwise operators
    "last": lambda data, *args: TemporalOperators.last(data),
    "exists": lambda data, *args: TemporalOperators.exists(data),
    "missing": lambda data, *args: TemporalOperators.missing(data),
}


def apply_operator(
    operator: str,
    data: List[DataPoint],
    window_seconds: Optional[int] = None,
    reference_time: Optional[datetime] = None,
    percentile_value: Optional[float] = None,
) -> Optional[float]:
    """
    Apply a named operator to data.

    Args:
        operator: Operator name (delta, slope, ema, etc.)
        data: List of DataPoints
        window_seconds: Window size (required for windowed operators)
        reference_time: Reference time for window
        percentile_value: Percentile value (0-100) for percentile operator

    Returns:
        Computed value, or None if computation fails
    """
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator: {operator}")

    op_func = OPERATORS[operator]

    # Pointwise operators (no window required)
    if operator in ("last", "exists", "missing"):
        return op_func(data)

    # Windowed operators require window
    if window_seconds is None:
        raise ValueError(f"Operator '{operator}' requires a window specification")

    # Percentile requires additional parameter
    if operator == "percentile":
        if percentile_value is None:
            raise ValueError("percentile operator requires percentile_value parameter")
        return TemporalOperators.percentile(data, window_seconds, percentile_value, reference_time)

    return op_func(data, window_seconds, reference_time)
