"""
Tests for RFC-0008: Vendor-Neutral Foundation Architecture.

Tests cover:
- Phase 1: ClinicalDomain, FilterPredicate, FilterPredicateSet
- Phase 2: DataBackend lifecycle and capabilities
- Phase 3: CohortCompiler capabilities
- Phase 4: Example scenarios free of concept_id
"""

import warnings
from pathlib import Path

import pytest

from psdl.core.ir import ClinicalDomain, Domain, Signal

# =============================================================================
# Phase 1: ClinicalDomain Tests
# =============================================================================


class TestClinicalDomain:
    """Tests for the ClinicalDomain enum (RFC-0008)."""

    def test_clinical_domain_values(self):
        """All clinical domain values exist."""
        assert ClinicalDomain.LABORATORY.value == "laboratory"
        assert ClinicalDomain.VITAL_SIGN.value == "vital_sign"
        assert ClinicalDomain.CONDITION.value == "condition"
        assert ClinicalDomain.MEDICATION.value == "medication"
        assert ClinicalDomain.PROCEDURE.value == "procedure"
        assert ClinicalDomain.OBSERVATION.value == "observation"
        assert ClinicalDomain.DEMOGRAPHIC.value == "demographic"

    def test_from_legacy_measurement(self):
        """Legacy MEASUREMENT maps to LABORATORY."""
        result = ClinicalDomain.from_legacy(Domain.MEASUREMENT)
        assert result == ClinicalDomain.LABORATORY

    def test_from_legacy_condition(self):
        """Legacy CONDITION maps to CONDITION."""
        result = ClinicalDomain.from_legacy(Domain.CONDITION)
        assert result == ClinicalDomain.CONDITION

    def test_from_legacy_drug(self):
        """Legacy DRUG maps to MEDICATION."""
        result = ClinicalDomain.from_legacy(Domain.DRUG)
        assert result == ClinicalDomain.MEDICATION

    def test_from_legacy_procedure(self):
        """Legacy PROCEDURE maps to PROCEDURE."""
        result = ClinicalDomain.from_legacy(Domain.PROCEDURE)
        assert result == ClinicalDomain.PROCEDURE

    def test_from_legacy_observation(self):
        """Legacy OBSERVATION maps to OBSERVATION."""
        result = ClinicalDomain.from_legacy(Domain.OBSERVATION)
        assert result == ClinicalDomain.OBSERVATION

    def test_from_legacy_all_domains(self):
        """All legacy domains can be converted."""
        for domain in Domain:
            result = ClinicalDomain.from_legacy(domain)
            assert isinstance(result, ClinicalDomain)


class TestSignalDeprecation:
    """Tests for Signal.concept_id deprecation warning."""

    def test_signal_without_concept_id_no_warning(self):
        """Signal without concept_id should not emit warning."""
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            signal = Signal(name="Cr", ref="creatinine")
            assert signal.concept_id is None

    def test_signal_with_concept_id_emits_warning(self):
        """Signal with concept_id should emit DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="concept_id is deprecated"):
            Signal(name="Cr", ref="creatinine", concept_id=3016723)

    def test_signal_clinical_domain_default(self):
        """Signal has default clinical_domain of LABORATORY."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            signal = Signal(name="Cr", ref="creatinine")
            assert signal.clinical_domain == ClinicalDomain.LABORATORY


# =============================================================================
# Phase 1: FilterPredicate Tests
# =============================================================================


class TestFilterPredicate:
    """Tests for FilterPredicate and FilterPredicateSet (RFC-0008)."""

    def test_predicate_eq_numeric(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="concept_id", operator="eq", value=3016723)
        assert p.to_sql() == "concept_id = 3016723"

    def test_predicate_eq_string(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="source_value", operator="eq", value="Creatinine")
        assert p.to_sql() == "source_value = 'Creatinine'"

    def test_predicate_in_numeric(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="concept_id", operator="in", value=[1, 2, 3])
        assert p.to_sql() == "concept_id IN (1, 2, 3)"

    def test_predicate_in_string(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="source_value", operator="in", value=["A", "B"])
        assert p.to_sql() == "source_value IN ('A', 'B')"

    def test_predicate_contains(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="name", operator="contains", value="creat")
        assert p.to_sql() == "name LIKE '%creat%'"

    def test_predicate_custom(self):
        from psdl.core.dataset import FilterPredicate

        p = FilterPredicate(field="custom", operator="custom", value="value_as_number > 0")
        assert p.to_sql() == "value_as_number > 0"


