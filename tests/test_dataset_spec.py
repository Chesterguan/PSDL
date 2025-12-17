"""
Tests for PSDL Dataset Specification (RFC-0004).

Tests the DatasetSpec loader, validation, and binding resolution.
"""

import tempfile
from pathlib import Path

import pytest

from psdl.core.dataset import (
    Binding,
    BindingResolutionError,
    Conventions,
    DatasetSpec,
    DatasetValidationError,
    ElementSpec,
    FilterSpec,
    load_dataset_spec,
    validate_dataset_spec,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def minimal_spec_yaml():
    """Minimal valid dataset spec YAML."""
    return """
psdl_version: "0.3"

dataset:
  name: test_minimal
  version: "1.0.0"

data_model: omop

elements:
  creatinine:
    table: measurement
    value_field: value_as_number
    filter:
      concept_id: 3016723
    unit: mg/dL
"""


@pytest.fixture
def full_spec_yaml():
    """Full dataset spec YAML with all features."""
    return """
psdl_version: "0.3"

dataset:
  name: test_full
  version: "2.0.0"
  description: "Full test dataset spec"

data_model: omop

conventions:
  patient_id_field: person_id
  default_time_field: measurement_datetime
  timezone: UTC
  schema: cdm_schema
  unit_strategy: strict

elements:
  creatinine:
    kind: lab
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3016723, 3020564]
    unit: mg/dL
    value_type: numeric
    description: "Serum creatinine"

  heart_rate:
    kind: vital
    table: measurement
    value_field: value_as_number
    filter:
      concept_id: 3027018
    unit: bpm

  temperature_source:
    kind: vital
    table: measurement
    value_field: value_as_number
    filter:
      source_value: ["Temperature", "Temp"]
    unit: celsius

valuesets:
  aki_labs:
    description: "AKI-related lab codes"
    codes:
      - 3016723
      - 3013682
      - 3020564

metadata:
  source: "Test Dataset"
  omop_version: "5.4"
  created: "2025-12-16"
"""


@pytest.fixture
def temp_spec_file(minimal_spec_yaml):
    """Create a temporary spec file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(minimal_spec_yaml)
        return Path(f.name)


# =============================================================================
# Test Loading
# =============================================================================


class TestLoadDatasetSpec:
    """Tests for load_dataset_spec function."""

    def test_load_minimal_spec(self, minimal_spec_yaml):
        """Load a minimal valid dataset spec."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(minimal_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        assert spec.name == "test_minimal"
        assert spec.version == "1.0.0"
        assert spec.data_model == "omop"
        assert "creatinine" in spec.elements

    def test_load_full_spec(self, full_spec_yaml):
        """Load a full dataset spec with all features."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(full_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        assert spec.name == "test_full"
        assert spec.version == "2.0.0"
        assert spec.description == "Full test dataset spec"
        assert spec.conventions.schema == "cdm_schema"
        assert len(spec.elements) == 3
        assert "aki_labs" in spec.valuesets

    def test_load_existing_omop_spec(self):
        """Load the existing OMOP CDM v5.4 dataset spec."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")

        assert spec.name == "omop_cdm_v54"
        assert spec.data_model == "omop"
        assert "creatinine" in spec.elements
        assert "heart_rate" in spec.elements
        assert spec.conventions.patient_id_field == "person_id"

    def test_load_nonexistent_file(self):
        """Loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_dataset_spec("nonexistent/path/spec.yaml")

    def test_load_invalid_yaml(self):
        """Loading invalid YAML raises DatasetValidationError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{ invalid yaml: [")
            f.flush()
            with pytest.raises(DatasetValidationError):
                load_dataset_spec(f.name)

    def test_checksum_computed(self, minimal_spec_yaml):
        """Checksum is computed when loading."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(minimal_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        assert spec.checksum is not None
        assert len(spec.checksum) == 64  # SHA-256 hex

    def test_source_path_stored(self, minimal_spec_yaml):
        """Source path is stored when loading."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(minimal_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        assert spec.source_path is not None
        assert spec.source_path.exists()


# =============================================================================
# Test Validation
# =============================================================================


class TestValidateDatasetSpec:
    """Tests for validate_dataset_spec function."""

    def test_valid_spec(self):
        """Valid spec returns empty error list."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
            "elements": {"creatinine": {"table": "measurement", "value_field": "value_as_number"}},
        }
        errors = validate_dataset_spec(data)
        assert len(errors) == 0

    def test_missing_psdl_version(self):
        """Missing psdl_version is an error."""
        data = {
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
            "elements": {"cr": {"table": "t", "value_field": "v"}},
        }
        errors = validate_dataset_spec(data)
        assert any("psdl_version" in e for e in errors)

    def test_missing_dataset(self):
        """Missing dataset section is an error."""
        data = {
            "psdl_version": "0.3",
            "data_model": "omop",
            "elements": {"cr": {"table": "t", "value_field": "v"}},
        }
        errors = validate_dataset_spec(data)
        assert any("dataset" in e for e in errors)

    def test_missing_elements(self):
        """Missing elements section is an error."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
        }
        errors = validate_dataset_spec(data)
        assert any("elements" in e for e in errors)

    def test_empty_elements(self):
        """Empty elements section is an error."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
            "elements": {},
        }
        errors = validate_dataset_spec(data)
        assert any("at least one" in e for e in errors)

    def test_invalid_data_model(self):
        """Invalid data_model is an error."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "invalid",
            "elements": {"cr": {"table": "t", "value_field": "v"}},
        }
        errors = validate_dataset_spec(data)
        assert any("data_model" in e for e in errors)

    def test_element_missing_table(self):
        """Element missing table is an error."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
            "elements": {"cr": {"value_field": "v"}},
        }
        errors = validate_dataset_spec(data)
        assert any("table" in e for e in errors)

    def test_element_missing_value_field(self):
        """Element missing value_field is an error."""
        data = {
            "psdl_version": "0.3",
            "dataset": {"name": "test", "version": "1.0.0"},
            "data_model": "omop",
            "elements": {"cr": {"table": "t"}},
        }
        errors = validate_dataset_spec(data)
        assert any("value_field" in e for e in errors)


# =============================================================================
# Test Binding Resolution
# =============================================================================


class TestBindingResolution:
    """Tests for DatasetSpec.resolve method."""

    def test_resolve_basic_element(self):
        """Resolve a basic element to binding."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        binding = spec.resolve("creatinine")

        assert isinstance(binding, Binding)
        assert binding.table == "cdm.measurement"
        assert binding.value_field == "value_as_number"
        assert binding.patient_field == "person_id"
        assert binding.unit == "mg/dL"
        assert "3016723" in binding.filter_expr

    def test_resolve_applies_schema(self):
        """Resolve applies schema prefix from conventions."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        binding = spec.resolve("heart_rate")

        # Schema "cdm" should be prefixed
        assert binding.table.startswith("cdm.")

    def test_resolve_unknown_raises(self):
        """Resolving unknown reference raises BindingResolutionError."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")

        with pytest.raises(BindingResolutionError) as exc_info:
            spec.resolve("nonexistent_signal")

        assert "nonexistent_signal" in str(exc_info.value)
        assert "Available elements" in str(exc_info.value)

    def test_resolve_uses_convention_defaults(self, full_spec_yaml):
        """Resolve uses convention defaults for missing fields."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(full_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        # heart_rate doesn't specify time_field, should use default
        binding = spec.resolve("heart_rate")
        assert binding.time_field == "measurement_datetime"

    def test_filter_expr_with_multiple_concept_ids(self, full_spec_yaml):
        """Filter expression handles multiple concept_ids."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(full_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        binding = spec.resolve("creatinine")
        # Should have IN clause with both IDs
        assert "IN" in binding.filter_expr
        assert "3016723" in binding.filter_expr
        assert "3020564" in binding.filter_expr

    def test_filter_expr_with_source_value(self, full_spec_yaml):
        """Filter expression handles source_value filter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(full_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        binding = spec.resolve("temperature_source")
        assert "source_value" in binding.filter_expr
        assert "Temperature" in binding.filter_expr


# =============================================================================
# Test DatasetSpec Methods
# =============================================================================


class TestDatasetSpecMethods:
    """Tests for DatasetSpec helper methods."""

    def test_list_elements(self):
        """list_elements returns sorted element names."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        elements = spec.list_elements()

        assert isinstance(elements, list)
        assert len(elements) > 0
        assert "creatinine" in elements
        assert elements == sorted(elements)

    def test_list_elements_by_kind(self):
        """list_elements_by_kind filters by kind."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")

        labs = spec.list_elements_by_kind("lab")
        vitals = spec.list_elements_by_kind("vital")

        assert "creatinine" in labs
        assert "heart_rate" in vitals
        assert "creatinine" not in vitals

    def test_get_valueset(self, full_spec_yaml):
        """get_valueset returns valueset by name."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(full_spec_yaml)
            f.flush()
            spec = load_dataset_spec(f.name)

        vs = spec.get_valueset("aki_labs")
        assert vs is not None
        assert 3016723 in vs.codes

    def test_get_valueset_missing(self):
        """get_valueset returns None for missing valueset."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        vs = spec.get_valueset("nonexistent")
        assert vs is None

    def test_to_dict(self):
        """to_dict returns serializable dictionary."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        d = spec.to_dict()

        assert isinstance(d, dict)
        assert d["psdl_version"] == spec.psdl_version
        assert d["dataset"]["name"] == spec.name
        assert "creatinine" in d["elements"]


