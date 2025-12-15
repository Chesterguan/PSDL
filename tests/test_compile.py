"""
Tests for PSDL Scenario Compiler.

Tests the RFC-0006 compilation architecture including:
- Canonical hashing (spec/hashing.yaml conformance)
- Structured diagnostics (error codes, source locations)
- Dependency DAG construction
- Dataset binding validation (Enhancement A)
- ScenarioIR artifact generation
"""

import hashlib
from datetime import datetime

import pytest

from psdl.core.compile import (
    CompilationDiagnostics,
    DependencyAnalysis,
    DependencyDAG,
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
    ScenarioCompiler,
    SourceLocation,
    canonicalize_json,
    compile_scenario,
    compute_sha256,
    compute_spec_hash,
    compute_toolchain_hash,
)
from psdl.core.parser import parse_scenario

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_scenario_yaml():
    """Simple v0.3 scenario with minimal complexity."""
    return """
scenario: SimpleTest
version: "1.0"
description: Test scenario for compiler

signals:
  Cr:
    ref: creatinine
    concept_id: 3016723
    unit: mg/dL

trends:
  cr_delta:
    expr: delta(Cr, 48h)

logic:
  acute_rise:
    when: cr_delta > 0.3
    severity: medium
"""


@pytest.fixture
def multi_signal_scenario_yaml():
    """Scenario with multiple signals and trends."""
    return """
scenario: MultiSignalTest
version: "1.0"
description: Test scenario with multiple signals

signals:
  Cr:
    ref: creatinine
    concept_id: 3016723
    unit: mg/dL
  BUN:
    ref: blood_urea_nitrogen
    concept_id: 3004501
    unit: mg/dL
  HR:
    ref: heart_rate
    concept_id: 3027018
    unit: bpm

trends:
  cr_delta:
    expr: delta(Cr, 48h)
  bun_slope:
    expr: slope(BUN, 24h)
  hr_avg:
    expr: sma(HR, 6h)

logic:
  kidney_alert:
    when: cr_delta > 0.3 AND bun_slope > 0
    severity: high
  cardiac_alert:
    when: hr_avg > 100
    severity: medium
"""


@pytest.fixture
def scenario_with_unused_entities_yaml():
    """Scenario with unused signals and trends."""
    return """
scenario: UnusedEntitiesTest
version: "1.0"
description: Test unused entity detection

signals:
  Cr:
    ref: creatinine
    unit: mg/dL
  UnusedSignal:
    ref: unused_signal
    unit: mmol/L

trends:
  cr_delta:
    expr: delta(Cr, 48h)
  unused_trend:
    expr: sma(Cr, 24h)

logic:
  alert:
    when: cr_delta > 0.3
    severity: medium
"""


@pytest.fixture
def compiled_simple_ir(simple_scenario_yaml):
    """Pre-compiled IR for simple scenario."""
    scenario = parse_scenario(simple_scenario_yaml)
    compiler = ScenarioCompiler()
    return compiler.compile(scenario, simple_scenario_yaml)


# =============================================================================
# Canonical Hashing Tests (spec/hashing.yaml conformance)
# =============================================================================


