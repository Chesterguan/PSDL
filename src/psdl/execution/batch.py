"""
PSDL Batch Evaluator - Retrospective scenario execution.

This module provides:
1. Signal data fetching (pluggable backends)
2. Trend computation using temporal operators
3. Logic evaluation with boolean algebra
4. Patient-level scenario evaluation
5. Cohort-level batch evaluation with automatic optimization:
   - Small cohorts / explicit patient_ids: In-memory parallel evaluation
   - Large cohorts with OMOP backend: SQL push-down for database-side computation

Execution Modes:
    PSDL supports two execution modes based on timing:

    1. Batch (this module) - Retrospective analysis
       - OMOP backend: SQL database queries
       - Automatic SQL compilation for large cohorts

    2. Streaming (execution.streaming) - Real-time monitoring
       - FHIR events via subscriptions
       - Apache Flink for continuous processing

Usage:
    # Simple usage - system auto-selects best strategy
    evaluator = PSDLEvaluator(scenario, backend)
    results = evaluator.evaluate_cohort()  # Auto-optimized

    # Single patient evaluation
    result = evaluator.evaluate_patient(patient_id=123)

    # Explicit parallel execution
    results = evaluator.evaluate_cohort(max_workers=4)
"""

import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from ..adapters.omop import OMOPBackend

from ..core.ir import LogicExpr, PSDLScenario, Signal, TrendExpr
from ..operators import DataPoint, TemporalOperators, apply_operator


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

    def add_patient(self, patient_id: Any, **attributes):
        """Add a patient with optional attributes."""
        self.patients.add(patient_id)

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


