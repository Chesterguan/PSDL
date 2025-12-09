"""
PSDL OMOP CDM Backend

Connects PSDL to OMOP Common Data Model databases.
Supports OMOP CDM v5.4 (recommended) and v5.3.

Reference: https://ohdsi.github.io/CommonDataModel/cdm54.html

Usage:
    from psdl.backends import OMOPBackend, OMOPConfig

    config = OMOPConfig(
        connection_string="postgresql://user:pass@host/db",
        cdm_schema="cdm",
        cdm_version="5.4"
    )
    backend = OMOPBackend(config)

    evaluator = PSDLEvaluator(scenario, backend)
    result = evaluator.evaluate_patient(patient_id=12345)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from ..execution.batch import DataBackend
    from ..operators import DataPoint
    from ..parser import Signal
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from execution.batch import DataBackend

    from operators import DataPoint
    from parser import Signal


class CDMVersion(Enum):
    """Supported OMOP CDM versions."""

    V5_3 = "5.3"
    V5_4 = "5.4"


class OMOPDomain(Enum):
    """OMOP CDM domain tables."""

    MEASUREMENT = "measurement"
    OBSERVATION = "observation"
    CONDITION = "condition_occurrence"
    DRUG = "drug_exposure"
    PROCEDURE = "procedure_occurrence"
    DEVICE = "device_exposure"
    VISIT = "visit_occurrence"


# Mapping from PSDL domain names to OMOP tables
DOMAIN_TABLE_MAP = {
    "measurement": "measurement",
    "observation": "observation",
    "condition": "condition_occurrence",
    "drug": "drug_exposure",
    "procedure": "procedure_occurrence",
}


@dataclass
class OMOPConfig:
    """
    Configuration for OMOP CDM backend.

    Args:
        connection_string: Database connection string
            - PostgreSQL: "postgresql://user:pass@host:5432/dbname"
            - SQL Server: "mssql+pyodbc://user:pass@host/dbname?driver=..."
            - SQLite: "sqlite:///path/to/database.db"
        cdm_schema: Schema name containing CDM tables (default: "cdm")
        vocab_schema: Schema name containing vocabulary tables (default: same as cdm_schema)
        cdm_version: CDM version - "5.3" or "5.4" (default: "5.4")
        use_datetime: Use datetime fields instead of date fields (default: True)
        use_source_values: Use source_value instead of concept_id for lookups (default: False)
            Useful for OMOP databases with unmapped concepts
    """

    connection_string: str
    cdm_schema: str = "cdm"
    vocab_schema: Optional[str] = None
    cdm_version: str = "5.4"
    use_datetime: bool = True
    use_source_values: bool = False
    # Optional concept ID overrides for signals
    concept_mappings: Dict[str, int] = field(default_factory=dict)
    # Optional source value overrides for signals (when use_source_values=True)
    source_value_mappings: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.vocab_schema is None:
            self.vocab_schema = self.cdm_schema
        if self.cdm_version not in ["5.3", "5.4"]:
            raise ValueError(f"Unsupported CDM version: {self.cdm_version}. Use '5.3' or '5.4'")


class OMOPBackend(DataBackend):
    """
    OMOP CDM data backend for PSDL.

    Fetches clinical data from OMOP CDM databases and converts
    to PSDL DataPoint format for evaluation.

    Supports:
    - Measurements (labs, vitals)
    - Observations
    - Conditions (for presence/absence checks)
    - Multiple database engines via SQLAlchemy

    Example:
        config = OMOPConfig(
            connection_string="postgresql://localhost/synthea",
            cdm_schema="public"
        )
        backend = OMOPBackend(config)

        # Use with PSDL evaluator
        evaluator = PSDLEvaluator(scenario, backend)
        results = evaluator.evaluate_cohort()
    """

    def __init__(self, config: OMOPConfig):
        """
        Initialize OMOP backend with configuration.

        Args:
            config: OMOPConfig with connection details
        """
        self.config = config
        self._engine = None
        self._connection = None

    def _get_engine(self):
        """Lazy initialization of database engine."""
        if self._engine is None:
            try:
                from sqlalchemy import create_engine

                self._engine = create_engine(self.config.connection_string)
            except ImportError:
                raise ImportError("SQLAlchemy is required for OMOP backend. " "Install with: pip install sqlalchemy")
        return self._engine

    def _execute_query(self, query: str, params: Dict[str, Any]) -> List[Dict]:
        """Execute SQL query and return results as list of dicts."""
        engine = self._get_engine()
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                result = conn.execute(text(query), params)
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
        except Exception as e:
            raise RuntimeError(f"Query execution failed: {e}")

    def _get_table_name(self, domain: str) -> str:
        """Get fully qualified table name for a domain."""
        table = DOMAIN_TABLE_MAP.get(domain, "measurement")
        return f"{self.config.cdm_schema}.{table}"

    def _get_datetime_column(self, domain: str) -> str:
        """Get the appropriate datetime column based on domain and config."""
        if domain == "measurement":
            return "measurement_datetime" if self.config.use_datetime else "measurement_date"
        elif domain == "observation":
            return "observation_datetime" if self.config.use_datetime else "observation_date"
        elif domain == "condition":
            return "condition_start_datetime" if self.config.use_datetime else "condition_start_date"
        elif domain == "drug":
            return "drug_exposure_start_datetime" if self.config.use_datetime else "drug_exposure_start_date"
        elif domain == "procedure":
            return "procedure_datetime" if self.config.use_datetime else "procedure_date"
        return "measurement_datetime"

    def _get_value_column(self, domain: str) -> str:
        """Get the value column for a domain."""
        if domain == "measurement":
            return "value_as_number"
        elif domain == "observation":
            return "value_as_number"
        # For other domains, we might check presence (1.0) or absence (0.0)
        return "1.0"

    def _get_concept_id(self, signal: Signal) -> int:
        """
        Get the concept_id for a signal.

        Priority:
        1. Config-level concept_mappings override
        2. Signal's concept_id field
        3. Raise error if not found
        """
        # Check config overrides first
        if signal.name in self.config.concept_mappings:
            return self.config.concept_mappings[signal.name]

        # Use signal's concept_id
        if signal.concept_id is not None:
            return signal.concept_id

        raise ValueError(
            f"No concept_id found for signal '{signal.name}'. "
            f"Either set concept_id in the scenario or add to config.concept_mappings"
        )

    def _get_source_value(self, signal: Signal) -> str:
        """
        Get the source_value for a signal when using source value lookups.

        Priority:
        1. Config-level source_value_mappings override
        2. Signal's source field
        3. Signal's name as fallback
        """
        # Check config overrides first
        if signal.name in self.config.source_value_mappings:
            return self.config.source_value_mappings[signal.name]

        # Use signal's source field
        if signal.source is not None:
            return signal.source

        # Use signal name as fallback
        return signal.name

    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """
        Fetch time-series data for a signal from OMOP CDM.

        Args:
            patient_id: OMOP person_id
            signal: Signal definition with concept_id
            window_seconds: How far back to fetch
            reference_time: End of the time window

        Returns:
            List of DataPoints sorted by timestamp (ascending)
        """
        domain = signal.domain.value if signal.domain else "measurement"
        table = self._get_table_name(domain)
        datetime_col = self._get_datetime_column(domain)
        value_col = self._get_value_column(domain)

        window_start = reference_time - timedelta(seconds=window_seconds)

        # Build query based on domain and whether to use source values
        if self.config.use_source_values:
            source_value = self._get_source_value(signal)
            if domain in ["measurement", "observation"]:
                query = f"""
                    SELECT
                        {datetime_col} as event_datetime,
                        {value_col} as value
                    FROM {table}
                    WHERE person_id = :person_id
                      AND {domain}_source_value = :source_value
                      AND {datetime_col} >= :window_start
                      AND {datetime_col} <= :reference_time
                      AND {value_col} IS NOT NULL
                    ORDER BY {datetime_col} ASC
                """
            else:
                query = f"""
                    SELECT
                        {datetime_col} as event_datetime,
                        1.0 as value
                    FROM {table}
                    WHERE person_id = :person_id
                      AND {domain.split('_')[0]}_source_value = :source_value
                      AND {datetime_col} >= :window_start
                      AND {datetime_col} <= :reference_time
                    ORDER BY {datetime_col} ASC
                """
            params = {
                "person_id": patient_id,
                "source_value": source_value,
                "window_start": window_start,
                "reference_time": reference_time,
            }
        else:
            concept_id = self._get_concept_id(signal)
            if domain in ["measurement", "observation"]:
                query = f"""
                    SELECT
                        {datetime_col} as event_datetime,
                        {value_col} as value
                    FROM {table}
                    WHERE person_id = :person_id
                      AND {domain}_concept_id = :concept_id
                      AND {datetime_col} >= :window_start
                      AND {datetime_col} <= :reference_time
                      AND {value_col} IS NOT NULL
                    ORDER BY {datetime_col} ASC
                """
            else:
                # For conditions/drugs/procedures, we return presence as 1.0
                query = f"""
                    SELECT
                        {datetime_col} as event_datetime,
                        1.0 as value
                    FROM {table}
                    WHERE person_id = :person_id
                      AND {domain.split('_')[0]}_concept_id = :concept_id
                      AND {datetime_col} >= :window_start
                      AND {datetime_col} <= :reference_time
                    ORDER BY {datetime_col} ASC
                """
            params = {
                "person_id": patient_id,
                "concept_id": concept_id,
                "window_start": window_start,
                "reference_time": reference_time,
            }

        rows = self._execute_query(query, params)

        # Convert to DataPoints
        data_points = []
        for row in rows:
            if row["event_datetime"] and row["value"] is not None:
                data_points.append(
                    DataPoint(
                        timestamp=row["event_datetime"],
                        value=float(row["value"]),
                    )
                )

        return data_points

    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Get patient IDs matching population criteria.

        Note: Population filter parsing is not yet implemented.
        Currently returns all person_ids from the person table.

        Args:
            population_include: Inclusion criteria (not yet implemented)
            population_exclude: Exclusion criteria (not yet implemented)

        Returns:
            List of person_ids
        """
        # TODO: Implement population filter parsing
        # For now, return all patients
        query = f"""
            SELECT person_id
            FROM {self.config.cdm_schema}.person
            ORDER BY person_id
        """

        rows = self._execute_query(query, {})
        return [row["person_id"] for row in rows]

    def get_patient_ids_with_signal(
        self,
        signal: Signal,
        min_observations: int = 1,
    ) -> List[Any]:
        """
        Get patient IDs who have at least N observations of a signal.

        Useful for research cohort identification.

        Args:
            signal: Signal to check for
            min_observations: Minimum number of observations required

        Returns:
            List of person_ids with sufficient data
        """
        domain = signal.domain.value if signal.domain else "measurement"
        table = self._get_table_name(domain)

        if self.config.use_source_values:
            source_value = self._get_source_value(signal)
            query = f"""
                SELECT person_id, COUNT(*) as obs_count
                FROM {table}
                WHERE {domain}_source_value = :source_value
                GROUP BY person_id
                HAVING COUNT(*) >= :min_obs
                ORDER BY person_id
            """
            params = {"source_value": source_value, "min_obs": min_observations}
        else:
            concept_id = self._get_concept_id(signal)
            query = f"""
                SELECT person_id, COUNT(*) as obs_count
                FROM {table}
                WHERE {domain}_concept_id = :concept_id
                GROUP BY person_id
                HAVING COUNT(*) >= :min_obs
                ORDER BY person_id
            """
            params = {"concept_id": concept_id, "min_obs": min_observations}

        rows = self._execute_query(query, params)
        return [row["person_id"] for row in rows]

    def close(self):
        """Close database connection."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


# Convenience function for quick setup
def create_omop_backend(
    connection_string: str,
    cdm_schema: str = "cdm",
    cdm_version: str = "5.4",
    use_source_values: bool = False,
    source_value_mappings: Optional[Dict[str, str]] = None,
) -> OMOPBackend:
    """
    Create an OMOP backend with minimal configuration.

    Args:
        connection_string: Database connection string
        cdm_schema: Schema containing CDM tables
        cdm_version: CDM version ("5.3" or "5.4")
        use_source_values: Use source_value instead of concept_id (for unmapped data)
        source_value_mappings: Map signal names to source values

    Returns:
        Configured OMOPBackend instance

    Example:
        # Standard OMOP with mapped concepts
        backend = create_omop_backend(
            "postgresql://user:pass@localhost/synthea",
            cdm_schema="public"
        )

        # OMOP with unmapped concepts (use source values)
        backend = create_omop_backend(
            "postgresql://user:pass@localhost/mimic",
            cdm_schema="public",
            use_source_values=True,
            source_value_mappings={"Cr": "Creatinine", "Lact": "Lactate"}
        )
    """
    config = OMOPConfig(
        connection_string=connection_string,
        cdm_schema=cdm_schema,
        cdm_version=cdm_version,
        use_source_values=use_source_values,
        source_value_mappings=source_value_mappings or {},
    )
    return OMOPBackend(config)
