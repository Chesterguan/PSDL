"""
Local FHIR Integration Tests

Tests PSDL against a local HAPI FHIR server with pre-loaded test data.
These tests are fast and deterministic because they use controlled test data.

Prerequisites:
    1. Start HAPI FHIR: docker run -d --name psdl-fhir -p 8080:8080 hapiproject/hapi:latest
    2. Load test data: python tests/fixtures/load_fhir_test_data.py

Run with: pytest tests/test_fhir_local.py -v
Skip with: pytest tests/ -v --ignore=tests/test_fhir_local.py

Environment variable FHIR_LOCAL=1 enables these tests in CI.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from psdl.adapters.fhir import FHIRBackend, FHIRConfig
from psdl.execution.batch import PSDLEvaluator
from psdl.parser import PSDLParser

# Check if local FHIR server is available
LOCAL_FHIR_URL = os.environ.get("FHIR_LOCAL_URL", "http://localhost:8080/fhir")


def fhir_available():
    """Check if local FHIR server is available AND has test data loaded."""
    try:
        import requests

        # Check server is responding
        response = requests.get(f"{LOCAL_FHIR_URL}/metadata", timeout=5)
        if response.status_code != 200:
            return False

        # Check if test patients are loaded (not just server availability)
        # Look for our specific test patient IDs
        test_patient_response = requests.get(f"{LOCAL_FHIR_URL}/Patient/aki-triggered", timeout=5)
        if test_patient_response.status_code != 200:
            return False

        # Also verify observations exist for test patient
        obs_response = requests.get(
            f"{LOCAL_FHIR_URL}/Observation?subject=Patient/aki-triggered&code=2160-0",
            timeout=5,
        )
        if obs_response.status_code != 200:
            return False
        obs_data = obs_response.json()
        return obs_data.get("total", 0) >= 4  # Expect at least 4 creatinine observations
    except Exception:
        return False


# Skip all tests unless FHIR_LOCAL=1 is explicitly set
# These tests require a properly configured local FHIR server with test data
FHIR_LOCAL_REQUIRED = os.environ.get("FHIR_LOCAL", "0") == "1"
FHIR_AVAILABLE = FHIR_LOCAL_REQUIRED and fhir_available()

if FHIR_LOCAL_REQUIRED and not FHIR_AVAILABLE:
    pytest.fail("FHIR_LOCAL=1 but local FHIR server not available")

pytestmark = pytest.mark.skipif(
    not FHIR_AVAILABLE,
    reason="Local FHIR server not available. "
    "Start with: docker run -d --name psdl-fhir -p 8080:8080 hapiproject/hapi:latest",
)


@pytest.fixture
def backend():
    """Create a backend connected to local FHIR."""
    config = FHIRConfig(
        base_url=LOCAL_FHIR_URL,
        timeout=10,
    )
    backend = FHIRBackend(config)
    yield backend
    backend.close()


@pytest.fixture
def parser():
    """Create a PSDL parser."""
    return PSDLParser()


class TestLocalFHIRConnection:
    """Test basic FHIR connectivity."""

    def test_server_available(self, backend):
        """Test that local FHIR server is responding."""
        session = backend._get_session()
        response = session.get(f"{LOCAL_FHIR_URL}/metadata", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data.get("resourceType") == "CapabilityStatement"

    def test_patients_loaded(self, backend):
        """Test that test patients are loaded."""
        patients = backend.get_patient_ids()
        assert len(patients) >= 5, "Expected at least 5 test patients"

        # Check for specific test patients
        assert "aki-triggered" in patients
        assert "aki-stable" in patients
        assert "normal-patient" in patients

    def test_get_patient(self, backend):
        """Test fetching a specific patient."""
        patient = backend.get_patient("aki-triggered")
        assert patient is not None
        assert patient.get("resourceType") == "Patient"


class TestAKIDetection:
    """Test AKI detection scenario against local FHIR data."""

    AKI_SCENARIO = """
scenario: AKI_Detection_Test
version: "0.1.0"
description: "Detect rising creatinine indicating AKI"

signals:
  Cr:
    source: "2160-0"  # LOINC for creatinine
    unit: mg/dL

trends:
  cr_high:
    expr: last(Cr) > 1.5
    description: "Current creatinine elevated"

  cr_rising:
    expr: delta(Cr, 6h) > 0.3
    description: "Creatinine rose > 0.3 in 6 hours"

