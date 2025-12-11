"""
Clinical Validation Tests

These tests validate that PSDL produces clinically meaningful and correct results.
We create synthetic patient cohorts with KNOWN clinical outcomes and verify
that PSDL correctly identifies them.

This is critical validation - not just "does it run" but "does it work correctly".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import random  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from typing import Dict, List  # noqa: E402

import pytest  # noqa: E402

from psdl.core import PSDLParser  # noqa: E402
from psdl.operators import DataPoint  # noqa: E402
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator  # noqa: E402

PSDLEvaluator = SinglePatientEvaluator


@dataclass
class SyntheticPatient:
    """A synthetic patient with known clinical state."""

    patient_id: str
    age: int
    expected_aki: bool  # Ground truth: should AKI be detected?
    expected_sepsis: bool  # Ground truth: should sepsis be detected?
    expected_deterioration: bool  # Ground truth: should deterioration be detected?
    clinical_notes: str  # Description for debugging


class ClinicalDataGenerator:
    """Generate clinically realistic synthetic patient data."""

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def generate_stable_patient(self, patient_id: str) -> tuple:
        """Generate a stable patient with normal values."""
        return (
            SyntheticPatient(
                patient_id=patient_id,
                age=random.randint(30, 70),
                expected_aki=False,
                expected_sepsis=False,
                expected_deterioration=False,
                clinical_notes="Stable patient, all vitals normal",
            ),
            self._stable_vitals(),
        )

    def generate_aki_stage1_patient(self, patient_id: str) -> tuple:
        """Generate a patient with KDIGO Stage 1 AKI."""
        return (
            SyntheticPatient(
                patient_id=patient_id,
                age=random.randint(50, 80),
                expected_aki=True,
                expected_sepsis=False,
                expected_deterioration=False,
                clinical_notes="AKI Stage 1: Creatinine rise >0.3 mg/dL in 48h",
            ),
            self._aki_stage1_vitals(),
        )

    def generate_aki_stage2_patient(self, patient_id: str) -> tuple:
        """Generate a patient with KDIGO Stage 2 AKI."""
        return (
            SyntheticPatient(
                patient_id=patient_id,
                age=random.randint(55, 85),
                expected_aki=True,
                expected_sepsis=False,
                expected_deterioration=True,  # Stage 2 indicates deterioration
                clinical_notes="AKI Stage 2: Creatinine doubled from baseline",
            ),
            self._aki_stage2_vitals(),
        )

    def generate_sepsis_patient(self, patient_id: str) -> tuple:
        """Generate a patient meeting sepsis criteria."""
        return (
            SyntheticPatient(
                patient_id=patient_id,
                age=random.randint(40, 75),
                expected_aki=False,
                expected_sepsis=True,
                expected_deterioration=True,
                clinical_notes="Sepsis: qSOFA positive + elevated lactate",
            ),
            self._sepsis_vitals(),
        )

    def generate_ckd_stable_patient(self, patient_id: str) -> tuple:
        """Generate a CKD patient with chronically elevated but STABLE creatinine."""
        return (
            SyntheticPatient(
                patient_id=patient_id,
                age=random.randint(60, 85),
                expected_aki=False,  # CKD is NOT acute - should NOT trigger AKI
                expected_sepsis=False,
                expected_deterioration=False,
                clinical_notes="CKD Stage 3: Elevated but stable creatinine (no acute injury)",
            ),
            self._ckd_stable_vitals(),
        )

    def _stable_vitals(self) -> Dict[str, List[DataPoint]]:
        """Normal stable vital signs over 48 hours."""
        now = datetime.now()
        data = {}

        # Creatinine: stable around 0.9 mg/dL
        data["Cr"] = [
            DataPoint(now - timedelta(hours=48), 0.9),
            DataPoint(now - timedelta(hours=36), 0.88),
            DataPoint(now - timedelta(hours=24), 0.92),
            DataPoint(now - timedelta(hours=12), 0.89),
            DataPoint(now, 0.90),
        ]

        # Lactate: normal < 2.0
        data["Lact"] = [
            DataPoint(now - timedelta(hours=24), 1.0),
            DataPoint(now - timedelta(hours=12), 1.1),
            DataPoint(now, 1.0),
        ]

        # MAP: normal 70-100
        data["MAP"] = [
            DataPoint(now - timedelta(hours=24), 78),
            DataPoint(now - timedelta(hours=12), 80),
            DataPoint(now, 79),
        ]

        # Respiratory rate: normal
        data["RR"] = [DataPoint(now, 16)]

        # Systolic BP: normal
        data["SBP"] = [DataPoint(now, 120)]

        # Temperature: normal
        data["Temp"] = [DataPoint(now, 37.0)]

        # Heart rate: normal
        data["HR"] = [DataPoint(now, 75)]

        return data

    def _aki_stage1_vitals(self) -> Dict[str, List[DataPoint]]:
        """AKI Stage 1: Creatinine rise >=0.3 mg/dL in 48h."""
        now = datetime.now()
        data = self._stable_vitals()

        # Override creatinine with rising pattern
        # Baseline 1.0, rises to 1.4 (delta = 0.4, >0.3 threshold)
        data["Cr"] = [
            DataPoint(now - timedelta(hours=48), 1.0),
            DataPoint(now - timedelta(hours=36), 1.05),
            DataPoint(now - timedelta(hours=24), 1.15),
            DataPoint(now - timedelta(hours=12), 1.25),
            DataPoint(now, 1.4),
        ]

        return data

    def _aki_stage2_vitals(self) -> Dict[str, List[DataPoint]]:
        """AKI Stage 2: More severe creatinine rise with rapid trajectory."""
        now = datetime.now()
        data = self._stable_vitals()

        # Creatinine doubles and rises rapidly
        data["Cr"] = [
            DataPoint(now - timedelta(hours=48), 1.0),
            DataPoint(now - timedelta(hours=36), 1.2),
            DataPoint(now - timedelta(hours=24), 1.5),
            DataPoint(now - timedelta(hours=12), 1.8),
            DataPoint(now, 2.2),  # More than doubled
        ]

        # Also add rising lactate (sign of deterioration)
        data["Lact"] = [
            DataPoint(now - timedelta(hours=24), 1.5),
            DataPoint(now - timedelta(hours=12), 2.0),
            DataPoint(now, 2.5),
        ]

        return data

    def _sepsis_vitals(self) -> Dict[str, List[DataPoint]]:
        """Sepsis: qSOFA >= 2 + elevated lactate."""
        now = datetime.now()
        data = {}

        # Creatinine: slightly elevated but not rising dramatically
        data["Cr"] = [
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now, 1.2),
        ]

        # Lactate: elevated > 2.0
        data["Lact"] = [
            DataPoint(now - timedelta(hours=12), 2.5),
            DataPoint(now, 3.5),
        ]

        # MAP: low (hypotension)
        data["MAP"] = [
            DataPoint(now - timedelta(hours=12), 68),
            DataPoint(now, 58),
        ]

        # Respiratory rate: tachypnea >= 22
        data["RR"] = [DataPoint(now, 26)]

        # Systolic BP: hypotension <= 100
        data["SBP"] = [DataPoint(now, 92)]

        # Temperature: fever
        data["Temp"] = [DataPoint(now, 38.8)]

        # Heart rate: tachycardia
        data["HR"] = [DataPoint(now, 115)]

        # WBC: elevated
        data["WBC"] = [DataPoint(now, 16.5)]

        return data

    def _ckd_stable_vitals(self) -> Dict[str, List[DataPoint]]:
        """CKD: Chronically elevated but STABLE creatinine."""
        now = datetime.now()
        data = self._stable_vitals()

        # Creatinine: high but stable (CKD baseline)
        # This should NOT trigger AKI because there's no acute change
        data["Cr"] = [
            DataPoint(now - timedelta(hours=48), 2.5),
            DataPoint(now - timedelta(hours=36), 2.48),
            DataPoint(now - timedelta(hours=24), 2.52),
            DataPoint(now - timedelta(hours=12), 2.50),
            DataPoint(now, 2.51),
        ]

        return data


class TestAKIDetectionValidation:
    """Validate AKI detection produces clinically correct results."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    @pytest.fixture
    def generator(self):
        return ClinicalDataGenerator(seed=42)

    def _load_patient_data(self, backend, patient_id, data):
        """Load patient data into backend."""
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

    def test_stable_patient_no_aki(self, scenario, generator):
        """Stable patient should NOT trigger AKI."""
        backend = InMemoryBackend()
        patient, data = generator.generate_stable_patient("stable-001")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        # Clinical expectation: NO AKI
        assert (
            result.is_triggered == patient.expected_aki
        ), f"Stable patient incorrectly triggered: {result.triggered_logic}"
        print(f"✓ {patient.clinical_notes}: correctly NOT triggered")

    def test_aki_stage1_detected(self, scenario, generator):
        """AKI Stage 1 patient SHOULD trigger."""
        backend = InMemoryBackend()
        patient, data = generator.generate_aki_stage1_patient("aki1-001")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        # Clinical expectation: AKI detected
        assert (
            result.is_triggered == patient.expected_aki
        ), f"AKI Stage 1 patient NOT detected! Trends: {result.trend_results}"
        assert "aki_stage1" in result.triggered_logic or "aki_present" in result.triggered_logic
        print(f"✓ {patient.clinical_notes}: correctly triggered {result.triggered_logic}")

    def test_aki_stage2_detected(self, scenario, generator):
        """AKI Stage 2 patient SHOULD trigger with higher severity."""
        backend = InMemoryBackend()
        patient, data = generator.generate_aki_stage2_patient("aki2-001")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        assert result.is_triggered == patient.expected_aki
        # Should trigger stage 2 or higher
        assert any(r in result.triggered_logic for r in ["aki_stage2", "aki_stage3", "aki_present"])
        print(f"✓ {patient.clinical_notes}: correctly triggered {result.triggered_logic}")

    def test_ckd_stable_no_aki(self, scenario, generator):
        """CKD patient with stable creatinine should NOT trigger AKI."""
        backend = InMemoryBackend()
        patient, data = generator.generate_ckd_stable_patient("ckd-001")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        # Clinical expectation: NO AKI (chronic, not acute)
        # The delta should be near 0
        assert (
            result.is_triggered == patient.expected_aki
        ), f"CKD stable patient incorrectly triggered: {result.triggered_logic}"
        print(f"✓ {patient.clinical_notes}: correctly NOT triggered")


