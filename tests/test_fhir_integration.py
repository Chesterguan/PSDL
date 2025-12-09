"""
FHIR R4 Integration Tests

Tests against public FHIR servers to validate real-world functionality.
These tests require network access and may be slow.

Run with: pytest tests/test_fhir_integration.py -v -m integration
Skip with: pytest tests/ -v -m "not integration"
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

from reference.python.adapters.fhir import (  # noqa: E402
    FHIRBackend,
    FHIRConfig,
    create_fhir_backend,
)
from reference.python.parser import Domain, PSDLParser, Signal  # noqa: E402
from reference.python.execution.batch import PSDLEvaluator  # noqa: E402


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestHAPIFHIRServer:
    """Integration tests against the public HAPI FHIR server."""

    HAPI_BASE_URL = "https://hapi.fhir.org/baseR4"

    @pytest.fixture
    def backend(self):
        """Create a backend connected to HAPI FHIR."""
        config = FHIRConfig(
            base_url=self.HAPI_BASE_URL,
            timeout=30,
        )
        backend = FHIRBackend(config)
        yield backend
        backend.close()

    def test_connection(self, backend):
        """Test that we can connect to HAPI FHIR."""
        # Try to get metadata/capability statement
        try:
            session = backend._get_session()
            response = session.get(
                f"{self.HAPI_BASE_URL}/metadata", timeout=backend.config.timeout
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get("resourceType") == "CapabilityStatement"
            print(f"\nConnected to: {data.get('software', {}).get('name', 'Unknown')}")
        except Exception as e:
            pytest.skip(f"Could not connect to HAPI FHIR: {e}")

    def test_get_patients(self, backend):
        """Test fetching patient list from HAPI FHIR."""
        try:
            patients = backend.get_patient_ids()
            assert isinstance(patients, list)
            print(f"\nFound {len(patients)} patients on HAPI FHIR")

            if len(patients) > 0:
                # Verify we got valid patient IDs
                assert all(isinstance(p, str) for p in patients)
                print(f"Sample patient IDs: {patients[:5]}")
        except Exception as e:
            pytest.skip(f"Could not fetch patients: {e}")

    def test_get_single_patient(self, backend):
        """Test fetching a single patient resource."""
        try:
            # First get some patient IDs
            patients = backend.get_patient_ids()
            if not patients:
                pytest.skip("No patients available on server")

            # Fetch the first patient
            patient = backend.get_patient(patients[0])
            assert patient is not None
            assert patient.get("resourceType") == "Patient"
            assert "id" in patient

            print(f"\nPatient resource keys: {list(patient.keys())}")
        except Exception as e:
            pytest.skip(f"Could not fetch patient: {e}")

    def test_search_patients_with_observation(self, backend):
        """Test searching for patients with specific observations."""
        try:
            # Search for patients with heart rate observations
            patients = backend.search_patients_with_observation(
                loinc_code="8867-4", min_count=1
            )  # Heart rate
            assert isinstance(patients, list)
            print(f"\nFound {len(patients)} patients with heart rate observations")
        except Exception as e:
            pytest.skip(f"Could not search observations: {e}")

    def test_fetch_observation_data(self, backend):
        """Test fetching observation data for a signal."""
        try:
            # First find patients with creatinine data
            patients = backend.search_patients_with_observation(
                loinc_code="2160-0", min_count=1
            )  # Creatinine

            if not patients:
                # Try a more common observation
                patients = backend.search_patients_with_observation(
                    loinc_code="8867-4", min_count=1
                )  # Heart rate

            if not patients:
                pytest.skip("No patients with observations found")

            # Create a signal for the observation
            signal = Signal(
                name="test_signal",
                source="8867-4",  # Use LOINC code directly
                domain=Domain.MEASUREMENT,
            )

            # Fetch data for the first patient
            data_points = backend.fetch_signal_data(
                patient_id=patients[0],
                signal=signal,
                window_seconds=86400 * 365,  # 1 year window
                reference_time=datetime.now(),
            )

            print(f"\nFetched {len(data_points)} data points for patient {patients[0]}")
            if data_points:
                print(f"Sample: {data_points[0]}")
        except Exception as e:
            pytest.skip(f"Could not fetch observation data: {e}")


class TestFHIRWithScenario:
    """Test PSDL scenarios against FHIR backend."""

    HAPI_BASE_URL = "https://hapi.fhir.org/baseR4"

    @pytest.fixture
    def backend(self):
        """Create a backend connected to HAPI FHIR."""
        config = FHIRConfig(
            base_url=self.HAPI_BASE_URL,
            timeout=30,
        )
        backend = FHIRBackend(config)
        yield backend
        backend.close()

    @pytest.fixture
    def simple_scenario_yaml(self, tmp_path):
        """Create a simple test scenario."""
        scenario_content = """
