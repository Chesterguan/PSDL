"""
PSDL Single Patient Evaluator - Python-based patient evaluation.

This module provides:
1. Single patient scenario evaluation
2. Pluggable data backends (in-memory, OMOP, FHIR)
3. Temporal operator computation
4. Logic expression evaluation

Usage:
    evaluator = SinglePatientEvaluator(scenario, backend)
    result = evaluator.evaluate(patient_id=123)
"""

import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ...core.ir import LogicExpr, PSDLScenario, Signal, TrendExpr
from ...operators import DataPoint, TemporalOperators, apply_operator


@dataclass
class EvaluationContext:
    """Context for a single patient evaluation."""

    patient_id: Any
    reference_time: datetime
    signal_data: Dict[str, List[DataPoint]] = field(default_factory=dict)
    trend_values: Dict[str, Optional[float]] = field(default_factory=dict)
    trend_results: Dict[str, bool] = field(default_factory=dict)
    logic_results: Dict[str, bool] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Result of evaluating a scenario for a patient."""

    patient_id: Any
    timestamp: datetime
    triggered_logic: List[str]  # Names of logic expressions that evaluated to True
    trend_values: Dict[str, Optional[float]]
    trend_results: Dict[str, bool]
    logic_results: Dict[str, bool]

    @property
    def is_triggered(self) -> bool:
        """True if any logic expression triggered."""
        return len(self.triggered_logic) > 0

    @property
    def any_triggered(self) -> bool:
        """Alias for is_triggered for backward compatibility."""
        return self.is_triggered


class DataBackend(ABC):
    """
    Abstract base class for data backends.

    Implement this interface to connect PSDL to different data sources:
    - OMOP CDM (SQL)
    - FHIR servers
    - In-memory data
    - Streaming sources
    """

    @abstractmethod
    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """
        Fetch time-series data for a signal.

        Args:
            patient_id: Patient identifier
            signal: Signal definition
            window_seconds: How far back to fetch
            reference_time: End of the time window

        Returns:
            List of DataPoints sorted by timestamp (ascending)
        """
        pass

    @abstractmethod
    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Get patient IDs matching population criteria.

        Args:
            population_include: Inclusion criteria expressions
            population_exclude: Exclusion criteria expressions

        Returns:
            List of patient IDs
        """
        pass


class InMemoryBackend(DataBackend):
    """
    In-memory data backend for testing.

    Usage:
        backend = InMemoryBackend()
        backend.add_data(patient_id=1, signal_name="Cr", data=[
            DataPoint(datetime(2024, 1, 1, 10, 0), 1.0),
            DataPoint(datetime(2024, 1, 1, 16, 0), 1.4),
        ])
    """

    def __init__(self):
        self.data: Dict[Any, Dict[str, List[DataPoint]]] = {}
        self.patients: Set[Any] = set()

    def add_data(self, patient_id: Any, signal_name: str, data: List[DataPoint]):
        """Add signal data for a patient."""
        if patient_id not in self.data:
            self.data[patient_id] = {}
        self.data[patient_id][signal_name] = sorted(data, key=lambda dp: dp.timestamp)
        self.patients.add(patient_id)

    def add_observation(self, patient_id: Any, signal_name: str, value: float, timestamp: datetime):
        """
        Add a single observation for a patient (convenience method).

        Args:
            patient_id: Patient identifier
            signal_name: Name of the signal
            value: Observation value
            timestamp: When the observation was recorded
        """
        if patient_id not in self.data:
            self.data[patient_id] = {}
        if signal_name not in self.data[patient_id]:
            self.data[patient_id][signal_name] = []
        self.data[patient_id][signal_name].append(DataPoint(timestamp=timestamp, value=value))
        self.data[patient_id][signal_name].sort(key=lambda dp: dp.timestamp)
        self.patients.add(patient_id)

    def add_patient(self, patient_id: Any, **attributes):
        """Add a patient with optional attributes."""
        self.patients.add(patient_id)

    def observation_count(self) -> int:
        """Return total number of observations across all patients."""
        total = 0
        for patient_data in self.data.values():
            for signal_data in patient_data.values():
                total += len(signal_data)
        return total

    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """Fetch signal data from in-memory store."""
        patient_data = self.data.get(patient_id, {})
        signal_data = patient_data.get(signal.name, [])

        # Filter by window
        return TemporalOperators.filter_by_window(signal_data, window_seconds, reference_time)

    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """Get all patient IDs (filtering not implemented for in-memory)."""
        return list(self.patients)