class TestCanonicalHashing:
    """Tests for canonical hashing functions per spec/hashing.yaml."""

    def test_canonicalize_json_sort_keys(self):
        """Canonical JSON should sort keys alphabetically."""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonicalize_json(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_canonicalize_json_no_whitespace(self):
        """Canonical JSON should have no extra whitespace."""
        obj = {"key": "value", "nested": {"inner": 123}}
        result = canonicalize_json(obj)
        assert " " not in result
        assert "\n" not in result
        assert result == '{"key":"value","nested":{"inner":123}}'

    def test_canonicalize_json_unicode(self):
        """Canonical JSON should allow Unicode (ensure_ascii=false)."""
        obj = {"name": "测试", "emoji": "✓"}
        result = canonicalize_json(obj)
        assert "测试" in result
        assert "✓" in result

    def test_compute_sha256_output_format(self):
        """SHA-256 should return 64 lowercase hex characters."""
        content = "test content"
        result = compute_sha256(content)
        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    def test_compute_sha256_deterministic(self):
        """Same content should produce same hash."""
        content = "reproducible content"
        hash1 = compute_sha256(content)
        hash2 = compute_sha256(content)
        assert hash1 == hash2

    def test_compute_sha256_different_content(self):
        """Different content should produce different hash."""
        hash1 = compute_sha256("content 1")
        hash2 = compute_sha256("content 2")
        assert hash1 != hash2

    def test_compute_sha256_matches_stdlib(self):
        """Should match Python stdlib hashlib."""
        content = "verification content"
        result = compute_sha256(content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert result == expected


class TestSpecHash:
    """Tests for spec_hash computation."""

    def test_spec_hash_format(self, simple_scenario_yaml):
        """spec_hash should be 64 hex characters."""
        scenario = parse_scenario(simple_scenario_yaml)
        hash_value = compute_spec_hash(scenario)
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_spec_hash_deterministic(self, simple_scenario_yaml):
        """Same scenario should produce same spec_hash."""
        scenario = parse_scenario(simple_scenario_yaml)
        hash1 = compute_spec_hash(scenario)
        hash2 = compute_spec_hash(scenario)
        assert hash1 == hash2

    def test_spec_hash_excludes_description(self):
        """Descriptions should not affect spec_hash."""
        yaml1 = """
scenario: Test
version: "1.0"
description: Description One
signals:
  Cr:
    ref: creatinine
trends:
  cr_delta:
    expr: delta(Cr, 6h)
logic:
  alert:
    when: cr_delta > 0
"""
        yaml2 = """
scenario: Test
version: "1.0"
description: Different Description
signals:
  Cr:
    ref: creatinine
trends:
  cr_delta:
    expr: delta(Cr, 6h)
logic:
  alert:
    when: cr_delta > 0
"""
        scenario1 = parse_scenario(yaml1)
        scenario2 = parse_scenario(yaml2)
        # Note: Actually descriptions are not part of spec_hash, so they should match
        hash1 = compute_spec_hash(scenario1)
        hash2 = compute_spec_hash(scenario2)
        assert hash1 == hash2

    def test_spec_hash_different_for_different_signals(self):
        """Different signals should produce different spec_hash."""
        yaml1 = """
scenario: Test
version: "1.0"
signals:
  Cr:
    ref: creatinine
trends:
  delta1:
    expr: delta(Cr, 6h)
logic:
  alert:
    when: delta1 > 0
"""
        yaml2 = """
scenario: Test
version: "1.0"
signals:
  BUN:
    ref: blood_urea_nitrogen
trends:
  delta1:
    expr: delta(BUN, 6h)
logic:
  alert:
    when: delta1 > 0
"""
        scenario1 = parse_scenario(yaml1)
        scenario2 = parse_scenario(yaml2)
        hash1 = compute_spec_hash(scenario1)
        hash2 = compute_spec_hash(scenario2)
        assert hash1 != hash2


class TestIRHash:
    """Tests for ir_hash computation."""

    def test_ir_hash_format(self, compiled_simple_ir):
        """ir_hash should be 64 hex characters."""
        assert len(compiled_simple_ir.ir_hash) == 64
        assert all(c in "0123456789abcdef" for c in compiled_simple_ir.ir_hash)

    def test_ir_hash_deterministic(self, simple_scenario_yaml):
        """Same IR should produce same ir_hash."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir1 = compiler.compile(scenario, simple_scenario_yaml)
        ir2 = compiler.compile(scenario, simple_scenario_yaml)
        assert ir1.ir_hash == ir2.ir_hash


class TestToolchainHash:
    """Tests for toolchain_hash computation."""

    def test_toolchain_hash_format(self):
        """toolchain_hash should be 64 hex characters."""
        hash_value = compute_toolchain_hash()
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_toolchain_hash_deterministic(self):
        """Same toolchain should produce same hash."""
        hash1 = compute_toolchain_hash()
        hash2 = compute_toolchain_hash()
        assert hash1 == hash2

    def test_toolchain_hash_in_ir(self, compiled_simple_ir):
        """Compiled IR should include toolchain_hash."""
        assert compiled_simple_ir.toolchain_hash
        assert len(compiled_simple_ir.toolchain_hash) == 64


# =============================================================================
# Scenario Compiler Tests
# =============================================================================


class TestScenarioCompiler:
    """Tests for ScenarioCompiler class."""

    def test_compile_simple_scenario(self, simple_scenario_yaml):
        """Compiler should produce valid IR for simple scenario."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert ir.scenario_name == "SimpleTest"
        assert ir.scenario_version == "1.0"
        assert ir.compilation.success

    def test_compile_resolves_signals(self, simple_scenario_yaml):
        """Compiler should resolve all signals."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert "Cr" in ir.signals
        assert ir.signals["Cr"].ref == "creatinine"
        assert ir.signals["Cr"].concept_id == 3016723
        assert ir.signals["Cr"].unit == "mg/dL"

    def test_compile_resolves_trends(self, simple_scenario_yaml):
        """Compiler should resolve trends with dependencies."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert "cr_delta" in ir.trends
        assert ir.trends["cr_delta"].raw_expr == "delta(Cr, 48h)"
        assert "Cr" in ir.trends["cr_delta"].signals_used
        assert ir.trends["cr_delta"].return_type == "numeric"

    def test_compile_resolves_logic(self, simple_scenario_yaml):
        """Compiler should resolve logic with dependencies."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert "acute_rise" in ir.logic
        assert "cr_delta" in ir.logic["acute_rise"].trends_used
        assert ir.logic["acute_rise"].severity == "medium"

    def test_compile_builds_dag(self, multi_signal_scenario_yaml):
        """Compiler should build correct dependency DAG."""
        scenario = parse_scenario(multi_signal_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, multi_signal_scenario_yaml)

        # Check signal order
        assert set(ir.dag.signal_order) == {"Cr", "BUN", "HR"}

        # Check trend order
        assert set(ir.dag.trend_order) == {"cr_delta", "bun_slope", "hr_avg"}

        # Check logic order
        assert set(ir.dag.logic_order) == {"kidney_alert", "cardiac_alert"}

    def test_compile_includes_hashes(self, simple_scenario_yaml):
        """Compiled IR should include all three hashes."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert ir.spec_hash and len(ir.spec_hash) == 64
        assert ir.ir_hash and len(ir.ir_hash) == 64
        assert ir.toolchain_hash and len(ir.toolchain_hash) == 64

    def test_compile_includes_timestamp(self, simple_scenario_yaml):
        """Compiled IR should include compilation timestamp."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert ir.compiled_at is not None
        assert isinstance(ir.compiled_at, datetime)


class TestCompilationDiagnostics:
    """Tests for structured compilation diagnostics."""

    def test_diagnostics_success_on_valid_scenario(self, simple_scenario_yaml):
        """Valid scenario should have success=True."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        assert ir.compilation.success is True
        assert len(ir.compilation.errors) == 0

    def test_diagnostics_detects_unused_signal(self, scenario_with_unused_entities_yaml):
        """Compiler should warn about unused signals."""
        scenario = parse_scenario(scenario_with_unused_entities_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, scenario_with_unused_entities_yaml)

        # Should still succeed (warnings don't fail compilation)
        assert ir.compilation.success

        # Should have warning about unused signal
        warnings = ir.compilation.warnings
        unused_signal_warnings = [w for w in warnings if "UnusedSignal" in w]
        assert len(unused_signal_warnings) > 0

    def test_diagnostics_detects_unused_trend(self, scenario_with_unused_entities_yaml):
        """Compiler should warn about unused trends."""
        scenario = parse_scenario(scenario_with_unused_entities_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, scenario_with_unused_entities_yaml)

        # Should have warning about unused trend
        warnings = ir.compilation.warnings
        unused_trend_warnings = [w for w in warnings if "unused_trend" in w]
        assert len(unused_trend_warnings) > 0

    def test_diagnostics_dependency_analysis(self, scenario_with_unused_entities_yaml):
        """Compiler should include dependency analysis."""
        scenario = parse_scenario(scenario_with_unused_entities_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, scenario_with_unused_entities_yaml)

        dep_analysis = ir.compilation.dependency_analysis
        assert dep_analysis is not None
        assert "UnusedSignal" in dep_analysis.unused_signals
        assert "unused_trend" in dep_analysis.unused_trends

    def test_diagnostics_type_analysis(self, simple_scenario_yaml):
        """Compiler should include type analysis."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        type_analysis = ir.compilation.type_analysis
        assert type_analysis is not None
        assert type_analysis.signal_types.get("Cr") == "timeseries"
        assert type_analysis.trend_types.get("cr_delta") == "numeric"
        assert type_analysis.logic_types.get("acute_rise") == "boolean"


class TestDiagnosticStructure:
    """Tests for Diagnostic and related classes."""

    def test_diagnostic_code_constants(self):
        """DiagnosticCode should have expected constants."""
        assert DiagnosticCode.SIGNAL_NOT_FOUND == "S100"
        assert DiagnosticCode.TREND_UNKNOWN_SIGNAL == "T101"
        assert DiagnosticCode.LOGIC_UNKNOWN_TERM == "L101"
        assert DiagnosticCode.DAG_CIRCULAR_DEPENDENCY == "D100"
        assert DiagnosticCode.UNUSED_SIGNAL == "W100"
        assert DiagnosticCode.UNUSED_TREND == "W101"

    def test_diagnostic_severity_constants(self):
        """DiagnosticSeverity should have expected constants."""
        assert DiagnosticSeverity.ERROR == "error"
        assert DiagnosticSeverity.WARNING == "warning"
        assert DiagnosticSeverity.INFO == "info"
        assert DiagnosticSeverity.HINT == "hint"

    def test_source_location_structure(self):
        """SourceLocation should store location info."""
        loc = SourceLocation(line=10, column=5, node_path="trends.cr_delta.expr")
        assert loc.line == 10
        assert loc.column == 5
        assert loc.node_path == "trends.cr_delta.expr"

    def test_diagnostic_to_dict(self):
        """Diagnostic should serialize to dict correctly."""
        diag = Diagnostic(
            code=DiagnosticCode.TREND_UNKNOWN_SIGNAL,
            severity=DiagnosticSeverity.ERROR,
            message="Unknown signal 'Foo'",
            location=SourceLocation(node_path="trends.test.expr"),
            related_nodes=["Foo"],
            suggestion="Define signal 'Foo' in signals section",
        )
        result = diag.to_dict()

        assert result["code"] == "T101"
        assert result["severity"] == "error"
        assert result["message"] == "Unknown signal 'Foo'"
        assert result["location"]["node_path"] == "trends.test.expr"
        assert result["related_nodes"] == ["Foo"]
        assert result["suggestion"] == "Define signal 'Foo' in signals section"

    def test_compilation_diagnostics_add_error(self):
        """CompilationDiagnostics should track errors correctly."""
        diag = CompilationDiagnostics(success=True)
        assert diag.success is True

        diag.add_error(
            code=DiagnosticCode.SIGNAL_NOT_FOUND,
            message="Signal not found",
        )

        assert diag.success is False
        assert len(diag.errors) == 1
        assert diag.errors[0] == "Signal not found"

    def test_compilation_diagnostics_add_warning(self):
        """CompilationDiagnostics should track warnings correctly."""
        diag = CompilationDiagnostics(success=True)

        diag.add_warning(
            code=DiagnosticCode.UNUSED_SIGNAL,
            message="Unused signal",
        )

        assert diag.success is True  # Warnings don't fail
        assert len(diag.warnings) == 1
        assert diag.warnings[0] == "Unused signal"

    def test_compilation_diagnostics_to_dict(self):
        """CompilationDiagnostics should serialize to dict."""
        diag = CompilationDiagnostics(success=True)
        diag.add_warning(code="W100", message="Test warning")
        diag.dependency_analysis = DependencyAnalysis(
            unused_signals={"UnusedSignal"},
            unused_trends={"unused_trend"},
        )

        result = diag.to_dict()

        assert result["success"] is True
        assert result["error_count"] == 0
        assert result["warning_count"] == 1
        assert "UnusedSignal" in result["dependency_analysis"]["unused_signals"]


# =============================================================================
# Dataset Binding Validation Tests (Enhancement A)
# =============================================================================


class TestDatasetBindingValidation:
    """Tests for dataset binding validation (Enhancement A)."""

    def test_compile_without_dataset_spec(self, simple_scenario_yaml):
        """Compilation without dataset_spec should succeed."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml, dataset_spec=None)

        assert ir.compilation.success

    def test_compile_with_matching_dataset_spec(self, simple_scenario_yaml):
        """Compilation with matching dataset_spec should succeed."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()

        dataset_spec = {
            "refs": {"creatinine": True},
            "types": {
                "creatinine": {"unit": "mg/dL"},
            },
        }

        ir = compiler.compile(scenario, simple_scenario_yaml, dataset_spec=dataset_spec)

        assert ir.compilation.success
        # Should have no dataset binding warnings
        binding_warnings = [w for w in ir.compilation.warnings if "not found in dataset" in w]
        assert len(binding_warnings) == 0

    def test_compile_with_missing_ref(self, simple_scenario_yaml):
        """Compilation with missing ref should produce warning."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()

        dataset_spec = {
            "refs": {},  # No refs defined
            "types": {},
        }

        ir = compiler.compile(scenario, simple_scenario_yaml, dataset_spec=dataset_spec)

        # Should succeed but with warning
        assert ir.compilation.success
        binding_warnings = [w for w in ir.compilation.warnings if "not found in dataset" in w]
        assert len(binding_warnings) > 0


# =============================================================================
# Dependency DAG Tests
# =============================================================================


class TestDependencyDAG:
    """Tests for DependencyDAG class."""

    def test_dag_structure(self):
        """DependencyDAG should have correct structure."""
        dag = DependencyDAG(
            signal_order=["Cr", "BUN"],
            trend_order=["cr_delta", "bun_slope"],
            logic_order=["alert"],
        )

        assert dag.signal_order == ["Cr", "BUN"]
        assert dag.trend_order == ["cr_delta", "bun_slope"]
        assert dag.logic_order == ["alert"]

    def test_dag_evaluation_order(self):
        """get_evaluation_order should return signals -> trends -> logic."""
        dag = DependencyDAG(
            signal_order=["Cr"],
            trend_order=["cr_delta"],
            logic_order=["alert"],
        )

        order = dag.get_evaluation_order()

        assert order == ["Cr", "cr_delta", "alert"]
        assert order.index("Cr") < order.index("cr_delta")
        assert order.index("cr_delta") < order.index("alert")


# =============================================================================
# Scenario IR Tests
# =============================================================================


class TestScenarioIR:
    """Tests for ScenarioIR class."""

    def test_ir_metadata(self, compiled_simple_ir):
        """IR should contain correct metadata."""
        assert compiled_simple_ir.scenario_name == "SimpleTest"
        assert compiled_simple_ir.scenario_version == "1.0"
        assert compiled_simple_ir.psdl_version is not None

    def test_ir_to_artifact(self, compiled_simple_ir):
        """IR should serialize to audit artifact correctly."""
        artifact = compiled_simple_ir.to_artifact()

        assert artifact["artifact_version"] == "1.0"
        assert artifact["scenario"]["name"] == "SimpleTest"
        assert artifact["hashes"]["spec_hash"] == compiled_simple_ir.spec_hash
        assert artifact["hashes"]["ir_hash"] == compiled_simple_ir.ir_hash
        assert artifact["hashes"]["toolchain_hash"] == compiled_simple_ir.toolchain_hash

    def test_ir_artifact_contains_dag(self, compiled_simple_ir):
        """Artifact should contain DAG information."""
        artifact = compiled_simple_ir.to_artifact()

        assert "dag" in artifact
        assert "signal_order" in artifact["dag"]
        assert "trend_order" in artifact["dag"]
        assert "logic_order" in artifact["dag"]
        assert "evaluation_order" in artifact["dag"]

    def test_ir_artifact_contains_signals(self, compiled_simple_ir):
        """Artifact should contain signal information."""
        artifact = compiled_simple_ir.to_artifact()

        assert "signals" in artifact
        assert "Cr" in artifact["signals"]
        assert artifact["signals"]["Cr"]["ref"] == "creatinine"

    def test_ir_artifact_contains_trends(self, compiled_simple_ir):
        """Artifact should contain trend information."""
        artifact = compiled_simple_ir.to_artifact()

        assert "trends" in artifact
        assert "cr_delta" in artifact["trends"]
        assert artifact["trends"]["cr_delta"]["expr"] == "delta(Cr, 48h)"
        assert "Cr" in artifact["trends"]["cr_delta"]["signals_used"]

    def test_ir_artifact_contains_logic(self, compiled_simple_ir):
        """Artifact should contain logic information."""
        artifact = compiled_simple_ir.to_artifact()

        assert "logic" in artifact
        assert "acute_rise" in artifact["logic"]
        assert artifact["logic"]["acute_rise"]["severity"] == "medium"


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestCompileScenarioFunction:
    """Tests for compile_scenario convenience function."""

    def test_compile_from_yaml_string(self, simple_scenario_yaml):
        """compile_scenario should accept YAML string."""
        ir = compile_scenario(simple_scenario_yaml)

        assert ir.scenario_name == "SimpleTest"
        assert ir.compilation.success

    def test_compile_from_file(self, tmp_path, simple_scenario_yaml):
        """compile_scenario should accept file path."""
        # Write scenario to temp file
        scenario_file = tmp_path / "test_scenario.yaml"
        scenario_file.write_text(simple_scenario_yaml)

        ir = compile_scenario(str(scenario_file))

        assert ir.scenario_name == "SimpleTest"
        assert ir.compilation.success


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestCompilerErrorHandling:
    """Tests for compiler error handling."""

    def test_unused_entities_produce_warnings(self, scenario_with_unused_entities_yaml):
        """Compiler should detect unused signals and trends."""
        scenario = parse_scenario(scenario_with_unused_entities_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, scenario_with_unused_entities_yaml)

        # Should succeed but with warnings
        assert ir.compilation.success is True
        assert any("UnusedSignal" in w for w in ir.compilation.warnings)
        assert any("unused_trend" in w for w in ir.compilation.warnings)

    def test_compile_captures_dependency_analysis(self, simple_scenario_yaml):
        """Compiler should capture dependency relationships."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        # Should have dependency analysis
        dep_analysis = ir.compilation.dependency_analysis
        assert dep_analysis is not None

        # Signal to trend dependencies should be tracked
        assert "Cr" in dep_analysis.signal_to_trends
        assert "cr_delta" in dep_analysis.signal_to_trends["Cr"]

    def test_compile_captures_type_analysis(self, simple_scenario_yaml):
        """Compiler should capture type analysis."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()
        ir = compiler.compile(scenario, simple_scenario_yaml)

        # Should have type analysis
        type_analysis = ir.compilation.type_analysis
        assert type_analysis is not None
        assert type_analysis.signal_types.get("Cr") == "timeseries"
        assert type_analysis.trend_types.get("cr_delta") == "numeric"
        assert type_analysis.logic_types.get("acute_rise") == "boolean"


# =============================================================================
# Hash Reproducibility Tests
# =============================================================================


class TestHashReproducibility:
    """Tests for hash reproducibility guarantees."""

    def test_spec_hash_stable_across_compilations(self, simple_scenario_yaml):
        """spec_hash should be identical across compilations."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()

        ir1 = compiler.compile(scenario, simple_scenario_yaml)
        ir2 = compiler.compile(scenario, simple_scenario_yaml)

        assert ir1.spec_hash == ir2.spec_hash

    def test_ir_hash_stable_across_compilations(self, simple_scenario_yaml):
        """ir_hash should be identical across compilations."""
        scenario = parse_scenario(simple_scenario_yaml)
        compiler = ScenarioCompiler()

        ir1 = compiler.compile(scenario, simple_scenario_yaml)
        ir2 = compiler.compile(scenario, simple_scenario_yaml)

        assert ir1.ir_hash == ir2.ir_hash

    def test_different_scenarios_different_hashes(self):
        """Different scenarios should produce different hashes."""
        yaml1 = """
scenario: Scenario1
version: "1.0"
signals:
  Cr:
    ref: creatinine
trends:
  delta1:
    expr: delta(Cr, 6h)
logic:
  alert:
    when: delta1 > 0
"""
        yaml2 = """
scenario: Scenario2
version: "1.0"
signals:
  BUN:
    ref: blood_urea_nitrogen
trends:
  delta1:
    expr: delta(BUN, 6h)
logic:
  alert:
    when: delta1 > 0
"""
        ir1 = compile_scenario(yaml1)
        ir2 = compile_scenario(yaml2)

        assert ir1.spec_hash != ir2.spec_hash
        assert ir1.ir_hash != ir2.ir_hash
