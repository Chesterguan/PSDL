"""
Independent Mathematical Verification Tests

These tests verify PSDL correctness using MANUALLY CALCULATED expected values.
This eliminates any possibility of circular validation.

Each test case includes:
1. Raw input data
2. Step-by-step manual calculation
3. Expected result (derived by hand, not code)
4. PSDL result for comparison

If PSDL matches manual calculations, the implementation is correct.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from psdl.core import PSDLParser
from psdl.operators import DataPoint, TemporalOperators
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

PSDLEvaluator = SinglePatientEvaluator


class TestManualDeltaVerification:
    """Verify delta operator against manual calculation."""

    def test_delta_simple_rise(self):
        """
        Manual Calculation:
        Data: [1.0, 1.1, 1.2, 1.3, 1.4] at t=[-36h, -24h, -12h, -6h, 0h]
        Window: 48 hours
        All points are within 48h window.

        Delta = last - first = 1.4 - 1.0 = 0.4

        Expected: 0.4
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now - timedelta(hours=12), 1.2),
            DataPoint(now - timedelta(hours=6), 1.3),
            DataPoint(now, 1.4),
        ]

        # Manual calculation
        EXPECTED_DELTA = 1.4 - 1.0  # = 0.4

        # PSDL calculation
        window_48h = 48 * 60 * 60  # 48 hours in seconds
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Manual Delta Verification ===")
        print(f"Input: {[dp.value for dp in data]}")
        print(f"Manual calculation: 1.4 - 1.0 = {EXPECTED_DELTA}")
        print(f"PSDL result: {psdl_delta}")

        assert (
            abs(psdl_delta - EXPECTED_DELTA) < 0.001
        ), f"PSDL delta {psdl_delta} != manual {EXPECTED_DELTA}"

    def test_delta_with_partial_window(self):
        """
        Manual Calculation:
        Data: [1.0, 1.5, 2.0, 2.5, 3.0] at t=[-72h, -60h, -36h, -12h, 0h]
        Window: 48 hours
        Points within 48h: [2.0, 2.5, 3.0] (at -36h, -12h, 0h)

        Delta = last - first_in_window = 3.0 - 2.0 = 1.0

        Expected: 1.0
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=72), 1.0),  # Outside window
            DataPoint(now - timedelta(hours=60), 1.5),  # Outside window
            DataPoint(now - timedelta(hours=36), 2.0),  # Inside window (first)
            DataPoint(now - timedelta(hours=12), 2.5),  # Inside window
            DataPoint(now, 3.0),  # Inside window (last)
        ]

        # Manual calculation
        EXPECTED_DELTA = 3.0 - 2.0  # = 1.0

        # PSDL calculation
        window_48h = 48 * 60 * 60
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Partial Window Delta Verification ===")
        print(f"Full data: {[dp.value for dp in data]}")
        print("Points in 48h window: [2.0, 2.5, 3.0]")
        print(f"Manual calculation: 3.0 - 2.0 = {EXPECTED_DELTA}")
        print(f"PSDL result: {psdl_delta}")

        assert abs(psdl_delta - EXPECTED_DELTA) < 0.001

    def test_delta_stable_patient(self):
        """
        Manual Calculation:
        Data: [1.0, 1.02, 0.98, 1.01, 1.0] at regular intervals
        Window: 48 hours

        Delta = 1.0 - 1.0 = 0.0

        Expected: 0.0 (stable, no AKI trigger)
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.02),
            DataPoint(now - timedelta(hours=12), 0.98),
            DataPoint(now - timedelta(hours=6), 1.01),
            DataPoint(now, 1.0),
        ]

        EXPECTED_DELTA = 1.0 - 1.0  # = 0.0

        window_48h = 48 * 60 * 60
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Stable Patient Delta Verification ===")
        print(f"Input: {[dp.value for dp in data]}")
        print(f"Manual calculation: 1.0 - 1.0 = {EXPECTED_DELTA}")
        print(f"PSDL result: {psdl_delta}")

        assert abs(psdl_delta - EXPECTED_DELTA) < 0.001


