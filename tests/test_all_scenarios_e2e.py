"""
Comprehensive End-to-End Scenario Tests

This test module validates ALL PSDL example scenarios through complete workflows:
1. Parse YAML scenario definition
2. Load patient data (synthetic or real)
3. Evaluate scenario
4. Validate results
5. Generate alerts/reports

These tests prove that PSDL works as a complete system, not just individual components.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from psdl.core import PSDLParser
from psdl.operators import DataPoint
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

PSDLEvaluator = SinglePatientEvaluator

# ============================================================================
# Test Data Generators
# ============================================================================


class PatientDataGenerator:
    """Generate realistic patient data for testing."""

    @staticmethod
    def create_aki_stage1_patient(patient_id: str, now: datetime) -> Dict[str, List[DataPoint]]:
        """Patient with AKI Stage 1 (Cr rise >= 0.3 mg/dL in 48h)."""
        return {
            "Cr": [
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now - timedelta(hours=36), 1.1),
                DataPoint(now - timedelta(hours=24), 1.2),
                DataPoint(now - timedelta(hours=12), 1.3),
                DataPoint(now, 1.4),  # Delta = 0.4 >= 0.3
            ],
            "BUN": [
                DataPoint(now - timedelta(hours=24), 18),
                DataPoint(now, 25),
            ],
        }

    @staticmethod
    def create_aki_stage3_patient(patient_id: str, now: datetime) -> Dict[str, List[DataPoint]]:
        """Patient with AKI Stage 3 (Cr >= 4.0 mg/dL)."""
        return {
            "Cr": [
                DataPoint(now - timedelta(hours=48), 1.5),
                DataPoint(now - timedelta(hours=36), 2.2),
                DataPoint(now - timedelta(hours=24), 3.0),
                DataPoint(now - timedelta(hours=12), 3.8),
                DataPoint(now, 4.5),  # >= 4.0
            ],
            "BUN": [
                DataPoint(now - timedelta(hours=24), 30),
                DataPoint(now, 55),
            ],
        }

    @staticmethod
    def create_stable_patient(patient_id: str, now: datetime) -> Dict[str, List[DataPoint]]:
        """Stable patient with no clinical triggers."""
        return {
            "Cr": [
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now - timedelta(hours=36), 1.02),
                DataPoint(now - timedelta(hours=24), 0.98),
                DataPoint(now - timedelta(hours=12), 1.01),
                DataPoint(now, 1.0),  # Stable
            ],
            "BUN": [
                DataPoint(now - timedelta(hours=24), 15),
                DataPoint(now, 14),
            ],
            "MAP": [
                DataPoint(now - timedelta(hours=4), 85),
                DataPoint(now - timedelta(hours=2), 82),
                DataPoint(now, 80),  # Normal
            ],
            "HR": [
                DataPoint(now - timedelta(hours=4), 72),
                DataPoint(now - timedelta(hours=2), 75),
                DataPoint(now, 74),  # Normal
            ],
            "Lact": [
                DataPoint(now - timedelta(hours=4), 1.0),
                DataPoint(now - timedelta(hours=2), 1.1),
                DataPoint(now, 1.0),  # Normal
            ],
            "RR": [DataPoint(now, 16)],
            "SBP": [DataPoint(now, 120)],
            "Temp": [DataPoint(now, 37.0)],
            "WBC": [DataPoint(now, 8.0)],
        }

    @staticmethod
    def create_icu_deteriorating_patient(
        patient_id: str, now: datetime
    ) -> Dict[str, List[DataPoint]]:
        """ICU patient showing signs of deterioration."""
        return {
            "MAP": [
                DataPoint(now - timedelta(hours=4), 75),
                DataPoint(now - timedelta(hours=2), 68),
                DataPoint(now, 58),  # Hypotensive < 65
            ],
            "HR": [
                DataPoint(now - timedelta(hours=4), 90),
                DataPoint(now - timedelta(hours=2), 110),
                DataPoint(now, 130),  # Tachycardic > 120
            ],
            "Lact": [
                DataPoint(now - timedelta(hours=4), 1.5),
                DataPoint(now - timedelta(hours=2), 2.5),
                DataPoint(now, 4.0),  # Rising lactate
            ],
            "Cr": [
                DataPoint(now - timedelta(hours=24), 1.2),
                DataPoint(now, 1.8),
            ],
            "RR": [DataPoint(now, 28)],
            "SBP": [DataPoint(now, 85)],
            "Temp": [DataPoint(now, 38.5)],
        }

    @staticmethod
    def create_sepsis_patient(patient_id: str, now: datetime) -> Dict[str, List[DataPoint]]:
        """Patient with sepsis presentation."""
        return {
            "RR": [
                DataPoint(now - timedelta(hours=4), 18),
                DataPoint(now - timedelta(hours=2), 22),
                DataPoint(now, 26),  # Tachypneic >= 22
            ],
            "SBP": [
                DataPoint(now - timedelta(hours=4), 115),
                DataPoint(now - timedelta(hours=2), 100),
                DataPoint(now, 90),  # Hypotensive <= 100
            ],
            "Temp": [
                DataPoint(now - timedelta(hours=4), 37.2),
                DataPoint(now - timedelta(hours=2), 38.0),
                DataPoint(now, 39.2),  # Febrile > 38
            ],
            "HR": [
                DataPoint(now - timedelta(hours=4), 85),
                DataPoint(now - timedelta(hours=2), 105),
                DataPoint(now, 125),  # Tachycardic > 100
            ],
            "Lact": [
                DataPoint(now - timedelta(hours=4), 1.2),
                DataPoint(now - timedelta(hours=2), 2.2),
                DataPoint(now, 3.5),  # Elevated > 2
            ],
            "WBC": [DataPoint(now, 18.0)],  # Leukocytosis > 12
            "MAP": [DataPoint(now, 62)],
            "Cr": [
                DataPoint(now - timedelta(hours=24), 1.0),
                DataPoint(now, 1.3),
            ],
        }


# ============================================================================
# Comprehensive Scenario Tests
# ============================================================================


class TestAKIScenarioComplete:
    """Complete end-to-end tests for AKI detection scenario."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def test_scenario_metadata(self, scenario):
        """Verify scenario is parsed correctly."""
        assert scenario.name == "AKI_KDIGO_Detection"
        assert scenario.version == "1.0.0"
        assert "Cr" in scenario.signals
        assert "aki_stage1" in scenario.logic
        assert "aki_stage3" in scenario.logic

        print("\n=== AKI Scenario Metadata ===")
        print(f"Name: {scenario.name}")
        print(f"Version: {scenario.version}")
        print(f"Signals: {list(scenario.signals.keys())}")
        print(f"Trends: {list(scenario.trends.keys())}")
        print(f"Logic rules: {list(scenario.logic.keys())}")

    def test_stage1_detection(self, scenario):
        """Verify AKI Stage 1 is correctly detected."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "aki_stage1_patient"

        data = PatientDataGenerator.create_aki_stage1_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== AKI Stage 1 Detection ===")
        print(f"Patient: {patient_id}")
        print(f"Triggered: {result.is_triggered}")
        print(f"Rules: {result.triggered_logic}")
        print(f"Trend values: {result.trend_values}")

        assert result.is_triggered
        assert "aki_stage1" in result.triggered_logic
        assert "aki_present" in result.triggered_logic

    def test_stage3_detection(self, scenario):
        """Verify AKI Stage 3 is correctly detected."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "aki_stage3_patient"

        data = PatientDataGenerator.create_aki_stage3_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== AKI Stage 3 Detection ===")
        print(f"Patient: {patient_id}")
        print(f"Triggered: {result.is_triggered}")
        print(f"Rules: {result.triggered_logic}")

        assert result.is_triggered
        assert "aki_stage3" in result.triggered_logic

    def test_stable_patient_no_aki(self, scenario):
        """Verify stable patients do NOT trigger AKI."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "stable_patient"

        data = PatientDataGenerator.create_stable_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Stable Patient (No AKI) ===")
        print(f"Patient: {patient_id}")
        print(f"Triggered: {result.is_triggered}")

        assert not result.is_triggered


class TestICUScenarioComplete:
    """Complete end-to-end tests for ICU deterioration scenario."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/icu_deterioration.yaml")

    def test_scenario_metadata(self, scenario):
        """Verify scenario is parsed correctly."""
        assert scenario.name == "ICU_Deterioration_v1"
        assert "MAP" in scenario.signals
        assert "Lact" in scenario.signals
        assert "HR" in scenario.signals

        print("\n=== ICU Scenario Metadata ===")
        print(f"Name: {scenario.name}")
        print(f"Signals: {list(scenario.signals.keys())}")
        print(f"Logic rules: {list(scenario.logic.keys())}")

    def test_deterioration_detection(self, scenario):
        """Verify ICU deterioration is correctly detected."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "icu_deteriorating"

        data = PatientDataGenerator.create_icu_deteriorating_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== ICU Deterioration Detection ===")
        print(f"Patient: {patient_id}")
        print(f"Triggered: {result.is_triggered}")
        print(f"Rules: {result.triggered_logic}")
        print(f"Trend values: {result.trend_values}")

        assert result.is_triggered
        # Should detect hypotension, rising lactate, and/or tachycardia
        assert len(result.triggered_logic) > 0

    def test_stable_patient_no_deterioration(self, scenario):
        """Verify stable patients do NOT trigger deterioration."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "stable_icu"

        data = PatientDataGenerator.create_stable_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Stable ICU Patient ===")
        print(f"Triggered: {result.is_triggered}")

        assert not result.is_triggered


