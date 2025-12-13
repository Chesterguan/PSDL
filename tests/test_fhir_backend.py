"""
Tests for FHIR R4 Backend

Tests the FHIR backend connector for PSDL using mocks.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from psdl.adapters.fhir import (  # noqa: E402
    DOMAIN_RESOURCE_MAP,
    LOINC_CODES,
    REQUESTS_AVAILABLE,
    FHIRBackend,
    FHIRConfig,
    FHIRResourceType,
    create_fhir_backend,
)
from psdl.core.ir import Domain, Signal  # noqa: E402

# Skip tests that require requests if not available
requires_requests = pytest.mark.skipif(
    not REQUESTS_AVAILABLE, reason="requests library not installed"
)


class TestFHIRConfig:
    """Tests for FHIRConfig dataclass."""

    def test_basic_config(self):
        """Test basic configuration."""
        config = FHIRConfig(base_url="https://fhir.example.org/r4")
        assert config.base_url == "https://fhir.example.org/r4"
        assert config.auth_token is None
        assert config.auth_type == "bearer"
        assert config.timeout == 30
        assert config.verify_ssl is True

    def test_trailing_slash_removed(self):
        """Test that trailing slash is removed from base_url."""
        config = FHIRConfig(base_url="https://fhir.example.org/r4/")
        assert config.base_url == "https://fhir.example.org/r4"

    def test_full_config(self):
        """Test full configuration with all options."""
        config = FHIRConfig(
            base_url="https://fhir.example.org/r4",
            auth_token="my-token",
            auth_type="bearer",
            timeout=60,
            verify_ssl=False,
            headers={"X-Custom": "value"},
            loinc_mappings={"my_signal": "12345-6"},
        )
        assert config.auth_token == "my-token"
        assert config.timeout == 60
        assert config.verify_ssl is False
        assert config.headers == {"X-Custom": "value"}
        assert config.loinc_mappings == {"my_signal": "12345-6"}


class TestFHIRResourceMapping:
    """Tests for FHIR resource type mappings."""

    def test_domain_resource_map(self):
        """Test domain to FHIR resource mapping."""
        assert DOMAIN_RESOURCE_MAP["measurement"] == FHIRResourceType.OBSERVATION
        assert DOMAIN_RESOURCE_MAP["observation"] == FHIRResourceType.OBSERVATION
        assert DOMAIN_RESOURCE_MAP["condition"] == FHIRResourceType.CONDITION
        assert DOMAIN_RESOURCE_MAP["drug"] == FHIRResourceType.MEDICATION_ADMINISTRATION
        assert DOMAIN_RESOURCE_MAP["procedure"] == FHIRResourceType.PROCEDURE

    def test_loinc_codes(self):
        """Test common LOINC code mappings."""
        assert LOINC_CODES["creatinine"] == "2160-0"
        assert LOINC_CODES["lactate"] == "2524-7"
        assert LOINC_CODES["heart_rate"] == "8867-4"
        assert LOINC_CODES["oxygen_saturation"] == "2708-6"


class TestFHIRBackend:
    """Tests for FHIRBackend."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return FHIRConfig(
            base_url="https://fhir.test.org/r4",
            auth_token="test-token",
        )

    @pytest.fixture
    def backend(self, config):
        """Create a test backend."""
        return FHIRBackend(config)

    def test_initialization(self, backend, config):
        """Test backend initialization."""
        assert backend.config == config
        assert backend._session is None

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_session_creation(self, mock_requests, backend):
        """Test HTTP session creation with authentication."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        session = backend._get_session()

        assert session == mock_session
        mock_session.headers.update.assert_called()

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_session_bearer_auth(self, mock_requests, config):
        """Test bearer token authentication."""
        mock_session = MagicMock()
        mock_session.headers = {}
        mock_requests.Session.return_value = mock_session

        backend = FHIRBackend(config)
        backend._get_session()

        # Check that Authorization header was set
        assert "Authorization" in mock_session.headers

    def test_get_loinc_code_from_mappings(self, config):
        """Test LOINC code lookup from config mappings."""
        config.loinc_mappings = {"custom_signal": "99999-9"}
        backend = FHIRBackend(config)

        signal = Signal(
            name="custom_signal",
            ref="custom",
            domain=Domain.MEASUREMENT,
        )

        code = backend._get_loinc_code(signal)
        assert code == "99999-9"

    def test_get_loinc_code_from_source(self, backend):
        """Test LOINC code lookup from signal source."""
        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )

        code = backend._get_loinc_code(signal)
        assert code == "2160-0"

    def test_get_loinc_code_direct(self, backend):
        """Test LOINC code when source is already a LOINC code."""
        signal = Signal(
            name="custom",
            ref="12345-6",
            domain=Domain.MEASUREMENT,
        )

        code = backend._get_loinc_code(signal)
        assert code == "12345-6"

    def test_parse_datetime_iso(self, backend):
        """Test parsing ISO datetime strings."""
        dt = backend._parse_datetime("2024-01-15T10:30:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30

    def test_parse_datetime_date_only(self, backend):
        """Test parsing date-only strings."""
        dt = backend._parse_datetime("2024-01-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_datetime_invalid(self, backend):
        """Test parsing invalid datetime."""
        dt = backend._parse_datetime("not-a-date")
        assert dt is None

    def test_parse_datetime_empty(self, backend):
        """Test parsing empty string."""
        dt = backend._parse_datetime("")
        assert dt is None

    def test_extract_observation_value_quantity(self, backend):
        """Test extracting value from valueQuantity."""
        observation = {
            "resourceType": "Observation",
            "valueQuantity": {"value": 1.5, "unit": "mg/dL"},
        }

        value = backend._extract_observation_value(observation)
        assert value == 1.5

    def test_extract_observation_value_integer(self, backend):
        """Test extracting value from valueInteger."""
        observation = {
            "resourceType": "Observation",
            "valueInteger": 42,
        }

        value = backend._extract_observation_value(observation)
        assert value == 42.0

    def test_extract_observation_value_string(self, backend):
        """Test extracting numeric value from valueString."""
        observation = {
            "resourceType": "Observation",
            "valueString": "1.23",
        }

        value = backend._extract_observation_value(observation)
        assert value == 1.23

    def test_extract_observation_value_component(self, backend):
        """Test extracting value from component (e.g., blood pressure)."""
        observation = {
            "resourceType": "Observation",
            "component": [
                {"code": {"text": "systolic"}, "valueQuantity": {"value": 120}},
                {"code": {"text": "diastolic"}, "valueQuantity": {"value": 80}},
            ],
        }

        value = backend._extract_observation_value(observation)
        assert value == 120  # Returns first component

    def test_extract_observation_datetime(self, backend):
        """Test extracting datetime from effectiveDateTime."""
        observation = {
            "resourceType": "Observation",
            "effectiveDateTime": "2024-01-15T10:30:00Z",
        }

        dt = backend._extract_observation_datetime(observation)
        assert dt is not None
        assert dt.year == 2024

    def test_extract_observation_datetime_period(self, backend):
        """Test extracting datetime from effectivePeriod."""
        observation = {
            "resourceType": "Observation",
            "effectivePeriod": {
                "start": "2024-01-15T10:00:00Z",
                "end": "2024-01-15T11:00:00Z",
            },
        }

        dt = backend._extract_observation_datetime(observation)
        assert dt is not None
        assert dt.hour == 10

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_fetch_signal_data(self, mock_requests, backend):
        """Test fetching signal data from FHIR server."""
        # Mock session and response
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "effectiveDateTime": "2024-01-15T10:00:00Z",
                        "valueQuantity": {"value": 1.2, "unit": "mg/dL"},
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "effectiveDateTime": "2024-01-15T12:00:00Z",
                        "valueQuantity": {"value": 1.5, "unit": "mg/dL"},
                    }
                },
            ],
        }
        mock_session.get.return_value = mock_response

        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )

        reference_time = datetime(2024, 1, 15, 14, 0, 0)
        data_points = backend.fetch_signal_data(
            patient_id="patient-123",
            signal=signal,
            window_seconds=86400,  # 24 hours
            reference_time=reference_time,
        )

        assert len(data_points) == 2
        assert data_points[0].value == 1.2
        assert data_points[1].value == 1.5

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_fetch_signal_data_empty_bundle(self, mock_requests, backend):
        """Test handling empty bundle response."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Bundle",
            "entry": [],
        }
        mock_session.get.return_value = mock_response

        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )

        data_points = backend.fetch_signal_data(
            patient_id="patient-123",
            signal=signal,
            window_seconds=86400,
            reference_time=datetime.now(),
        )

        assert len(data_points) == 0

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_fetch_signal_data_request_error(self, mock_requests, backend):
        """Test handling request errors gracefully."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session
        mock_session.get.side_effect = Exception("Connection error")

        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )

        data_points = backend.fetch_signal_data(
            patient_id="patient-123",
            signal=signal,
            window_seconds=86400,
            reference_time=datetime.now(),
        )

        # Should return empty list on error
        assert len(data_points) == 0

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_get_patient_ids(self, mock_requests, backend):
        """Test fetching patient IDs."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {"resource": {"id": "patient-1"}},
                {"resource": {"id": "patient-2"}},
                {"resource": {"id": "patient-3"}},
            ],
            "link": [],
        }
        mock_session.get.return_value = mock_response

        patient_ids = backend.get_patient_ids()

        assert len(patient_ids) == 3
        assert "patient-1" in patient_ids
        assert "patient-2" in patient_ids

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_get_patient(self, mock_requests, backend):
        """Test fetching single patient."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Patient",
            "id": "patient-123",
            "name": [{"given": ["John"], "family": "Doe"}],
        }
        mock_session.get.return_value = mock_response

        patient = backend.get_patient("patient-123")

        assert patient is not None
        assert patient["id"] == "patient-123"

    def test_close(self, backend):
        """Test closing the backend."""
        backend._session = MagicMock()
        backend.close()
        assert backend._session is None


class TestCreateFHIRBackend:
    """Tests for convenience function."""

    def test_create_fhir_backend(self):
        """Test creating FHIR backend with convenience function."""
        backend = create_fhir_backend(
            base_url="https://fhir.example.org/r4",
            auth_token="my-token",
        )

        assert isinstance(backend, FHIRBackend)
        assert backend.config.base_url == "https://fhir.example.org/r4"
        assert backend.config.auth_token == "my-token"

    def test_create_fhir_backend_no_auth(self):
        """Test creating FHIR backend without authentication."""
        backend = create_fhir_backend(
            base_url="https://fhir.example.org/r4",
        )

        assert isinstance(backend, FHIRBackend)
        assert backend.config.auth_token is None


class TestMappingProviderIntegration:
    """Tests for MappingProvider integration with FHIR backend."""

    def test_get_loinc_code_from_mapping_provider(self):
        """Test LOINC code lookup from MappingProvider."""
        from psdl.mapping import MappingProvider, SignalMapping

        mapping = MappingProvider(
            institution="Test Hospital",
            signals={
                "creatinine": SignalMapping(loinc_code="2160-0"),
                "custom_signal": SignalMapping(loinc_code="99999-9"),
            },
        )

        config = FHIRConfig(base_url="https://fhir.test.org/r4")
        backend = FHIRBackend(config, mapping=mapping)

        # Test lookup from mapping
        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )
        code = backend._get_loinc_code(signal)
        assert code == "2160-0"

        # Test custom signal
        signal2 = Signal(
            name="custom",
            ref="custom_signal",
            domain=Domain.MEASUREMENT,
        )
        code2 = backend._get_loinc_code(signal2)
        assert code2 == "99999-9"

    def test_mapping_provider_priority_over_config(self):
        """Test that MappingProvider takes priority over config.loinc_mappings."""
        from psdl.mapping import MappingProvider, SignalMapping

        mapping = MappingProvider(
            institution="Test Hospital",
            signals={
                "creatinine": SignalMapping(loinc_code="11111-1"),  # Different code
            },
        )

        config = FHIRConfig(
            base_url="https://fhir.test.org/r4",
            loinc_mappings={"creatinine": "22222-2"},  # Config override (lower priority)
        )
        backend = FHIRBackend(config, mapping=mapping)

        signal = Signal(
            name="Cr",
            ref="creatinine",
            domain=Domain.MEASUREMENT,
        )

        # Should use MappingProvider code, not config override
        code = backend._get_loinc_code(signal)
        assert code == "11111-1"

    def test_fallback_to_config_when_not_in_mapping(self):
        """Test fallback to config when signal not in MappingProvider."""
        from psdl.mapping import MappingProvider, SignalMapping

        mapping = MappingProvider(
            institution="Test Hospital",
            signals={
                "creatinine": SignalMapping(loinc_code="2160-0"),
            },
        )

        # Config loinc_mappings is keyed by signal.name (not source)
        config = FHIRConfig(
            base_url="https://fhir.test.org/r4",
            loinc_mappings={"other": "33333-3"},  # keyed by signal name
        )
        backend = FHIRBackend(config, mapping=mapping)

        signal = Signal(
            name="other",
            ref="other_signal",
            domain=Domain.MEASUREMENT,
        )

        # Should fall back to config since not in mapping
        code = backend._get_loinc_code(signal)
        assert code == "33333-3"


class TestConditionHandling:
    """Tests for Condition resource handling."""

    @pytest.fixture
    def backend(self):
        config = FHIRConfig(base_url="https://fhir.test.org/r4")
        return FHIRBackend(config)

    @requires_requests
    @patch("psdl.adapters.fhir.requests")
    def test_fetch_condition_data(self, mock_requests, backend):
        """Test fetching condition data."""
        mock_session = MagicMock()
        mock_requests.Session.return_value = mock_session

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "onsetDateTime": "2024-01-10T08:00:00Z",
                        "code": {
                            "coding": [{"system": "http://snomed.info/sct", "code": "123456"}]
                        },
                    }
                },
            ],
        }
        mock_session.get.return_value = mock_response

        signal = Signal(
            name="diabetes",
            ref="diabetes_condition",
            domain=Domain.CONDITION,
        )

        data_points = backend.fetch_signal_data(
            patient_id="patient-123",
            signal=signal,
            window_seconds=86400 * 365,  # 1 year
            reference_time=datetime(2024, 1, 15, 12, 0, 0),
        )

        assert len(data_points) == 1
        assert data_points[0].value == 1.0  # Condition presence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
