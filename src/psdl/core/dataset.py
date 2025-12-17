"""
PSDL Dataset Specification - Portable Data Binding Layer (RFC-0004)

Dataset Specs map semantic signal references to physical data locations,
enabling the same PSDL scenario to run across different datasets.

Architecture (RFC-0004):
    Scenario    = intent    (WHAT to detect)
    DatasetSpec = binding   (WHERE to find it)
    Adapter     = execution (HOW to run it)

Why This File is NOT Auto-Generated:
    Unlike files in `_generated/` which are produced from spec files,
    this module is manually written because:

    1. DatasetSpec is a RUNTIME LOADER - it reads user-provided YAML files
       at runtime, not at code generation time.

    2. RUNTIME VALIDATION - Validates against `spec/dataset_schema.json`
       when loading, catching errors with clear messages.

    3. NO SPEC-TO-CODE MAPPING - Unlike AST nodes (fixed structure defined
       in spec/ast-nodes.yaml), DatasetSpec loads arbitrary user content.

    See: src/psdl/_generated/README.md for codegen boundaries.

Usage:
    from psdl import load_dataset_spec

    # Load a dataset spec
    spec = load_dataset_spec("dataset_specs/mimic_iv_omop.yaml")

    # Resolve a signal reference to physical binding
    binding = spec.resolve("creatinine")
    print(binding.table)  # "measurement"
    print(binding.filter_expr)  # "concept_id IN (3016723)"

    # Use with OMOP backend
    from psdl.adapters.omop import OMOPBackend, OMOPConfig
    config = OMOPConfig(connection_string="postgresql://...")
    backend = OMOPBackend(config, dataset_spec=spec)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal, Protocol

import yaml

__all__ = [
    # Core types
    "DatasetSpec",
    "ElementSpec",
    "FilterSpec",
    "Conventions",
    "ValuesetSpec",
    "UnitConversion",
    # Adapter interface types (RFC-0004)
    "Binding",
    "Event",
    "DatasetAdapter",
    # Public API
    "load_dataset_spec",
    "validate_dataset_spec",
    # Exceptions
    "DatasetSpecError",
    "DatasetValidationError",
    "BindingResolutionError",
]


# =============================================================================
# Exceptions
# =============================================================================


class DatasetSpecError(Exception):
    """Base exception for dataset spec errors."""

    pass


class DatasetValidationError(DatasetSpecError):
    """Raised when dataset spec fails schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []

    def __str__(self) -> str:
        if self.errors:
            error_list = "\n  - ".join(self.errors[:5])  # Show first 5
            more = f"\n  ... and {len(self.errors) - 5} more" if len(self.errors) > 5 else ""
            return f"{self.args[0]}\n  - {error_list}{more}"
        return self.args[0]


class BindingResolutionError(DatasetSpecError):
    """Raised when a signal reference cannot be resolved."""

    def __init__(self, ref: str, available: list[str]):
        self.ref = ref
        self.available = available
        super().__init__(
            f"Unknown signal reference '{ref}'. "
            f"Available elements: {', '.join(sorted(available)[:10])}"
            + (f" ... and {len(available) - 10} more" if len(available) > 10 else "")
        )


# =============================================================================
# Data Types (matching spec/dataset_schema.json)
# =============================================================================

# Type aliases
ElementKind = Literal[
    "lab", "vital", "demographic", "condition", "drug", "procedure", "observation"
]
ValueType = Literal["numeric", "integer", "string", "boolean", "datetime"]
UnitStrategy = Literal["strict", "allow_declare", "backend_specific"]
DataModel = Literal["omop", "fhir", "custom"]


@dataclass(frozen=True)
class UnitConversion:
    """Unit conversion declaration."""

    to: str
    factor: float
    offset: float = 0.0


@dataclass(frozen=True)
class FilterSpec:
    """Criteria to filter/identify an element in data."""

    concept_id: int | list[int] | None = None
    code: str | None = None
    code_system: str | None = None
    source_value: str | list[str] | None = None
    custom: str | None = None
    valueset: str | None = None  # Reference to valueset name

    def to_filter_expr(self, spec: DatasetSpec) -> str:
        """Convert filter to SQL-like expression."""
        conditions = []

        if self.concept_id is not None:
            if isinstance(self.concept_id, list):
                ids = ", ".join(str(c) for c in self.concept_id)
                conditions.append(f"concept_id IN ({ids})")
            else:
                conditions.append(f"concept_id = {self.concept_id}")

        if self.source_value is not None:
            if isinstance(self.source_value, list):
                vals = ", ".join(f"'{v}'" for v in self.source_value)
                conditions.append(f"source_value IN ({vals})")
            else:
                conditions.append(f"source_value = '{self.source_value}'")

        if self.code is not None:
            conditions.append(f"code = '{self.code}'")

        if self.code_system is not None:
            conditions.append(f"code_system = '{self.code_system}'")

        if self.valueset is not None:
            # Resolve valueset to codes
            vs = spec.get_valueset(self.valueset)
            if vs and vs.codes:
                codes = ", ".join(str(c) for c in vs.codes)
                conditions.append(f"concept_id IN ({codes})")

        if self.custom is not None:
            conditions.append(self.custom)

        return " AND ".join(conditions) if conditions else "1=1"


