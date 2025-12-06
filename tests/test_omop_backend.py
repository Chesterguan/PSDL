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
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime", "python"))

from backends.omop import OMOPBackend  # noqa: E402
from backends.omop import OMOPConfig  # noqa: E402
from backends.omop import create_omop_backend  # noqa: E402

from parser import Domain  # noqa: E402
from parser import Signal  # noqa: E402


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
            source="creatinine",
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

        signal = Signal(name="CustomSignal", source="custom", concept_id=None)
        concept_id = backend._get_concept_id(signal)
        assert concept_id == 12345

    def test_get_concept_id_missing(self, backend):
        signal = Signal(name="Unknown", source="unknown", concept_id=None)
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

        patient_ids = backend.get_patient_ids_with_signal(
            creatinine_signal, min_observations=3
        )

        assert patient_ids == [1, 3]


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


class TestOMOPBackendIntegration:
    """
    Integration tests that require a real OMOP database.
    These are skipped by default - run with: pytest -m integration

    Local OMOP Database Setup (Prometheno/MIMIC-IV):
    - Host: localhost
    - Port: 5434
    - Database: mimic (or omop)
    - Schema: mimiciv (OMOP CDM schema)

    Set environment variable:
        export OMOP_TEST_CONNECTION="postgresql://user:pass@localhost:5434/mimic"

    Or for default local setup:
        export OMOP_LOCAL=1
    """

    # Default local connection for Prometheno OMOP database (MIMIC-IV data)
    LOCAL_CONNECTION = "postgresql://prometheno:prometheno_dev_2024@localhost:5434/prometheno_omop"

    @pytest.fixture
    def real_backend(self):
        """Create backend with real connection if available."""
        # Check for explicit connection string
        conn_string = os.environ.get("OMOP_TEST_CONNECTION")

        # Or use local default if OMOP_LOCAL is set
        if not conn_string and os.environ.get("OMOP_LOCAL"):
            conn_string = self.LOCAL_CONNECTION

        if not conn_string:
            pytest.skip(
                "OMOP database not configured. Set OMOP_TEST_CONNECTION or OMOP_LOCAL=1"
            )

        try:
            # Use "public" schema for local Prometheno OMOP database
            # Use source values since MIMIC-IV OMOP has unmapped concepts (all concept_id=0)
            backend = create_omop_backend(
                conn_string,
                cdm_schema="public",
                use_source_values=True,
                source_value_mappings={
                    "Cr": "Creatinine",
                    "Lact": "Lactate",
                    "HR": "Heart Rate",
                    "BUN": "Urea Nitrogen",
                    "K": "Potassium",
                    "Hgb": "Hemoglobin",
                }
            )
            return backend
        except Exception as e:
            pytest.skip(f"Could not connect to OMOP database: {e}")

    @pytest.mark.integration
    def test_real_connection(self, real_backend):
        """Test actual database connection."""
        patient_ids = real_backend.get_patient_ids()
        assert isinstance(patient_ids, list)
        print(f"\nConnected to OMOP database")
        print(f"Found {len(patient_ids)} patients")

    @pytest.mark.integration
    def test_fetch_creatinine_data(self, real_backend):
        """Test fetching creatinine data from real database."""
        from runtime.python.parser import Signal, Domain

        # Get some patient IDs
        patient_ids = real_backend.get_patient_ids()
        if not patient_ids:
            pytest.skip("No patients in database")

        # Create creatinine signal
        cr_signal = Signal(
            name="Cr",
            source="creatinine",
            concept_id=3016723,  # OMOP concept for creatinine
            domain=Domain.MEASUREMENT,
            unit="mg/dL",
        )

        # MIMIC-IV data is date-shifted (years 2100-2200)
        # Use a reference time in that range
        reference_time = datetime(2180, 6, 1)

        # Fetch data for first few patients
        patients_with_data = 0
        for pid in patient_ids[:20]:
            data = real_backend.fetch_signal_data(
                patient_id=pid,
                signal=cr_signal,
                window_seconds=86400 * 365 * 10,  # 10 years
                reference_time=reference_time,
            )
            if data:
                patients_with_data += 1
                if patients_with_data == 1:
                    print(f"\n  Sample data for patient {pid}: {data[:3]}")

        print(f"\nPatients with creatinine data: {patients_with_data}/20")
        assert patients_with_data > 0  # Should find some patients with data

    @pytest.mark.integration
    def test_evaluate_aki_scenario(self, real_backend):
        """Test evaluating AKI scenario against real OMOP data."""
        from runtime.python.parser import PSDLParser
        from runtime.python.evaluator import PSDLEvaluator

        # Parse AKI scenario
        parser = PSDLParser()
        scenario = parser.parse_file("examples/aki_detection.yaml")

        # Get patients
        patient_ids = real_backend.get_patient_ids()
        if not patient_ids:
            pytest.skip("No patients in database")

        # MIMIC-IV data is date-shifted (years 2100-2200)
        reference_time = datetime(2180, 6, 1)

        # Evaluate first 50 patients
        evaluator = PSDLEvaluator(scenario, real_backend)
        triggered = 0
        evaluated = 0

        for pid in patient_ids[:50]:
            try:
                result = evaluator.evaluate_patient(
                    patient_id=pid,
                    reference_time=reference_time
                )
                evaluated += 1
                if result.is_triggered:
                    triggered += 1
            except Exception:
                pass  # Skip patients with issues

        print(f"\n=== AKI Evaluation on OMOP Database ===")
        print(f"Evaluated: {evaluated}")
        print(f"Triggered: {triggered}")
        if evaluated > 0:
            print(f"Rate: {triggered/evaluated*100:.1f}%")


