"""
Tests for PSDL Evaluator

Run with: pytest tests/test_evaluator.py -v
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

# Add runtime to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from psdl.core import PSDLParser  # noqa: E402
from psdl.operators import DataPoint, TemporalOperators  # noqa: E402
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator  # noqa: E402

PSDLEvaluator = SinglePatientEvaluator


class TestTemporalOperators:
    """Tests for temporal operators."""

    @pytest.fixture
    def sample_data(self):
        """Sample time-series data for testing."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        return [
            DataPoint(base_time - timedelta(hours=6), 1.0),
            DataPoint(base_time - timedelta(hours=5), 1.1),
            DataPoint(base_time - timedelta(hours=4), 1.2),
            DataPoint(base_time - timedelta(hours=3), 1.3),
            DataPoint(base_time - timedelta(hours=2), 1.4),
            DataPoint(base_time - timedelta(hours=1), 1.5),
            DataPoint(base_time, 1.6),
        ]

    @pytest.fixture
    def reference_time(self):
        return datetime(2024, 1, 1, 12, 0, 0)

    def test_last(self, sample_data):
        result = TemporalOperators.last(sample_data)
        assert result == 1.6

    def test_last_empty(self):
        result = TemporalOperators.last([])
        assert result is None

    def test_first(self, sample_data, reference_time):
        # First value in 3-hour window
        result = TemporalOperators.first(sample_data, 3 * 3600, reference_time)
        assert result == 1.3

    def test_delta(self, sample_data, reference_time):
        # Change over 6 hours
        result = TemporalOperators.delta(sample_data, 6 * 3600, reference_time)
        assert abs(result - 0.6) < 0.01  # 1.6 - 1.0

    def test_delta_short_window(self, sample_data, reference_time):
        # Change over 2 hours
        result = TemporalOperators.delta(sample_data, 2 * 3600, reference_time)
        assert abs(result - 0.2) < 0.01  # 1.6 - 1.4

    def test_sma(self, sample_data, reference_time):
        # Simple moving average over 3 hours
        result = TemporalOperators.sma(sample_data, 3 * 3600, reference_time)
        expected = (1.3 + 1.4 + 1.5 + 1.6) / 4
        assert abs(result - expected) < 0.01

    def test_min_val(self, sample_data, reference_time):
        result = TemporalOperators.min_val(sample_data, 6 * 3600, reference_time)
        assert result == 1.0

    def test_max_val(self, sample_data, reference_time):
        result = TemporalOperators.max_val(sample_data, 6 * 3600, reference_time)
        assert result == 1.6

    def test_count(self, sample_data, reference_time):
        result = TemporalOperators.count(sample_data, 3 * 3600, reference_time)
        assert result == 4

    def test_slope_positive(self, sample_data, reference_time):
        # Data is steadily increasing, slope should be positive
        result = TemporalOperators.slope(sample_data, 6 * 3600, reference_time)
        assert result > 0

    def test_slope_flat(self, reference_time):
        # Flat data
        flat_data = [DataPoint(reference_time - timedelta(hours=i), 1.0) for i in range(6, 0, -1)]
        result = TemporalOperators.slope(flat_data, 6 * 3600, reference_time)
        assert abs(result) < 0.01


class TestInMemoryBackend:
    """Tests for the in-memory data backend."""

    def test_add_and_fetch_data(self):
        backend = InMemoryBackend()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        data = [
            DataPoint(base_time - timedelta(hours=2), 1.0),
            DataPoint(base_time - timedelta(hours=1), 1.5),
            DataPoint(base_time, 2.0),
        ]

        from psdl.core.ir import Signal

        signal = Signal(name="Cr", ref="creatinine")

        backend.add_data(patient_id=1, signal_name="Cr", data=data)

        # Fetch with 3-hour window
        result = backend.fetch_signal_data(
            patient_id=1,
            signal=signal,
            window_seconds=3 * 3600,
            reference_time=base_time,
        )

        assert len(result) == 3
        assert result[-1].value == 2.0

    def test_get_patient_ids(self):
        backend = InMemoryBackend()
        backend.add_patient(1)
        backend.add_patient(2)
        backend.add_patient(3)

        ids = backend.get_patient_ids()
        assert set(ids) == {1, 2, 3}