class TestFilterPredicateSet:
    """Tests for FilterPredicateSet composition."""

    def test_empty_set_to_sql(self):
        from psdl.core.dataset import FilterPredicateSet

        pset = FilterPredicateSet()
        assert pset.to_sql() == "1=1"

    def test_single_predicate(self):
        from psdl.core.dataset import FilterPredicate, FilterPredicateSet

        p = FilterPredicate(field="concept_id", operator="eq", value=42)
        pset = FilterPredicateSet(predicates=(p,))
        assert pset.to_sql() == "concept_id = 42"

    def test_multiple_predicates(self):
        from psdl.core.dataset import FilterPredicate, FilterPredicateSet

        p1 = FilterPredicate(field="concept_id", operator="eq", value=42)
        p2 = FilterPredicate(field="source_value", operator="eq", value="test")
        pset = FilterPredicateSet(predicates=(p1, p2))
        assert pset.to_sql() == "concept_id = 42 AND source_value = 'test'"

    def test_len(self):
        from psdl.core.dataset import FilterPredicate, FilterPredicateSet

        p = FilterPredicate(field="x", operator="eq", value=1)
        pset = FilterPredicateSet(predicates=(p, p, p))
        assert len(pset) == 3

    def test_iter(self):
        from psdl.core.dataset import FilterPredicate, FilterPredicateSet

        p1 = FilterPredicate(field="a", operator="eq", value=1)
        p2 = FilterPredicate(field="b", operator="eq", value=2)
        pset = FilterPredicateSet(predicates=(p1, p2))
        assert list(pset) == [p1, p2]


class TestFilterSpecToPredicates:
    """Tests for FilterSpec.to_predicates() conversion."""

    def test_concept_id_single(self):
        from psdl.core.dataset import FilterSpec

        fs = FilterSpec(concept_id=3016723)
        pset = fs.to_predicates()
        assert len(pset) == 1
        assert pset.predicates[0].field == "concept_id"
        assert pset.predicates[0].operator == "eq"
        assert pset.predicates[0].value == 3016723

    def test_concept_id_list(self):
        from psdl.core.dataset import FilterSpec

        fs = FilterSpec(concept_id=[1, 2, 3])
        pset = fs.to_predicates()
        assert len(pset) == 1
        assert pset.predicates[0].operator == "in"
        assert pset.predicates[0].value == [1, 2, 3]

    def test_source_value(self):
        from psdl.core.dataset import FilterSpec

        fs = FilterSpec(source_value="Creatinine")
        pset = fs.to_predicates()
        assert len(pset) == 1
        assert pset.predicates[0].field == "source_value"
        assert pset.predicates[0].operator == "eq"

    def test_multiple_criteria(self):
        from psdl.core.dataset import FilterSpec

        fs = FilterSpec(concept_id=42, source_value="test")
        pset = fs.to_predicates()
        assert len(pset) == 2

    def test_to_filter_expr_consistency(self):
        """to_filter_expr() should produce same SQL as to_predicates().to_sql()."""
        from psdl.core.dataset import DatasetSpec, ElementSpec, FilterSpec

        fs = FilterSpec(concept_id=3016723)
        spec = DatasetSpec(
            psdl_version="0.4",
            name="test",
            version="1.0",
            data_model="omop",
            elements={"cr": ElementSpec(table="measurement", value_field="value_as_number")},
            _validated=True,
        )
        sql_from_expr = fs.to_filter_expr(spec)
        sql_from_preds = fs.to_predicates(spec).to_sql()
        assert sql_from_expr == sql_from_preds


