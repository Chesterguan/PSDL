"""
Synthea FHIR Clinical Validation Tests

Validates PSDL against real Synthea synthetic patient data.
Uses local FHIR bundle files to test clinical scenarios.

Data source: Set SYNTHEA_FHIR_PATH environment variable or configure path below.
Download Synthea data from: https://synthea.mitre.org/downloads
"""

import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402

from reference.python.parser import PSDLParser  # noqa: E402
from reference.python.evaluator import PSDLEvaluator, InMemoryBackend  # noqa: E402
from reference.python.operators import DataPoint  # noqa: E402


# Path to Synthea FHIR data - configure for your local setup
# Download from: https://synthea.mitre.org/downloads
SYNTHEA_FHIR_PATH = Path(os.environ.get("SYNTHEA_FHIR_PATH", "./data/synthea/fhir"))

# LOINC codes for common clinical measurements
# Updated based on actual Synthea FHIR output
LOINC_MAPPING = {
    # Renal function
    "38483-4": "Cr",  # Creatinine (Synthea uses this code)
    "2160-0": "Cr",  # Creatinine (standard code, kept for compatibility)
    "6299-2": "BUN",  # Urea Nitrogen (Synthea)
    "3094-0": "BUN",  # Blood Urea Nitrogen (standard)
    "33914-3": "eGFR",  # Estimated GFR
    # Electrolytes
    "2947-0": "Na",  # Sodium (Synthea)
    "2951-2": "Na",  # Sodium (standard)
    "6298-4": "K",  # Potassium (Synthea)
    "2823-3": "K",  # Potassium (standard)
    "17861-6": "Ca",  # Calcium
    "49765-1": "Ca",  # Calcium (Synthea)
    "2069-3": "Cl",  # Chloride
    "20565-8": "CO2",  # Carbon Dioxide
    # Metabolic
    "2339-0": "Glucose",  # Glucose (Synthea)
    "2345-7": "Glucose",  # Glucose (standard)
    "2093-3": "Chol",  # Total Cholesterol
    "2571-8": "TG",  # Triglycerides
    "18262-6": "LDL",  # LDL Cholesterol
    "2085-9": "HDL",  # HDL Cholesterol
    "4548-4": "HbA1c",  # Hemoglobin A1c
    # Hematology
    "718-7": "Hgb",  # Hemoglobin
    "6690-2": "WBC",  # White Blood Cell Count
    "789-8": "RBC",  # Red Blood Cell Count
    "4544-3": "Hct",  # Hematocrit
    # Vitals (less common in Synthea labs, but included)
    "8867-4": "HR",  # Heart Rate
    "8480-6": "SBP",  # Systolic BP
    "8462-4": "DBP",  # Diastolic BP
    "8310-5": "Temp",  # Body Temperature
    "9279-1": "RR",  # Respiratory Rate
    "2708-6": "SpO2",  # Oxygen Saturation
    "2524-7": "Lact",  # Lactate
}