class TestLocalOMOPMIMIC:
    """
    Tests specifically for local Prometheno OMOP database (MIMIC-IV data).
    Run with: OMOP_LOCAL=1 pytest tests/test_omop_backend.py -v -m integration

    Database Info:
    - Host: localhost:5434
    - Database: prometheno_omop
    - ~364K patients, ~429K measurements
    """

    LOCAL_CONNECTION = "postgresql://prometheno:prometheno_dev_2024@localhost:5434/prometheno_omop"

    @pytest.fixture
    def mimic_backend(self):
        """Connect to local MIMIC-IV OMOP database."""
        if not os.environ.get("OMOP_LOCAL"):
            pytest.skip("Set OMOP_LOCAL=1 to run local MIMIC tests")

        try:
            # Use "public" schema for local MIMIC-IV OMOP database
            # Use source values since MIMIC-IV OMOP has unmapped concepts (all concept_id=0)
            backend = create_omop_backend(
                self.LOCAL_CONNECTION,
                cdm_schema="public",
                use_source_values=True,
                source_value_mappings={
                    "Cr": "Creatinine",
                    "Lact": "Lactate",
                    "HR": "Heart Rate",
                    "BUN": "Urea Nitrogen",
                    "K": "Potassium",
                    "Hgb": "Hemoglobin",
                }
            )
            return backend
        except Exception as e:
            pytest.skip(f"Could not connect to local MIMIC: {e}")

    @pytest.mark.integration
    def test_mimic_patient_count(self, mimic_backend):
        """Verify MIMIC-IV patient count."""
        patient_ids = mimic_backend.get_patient_ids()
        print(f"\nMIMIC-IV patients: {len(patient_ids)}")
        # MIMIC-IV has ~300k+ patients
        assert len(patient_ids) > 0

    @pytest.mark.integration
    def test_mimic_measurement_concepts(self, mimic_backend):
        """Check available measurement concepts in MIMIC."""
        # Common OMOP concept IDs for ICU data
        concepts = {
            3016723: "Creatinine",
            3013682: "BUN",
            3004249: "Potassium",
            3000963: "Hemoglobin",
            3027018: "Heart Rate",
            3004249: "Sodium",
        }

        print("\n=== MIMIC-IV Measurement Concepts ===")
        for concept_id, name in concepts.items():
            # This would require a query to check if concept exists
            print(f"  {concept_id}: {name}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
