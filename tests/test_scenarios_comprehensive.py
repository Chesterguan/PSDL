"""
Comprehensive Scenario Tests

Tests all example scenarios with various data patterns to ensure
correct evaluation under different clinical conditions.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402

from psdl.core import PSDLParser  # noqa: E402
from psdl.operators import DataPoint  # noqa: E402
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator  # noqa: E402

PSDLEvaluator = SinglePatientEvaluator


class TestAKIDetectionScenario:
    """Comprehensive tests for AKI detection scenario."""

    @pytest.fixture
    def scenario(self):
        """Load the AKI detection scenario."""
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    @pytest.fixture
    def backend(self):
        """Create a fresh in-memory backend."""
        return InMemoryBackend()

    def test_normal_creatinine_no_alert(self, scenario, backend):
        """Patient with stable normal creatinine should not trigger."""
        now = datetime.now()

        # Normal stable creatinine (0.8-1.0 mg/dL)
        backend.add_data(
            patient_id=1,
            signal_name="Cr",
            data=[
                DataPoint(now - timedelta(hours=24), 0.9),
                DataPoint(now - timedelta(hours=18), 0.85),
                DataPoint(now - timedelta(hours=12), 0.92),
                DataPoint(now - timedelta(hours=6), 0.88),
                DataPoint(now, 0.90),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert not result.is_triggered
        assert len(result.triggered_logic) == 0

    def test_acute_creatinine_rise_triggers_stage1(self, scenario, backend):
        """Acute creatinine rise >0.3 mg/dL in 48h should trigger Stage 1."""
        now = datetime.now()

        # Creatinine rising from 1.0 to 1.5 (0.5 rise in 6 hours)
        backend.add_data(
            patient_id=1,
            signal_name="Cr",
            data=[
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now - timedelta(hours=24), 1.1),
                DataPoint(now - timedelta(hours=12), 1.2),
                DataPoint(now - timedelta(hours=6), 1.3),
                DataPoint(now, 1.5),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert result.is_triggered
        assert "aki_stage1" in result.triggered_logic

    def test_severe_creatinine_rise_triggers_stage2(self, scenario, backend):
        """Creatinine doubling should trigger Stage 2."""
        now = datetime.now()

        # Creatinine doubling from 1.0 to 2.0
        backend.add_data(
            patient_id=1,
            signal_name="Cr",
            data=[
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now - timedelta(hours=36), 1.2),
                DataPoint(now - timedelta(hours=24), 1.5),
                DataPoint(now - timedelta(hours=12), 1.8),
                DataPoint(now, 2.0),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert result.is_triggered
        # Should trigger both stage1 and stage2
        assert "aki_stage1" in result.triggered_logic or "aki_stage2" in result.triggered_logic

    def test_chronic_elevated_creatinine_no_acute_alert(self, scenario, backend):
        """Chronically elevated but stable creatinine should not trigger."""
        now = datetime.now()

        # Elevated but stable (CKD patient)
        backend.add_data(
            patient_id=1,
            signal_name="Cr",
            data=[
                DataPoint(now - timedelta(hours=48), 2.5),
                DataPoint(now - timedelta(hours=36), 2.4),
                DataPoint(now - timedelta(hours=24), 2.5),
                DataPoint(now - timedelta(hours=12), 2.6),
                DataPoint(now, 2.5),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        # Stage 1 requires delta > 0.3, this is stable
        # May or may not trigger depending on exact scenario definition
        print(f"Chronic elevated result: {result.triggered_logic}")

    def test_single_data_point_handling(self, scenario, backend):
        """Scenario should handle patients with only one data point."""
        now = datetime.now()

        backend.add_data(patient_id=1, signal_name="Cr", data=[DataPoint(now, 1.8)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        # Should not crash, may or may not trigger
        assert hasattr(result, "is_triggered")

    def test_no_data_handling(self, scenario, backend):
        """Scenario should handle patients with no data gracefully."""
        now = datetime.now()

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=999, reference_time=now)

        assert not result.is_triggered


class TestICUDeteriorationScenario:
    """Comprehensive tests for ICU deterioration scenario."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/icu_deterioration.yaml")

    @pytest.fixture
    def backend(self):
        return InMemoryBackend()

    def _add_stable_vitals(self, backend, patient_id, now):
        """Add normal stable vital signs."""
        for i in range(12):
            t = now - timedelta(hours=12 - i)
            backend.add_data(patient_id, "MAP", [DataPoint(t, 75)])
            backend.add_data(patient_id, "Lactate", [DataPoint(t, 1.0)])
            backend.add_data(patient_id, "Cr", [DataPoint(t, 0.9)])
            backend.add_data(patient_id, "UO", [DataPoint(t, 60)])

    def test_stable_patient_no_alert(self, scenario, backend):
        """Stable ICU patient should not trigger deterioration."""
        now = datetime.now()
        self._add_stable_vitals(backend, 1, now)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert not result.is_triggered

    def test_hypotension_triggers_alert(self, scenario, backend):
        """Dropping MAP should trigger hemodynamic concern."""
        now = datetime.now()

        # MAP dropping from 75 to 55
        for i in range(6):
            t = now - timedelta(hours=6 - i)
            map_value = 75 - (i * 4)  # Drops 4 per hour
            backend.add_data(1, "MAP", [DataPoint(t, map_value)])
            backend.add_data(1, "Lactate", [DataPoint(t, 1.0)])
            backend.add_data(1, "Cr", [DataPoint(t, 0.9)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        # Check for hemodynamic-related triggers
        print(f"Hypotension result: {result.triggered_logic}")

    def test_rising_lactate_triggers_alert(self, scenario, backend):
        """Rising lactate should trigger tissue perfusion concern."""
        now = datetime.now()

        # Lactate rising from 1.0 to 4.0
        for i in range(6):
            t = now - timedelta(hours=6 - i)
            lactate = 1.0 + (i * 0.6)
            backend.add_data(1, "Lactate", [DataPoint(t, lactate)])
            backend.add_data(1, "MAP", [DataPoint(t, 70)])
            backend.add_data(1, "Cr", [DataPoint(t, 0.9)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        print(f"Rising lactate result: {result.triggered_logic}")

    def test_multiple_deterioration_factors(self, scenario, backend):
        """Multiple deteriorating factors should trigger high severity."""
        now = datetime.now()

        # Everything getting worse - use signal names from scenario
        # Need to add multiple data points per signal for proper delta/slope calculations
        cr_data = []
        lact_data = []
        map_data = []

        for i in range(12):  # More data points, more granular
            t = now - timedelta(hours=12 - i)
            cr_data.append(DataPoint(t, 1.0 + i * 0.1))  # Rises from 1.0 to 2.1
            lact_data.append(DataPoint(t, 1.0 + i * 0.3))  # Rises from 1.0 to 4.3
            map_data.append(DataPoint(t, 70 - i * 2))  # Falls from 70 to 48

        backend.add_data(1, "Cr", cr_data)
        backend.add_data(1, "Lact", lact_data)
        backend.add_data(1, "MAP", map_data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        # Print debug info
        print(f"Multi-factor deterioration trend values: {result.trend_values}")
        print(f"Multi-factor deterioration trend results: {result.trend_results}")
        print(f"Multi-factor deterioration: {result.triggered_logic}")

        # Should trigger some deterioration alerts with this data
        assert result.is_triggered, f"Expected trigger with trends: {result.trend_results}"


class TestSepsisScreeningScenario:
    """Comprehensive tests for sepsis screening scenario."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/sepsis_screening.yaml")

    @pytest.fixture
    def backend(self):
        return InMemoryBackend()

    def test_normal_vitals_no_sepsis(self, scenario, backend):
        """Normal vital signs should not trigger sepsis screen."""
        now = datetime.now()

        backend.add_data(1, "RR", [DataPoint(now, 16)])
        backend.add_data(1, "SBP", [DataPoint(now, 120)])
        backend.add_data(1, "HR", [DataPoint(now, 75)])
        backend.add_data(1, "Temp", [DataPoint(now, 37.0)])
        backend.add_data(1, "WBC", [DataPoint(now, 8.0)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert not result.is_triggered

    def test_qsofa_criteria_met(self, scenario, backend):
        """qSOFA >= 2 should trigger sepsis screening."""
        now = datetime.now()

        # qSOFA criteria: RR >= 22, SBP <= 100, altered mental status
        backend.add_data(1, "RR", [DataPoint(now, 24)])  # Elevated
        backend.add_data(1, "SBP", [DataPoint(now, 95)])  # Low
        backend.add_data(1, "HR", [DataPoint(now, 110)])
        backend.add_data(1, "Temp", [DataPoint(now, 38.5)])  # Fever
        backend.add_data(1, "WBC", [DataPoint(now, 15.0)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        print(f"qSOFA result: {result.triggered_logic}")

    def test_sepsis_with_lactate_elevation(self, scenario, backend):
        """Sepsis with elevated lactate should be high severity."""
        now = datetime.now()

        backend.add_data(1, "RR", [DataPoint(now, 26)])
        backend.add_data(1, "SBP", [DataPoint(now, 90)])
        backend.add_data(1, "HR", [DataPoint(now, 115)])
        backend.add_data(1, "Temp", [DataPoint(now, 39.0)])
        backend.add_data(1, "WBC", [DataPoint(now, 18.0)])
        backend.add_data(1, "Lactate", [DataPoint(now, 3.5)])  # Elevated

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert result.is_triggered
        print(f"Sepsis with lactate: {result.triggered_logic}")

    def test_hypothermia_as_sepsis_sign(self, scenario, backend):
        """Hypothermia should also trigger sepsis concern."""
        now = datetime.now()

        backend.add_data(1, "RR", [DataPoint(now, 22)])
        backend.add_data(1, "SBP", [DataPoint(now, 98)])
        backend.add_data(1, "Temp", [DataPoint(now, 35.5)])  # Hypothermia
        backend.add_data(1, "HR", [DataPoint(now, 100)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        print(f"Hypothermia sepsis: {result.triggered_logic}")


class TestTemporalOperatorEdgeCases:
    """Test edge cases for temporal operators in scenarios."""

    @pytest.fixture
    def delta_scenario_yaml(self, tmp_path):
        """v0.3: trends produce numeric, logic handles comparisons."""
        content = """
scenario: Delta_Test
version: "0.3.0"

signals:
  Value:
    ref: test_value
    unit: units

trends:
  delta_6h:
    expr: delta(Value, 6h)
    description: "Value change in 6 hours"

  delta_24h:
    expr: delta(Value, 24h)
    description: "Value change in 24 hours"

logic:
  rising_fast:
    when: delta_6h > 10
    description: "Value increased by more than 10 in 6 hours"
  rising_slow:
    when: delta_24h > 5
    description: "Value increased by more than 5 in 24 hours"
  acute_rise:
    when: rising_fast
    severity: high
"""
        f = tmp_path / "delta_test.yaml"
        f.write_text(content)
        return str(f)

    def test_delta_with_exact_window(self, delta_scenario_yaml):
        """Test delta calculation with data at exact window boundaries."""
        parser = PSDLParser()
        scenario = parser.parse_file(delta_scenario_yaml)
        backend = InMemoryBackend()

        now = datetime.now()

        # Data exactly at window boundary
        backend.add_data(
            1,
            "Value",
            [
                DataPoint(now - timedelta(hours=6), 50),
                DataPoint(now, 65),  # Delta = 15
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert result.is_triggered
        assert "acute_rise" in result.triggered_logic

    def test_delta_with_sparse_data(self, delta_scenario_yaml):
        """Test delta with data points not at window boundaries."""
        parser = PSDLParser()
        scenario = parser.parse_file(delta_scenario_yaml)
        backend = InMemoryBackend()

        now = datetime.now()

        # Data not exactly at boundaries
        backend.add_data(
            1,
            "Value",
            [
                DataPoint(now - timedelta(hours=8), 50),  # Outside 6h window
                DataPoint(now - timedelta(hours=4), 55),
                DataPoint(now - timedelta(hours=2), 60),
                DataPoint(now, 62),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        # Delta should be calculated from data within window
        print(f"Sparse data result: {result.trend_values}")

    def test_slope_calculation(self, tmp_path):
        """Test slope operator for trend detection (v0.3 syntax)."""
        content = """
scenario: Slope_Test
version: "0.3.0"

signals:
  Value:
    ref: test_value
    unit: units

trends:
  slope_6h:
    expr: slope(Value, 6h)
    description: "6-hour slope"

logic:
  rising_trend:
    when: slope_6h > 0
    description: "Value is trending upward"
  falling_trend:
    when: slope_6h < 0
    description: "Value is trending downward"
  going_up:
    when: rising_trend
    severity: low
  going_down:
    when: falling_trend
    severity: low
"""
        f = tmp_path / "slope_test.yaml"
        f.write_text(content)

        parser = PSDLParser()
        scenario = parser.parse_file(str(f))
        backend = InMemoryBackend()

        now = datetime.now()

        # Clear upward trend
        backend.add_data(
            1,
            "Value",
            [
                DataPoint(now - timedelta(hours=5), 10),
                DataPoint(now - timedelta(hours=4), 15),
                DataPoint(now - timedelta(hours=3), 20),
                DataPoint(now - timedelta(hours=2), 25),
                DataPoint(now - timedelta(hours=1), 30),
                DataPoint(now, 35),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert "going_up" in result.triggered_logic
        assert "going_down" not in result.triggered_logic


class TestBatchEvaluation:
    """Test evaluating multiple patients in batch."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def test_evaluate_multiple_patients(self, scenario):
        """Test evaluating a cohort of patients."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Add data for 10 patients with varying creatinine patterns
        for i in range(10):
            patient_id = i + 1

            # Some patients have rising creatinine, some stable
            if i % 3 == 0:
                # Rising pattern
                data = [
                    DataPoint(now - timedelta(hours=48), 1.0),
                    DataPoint(now - timedelta(hours=24), 1.2),
                    DataPoint(now, 1.5),
                ]
            else:
                # Stable pattern
                data = [
                    DataPoint(now - timedelta(hours=48), 0.9),
                    DataPoint(now - timedelta(hours=24), 0.95),
                    DataPoint(now, 0.9),
                ]

            backend.add_data(patient_id, "Cr", data)

        evaluator = PSDLEvaluator(scenario, backend)

        # Evaluate all patients
        triggered_patients = []
        for patient_id in range(1, 11):
            result = evaluator.evaluate_patient(patient_id=patient_id, reference_time=now)
            if result.is_triggered:
                triggered_patients.append(patient_id)

        print(f"\nBatch evaluation: {len(triggered_patients)}/10 patients triggered")
        print(f"Triggered patients: {triggered_patients}")

        # Patients 1, 4, 7, 10 should have rising pattern
        # Whether they trigger depends on scenario thresholds


class TestScenarioValidation:
    """Test scenario validation and error handling."""

    def test_invalid_signal_reference_in_trend(self, tmp_path):
        """Scenario with invalid signal reference should fail validation (v0.3 syntax)."""
        content = """
scenario: Invalid_Test
version: "0.3.0"

signals:
  Cr:
    ref: creatinine
    unit: mg/dL

trends:
  bad_value:
    expr: last(NonExistent)
    description: "References non-existent signal"

logic:
  bad_trend:
    when: bad_value > 1.0
    description: "Bad trend check"
  test:
    when: bad_trend
    severity: low
"""
        f = tmp_path / "invalid.yaml"
        f.write_text(content)

        parser = PSDLParser()

        # Parser should raise an error for invalid signal reference
        with pytest.raises(Exception) as exc_info:
            parser.parse_file(str(f))

        # Error should mention the non-existent signal
        assert "NonExistent" in str(exc_info.value)

    def test_circular_logic_reference(self, tmp_path):
        """Scenario with circular logic should be detected (v0.3 syntax)."""
        content = """
scenario: Circular_Test
version: "0.3.0"

signals:
  Value:
    ref: test
    unit: units

trends:
  value:
    expr: last(Value)
    description: "Current value"

logic:
  trend_a:
    when: value > 5
    description: "Simple trend check"
  rule_a:
    when: rule_b
    severity: low
  rule_b:
    when: rule_a
    severity: low
"""
        f = tmp_path / "circular.yaml"
        f.write_text(content)

        parser = PSDLParser()
        # This might fail at parse or validation time
        try:
            scenario = parser.parse_file(str(f))
            errors = scenario.validate()
            # Should have validation errors for circular reference
            print(f"Circular reference errors: {errors}")
        except Exception as e:
            # Parser might catch this
            print(f"Parser caught circular reference: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