class TestBindingFilterPredicates:
    """Tests for Binding.filter_predicates field."""

    def test_binding_with_filter_predicates(self):
        from psdl.core.dataset import Binding, FilterPredicate, FilterPredicateSet

        pset = FilterPredicateSet(
            predicates=(FilterPredicate(field="concept_id", operator="eq", value=42),)
        )
        binding = Binding(
            table="measurement",
            value_field="value_as_number",
            time_field="measurement_datetime",
            patient_field="person_id",
            filter_expr="concept_id = 42",
            filter_predicates=pset,
        )
        assert binding.filter_predicates is not None
        assert len(binding.filter_predicates) == 1

    def test_binding_without_filter_predicates(self):
        from psdl.core.dataset import Binding

        binding = Binding(
            table="measurement",
            value_field="value_as_number",
            time_field="measurement_datetime",
            patient_field="person_id",
            filter_expr="1=1",
        )
        assert binding.filter_predicates is None

    def test_resolve_populates_filter_predicates(self):
        """DatasetSpec.resolve() should populate both filter_expr and filter_predicates."""
        from psdl.core.dataset import DatasetSpec, ElementSpec, FilterSpec

        spec = DatasetSpec(
            psdl_version="0.4",
            name="test",
            version="1.0",
            data_model="omop",
            elements={
                "creatinine": ElementSpec(
                    table="measurement",
                    value_field="value_as_number",
                    filter=FilterSpec(concept_id=3016723),
                ),
            },
            _validated=True,
        )
        binding = spec.resolve("creatinine")
        assert binding.filter_predicates is not None
        assert len(binding.filter_predicates) == 1
        assert binding.filter_expr == binding.filter_predicates.to_sql()


# =============================================================================
# Phase 2: DataBackend Lifecycle Tests
# =============================================================================


class TestDataBackendLifecycle:
    """Tests for DataBackend lifecycle methods (RFC-0008)."""

    def test_inmemory_context_manager(self):
        """InMemoryBackend supports context manager protocol."""
        from psdl.runtimes.single import InMemoryBackend

        with InMemoryBackend() as backend:
            assert backend is not None

    def test_inmemory_capabilities(self):
        """InMemoryBackend has empty capabilities by default."""
        from psdl.runtimes.single import InMemoryBackend

        backend = InMemoryBackend()
        assert backend.capabilities == set()

    def test_inmemory_resolve_binding_returns_none(self):
        """InMemoryBackend.resolve_binding returns None by default."""
        from psdl.runtimes.single import InMemoryBackend

        backend = InMemoryBackend()
        assert backend.resolve_binding("creatinine") is None

    def test_inmemory_close_no_error(self):
        """InMemoryBackend.close() doesn't raise."""
        from psdl.runtimes.single import InMemoryBackend

        backend = InMemoryBackend()
        backend.close()

    def test_inmemory_connect_no_error(self):
        """InMemoryBackend.connect() doesn't raise."""
        from psdl.runtimes.single import InMemoryBackend

        backend = InMemoryBackend()
        backend.connect()


class TestAdapterCapabilities:
    """Tests for adapter capability declarations (RFC-0008)."""

    def test_omop_has_dataset_adapter_capability(self):
        """OMOPBackend declares dataset_adapter capability."""
        from psdl.adapters.omop import OMOPBackend, OMOPConfig

        config = OMOPConfig(connection_string="sqlite:///test.db")
        backend = OMOPBackend(config)
        assert "dataset_adapter" in backend.capabilities

    def test_fhir_capabilities(self):
        """FHIRBackend has capabilities property."""
        from psdl.adapters.fhir import FHIRBackend, FHIRConfig

        config = FHIRConfig(base_url="http://localhost:8080")
        backend = FHIRBackend(config)
        assert isinstance(backend.capabilities, set)

    def test_fhir_dataset_spec_parameter(self):
        """FHIRBackend accepts dataset_spec parameter."""
        from psdl.adapters.fhir import FHIRBackend, FHIRConfig

        config = FHIRConfig(base_url="http://localhost:8080")
        backend = FHIRBackend(config, dataset_spec="test")
        assert backend.dataset_spec == "test"

    def test_physionet_capabilities(self):
        """PhysioNetBackend has capabilities property."""
        from psdl.adapters.physionet import PhysioNetBackend

        backend = PhysioNetBackend("/tmp/test")
        assert isinstance(backend.capabilities, set)