@dataclass(frozen=True)
class ElementSpec:
    """Physical binding for a semantic element."""

    table: str
    value_field: str
    time_field: str | None = None
    patient_field: str | None = None
    filter: FilterSpec | None = None
    unit: str | None = None
    value_type: ValueType = "numeric"
    kind: ElementKind | None = None
    transform: str | None = None
    description: str | None = None
    unit_conversions: tuple[UnitConversion, ...] = ()


@dataclass(frozen=True)
class Conventions:
    """Global conventions for a dataset."""

    patient_id_field: str = "person_id"
    default_time_field: str | None = None
    timezone: str = "UTC"
    schema: str | None = None
    unit_strategy: UnitStrategy = "strict"


@dataclass(frozen=True)
class ValuesetSpec:
    """Valueset definition (inline codes or file reference)."""

    codes: tuple[int | str, ...] | None = None
    code_system: str | None = None
    description: str | None = None
    file: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class DatasetMetadata:
    """Metadata for auditing and documentation."""

    source: str | None = None
    source_version: str | None = None
    omop_version: str | None = None
    fhir_version: str | None = None
    created: str | None = None
    updated: str | None = None
    maintainer: str | None = None
    license: str | None = None


# =============================================================================
# Adapter Interface Types (RFC-0004)
# =============================================================================


@dataclass(frozen=True)
class Binding:
    """Resolved binding from Dataset Spec - the contract between spec and adapter."""

    table: str
    value_field: str
    time_field: str
    patient_field: str
    filter_expr: str
    unit: str | None = None
    value_type: ValueType = "numeric"
    transform: str | None = None


@dataclass
class Event:
    """Canonical event format returned by adapters."""

    patient_id: str
    timestamp: datetime
    signal_ref: str
    value: float | str | bool | None
    unit: str | None = None