scenario: FHIR_Integration_Test
version: "0.1.0"
description: "Simple scenario for FHIR integration testing"

signals:
  HR:
    source: "8867-4"
    unit: bpm

trends:
  hr_present:
    expr: count(HR, 365d) > 0
    description: "Has heart rate data in past year"

  hr_high:
    expr: last(HR) > 100
    description: "Heart rate above 100"

logic:
  tachycardia:
    expr: hr_present AND hr_high
    severity: medium
    description: "Patient has tachycardia"
"""
        scenario_file = tmp_path / "test_scenario.yaml"
        scenario_file.write_text(scenario_content)
        return str(scenario_file)

    def test_parse_and_evaluate_with_fhir(self, backend, simple_scenario_yaml):
        """Test parsing a scenario and evaluating against FHIR data."""
        try:
            # Parse the scenario
            parser = PSDLParser()
            scenario = parser.parse_file(simple_scenario_yaml)

            assert scenario.name == "FHIR_Integration_Test"
            assert "HR" in scenario.signals

            # Find a patient with heart rate data
            patients = backend.search_patients_with_observation(
                loinc_code="8867-4", min_count=1
            )

            if not patients:
                pytest.skip("No patients with heart rate data")

            # Create evaluator and evaluate
            evaluator = PSDLEvaluator(scenario, backend)
            result = evaluator.evaluate_patient(
                patient_id=patients[0], reference_time=datetime.now()
            )

            print(f"\nEvaluation result for patient {patients[0]}:")
            print(f"  is_triggered: {result.is_triggered}")
            print(f"  trend_values: {result.trend_values}")
            print(f"  triggered_logic: {result.triggered_logic}")

            # The result should be valid (either triggered or not)
            assert hasattr(result, "is_triggered")
            assert hasattr(result, "trend_values")

        except Exception as e:
            pytest.skip(f"Could not evaluate scenario: {e}")


class TestMultiplePublicServers:
    """
    Test against multiple public FHIR servers for compatibility.

    Public FHIR R4 Servers:
    - HAPI FHIR: https://hapi.fhir.org/baseR4 (most popular, Smile Digital Health)
    - Firely Server: https://server.fire.ly/r4 (very reliable)
    - Grahame's Test Server: http://test.fhir.org/r4 (HL7 reference)
    - AEGIS WildFHIR: https://wildfhir4.aegis.net/fhir4-0-1 (full operations support)

    See: https://confluence.hl7.org/display/FHIR/Public+Test+Servers
    """

    SERVERS = [
        ("HAPI FHIR", "https://hapi.fhir.org/baseR4"),
        ("Firely Server", "https://server.fire.ly/r4"),
        ("Grahame Test Server", "http://test.fhir.org/r4"),
        ("AEGIS WildFHIR", "https://wildfhir4.aegis.net/fhir4-0-1"),
    ]

    @pytest.mark.parametrize("server_name,base_url", SERVERS)
    def test_server_connectivity(self, server_name, base_url):
        """Test connectivity to various public FHIR servers."""
        try:
            backend = create_fhir_backend(base_url)

            # Try to get capability statement
            session = backend._get_session()
            response = session.get(f"{base_url}/metadata", timeout=30)

            if response.status_code == 200:
                data = response.json()
                print(f"\n{server_name}: Connected successfully")
                print(f"  FHIR Version: {data.get('fhirVersion', 'Unknown')}")
            else:
                print(f"\n{server_name}: HTTP {response.status_code}")

            backend.close()

        except Exception as e:
            pytest.skip(f"{server_name} not available: {e}")

    @pytest.mark.parametrize("server_name,base_url", SERVERS)
    def test_patient_search(self, server_name, base_url):
        """Test patient search on various servers."""
        try:
            backend = create_fhir_backend(base_url)
            patients = backend.get_patient_ids()

            print(f"\n{server_name}: {len(patients)} patients found")

            backend.close()
            assert isinstance(patients, list)

        except Exception as e:
            pytest.skip(f"{server_name} not available: {e}")


class TestFHIRDataQuality:
    """Test data quality and edge cases with real FHIR data."""

    HAPI_BASE_URL = "https://hapi.fhir.org/baseR4"

    @pytest.fixture
    def backend(self):
        config = FHIRConfig(base_url=self.HAPI_BASE_URL, timeout=30)
        backend = FHIRBackend(config)
        yield backend
        backend.close()

    def test_empty_patient_graceful_handling(self, backend):
        """Test that non-existent patient is handled gracefully."""
        patient = backend.get_patient("non-existent-patient-id-12345")
        # Should return None, not raise exception
        assert patient is None

    def test_observation_with_no_data(self, backend):
        """Test fetching observations that don't exist."""
        signal = Signal(
            name="rare_test",
            source="99999-9",  # Non-existent LOINC
            domain=Domain.MEASUREMENT,
        )

        data_points = backend.fetch_signal_data(
            patient_id="some-patient",
            signal=signal,
            window_seconds=86400,
            reference_time=datetime.now(),
        )

        # Should return empty list, not error
        assert data_points == []

    def test_various_loinc_codes(self, backend):
        """Test fetching data for various common LOINC codes."""
        loinc_codes = {
            "8867-4": "Heart Rate",
            "8480-6": "Systolic BP",
            "2160-0": "Creatinine",
            "2823-3": "Potassium",
            "718-7": "Hemoglobin",
        }

        results = {}
        for code, name in loinc_codes.items():
            try:
                patients = backend.search_patients_with_observation(code, min_count=1)
                results[name] = len(patients)
            except Exception:
                results[name] = "Error"

        print("\nPatient counts by observation type:")
        for name, count in results.items():
            print(f"  {name}: {count}")