class TestPSDLEvaluator:
    """Tests for the PSDL evaluator (v0.3 syntax)."""

    @pytest.fixture
    def simple_scenario_yaml(self):
        """v0.3: trends produce numeric, logic handles comparisons."""
        return """
scenario: Test_Evaluator
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
    unit: mg/dL
trends:
  cr_high:
    expr: last(Cr)
  cr_rising:
    expr: delta(Cr, 6h)
logic:
  renal_concern:
    when: cr_high > 1.5 AND cr_rising > 0.3
    severity: high
  any_issue:
    when: cr_high > 1.5 OR cr_rising > 0.3
"""

    @pytest.fixture
    def backend_with_data(self):
        backend = InMemoryBackend()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Patient 1: High and rising creatinine (should trigger)
        backend.add_data(
            patient_id=1,
            signal_name="Cr",
            data=[
                DataPoint(base_time - timedelta(hours=6), 1.0),
                DataPoint(base_time - timedelta(hours=3), 1.3),
                DataPoint(base_time, 1.8),  # High (>1.5) and delta=0.8 (>0.3)
            ],
        )

        # Patient 2: Normal creatinine (should not trigger)
        backend.add_data(
            patient_id=2,
            signal_name="Cr",
            data=[
                DataPoint(base_time - timedelta(hours=6), 0.9),
                DataPoint(base_time - timedelta(hours=3), 0.95),
                DataPoint(base_time, 1.0),  # Normal
            ],
        )

        # Patient 3: High but stable creatinine
        backend.add_data(
            patient_id=3,
            signal_name="Cr",
            data=[
                DataPoint(base_time - timedelta(hours=6), 1.6),
                DataPoint(base_time - timedelta(hours=3), 1.6),
                DataPoint(base_time, 1.6),  # High but stable (delta=0)
            ],
        )

        return backend, base_time

    def test_evaluate_single_patient_triggered(self, simple_scenario_yaml, backend_with_data):
        """v0.3: Test patient that triggers both conditions."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(patient_id=1, reference_time=base_time)

        assert result.is_triggered
        assert "renal_concern" in result.triggered_logic
        # v0.3: trends produce numeric values, check trend values
        assert result.trend_values["cr_high"] == 1.8  # last value > 1.5
        assert result.trend_values["cr_rising"] > 0.3  # delta > 0.3

    def test_evaluate_single_patient_not_triggered(self, simple_scenario_yaml, backend_with_data):
        """v0.3: Test patient with normal values."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(patient_id=2, reference_time=base_time)

        assert not result.is_triggered
        # v0.3: trends produce numeric values, logic does comparison
        assert result.trend_values["cr_high"] == 1.0  # last value <= 1.5
        assert result.trend_values["cr_rising"] <= 0.3  # delta <= 0.3

    def test_evaluate_partial_match(self, simple_scenario_yaml, backend_with_data):
        """v0.3: Test patient that only triggers one condition."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        # Patient 3 is high but not rising
        result = evaluator.evaluate_patient(patient_id=3, reference_time=base_time)

        assert result.is_triggered  # any_issue should trigger (cr_high > 1.5)
        assert "any_issue" in result.triggered_logic
        assert "renal_concern" not in result.triggered_logic
        # v0.3: check numeric trend values
        assert result.trend_values["cr_high"] == 1.6  # > 1.5
        assert result.trend_values["cr_rising"] == 0.0  # delta = 0, not > 0.3

    def test_evaluate_cohort(self, simple_scenario_yaml, backend_with_data):
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        results = evaluator.evaluate_cohort(reference_time=base_time, patient_ids=[1, 2, 3])

        assert len(results) == 3

        # Check each patient
        results_by_id = {r.patient_id: r for r in results}

        assert results_by_id[1].is_triggered
        assert not results_by_id[2].is_triggered
        assert results_by_id[3].is_triggered

    def test_evaluate_cohort_parallel(self, simple_scenario_yaml, backend_with_data):
        """Test parallel execution produces same results as serial."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        # Serial execution
        serial_results = evaluator.evaluate_cohort(reference_time=base_time, patient_ids=[1, 2, 3])

        # Parallel execution with explicit workers
        parallel_results = evaluator.evaluate_cohort(
            reference_time=base_time, patient_ids=[1, 2, 3], max_workers=2
        )

        assert len(parallel_results) == len(serial_results)

        # Compare results (parallel results are sorted by patient_id)
        serial_by_id = {r.patient_id: r for r in serial_results}
        parallel_by_id = {r.patient_id: r for r in parallel_results}

        for patient_id in [1, 2, 3]:
            serial = serial_by_id[patient_id]
            parallel = parallel_by_id[patient_id]
            assert serial.is_triggered == parallel.is_triggered
            assert serial.triggered_logic == parallel.triggered_logic
            assert serial.trend_results == parallel.trend_results

    def test_evaluate_cohort_parallel_auto_workers(self, simple_scenario_yaml, backend_with_data):
        """Test parallel execution with auto-detected worker count."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        # max_workers=0 means auto-detect
        results = evaluator.evaluate_cohort(
            reference_time=base_time, patient_ids=[1, 2, 3], max_workers=0
        )

        assert len(results) == 3

        # Verify results are correct
        results_by_id = {r.patient_id: r for r in results}
        assert results_by_id[1].is_triggered
        assert not results_by_id[2].is_triggered
        assert results_by_id[3].is_triggered

    def test_get_triggered_patients(self, simple_scenario_yaml, backend_with_data):
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        # Add patients to backend
        backend.add_patient(1)
        backend.add_patient(2)
        backend.add_patient(3)

        triggered = evaluator.get_triggered_patients(reference_time=base_time)

        triggered_ids = [r.patient_id for r in triggered]
        assert 1 in triggered_ids
        assert 2 not in triggered_ids
        assert 3 in triggered_ids

    def test_trend_values_computed(self, simple_scenario_yaml, backend_with_data):
        """v0.3: Verify numeric trend values are computed correctly."""
        parser = PSDLParser()
        scenario = parser.parse_string(simple_scenario_yaml)

        backend, base_time = backend_with_data
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(patient_id=1, reference_time=base_time)

        # v0.3: trends produce numeric values
        assert result.trend_values["cr_high"] == 1.8  # last value
        assert abs(result.trend_values["cr_rising"] - 0.8) < 0.01  # delta


class TestComplexLogic:
    """Tests for complex logic expressions (v0.3 syntax)."""

    @pytest.fixture
    def complex_scenario_yaml(self):
        """v0.3: trends produce numeric, comparisons in logic."""
        return """