# =============================================================================
# Test Data Types
# =============================================================================


class TestDataTypes:
    """Tests for dataclass types."""

    def test_binding_frozen(self):
        """Binding is immutable."""
        binding = Binding(
            table="t",
            value_field="v",
            time_field="ts",
            patient_field="p",
            filter_expr="1=1",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            binding.table = "new_table"

    def test_element_spec_defaults(self):
        """ElementSpec has correct defaults."""
        elem = ElementSpec(table="t", value_field="v")

        assert elem.value_type == "numeric"
        assert elem.time_field is None
        assert elem.patient_field is None

    def test_conventions_defaults(self):
        """Conventions has correct defaults."""
        conv = Conventions()

        assert conv.patient_id_field == "person_id"
        assert conv.timezone == "UTC"
        assert conv.unit_strategy == "strict"

    def test_filter_spec_to_filter_expr(self):
        """FilterSpec.to_filter_expr generates correct SQL."""
        # Create a validated spec for testing (using _validated=True for internal test)
        spec = DatasetSpec(
            psdl_version="0.3",
            name="test",
            version="1.0.0",
            data_model="omop",
            elements={},
            _validated=True,  # Internal use for testing
        )

        # Single concept_id
        f1 = FilterSpec(concept_id=12345)
        assert f1.to_filter_expr(spec) == "concept_id = 12345"

        # Multiple concept_ids
        f2 = FilterSpec(concept_id=[123, 456])
        assert "IN (123, 456)" in f2.to_filter_expr(spec)

        # Source value
        f3 = FilterSpec(source_value="Test")
        assert "source_value = 'Test'" in f3.to_filter_expr(spec)

        # Custom filter
        f4 = FilterSpec(custom="custom_field > 10")
        assert "custom_field > 10" in f4.to_filter_expr(spec)


# =============================================================================
# Test Mandatory Validation
# =============================================================================


class TestMandatoryValidation:
    """Tests for mandatory validation enforcement."""

    def test_unvalidated_spec_cannot_resolve(self):
        """Direct construction without validation cannot resolve bindings."""
        from psdl.core.dataset import DatasetSpecError

        # Direct construction - bypasses load_dataset_spec()
        spec = DatasetSpec(
            psdl_version="0.3",
            name="test",
            version="1.0.0",
            data_model="omop",
            elements={"test_element": ElementSpec(table="t", value_field="v")},
            # _validated defaults to False
        )

        assert not spec.is_validated

        with pytest.raises(DatasetSpecError) as exc_info:
            spec.resolve("test_element")

        assert "not validated" in str(exc_info.value)
        assert "load_dataset_spec()" in str(exc_info.value)

    def test_validated_spec_can_resolve(self):
        """Spec loaded via load_dataset_spec() can resolve bindings."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")

        assert spec.is_validated

        # Should work without error
        binding = spec.resolve("creatinine")
        assert binding.table is not None

    def test_is_validated_property(self):
        """is_validated property reflects validation state."""
        # Unvalidated
        unvalidated = DatasetSpec(
            psdl_version="0.3",
            name="test",
            version="1.0.0",
            data_model="omop",
            elements={"x": ElementSpec(table="t", value_field="v")},
        )
        assert not unvalidated.is_validated

        # Validated via load
        validated = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")
        assert validated.is_validated


# =============================================================================
# Test Error Messages
# =============================================================================


class TestErrorMessages:
    """Tests for error message quality."""

    def test_binding_error_shows_available(self):
        """BindingResolutionError shows available elements."""
        spec = load_dataset_spec("dataset_specs/omop_cdm_v54.yaml")

        try:
            spec.resolve("bad_signal")
        except BindingResolutionError as e:
            assert "bad_signal" in str(e)
            assert "creatinine" in str(e) or "Available" in str(e)

    def test_validation_error_lists_issues(self):
        """DatasetValidationError lists all issues."""
        data = {
            "data_model": "invalid",
            "elements": {},
        }
        errors = validate_dataset_spec(data)

        # Should catch multiple errors
        assert len(errors) >= 2  # Missing psdl_version, dataset, invalid data_model