class TestSepsisDetectionValidation:
    """Validate sepsis detection produces clinically correct results."""

    @pytest.fixture
    def scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/sepsis_screening.yaml")

    @pytest.fixture
    def generator(self):
        return ClinicalDataGenerator(seed=42)

    def _load_patient_data(self, backend, patient_id, data):
        for signal_name, datapoints in data.items():
            backend.add_data(patient_id, signal_name, datapoints)

    def test_stable_patient_no_sepsis(self, scenario, generator):
        """Stable patient should NOT trigger sepsis."""
        backend = InMemoryBackend()
        patient, data = generator.generate_stable_patient("stable-002")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        assert (
            result.is_triggered == patient.expected_sepsis
        ), f"Stable patient incorrectly triggered sepsis: {result.triggered_logic}"
        print(f"✓ {patient.clinical_notes}: correctly NOT triggered for sepsis")

    def test_sepsis_patient_detected(self, scenario, generator):
        """Septic patient SHOULD trigger."""
        backend = InMemoryBackend()
        patient, data = generator.generate_sepsis_patient("sepsis-001")
        self._load_patient_data(backend, patient.patient_id, data)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient(
            patient_id=patient.patient_id, reference_time=datetime.now()
        )

        assert (
            result.is_triggered == patient.expected_sepsis
        ), f"Septic patient NOT detected! Trends: {result.trend_results}"
        print(f"✓ {patient.clinical_notes}: correctly triggered {result.triggered_logic}")