class DatasetAdapter(Protocol):
    """Interface that all adapters must implement (RFC-0004)."""

    def load_dataset_spec(self, uri_or_path: str) -> DatasetSpec:
        """Load and validate a Dataset Spec file."""
        ...

    def resolve_binding(self, signal_ref: str, spec: DatasetSpec) -> Binding:
        """Resolve a semantic reference to a physical binding."""
        ...

    def fetch_events(
        self,
        binding: Binding,
        patient_ids: list[str] | None = None,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> Iterator[Event]:
        """Fetch events from data source, return canonical stream."""
        ...


# =============================================================================
# DatasetSpec - Main Class
# =============================================================================


@dataclass
class DatasetSpec:
    """
    PSDL Dataset Specification.

    Maps semantic signal references to physical data locations.
    Loaded from YAML files and validated against spec/dataset_schema.json.

    IMPORTANT: Always use load_dataset_spec() to create instances.
    Direct construction is for internal/testing use only and will
    be marked as unvalidated.
    """

    # Required fields
    psdl_version: str
    name: str
    version: str
    data_model: DataModel
    elements: dict[str, ElementSpec]

    # Optional fields
    description: str | None = None
    conventions: Conventions = field(default_factory=Conventions)
    valuesets: dict[str, ValuesetSpec] = field(default_factory=dict)
    metadata: DatasetMetadata | None = None

    # Internal state (set by load_dataset_spec)
    _source_path: Path | None = field(default=None, repr=False)
    _checksum: str | None = field(default=None, repr=False)
    _validated: bool = field(default=False, repr=False)

    @property
    def source_path(self) -> Path | None:
        """Path to the source file, if loaded from file."""
        return self._source_path

    @property
    def checksum(self) -> str | None:
        """SHA-256 checksum of the source file."""
        return self._checksum

    @property
    def is_validated(self) -> bool:
        """Whether this spec was validated against the JSON schema."""
        return self._validated

    def _check_validated(self) -> None:
        """Raise error if spec was not loaded through load_dataset_spec()."""
        if not self._validated:
            raise DatasetSpecError(
                "DatasetSpec was not validated. Use load_dataset_spec() to load specs. "
                "Direct construction bypasses schema validation and is not allowed in production."
            )

    def resolve(self, signal_ref: str) -> Binding:
        """
        Resolve a semantic reference to a physical binding.

        Args:
            signal_ref: Semantic reference name (e.g., "creatinine")

        Returns:
            Binding object with physical location details

        Raises:
            DatasetSpecError: If spec was not validated via load_dataset_spec()
            BindingResolutionError: If reference not found in elements
        """
        self._check_validated()

        if signal_ref not in self.elements:
            raise BindingResolutionError(signal_ref, list(self.elements.keys()))

        elem = self.elements[signal_ref]

        # Apply conventions for missing fields
        time_field = (
            elem.time_field or self.conventions.default_time_field or "measurement_datetime"
        )
        patient_field = elem.patient_field or self.conventions.patient_id_field

        # Build filter expression
        filter_expr = elem.filter.to_filter_expr(self) if elem.filter else "1=1"

        # Prepend schema if configured
        table = elem.table
        if self.conventions.schema:
            table = f"{self.conventions.schema}.{elem.table}"

        return Binding(
            table=table,
            value_field=elem.value_field,
            time_field=time_field,
            patient_field=patient_field,
            filter_expr=filter_expr,
            unit=elem.unit,
            value_type=elem.value_type,
            transform=elem.transform,
        )

    def get_valueset(self, name: str) -> ValuesetSpec | None:
        """Get a valueset by name."""
        return self.valuesets.get(name)

    def list_elements(self) -> list[str]:
        """List all available element names."""
        return sorted(self.elements.keys())

    def list_elements_by_kind(self, kind: ElementKind) -> list[str]:
        """List elements of a specific kind."""
        return sorted(name for name, elem in self.elements.items() if elem.kind == kind)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for serialization)."""
        return {
            "psdl_version": self.psdl_version,
            "dataset": {
                "name": self.name,
                "version": self.version,
                "description": self.description,
            },
            "data_model": self.data_model,
            "conventions": {
                "patient_id_field": self.conventions.patient_id_field,
                "default_time_field": self.conventions.default_time_field,
                "timezone": self.conventions.timezone,
                "schema": self.conventions.schema,
                "unit_strategy": self.conventions.unit_strategy,
            },
            "elements": {
                name: {
                    "table": elem.table,
                    "value_field": elem.value_field,
                    "time_field": elem.time_field,
                    "unit": elem.unit,
                    "kind": elem.kind,
                }
                for name, elem in self.elements.items()
            },
        }


# =============================================================================
# Loading and Validation
# =============================================================================


def _load_schema() -> dict[str, Any]:
    """Load the dataset JSON schema."""
    schema_path = Path(__file__).parent.parent.parent.parent / "spec" / "dataset_schema.json"
    if not schema_path.exists():
        # Fallback for installed package
        import importlib.resources

        try:
            with importlib.resources.files("psdl").joinpath(
                "../spec/dataset_schema.json"
            ).open() as f:
                return json.load(f)
        except Exception:
            return {}  # Schema validation will be skipped
    with open(schema_path) as f:
        return json.load(f)


def _parse_filter(data: dict[str, Any] | None) -> FilterSpec | None:
    """Parse filter specification from raw data."""
    if not data:
        return None

    # Handle valueset reference
    valueset_ref = None
    concept_id = data.get("concept_id")
    if isinstance(concept_id, dict) and "valueset" in concept_id:
        valueset_ref = concept_id["valueset"]
        concept_id = None

    return FilterSpec(
        concept_id=concept_id,
        code=data.get("code"),
        code_system=data.get("code_system"),
        source_value=data.get("source_value"),
        custom=data.get("custom"),
        valueset=valueset_ref,
    )


def _parse_element(data: dict[str, Any]) -> ElementSpec:
    """Parse element specification from raw data."""
    conversions = tuple(
        UnitConversion(
            to=c["to"],
            factor=c["factor"],
            offset=c.get("offset", 0.0),
        )
        for c in data.get("unit_conversions", [])
    )

    return ElementSpec(
        table=data["table"],
        value_field=data["value_field"],
        time_field=data.get("time_field"),
        patient_field=data.get("patient_field"),
        filter=_parse_filter(data.get("filter")),
        unit=data.get("unit"),
        value_type=data.get("value_type", "numeric"),
        kind=data.get("kind"),
        transform=data.get("transform"),
        description=data.get("description"),
        unit_conversions=conversions,
    )


def _parse_valueset(data: dict[str, Any]) -> ValuesetSpec:
    """Parse valueset specification from raw data."""
    codes = data.get("codes")
    if codes:
        # Extract code values from CodeEntry format if needed
        parsed_codes = []
        for c in codes:
            if isinstance(c, dict):
                parsed_codes.append(c.get("code", c))
            else:
                parsed_codes.append(c)
        codes = tuple(parsed_codes)

    return ValuesetSpec(
        codes=codes,
        code_system=data.get("code_system"),
        description=data.get("description"),
        file=data.get("file"),
        sha256=data.get("sha256"),
    )


def _parse_conventions(data: dict[str, Any] | None) -> Conventions:
    """Parse conventions from raw data."""
    if not data:
        return Conventions()

    return Conventions(
        patient_id_field=data.get("patient_id_field", "person_id"),
        default_time_field=data.get("default_time_field"),
        timezone=data.get("timezone", "UTC"),
        schema=data.get("schema"),
        unit_strategy=data.get("unit_strategy", "strict"),
    )


def _parse_metadata(data: dict[str, Any] | None) -> DatasetMetadata | None:
    """Parse metadata from raw data."""
    if not data:
        return None

    return DatasetMetadata(
        source=data.get("source"),
        source_version=data.get("source_version"),
        omop_version=data.get("omop_version"),
        fhir_version=data.get("fhir_version"),
        created=data.get("created"),
        updated=data.get("updated"),
        maintainer=data.get("maintainer"),
        license=data.get("license"),
    )


def validate_dataset_spec(data: dict[str, Any]) -> list[str]:
    """
    Validate dataset spec data against JSON schema.

    Args:
        data: Parsed YAML/JSON data

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Basic structure validation
    required = ["psdl_version", "dataset", "data_model", "elements"]
    for req_field in required:
        if req_field not in data:
            errors.append(f"Missing required field: '{req_field}'")

    if "dataset" in data:
        dataset = data["dataset"]
        if not isinstance(dataset, dict):
            errors.append("'dataset' must be an object")
        else:
            if "name" not in dataset:
                errors.append("Missing required field: 'dataset.name'")
            if "version" not in dataset:
                errors.append("Missing required field: 'dataset.version'")

    if "data_model" in data:
        if data["data_model"] not in ("omop", "fhir", "custom"):
            errors.append(
                f"Invalid data_model: '{data['data_model']}'. Must be 'omop', 'fhir', or 'custom'"
            )

    if "elements" in data:
        elements = data["elements"]
        if not isinstance(elements, dict):
            errors.append("'elements' must be an object")
        elif len(elements) == 0:
            errors.append("'elements' must have at least one element")
        else:
            for name, elem in elements.items():
                if not isinstance(elem, dict):
                    errors.append(f"Element '{name}' must be an object")
                    continue
                if "table" not in elem:
                    errors.append(f"Element '{name}' missing required field: 'table'")
                if "value_field" not in elem:
                    errors.append(f"Element '{name}' missing required field: 'value_field'")

    # Try JSON Schema validation if jsonschema is available
    try:
        import jsonschema

        schema = _load_schema()
        if schema:
            validator = jsonschema.Draft202012Validator(schema)
            for error in validator.iter_errors(data):
                path = ".".join(str(p) for p in error.absolute_path)
                msg = f"{path}: {error.message}" if path else error.message
                if msg not in errors:  # Avoid duplicates
                    errors.append(msg)
    except ImportError:
        pass  # jsonschema not available, use basic validation only

    return errors


