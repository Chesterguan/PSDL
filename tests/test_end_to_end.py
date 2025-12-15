"""
End-to-End Tests

Complete workflow tests from scenario parsing through evaluation and result handling.
Tests the full PSDL pipeline as it would be used in production.
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


class TestFullWorkflow:
    """Test complete PSDL workflow from YAML to evaluation results."""

    def test_complete_aki_workflow(self):
        """End-to-end test of AKI detection workflow."""
        # Step 1: Parse scenario from file
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")

        assert scenario.name == "AKI_KDIGO_Detection"
        assert "Cr" in scenario.signals

        # Step 2: Set up data backend with simulated EHR data
        backend = InMemoryBackend()
        now = datetime.now()

        # Simulate a patient developing AKI
        # Baseline creatinine: 1.0 mg/dL
        # Rising to 1.6 mg/dL over 48 hours
        creatinine_data = [
            DataPoint(now - timedelta(hours=48), 1.0),
            DataPoint(now - timedelta(hours=42), 1.05),
            DataPoint(now - timedelta(hours=36), 1.1),
            DataPoint(now - timedelta(hours=30), 1.15),
            DataPoint(now - timedelta(hours=24), 1.2),
            DataPoint(now - timedelta(hours=18), 1.3),
            DataPoint(now - timedelta(hours=12), 1.4),
            DataPoint(now - timedelta(hours=6), 1.5),
            DataPoint(now, 1.6),
        ]

        backend.add_data(patient_id="patient-001", signal_name="Cr", data=creatinine_data)

        # Step 3: Create evaluator and evaluate
        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id="patient-001", reference_time=now)

        # Step 4: Verify results
        assert result.is_triggered, "AKI should be detected"
        assert "aki_stage1" in result.triggered_logic

        # Step 5: Generate alert (simulated)
        if result.is_triggered:
            alert = self._generate_alert(scenario, result, "patient-001")
            assert "AKI" in alert
            assert "patient-001" in alert
            print(f"\nGenerated alert:\n{alert}")

    def _generate_alert(self, scenario, result, patient_id):
        """Simulate alert generation from evaluation result."""
        triggered_rules = result.triggered_logic
        severities = []

        for rule_name in triggered_rules:
            if rule_name in scenario.logic:
                rule = scenario.logic[rule_name]
                severity = rule.severity.value if rule.severity else "info"
                severities.append((rule_name, severity, rule.description))

        max_severity = max((s[1] for s in severities), default="unknown")

        alert = f"""
=== PSDL CLINICAL ALERT ===
Patient: {patient_id}
Scenario: {scenario.name}
Severity: {max_severity}
Time: {datetime.now().isoformat()}