# =============================================================================
# Phase 2: BatchRuntime Tests
# =============================================================================


class TestBatchRuntime:
    """Tests for BatchRuntime and SQLBatchRuntime (RFC-0008)."""

    def test_batch_result_dataclass(self):
        from psdl.runtimes.batch import BatchResult

        result = BatchResult(
            patient_id="123",
            triggered=True,
            triggered_logic=["aki_stage1"],
        )
        assert result.patient_id == "123"
        assert result.triggered is True
        assert result.triggered_logic == ["aki_stage1"]

    def test_batch_result_defaults(self):
        from psdl.runtimes.batch import BatchResult

        result = BatchResult(patient_id="456", triggered=False)
        assert result.trend_values == {}
        assert result.logic_results == {}
        assert result.metadata == {}


# =============================================================================
# Phase 3: CohortCompiler Integration Tests
# =============================================================================


class TestCohortCompilerRFC0008:
    """Tests for CohortCompiler RFC-0008 integration."""

    def test_capabilities(self):
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        assert "sql" in compiler.capabilities

    def test_get_sql_dialect(self):
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        assert compiler.get_sql_dialect() == "postgresql"

    def test_render_interval(self):
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        assert compiler.render_interval(3600) == "INTERVAL '3600 seconds'"

    def test_dataset_spec_parameter(self):
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler(dataset_spec="test")
        assert compiler.dataset_spec == "test"

    def test_execute_raises(self):
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        with pytest.raises(NotImplementedError):
            list(compiler.execute(None))


# =============================================================================
# Phase 4: Example Scenario Tests
# =============================================================================


class TestExampleScenariosNoConceptId:
    """Verify example scenarios do not contain concept_id."""

    def _get_example_dir(self) -> Path:
        return Path(__file__).parent.parent / "src" / "psdl" / "examples"

    def test_examples_no_concept_id(self):
        """No example scenario YAML should contain concept_id values."""
        examples_dir = self._get_example_dir()
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        for yaml_file in examples_dir.glob("*.yaml"):
            content = yaml_file.read_text()
            # Allow comment mentions, but no actual key usage
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "concept_id:" in stripped:
                    pytest.fail(f"{yaml_file.name} contains concept_id at line: {stripped}")


class TestBenchmarkScenariosNoConceptId:
    """Verify benchmark scenarios do not contain concept_id."""

    def test_benchmarks_no_concept_id(self):
        from psdl.benchmarks.scenarios import BENCHMARK_SCENARIOS

        for name, scenario in BENCHMARK_SCENARIOS.items():
            for sig_name, sig_def in scenario.get("signals", {}).items():
                if isinstance(sig_def, dict):
                    assert "concept_id" not in sig_def, (
                        f"Benchmark '{name}' signal '{sig_name}' " f"still has concept_id"
                    )


# =============================================================================
# Phase 1c: Export Tests
# =============================================================================


class TestExports:
    """Verify new types are properly exported."""

    def test_clinical_domain_importable(self):
        from psdl import ClinicalDomain

        assert ClinicalDomain.LABORATORY is not None

    def test_filter_predicate_importable(self):
        from psdl import FilterPredicate

        assert FilterPredicate is not None

    def test_filter_predicate_set_importable(self):
        from psdl import FilterPredicateSet

        assert FilterPredicateSet is not None

    def test_version_is_0_4_0(self):
        import psdl

        assert psdl.__version__ == "0.4.0"


# =============================================================================
# Parser Deprecation Warning Tests
# =============================================================================