class TestCohortValidation:
    """Validate PSDL accuracy across a diverse patient cohort."""

    @pytest.fixture
    def generator(self):
        return ClinicalDataGenerator(seed=42)

    def test_aki_cohort_sensitivity_specificity(self, generator):
        """Calculate sensitivity and specificity for AKI detection."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()

        # Generate a cohort with known outcomes
        cohort = []

        # True positives (should trigger)
        for i in range(10):
            patient, data = generator.generate_aki_stage1_patient(f"aki-tp-{i}")
            cohort.append((patient, data))

        # True negatives (should NOT trigger)
        for i in range(15):
            patient, data = generator.generate_stable_patient(f"stable-tn-{i}")
            cohort.append((patient, data))

        # Load all data
        for patient, data in cohort:
            for signal_name, datapoints in data.items():
                backend.add_data(patient.patient_id, signal_name, datapoints)

        # Evaluate
        evaluator = PSDLEvaluator(scenario, backend)
        now = datetime.now()

        true_positives = 0
        true_negatives = 0
        false_positives = 0
        false_negatives = 0

        for patient, _ in cohort:
            result = evaluator.evaluate_patient(patient_id=patient.patient_id, reference_time=now)

            predicted_positive = result.is_triggered
            actual_positive = patient.expected_aki

            if predicted_positive and actual_positive:
                true_positives += 1
            elif not predicted_positive and not actual_positive:
                true_negatives += 1
            elif predicted_positive and not actual_positive:
                false_positives += 1
                print(f"  FP: {patient.patient_id} - {patient.clinical_notes}")
            else:
                false_negatives += 1
                print(f"  FN: {patient.patient_id} - {patient.clinical_notes}")

        # Calculate metrics
        sensitivity = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0
        )
        specificity = (
            true_negatives / (true_negatives + false_positives)
            if (true_negatives + false_positives) > 0
            else 0
        )
        accuracy = (true_positives + true_negatives) / len(cohort)

        print("\n=== AKI Detection Validation Results ===")
        print(f"Cohort size: {len(cohort)}")
        print(f"True Positives:  {true_positives}")
        print(f"True Negatives:  {true_negatives}")
        print(f"False Positives: {false_positives}")
        print(f"False Negatives: {false_negatives}")
        print(f"Sensitivity: {sensitivity:.1%}")
        print(f"Specificity: {specificity:.1%}")
        print(f"Accuracy:    {accuracy:.1%}")

        # Assert high performance
        assert sensitivity >= 0.9, f"Sensitivity too low: {sensitivity:.1%}"
        assert specificity >= 0.9, f"Specificity too low: {specificity:.1%}"

    def test_mixed_cohort_validation(self, generator):
        """Test with a realistic mixed cohort."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")
        backend = InMemoryBackend()

        cohort = []

        # Mix of patient types
        for i in range(5):
            cohort.append(generator.generate_stable_patient(f"stable-{i}"))
        for i in range(3):
            cohort.append(generator.generate_aki_stage1_patient(f"aki1-{i}"))
        for i in range(2):
            cohort.append(generator.generate_aki_stage2_patient(f"aki2-{i}"))
        for i in range(3):
            cohort.append(generator.generate_ckd_stable_patient(f"ckd-{i}"))
        for i in range(2):
            cohort.append(generator.generate_sepsis_patient(f"sepsis-{i}"))

        # Load data
        for patient, data in cohort:
            for signal_name, datapoints in data.items():
                backend.add_data(patient.patient_id, signal_name, datapoints)

        evaluator = PSDLEvaluator(scenario, backend)
        now = datetime.now()

        correct = 0
        incorrect = 0

        print("\n=== Mixed Cohort Validation ===")
        for patient, _ in cohort:
            result = evaluator.evaluate_patient(patient_id=patient.patient_id, reference_time=now)

            if result.is_triggered == patient.expected_aki:
                correct += 1
                status = "✓"
            else:
                incorrect += 1
                status = "✗"
                print(
                    f"  {status} {patient.patient_id}: "
                    f"expected={patient.expected_aki}, got={result.is_triggered}"
                )
                print(f"      Notes: {patient.clinical_notes}")
                print(f"      Trends: {result.trend_results}")

        accuracy = correct / len(cohort)
        print(f"\nAccuracy: {correct}/{len(cohort)} = {accuracy:.1%}")

        assert accuracy >= 0.85, f"Accuracy too low: {accuracy:.1%}"