Triggered Rules:
"""
        for name, severity, desc in severities:
            alert += f"  - [{severity}] {name}: {desc}\n"

        alert += f"\nTrend Values: {result.trend_values}\n"
        return alert

    def test_complete_sepsis_workflow(self):
        """End-to-end test of sepsis screening workflow."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/sepsis_screening.yaml")

        backend = InMemoryBackend()
        now = datetime.now()

        # Patient presenting with sepsis signs
        # Tachypnea, hypotension, fever, elevated lactate
        backend.add_data(
            "sepsis-patient",
            "RR",
            [
                DataPoint(now - timedelta(hours=4), 18),
                DataPoint(now - timedelta(hours=2), 22),
                DataPoint(now, 26),
            ],
        )
        backend.add_data(
            "sepsis-patient",
            "SBP",
            [
                DataPoint(now - timedelta(hours=4), 115),
                DataPoint(now - timedelta(hours=2), 100),
                DataPoint(now, 92),
            ],
        )
        backend.add_data(
            "sepsis-patient",
            "Temp",
            [
                DataPoint(now - timedelta(hours=4), 37.2),
                DataPoint(now - timedelta(hours=2), 38.0),
                DataPoint(now, 38.8),
            ],
        )
        backend.add_data(
            "sepsis-patient",
            "HR",
            [
                DataPoint(now - timedelta(hours=4), 85),
                DataPoint(now - timedelta(hours=2), 100),
                DataPoint(now, 115),
            ],
        )
        backend.add_data(
            "sepsis-patient",
            "Lactate",
            [
                DataPoint(now - timedelta(hours=4), 1.2),
                DataPoint(now - timedelta(hours=2), 2.0),
                DataPoint(now, 3.2),
            ],
        )
        backend.add_data(
            "sepsis-patient",
            "WBC",
            [
                DataPoint(now, 16.5),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id="sepsis-patient", reference_time=now)

        print("\nSepsis workflow result:")
        print(f"  Triggered: {result.is_triggered}")
        print(f"  Rules: {result.triggered_logic}")
        print(f"  Trend values: {result.trend_values}")


class TestDynamicScenarioCreation:
    """Test creating and evaluating scenarios dynamically."""

    def test_scenario_from_string(self):
        """Test parsing scenario from YAML string (v0.3 syntax)."""
        yaml_content = """
scenario: Dynamic_Test
version: "0.3.0"
description: "Dynamically created scenario"

signals:
  TestSignal:
    ref: test_source
    unit: units

trends:
  signal_value:
    expr: last(TestSignal)
    description: "Current signal value"

logic:
  high_value:
    when: signal_value > 100
    description: "Value is high"
  alert_high:
    when: high_value
    severity: medium
    description: "High value detected"
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert scenario.name == "Dynamic_Test"
        assert "TestSignal" in scenario.signals

        # Evaluate
        backend = InMemoryBackend()
        now = datetime.now()
        backend.add_data(1, "TestSignal", [DataPoint(now, 150)])

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id=1, reference_time=now)

        assert result.is_triggered
        assert "alert_high" in result.triggered_logic

    def test_multiple_scenarios_same_backend(self):
        """Test running multiple scenarios against the same patient data."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Add comprehensive patient data
        backend.add_data(
            1,
            "Cr",
            [
                DataPoint(now - timedelta(hours=24), 1.0),
                DataPoint(now, 1.5),
            ],
        )
        backend.add_data(1, "MAP", [DataPoint(now, 68)])
        backend.add_data(1, "Lactate", [DataPoint(now, 2.5)])
        backend.add_data(1, "RR", [DataPoint(now, 24)])
        backend.add_data(1, "SBP", [DataPoint(now, 95)])
        backend.add_data(1, "Temp", [DataPoint(now, 38.5)])
        backend.add_data(1, "HR", [DataPoint(now, 110)])
        backend.add_data(1, "WBC", [DataPoint(now, 15)])

        parser = PSDLParser()

        # Load and evaluate multiple scenarios
        scenarios = [
            "examples/aki_detection.yaml",
            "examples/icu_deterioration.yaml",
            "examples/sepsis_screening.yaml",
        ]

        results = {}
        for scenario_file in scenarios:
            scenario = parser.parse_file(scenario_file)
            evaluator = PSDLEvaluator(scenario, backend)
            result = evaluator.evaluate_patient(patient_id=1, reference_time=now)
            results[scenario.name] = {
                "triggered": result.is_triggered,
                "rules": result.triggered_logic,
            }

        print("\nMulti-scenario evaluation results:")
        for name, res in results.items():
            print(f"  {name}: triggered={res['triggered']}, rules={res['rules']}")


class TestCohortEvaluation:
    """Test evaluating scenarios across patient cohorts."""

    def test_cohort_screening(self):
        """Evaluate a scenario across a cohort and identify at-risk patients."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()
        now = datetime.now()

        # Create a cohort of 20 patients with varying creatinine patterns
        cohort = []
        for i in range(20):
            patient_id = f"patient-{i:03d}"
            cohort.append(patient_id)

            # Vary the creatinine pattern
            if i < 5:
                # Normal stable
                cr_values = [0.9, 0.85, 0.92, 0.88, 0.9]
            elif i < 10:
                # Slightly elevated but stable
                cr_values = [1.2, 1.18, 1.22, 1.2, 1.21]
            elif i < 15:
                # Mild rise (might trigger)
                cr_values = [1.0, 1.1, 1.2, 1.3, 1.4]
            else:
                # Significant rise (should trigger)
                cr_values = [1.0, 1.2, 1.4, 1.6, 1.8]

            data = []
            for j, val in enumerate(cr_values):
                t = now - timedelta(hours=(len(cr_values) - j - 1) * 12)
                data.append(DataPoint(t, val))

            backend.add_data(patient_id, "Cr", data)

        # Evaluate all patients
        evaluator = PSDLEvaluator(scenario, backend)

        at_risk = []
        not_triggered = []

        for patient_id in cohort:
            result = evaluator.evaluate_patient(patient_id=patient_id, reference_time=now)
            if result.is_triggered:
                at_risk.append(
                    {
                        "patient_id": patient_id,
                        "rules": result.triggered_logic,
                        "values": result.trend_values,
                    }
                )
            else:
                not_triggered.append(patient_id)

        print("\nCohort screening results:")
        print(f"  Total patients: {len(cohort)}")
        print(f"  At-risk patients: {len(at_risk)}")
        print(f"  Not triggered: {len(not_triggered)}")

        for patient in at_risk:
            print(f"  - {patient['patient_id']}: {patient['rules']}")

    def test_cohort_with_severity_stratification(self):
        """Stratify cohort by alert severity."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/icu_deterioration.yaml")
        backend = InMemoryBackend()
        now = datetime.now()

        # Create patients with varying severity
        patients = {
            "stable-001": {"MAP": 75, "Lactate": 1.0, "Cr": 0.9},
            "mild-001": {"MAP": 68, "Lactate": 1.5, "Cr": 1.2},
            "moderate-001": {"MAP": 62, "Lactate": 2.5, "Cr": 1.5},
            "severe-001": {"MAP": 55, "Lactate": 4.0, "Cr": 2.0},
        }

        for patient_id, values in patients.items():
            for signal, value in values.items():
                backend.add_data(patient_id, signal, [DataPoint(now, value)])

        evaluator = PSDLEvaluator(scenario, backend)

        severity_groups = {
            "low": [],
            "medium": [],
            "high": [],
            "critical": [],
            "none": [],
        }

        for patient_id in patients:
            result = evaluator.evaluate_patient(patient_id=patient_id, reference_time=now)

            if not result.is_triggered:
                severity_groups["none"].append(patient_id)
            else:
                # Find highest severity among triggered rules
                max_severity = "low"
                for rule_name in result.triggered_logic:
                    if rule_name in scenario.logic:
                        rule_severity = scenario.logic[rule_name].severity
                        if self._compare_severity(rule_severity, max_severity) > 0:
                            max_severity = rule_severity
                severity_groups[max_severity].append(patient_id)

        print("\nSeverity stratification:")
        for severity, patients_list in severity_groups.items():
            if patients_list:
                print(f"  {severity}: {patients_list}")

    def _compare_severity(self, sev1, sev2):
        """Compare two severity levels. Returns >0 if sev1 > sev2."""
        order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return order.get(sev1, 0) - order.get(sev2, 0)


