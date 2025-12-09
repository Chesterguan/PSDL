"""
MIMIC-IV FHIR Clinical Validation Tests

Validates PSDL against real MIMIC-IV hospital data.
MIMIC-IV contains de-identified ICU patient data from Beth Israel Deaconess Medical Center.

Data source: Set MIMIC_FHIR_PATH environment variable or configure path below.
Download from: https://physionet.org/content/mimic-iv-fhir/ (requires credentialed access)

Note: MIMIC-IV data requires PhysioNet credentialed access.
These tests demonstrate that PSDL works with real hospital EHR data.
"""

import sys
import os
import json
import gzip
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Iterator
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from reference.python.parser import PSDLParser
from reference.python.execution.batch import PSDLEvaluator, InMemoryBackend
from reference.python.operators import DataPoint


# Path to MIMIC-IV FHIR data - configure for your local setup
# Download from: https://physionet.org/content/mimic-iv-fhir/ (requires credentialed access)
MIMIC_FHIR_PATH = Path(os.environ.get("MIMIC_FHIR_PATH", "./data/mimic-iv-fhir"))

# MIMIC lab item codes mapping to PSDL signals
# These are MIMIC-specific codes, not LOINC
MIMIC_LAB_MAPPING = {
    # Renal function
    "50912": "Cr",  # Creatinine
    "50920": "eGFR",  # Estimated GFR
    "51006": "BUN",  # Urea Nitrogen
    # Electrolytes
    "50983": "Na",  # Sodium
    "50971": "K",  # Potassium
    "50893": "Ca",  # Calcium Total
    "50902": "Cl",  # Chloride
    "50882": "CO2",  # Bicarbonate (Total CO2)
    "50804": "CO2",  # Calculated Total CO2
    # Metabolic
    "50931": "Glucose",  # Glucose
    "50809": "Glucose",  # Glucose (Blood Gas)
    # Blood gases
    "50813": "Lact",  # Lactate
    "50820": "pH",  # pH
    # Hematology
    "51222": "Hgb",  # Hemoglobin
    "51301": "WBC",  # White Blood Cells
    "51265": "Plt",  # Platelet Count
    # Cardiac
    "50911": "CK",  # Creatine Kinase
    "51003": "TnT",  # Troponin T
}


def skip_if_no_mimic():
    """Skip test if MIMIC data is not available."""
    if not MIMIC_FHIR_PATH.exists():
        pytest.skip("MIMIC-IV FHIR data not available")


class MIMICFHIRLoader:
    """Load and parse MIMIC-IV FHIR ndjson files."""

    def __init__(self, fhir_path: Path):
        self.fhir_path = fhir_path

    def stream_ndjson_gz(self, filename: str, limit: int = None) -> Iterator[Dict]:
        """Stream records from a gzipped ndjson file."""
        filepath = self.fhir_path / filename
        if not filepath.exists():
            return

        count = 0
        with gzip.open(filepath, "rt", encoding="utf-8") as f:
            for line in f:
                if limit and count >= limit:
                    break
                try:
                    yield json.loads(line.strip())
                    count += 1
                except json.JSONDecodeError:
                    continue

    def get_lab_observations(
        self, patient_id: str = None, lab_codes: List[str] = None, limit: int = 10000
    ) -> List[Dict]:
        """Get lab observations, optionally filtered by patient and lab codes."""
        observations = []

        for obs in self.stream_ndjson_gz(
            "MimicObservationLabevents.ndjson.gz", limit=limit
        ):
            # Filter by patient if specified
            if patient_id:
                subject_ref = obs.get("subject", {}).get("reference", "")
                if not subject_ref.endswith(patient_id):
                    continue

            # Filter by lab codes if specified
            if lab_codes:
                coding = obs.get("code", {}).get("coding", [{}])[0]
                code = coding.get("code")
                if code not in lab_codes:
                    continue

            observations.append(obs)

        return observations

    def get_patients(self, limit: int = 100) -> List[Dict]:
        """Get patient resources."""
        return list(self.stream_ndjson_gz("MimicPatient.ndjson.gz", limit=limit))

    def get_icu_encounters(self, limit: int = 1000) -> List[Dict]:
        """Get ICU encounters."""
        return list(self.stream_ndjson_gz("MimicEncounterICU.ndjson.gz", limit=limit))

    def observation_to_datapoint(self, obs: Dict) -> Optional[tuple]:
        """Convert MIMIC observation to (signal_name, DataPoint)."""
        # Get code
        coding = obs.get("code", {}).get("coding", [{}])[0]
        code = coding.get("code")

        if code not in MIMIC_LAB_MAPPING:
            return None

        signal_name = MIMIC_LAB_MAPPING[code]

        # Get value
        value_quantity = obs.get("valueQuantity", {})
        value = value_quantity.get("value")

        if value is None:
            return None

        # Get timestamp
        timestamp_str = obs.get("effectiveDateTime")
        if not timestamp_str:
            timestamp_str = obs.get("issued")

        if not timestamp_str:
            return None

        try:
            # Parse ISO timestamp (MIMIC uses offset format like "2140-01-06T09:49:00-05:00")
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            # Convert to naive datetime for consistency
            timestamp = timestamp.replace(tzinfo=None)
        except (ValueError, AttributeError):
            return None

        return signal_name, DataPoint(timestamp, float(value))