logic:
  aki_risk:
    expr: cr_high AND cr_rising
    severity: high
    description: "High AKI risk - elevated and rising creatinine"
"""

    def test_aki_triggered_patient(self, backend, parser):
        """Patient with rising creatinine should trigger AKI detection."""
        scenario = parser.parse_string(self.AKI_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="aki-triggered", reference_time=datetime.utcnow()
        )

        # This patient has creatinine: 1.0 -> 1.2 -> 1.5 -> 1.8
        # last(Cr) = 1.8 > 1.5 (True)
        # delta(Cr, 6h) = 0.8 > 0.3 (True)
        assert result.is_triggered, "AKI patient should trigger"
        assert "aki_risk" in result.triggered_logic
        assert result.trend_results["cr_high"] is True
        assert result.trend_results["cr_rising"] is True

    def test_stable_patient_not_triggered(self, backend, parser):
        """Patient with stable creatinine should NOT trigger AKI detection."""
        scenario = parser.parse_string(self.AKI_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="aki-stable", reference_time=datetime.utcnow()
        )

        # This patient has creatinine: 1.0 -> 0.95 -> 1.05 -> 1.0
        # last(Cr) = 1.0 NOT > 1.5 (False)
        # delta(Cr, 6h) = 0.0 NOT > 0.3 (False)
        assert result.trend_results["cr_high"] is False
        assert result.trend_results["cr_rising"] is False
        assert "aki_risk" not in result.triggered_logic

    def test_normal_patient_not_triggered(self, backend, parser):
        """Normal patient should NOT trigger AKI detection."""
        scenario = parser.parse_string(self.AKI_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="normal-patient", reference_time=datetime.utcnow()
        )

        assert result.trend_results["cr_high"] is False
        assert "aki_risk" not in result.triggered_logic


class TestICUDeterioration:
    """Test ICU deterioration detection against local FHIR data."""

    ICU_SCENARIO = """
scenario: ICU_Deterioration_Test
version: "0.1.0"
description: "Detect clinical deterioration in ICU"

signals:
  HR:
    source: "8867-4"  # LOINC for heart rate
    unit: bpm

  SBP:
    source: "8480-6"  # LOINC for systolic BP
    unit: mmHg

trends:
  tachycardia:
    expr: last(HR) > 100
    description: "Heart rate > 100 bpm"

  hr_rising:
    expr: delta(HR, 4h) > 20
    description: "Heart rate increased > 20 in 4 hours"

  hypotension:
    expr: last(SBP) < 90
    description: "Systolic BP < 90 mmHg"

  bp_falling:
    expr: delta(SBP, 4h) < -20
    description: "Systolic BP dropped > 20 in 4 hours"

logic:
  deterioration:
    expr: (tachycardia AND hr_rising) OR (hypotension AND bp_falling)
    severity: critical
    description: "ICU patient deteriorating"
"""

    def test_deteriorating_patient_triggered(self, backend, parser):
        """ICU deteriorating patient should trigger alert."""
        scenario = parser.parse_string(self.ICU_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="icu-deteriorating", reference_time=datetime.utcnow()
        )

        # This patient has:
        # HR: 75 -> 82 -> 95 -> 108 -> 120 (rising, last=120 > 100)
        # SBP: 120 -> 115 -> 105 -> 95 -> 88 (falling, last=88 < 90)
        assert result.is_triggered, "ICU deteriorating patient should trigger"
        assert "deterioration" in result.triggered_logic

    def test_normal_patient_not_triggered(self, backend, parser):
        """Normal patient should NOT trigger ICU alert."""
        scenario = parser.parse_string(self.ICU_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="normal-patient", reference_time=datetime.utcnow()
        )

        # Normal patient has stable vitals
        assert "deterioration" not in result.triggered_logic


class TestSepsisScreening:
    """Test sepsis screening against local FHIR data."""

    SEPSIS_SCENARIO = """
scenario: Sepsis_Screening_Test
version: "0.1.0"
description: "qSOFA-inspired sepsis screening"

signals:
  Temp:
    source: "8310-5"  # LOINC for body temperature
    unit: Cel

  Lactate:
    source: "2524-7"  # LOINC for lactate
    unit: mmol/L

  HR:
    source: "8867-4"  # LOINC for heart rate
    unit: bpm