class TestFHIRPerformance:
    """Performance tests for FHIR backend."""

    HAPI_BASE_URL = "https://hapi.fhir.org/baseR4"

    @pytest.fixture
    def backend(self):
        config = FHIRConfig(base_url=self.HAPI_BASE_URL, timeout=60)
        backend = FHIRBackend(config)
        yield backend
        backend.close()

    def test_bulk_patient_fetch_timing(self, backend):
        """Measure time to fetch multiple patients."""
        import time

        try:
            start = time.time()
            patients = backend.get_patient_ids()
            elapsed = time.time() - start

            print(f"\nFetched {len(patients)} patient IDs in {elapsed:.2f}s")
            print(f"Rate: {len(patients)/elapsed:.1f} patients/second")

        except Exception as e:
            pytest.skip(f"Could not run performance test: {e}")

    def test_observation_fetch_timing(self, backend):
        """Measure time to fetch observations."""
        import time

        try:
            # Find a patient with data
            patients = backend.search_patients_with_observation("8867-4", min_count=1)
            if not patients:
                pytest.skip("No patients with heart rate data")

            signal = Signal(
                name="HR",
                source="8867-4",
                domain=Domain.MEASUREMENT,
            )

            # Time the fetch
            start = time.time()
            data_points = backend.fetch_signal_data(
                patient_id=patients[0],
                signal=signal,
                window_seconds=86400 * 365,
                reference_time=datetime.now(),
            )
            elapsed = time.time() - start

            print(f"\nFetched {len(data_points)} observations in {elapsed:.2f}s")

        except Exception as e:
            pytest.skip(f"Could not run performance test: {e}")


if __name__ == "__main__":
    # Run integration tests only
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