class MIMICPSDLBackend(InMemoryBackend):
    """PSDL backend that loads data from MIMIC-IV FHIR."""

    def __init__(self, loader: MIMICFHIRLoader):
        super().__init__()
        self.loader = loader
        self.loaded_patients = set()

    def load_patient_labs(self, patient_id: str, lab_limit: int = 1000) -> int:
        """Load lab data for a specific patient."""
        if patient_id in self.loaded_patients:
            return 0

        observations = self.loader.get_lab_observations(
            patient_id=patient_id,
            lab_codes=list(MIMIC_LAB_MAPPING.keys()),
            limit=lab_limit,
        )

        # Group by signal
        signal_data = defaultdict(list)

        for obs in observations:
            result = self.loader.observation_to_datapoint(obs)
            if result:
                signal_name, dp = result
                signal_data[signal_name].append(dp)

        # Add to backend
        for signal_name, datapoints in signal_data.items():
            self.add_data(patient_id, signal_name, datapoints)

        self.loaded_patients.add(patient_id)
        return len(observations)

    def load_from_stream(self, limit: int = 10000) -> Dict[str, int]:
        """Stream observations and load into backend."""
        patient_data = defaultdict(lambda: defaultdict(list))
        stats = {"observations": 0, "patients": 0, "signals": defaultdict(int)}

        for obs in self.loader.stream_ndjson_gz(
            "MimicObservationLabevents.ndjson.gz", limit=limit
        ):
            result = self.loader.observation_to_datapoint(obs)
            if not result:
                continue

            signal_name, dp = result
            subject_ref = obs.get("subject", {}).get("reference", "")
            patient_id = (
                subject_ref.split("/")[-1] if "/" in subject_ref else subject_ref
            )

            patient_data[patient_id][signal_name].append(dp)
            stats["observations"] += 1
            stats["signals"][signal_name] += 1

        # Add all data to backend
        for patient_id, signals in patient_data.items():
            for signal_name, datapoints in signals.items():
                self.add_data(patient_id, signal_name, datapoints)
            self.loaded_patients.add(patient_id)

        stats["patients"] = len(patient_data)
        return stats


@pytest.fixture
def mimic_loader():
    """Create MIMIC FHIR loader."""
    skip_if_no_mimic()
    return MIMICFHIRLoader(MIMIC_FHIR_PATH)


@pytest.fixture
def aki_scenario():
    """Load AKI detection scenario."""
    parser = PSDLParser()
    return parser.parse_file("examples/aki_detection.yaml")


@pytest.fixture
def icu_scenario():
    """Load ICU deterioration scenario."""
    parser = PSDLParser()
    return parser.parse_file("examples/icu_deterioration.yaml")


class TestMIMICDataLoading:
    """Test basic MIMIC data loading capabilities."""

    def test_stream_lab_observations(self, mimic_loader):
        """Test streaming lab observations."""
        count = 0
        cr_count = 0

        for obs in mimic_loader.stream_ndjson_gz(
            "MimicObservationLabevents.ndjson.gz", limit=10000
        ):
            count += 1
            coding = obs.get("code", {}).get("coding", [{}])[0]
            if coding.get("code") == "50912":  # Creatinine
                cr_count += 1

        print(f"\nStreamed {count} observations, {cr_count} creatinine values")
        assert count > 0
        assert cr_count > 0

    def test_observation_conversion(self, mimic_loader):
        """Test converting MIMIC observations to DataPoints."""
        converted = 0
        failed = 0

        for obs in mimic_loader.stream_ndjson_gz(
            "MimicObservationLabevents.ndjson.gz", limit=1000
        ):
            result = mimic_loader.observation_to_datapoint(obs)
            if result:
                converted += 1
            else:
                failed += 1

        print(f"\nConverted: {converted}, Failed/Filtered: {failed}")
        assert converted > 0

    def test_get_patients(self, mimic_loader):
        """Test getting patient resources."""
        patients = mimic_loader.get_patients(limit=100)
        print(f"\nLoaded {len(patients)} patients")

        if patients:
            # Show sample patient structure
            sample = patients[0]
            print(f"Sample patient ID: {sample.get('id')}")
            print(f"Sample patient gender: {sample.get('gender')}")

        assert len(patients) > 0


