"""
PSDL Single Patient Evaluator - Python-based patient evaluation.

This module provides:
1. Single patient scenario evaluation
2. Pluggable data backends (in-memory, OMOP, FHIR)
3. Temporal operator computation
4. Logic expression evaluation
5. ScenarioIR integration for DAG-ordered evaluation

Version 0.3.0 Changes (RFC-0005):
- Added to_standard_result() for v0.3 EvaluationResult format
- Added triggered property for v0.3 compatibility
- Added ScenarioIR integration with from_ir() class method
- Added compilation_hashes to EvaluationResult for audit trails

Usage:
    # From parsed scenario
    evaluator = SinglePatientEvaluator(scenario, backend)
    result = evaluator.evaluate(patient_id=123)

    # From compiled IR (recommended for audit trails)
    from psdl.core.compile import compile_scenario
    ir = compile_scenario("scenario.yaml")
    evaluator = SinglePatientEvaluator.from_ir(ir, backend)
    result = evaluator.evaluate(patient_id=123)

    # v0.3 standard format
    standard_result = result.to_standard_result()
"""

import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ...core.ir import EvaluationResult as StandardEvaluationResult
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
class CompilationHashes:
    """Compilation hashes for audit trail (from ScenarioIR)."""

    spec_hash: str
    ir_hash: str
    toolchain_hash: str