class TestParserDeprecationWarning:
    """Tests for deprecation warning when parsing scenarios with concept_id."""

    def test_parser_warns_on_concept_id(self):
        """Parsing YAML with concept_id should emit DeprecationWarning (via Signal.__post_init__)."""
        from psdl import PSDLParser

        yaml_content = """
scenario: Test
version: "1.0"
signals:
  HR:
    ref: heart_rate
    concept_id: 3027018
trends:
  hr_current:
    expr: last(HR)
logic:
  tachy:
    when: hr_current > 100
"""
        parser = PSDLParser()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            parser.parse_string(yaml_content)
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "concept_id" in str(deprecation_warnings[0].message)


# =============================================================================
# Gap Fix Tests: core/__init__ exports (Gap 1)
# =============================================================================


class TestCoreSubpackageExports:
    """Verify psdl.core exports new RFC-0008 types."""

    def test_core_exports_clinical_domain(self):
        from psdl.core import ClinicalDomain

        assert ClinicalDomain.LABORATORY.value == "laboratory"

    def test_core_exports_filter_predicate(self):
        from psdl.core import FilterPredicate

        p = FilterPredicate(field="x", operator="eq", value=1)
        assert p.field == "x"

    def test_core_exports_filter_predicate_set(self):
        from psdl.core import FilterPredicateSet

        ps = FilterPredicateSet()
        assert len(ps) == 0


# =============================================================================
# Gap Fix Tests: Parser clinical_domain (Gap 2)
# =============================================================================


class TestParserClinicalDomain:
    """Verify parser correctly sets clinical_domain on signals."""

    def test_parser_sets_clinical_domain_from_domain(self):
        """When YAML has domain: condition, clinical_domain should be CONDITION."""
        from psdl import PSDLParser

        yaml_content = """
scenario: TestDomain
version: "1.0"
signals:
  DX:
    ref: diagnosis
    domain: condition
trends:
  dx_current:
    expr: last(DX)
logic:
  has_dx:
    when: dx_current > 0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)
        signal = scenario.signals["DX"]
        assert signal.clinical_domain == ClinicalDomain.CONDITION

    def test_parser_defaults_clinical_domain_laboratory(self):
        """Without domain key, clinical_domain defaults to LABORATORY."""
        from psdl import PSDLParser

        yaml_content = """
scenario: TestDefault
version: "1.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_current:
    expr: last(Cr)
logic:
  high_cr:
    when: cr_current > 1.2
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)
        signal = scenario.signals["Cr"]
        assert signal.clinical_domain == ClinicalDomain.LABORATORY

    def test_parser_clinical_domain_override(self):
        """Explicit clinical_domain in YAML overrides domain-derived value."""
        from psdl import PSDLParser

        yaml_content = """
scenario: TestOverride
version: "1.0"
signals:
  BP:
    ref: blood_pressure
    domain: measurement
    clinical_domain: vital_sign
trends:
  bp_current:
    expr: last(BP)
logic:
  high_bp:
    when: bp_current > 140
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)
        signal = scenario.signals["BP"]
        assert signal.clinical_domain == ClinicalDomain.VITAL_SIGN

    def test_parser_all_domain_mappings(self):
        """All Domain enum values produce correct ClinicalDomain."""
        from psdl import PSDLParser

        for domain_val, expected_cd in [
            ("measurement", ClinicalDomain.LABORATORY),
            ("condition", ClinicalDomain.CONDITION),
            ("drug", ClinicalDomain.MEDICATION),
            ("procedure", ClinicalDomain.PROCEDURE),
            ("observation", ClinicalDomain.OBSERVATION),
        ]:
            yaml_content = f"""
scenario: TestMap
version: "1.0"
signals:
  S:
    ref: signal_ref
    domain: {domain_val}
trends:
  s_current:
    expr: last(S)
logic:
  rule:
    when: s_current > 0
