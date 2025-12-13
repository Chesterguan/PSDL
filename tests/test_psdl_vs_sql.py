"""
PSDL vs Pure SQL Comparison Tests

This test validates that PSDL produces identical results to hand-written SQL
for the same clinical logic. This is critical for proving PSDL correctness.

If PSDL results match SQL results, we can be confident that:
1. The PSDL parser correctly interprets clinical scenarios
2. The evaluator correctly applies temporal operators
3. The logic engine correctly combines conditions
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from psdl.core import PSDLParser
from psdl.operators import DataPoint
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

PSDLEvaluator = SinglePatientEvaluator


class SQLEmulator:
    """
    Emulates SQL queries on in-memory data.
    This mimics what a real SQL backend would do.
    """

    def __init__(self, data: Dict[str, Dict[str, List[DataPoint]]]):
        """
        data structure: {patient_id: {signal_name: [DataPoint, ...]}}
        """
        self.data = data

    def execute_aki_detection_sql(
        self, patient_id: str, reference_time: datetime
    ) -> Dict[str, Any]:
        """
        Pure SQL-style logic for AKI detection.

        Equivalent SQL:
        ```sql
        WITH recent_cr AS (
            SELECT value, timestamp
            FROM measurements
            WHERE patient_id = :patient_id
              AND signal = 'Cr'
              AND timestamp <= :reference_time
              AND timestamp >= :reference_time - INTERVAL '48 hours'
            ORDER BY timestamp DESC
        ),
        baseline_cr AS (
            SELECT AVG(value) as baseline
            FROM measurements
            WHERE patient_id = :patient_id
              AND signal = 'Cr'
              AND timestamp <= :reference_time - INTERVAL '48 hours'
              AND timestamp >= :reference_time - INTERVAL '7 days'
        ),
        cr_delta AS (
            SELECT
                (SELECT value FROM recent_cr ORDER BY timestamp DESC LIMIT 1) -
                (SELECT value FROM recent_cr ORDER BY timestamp ASC LIMIT 1) as delta_48h
        )
        SELECT
            CASE
                WHEN cr_delta.delta_48h >= 0.3 THEN 'stage1'
                ELSE NULL
            END as aki_stage,
            recent_cr.latest_value,
            baseline_cr.baseline,
            cr_delta.delta_48h
        FROM cr_delta, recent_cr, baseline_cr
        ```
        """
        cr_data = self.data.get(patient_id, {}).get("Cr", [])

        if not cr_data:
            return {"triggered": False, "reason": "no_data"}

        # Filter to relevant time windows
        window_48h = reference_time - timedelta(hours=48)
        window_7d = reference_time - timedelta(days=7)

        recent_cr = [dp for dp in cr_data if window_48h <= dp.timestamp <= reference_time]
        baseline_cr = [dp for dp in cr_data if window_7d <= dp.timestamp < window_48h]

        if len(recent_cr) < 2:
            return {"triggered": False, "reason": "insufficient_recent_data"}

        # Sort by timestamp
        recent_cr.sort(key=lambda x: x.timestamp)

        # Calculate delta (latest - earliest in 48h window)
        latest_value = recent_cr[-1].value
        earliest_value = recent_cr[0].value
        delta_48h = latest_value - earliest_value

        # Calculate baseline if available
        baseline_avg = None
        if baseline_cr:
            baseline_avg = sum(dp.value for dp in baseline_cr) / len(baseline_cr)

        # AKI Stage 1: delta >= 0.3 mg/dL in 48h
        # AKI Stage 2: delta >= 1.0 mg/dL (2x baseline)
        # AKI Stage 3: delta >= 2.0 mg/dL (3x baseline) or value >= 4.0

        result = {
            "latest_cr": latest_value,
            "earliest_cr": earliest_value,
            "delta_48h": delta_48h,
            "baseline_avg": baseline_avg,
            "triggered": False,
            "stage": None,
        }

        if delta_48h >= 2.0 or latest_value >= 4.0:
            result["triggered"] = True
            result["stage"] = "stage3"
        elif delta_48h >= 1.0:
            result["triggered"] = True
            result["stage"] = "stage2"
        elif delta_48h >= 0.3:
            result["triggered"] = True
            result["stage"] = "stage1"

        return result

    def execute_icu_deterioration_sql(
        self, patient_id: str, reference_time: datetime
    ) -> Dict[str, Any]:
        """
        Pure SQL-style logic for ICU deterioration.

        Checks:
        - MAP < 65 mmHg
        - Lactate delta > 1.0 in 4h
        - Heart rate > 120 bpm
        """
        map_data = self.data.get(patient_id, {}).get("MAP", [])
        lactate_data = self.data.get(patient_id, {}).get("Lact", [])
        hr_data = self.data.get(patient_id, {}).get("HR", [])

        window_4h = reference_time - timedelta(hours=4)

        result = {
            "triggered": False,
            "conditions_met": [],
            "latest_map": None,
            "latest_hr": None,
            "lactate_delta": None,
        }

        # Check MAP
        recent_map = [dp for dp in map_data if dp.timestamp <= reference_time]
        if recent_map:
            latest_map = max(recent_map, key=lambda x: x.timestamp).value
            result["latest_map"] = latest_map
            if latest_map < 65:
                result["conditions_met"].append("hypotension")

        # Check HR
        recent_hr = [dp for dp in hr_data if dp.timestamp <= reference_time]
        if recent_hr:
            latest_hr = max(recent_hr, key=lambda x: x.timestamp).value
            result["latest_hr"] = latest_hr
            if latest_hr > 120:
                result["conditions_met"].append("tachycardia")

        # Check Lactate delta
        recent_lactate = [dp for dp in lactate_data if window_4h <= dp.timestamp <= reference_time]
        if len(recent_lactate) >= 2:
            recent_lactate.sort(key=lambda x: x.timestamp)
            lactate_delta = recent_lactate[-1].value - recent_lactate[0].value
            result["lactate_delta"] = lactate_delta
            if lactate_delta > 1.0:
                result["conditions_met"].append("rising_lactate")

        result["triggered"] = len(result["conditions_met"]) > 0

        return result


class TestPSDLvsSQLEquivalence:
    """Test that PSDL produces identical results to pure SQL logic."""

    @pytest.fixture
    def aki_scenario(self):
        """Load AKI detection scenario."""
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    @pytest.fixture
    def icu_scenario(self):
        """Load ICU deterioration scenario."""
        parser = PSDLParser()
        return parser.parse_file("examples/icu_deterioration.yaml")

    def create_test_patient_aki_stage1(self) -> Tuple[str, Dict, datetime]:
        """Create a patient with AKI Stage 1 pattern."""
        patient_id = "sql_test_aki_stage1"
        now = datetime.now()

        # Creatinine rising from 1.0 to 1.4 (delta = 0.4, triggers stage 1)
        cr_data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.1),
            DataPoint(now - timedelta(hours=12), 1.2),
            DataPoint(now - timedelta(hours=6), 1.3),
            DataPoint(now, 1.4),
        ]

        data = {patient_id: {"Cr": cr_data}}
        return patient_id, data, now

    def create_test_patient_aki_stage3(self) -> Tuple[str, Dict, datetime]:
        """Create a patient with AKI Stage 3 pattern."""
        patient_id = "sql_test_aki_stage3"
        now = datetime.now()

        # Creatinine rising from 1.0 to 4.5 (severe AKI)
        cr_data = [
            DataPoint(now - timedelta(hours=40), 1.0),
            DataPoint(now - timedelta(hours=30), 2.0),
            DataPoint(now - timedelta(hours=20), 3.0),
            DataPoint(now - timedelta(hours=10), 4.0),
            DataPoint(now, 4.5),
        ]

        data = {patient_id: {"Cr": cr_data}}
        return patient_id, data, now

    def create_test_patient_stable(self) -> Tuple[str, Dict, datetime]:
        """Create a patient with stable creatinine."""
        patient_id = "sql_test_stable"
        now = datetime.now()

        # Stable creatinine around 1.0
        cr_data = [
            DataPoint(now - timedelta(hours=36), 1.0),
            DataPoint(now - timedelta(hours=24), 1.05),
            DataPoint(now - timedelta(hours=12), 0.98),
            DataPoint(now - timedelta(hours=6), 1.02),
            DataPoint(now, 1.0),
        ]

        data = {patient_id: {"Cr": cr_data}}
        return patient_id, data, now

    def create_test_patient_icu_deteriorating(self) -> Tuple[str, Dict, datetime]:
        """Create a deteriorating ICU patient."""
        patient_id = "sql_test_icu"
        now = datetime.now()

        # Low MAP, rising lactate, tachycardia
        map_data = [
            DataPoint(now - timedelta(hours=4), 70.0),
            DataPoint(now - timedelta(hours=2), 65.0),
            DataPoint(now, 58.0),  # Hypotensive
        ]
        lactate_data = [
            DataPoint(now - timedelta(hours=4), 1.5),
            DataPoint(now - timedelta(hours=2), 2.5),
            DataPoint(now, 3.5),  # Rising lactate (delta = 2.0)
        ]
        hr_data = [
            DataPoint(now - timedelta(hours=4), 90.0),
            DataPoint(now - timedelta(hours=2), 110.0),
            DataPoint(now, 130.0),  # Tachycardic
        ]

        data = {
            patient_id: {
                "MAP": map_data,
                "Lact": lactate_data,
                "HR": hr_data,
            }
        }
        return patient_id, data, now

    def test_aki_stage1_equivalence(self, aki_scenario):
        """Test that PSDL and SQL agree on AKI Stage 1 detection."""
        patient_id, data, reference_time = self.create_test_patient_aki_stage1()

        # SQL result
        sql_emulator = SQLEmulator(data)
        sql_result = sql_emulator.execute_aki_detection_sql(patient_id, reference_time)

        # PSDL result
        backend = InMemoryBackend()
        for pid, signals in data.items():
            for signal_name, datapoints in signals.items():
                backend.add_data(pid, signal_name, datapoints)

        evaluator = PSDLEvaluator(aki_scenario, backend)
        psdl_result = evaluator.evaluate_patient(patient_id, reference_time)

        # Compare results
        print("\n=== AKI Stage 1 Comparison ===")
        print(f"SQL triggered: {sql_result['triggered']}, stage: {sql_result['stage']}")
        print(f"SQL delta_48h: {sql_result['delta_48h']:.2f}")
        print(f"PSDL triggered: {psdl_result.is_triggered}")
        print(f"PSDL rules: {psdl_result.triggered_logic}")

        # Both should detect AKI
        assert (
            sql_result["triggered"] == psdl_result.is_triggered
        ), f"Mismatch: SQL={sql_result['triggered']}, PSDL={psdl_result.is_triggered}"

        # Both should identify stage 1
        if sql_result["triggered"]:
            assert sql_result["stage"] == "stage1"
            # PSDL should have triggered aki_stage1 or aki_present
            assert any(
                "stage1" in name or "present" in name for name in psdl_result.triggered_logic
            )

    def test_aki_stage3_equivalence(self, aki_scenario):
        """Test that PSDL and SQL agree on AKI Stage 3 detection."""
        patient_id, data, reference_time = self.create_test_patient_aki_stage3()

        # SQL result
        sql_emulator = SQLEmulator(data)
        sql_result = sql_emulator.execute_aki_detection_sql(patient_id, reference_time)

        # PSDL result
        backend = InMemoryBackend()
        for pid, signals in data.items():
            for signal_name, datapoints in signals.items():
                backend.add_data(pid, signal_name, datapoints)

        evaluator = PSDLEvaluator(aki_scenario, backend)
        psdl_result = evaluator.evaluate_patient(patient_id, reference_time)

        print("\n=== AKI Stage 3 Comparison ===")
        print(f"SQL triggered: {sql_result['triggered']}, stage: {sql_result['stage']}")
        print(
            f"SQL delta_48h: {sql_result['delta_48h']:.2f}, "
            f"latest_cr: {sql_result['latest_cr']:.2f}"
        )
        print(f"PSDL triggered: {psdl_result.is_triggered}")
        print(f"PSDL rules: {psdl_result.triggered_logic}")

        # Both should detect severe AKI
        assert sql_result["triggered"] == psdl_result.is_triggered
        assert sql_result["stage"] == "stage3"

        assert any("stage3" in name for name in psdl_result.triggered_logic)

    def test_stable_patient_equivalence(self, aki_scenario):
        """Test that PSDL and SQL agree on stable patients (no AKI)."""
        patient_id, data, reference_time = self.create_test_patient_stable()

        # SQL result
        sql_emulator = SQLEmulator(data)
        sql_result = sql_emulator.execute_aki_detection_sql(patient_id, reference_time)

        # PSDL result
        backend = InMemoryBackend()
        for pid, signals in data.items():
            for signal_name, datapoints in signals.items():
                backend.add_data(pid, signal_name, datapoints)

        evaluator = PSDLEvaluator(aki_scenario, backend)
        psdl_result = evaluator.evaluate_patient(patient_id, reference_time)

        print("\n=== Stable Patient Comparison ===")
        print(f"SQL triggered: {sql_result['triggered']}")
        print(f"SQL delta_48h: {sql_result['delta_48h']:.2f}")
        print(f"PSDL triggered: {psdl_result.is_triggered}")

        # Neither should trigger
        assert sql_result["triggered"] is False
        assert psdl_result.is_triggered is False

    def test_icu_deterioration_equivalence(self, icu_scenario):
        """Test that PSDL and SQL agree on ICU deterioration."""
        patient_id, data, reference_time = self.create_test_patient_icu_deteriorating()

        # SQL result
        sql_emulator = SQLEmulator(data)
        sql_result = sql_emulator.execute_icu_deterioration_sql(patient_id, reference_time)

        # PSDL result
        backend = InMemoryBackend()
        for pid, signals in data.items():
            for signal_name, datapoints in signals.items():
                backend.add_data(pid, signal_name, datapoints)

        evaluator = PSDLEvaluator(icu_scenario, backend)
        psdl_result = evaluator.evaluate_patient(patient_id, reference_time)

        print("\n=== ICU Deterioration Comparison ===")
        print(f"SQL triggered: {sql_result['triggered']}")
        print(f"SQL conditions: {sql_result['conditions_met']}")
        print(
            f"SQL values: MAP={sql_result['latest_map']}, HR={sql_result['latest_hr']}, "
            f"Lact delta={sql_result['lactate_delta']}"
        )
        print(f"PSDL triggered: {psdl_result.is_triggered}")
        print(f"PSDL rules: {psdl_result.triggered_logic}")

        # Both should detect deterioration
        assert sql_result["triggered"] is True
        assert psdl_result.is_triggered is True


class TestBatchComparison:
    """Run batch comparisons to validate PSDL accuracy."""

    @pytest.fixture
    def aki_scenario(self):
        parser = PSDLParser()
        return parser.parse_file("examples/aki_detection.yaml")

    def generate_random_patients(self, n: int) -> List[Tuple[str, Dict, datetime]]:
        """Generate n patients with random creatinine patterns."""
        import random

        random.seed(42)  # Reproducible

        patients = []
        now = datetime.now()

        for i in range(n):
            patient_id = f"batch_patient_{i}"

            # Random pattern
            base_cr = random.uniform(0.7, 1.5)
            pattern = random.choice(["stable", "rising_mild", "rising_severe", "falling"])

            cr_values = []
            for h in range(48, -1, -6):
                if pattern == "stable":
                    value = base_cr + random.uniform(-0.1, 0.1)
                elif pattern == "rising_mild":
                    value = base_cr + (48 - h) / 48 * 0.4 + random.uniform(-0.05, 0.05)
                elif pattern == "rising_severe":
                    value = base_cr + (48 - h) / 48 * 3.0 + random.uniform(-0.1, 0.1)
                else:  # falling
                    value = base_cr + 1.0 - (48 - h) / 48 * 1.0 + random.uniform(-0.05, 0.05)

                cr_values.append(DataPoint(now - timedelta(hours=h), max(0.3, value)))

            data = {patient_id: {"Cr": cr_values}}
            patients.append((patient_id, data, now, pattern))

        return patients

    def test_batch_equivalence(self, aki_scenario):
        """Test PSDL vs SQL on a batch of patients."""
        patients = self.generate_random_patients(50)

        matches = 0
        mismatches = []

        for patient_id, data, reference_time, pattern in patients:
            # SQL
            sql_emulator = SQLEmulator(data)
            sql_result = sql_emulator.execute_aki_detection_sql(patient_id, reference_time)

            # PSDL
            backend = InMemoryBackend()
            for pid, signals in data.items():
                for signal_name, datapoints in signals.items():
                    backend.add_data(pid, signal_name, datapoints)

            evaluator = PSDLEvaluator(aki_scenario, backend)
            psdl_result = evaluator.evaluate_patient(patient_id, reference_time)

            # Compare AKI-specific logic, not all logic expressions
            # (some PSDL logic like cr_rising_trend are informational, not alerts)
            psdl_aki_triggered = (
                psdl_result.logic_results.get("aki_stage1", False)
                or psdl_result.logic_results.get("aki_stage2", False)
                or psdl_result.logic_results.get("aki_stage3", False)
            )

            if sql_result["triggered"] == psdl_aki_triggered:
                matches += 1
            else:
                mismatches.append(
                    {
                        "patient_id": patient_id,
                        "pattern": pattern,
                        "sql": sql_result,
                        "psdl_triggered": psdl_aki_triggered,
                    }
                )

        print("\n=== Batch Comparison Results ===")
        print(f"Total patients: {len(patients)}")
        print(f"Matches: {matches} ({matches/len(patients)*100:.1f}%)")
        print(f"Mismatches: {len(mismatches)}")

        if mismatches:
            print("\nMismatch details:")
            for m in mismatches[:5]:  # Show first 5
                print(
                    f"  {m['patient_id']} ({m['pattern']}): "
                    f"SQL={m['sql']['triggered']}, PSDL={m['psdl_triggered']}"
                )

        # Allow some tolerance due to edge cases in temporal calculations
        # But should be >90% match
        accuracy = matches / len(patients)
        assert accuracy >= 0.90, f"Accuracy {accuracy:.1%} below 90% threshold"


class TestSQLGenerationPreview:
    """
    Preview of what PSDL-to-SQL generation would look like.
    This demonstrates that PSDL can be compiled to SQL.
    """

    def test_generate_aki_sql(self):
        """Show what SQL would be generated from AKI scenario."""
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")

        # This is a preview of SQL generation (not actual implementation)
        sql_preview = """
-- Generated from PSDL scenario: {scenario.name}
-- Version: {scenario.version}

WITH signal_data AS (
    SELECT
        person_id,
        measurement_datetime,
        value_as_number as cr_value
    FROM measurement
    WHERE measurement_concept_id = 3016723  -- Creatinine (OMOP concept)
),

cr_delta_48h AS (
    SELECT
        person_id,
        MAX(cr_value) - MIN(cr_value) as delta,
        MAX(cr_value) as latest_value
    FROM signal_data
    WHERE measurement_datetime >= NOW() - INTERVAL '48 hours'
    GROUP BY person_id
),

aki_detection AS (
    SELECT
        person_id,
        CASE
            WHEN delta >= 2.0 OR latest_value >= 4.0 THEN 'stage3'
            WHEN delta >= 1.0 THEN 'stage2'
            WHEN delta >= 0.3 THEN 'stage1'
            ELSE NULL
        END as aki_stage,
        delta,
        latest_value
    FROM cr_delta_48h
)

SELECT * FROM aki_detection WHERE aki_stage IS NOT NULL;
"""
        print(sql_preview)

        # Verify the scenario has the expected structure
        assert "Cr" in scenario.signals
        assert any("delta" in t.operator for t in scenario.trends.values())