@dataclass
class EvaluationResult:
    """Result of evaluating a scenario for a patient."""

    patient_id: Any
    timestamp: datetime
    triggered_logic: List[str]  # Names of logic expressions that evaluated to True
    trend_values: Dict[str, Optional[float]]
    trend_results: Dict[str, bool]
    logic_results: Dict[str, bool]
    compilation_hashes: Optional[CompilationHashes] = None  # From ScenarioIR

    @property
    def is_triggered(self) -> bool:
        """True if any logic expression triggered."""
        return len(self.triggered_logic) > 0

    @property
    def any_triggered(self) -> bool:
        """Alias for is_triggered for backward compatibility."""
        return self.is_triggered

    @property
    def triggered(self) -> bool:
        """v0.3 compatible alias for is_triggered."""
        return self.is_triggered

    def to_standard_result(self) -> StandardEvaluationResult:
        """
        Convert to v0.3 StandardEvaluationResult format.

        Returns:
            StandardEvaluationResult with standardized fields
        """
        # Filter out None values from trend_values for standard format
        filtered_trend_values = {k: v for k, v in self.trend_values.items() if v is not None}

        return StandardEvaluationResult(
            patient_id=str(self.patient_id),
            triggered=self.is_triggered,
            triggered_logic=self.triggered_logic,
            current_state=None,  # State machine not evaluated in single patient mode
            trend_values=filtered_trend_values,
            logic_results=self.logic_results,
            index_time=self.timestamp if self.is_triggered else None,
        )


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
    - ScenarioIR integration for DAG-ordered evaluation and audit trails

    For large cohort analysis, use the CohortCompiler from runtimes.cohort.

    Usage:
        # From parsed scenario
        scenario = parser.parse_file("scenario.yaml")
        evaluator = SinglePatientEvaluator(scenario, backend)

        # From compiled IR (recommended for production/audit)
        from psdl.core.compile import compile_scenario
        ir = compile_scenario("scenario.yaml")
        evaluator = SinglePatientEvaluator.from_ir(ir, backend)

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

    def __init__(
        self,
        scenario: PSDLScenario,
        backend: DataBackend,
        scenario_ir: Optional[Any] = None,
    ):
        """
        Initialize evaluator with a scenario and data backend.

        Args:
            scenario: Parsed PSDL scenario
            backend: Data backend for fetching patient data
            scenario_ir: Optional compiled ScenarioIR for DAG ordering and hashes
        """
        self.scenario = scenario
        self.backend = backend
        self._scenario_ir = scenario_ir

        # Calculate max window needed for data fetching
        self._max_window_seconds = self._calculate_max_window()

        # Extract DAG order if IR is provided
        self._trend_order: Optional[List[str]] = None
        self._logic_order: Optional[List[str]] = None
        self._compilation_hashes: Optional[CompilationHashes] = None

        if scenario_ir is not None:
            self._trend_order = scenario_ir.dag.trend_order
            self._logic_order = scenario_ir.dag.logic_order
            self._compilation_hashes = CompilationHashes(
                spec_hash=scenario_ir.spec_hash,
                ir_hash=scenario_ir.ir_hash,
                toolchain_hash=scenario_ir.toolchain_hash,
            )

    @classmethod
    def from_ir(cls, scenario_ir: Any, backend: "DataBackend") -> "SinglePatientEvaluator":
        """
        Create an evaluator from a compiled ScenarioIR.

        This is the recommended way to create evaluators for production use,
        as it provides:
        - Pre-computed DAG order for efficient evaluation
        - Compilation hashes for audit trails
        - Validated scenario with resolved dependencies

        Args:
            scenario_ir: Compiled ScenarioIR from compile_scenario()
            backend: Data backend for fetching patient data

        Returns:
            SinglePatientEvaluator configured with IR

        Usage:
            from psdl.core.compile import compile_scenario
            ir = compile_scenario("scenario.yaml")
            evaluator = SinglePatientEvaluator.from_ir(ir, backend)
        """
        if scenario_ir.scenario is None:
            raise ValueError("ScenarioIR does not contain original scenario")
        return cls(scenario_ir.scenario, backend, scenario_ir=scenario_ir)

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
        trend_values: Optional[Dict[str, Optional[float]]] = None,
    ) -> bool:
        """
        Evaluate a logic expression.

        Supports: AND, OR, NOT operators with proper precedence.
        v0.3: Also supports comparison operators (>=, <=, >, <, ==, !=) with trend values.

        NULL handling: If any trend value used in a comparison is None,
        the comparison evaluates to False (SQL-like semantics).
        """
        expr = logic.expr

        # v0.3: Check if expression contains comparison operators
        has_comparison = any(op in expr for op in [">=", "<=", ">", "<", "==", "!="])

        # Replace term names with their values
        # Process in order of length (longest first) to avoid partial replacements
        terms_by_length = sorted(logic.terms, key=len, reverse=True)

        for term in terms_by_length:
            if has_comparison and trend_values and term in trend_values:
                # v0.3: Use numeric trend value for comparisons
                value = trend_values.get(term)
                if value is None:
                    # NULL comparison semantics: if value is None, replace with
                    # a marker that makes the comparison False
                    # We use "None" as a Python literal that will make comparisons fail safely
                    replacement = "None"
                else:
                    replacement = str(value)
            else:
                # Use boolean result from trends or logic
                value = trend_results.get(term)
                if value is None:
                    value = logic_results.get(term, False)
                replacement = str(value)

            # Replace term with value (case-insensitive)
            pattern = r"\b" + re.escape(term) + r"\b"
            expr = re.sub(pattern, replacement, expr, flags=re.IGNORECASE)

        # Convert logic operators to Python
        expr = expr.replace(" AND ", " and ").replace(" and ", " and ")
        expr = expr.replace(" OR ", " or ").replace(" or ", " or ")
        expr = re.sub(r"\bNOT\s+", "not ", expr, flags=re.IGNORECASE)

        # Evaluate the expression safely
        try:
            # Allow boolean and comparison operations
            # None comparisons will raise TypeError, which we catch and return False
            result = eval(expr, {"__builtins__": {}}, {"True": True, "False": False, "None": None})
            return bool(result)
        except TypeError:
            # None comparison (e.g., None < 92) - return False per NULL semantics
            return False
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
            (includes compilation_hashes if evaluator was created from ScenarioIR)
        """
        ref_time = reference_time or datetime.now()

        # Fetch all signal data
        signal_data = self._fetch_all_signals(patient_id, ref_time)

        # Evaluate all trends (use DAG order if available)
        trend_values: Dict[str, Optional[float]] = {}
        trend_results: Dict[str, bool] = {}

        trend_names = self._trend_order if self._trend_order else list(self.scenario.trends.keys())
        for name in trend_names:
            trend = self.scenario.trends[name]
            value, result = self._evaluate_trend(trend, signal_data, ref_time)
            trend_values[name] = value
            trend_results[name] = result

        # Evaluate all logic expressions (use DAG order if available)
        logic_results: Dict[str, bool] = {}
        triggered_logic: List[str] = []

        if self._logic_order:
            # Use pre-computed DAG order from ScenarioIR
            for name in self._logic_order:
                logic = self.scenario.logic[name]
                result = self._evaluate_logic(logic, trend_results, logic_results, trend_values)
                logic_results[name] = result
                if result:
                    triggered_logic.append(name)
        else:
            # Fall back to on-the-fly topological sort
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
                        result = self._evaluate_logic(
                            logic, trend_results, logic_results, trend_values
                        )
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
            compilation_hashes=self._compilation_hashes,
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