def load_dataset_spec(path: str | Path) -> DatasetSpec:
    """
    Load a Dataset Specification from a YAML file.

    Args:
        path: Path to the dataset spec YAML file

    Returns:
        DatasetSpec object

    Raises:
        FileNotFoundError: If file doesn't exist
        DatasetValidationError: If spec fails validation

    Example:
        >>> spec = load_dataset_spec("dataset_specs/mimic_iv_omop.yaml")
        >>> binding = spec.resolve("creatinine")
        >>> print(binding.table)
        "measurement"
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Dataset spec not found: {path}")

    # Read and compute checksum
    content = path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(content.encode()).hexdigest()

    # Parse YAML
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise DatasetValidationError(f"Invalid YAML in {path}: {e}")

    if not isinstance(data, dict):
        raise DatasetValidationError(
            f"Dataset spec must be a YAML object, got {type(data).__name__}"
        )

    # Validate
    errors = validate_dataset_spec(data)
    if errors:
        raise DatasetValidationError(f"Invalid dataset spec '{path}'", errors)

    # Parse structure
    dataset_info = data.get("dataset", {})
    elements = {name: _parse_element(elem) for name, elem in data.get("elements", {}).items()}
    valuesets = {name: _parse_valueset(vs) for name, vs in data.get("valuesets", {}).items()}

    spec = DatasetSpec(
        psdl_version=data["psdl_version"],
        name=dataset_info.get("name", path.stem),
        version=dataset_info.get("version", "0.0.0"),
        description=dataset_info.get("description"),
        data_model=data["data_model"],
        conventions=_parse_conventions(data.get("conventions")),
        elements=elements,
        valuesets=valuesets,
        metadata=_parse_metadata(data.get("metadata")),
        _source_path=path,
        _validated=True,  # Mark as validated - only set by load_dataset_spec()
        _checksum=checksum,
    )

    return spec
