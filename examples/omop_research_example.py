#!/usr/bin/env python3
"""
PSDL + OMOP CDM Research Example

This example demonstrates how to use PSDL with an OMOP CDM database
for retrospective clinical research.

Usage:
    # Set environment variable with connection string
    export OMOP_CONNECTION="postgresql://user:pass@localhost/synthea"

    # Run the example
    python examples/omop_research_example.py

Requirements:
    pip install psdl-lang[omop]
"""

import os
from datetime import datetime, timedelta

from psdl.parser import PSDLParser
from psdl.execution import PSDLEvaluator
from psdl.adapters.omop import OMOPBackend, OMOPConfig


def main():
    # ─────────────────────────────────────────────────────────────
    # 1. Configure OMOP Connection
    # ─────────────────────────────────────────────────────────────

    connection_string = os.environ.get(
        "OMOP_CONNECTION",
        "postgresql://localhost/synthea"  # Default for Synthea
    )

    config = OMOPConfig(
        connection_string=connection_string,
        cdm_schema="public",  # Adjust for your database
        cdm_version="5.4",
    )

    print(f"Connecting to OMOP CDM...")
    backend = OMOPBackend(config)

    # ─────────────────────────────────────────────────────────────
    # 2. Parse PSDL Scenario
    # ─────────────────────────────────────────────────────────────

    parser = PSDLParser()
    scenario_path = os.path.join(
        os.path.dirname(__file__),
        "aki_detection.yaml"
    )
    scenario = parser.parse_file(scenario_path)

    print(f"Loaded scenario: {scenario.name}")
    print(f"  Signals: {list(scenario.signals.keys())}")
    print(f"  Logic rules: {list(scenario.logic.keys())}")

    # ─────────────────────────────────────────────────────────────
    # 3. Find Patients with Required Data
    # ─────────────────────────────────────────────────────────────

    print("\nFinding patients with creatinine data...")
    cr_signal = scenario.signals["Cr"]

    try:
        patients = backend.get_patient_ids_with_signal(
            cr_signal,
            min_observations=3  # At least 3 creatinine measurements
        )
        print(f"  Found {len(patients)} patients with sufficient data")
    except Exception as e:
        print(f"  Error querying database: {e}")
        print("  Using sample patient IDs for demo...")
        patients = [1, 2, 3, 4, 5]

    # ─────────────────────────────────────────────────────────────
    # 4. Evaluate Cohort at Specific Time Point
    # ─────────────────────────────────────────────────────────────

    evaluator = PSDLEvaluator(scenario, backend)

    # Set reference time (e.g., end of study period)
    reference_time = datetime(2023, 12, 31, 23, 59, 59)
    print(f"\nEvaluating at: {reference_time}")

    # Track results
    triggered_patients = []
    aki_stages = {"aki_stage1": 0, "aki_stage2": 0, "aki_stage3": 0}

    for patient_id in patients[:100]:  # Limit for demo
        try:
            result = evaluator.evaluate_patient(
                patient_id=patient_id,
                reference_time=reference_time
            )

            if result.is_triggered:
                triggered_patients.append({
                    "patient_id": patient_id,
                    "logic": result.triggered_logic,
                    "cr_value": result.trend_values.get("cr_elevated"),
                })

                # Count AKI stages
                for stage in ["aki_stage1", "aki_stage2", "aki_stage3"]:
                    if stage in result.triggered_logic:
                        aki_stages[stage] += 1

        except Exception as e:
            # Skip patients with missing data
            continue

    # ─────────────────────────────────────────────────────────────
    # 5. Report Results
    # ─────────────────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("RESEARCH COHORT RESULTS")
    print("=" * 60)

    print(f"\nPatients evaluated: {min(len(patients), 100)}")
    print(f"Patients with AKI: {len(triggered_patients)}")

    if triggered_patients:
        print(f"\nAKI Stage Distribution:")
        for stage, count in aki_stages.items():
            print(f"  {stage}: {count}")

        print(f"\nSample triggered patients:")
        for p in triggered_patients[:5]:
            print(f"  Patient {p['patient_id']}: {p['logic']}")

    # ─────────────────────────────────────────────────────────────
    # 6. Timeline Analysis (Optional)
    # ─────────────────────────────────────────────────────────────

    if triggered_patients:
        print("\n" + "-" * 60)
        print("TIMELINE ANALYSIS (First Triggered Patient)")
        print("-" * 60)

        patient_id = triggered_patients[0]["patient_id"]
        print(f"\nScanning timeline for patient {patient_id}...")

        # Scan last 30 days
        end_time = reference_time
        start_time = end_time - timedelta(days=30)
        step = timedelta(hours=12)

        timeline_events = []
        current = start_time

        while current <= end_time:
            try:
                result = evaluator.evaluate_patient(patient_id, current)
                if result.is_triggered:
                    timeline_events.append({
                        "time": current,
                        "logic": result.triggered_logic,
                    })
            except Exception:
                pass
            current += step

        if timeline_events:
            print(f"Found {len(timeline_events)} trigger events in 30 days:")
            for event in timeline_events[:10]:
                print(f"  {event['time']}: {event['logic']}")
        else:
            print("No trigger events found in timeline scan")

    # ─────────────────────────────────────────────────────────────
    # Cleanup
    # ─────────────────────────────────────────────────────────────

    backend.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