"""
            parser = PSDLParser()
            scenario = parser.parse_string(yaml_content)
            assert (
                scenario.signals["S"].clinical_domain == expected_cd
            ), f"Domain '{domain_val}' should map to {expected_cd}"


# =============================================================================
# Gap Fix Tests: CohortCompiler dataset_spec (Gap 3)
# =============================================================================


class TestCohortCompilerDatasetSpec:
    """Verify CohortCompiler uses dataset_spec when provided."""

    def test_resolve_signal_binding_with_dataset_spec(self):
        """_resolve_signal_binding should use dataset_spec bindings."""
        from unittest.mock import MagicMock

        from psdl.core.dataset import FilterPredicate, FilterPredicateSet
        from psdl.runtimes.cohort.compiler import CohortCompiler

        # Create mock dataset_spec
        mock_binding = MagicMock()
        mock_binding.table = "custom_schema.lab_results"
        mock_binding.value_field = "result_value"
        mock_binding.time_field = "result_datetime"
        mock_binding.filter_predicates = FilterPredicateSet(
            predicates=(FilterPredicate(field="loinc_code", operator="eq", value="2160-0"),)
        )
        mock_binding.filter_expr = "loinc_code = '2160-0'"

        mock_ds = MagicMock()
        mock_ds.resolve.return_value = mock_binding

        compiler = CohortCompiler(schema="public", dataset_spec=mock_ds)
        mock_signal = MagicMock()
        mock_signal.ref = "creatinine"

        resolved = compiler._resolve_signal_binding("Cr", mock_signal)

        assert resolved["table"] == "custom_schema.lab_results"
        assert resolved["value_col"] == "result_value"
        assert resolved["datetime_col"] == "result_datetime"
        assert "loinc_code" in resolved["filter_cond"]

    def test_resolve_signal_binding_fallback_without_dataset_spec(self):
        """Without dataset_spec, falls back to OMOP defaults."""
        from unittest.mock import MagicMock

        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler(schema="myschema")
        mock_signal = MagicMock()
        mock_signal.concept_id = 3016723
        mock_signal.domain = MagicMock()
        mock_signal.domain.value = "measurement"

        resolved = compiler._resolve_signal_binding("Cr", mock_signal)

        assert resolved["table"] == "myschema.measurement"
        assert resolved["value_col"] == "value_as_number"
        assert resolved["datetime_col"] == "measurement_datetime"
        assert "3016723" in resolved["filter_cond"]

    def test_resolve_signal_binding_fallback_on_error(self):
        """If dataset_spec.resolve() raises, falls back to legacy."""
        from unittest.mock import MagicMock

        from psdl.runtimes.cohort.compiler import CohortCompiler

        mock_ds = MagicMock()
        mock_ds.resolve.side_effect = KeyError("not found")

        compiler = CohortCompiler(schema="public", dataset_spec=mock_ds)
        mock_signal = MagicMock()
        mock_signal.ref = "creatinine"
        mock_signal.concept_id = 3016723
        mock_signal.domain = MagicMock()
        mock_signal.domain.value = "measurement"

        resolved = compiler._resolve_signal_binding("Cr", mock_signal)
        # Should fall through to legacy
        assert resolved["table"] == "public.measurement"
        assert "3016723" in resolved["filter_cond"]


# =============================================================================
# Gap Fix Tests: ResolvedSignal clinical_domain (Gap 4)
# =============================================================================


class TestResolvedSignalClinicalDomain:
    """Verify ResolvedSignal carries clinical_domain through compilation."""

    def test_resolved_signal_has_clinical_domain(self):
        """Compiling a scenario should populate clinical_domain on ResolvedSignal."""
        from psdl import compile_scenario

        yaml_content = """
scenario: TestCompile
version: "1.0"
signals:
  DX:
    ref: diagnosis
    domain: condition
trends:
  dx_current:
    expr: last(DX)
logic:
  has_dx:
    when: dx_current > 0
"""
        ir = compile_scenario(yaml_content)
        assert ir.signals["DX"].clinical_domain == "condition"

    def test_artifact_includes_clinical_domain(self):
        """to_artifact() should include clinical_domain in signal data."""
        from psdl import compile_scenario

        yaml_content = """
scenario: TestArtifact
version: "1.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_current:
    expr: last(Cr)
logic:
  high:
    when: cr_current > 1.2
