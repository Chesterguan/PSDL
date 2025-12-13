"""
Tests for PSDL OMOP Backend

These tests use mocking to simulate database responses.
For integration tests with a real OMOP database, see tests/integration/

Run with: pytest tests/test_omop_backend.py -v
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# Add runtime to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from psdl.adapters.omop import OMOPBackend, OMOPConfig, create_omop_backend  # noqa: E402
from psdl.core.ir import Domain, Signal  # noqa: E402


class TestOMOPConfig:
    """Tests for OMOP configuration."""

    def test_default_config(self):
        config = OMOPConfig(connection_string="postgresql://localhost/test")
        assert config.cdm_schema == "cdm"
        assert config.vocab_schema == "cdm"
        assert config.cdm_version == "5.4"
        assert config.use_datetime is True

    def test_custom_config(self):
        config = OMOPConfig(
            connection_string="postgresql://localhost/test",
            cdm_schema="omop",
            vocab_schema="vocab",
            cdm_version="5.3",
            use_datetime=False,
        )
        assert config.cdm_schema == "omop"
        assert config.vocab_schema == "vocab"
        assert config.cdm_version == "5.3"

    def test_invalid_version(self):
        with pytest.raises(ValueError) as exc_info:
            OMOPConfig(
                connection_string="postgresql://localhost/test",
                cdm_version="6.0",
            )
        assert "Unsupported CDM version" in str(exc_info.value)

    def test_concept_mappings(self):
        config = OMOPConfig(
            connection_string="postgresql://localhost/test",
            concept_mappings={"Cr": 3016723, "Lact": 3047181},
        )
        assert config.concept_mappings["Cr"] == 3016723


class TestOMOPBackend:
    """Tests for OMOP backend with mocked database."""

    @pytest.fixture
    def config(self):
        return OMOPConfig(
            connection_string="postgresql://localhost/test",
            cdm_schema="cdm",
        )

    @pytest.fixture
    def backend(self, config):
        return OMOPBackend(config)

    @pytest.fixture
    def creatinine_signal(self):
        return Signal(
            name="Cr",
            ref="creatinine",
            concept_id=3016723,
            unit="mg/dL",
            domain=Domain.MEASUREMENT,
        )

    def test_get_concept_id_from_signal(self, backend, creatinine_signal):
        concept_id = backend._get_concept_id(creatinine_signal)
        assert concept_id == 3016723

    def test_get_concept_id_from_config(self, config):
        config.concept_mappings["CustomSignal"] = 12345
        backend = OMOPBackend(config)

        signal = Signal(name="CustomSignal", ref="custom", concept_id=None)
        concept_id = backend._get_concept_id(signal)
        assert concept_id == 12345

    def test_get_concept_id_missing(self, backend):
        signal = Signal(name="Unknown", ref="unknown", concept_id=None)
        with pytest.raises(ValueError) as exc_info:
            backend._get_concept_id(signal)
        assert "No concept_id found" in str(exc_info.value)

    def test_get_table_name(self, backend):
        assert backend._get_table_name("measurement") == "cdm.measurement"
        assert backend._get_table_name("observation") == "cdm.observation"
        assert backend._get_table_name("condition") == "cdm.condition_occurrence"

    def test_get_datetime_column(self, backend):
        assert backend._get_datetime_column("measurement") == "measurement_datetime"
        assert backend._get_datetime_column("observation") == "observation_datetime"
        assert backend._get_datetime_column("condition") == "condition_start_datetime"

    def test_get_datetime_column_date_mode(self, config):
        config.use_datetime = False
        backend = OMOPBackend(config)
        assert backend._get_datetime_column("measurement") == "measurement_date"

    @patch.object(OMOPBackend, "_execute_query")
    def test_fetch_signal_data(self, mock_query, backend, creatinine_signal):
        """Test fetching measurement data."""
        now = datetime(2024, 1, 15, 12, 0, 0)
        mock_query.return_value = [
            {"event_datetime": now - timedelta(hours=6), "value": 1.0},
            {"event_datetime": now - timedelta(hours=3), "value": 1.2},
            {"event_datetime": now, "value": 1.5},
        ]

        data = backend.fetch_signal_data(
            patient_id=12345,
            signal=creatinine_signal,
            window_seconds=24 * 3600,
            reference_time=now,
        )

        assert len(data) == 3
        assert data[0].value == 1.0
        assert data[2].value == 1.5
        mock_query.assert_called_once()

    @patch.object(OMOPBackend, "_execute_query")
    def test_fetch_signal_data_empty(self, mock_query, backend, creatinine_signal):
        """Test fetching when no data exists."""
        mock_query.return_value = []

        data = backend.fetch_signal_data(
            patient_id=12345,
            signal=creatinine_signal,
            window_seconds=24 * 3600,
            reference_time=datetime.now(),
        )

        assert len(data) == 0

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids(self, mock_query, backend):
        """Test retrieving patient IDs."""
        mock_query.return_value = [
            {"person_id": 1},
            {"person_id": 2},
            {"person_id": 3},
        ]

        patient_ids = backend.get_patient_ids()

        assert patient_ids == [1, 2, 3]

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids_with_signal(self, mock_query, backend, creatinine_signal):
        """Test finding patients with specific signal data."""
        mock_query.return_value = [
            {"person_id": 1, "obs_count": 5},
            {"person_id": 3, "obs_count": 10},
        ]

        patient_ids = backend.get_patient_ids_with_signal(creatinine_signal, min_observations=3)

        assert patient_ids == [1, 3]


class TestPopulationFiltering:
    """Tests for population filter parsing in OMOP backend."""

    @pytest.fixture
    def config(self):
        return OMOPConfig(
            connection_string="postgresql://localhost/test",
            cdm_schema="cdm",
        )

    @pytest.fixture
    def backend(self, config):
        return OMOPBackend(config)

    def test_parse_age_criterion(self, backend):
        """Test parsing age filter criteria."""
        params = {}

        # Test age >= 18
        sql, params, idx = backend._parse_population_criterion("age >= 18", params, 0)
        assert sql is not None
        assert "EXTRACT(YEAR FROM AGE" in sql
        assert ">=" in sql
        assert params["age_0"] == 18

        # Test age < 65
        sql, params, idx = backend._parse_population_criterion("age < 65", params, idx)
        assert sql is not None
        assert "<" in sql
        assert params["age_1"] == 65

    def test_parse_gender_criterion(self, backend):
        """Test parsing gender filter criteria."""
        params = {}

        # Test male
        sql, params, idx = backend._parse_population_criterion("gender == 'M'", params, 0)
        assert sql is not None
        assert "gender_concept_id" in sql
        assert params["gender_0"] == 8507  # OMOP Male concept

        # Test female
        sql, params, idx = backend._parse_population_criterion('gender == "F"', params, idx)
        assert sql is not None
        assert params["gender_1"] == 8532  # OMOP Female concept

    def test_parse_has_condition_criterion(self, backend):
        """Test parsing condition filter criteria."""
        params = {}

        sql, params, idx = backend._parse_population_criterion(
            "has_condition(201826)", params, 0
        )  # Type 2 Diabetes
        assert sql is not None
        assert "condition_occurrence" in sql
        assert "EXISTS" in sql
        assert params["cond_0"] == 201826

    def test_parse_has_measurement_criterion(self, backend):
        """Test parsing measurement filter criteria."""
        params = {}

        sql, params, idx = backend._parse_population_criterion(
            "has_measurement(3016723)", params, 0
        )  # Creatinine
        assert sql is not None
        assert "measurement" in sql.lower()
        assert "EXISTS" in sql
        assert params["meas_0"] == 3016723

    def test_parse_has_drug_criterion(self, backend):
        """Test parsing drug filter criteria."""
        params = {}

        sql, params, idx = backend._parse_population_criterion(
            "has_drug(1332419)", params, 0
        )  # Metformin
        assert sql is not None
        assert "drug_exposure" in sql
        assert "EXISTS" in sql
        assert params["drug_0"] == 1332419

    def test_parse_visit_type_criterion(self, backend):
        """Test parsing visit type filter criteria."""
        params = {}

        # ICU visit
        sql, params, idx = backend._parse_population_criterion("visit_type == 'ICU'", params, 0)
        assert sql is not None
        assert "visit_occurrence" in sql
        assert "EXISTS" in sql
        assert params["visit_0"] == 32037  # ICU concept

        # Inpatient visit
        sql, params, idx = backend._parse_population_criterion("visit_type == 'IP'", params, idx)
        assert sql is not None
        assert params["visit_1"] == 9201  # Inpatient concept

    def test_parse_unknown_criterion_returns_none(self, backend):
        """Test that unknown criteria return None (skip gracefully)."""
        params = {}

        sql, params, idx = backend._parse_population_criterion(
            "unknown_filter == 'value'", params, 0
        )
        assert sql is None
        assert idx == 0

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids_with_include_filters(self, mock_query, backend):
        """Test get_patient_ids with inclusion criteria."""
        mock_query.return_value = [{"person_id": 1}, {"person_id": 2}]

        patient_ids = backend.get_patient_ids(population_include=["age >= 18", "gender == 'M'"])

        assert patient_ids == [1, 2]
        # Verify query was built with AND for multiple include criteria
        call_args = mock_query.call_args
        query = call_args[0][0]
        assert "WHERE" in query
        assert "AND" in query

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids_with_exclude_filters(self, mock_query, backend):
        """Test get_patient_ids with exclusion criteria."""
        mock_query.return_value = [{"person_id": 1}]

        patient_ids = backend.get_patient_ids(
            population_exclude=["has_condition(201826)"]
        )  # Exclude diabetics

        assert patient_ids == [1]
        call_args = mock_query.call_args
        query = call_args[0][0]
        assert "NOT" in query

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids_with_include_and_exclude(self, mock_query, backend):
        """Test get_patient_ids with both include and exclude criteria."""
        mock_query.return_value = [{"person_id": 1}]

        patient_ids = backend.get_patient_ids(
            population_include=["age >= 18", "has_measurement(3016723)"],
            population_exclude=["has_condition(201826)"],
        )

        assert patient_ids == [1]
        call_args = mock_query.call_args
        query = call_args[0][0]
        # Should have both inclusion AND exclusion
        assert "WHERE" in query
        assert "NOT" in query

    @patch.object(OMOPBackend, "_execute_query")
    def test_get_patient_ids_no_filters(self, mock_query, backend):
        """Test get_patient_ids without any filters returns all patients."""
        mock_query.return_value = [{"person_id": i} for i in range(1, 6)]

        patient_ids = backend.get_patient_ids()

        assert patient_ids == [1, 2, 3, 4, 5]
        call_args = mock_query.call_args
        query = call_args[0][0]
        # Should not have WHERE clause for no filters
        assert "WHERE" not in query or query.count("WHERE") == 0


class TestCreateOMOPBackend:
    """Tests for convenience function."""

    def test_create_backend(self):
        backend = create_omop_backend(
            connection_string="postgresql://localhost/test",
            cdm_schema="public",
            cdm_version="5.4",
        )

        assert isinstance(backend, OMOPBackend)
        assert backend.config.cdm_schema == "public"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