class TestTimeSeriesEvaluation:
    """Test evaluation at different points in time."""

    def test_rolling_evaluation(self):
        """Evaluate scenario at multiple time points to track progression."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()

        # Create a patient with progressive AKI over 3 days
        base_time = datetime(2024, 1, 15, 8, 0, 0)

        creatinine_progression = [
            (0, 1.0),  # Day 1 morning
            (8, 1.0),  # Day 1 afternoon
            (24, 1.1),  # Day 2 morning
            (32, 1.2),  # Day 2 afternoon
            (48, 1.4),  # Day 3 morning
            (56, 1.6),  # Day 3 afternoon
            (72, 1.8),  # Day 4 morning
        ]

        data = [DataPoint(base_time + timedelta(hours=h), v) for h, v in creatinine_progression]
        backend.add_data("aki-progression", "Cr", data)

        evaluator = PSDLEvaluator(scenario, backend)

        # Evaluate at each time point
        timeline = []
        for hours, _ in creatinine_progression:
            eval_time = base_time + timedelta(hours=hours)
            result = evaluator.evaluate_patient(
                patient_id="aki-progression", reference_time=eval_time
            )
            timeline.append(
                {
                    "time": eval_time.isoformat(),
                    "hours": hours,
                    "triggered": result.is_triggered,
                    "rules": result.triggered_logic,
                }
            )

        print("\nAKI progression timeline:")
        for point in timeline:
            status = "ALERT" if point["triggered"] else "OK"
            print(f"  Hour {point['hours']:2d}: [{status}] {point['rules']}")


class TestErrorRecovery:
    """Test error handling and recovery in the workflow."""

    def test_missing_signal_data(self):
        """Test handling of missing signal data."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/icu_deterioration.yaml")
        backend = InMemoryBackend()
        now = datetime.now()

        # Only add some signals, not all
        backend.add_data("partial-patient", "MAP", [DataPoint(now, 65)])
        # Missing: Lactate, Cr, UO

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id="partial-patient", reference_time=now)

        # Should not crash, missing data treated as unavailable
        assert hasattr(result, "is_triggered")
        print(f"\nPartial data result: triggered={result.is_triggered}")

    def test_invalid_patient_id(self):
        """Test handling of non-existent patient."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id="non-existent-patient", reference_time=datetime.now()
        )

        # Should return a valid result (not triggered)
        assert not result.is_triggered
        assert len(result.triggered_logic) == 0

    def test_future_reference_time(self):
        """Test evaluation with future reference time."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()
        now = datetime.now()

        backend.add_data("test-patient", "Cr", [DataPoint(now, 1.5)])

        evaluator = PSDLEvaluator(scenario, backend)

        # Evaluate with a future time (data would be "in the past")
        future_time = now + timedelta(days=7)
        result = evaluator.evaluate_patient(patient_id="test-patient", reference_time=future_time)

        # Data is outside the window, so should not trigger
        print(f"\nFuture reference time result: {result.is_triggered}")


class TestResultSerialization:
    """Test serialization of evaluation results."""

    def test_result_to_dict(self):
        """Test converting result to dictionary for JSON serialization."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()
        now = datetime.now()

        backend.add_data(
            "test",
            "Cr",
            [
                DataPoint(now - timedelta(hours=24), 1.0),
                DataPoint(now, 1.5),
            ],
        )

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id="test", reference_time=now)

        # Convert to dict
        result_dict = {
            "patient_id": "test",
            "scenario": scenario.name,
            "scenario_version": scenario.version,
            "evaluation_time": now.isoformat(),
            "is_triggered": result.is_triggered,
            "triggered_logic": list(result.triggered_logic),
            "trend_values": {k: v for k, v in result.trend_values.items()},
        }

        import json

        json_str = json.dumps(result_dict, indent=2)
        print(f"\nResult JSON:\n{json_str}")

        # Verify it can be parsed back
        parsed = json.loads(json_str)
        assert parsed["scenario"] == "AKI_KDIGO_Detection"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