class TestMIMICAKIValidation:
    """Validate AKI detection against MIMIC-IV ICU patients."""

    def test_evaluate_mimic_patients(self, mimic_loader, aki_scenario):
        """Evaluate AKI scenario against MIMIC patients."""
        backend = MIMICPSDLBackend(mimic_loader)

        # Load observations from stream
        print("\nLoading MIMIC observations...")
        stats = backend.load_from_stream(limit=50000)

        print("\n=== MIMIC Data Loading Results ===")
        print(f"Total observations: {stats['observations']}")
        print(f"Unique patients: {stats['patients']}")
        print("Signal distribution:")
        for signal, count in sorted(stats["signals"].items(), key=lambda x: -x[1]):
            print(f"  {signal}: {count}")

        # Evaluate patients with creatinine data
        evaluator = PSDLEvaluator(aki_scenario, backend)

        triggered_count = 0
        evaluated_count = 0
        triggered_details = []

        for patient_id in backend.loaded_patients:
            # Get creatinine data
            cr_data = backend.data.get(patient_id, {}).get("Cr", [])

            if len(cr_data) < 2:
                continue

            evaluated_count += 1

            # Use latest observation as reference time
            reference_time = max(dp.timestamp for dp in cr_data)

            result = evaluator.evaluate_patient(patient_id, reference_time)

            if result.is_triggered:
                triggered_count += 1
                # Get delta value for analysis
                cr_values = [
                    dp.value for dp in sorted(cr_data, key=lambda x: x.timestamp)
                ]
                delta = cr_values[-1] - cr_values[0] if len(cr_values) >= 2 else 0
                triggered_details.append(
                    {
                        "patient_id": patient_id[:16] + "...",
                        "logic": result.triggered_logic,
                        "cr_range": f"{min(cr_values):.1f}-{max(cr_values):.1f}",
                        "delta": delta,
                    }
                )

        print("\n=== AKI Evaluation Results ===")
        print(f"Patients with sufficient Cr data: {evaluated_count}")
        print(f"AKI triggered: {triggered_count}")
        if evaluated_count > 0:
            print(f"AKI rate: {triggered_count/evaluated_count*100:.1f}%")

        if triggered_details:
            print("\nSample triggered patients:")
            for detail in triggered_details[:5]:
                print(f"  {detail['patient_id']}: {detail['logic']}")
                print(
                    f"    Cr range: {detail['cr_range']} mg/dL, delta: {detail['delta']:.2f}"
                )

        # MIMIC has ICU patients, so we expect some AKI
        # But not asserting specific rates since data varies
        assert evaluated_count > 0, "Should have patients with creatinine data"

    def test_compare_with_gfr(self, mimic_loader, aki_scenario):
        """Compare AKI detection with eGFR trends."""
        backend = MIMICPSDLBackend(mimic_loader)
        backend.load_from_stream(limit=30000)

        evaluator = PSDLEvaluator(aki_scenario, backend)

        aki_with_low_gfr = 0
        aki_with_normal_gfr = 0
        no_aki_with_low_gfr = 0

        for patient_id in backend.loaded_patients:
            cr_data = backend.data.get(patient_id, {}).get("Cr", [])
            gfr_data = backend.data.get(patient_id, {}).get("eGFR", [])

            if len(cr_data) < 2:
                continue

            reference_time = max(dp.timestamp for dp in cr_data)
            result = evaluator.evaluate_patient(patient_id, reference_time)

            # Check GFR if available
            latest_gfr = None
            if gfr_data:
                latest_gfr = max(gfr_data, key=lambda x: x.timestamp).value

            if result.is_triggered:
                if latest_gfr and latest_gfr < 60:
                    aki_with_low_gfr += 1
                elif latest_gfr:
                    aki_with_normal_gfr += 1
            else:
                if latest_gfr and latest_gfr < 60:
                    no_aki_with_low_gfr += 1

        print("\n=== AKI vs eGFR Correlation ===")
        print(f"AKI with low eGFR (<60): {aki_with_low_gfr}")
        print(f"AKI with normal eGFR: {aki_with_normal_gfr}")
        print(f"No AKI but low eGFR (possible CKD): {no_aki_with_low_gfr}")