class SinglePatientEvaluator:
    """
    Evaluates PSDL scenarios for single patients.

    This runtime is optimized for:
    - Low latency (Python in-memory computation)
    - Interactive use
    - Testing and development

    For large cohort analysis, use the CohortCompiler from runtimes.cohort.

    Usage:
        scenario = parser.parse_file("scenario.yaml")
        evaluator = SinglePatientEvaluator(scenario, backend)

        # Single patient
        result = evaluator.evaluate(patient_id=123)

        # Multiple patients (parallel)
        results = evaluator.evaluate_batch(patient_ids=[1, 2, 3], max_workers=4)
    """

    # Comparison operators for trend thresholds
    COMPARATORS = {
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "==": lambda a, b: abs(a - b) < 1e-10,
        "!=": lambda a, b: abs(a - b) >= 1e-10,
    }

    def __init__(self, scenario: PSDLScenario, backend: DataBackend):
        """
        Initialize evaluator with a scenario and data backend.

        Args:
            scenario: Parsed PSDL scenario
            backend: Data backend for fetching patient data
        """
        self.scenario = scenario
        self.backend = backend

        # Calculate max window needed for data fetching
        self._max_window_seconds = self._calculate_max_window()

    def _calculate_max_window(self) -> int:
        """Calculate the maximum window size needed across all trends."""
        max_window = 3600  # Default 1 hour

        for trend in self.scenario.trends.values():
            if trend.window:
                max_window = max(max_window, trend.window.seconds)

        return max_window

    def _fetch_all_signals(
        self, patient_id: Any, reference_time: datetime
    ) -> Dict[str, List[DataPoint]]:
        """Fetch all signal data for a patient."""
        signal_data = {}

        for name, signal in self.scenario.signals.items():
            data = self.backend.fetch_signal_data(
                patient_id=patient_id,
                signal=signal,
                window_seconds=self._max_window_seconds,
                reference_time=reference_time,
            )
            signal_data[name] = data

        return signal_data

    def _evaluate_trend(
        self,
        trend: TrendExpr,
        signal_data: Dict[str, List[DataPoint]],
        reference_time: datetime,
    ) -> Tuple[Optional[float], bool]:
        """
        Evaluate a single trend expression.

        Returns:
            Tuple of (computed_value, threshold_result)
        """
        data = signal_data.get(trend.signal, [])

        if not data:
            return None, False

        # Get window in seconds
        window_seconds = trend.window.seconds if trend.window else self._max_window_seconds

        # Apply operator
        value = apply_operator(
            operator=trend.operator,
            data=data,
            window_seconds=window_seconds,
            reference_time=reference_time,
        )

        if value is None:
            return None, False

        # Apply threshold comparison if specified
        if trend.comparator and trend.threshold is not None:
            comparator_fn = self.COMPARATORS.get(trend.comparator)
            if comparator_fn:
                result = comparator_fn(value, trend.threshold)
                return value, result

        # No threshold - return raw value (truthy if non-zero)
        return value, bool(value)

    def _evaluate_logic(
        self,
        logic: LogicExpr,
        trend_results: Dict[str, bool],
        logic_results: Dict[str, bool],
    ) -> bool:
        """
        Evaluate a logic expression.

        Supports: AND, OR, NOT operators with proper precedence.
        """
        expr = logic.expr.upper()

        # Replace term names with their boolean values
        # Process in order of length (longest first) to avoid partial replacements
        terms_by_length = sorted(logic.terms, key=len, reverse=True)

        for term in terms_by_length:
            # Look up value in trends first, then logic
            value = trend_results.get(term)
            if value is None:
                value = logic_results.get(term, False)

            # Replace term with Python boolean
            pattern = r"\b" + re.escape(term.upper()) + r"\b"
            expr = re.sub(pattern, str(value), expr)

        # Convert logic operators to Python
        expr = expr.replace(" AND ", " and ")
        expr = expr.replace(" OR ", " or ")
        expr = re.sub(r"\bNOT\s+", "not ", expr)

        # Evaluate the expression safely
        try:
            # Only allow boolean operations
            allowed_names = {
                "True": True,
                "False": False,
                "and": None,
                "or": None,
                "not": None,
            }
            result = eval(expr, {"__builtins__": {}}, allowed_names)
            return bool(result)
        except Exception:
            return False

    def evaluate(
        self, patient_id: Any, reference_time: Optional[datetime] = None
    ) -> EvaluationResult:
        """
        Evaluate the scenario for a single patient.

        Args:
            patient_id: Patient identifier
            reference_time: Point in time for evaluation (defaults to now)

        Returns:
            EvaluationResult with all computed values and triggered logic
        """
        ref_time = reference_time or datetime.now()

        # Fetch all signal data
        signal_data = self._fetch_all_signals(patient_id, ref_time)

        # Evaluate all trends
        trend_values: Dict[str, Optional[float]] = {}
        trend_results: Dict[str, bool] = {}

        for name, trend in self.scenario.trends.items():
            value, result = self._evaluate_trend(trend, signal_data, ref_time)
            trend_values[name] = value
            trend_results[name] = result

        # Evaluate all logic expressions
        logic_results: Dict[str, bool] = {}
        triggered_logic: List[str] = []

        # Sort logic by dependency order (simple topological sort)
        evaluated = set()
        to_evaluate = list(self.scenario.logic.keys())

        while to_evaluate:
            made_progress = False
            for name in to_evaluate[:]:
                logic = self.scenario.logic[name]

                # Check if all dependencies are resolved
                deps_resolved = all(
                    term in trend_results or term in logic_results for term in logic.terms
                )

                if deps_resolved:
                    result = self._evaluate_logic(logic, trend_results, logic_results)
                    logic_results[name] = result
                    if result:
                        triggered_logic.append(name)
                    evaluated.add(name)
                    to_evaluate.remove(name)
                    made_progress = True

            if not made_progress and to_evaluate:
                # Circular dependency or undefined terms - evaluate remaining as False
                for name in to_evaluate:
                    logic_results[name] = False
                break

        return EvaluationResult(
            patient_id=patient_id,
            timestamp=ref_time,
            triggered_logic=triggered_logic,
            trend_values=trend_values,
            trend_results=trend_results,
            logic_results=logic_results,
        )

    # Legacy alias
    def evaluate_patient(
        self, patient_id: Any, reference_time: Optional[datetime] = None
    ) -> EvaluationResult:
        """Legacy alias for evaluate()."""
        return self.evaluate(patient_id, reference_time)

    def evaluate_batch(
        self,
        patient_ids: Optional[List[Any]] = None,
        reference_time: Optional[datetime] = None,
        max_workers: Optional[int] = None,
    ) -> List[EvaluationResult]:
        """
        Evaluate the scenario for multiple patients.

        Args:
            patient_ids: List of patient IDs (defaults to all patients from backend)
            reference_time: Point in time for evaluation
            max_workers: Number of parallel workers (None=serial, 0=auto)

        Returns:
            List of EvaluationResults for all patients
        """
        ref_time = reference_time or datetime.now()

        # Get patient IDs if not provided
        if patient_ids is None:
            population = self.scenario.population
            patient_ids = self.backend.get_patient_ids(
                population_include=population.include if population else None,
                population_exclude=population.exclude if population else None,
            )

        # Serial execution
        if max_workers is None:
            results = []
            for patient_id in patient_ids:
                result = self.evaluate(patient_id, ref_time)
                results.append(result)
            return results

        # Parallel execution
        workers = max_workers if max_workers > 0 else None

        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_patient = {
                executor.submit(self.evaluate, patient_id, ref_time): patient_id
                for patient_id in patient_ids
            }

            for future in as_completed(future_to_patient):
                result = future.result()
                results.append(result)

        # Sort by patient_id for consistent ordering
        results.sort(key=lambda r: str(r.patient_id))

        return results

    # Legacy alias
    def evaluate_cohort(
        self,
        reference_time: Optional[datetime] = None,
        patient_ids: Optional[List[Any]] = None,
        max_workers: Optional[int] = None,
        use_sql: Optional[bool] = None,
    ) -> List[EvaluationResult]:
        """
        Legacy alias for evaluate_batch().

        Note: use_sql parameter is ignored - use CohortCompiler for SQL evaluation.
        """
        return self.evaluate_batch(patient_ids, reference_time, max_workers)

    def get_triggered_patients(
        self,
        reference_time: Optional[datetime] = None,
        logic_filter: Optional[List[str]] = None,
    ) -> List[EvaluationResult]:
        """
        Get only patients who triggered at least one logic expression.

        Args:
            reference_time: Point in time for evaluation
            logic_filter: Optional list of specific logic names to check

        Returns:
            List of EvaluationResults for triggered patients only
        """
        all_results = self.evaluate_batch(reference_time=reference_time)

        triggered = []
        for result in all_results:
            if logic_filter:
                if any(name in result.triggered_logic for name in logic_filter):
                    triggered.append(result)
            elif result.is_triggered:
                triggered.append(result)

        return triggered


# Legacy alias
PSDLEvaluator = SinglePatientEvaluator