class TestSepsisScenarioComplete:
    """Complete end-to-end tests for sepsis screening scenario."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/sepsis_screening.yaml")

    def test_scenario_metadata(self, scenario):
        """Verify scenario is parsed correctly."""
        assert scenario.name == "Sepsis_Screening_v1"
        assert "RR" in scenario.signals
        assert "SBP" in scenario.signals
        assert "Temp" in scenario.signals

        print("\n=== Sepsis Scenario Metadata ===")
        print(f"Name: {scenario.name}")
        print(f"Signals: {list(scenario.signals.keys())}")
        print(f"Logic rules: {list(scenario.logic.keys())}")

    def test_sepsis_detection(self, scenario):
        """Verify sepsis is correctly detected."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "sepsis_patient"

        data = PatientDataGenerator.create_sepsis_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Sepsis Detection ===")
        print(f"Patient: {patient_id}")
        print(f"Triggered: {result.is_triggered}")
        print(f"Rules: {result.triggered_logic}")
        print(f"Trend values: {result.trend_values}")

        assert result.is_triggered

    def test_stable_patient_no_sepsis(self, scenario):
        """Verify stable patients do NOT trigger sepsis."""
        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "stable_patient"

        data = PatientDataGenerator.create_stable_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Stable Patient (No Sepsis) ===")
        print(f"Triggered: {result.is_triggered}")

        assert not result.is_triggered