class TestMIMICMultiScenario:
    """Test multiple PSDL scenarios against MIMIC data."""

    @pytest.fixture
    def all_scenarios(self):
        """Load all example scenarios."""
        parser = PSDLParser()
        return {
            "AKI": parser.parse_file("examples/aki_detection.yaml"),
            "ICU": parser.parse_file("examples/icu_deterioration.yaml"),
            "Sepsis": parser.parse_file("examples/sepsis_screening.yaml"),
        }

    def test_multi_scenario_evaluation(self, mimic_loader, all_scenarios):
        """Evaluate all scenarios against MIMIC patients."""
        backend = MIMICPSDLBackend(mimic_loader)

        # Load more data for multi-scenario testing
        print("\nLoading MIMIC data for multi-scenario test...")
        stats = backend.load_from_stream(limit=100000)
        print(
            f"Loaded {stats['observations']} observations from {stats['patients']} patients"
        )

        results = {}

        for scenario_name, scenario in all_scenarios.items():
            evaluator = PSDLEvaluator(scenario, backend)

            triggered = 0
            evaluated = 0

            # Determine required signals for this scenario
            required_signals = list(scenario.signals.keys())

            for patient_id in backend.loaded_patients:
                # Check if patient has data for at least one required signal
                patient_signals = backend.data.get(patient_id, {})
                available = [s for s in required_signals if s in patient_signals]

                if not available:
                    continue

                # Get reference time from available data
                all_data = []
                for signal_name in available:
                    all_data.extend(patient_signals.get(signal_name, []))

                if not all_data:
                    continue

                evaluated += 1
                reference_time = max(dp.timestamp for dp in all_data)

                result = evaluator.evaluate_patient(patient_id, reference_time)
                if result.is_triggered:
                    triggered += 1

            results[scenario_name] = {"triggered": triggered, "evaluated": evaluated}

        print("\n=== Multi-Scenario Results ===")
        for name, r in results.items():
            if r["evaluated"] > 0:
                pct = r["triggered"] / r["evaluated"] * 100
                print(
                    f"  {name}: {r['triggered']}/{r['evaluated']} triggered ({pct:.1f}%)"
                )
            else:
                print(f"  {name}: No patients with required data")


class TestMIMICClinicalQueries:
    """Answer clinical questions using PSDL on MIMIC data."""

    def test_aki_stages_distribution(self, mimic_loader, aki_scenario):
        """Analyze distribution of AKI stages in MIMIC ICU patients."""
        backend = MIMICPSDLBackend(mimic_loader)
        backend.load_from_stream(limit=50000)

        evaluator = PSDLEvaluator(aki_scenario, backend)

        stage_counts = defaultdict(int)
        total_evaluated = 0

        for patient_id in backend.loaded_patients:
            cr_data = backend.data.get(patient_id, {}).get("Cr", [])

            if len(cr_data) < 2:
                continue

            total_evaluated += 1
            reference_time = max(dp.timestamp for dp in cr_data)
            result = evaluator.evaluate_patient(patient_id, reference_time)

            if result.is_triggered:
                # Determine highest stage
                if "aki_stage3" in result.triggered_logic:
                    stage_counts["Stage 3"] += 1
                elif "aki_stage2" in result.triggered_logic:
                    stage_counts["Stage 2"] += 1
                elif "aki_stage1" in result.triggered_logic:
                    stage_counts["Stage 1"] += 1
                else:
                    stage_counts["Other"] += 1
            else:
                stage_counts["No AKI"] += 1

        print("\n=== AKI Stage Distribution (MIMIC ICU) ===")
        print(f"Total patients evaluated: {total_evaluated}")
        for stage, count in sorted(stage_counts.items()):
            pct = count / total_evaluated * 100 if total_evaluated > 0 else 0
            print(f"  {stage}: {count} ({pct:.1f}%)")

    def test_lactate_trends(self, mimic_loader):
        """Analyze lactate trends in MIMIC patients."""
        backend = MIMICPSDLBackend(mimic_loader)
        backend.load_from_stream(limit=100000)

        elevated_lactate = 0
        normal_lactate = 0
        rising_trend = 0

        for patient_id in backend.loaded_patients:
            lact_data = backend.data.get(patient_id, {}).get("Lact", [])

            if not lact_data:
                continue

            latest = max(lact_data, key=lambda x: x.timestamp).value

            if latest > 2.0:  # mmol/L threshold
                elevated_lactate += 1
            else:
                normal_lactate += 1

            # Check for rising trend
            if len(lact_data) >= 2:
                sorted_data = sorted(lact_data, key=lambda x: x.timestamp)
                if sorted_data[-1].value > sorted_data[0].value + 1.0:
                    rising_trend += 1

        print("\n=== Lactate Analysis (MIMIC ICU) ===")
        print(f"Elevated (>2.0 mmol/L): {elevated_lactate}")
        print(f"Normal: {normal_lactate}")
        print(f"Rising trend (>1.0 increase): {rising_trend}")