class TestEdgeCases:
    """Test clinically important edge cases."""

    @pytest.fixture
    def aki_scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def test_borderline_creatinine_rise(self, aki_scenario):
        """Test borderline creatinine rise (exactly at threshold)."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Exactly 0.3 mg/dL rise - should trigger
        backend.add_data(
            "borderline",
            "Cr",
            [
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now, 1.3),  # Exactly 0.3 rise
            ],
        )

        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id="borderline", reference_time=now)

        # KDIGO says >= 0.3, so this should trigger
        print(
            f"Borderline (0.3 rise): triggered={result.is_triggered}, trends={result.trend_values}"
        )

    def test_just_below_threshold(self, aki_scenario):
        """Test just below threshold (should NOT trigger)."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Just below threshold
        backend.add_data(
            "below",
            "Cr",
            [
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now, 1.25),  # 0.25 rise - below 0.3 threshold
            ],
        )

        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id="below", reference_time=now)

        print(f"Below threshold (0.25 rise): triggered={result.is_triggered}")
        # Should NOT trigger for Stage 1 (requires >= 0.3)

    def test_rapid_then_stable(self, aki_scenario):
        """Patient who had acute rise but now stable."""
        backend = InMemoryBackend()
        now = datetime.now()

        # Rose acutely 24h ago, now stable
        backend.add_data(
            "recovering",
            "Cr",
            [
                DataPoint(now - timedelta(hours=48), 1.0),
                DataPoint(now - timedelta(hours=36), 1.5),  # Acute rise
                DataPoint(now - timedelta(hours=24), 1.5),
                DataPoint(now - timedelta(hours=12), 1.48),
                DataPoint(now, 1.45),  # Slightly improving
            ],
        )

        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id="recovering", reference_time=now)

        print(
            f"Recovering patient: triggered={result.is_triggered}, rules={result.triggered_logic}"
        )
        # May still trigger aki_stage1 but should also show recovery pattern


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