class TestManualSlopeVerification:
    """Verify slope operator against manual linear regression."""

    def test_slope_linear_increase(self):
        """
        Manual Linear Regression Calculation:
        Data points: (0h, 1.0), (12h, 2.0), (24h, 3.0)
        Time in seconds: x = [0, 43200, 86400]
        Values: y = [1.0, 2.0, 3.0]

        n = 3
        sum_x = 0 + 43200 + 86400 = 129600
        sum_y = 1.0 + 2.0 + 3.0 = 6.0
        sum_xy = 0*1.0 + 43200*2.0 + 86400*3.0 = 0 + 86400 + 259200 = 345600
        sum_x2 = 0 + 43200^2 + 86400^2 = 0 + 1866240000 + 7464960000 = 9331200000

        slope = (n*sum_xy - sum_x*sum_y) / (n*sum_x2 - sum_x^2)
        slope = (3*345600 - 129600*6.0) / (3*9331200000 - 129600^2)
        slope = (1036800 - 777600) / (27993600000 - 16796160000)
        slope = 259200 / 11197440000
        slope = 0.00002314815 per second
        slope = 0.0833 per hour (approximately)

        Expected: ~2.3e-5 per second (or 0.0833 per hour)
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=24), 1.0),
            DataPoint(now - timedelta(hours=12), 2.0),
            DataPoint(now, 3.0),
        ]

        # Manual calculation (value per second)
        # Perfect linear: goes from 1.0 to 3.0 over 24 hours
        # Rate = 2.0 / (24 * 3600) = 2.0 / 86400 ≈ 2.315e-5 per second
        EXPECTED_SLOPE = 2.0 / (24 * 3600)

        window_24h = 24 * 60 * 60
        psdl_slope = TemporalOperators.slope(data, window_24h, now)

        print("\n=== Manual Slope Verification ===")
        print(f"Input: {[(dp.timestamp, dp.value) for dp in data]}")
        print(f"Expected slope: {EXPECTED_SLOPE:.10f} per second")
        print(f"Expected slope: {EXPECTED_SLOPE * 3600:.6f} per hour")
        print(f"PSDL slope: {psdl_slope:.10f} per second")
        print(f"PSDL slope: {psdl_slope * 3600:.6f} per hour")

        # Allow 1% tolerance for floating point
        assert abs(psdl_slope - EXPECTED_SLOPE) / EXPECTED_SLOPE < 0.01


class TestManualAKITriggerVerification:
    """Verify complete AKI scenario against manual logic."""

    @pytest.fixture
    def aki_scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def test_aki_stage1_manual_verification(self, aki_scenario):
        """
        Manual AKI Stage 1 Verification:

        Input: Creatinine = [1.0, 1.1, 1.2, 1.3, 1.4] over 36 hours
        Delta = 1.4 - 1.0 = 0.4 mg/dL

        KDIGO Stage 1 Criteria: delta >= 0.3 mg/dL in 48h
        0.4 >= 0.3 → TRUE

        Expected: aki_stage1 TRIGGERED
        """
        now = datetime.now()
        patient_id = "manual_test_1"

        cr_data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now - timedelta(hours=12), 1.2),
            DataPoint(now - timedelta(hours=6), 1.3),
            DataPoint(now, 1.4),
        ]

        # Manual calculation
        delta = 1.4 - 1.0  # = 0.4
        EXPECTED_TRIGGER = delta >= 0.3  # = True

        # PSDL evaluation
        backend = InMemoryBackend()
        backend.add_data(patient_id, "Cr", cr_data)
        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Manual AKI Stage 1 Verification ===")
        print(f"Creatinine values: {[dp.value for dp in cr_data]}")
        print(f"Manual delta: {delta}")
        print("KDIGO Stage 1 threshold: >= 0.3")
        print(f"Manual trigger decision: {delta} >= 0.3 = {EXPECTED_TRIGGER}")
        print(f"PSDL triggered: {result.is_triggered}")
        print(f"PSDL triggered logic: {result.triggered_logic}")

        assert result.is_triggered == EXPECTED_TRIGGER
        assert "aki_stage1" in result.triggered_logic

    def test_no_aki_manual_verification(self, aki_scenario):
        """
        Manual No-AKI Verification:

        Input: Creatinine = [1.0, 1.05, 0.98, 1.02, 1.0] (stable)
        Delta = 1.0 - 1.0 = 0.0 mg/dL

        KDIGO Stage 1 Criteria: delta >= 0.3 mg/dL in 48h
        0.0 >= 0.3 → FALSE

        Expected: NOT TRIGGERED
        """
        now = datetime.now()
        patient_id = "manual_test_stable"

        cr_data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.05),
            DataPoint(now - timedelta(hours=12), 0.98),
            DataPoint(now - timedelta(hours=6), 1.02),
            DataPoint(now, 1.0),
        ]

        # Manual calculation
        delta = 1.0 - 1.0  # = 0.0
        EXPECTED_TRIGGER = delta >= 0.3  # = False

        # PSDL evaluation
        backend = InMemoryBackend()
        backend.add_data(patient_id, "Cr", cr_data)
        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Manual No-AKI Verification ===")
        print(f"Creatinine values: {[dp.value for dp in cr_data]}")
        print(f"Manual delta: {delta}")
        print("KDIGO Stage 1 threshold: >= 0.3")
        print(f"Manual trigger decision: {delta} >= 0.3 = {EXPECTED_TRIGGER}")
        print(f"PSDL triggered: {result.is_triggered}")

        assert result.is_triggered == EXPECTED_TRIGGER

    def test_aki_stage3_manual_verification(self, aki_scenario):
        """
        Manual AKI Stage 3 Verification:

        Input: Creatinine = [1.0, 2.0, 3.0, 4.0, 4.5] over 40 hours
        Latest value = 4.5 mg/dL

        KDIGO Stage 3 Criteria: Cr >= 4.0 mg/dL
        4.5 >= 4.0 → TRUE

        Expected: aki_stage3 TRIGGERED
        """
        now = datetime.now()
        patient_id = "manual_test_stage3"

        cr_data = [
            DataPoint(now - timedelta(hours=40), 1.0),
            DataPoint(now - timedelta(hours=30), 2.0),
            DataPoint(now - timedelta(hours=20), 3.0),
            DataPoint(now - timedelta(hours=10), 4.0),
            DataPoint(now, 4.5),
        ]

        # Manual calculation
        latest_cr = 4.5
        EXPECTED_TRIGGER = latest_cr >= 4.0  # = True

        # PSDL evaluation
        backend = InMemoryBackend()
        backend.add_data(patient_id, "Cr", cr_data)
        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Manual AKI Stage 3 Verification ===")
        print(f"Creatinine values: {[dp.value for dp in cr_data]}")
        print(f"Latest creatinine: {latest_cr}")
        print("KDIGO Stage 3 threshold: >= 4.0 mg/dL")
        print(f"Manual trigger decision: {latest_cr} >= 4.0 = {EXPECTED_TRIGGER}")
        print(f"PSDL triggered: {result.is_triggered}")
        print(f"PSDL triggered logic: {result.triggered_logic}")

        assert result.is_triggered == EXPECTED_TRIGGER
        assert "aki_stage3" in result.triggered_logic


class TestEdgeCasesManualVerification:
    """Verify edge cases with manual calculations."""

    def test_exactly_at_threshold(self):
        """
        Edge Case: Delta exactly at threshold

        Input: Creatinine = [1.0, 1.1, 1.2, 1.3] → Delta = 0.3 EXACTLY
        KDIGO: delta >= 0.3 → Should trigger (>= is inclusive)

        Expected: TRIGGERED
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now - timedelta(hours=12), 1.2),
            DataPoint(now, 1.3),  # Delta = 1.3 - 1.0 = 0.3 exactly
        ]

        EXPECTED_DELTA = 0.3
        # Expected: should trigger since 0.3 >= 0.3

        window_48h = 48 * 60 * 60
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Threshold Edge Case ===")
        print(f"Manual delta: 1.3 - 1.0 = {EXPECTED_DELTA}")
        print(f"PSDL delta: {psdl_delta}")
        print(f"Threshold test: {psdl_delta} >= 0.3 = {psdl_delta >= 0.3}")

        assert abs(psdl_delta - EXPECTED_DELTA) < 0.001
        assert psdl_delta >= 0.3  # Should trigger

    def test_just_below_threshold(self):
        """
        Edge Case: Delta just below threshold

        Input: Creatinine = [1.0, 1.1, 1.15, 1.29] → Delta = 0.29
        KDIGO: delta >= 0.3 → Should NOT trigger

        Expected: NOT TRIGGERED
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now - timedelta(hours=12), 1.15),
            DataPoint(now, 1.29),  # Delta = 1.29 - 1.0 = 0.29
        ]

        EXPECTED_DELTA = 0.29
        # Expected: should NOT trigger since 0.29 < 0.3

        window_48h = 48 * 60 * 60
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Below Threshold Edge Case ===")
        print(f"Manual delta: 1.29 - 1.0 = {EXPECTED_DELTA}")
        print(f"PSDL delta: {psdl_delta}")
        print(f"Threshold test: {psdl_delta} >= 0.3 = {psdl_delta >= 0.3}")

        assert abs(psdl_delta - EXPECTED_DELTA) < 0.001
        assert not (psdl_delta >= 0.3)  # Should NOT trigger

    def test_negative_delta(self):
        """
        Edge Case: Falling creatinine (recovery)

        Input: Creatinine = [2.0, 1.8, 1.5, 1.2, 1.0] → Delta = -1.0
        This represents recovery, not AKI

        Expected: Delta = -1.0, NOT TRIGGERED for AKI
        """
        now = datetime.now()
        data = [
            DataPoint(now - timedelta(hours=36), 2.0),
            DataPoint(now - timedelta(hours=24), 1.8),
            DataPoint(now - timedelta(hours=12), 1.5),
            DataPoint(now - timedelta(hours=6), 1.2),
            DataPoint(now, 1.0),
        ]

        EXPECTED_DELTA = 1.0 - 2.0  # = -1.0

        window_48h = 48 * 60 * 60
        psdl_delta = TemporalOperators.delta(data, window_48h, now)

        print("\n=== Negative Delta (Recovery) ===")
        print(f"Manual delta: 1.0 - 2.0 = {EXPECTED_DELTA}")
        print(f"PSDL delta: {psdl_delta}")
        print("This is recovery, not AKI")

        assert abs(psdl_delta - EXPECTED_DELTA) < 0.001
        assert psdl_delta < 0  # Negative = falling = recovery


class TestClinicalReferenceCases:
    """
    Test cases based on published clinical literature.
    These verify PSDL against real-world clinical expectations.
    """

    @pytest.fixture
    def aki_scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def test_kdigo_stage1_example(self, aki_scenario):
        """
        KDIGO Guideline Example:
        "An increase in serum creatinine by ≥0.3 mg/dl within 48 hours"

        Patient: Baseline Cr 0.9, increases to 1.3 over 24 hours
        Delta = 1.3 - 0.9 = 0.4 mg/dL
        Result: AKI Stage 1

        Reference: KDIGO Clinical Practice Guideline for AKI, 2012
        """
        now = datetime.now()
        patient_id = "kdigo_example_1"

        # Simulate admission labs followed by rising creatinine
        cr_data = [
            DataPoint(now - timedelta(hours=24), 0.9),  # Admission
            DataPoint(now - timedelta(hours=12), 1.1),  # Rising
            DataPoint(now, 1.3),  # Current
        ]

        backend = InMemoryBackend()
        backend.add_data(patient_id, "Cr", cr_data)
        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== KDIGO Stage 1 Clinical Example ===")
        print("Baseline Cr: 0.9 mg/dL")
        print("Current Cr: 1.3 mg/dL")
        print("Delta: 0.4 mg/dL (>= 0.3 threshold)")
        print("Expected: AKI Stage 1")
        print(f"PSDL result: {'Stage 1' if 'aki_stage1' in result.triggered_logic else 'No AKI'}")

        assert result.is_triggered
        assert "aki_stage1" in result.triggered_logic

    def test_contrast_induced_aki(self, aki_scenario):
        """
        Clinical Scenario: Contrast-Induced AKI
        Post-cardiac catheterization, Cr rises from 1.0 to 1.5 mg/dL
        over 48 hours (delta = 0.5 mg/dL)

        Expected: AKI Stage 1
        """
        now = datetime.now()
        patient_id = "contrast_aki"

        # Pre-cath baseline, then post-cath rise
        cr_data = [
            DataPoint(now - timedelta(hours=48), 1.0),  # Pre-cath
            DataPoint(now - timedelta(hours=24), 1.2),  # 24h post
            DataPoint(now, 1.5),  # 48h post
        ]

        backend = InMemoryBackend()
        backend.add_data(patient_id, "Cr", cr_data)
        evaluator = PSDLEvaluator(aki_scenario, backend)
        result = evaluator.evaluate_patient(patient_id, now)

        print("\n=== Contrast-Induced AKI Example ===")
        print("Pre-procedure Cr: 1.0 mg/dL")
        print("48h post-procedure Cr: 1.5 mg/dL")
        print("Delta: 0.5 mg/dL")
        print(f"PSDL result: {result.triggered_logic}")

        assert result.is_triggered
        assert "aki_stage1" in result.triggered_logic