trends:
  fever:
    expr: last(Temp) > 38.3
    description: "Temperature > 38.3 C (fever)"

  elevated_lactate:
    expr: last(Lactate) > 2.0
    description: "Lactate > 2 mmol/L"

  tachycardia:
    expr: last(HR) > 100
    description: "Heart rate > 100 bpm"

logic:
  sepsis_risk:
    expr: fever AND elevated_lactate AND tachycardia
    severity: critical
    description: "Sepsis risk - fever + elevated lactate + tachycardia"
"""

    def test_sepsis_patient_triggered(self, backend, parser):
        """Patient meeting sepsis criteria should trigger."""
        scenario = parser.parse_string(self.SEPSIS_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="sepsis-positive", reference_time=datetime.utcnow()
        )

        # This patient has:
        # Temp: last = 39.2 > 38.3 (True)
        # Lactate: last = 3.5 > 2.0 (True)
        # HR: last = 125 > 100 (True)
        assert result.is_triggered, "Sepsis patient should trigger"
        assert "sepsis_risk" in result.triggered_logic
        assert result.trend_results["fever"] is True
        assert result.trend_results["elevated_lactate"] is True
        assert result.trend_results["tachycardia"] is True

    def test_normal_patient_not_triggered(self, backend, parser):
        """Normal patient should NOT trigger sepsis alert."""
        scenario = parser.parse_string(self.SEPSIS_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        result = evaluator.evaluate_patient(
            patient_id="normal-patient", reference_time=datetime.utcnow()
        )

        assert result.trend_results["fever"] is False
        assert "sepsis_risk" not in result.triggered_logic


class TestCohortEvaluation:
    """Test cohort-level evaluation."""

    SIMPLE_SCENARIO = """
scenario: Cohort_Test
version: "0.1.0"

signals:
  Cr:
    source: "2160-0"

trends:
  cr_high:
    expr: last(Cr) > 1.5

logic:
  alert:
    expr: cr_high
"""

    def test_evaluate_all_patients(self, backend, parser):
        """Evaluate scenario across all test patients."""
        scenario = parser.parse_string(self.SIMPLE_SCENARIO)
        evaluator = PSDLEvaluator(scenario, backend)

        # Get all patient IDs
        patient_ids = backend.get_patient_ids()

        # Evaluate cohort
        results = evaluator.evaluate_cohort(
            reference_time=datetime.utcnow(), patient_ids=patient_ids
        )

        assert len(results) == len(patient_ids)

        # Check results by patient
        results_by_id = {r.patient_id: r for r in results}

        # aki-triggered has high creatinine (1.8)
        if "aki-triggered" in results_by_id:
            assert results_by_id["aki-triggered"].is_triggered

        # normal-patient has low creatinine (~0.9-1.0)
        if "normal-patient" in results_by_id:
            assert not results_by_id["normal-patient"].is_triggered


class TestDataFetching:
    """Test low-level data fetching."""

    def test_fetch_creatinine_data(self, backend):
        """Test fetching creatinine observations."""
        from psdl.parser import Domain, Signal

        signal = Signal(
            name="Cr",
            source="2160-0",  # Creatinine LOINC
            domain=Domain.MEASUREMENT,
        )

        data_points = backend.fetch_signal_data(
            patient_id="aki-triggered",
            signal=signal,
            window_seconds=86400,  # 24 hours
            reference_time=datetime.utcnow(),
        )

        assert len(data_points) >= 4, "Expected at least 4 creatinine observations"

        # Verify data is sorted by timestamp
        timestamps = [dp.timestamp for dp in data_points]
        assert timestamps == sorted(timestamps), "Data should be sorted by timestamp"

        # Verify values are reasonable
        values = [dp.value for dp in data_points]
        assert all(0.5 < v < 10 for v in values), "Creatinine values should be in reasonable range"

    def test_fetch_heart_rate_data(self, backend):
        """Test fetching heart rate observations."""
        from psdl.parser import Domain, Signal

        signal = Signal(
            name="HR",
            source="8867-4",  # Heart rate LOINC
            domain=Domain.MEASUREMENT,
        )

        data_points = backend.fetch_signal_data(
            patient_id="icu-deteriorating",
            signal=signal,
            window_seconds=86400,
            reference_time=datetime.utcnow(),
        )

        assert len(data_points) >= 5, "Expected at least 5 heart rate observations"

        # Verify heart rate values are reasonable
        values = [dp.value for dp in data_points]
        assert all(40 < v < 200 for v in values), "Heart rate values should be in reasonable range"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