"""
        ir = compile_scenario(yaml_content)
        artifact = ir.to_artifact()
        assert "clinical_domain" in artifact["signals"]["Cr"]
        assert artifact["signals"]["Cr"]["clinical_domain"] == "laboratory"


# =============================================================================
# Gap Fix Tests: ClinicalEvent source_ids (Gap 5)
# =============================================================================


class TestClinicalEventSourceIds:
    """Verify ClinicalEvent vendor-neutral source_ids bag."""

    def test_source_ids_default_empty(self):
        """New ClinicalEvent without vendor fields has empty source_ids."""
        from datetime import datetime

        from psdl.execution.streaming.models import ClinicalEvent

        event = ClinicalEvent(
            patient_id="p1",
            timestamp=datetime(2024, 1, 1),
            signal_type="HR",
            value=80.0,
            unit="bpm",
        )
        assert event.source_ids == {}

    def test_source_ids_direct(self):
        """source_ids can be set directly."""
        from datetime import datetime

        from psdl.execution.streaming.models import ClinicalEvent

        event = ClinicalEvent(
            patient_id="p1",
            timestamp=datetime(2024, 1, 1),
            signal_type="HR",
            value=80.0,
            unit="bpm",
            source_ids={"loinc_code": "8867-4"},
        )
        assert event.source_ids["loinc_code"] == "8867-4"

    def test_concept_id_deprecation_warning(self):
        """Setting concept_id should warn and auto-migrate to source_ids."""
        from datetime import datetime

        from psdl.execution.streaming.models import ClinicalEvent

        with pytest.warns(DeprecationWarning, match="concept_id is deprecated"):
            event = ClinicalEvent(
                patient_id="p1",
                timestamp=datetime(2024, 1, 1),
                signal_type="HR",
                value=80.0,
                unit="bpm",
                concept_id=3027018,
            )
        assert event.source_ids["concept_id"] == 3027018

    def test_fhir_resource_id_deprecation_warning(self):
        """Setting fhir_resource_id should warn and auto-migrate to source_ids."""
        from datetime import datetime

        from psdl.execution.streaming.models import ClinicalEvent

        with pytest.warns(DeprecationWarning, match="fhir_resource_id is deprecated"):
            event = ClinicalEvent(
                patient_id="p1",
                timestamp=datetime(2024, 1, 1),
                signal_type="HR",
                value=80.0,
                unit="bpm",
                fhir_resource_id="abc-123",
            )
        assert event.source_ids["fhir_resource_id"] == "abc-123"

    def test_to_dict_includes_source_ids(self):
        """to_dict() should serialize source_ids."""
        from datetime import datetime

        from psdl.execution.streaming.models import ClinicalEvent

        event = ClinicalEvent(
            patient_id="p1",
            timestamp=datetime(2024, 1, 1),
            signal_type="HR",
            value=80.0,
            unit="bpm",
            source_ids={"custom_key": "val"},
        )
        d = event.to_dict()
        assert d["source_ids"] == {"custom_key": "val"}

    def test_from_dict_reads_source_ids(self):
        """from_dict() should deserialize source_ids."""
        from psdl.execution.streaming.models import ClinicalEvent

        data = {
            "patient_id": "p1",
            "timestamp": "2024-01-01T00:00:00",
            "signal_type": "HR",
            "value": 80.0,
            "unit": "bpm",
            "source_ids": {"loinc": "8867-4"},
        }
        event = ClinicalEvent.from_dict(data)
        assert event.source_ids["loinc"] == "8867-4"


# =============================================================================
# Phase 2 Wiring: CohortCompiler inherits SQLBatchRuntime (#8)
# =============================================================================


class TestCohortCompilerSQLBatchRuntime:
    """Verify CohortCompiler properly inherits SQLBatchRuntime."""

    def test_isinstance_sql_batch_runtime(self):
        from psdl.runtimes.batch import SQLBatchRuntime
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        assert isinstance(compiler, SQLBatchRuntime)

    def test_isinstance_batch_runtime(self):
        from psdl.runtimes.batch import BatchRuntime
        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler()
        assert isinstance(compiler, BatchRuntime)

    def test_compile_with_dataset_spec_override(self):
        """compile(scenario, dataset_spec=...) should override self.dataset_spec."""
        from unittest.mock import MagicMock, patch

        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler(dataset_spec="original")

        # Mock _compile_impl to avoid actual compilation
        with patch.object(compiler, "_compile_impl") as mock_impl:
            mock_impl.return_value = MagicMock()
            compiler.compile("scenario", dataset_spec="override")

            # During compilation, dataset_spec should have been overridden
            mock_impl.assert_called_once_with("scenario")

        # After compilation, dataset_spec should be restored
        assert compiler.dataset_spec == "original"

    def test_compile_without_dataset_spec_keeps_original(self):
        """compile(scenario) without dataset_spec uses self.dataset_spec."""
        from unittest.mock import MagicMock, patch

        from psdl.runtimes.cohort.compiler import CohortCompiler

        compiler = CohortCompiler(dataset_spec="original")

        with patch.object(compiler, "_compile_impl") as mock_impl:
            mock_impl.return_value = MagicMock()
            compiler.compile("scenario")

        assert compiler.dataset_spec == "original"


# =============================================================================
# Phase 2 Wiring: OMOPBackend inherits BatchRuntime (#9)
# =============================================================================


class TestOMOPBackendBatchRuntime:
    """Verify OMOPBackend properly inherits BatchRuntime."""

    def test_isinstance_batch_runtime(self):
        from psdl.adapters.omop import OMOPBackend, OMOPConfig
        from psdl.runtimes.batch import BatchRuntime

        config = OMOPConfig(connection_string="sqlite:///test.db")
        backend = OMOPBackend(config)
        assert isinstance(backend, BatchRuntime)

    def test_capabilities_includes_sql(self):
        from psdl.adapters.omop import OMOPBackend, OMOPConfig

        config = OMOPConfig(connection_string="sqlite:///test.db")
        backend = OMOPBackend(config)
        assert "sql" in backend.capabilities
        assert "dataset_adapter" in backend.capabilities

    def test_compile_delegates_to_cohort_compiler(self):
        """OMOPBackend.compile() should delegate to CohortCompiler."""
        from unittest.mock import MagicMock, patch

        from psdl.adapters.omop import OMOPBackend, OMOPConfig

        config = OMOPConfig(connection_string="sqlite:///test.db")
        backend = OMOPBackend(config)

        mock_scenario = MagicMock()

        with patch("psdl.runtimes.cohort.CohortCompiler") as MockCompiler:
            mock_instance = MagicMock()
            MockCompiler.return_value = mock_instance
            mock_instance.compile.return_value = MagicMock()

            backend.compile(mock_scenario)

            MockCompiler.assert_called_once()
            mock_instance.compile.assert_called_once()

    def test_compile_uses_dataset_spec(self):
        """OMOPBackend.compile() passes dataset_spec to CohortCompiler."""
        from unittest.mock import MagicMock, patch

        from psdl.adapters.omop import OMOPBackend, OMOPConfig

        mock_ds = MagicMock()
        config = OMOPConfig(connection_string="sqlite:///test.db")
        backend = OMOPBackend(config, dataset_spec=mock_ds)

        with patch("psdl.runtimes.cohort.CohortCompiler") as MockCompiler:
            mock_instance = MagicMock()
            MockCompiler.return_value = mock_instance
            mock_instance.compile.return_value = MagicMock()

            backend.compile(MagicMock())

            # Verify dataset_spec was passed to CohortCompiler
            call_kwargs = MockCompiler.call_args[1]
            assert call_kwargs["dataset_spec"] is mock_ds


# =============================================================================
# Domain Deprecation Docstring
# =============================================================================


class TestDomainDeprecation:
    """Verify Domain enum has deprecation notice."""

    def test_domain_docstring_mentions_deprecated(self):
        assert "deprecated" in Domain.__doc__.lower()

    def test_domain_docstring_mentions_clinical_domain(self):
        assert "ClinicalDomain" in Domain.__doc__