class SyntheaFHIRLoader:
    """Load and parse Synthea FHIR bundles."""

    def __init__(self, fhir_path: Path):
        self.fhir_path = fhir_path

    def list_patients(self, limit: int = None) -> List[Path]:
        """List all patient FHIR bundle files."""
        files = list(self.fhir_path.glob("*.json"))
        if limit:
            files = files[:limit]
        return files

    def load_patient_bundle(self, file_path: Path) -> Dict:
        """Load a single patient's FHIR bundle."""
        with open(file_path, "r") as f:
            return json.load(f)

    def extract_patient_id(self, bundle: Dict) -> Optional[str]:
        """Extract patient ID from bundle."""
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                return resource.get("id")
        return None

    def extract_observations(self, bundle: Dict) -> List[Dict]:
        """Extract all Observation resources from bundle."""
        observations = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Observation":
                observations.append(resource)
        return observations

    def extract_conditions(self, bundle: Dict) -> List[Dict]:
        """Extract all Condition resources from bundle."""
        conditions = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Condition":
                conditions.append(resource)
        return conditions

    def extract_procedures(self, bundle: Dict) -> List[Dict]:
        """Extract all Procedure resources from bundle."""
        procedures = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Procedure":
                procedures.append(resource)
        return procedures

    def observation_to_datapoint(self, obs: Dict) -> Optional[tuple]:
        """Convert FHIR Observation to (loinc_code, DataPoint)."""
        # Get LOINC code
        coding = obs.get("code", {}).get("coding", [])
        loinc_code = None
        for c in coding:
            if c.get("system") == "http://loinc.org":
                loinc_code = c.get("code")
                break

        if not loinc_code:
            return None

        # Get value
        value = None
        if "valueQuantity" in obs:
            value = obs["valueQuantity"].get("value")
        elif "valueString" in obs:
            try:
                value = float(obs["valueString"])
            except (ValueError, TypeError):
                pass

        if value is None:
            return None

        # Get timestamp
        timestamp = None
        if "effectiveDateTime" in obs:
            try:
                ts_str = obs["effectiveDateTime"]
                # Parse ISO format
                if "T" in ts_str:
                    timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00").split("+")[0])
                else:
                    timestamp = datetime.strptime(ts_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        if timestamp is None:
            return None

        return loinc_code, DataPoint(timestamp=timestamp, value=value)


class SyntheaPSDLBackend(InMemoryBackend):
    """Backend that loads data from Synthea FHIR bundles."""

    def __init__(self, loader: SyntheaFHIRLoader):
        super().__init__()
        self.loader = loader
        self.loaded_patients = set()

    def load_patient(self, file_path: Path) -> Optional[str]:
        """Load a patient from FHIR bundle into backend."""
        bundle = self.loader.load_patient_bundle(file_path)
        patient_id = self.loader.extract_patient_id(bundle)

        if not patient_id or patient_id in self.loaded_patients:
            return None

        # Extract and load observations
        observations = self.loader.extract_observations(bundle)

        signal_data: Dict[str, List[DataPoint]] = {}

        for obs in observations:
            result = self.loader.observation_to_datapoint(obs)
            if result:
                loinc_code, datapoint = result
                signal_name = LOINC_MAPPING.get(loinc_code)
                if signal_name:
                    if signal_name not in signal_data:
                        signal_data[signal_name] = []
                    signal_data[signal_name].append(datapoint)

        # Sort by timestamp and add to backend
        for signal_name, datapoints in signal_data.items():
            datapoints.sort(key=lambda dp: dp.timestamp)
            self.add_data(patient_id, signal_name, datapoints)

        self.loaded_patients.add(patient_id)
        return patient_id

    def get_signal_data(self, patient_id: str, signal_name: str) -> List[DataPoint]:
        """Get raw signal data for a patient (for analysis purposes)."""
        return self.data.get(patient_id, {}).get(signal_name, [])


@pytest.fixture
def synthea_loader():
    """Create Synthea FHIR loader."""
    if not SYNTHEA_FHIR_PATH.exists():
        pytest.skip(f"Synthea data not found at {SYNTHEA_FHIR_PATH}")
    return SyntheaFHIRLoader(SYNTHEA_FHIR_PATH)


@pytest.fixture
def aki_scenario():
    """Load AKI detection scenario."""
    parser = PSDLParser()
    return parser.parse_file("examples/aki_detection.yaml")


class TestSyntheaDataLoading:
    """Test loading Synthea FHIR data."""

    def test_list_patients(self, synthea_loader):
        """Test listing patient files."""
        patients = synthea_loader.list_patients(limit=10)
        assert len(patients) > 0
        print(f"\nFound {len(patients)} patient files (showing first 10)")
        for p in patients[:5]:
            print(f"  - {p.name}")

    def test_load_single_patient(self, synthea_loader):
        """Test loading a single patient bundle."""
        patients = synthea_loader.list_patients(limit=1)
        bundle = synthea_loader.load_patient_bundle(patients[0])

        assert bundle.get("resourceType") == "Bundle"
        patient_id = synthea_loader.extract_patient_id(bundle)
        assert patient_id is not None
        print(f"\nLoaded patient: {patient_id}")

        observations = synthea_loader.extract_observations(bundle)
        print(f"Observations: {len(observations)}")

        conditions = synthea_loader.extract_conditions(bundle)
        print(f"Conditions: {len(conditions)}")

        procedures = synthea_loader.extract_procedures(bundle)
        print(f"Procedures: {len(procedures)}")

    def test_extract_observations(self, synthea_loader):
        """Test extracting and converting observations."""
        patients = synthea_loader.list_patients(limit=5)

        total_obs = 0
        converted_obs = 0
        signal_counts = {}

        for patient_file in patients:
            bundle = synthea_loader.load_patient_bundle(patient_file)
            observations = synthea_loader.extract_observations(bundle)
            total_obs += len(observations)

            for obs in observations:
                result = synthea_loader.observation_to_datapoint(obs)
                if result:
                    converted_obs += 1
                    loinc_code, _ = result
                    signal_name = LOINC_MAPPING.get(loinc_code, loinc_code)
                    signal_counts[signal_name] = signal_counts.get(signal_name, 0) + 1

        print(f"\nTotal observations: {total_obs}")
        print(f"Converted to DataPoints: {converted_obs}")
        print("Signal distribution:")
        for signal, count in sorted(signal_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {signal}: {count}")


class TestSyntheaAKIValidation:
    """Validate AKI detection against Synthea data."""

    def test_evaluate_synthea_patients(self, synthea_loader, aki_scenario):
        """Evaluate AKI scenario against Synthea patients."""
        backend = SyntheaPSDLBackend(synthea_loader)

        # Load patients
        patient_files = synthea_loader.list_patients(limit=50)
        loaded_ids = []

        for pf in patient_files:
            pid = backend.load_patient(pf)
            if pid:
                loaded_ids.append(pid)

        print(f"\nLoaded {len(loaded_ids)} patients with data")

        # Evaluate each patient
        evaluator = PSDLEvaluator(aki_scenario, backend)

        results = {
            "total": len(loaded_ids),
            "with_cr_data": 0,
            "triggered": 0,
            "not_triggered": 0,
            "triggered_rules": {},
        }

        for patient_id in loaded_ids:
            # Check if patient has creatinine data
            cr_data = backend.get_signal_data(patient_id, "Cr")
            if not cr_data:
                continue

            results["with_cr_data"] += 1

            # Use the most recent data point as reference time
            reference_time = max(dp.timestamp for dp in cr_data)

            result = evaluator.evaluate_patient(patient_id=patient_id, reference_time=reference_time)

            if result.is_triggered:
                results["triggered"] += 1
                for rule in result.triggered_logic:
                    results["triggered_rules"][rule] = results["triggered_rules"].get(rule, 0) + 1
            else:
                results["not_triggered"] += 1

        print("\n=== AKI Evaluation Results ===")
        print(f"Total patients loaded: {results['total']}")
        print(f"Patients with Cr data: {results['with_cr_data']}")
        print(f"Triggered: {results['triggered']}")
        print(f"Not triggered: {results['not_triggered']}")
        if results["with_cr_data"] > 0:
            trigger_rate = results["triggered"] / results["with_cr_data"]
            print(f"Trigger rate: {trigger_rate:.1%}")
        print("Triggered rules breakdown:")
        for rule, count in sorted(results["triggered_rules"].items(), key=lambda x: -x[1]):
            print(f"  {rule}: {count}")

    def test_creatinine_patterns(self, synthea_loader):
        """Analyze creatinine patterns in Synthea data."""
        backend = SyntheaPSDLBackend(synthea_loader)

        patient_files = synthea_loader.list_patients(limit=100)

        patterns = {
            "stable_normal": 0,  # Cr < 1.2, stable
            "stable_elevated": 0,  # Cr >= 1.2, stable
            "rising": 0,  # Cr increasing
            "falling": 0,  # Cr decreasing
            "insufficient_data": 0,  # < 2 data points
        }

        for pf in patient_files:
            pid = backend.load_patient(pf)
            if not pid:
                continue

            cr_data = backend.get_signal_data(pid, "Cr")
            if not cr_data or len(cr_data) < 2:
                patterns["insufficient_data"] += 1
                continue

            # Sort by time
            cr_data.sort(key=lambda x: x.timestamp)

            # Calculate delta
            first_value = cr_data[0].value
            last_value = cr_data[-1].value
            delta = last_value - first_value

            # Classify pattern
            if abs(delta) < 0.2:  # Stable
                if last_value < 1.2:
                    patterns["stable_normal"] += 1
                else:
                    patterns["stable_elevated"] += 1
            elif delta > 0:
                patterns["rising"] += 1
            else:
                patterns["falling"] += 1

        print("\n=== Creatinine Pattern Analysis ===")
        for pattern, count in patterns.items():
            print(f"  {pattern}: {count}")


class TestSyntheaMultiScenario:
    """Test multiple scenarios against Synthea data."""

    @pytest.fixture
    def scenarios(self):
        """Load all example scenarios."""
        parser = PSDLParser()
        return {
            "AKI": parser.parse_file("examples/aki_detection.yaml"),
            "ICU": parser.parse_file("examples/icu_deterioration.yaml"),
            "Sepsis": parser.parse_file("examples/sepsis_screening.yaml"),
        }

    def test_multi_scenario_evaluation(self, synthea_loader, scenarios):
        """Evaluate all scenarios against Synthea patients."""
        backend = SyntheaPSDLBackend(synthea_loader)

        # Load patients
        patient_files = synthea_loader.list_patients(limit=100)
        loaded_ids = []

        for pf in patient_files:
            pid = backend.load_patient(pf)
            if pid:
                loaded_ids.append(pid)

        print(f"\nLoaded {len(loaded_ids)} patients")

        # Track results per scenario
        scenario_results = {}

        for scenario_name, scenario in scenarios.items():
            evaluator = PSDLEvaluator(scenario, backend)

            triggered_count = 0
            for patient_id in loaded_ids:
                # Get reference time from any available data
                all_data = []
                for signal_name in scenario.signals:
                    data = backend.get_signal_data(patient_id, signal_name)
                    if data:
                        all_data.extend(data)

                if not all_data:
                    continue

                reference_time = max(dp.timestamp for dp in all_data)

                result = evaluator.evaluate_patient(patient_id=patient_id, reference_time=reference_time)

                if result.is_triggered:
                    triggered_count += 1

            scenario_results[scenario_name] = triggered_count

        print("\n=== Multi-Scenario Results ===")
        for name, count in scenario_results.items():
            pct = count / len(loaded_ids) * 100 if loaded_ids else 0
            print(f"  {name}: {count}/{len(loaded_ids)} triggered ({pct:.1f}%)")


class TestCardiacSurgeryQuery:
    """Answer the user's question: How many patients have cardiac surgery from 2020-2025?"""

    def test_count_cardiac_procedures(self, synthea_loader):
        """Count patients with cardiac surgery procedures."""
        patient_files = synthea_loader.list_patients()  # All patients

        cardiac_surgery_codes = {
            # SNOMED CT codes for cardiac procedures (common ones)
            "232717009": "Coronary artery bypass grafting",
            "429064006": "Implantation of biventricular cardiac pacemaker",
            "429528004": "Percutaneous coronary intervention",
            "174810003": "Open heart surgery",
            "233004008": "Heart valve replacement",
            "74371005": "Cardiac catheterization",
            "418824004": "Off-pump coronary artery bypass",
        }

        patients_with_cardiac = []
        procedure_counts = {}
        year_counts = {}

        for pf in patient_files:
            bundle = synthea_loader.load_patient_bundle(pf)
            patient_id = synthea_loader.extract_patient_id(bundle)
            procedures = synthea_loader.extract_procedures(bundle)

            for proc in procedures:
                # Get procedure code
                coding = proc.get("code", {}).get("coding", [])
                for c in coding:
                    code = c.get("code")
                    display = c.get("display", "Unknown")

                    # Check if it's a cardiac procedure
                    is_cardiac = (
                        code in cardiac_surgery_codes
                        or "cardiac" in display.lower()
                        or "heart" in display.lower()
                        or "coronary" in display.lower()
                        or "cabg" in display.lower()
                    )

                    if is_cardiac:
                        # Get procedure date
                        performed = proc.get("performedDateTime") or proc.get("performedPeriod", {}).get("start")
                        if performed:
                            try:
                                year = int(performed[:4])
                                if 2020 <= year <= 2025:
                                    patients_with_cardiac.append(patient_id)
                                    procedure_counts[display] = procedure_counts.get(display, 0) + 1
                                    year_counts[year] = year_counts.get(year, 0) + 1
                            except (ValueError, TypeError):
                                pass

        # Remove duplicates
        unique_patients = list(set(patients_with_cardiac))

        print("\n=== Cardiac Surgery Analysis (2020-2025) ===")
        print(f"Total patients scanned: {len(patient_files)}")
        print(f"Patients with cardiac procedures: {len(unique_patients)}")
        print("\nProcedure types:")
        for proc, count in sorted(procedure_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {proc}: {count}")
        print("\nBy year:")
        for year in sorted(year_counts.keys()):
            print(f"  {year}: {year_counts[year]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