class TestAllScenariosIntegration:
    """Integration tests running all scenarios together."""

    @pytest.fixture
    def all_scenarios(self):
        """Load all example scenarios."""
        parser = PSDLParser()
        return {
            "AKI": parser.parse_file("examples/aki_detection.yaml"),
            "ICU": parser.parse_file("examples/icu_deterioration.yaml"),
            "Sepsis": parser.parse_file("examples/sepsis_screening.yaml"),
        }

    def test_multi_scenario_cohort(self, all_scenarios):
        """Run all scenarios against a patient cohort."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Create diverse patient cohort
        patients = {
            "stable_001": PatientDataGenerator.create_stable_patient("stable_001", now),
            "stable_002": PatientDataGenerator.create_stable_patient("stable_002", now),
            "aki_stage1": PatientDataGenerator.create_aki_stage1_patient("aki_stage1", now),
            "aki_stage3": PatientDataGenerator.create_aki_stage3_patient("aki_stage3", now),
            "icu_sick": PatientDataGenerator.create_icu_deteriorating_patient("icu_sick", now),
            "sepsis": PatientDataGenerator.create_sepsis_patient("sepsis", now),
        }

        # Load all patient data
        for patient_id, data in patients.items():
            for signal_name, datapoints in data.items():
                backend.add_data(patient_id, signal_name, datapoints)

        # Run all scenarios against all patients
        results = {}
        for scenario_name, scenario in all_scenarios.items():
            evaluator = PSDLEvaluator(scenario, backend)
            scenario_results = {}

            for patient_id in patients.keys():
                result = evaluator.evaluate_patient(patient_id, now)
                scenario_results[patient_id] = {
                    "triggered": result.is_triggered,
                    "rules": result.triggered_logic,
                }

            results[scenario_name] = scenario_results

        # Print comprehensive report
        print(f"\n{'='*60}")
        print("MULTI-SCENARIO COHORT EVALUATION REPORT")
        print(f"{'='*60}")
        print(f"Patients: {len(patients)}")
        print(f"Scenarios: {list(all_scenarios.keys())}")
        print(f"{'='*60}")

        for scenario_name, scenario_results in results.items():
            triggered = sum(1 for r in scenario_results.values() if r["triggered"])
            print(f"\n{scenario_name}:")
            print(f"  Triggered: {triggered}/{len(patients)}")
            for patient_id, r in scenario_results.items():
                status = "ALERT" if r["triggered"] else "OK"
                rules = ", ".join(r["rules"]) if r["rules"] else "-"
                print(f"    {patient_id}: [{status}] {rules}")

        # Verify expected outcomes
        # AKI scenario
        assert results["AKI"]["aki_stage1"]["triggered"]
        assert results["AKI"]["aki_stage3"]["triggered"]
        assert not results["AKI"]["stable_001"]["triggered"]

        # ICU scenario
        assert results["ICU"]["icu_sick"]["triggered"]
        assert not results["ICU"]["stable_001"]["triggered"]

        # Sepsis scenario
        assert results["Sepsis"]["sepsis"]["triggered"]
        assert not results["Sepsis"]["stable_001"]["triggered"]

    def test_scenario_independence(self, all_scenarios):
        """Verify scenarios evaluate independently."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Patient with AKI but no sepsis or ICU deterioration
        patient_id = "aki_only"
        data = PatientDataGenerator.create_aki_stage1_patient(patient_id, now)
        # Add normal vitals
        data["MAP"] = [DataPoint(now, 80)]
        data["HR"] = [DataPoint(now, 75)]
        data["Lact"] = [DataPoint(now, 1.0)]
        data["RR"] = [DataPoint(now, 16)]
        data["SBP"] = [DataPoint(now, 120)]
        data["Temp"] = [DataPoint(now, 37.0)]
        data["WBC"] = [DataPoint(now, 8.0)]

        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        # Evaluate all scenarios
        results = {}
        for name, scenario in all_scenarios.items():
            evaluator = PSDLEvaluator(scenario, backend)
            result = evaluator.evaluate_patient(patient_id, now)
            results[name] = result.is_triggered

        print("\n=== Scenario Independence Test ===")
        print("Patient has AKI but normal vitals")
        for name, triggered in results.items():
            print(f"  {name}: {'TRIGGERED' if triggered else 'NOT TRIGGERED'}")

        # AKI should trigger, others should not
        assert results["AKI"] is True
        assert results["ICU"] is False
        assert results["Sepsis"] is False


