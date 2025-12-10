#!/usr/bin/env python3
"""
Load test data into local FHIR server for PSDL integration testing.

This creates patients with clinical data that matches our test scenarios:
- AKI detection (rising creatinine)
- ICU deterioration (heart rate, blood pressure)
- Sepsis screening (temperature, lactate)

Usage:
    python tests/fixtures/load_fhir_test_data.py [--base-url http://localhost:8080/fhir]
"""

import sys
from datetime import datetime, timedelta
from typing import Dict

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


# LOINC codes for common clinical measurements
LOINC = {
    "creatinine": "2160-0",
    "heart_rate": "8867-4",
    "systolic_bp": "8480-6",
    "diastolic_bp": "8462-4",
    "temperature": "8310-5",
    "respiratory_rate": "9279-1",
    "oxygen_saturation": "2708-6",
    "lactate": "2524-7",
    "potassium": "2823-3",
    "hemoglobin": "718-7",
    "wbc": "6690-2",
    "gcs": "9269-2",
}


class FHIRTestDataLoader:
    """Load test data into FHIR server."""

    def __init__(self, base_url: str = "http://localhost:8080/fhir"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json",
            }
        )

    def create_patient(
        self, patient_id: str, name: str, birth_date: str = "1970-01-01"
    ) -> Dict:
        """Create a patient resource."""
        patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [
                {"system": "http://psdl.test/patient-id", "value": patient_id}
            ],
            "name": [
                {
                    "family": name.split()[-1] if " " in name else name,
                    "given": [name.split()[0]] if " " in name else [name],
                }
            ],
            "birthDate": birth_date,
            "gender": "unknown",
        }

        response = self.session.put(
            f"{self.base_url}/Patient/{patient_id}", json=patient
        )
        response.raise_for_status()
        return response.json()

    def create_observation(
        self,
        patient_id: str,
        loinc_code: str,
        value: float,
        unit: str,
        timestamp: datetime,
        obs_id: str = None,
    ) -> Dict:
        """Create an observation resource."""
        if obs_id is None:
            obs_id = f"{patient_id}-{loinc_code}-{timestamp.strftime('%Y%m%d%H%M%S')}"

        observation = {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": loinc_code,
                        "display": self._get_loinc_display(loinc_code),
                    }
                ]
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valueQuantity": {
                "value": value,
                "unit": unit,
                "system": "http://unitsofmeasure.org",
            },
        }

        response = self.session.put(
            f"{self.base_url}/Observation/{obs_id}", json=observation
        )
        response.raise_for_status()
        return response.json()

    def _get_loinc_display(self, code: str) -> str:
        """Get display name for LOINC code."""
        displays = {
            "2160-0": "Creatinine",
            "8867-4": "Heart rate",
            "8480-6": "Systolic blood pressure",
            "8462-4": "Diastolic blood pressure",
            "8310-5": "Body temperature",
            "9279-1": "Respiratory rate",
            "2708-6": "Oxygen saturation",
            "2524-7": "Lactate",
            "2823-3": "Potassium",
            "718-7": "Hemoglobin",
            "6690-2": "WBC",
            "9269-2": "Glasgow coma scale",
        }
        return displays.get(code, code)

    def load_aki_patient_triggered(self):
        """
        Create patient with rising creatinine (should trigger AKI detection).

        Creatinine rises from 1.0 to 1.8 over 6 hours.
        """
        patient_id = "aki-triggered"
        now = datetime.utcnow()

        print(f"Creating AKI patient (triggered): {patient_id}")
        self.create_patient(patient_id, "AKI Triggered")

        # Rising creatinine pattern
        values = [
            (now - timedelta(hours=6), 1.0),
            (now - timedelta(hours=4), 1.2),
            (now - timedelta(hours=2), 1.5),
            (now, 1.8),  # High and rising
        ]

        for ts, val in values:
            self.create_observation(patient_id, LOINC["creatinine"], val, "mg/dL", ts)
        print(f"  Created {len(values)} creatinine observations")

    def load_aki_patient_stable(self):
        """
        Create patient with stable creatinine (should NOT trigger AKI).

        Creatinine stays around 1.0 mg/dL.
        """
        patient_id = "aki-stable"
        now = datetime.utcnow()

        print(f"Creating AKI patient (stable): {patient_id}")
        self.create_patient(patient_id, "AKI Stable")

        # Stable creatinine pattern
        values = [
            (now - timedelta(hours=6), 1.0),
            (now - timedelta(hours=4), 0.95),
            (now - timedelta(hours=2), 1.05),
            (now, 1.0),
        ]

        for ts, val in values:
            self.create_observation(patient_id, LOINC["creatinine"], val, "mg/dL", ts)
        print(f"  Created {len(values)} creatinine observations")

    def load_icu_deterioration_patient(self):
        """
        Create patient with ICU deterioration pattern.

        Rising heart rate + falling blood pressure.
        """
        patient_id = "icu-deteriorating"
        now = datetime.utcnow()

        print(f"Creating ICU deterioration patient: {patient_id}")
        self.create_patient(patient_id, "ICU Deteriorating")

        # Heart rate rising
        hr_values = [
            (now - timedelta(hours=4), 75),
            (now - timedelta(hours=3), 82),
            (now - timedelta(hours=2), 95),
            (now - timedelta(hours=1), 108),
            (now, 120),
        ]

        for ts, val in hr_values:
            self.create_observation(
                patient_id, LOINC["heart_rate"], float(val), "bpm", ts
            )

        # Blood pressure falling
        bp_values = [
            (now - timedelta(hours=4), 120),
            (now - timedelta(hours=3), 115),
            (now - timedelta(hours=2), 105),
            (now - timedelta(hours=1), 95),
            (now, 88),
        ]

        for ts, val in bp_values:
            self.create_observation(
                patient_id, LOINC["systolic_bp"], float(val), "mmHg", ts
            )

        print(f"  Created {len(hr_values)} HR + {len(bp_values)} BP observations")

    def load_sepsis_patient(self):
        """
        Create patient meeting sepsis criteria.

        High temperature, elevated lactate, tachycardia.
        """
        patient_id = "sepsis-positive"
        now = datetime.utcnow()

        print(f"Creating sepsis patient: {patient_id}")
        self.create_patient(patient_id, "Sepsis Positive")

        # Temperature rising (fever)
        temp_values = [
            (now - timedelta(hours=3), 37.2),
            (now - timedelta(hours=2), 38.0),
            (now - timedelta(hours=1), 38.8),
            (now, 39.2),
        ]
        for ts, val in temp_values:
            self.create_observation(patient_id, LOINC["temperature"], val, "Cel", ts)

        # Elevated lactate
        lactate_values = [
            (now - timedelta(hours=3), 1.5),
            (now - timedelta(hours=1), 2.8),
            (now, 3.5),
        ]
        for ts, val in lactate_values:
            self.create_observation(patient_id, LOINC["lactate"], val, "mmol/L", ts)

        # Tachycardia
        hr_values = [
            (now - timedelta(hours=3), 88),
            (now - timedelta(hours=2), 102),
            (now - timedelta(hours=1), 115),
            (now, 125),
        ]
        for ts, val in hr_values:
            self.create_observation(
                patient_id, LOINC["heart_rate"], float(val), "bpm", ts
            )

        print("  Created temp + lactate + HR observations")

    def load_normal_patient(self):
        """
        Create patient with all normal values.

        Should not trigger any clinical alerts.
        """
        patient_id = "normal-patient"
        now = datetime.utcnow()

        print(f"Creating normal patient: {patient_id}")
        self.create_patient(patient_id, "Normal Patient")

        # Normal creatinine
        for i in range(4):
            ts = now - timedelta(hours=i * 2)
            self.create_observation(
                patient_id, LOINC["creatinine"], 0.9 + (i % 2) * 0.1, "mg/dL", ts
            )

        # Normal heart rate
        for i in range(4):
            ts = now - timedelta(hours=i * 2)
            self.create_observation(
                patient_id, LOINC["heart_rate"], 70 + (i % 2) * 5, "bpm", ts
            )

        # Normal blood pressure
        for i in range(4):
            ts = now - timedelta(hours=i * 2)
            self.create_observation(
                patient_id, LOINC["systolic_bp"], 118 + (i % 2) * 4, "mmHg", ts
            )

        # Normal temperature
        for i in range(4):
            ts = now - timedelta(hours=i * 2)
            self.create_observation(
                patient_id, LOINC["temperature"], 36.8 + (i % 2) * 0.2, "Cel", ts
            )

        print("  Created all normal observations")

    def load_all_test_data(self):
        """Load all test patients."""
        print(f"\nLoading FHIR test data to: {self.base_url}")
        print("=" * 50)

        self.load_aki_patient_triggered()
        self.load_aki_patient_stable()
        self.load_icu_deterioration_patient()
        self.load_sepsis_patient()
        self.load_normal_patient()

        print("=" * 50)
        print("Test data loaded successfully!")
        print("\nCreated patients:")
        print("  - aki-triggered: Rising creatinine (should trigger AKI)")
        print("  - aki-stable: Stable creatinine (should not trigger)")
        print("  - icu-deteriorating: Rising HR + falling BP")
        print("  - sepsis-positive: Fever + elevated lactate + tachycardia")
        print("  - normal-patient: All normal values")

    def verify_data(self):
        """Verify test data was loaded."""
        print("\nVerifying loaded data...")

        # Count patients
        response = self.session.get(f"{self.base_url}/Patient?_summary=count")
        if response.ok:
            data = response.json()
            count = data.get("total", 0)
            print(f"  Patients: {count}")

        # Count observations
        response = self.session.get(f"{self.base_url}/Observation?_summary=count")
        if response.ok:
            data = response.json()
            count = data.get("total", 0)
            print(f"  Observations: {count}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load FHIR test data")
    parser.add_argument(
        "--base-url", default="http://localhost:8080/fhir", help="FHIR server base URL"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify existing data"
    )
    args = parser.parse_args()

    loader = FHIRTestDataLoader(args.base_url)

    if args.verify_only:
        loader.verify_data()
    else:
        loader.load_all_test_data()
        loader.verify_data()


if __name__ == "__main__":
    main()