scenario: Complex_Logic_Test
version: "0.3.0"
signals:
  A:
    ref: signal_a
  B:
    ref: signal_b
  C:
    ref: signal_c
trends:
  a_value:
    expr: last(A)
  b_value:
    expr: last(B)
  c_value:
    expr: last(C)
logic:
  a_high:
    when: a_value > 5
  b_high:
    when: b_value > 5
  c_high:
    when: c_value > 5
  stage1:
    when: a_high
  stage2:
    when: stage1 AND b_high
  stage3:
    when: stage2 OR c_high
"""

    def test_cascading_logic(self, complex_scenario_yaml):
        """v0.3: Test cascading logic rules with numeric trends."""
        parser = PSDLParser()
        scenario = parser.parse_string(complex_scenario_yaml)

        backend = InMemoryBackend()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # A=10 (high), B=10 (high), C=1 (low)
        backend.add_data(1, "A", [DataPoint(base_time, 10)])
        backend.add_data(1, "B", [DataPoint(base_time, 10)])
        backend.add_data(1, "C", [DataPoint(base_time, 1)])
        backend.add_patient(1)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(1, base_time)

        # v0.3: a_high, b_high, c_high are now logic rules, not trends
        assert result.logic_results["a_high"] is True  # a_value > 5
        assert result.logic_results["b_high"] is True  # b_value > 5
        assert result.logic_results["c_high"] is False  # c_value <= 5
        assert result.logic_results["stage1"] is True  # a_high
        assert result.logic_results["stage2"] is True  # stage1 AND b_high
        assert result.logic_results["stage3"] is True  # stage2 OR c_high

    def test_or_logic_short_circuit(self, complex_scenario_yaml):
        """v0.3: Test OR logic with cascading rules."""
        parser = PSDLParser()
        scenario = parser.parse_string(complex_scenario_yaml)

        backend = InMemoryBackend()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # A=1 (low), B=1 (low), C=10 (high)
        # stage1 = False, stage2 = False, but stage3 should be True via c_high
        backend.add_data(1, "A", [DataPoint(base_time, 1)])
        backend.add_data(1, "B", [DataPoint(base_time, 1)])
        backend.add_data(1, "C", [DataPoint(base_time, 10)])
        backend.add_patient(1)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(1, base_time)

        # v0.3: check logic rules
        assert result.logic_results["a_high"] is False  # a_value <= 5
        assert result.logic_results["c_high"] is True  # c_value > 5
        assert result.logic_results["stage1"] is False
        assert result.logic_results["stage2"] is False
        assert result.logic_results["stage3"] is True  # c_high is True


class TestMissingData:
    """Tests for handling missing data (v0.3 syntax)."""

    @pytest.fixture
    def scenario_yaml(self):
        """v0.3: trends produce numeric, logic handles comparisons."""
        return """
scenario: Missing_Data_Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  cr_high:
    when: cr_value > 1.5
  concern:
    when: cr_high
"""

    def test_no_data_for_signal(self, scenario_yaml):
        """v0.3: Test handling when no data exists for a signal."""
        parser = PSDLParser()
        scenario = parser.parse_string(scenario_yaml)

        backend = InMemoryBackend()
        backend.add_patient(1)
        # No creatinine data added

        evaluator = PSDLEvaluator(scenario, backend)
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        result = evaluator.evaluate_patient(1, base_time)

        # v0.3: cr_value is a trend, cr_high is a logic rule
        assert result.trend_values["cr_value"] is None
        assert result.logic_results["cr_high"] is False
        assert result.logic_results["concern"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