class TestAlertGeneration:
    """Test complete alert generation workflow."""

    def test_generate_clinical_alert(self):
        """Generate a complete clinical alert from evaluation."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")

        backend = InMemoryBackend()
        now = datetime.now()
        patient_id = "alert_test_patient"

        data = PatientDataGenerator.create_aki_stage3_patient(patient_id, now)
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        # Generate structured alert
        alert = {
            "type": "CLINICAL_ALERT",
            "timestamp": now.isoformat(),
            "patient_id": patient_id,
            "scenario": {
                "name": scenario.name,
                "version": scenario.version,
            },
            "evaluation": {
                "triggered": result.is_triggered,
                "rules": result.triggered_logic,
                "trend_values": {k: v for k, v in result.trend_values.items() if v is not None},
            },
            "severity": "critical" if "aki_stage3" in result.triggered_logic else "medium",
            "recommended_actions": [
                "Notify nephrologist",
                "Check urine output",
                "Review medications for nephrotoxins",
                "Consider fluid challenge",
            ],
        }

        print(f"\n{'='*60}")
        print("GENERATED CLINICAL ALERT")
        print(f"{'='*60}")
        import json

        print(json.dumps(alert, indent=2, default=str))
        print(f"{'='*60}")

        assert alert["evaluation"]["triggered"]
        assert alert["severity"] == "critical"
        assert len(alert["evaluation"]["rules"]) > 0
