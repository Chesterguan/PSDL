"""
PSDL OMOP CDM Backend

Connects PSDL to OMOP Common Data Model databases.
Supports OMOP CDM v5.4 (recommended) and v5.3.

Reference: https://ohdsi.github.io/CommonDataModel/cdm54.html

Architecture (RFC-0004):
    PSDL uses a three-layer architecture:

    - Scenario: Defines WHAT to detect (clinical logic)
    - DatasetSpec: Defines WHERE to find data (physical bindings)
    - Adapter: Defines HOW to execute (SQL generation)

    This separation enables:
    - Portable scenarios that work across institutions
    - Auditable data bindings in versioned YAML files
    - Easy testing with different datasets

Usage with DatasetSpec (Recommended - RFC-0004):
    from psdl import load_dataset_spec
    from psdl.adapters.omop import OMOPBackend, OMOPConfig

    # Load dataset specification
    spec = load_dataset_spec("dataset_specs/mimic_iv_omop.yaml")

    # Create adapter with dataset spec
    config = OMOPConfig(connection_string="postgresql://user:pass@host/db")
    backend = OMOPBackend(config, dataset_spec=spec)

    # Run portable scenario
    evaluator = PSDLEvaluator(scenario, backend)
    result = evaluator.evaluate_patient(patient_id=12345)

Legacy Usage (MappingProvider):
    from psdl.mapping import load_mapping

    mapping = load_mapping("mappings/mimic_iv.yaml")
    config = OMOPConfig(
        connection_string="postgresql://user:pass@host/db",
        cdm_schema="public"
    )
    backend = OMOPBackend(config, mapping=mapping)

Legacy Usage (config-level mappings):
    config = OMOPConfig(
        connection_string="postgresql://user:pass@host/db",
        cdm_schema="cdm",
        use_source_values=True,
        source_value_mappings={"Cr": "Creatinine"}
    )
    backend = OMOPBackend(config)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

if TYPE_CHECKING:
    from ..mapping import MappingProvider

from ..core.dataset import Binding, DatasetSpec, Event
from ..core.ir import Signal
from ..operators import DataPoint
from ..runtimes.single import DataBackend


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

    Example with DatasetSpec (Recommended - RFC-0004):
        from psdl import load_dataset_spec

        spec = load_dataset_spec("dataset_specs/mimic_iv_omop.yaml")
        config = OMOPConfig(connection_string="postgresql://localhost/mimic")
        backend = OMOPBackend(config, dataset_spec=spec)

        evaluator = PSDLEvaluator(scenario, backend)
        results = evaluator.evaluate_cohort()

    Example with MappingProvider (Legacy):
        from psdl.mapping import load_mapping

        mapping = load_mapping("mappings/mimic_iv.yaml")
        config = OMOPConfig(
            connection_string="postgresql://localhost/mimic",
            cdm_schema="public"
        )
        backend = OMOPBackend(config, mapping=mapping)
    """

    def __init__(
        self,
        config: OMOPConfig,
        dataset_spec: Optional[DatasetSpec] = None,
        mapping: Optional["MappingProvider"] = None,
    ):
        """
        Initialize OMOP backend with configuration and optional bindings.

        Args:
            config: OMOPConfig with connection details
            dataset_spec: DatasetSpec for signal-to-physical bindings (recommended).
                         Takes highest precedence when provided.
            mapping: Optional MappingProvider for signal-to-terminology translation.
                    If provided, takes precedence over config mappings.
        """
        self.config = config
        self.dataset_spec = dataset_spec
        self.mapping = mapping
        self._engine = None
        self._connection = None

        # If dataset_spec provided, use its conventions
        if dataset_spec is not None:
            if dataset_spec.conventions.schema:
                self.config.cdm_schema = dataset_spec.conventions.schema

        # If mapping provided, update config settings
        if mapping is not None:
            if mapping.use_source_values:
                self.config.use_source_values = True

    def _get_engine(self):
        """Lazy initialization of database engine."""
        if self._engine is None:
            try:
                from sqlalchemy import create_engine

                self._engine = create_engine(self.config.connection_string)
            except ImportError:
                raise ImportError(
                    "SQLAlchemy is required for OMOP backend. "
                    "Install with: pip install sqlalchemy"
                )
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
            return (
                "condition_start_datetime" if self.config.use_datetime else "condition_start_date"
            )
        elif domain == "drug":
            return (
                "drug_exposure_start_datetime"
                if self.config.use_datetime
                else "drug_exposure_start_date"
            )
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

    def resolve_binding(self, signal_ref: str) -> Optional[Binding]:
        """
        Resolve a semantic reference to a physical binding (RFC-0004 interface).

        Args:
            signal_ref: Semantic reference name (e.g., "creatinine")

        Returns:
            Binding object if dataset_spec is available, None otherwise
        """
        if self.dataset_spec is not None:
            try:
                return self.dataset_spec.resolve(signal_ref)
            except Exception:
                return None
        return None

    def fetch_events(
        self,
        binding: Binding,
        patient_ids: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> Iterator[Event]:
        """
        Fetch events from data source using a resolved binding (RFC-0004 interface).

        Args:
            binding: Resolved physical binding
            patient_ids: Optional list of patient IDs to filter
            time_range: Optional (start, end) datetime tuple

        Yields:
            Event objects in canonical format
        """
        # Build query from binding
        query_parts = [
            f"SELECT {binding.patient_field} as patient_id,",
            f"       {binding.time_field} as event_time,",
            f"       {binding.value_field} as value",
            f"FROM {binding.table}",
            f"WHERE {binding.filter_expr}",
        ]

        params: Dict[str, Any] = {}

        if patient_ids:
            query_parts.append("AND patient_id IN :patient_ids")
            params["patient_ids"] = tuple(patient_ids)

        if time_range:
            query_parts.append(f"AND {binding.time_field} >= :start_time")
            query_parts.append(f"AND {binding.time_field} <= :end_time")
            params["start_time"] = time_range[0]
            params["end_time"] = time_range[1]

        query_parts.append(f"ORDER BY {binding.patient_field}, {binding.time_field}")

        query = "\n".join(query_parts)
        rows = self._execute_query(query, params)

        for row in rows:
            if row["event_time"] and row["value"] is not None:
                yield Event(
                    patient_id=str(row["patient_id"]),
                    timestamp=row["event_time"],
                    signal_ref="",  # Caller should set this
                    value=float(row["value"]) if binding.value_type == "numeric" else row["value"],
                    unit=binding.unit,
                )

    def _get_concept_id(self, signal: Signal) -> int:
        """
        Get the concept_id for a signal.

        Priority:
        1. DatasetSpec (if provided) - RFC-0004
        2. MappingProvider (if provided)
        3. Config-level concept_mappings override
        4. Signal's concept_id field
        5. Raise error if not found
        """
        # Check DatasetSpec first (RFC-0004 recommended approach)
        if self.dataset_spec is not None:
            signal_ref = signal.source or signal.name
            if signal_ref in self.dataset_spec.elements:
                elem = self.dataset_spec.elements[signal_ref]
                if elem.filter and elem.filter.concept_id is not None:
                    cid = elem.filter.concept_id
                    return cid[0] if isinstance(cid, list) else cid

        # Check MappingProvider (legacy approach)
        if self.mapping is not None:
            # Try to get from mapping using signal's source (logical name)
            concept_id = self.mapping.get_concept_id(signal.source or signal.name)
            if concept_id is not None:
                return concept_id

        # Check config overrides (legacy approach)
        if signal.name in self.config.concept_mappings:
            return self.config.concept_mappings[signal.name]

        # Use signal's concept_id
        if signal.concept_id is not None:
            return signal.concept_id

        raise ValueError(
            f"No concept_id found for signal '{signal.name}'. "
            f"Provide a dataset_spec, mapping file, set concept_id in the scenario, "
            f"or add to config.concept_mappings"
        )

    def _get_source_value(self, signal: Signal) -> str:
        """
        Get the source_value for a signal when using source value lookups.

        Priority:
        1. DatasetSpec (if provided) - RFC-0004
        2. MappingProvider (if provided)
        3. Config-level source_value_mappings override
        4. Signal's source field
        5. Signal's name as fallback
        """
        # Check DatasetSpec first (RFC-0004 recommended approach)
        if self.dataset_spec is not None:
            signal_ref = signal.source or signal.name
            if signal_ref in self.dataset_spec.elements:
                elem = self.dataset_spec.elements[signal_ref]
                if elem.filter and elem.filter.source_value is not None:
                    sv = elem.filter.source_value
                    return sv[0] if isinstance(sv, list) else sv

        # Check MappingProvider (legacy approach)
        if self.mapping is not None:
            # Try to get from mapping using signal's source (logical name)
            source_value = self.mapping.get_source_value(signal.source or signal.name)
            if source_value is not None:
                return source_value

        # Check config overrides (legacy approach)
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

    def _parse_population_criterion(
        self, criterion: str, params: Dict[str, Any], param_idx: int
    ) -> Tuple[Optional[str], Dict[str, Any], int]:
        """
        Parse a single population criterion into SQL.

        Supported patterns:
        - "age >= 18" / "age < 65" - Age-based filters
        - "gender == 'M'" / "gender == 'F'" - Gender filters
        - "has_condition(concept_id)" - Has condition with concept
        - "has_measurement(concept_id)" - Has measurement with concept
        - "visit_type == 'ICU'" - Visit type filters

        Returns:
            Tuple of (sql_fragment, updated_params, next_param_idx)
            Returns (None, params, param_idx) if criterion cannot be parsed
        """
        criterion = criterion.strip()

        # Age comparisons: "age >= 18", "age < 65"
        age_pattern = re.match(r"age\s*(>=|<=|>|<|==|!=)\s*(\d+)", criterion)
        if age_pattern:
            op, value = age_pattern.groups()
            param_name = f"age_{param_idx}"
            sql = f"EXTRACT(YEAR FROM AGE(p.birth_datetime)) {op} :{param_name}"
            params[param_name] = int(value)
            return sql, params, param_idx + 1

        # Gender comparisons: "gender == 'M'" or "gender == 'F'"
        gender_pattern = re.match(r"gender\s*==\s*['\"]([MF])['\"]", criterion)
        if gender_pattern:
            gender = gender_pattern.group(1)
            param_name = f"gender_{param_idx}"
            # OMOP uses 8507 for Male, 8532 for Female
            gender_concept = 8507 if gender == "M" else 8532
            sql = f"p.gender_concept_id = :{param_name}"
            params[param_name] = gender_concept
            return sql, params, param_idx + 1

        # has_condition(concept_id): Patient has condition
        condition_pattern = re.match(r"has_condition\s*\(\s*(\d+)\s*\)", criterion)
        if condition_pattern:
            concept_id = int(condition_pattern.group(1))
            param_name = f"cond_{param_idx}"
            sql = f"""EXISTS (
                SELECT 1 FROM {self.config.cdm_schema}.condition_occurrence co
                WHERE co.person_id = p.person_id
                AND co.condition_concept_id = :{param_name}
            )"""
            params[param_name] = concept_id
            return sql, params, param_idx + 1

        # has_measurement(concept_id): Patient has measurement
        measurement_pattern = re.match(r"has_measurement\s*\(\s*(\d+)\s*\)", criterion)
        if measurement_pattern:
            concept_id = int(measurement_pattern.group(1))
            param_name = f"meas_{param_idx}"
            sql = f"""EXISTS (
                SELECT 1 FROM {self.config.cdm_schema}.measurement m
                WHERE m.person_id = p.person_id
                AND m.measurement_concept_id = :{param_name}
            )"""
            params[param_name] = concept_id
            return sql, params, param_idx + 1

        # has_drug(concept_id): Patient has drug exposure
        drug_pattern = re.match(r"has_drug\s*\(\s*(\d+)\s*\)", criterion)
        if drug_pattern:
            concept_id = int(drug_pattern.group(1))
            param_name = f"drug_{param_idx}"
            sql = f"""EXISTS (
                SELECT 1 FROM {self.config.cdm_schema}.drug_exposure de
                WHERE de.person_id = p.person_id
                AND de.drug_concept_id = :{param_name}
            )"""
            params[param_name] = concept_id
            return sql, params, param_idx + 1

        # visit_type == 'ICU' or similar
        visit_pattern = re.match(r"visit_type\s*==\s*['\"](\w+)['\"]", criterion)
        if visit_pattern:
            visit_type = visit_pattern.group(1)
            param_name = f"visit_{param_idx}"
            # Map common visit types to concept IDs
            visit_type_map = {
                "ICU": 32037,  # Intensive Care
                "ED": 9203,  # Emergency Room Visit
                "IP": 9201,  # Inpatient Visit
                "OP": 9202,  # Outpatient Visit
            }
            concept_id = visit_type_map.get(visit_type.upper())
            if concept_id:
                sql = f"""EXISTS (
                    SELECT 1 FROM {self.config.cdm_schema}.visit_occurrence vo
                    WHERE vo.person_id = p.person_id
                    AND vo.visit_concept_id = :{param_name}
                )"""
                params[param_name] = concept_id
                return sql, params, param_idx + 1

        # Criterion not recognized - log warning and skip
        return None, params, param_idx

    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Get patient IDs matching population criteria.

        Supports filtering by:
        - Age: "age >= 18", "age < 65"
        - Gender: "gender == 'M'", "gender == 'F'"
        - Conditions: "has_condition(concept_id)"
        - Measurements: "has_measurement(concept_id)"
        - Drugs: "has_drug(concept_id)"
        - Visit type: "visit_type == 'ICU'"

        Args:
            population_include: Inclusion criteria (all must match)
            population_exclude: Exclusion criteria (any excludes patient)

        Returns:
            List of person_ids matching criteria
        """
        params: Dict[str, Any] = {}
        param_idx = 0
        include_clauses: List[str] = []
        exclude_clauses: List[str] = []

        # Parse inclusion criteria
        if population_include:
            for criterion in population_include:
                sql, params, param_idx = self._parse_population_criterion(
                    criterion, params, param_idx
                )
                if sql:
                    include_clauses.append(sql)

        # Parse exclusion criteria
        if population_exclude:
            for criterion in population_exclude:
                sql, params, param_idx = self._parse_population_criterion(
                    criterion, params, param_idx
                )
                if sql:
                    exclude_clauses.append(sql)

        # Build query
        query = f"""
            SELECT p.person_id
            FROM {self.config.cdm_schema}.person p
        """

        where_parts = []

        # Add inclusion criteria (AND together)
        if include_clauses:
            where_parts.append("(" + " AND ".join(include_clauses) + ")")

        # Add exclusion criteria (NOT any)
        if exclude_clauses:
            for clause in exclude_clauses:
                where_parts.append(f"NOT ({clause})")

        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)

        query += " ORDER BY p.person_id"

        rows = self._execute_query(query, params)
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