class PSDLEvaluator:
    """
    Evaluates PSDL scenarios against patient data.

    Usage:
        scenario = parser.parse_file("scenario.yaml")
        evaluator = PSDLEvaluator(scenario, backend)

        # Single patient
        result = evaluator.evaluate_patient(patient_id=123)

        # All matching patients
        results = evaluator.evaluate_cohort()
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

    # Threshold for automatic SQL push-down (number of patients)
    SQL_PUSHDOWN_THRESHOLD = 1000

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

        # Check if SQL push-down is available
        self._sql_compiler = None
        if self._is_omop_backend():
            compiler = SQLCompiler(scenario, self.backend)
            if compiler.can_compile():
                self._sql_compiler = compiler

    def _is_omop_backend(self) -> bool:
        """Check if the backend is an OMOP backend that supports SQL push-down."""
        # Check by class name to avoid import issues
        return self.backend.__class__.__name__ == "OMOPBackend"

    def _should_use_sql(self, patient_ids: Optional[List[Any]] = None) -> bool:
        """
        Determine if SQL push-down should be used.

        Returns True if:
        - Backend is OMOP
        - Scenario can be compiled to SQL
        - No explicit patient_ids provided (evaluating full cohort)

        Note: We always use SQL for full cohort evaluation to avoid
        loading all patient IDs into memory first.
        """
        if self._sql_compiler is None:
            return False

        # If explicit patient_ids provided, use in-memory evaluation
        if patient_ids is not None:
            return False

        return True

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

    def evaluate_patient(
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

    def evaluate_cohort(
        self,
        reference_time: Optional[datetime] = None,
        patient_ids: Optional[List[Any]] = None,
        max_workers: Optional[int] = None,
        use_sql: Optional[bool] = None,
    ) -> List[EvaluationResult]:
        """
        Evaluate the scenario for all patients in the cohort.

        Automatically selects the best execution strategy:
        - SQL push-down: For OMOP backends with full cohort evaluation
        - Parallel in-memory: For explicit patient_ids or non-SQL backends
        - Serial in-memory: When max_workers is None

        Args:
            reference_time: Point in time for evaluation
            patient_ids: Optional list of patient IDs (otherwise uses population filter)
            max_workers: Number of parallel workers (None=serial, 0=auto based on CPU count)
            use_sql: Force SQL mode (True), in-memory mode (False), or auto-detect (None)

        Returns:
            List of EvaluationResults for all patients

        Example:
            # Auto-detect best strategy (recommended)
            results = evaluator.evaluate_cohort()

            # Force in-memory with parallel execution
            results = evaluator.evaluate_cohort(max_workers=4, use_sql=False)

            # Force SQL push-down
            results = evaluator.evaluate_cohort(use_sql=True)
        """
        ref_time = reference_time or datetime.now()

        # Determine execution strategy
        should_use_sql = use_sql if use_sql is not None else self._should_use_sql(patient_ids)

        # SQL push-down execution (for large cohorts with OMOP)
        if should_use_sql and self._sql_compiler is not None:
            return self._sql_compiler.execute(ref_time)

        # In-memory execution: Get patient IDs first
        if patient_ids is None:
            population = self.scenario.population
            patient_ids = self.backend.get_patient_ids(
                population_include=population.include if population else None,
                population_exclude=population.exclude if population else None,
            )

        # Serial execution (default for backward compatibility)
        if max_workers is None:
            results = []
            for patient_id in patient_ids:
                result = self.evaluate_patient(patient_id, ref_time)
                results.append(result)
            return results

        # Parallel execution
        # max_workers=0 means auto-detect based on CPU count
        workers = max_workers if max_workers > 0 else None

        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all patient evaluations
            future_to_patient = {
                executor.submit(self.evaluate_patient, patient_id, ref_time): patient_id
                for patient_id in patient_ids
            }

            # Collect results as they complete
            for future in as_completed(future_to_patient):
                result = future.result()
                results.append(result)

        # Sort by patient_id to maintain consistent ordering
        results.sort(key=lambda r: str(r.patient_id))

        return results

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
        all_results = self.evaluate_cohort(reference_time)

        triggered = []
        for result in all_results:
            if logic_filter:
                # Check specific logic expressions
                if any(name in result.triggered_logic for name in logic_filter):
                    triggered.append(result)
            elif result.is_triggered:
                triggered.append(result)

        return triggered


# =============================================================================
# SQL Compiler for Large Cohort Optimization
# =============================================================================


class SQLCompiler:
    """
    Compiles PSDL scenarios to SQL for database-side execution.

    This is an internal optimization used by PSDLEvaluator when:
    - Backend is OMOP (SQL database)
    - No explicit patient_ids provided (evaluating entire cohort)
    - Cohort size exceeds threshold

    The SQL compiler translates PSDL temporal operators to SQL window functions,
    allowing the database to compute trends for millions of patients efficiently.

    Supported operators:
    - last: Most recent value via ROW_NUMBER() window function
    - first: Earliest value in window via ROW_NUMBER()
    - delta: Difference between latest and earliest values in window
    - slope: Linear regression slope via REGR_SLOPE() (PostgreSQL)
    - sma: Simple moving average via AVG()
    - min/max: MIN()/MAX() over window
    - count: COUNT(*) over window

    Not yet supported (fall back to in-memory):
    - ema: Exponential weighted average (requires recursive computation)
    """

    # Operator mappings to SQL
    OPERATOR_SQL = {
        "last": "last_value",
        "first": "first_value",
        "delta": "delta",
        "slope": "regr_slope",
        "sma": "avg",
        "min": "min",
        "max": "max",
        "count": "count",
    }

    def __init__(self, scenario: "PSDLScenario", backend: "OMOPBackend"):
        """
        Initialize SQL compiler.

        Args:
            scenario: Parsed PSDL scenario
            backend: OMOP backend with database connection
        """
        self.scenario = scenario
        self.backend = backend

    # Operators that cannot be efficiently compiled to SQL
    # EMA requires recursive computation which is complex and slow in SQL
    UNSUPPORTED_OPERATORS = {"ema"}

    def can_compile(self) -> bool:
        """
        Check if the scenario can be fully compiled to SQL.

        Returns False if any operator requires in-memory computation.

        Currently unsupported:
        - ema: Exponential Moving Average requires recursive computation.
          While technically possible via recursive CTEs, it's complex and
          slow for multi-patient queries. The hybrid approach (SQL for
          supported operators + in-memory fallback) is more practical.

        Returns:
            True if all operators can be compiled to SQL, False otherwise
        """
        for trend in self.scenario.trends.values():
            if trend.operator.lower() in self.UNSUPPORTED_OPERATORS:
                return False

        return True

    def get_unsupported_trends(self) -> dict:
        """
        Get trends that use unsupported operators.

        Returns:
            Dict mapping trend names to their unsupported operators
        """
        unsupported = {}
        for name, trend in self.scenario.trends.items():
            if trend.operator.lower() in self.UNSUPPORTED_OPERATORS:
                unsupported[name] = trend.operator
        return unsupported

    def compile_trend_sql(self, trend_name: str, trend: "TrendExpr") -> str:
        """
        Compile a single trend expression to SQL.

        Args:
            trend_name: Name of the trend
            trend: TrendExpr to compile

        Returns:
            SQL CTE fragment for this trend
        """
        signal = self.scenario.signals.get(trend.signal)
        if not signal:
            raise ValueError(f"Signal '{trend.signal}' not found for trend '{trend_name}'")

        # Get table and column info from backend
        domain = signal.domain.value if signal.domain else "measurement"
        schema = self.backend.config.cdm_schema
        table = f"{schema}.{domain}"
        datetime_col = self.backend._get_datetime_column(domain)
        value_col = self.backend._get_value_column(domain)

        # Get window in seconds
        window_seconds = trend.window.seconds if trend.window else 3600

        # Build the filter condition
        if self.backend.config.use_source_values:
            source_value = self.backend._get_source_value(signal)
            filter_cond = f"{domain}_source_value = '{source_value}'"
        else:
            concept_id = self.backend._get_concept_id(signal)
            filter_cond = f"{domain}_concept_id = {concept_id}"

        # Generate SQL based on operator
        operator = trend.operator.lower()

        if operator == "last":
            sql = f"""
    {trend_name}_data AS (
        SELECT person_id,
               {value_col} as value,
               ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} DESC) as rn
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
    ),
    {trend_name} AS (
        SELECT person_id, value as {trend_name}_value
        FROM {trend_name}_data WHERE rn = 1
    )"""

        elif operator == "first":
            sql = f"""
    {trend_name}_data AS (
        SELECT person_id,
               {value_col} as value,
               ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} ASC) as rn
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
    ),
    {trend_name} AS (
        SELECT person_id, value as {trend_name}_value
        FROM {trend_name}_data WHERE rn = 1
    )"""

        elif operator == "delta":
            sql = f"""
    {trend_name}_first AS (
        SELECT person_id, {value_col} as value,
               ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} ASC) as rn
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
    ),
    {trend_name}_last AS (
        SELECT person_id, {value_col} as value,
               ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} DESC) as rn
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
    ),
    {trend_name} AS (
        SELECT l.person_id,
               (l.value - f.value) as {trend_name}_value
        FROM {trend_name}_last l
        JOIN {trend_name}_first f ON l.person_id = f.person_id
        WHERE l.rn = 1 AND f.rn = 1
    )"""

        elif operator in ("sma", "avg"):
            sql = f"""
    {trend_name} AS (
        SELECT person_id,
               AVG({value_col}) as {trend_name}_value
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
        GROUP BY person_id
    )"""

        elif operator in ("min", "min_val"):
            sql = f"""
    {trend_name} AS (
        SELECT person_id,
               MIN({value_col}) as {trend_name}_value
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
        GROUP BY person_id
    )"""

        elif operator in ("max", "max_val"):
            sql = f"""
    {trend_name} AS (
        SELECT person_id,
               MAX({value_col}) as {trend_name}_value
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
        GROUP BY person_id
    )"""

        elif operator == "count":
            sql = f"""
    {trend_name} AS (
        SELECT person_id,
               COUNT(*) as {trend_name}_value
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
        GROUP BY person_id
    )"""

        elif operator == "slope":
            # PostgreSQL regr_slope(Y, X) computes slope of least-squares linear regression
            # Y = value, X = time in seconds from window start
            # Returns slope in units per second
            sql = f"""
    {trend_name} AS (
        SELECT person_id,
               REGR_SLOPE(
                   {value_col},
                   EXTRACT(EPOCH FROM {datetime_col})
               ) as {trend_name}_value
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
        GROUP BY person_id
        HAVING COUNT(*) >= 2
    )"""

        else:
            raise ValueError(f"Unsupported operator for SQL compilation: {operator}")

        return sql

    def compile_full_query(self) -> str:
        """
        Compile the full scenario to a single SQL query.

        Returns:
            Complete SQL query that evaluates all trends and logic
        """
        ctes = []
        trend_names = []

        # Compile each trend
        for trend_name, trend in self.scenario.trends.items():
            cte = self.compile_trend_sql(trend_name, trend)
            ctes.append(cte)
            trend_names.append(trend_name)

        # Build the final SELECT joining all trends
        schema = self.backend.config.cdm_schema

        # Start with person table
        select_cols = ["p.person_id"]
        joins = []

        for trend_name in trend_names:
            select_cols.append(
                f"COALESCE({trend_name}.{trend_name}_value, NULL) as {trend_name}_value"
            )
            joins.append(f"LEFT JOIN {trend_name} ON p.person_id = {trend_name}.person_id")

        # Add trend result columns (threshold comparisons)
        for trend_name, trend in self.scenario.trends.items():
            if trend.comparator and trend.threshold is not None:
                comp = trend.comparator
                thresh = trend.threshold
                select_cols.append(
                    f"CASE WHEN {trend_name}.{trend_name}_value {comp} {thresh} "
                    f"THEN true ELSE false END as {trend_name}_result"
                )
            else:
                select_cols.append(
                    f"CASE WHEN {trend_name}.{trend_name}_value IS NOT NULL "
                    f"THEN true ELSE false END as {trend_name}_result"
                )

        # Build final query
        query = "WITH " + ",\n".join(ctes)
        query += f"\nSELECT {', '.join(select_cols)}"
        query += f"\nFROM {schema}.person p"
        query += "\n" + "\n".join(joins)

        return query

    def execute(self, reference_time: datetime) -> List[EvaluationResult]:
        """
        Execute the compiled SQL query and return results.

        Args:
            reference_time: Point in time for evaluation

        Returns:
            List of EvaluationResults for all patients
        """
        query = self.compile_full_query()

        # Execute query
        from sqlalchemy import text

        engine = self.backend._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text(query), {"reference_time": reference_time})
            rows = result.fetchall()
            columns = result.keys()

        # Convert to EvaluationResults
        results = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            patient_id = row_dict["person_id"]

            # Extract trend values and results
            trend_values = {}
            trend_results = {}
            for trend_name in self.scenario.trends:
                value_key = f"{trend_name}_value"
                result_key = f"{trend_name}_result"
                trend_values[trend_name] = row_dict.get(value_key)
                trend_results[trend_name] = bool(row_dict.get(result_key, False))

            # Evaluate logic expressions (done in Python for flexibility)
            logic_results = {}
            triggered_logic = []

            evaluator = PSDLEvaluator.__new__(PSDLEvaluator)
            evaluator.scenario = self.scenario

            for logic_name, logic in self.scenario.logic.items():
                result = evaluator._evaluate_logic(logic, trend_results, logic_results)
                logic_results[logic_name] = result
                if result:
                    triggered_logic.append(logic_name)

            results.append(
                EvaluationResult(
                    patient_id=patient_id,
                    timestamp=reference_time,
                    triggered_logic=triggered_logic,
                    trend_values=trend_values,
                    trend_results=trend_results,
                    logic_results=logic_results,
                )
            )

        return results
