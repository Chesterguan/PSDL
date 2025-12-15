"""
PSDL Scenario Compiler - Compiles parsed scenarios to executable IR.

This module transforms a parsed PSDLScenario into a compiled ScenarioIR
with resolved dependencies, topologically sorted DAG, and content hashes
for audit/reproducibility.

RFC-0006: Spec-Driven Compilation Architecture

Hashing Specification (spec/hashing.yaml):
- algorithm: SHA-256 (full 64 hex characters)
- canonicalization: sorted keys, no whitespace, compact JSON
- toolchain_hash: includes psdl-lang version, Python version, spec version

Usage:
    from psdl.core.compile import compile_scenario, ScenarioCompiler

    # From file
    ir = compile_scenario("scenarios/aki_detection.yaml")

    # From parsed scenario
    compiler = ScenarioCompiler()
    ir = compiler.compile(scenario, source_yaml)

    # Save audit artifact
    ir.save_artifact("aki_detection.compiled.json")

    # Access hashes
    print(ir.spec_hash)      # Hash of canonical YAML
    print(ir.ir_hash)        # Hash of normalized IR
    print(ir.toolchain_hash) # Hash of compilation toolchain
"""

__all__ = [
    # Core classes
    "ScenarioCompiler",
    "ScenarioIR",
    "ResolvedSignal",
    "ResolvedTrend",
    "ResolvedLogic",
    "DependencyDAG",
    # Diagnostics
    "CompilationDiagnostics",
    "DiagnosticSeverity",
    "DiagnosticCode",
    "SourceLocation",
    "Diagnostic",
    "DependencyAnalysis",
    "TypeAnalysis",
    # Hashing functions
    "canonicalize_json",
    "compute_sha256",
    "compute_spec_hash",
    "compute_ir_hash",
    "compute_toolchain_hash",
    # Convenience function
    "compile_scenario",
]

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psdl
from psdl._generated.ast_types import (
    AndExpr,
    ArithExpr,
    ComparisonExpr,
    NotExpr,
    OrExpr,
    TemporalCall,
    TermRef,
    TrendExpression,
)
from psdl.core.ir import LogicExpr, PSDLScenario, TrendExpr


@dataclass
class ResolvedSignal:
    """Signal with resolved metadata."""

    name: str
    ref: str
    concept_id: Optional[int] = None
    unit: Optional[str] = None
    domain: str = "measurement"


@dataclass
class ResolvedTrend:
    """Trend with parsed AST and resolved dependencies."""

    name: str
    raw_expr: str
    ast: Any  # TrendExpression or ArithExpr
    signals_used: Set[str] = field(default_factory=set)
    trends_used: Set[str] = field(default_factory=set)
    return_type: str = "numeric"


@dataclass
class ResolvedLogic:
    """Logic rule with parsed AST and resolved dependencies."""

    name: str
    raw_expr: str
    ast: Any  # LogicNode
    trends_used: Set[str] = field(default_factory=set)
    logic_used: Set[str] = field(default_factory=set)
    severity: Optional[str] = None


@dataclass
class DependencyDAG:
    """Topologically sorted dependency graph."""

    signal_order: List[str] = field(default_factory=list)
    trend_order: List[str] = field(default_factory=list)
    logic_order: List[str] = field(default_factory=list)

    def get_evaluation_order(self) -> List[str]:
        """Return full evaluation order: signals -> trends -> logic."""
        return self.signal_order + self.trend_order + self.logic_order


# =============================================================================
# Compilation Diagnostics (H3: Full Structure)
# =============================================================================


class DiagnosticSeverity:
    """Severity levels for compilation diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class DiagnosticCode:
    """Standardized diagnostic codes for compilation issues."""

    # Signal errors (S1xx)
    SIGNAL_NOT_FOUND = "S100"
    SIGNAL_DUPLICATE = "S101"
    SIGNAL_INVALID_REF = "S102"

    # Trend errors (T1xx)
    TREND_INVALID_EXPR = "T100"
    TREND_UNKNOWN_SIGNAL = "T101"
    TREND_UNKNOWN_OPERATOR = "T102"
    TREND_INVALID_WINDOW = "T103"
    TREND_COMPARISON_IN_V03 = "T104"  # v0.3 strict: no comparisons in trends

    # Logic errors (L1xx)
    LOGIC_INVALID_EXPR = "L100"
    LOGIC_UNKNOWN_TERM = "L101"
    LOGIC_CIRCULAR_REF = "L102"
    LOGIC_TYPE_MISMATCH = "L103"

    # DAG errors (D1xx)
    DAG_CIRCULAR_DEPENDENCY = "D100"
    DAG_UNREACHABLE_NODE = "D101"

    # Warnings (W1xx)
    UNUSED_SIGNAL = "W100"
    UNUSED_TREND = "W101"
    DEPRECATED_SYNTAX = "W102"
    PERFORMANCE_HINT = "W103"


@dataclass
class SourceLocation:
    """Location in source YAML for diagnostic messages."""

    line: Optional[int] = None
    column: Optional[int] = None
    node_path: Optional[str] = None  # e.g., "trends.cr_delta.expr"


@dataclass
class Diagnostic:
    """A single compilation diagnostic (error, warning, info, hint)."""

    code: str
    severity: str
    message: str
    location: Optional[SourceLocation] = None
    related_nodes: List[str] = field(default_factory=list)
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for artifact output."""
        result = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.location:
            result["location"] = {
                "line": self.location.line,
                "column": self.location.column,
                "node_path": self.location.node_path,
            }
        if self.related_nodes:
            result["related_nodes"] = self.related_nodes
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result


@dataclass
class DependencyAnalysis:
    """Results of dependency analysis during compilation."""

    # Direct dependencies
    signal_to_trends: Dict[str, Set[str]] = field(default_factory=dict)
    trend_to_logic: Dict[str, Set[str]] = field(default_factory=dict)
    logic_to_logic: Dict[str, Set[str]] = field(default_factory=dict)

    # Reverse dependencies (what depends on this)
    trend_dependents: Dict[str, Set[str]] = field(default_factory=dict)
    logic_dependents: Dict[str, Set[str]] = field(default_factory=dict)

    # Unused entities
    unused_signals: Set[str] = field(default_factory=set)
    unused_trends: Set[str] = field(default_factory=set)

    # Circular references detected
    circular_refs: List[List[str]] = field(default_factory=list)


@dataclass
class TypeAnalysis:
    """Results of type checking during compilation."""

    # Expected types for each node
    signal_types: Dict[str, str] = field(default_factory=dict)  # signal -> "timeseries"
    trend_types: Dict[str, str] = field(default_factory=dict)  # trend -> "numeric"
    logic_types: Dict[str, str] = field(default_factory=dict)  # logic -> "boolean"

    # Type mismatches found
    mismatches: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class CompilationDiagnostics:
    """
    Full compilation diagnostics with structured errors, warnings, and analysis.

    This replaces the simple CompilationResult with a comprehensive structure
    suitable for IDE integration, CI/CD pipelines, and audit trails.
    """

    # Overall status
    success: bool

    # Structured diagnostics
    diagnostics: List[Diagnostic] = field(default_factory=list)

    # Analysis results
    dependency_analysis: Optional[DependencyAnalysis] = None
    type_analysis: Optional[TypeAnalysis] = None

    # Legacy compatibility (simple string lists)
    @property
    def errors(self) -> List[str]:
        """Legacy accessor: list of error messages."""
        return [d.message for d in self.diagnostics if d.severity == DiagnosticSeverity.ERROR]

    @property
    def warnings(self) -> List[str]:
        """Legacy accessor: list of warning messages."""
        return [d.message for d in self.diagnostics if d.severity == DiagnosticSeverity.WARNING]

    def add_error(
        self,
        code: str,
        message: str,
        location: Optional[SourceLocation] = None,
        related_nodes: Optional[List[str]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """Add an error diagnostic."""
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=DiagnosticSeverity.ERROR,
                message=message,
                location=location,
                related_nodes=related_nodes or [],
                suggestion=suggestion,
            )
        )
        self.success = False

    def add_warning(
        self,
        code: str,
        message: str,
        location: Optional[SourceLocation] = None,
        related_nodes: Optional[List[str]] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """Add a warning diagnostic."""
        self.diagnostics.append(
            Diagnostic(
                code=code,
                severity=DiagnosticSeverity.WARNING,
                message=message,
                location=location,
                related_nodes=related_nodes or [],
                suggestion=suggestion,
            )
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for artifact output."""
        result = {
            "success": self.success,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "error_count": len(
                [d for d in self.diagnostics if d.severity == DiagnosticSeverity.ERROR]
            ),
            "warning_count": len(
                [d for d in self.diagnostics if d.severity == DiagnosticSeverity.WARNING]
            ),
        }
        if self.dependency_analysis:
            result["dependency_analysis"] = {
                "unused_signals": sorted(self.dependency_analysis.unused_signals),
                "unused_trends": sorted(self.dependency_analysis.unused_trends),
                "circular_refs": self.dependency_analysis.circular_refs,
            }
        if self.type_analysis and self.type_analysis.mismatches:
            result["type_mismatches"] = self.type_analysis.mismatches
        return result


# Legacy alias for backwards compatibility
CompilationResult = CompilationDiagnostics


@dataclass
class ScenarioIR:
    """
    Compiled intermediate representation of a PSDL scenario.

    This is the executable artifact - immutable after compilation.
    Used for:
    - Runtime evaluation (DAG-ordered execution)
    - Audit/reproducibility (hash verification)
    - Multi-site deployment (deterministic execution)

    Hashes (spec/hashing.yaml):
    - spec_hash: SHA-256 of canonical scenario YAML
    - ir_hash: SHA-256 of normalized IR (deterministic)
    - toolchain_hash: SHA-256 of compilation toolchain info
    """

    # Metadata
    scenario_name: str
    scenario_version: str
    psdl_version: str
    compiled_at: datetime

    # Content hashes for reproducibility (full SHA-256, 64 hex chars)
    spec_hash: str
    ir_hash: str
    toolchain_hash: str  # toolchain hash

    # Resolved content
    signals: Dict[str, ResolvedSignal]
    trends: Dict[str, ResolvedTrend]
    logic: Dict[str, ResolvedLogic]

    # Dependency graph
    dag: DependencyDAG

    # Compilation status
    compilation: CompilationResult

    # Original source (for audit)
    source_yaml: str

    # Original scenario (for backwards compatibility)
    scenario: Optional[PSDLScenario] = None

    def to_artifact(self) -> dict:
        """
        Serialize to audit artifact.

        This is the immutable snapshot for IRB/FDA submission.
        """
        return {
            "artifact_version": "1.0",
            "scenario": {
                "name": self.scenario_name,
                "version": self.scenario_version,
            },
            "psdl_version": self.psdl_version,
            "compiled_at": self.compiled_at.isoformat(),
            "hashes": {
                "spec_hash": self.spec_hash,
                "ir_hash": self.ir_hash,
                "toolchain_hash": self.toolchain_hash,
            },
            "dag": {
                "signal_order": self.dag.signal_order,
                "trend_order": self.dag.trend_order,
                "logic_order": self.dag.logic_order,
                "evaluation_order": self.dag.get_evaluation_order(),
            },
            "signals": {
                name: {
                    "ref": s.ref,
                    "concept_id": s.concept_id,
                    "unit": s.unit,
                    "domain": s.domain,
                }
                for name, s in self.signals.items()
            },
            "trends": {
                name: {
                    "expr": t.raw_expr,
                    "signals_used": sorted(t.signals_used),
                    "trends_used": sorted(t.trends_used),
                    "return_type": t.return_type,
                }
                for name, t in self.trends.items()
            },
            "logic": {
                name: {
                    "expr": l.raw_expr,
                    "trends_used": sorted(l.trends_used),
                    "logic_used": sorted(l.logic_used),
                    "severity": l.severity,
                }
                for name, l in self.logic.items()
            },
            "compilation": {
                "success": self.compilation.success,
                "errors": self.compilation.errors,
                "warnings": self.compilation.warnings,
            },
        }

    def save_artifact(self, path: str) -> None:
        """Save compiled artifact to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_artifact(), f, indent=2)


# =============================================================================
# Canonical Hashing Functions (spec/hashing.yaml)
# =============================================================================


def canonicalize_json(obj: Any) -> str:
    """
    Convert object to canonical JSON for hashing.

    Per spec/hashing.yaml:
    - sort_keys: true
    - separators: (',', ':') - no whitespace
    - ensure_ascii: false - allow Unicode
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_sha256(content: str) -> str:
    """
    Compute SHA-256 hash of content.

    Per spec/hashing.yaml:
    - algorithm: sha256
    - output_format: hex (lowercase)
    - output_length: 64 characters
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_spec_hash(scenario: PSDLScenario) -> str:
    """
    Compute hash of canonical PSDL specification.

    Per spec/hashing.yaml hash_types.spec_hash:
    - Includes: scenario_name, version, signals, trends, logic, population
    - Excludes: descriptions, comments, whitespace formatting
    """
    # Build canonical representation (excluding descriptions)
    spec_content = {
        "name": scenario.name,
        "version": scenario.version,
        "signals": {
            name: {
                "source": s.ref or s.source,
                "concept_id": s.concept_id,
                "unit": s.unit,
                "domain": s.domain.value if s.domain else None,
            }
            for name, s in sorted(scenario.signals.items())
        },
        "trends": {
            name: {
                "operator": t.operator,
                "signal": t.signal,
                "window": str(t.window) if t.window else None,
                "raw_expr": t.raw_expr,
            }
            for name, t in sorted(scenario.trends.items())
        },
        "logic": {
            name: {
                "expr": l.expr,
                "severity": l.severity.value if l.severity else None,
            }
            for name, l in sorted(scenario.logic.items())
        },
    }

    # Add population if present
    if scenario.population:
        spec_content["population"] = {
            "include": sorted(scenario.population.include or []),
            "exclude": sorted(scenario.population.exclude or []),
        }

    return compute_sha256(canonicalize_json(spec_content))


def compute_ir_hash(
    signals: Dict[str, "ResolvedSignal"],
    trends: Dict[str, "ResolvedTrend"],
    logic: Dict[str, "ResolvedLogic"],
    dag: DependencyDAG,
) -> str:
    """
    Compute hash of normalized intermediate representation.

    Per spec/hashing.yaml hash_types.ir_hash:
    - Includes: normalized signals, trends, logic, dependency DAG
    - Excludes: source file location, parse metadata
    """
    ir_content = {
        "signals": {
            name: {
                "ref": s.ref,
                "concept_id": s.concept_id,
                "unit": s.unit,
                "domain": s.domain,
            }
            for name, s in sorted(signals.items())
        },
        "trends": {
            name: {
                "expr": t.raw_expr,
                "signals_used": sorted(t.signals_used),
                "trends_used": sorted(t.trends_used),
                "return_type": t.return_type,
            }
            for name, t in sorted(trends.items())
        },
        "logic": {
            name: {
                "expr": l.raw_expr,
                "trends_used": sorted(l.trends_used),
                "logic_used": sorted(l.logic_used),
                "severity": l.severity,
            }
            for name, l in sorted(logic.items())
        },
        "dag": {
            "signal_order": dag.signal_order,
            "trend_order": dag.trend_order,
            "logic_order": dag.logic_order,
        },
    }

    return compute_sha256(canonicalize_json(ir_content))


def compute_toolchain_hash() -> str:
    """
    Compute hash of compilation toolchain.

    Per spec/hashing.yaml hash_types.toolchain_hash:
    - Includes: psdl_lang_version, python_version, spec_version, grammar_hash
    - Excludes: runtime environment, optional dependencies
    """
    # Get Python version (major.minor only for stability)
    python_version = f"{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]}"

    # Get PSDL version
    psdl_version = psdl.__version__

    # Get spec version (from grammar file if available)
    spec_version = "0.3.0"

    # Compute grammar hash (if grammar file exists)
    grammar_hash = ""
    grammar_paths = [
        Path(__file__).parent.parent.parent.parent / "spec" / "grammar" / "expression.lark",
        Path(__file__).parent.parent / "spec" / "grammar" / "expression.lark",
    ]
    for grammar_path in grammar_paths:
        if grammar_path.exists():
            grammar_content = grammar_path.read_text()
            grammar_hash = compute_sha256(grammar_content)[:16]  # Short hash for grammar
            break

    toolchain_content = {
        "psdl_lang_version": psdl_version,
        "python_version": python_version,
        "spec_version": spec_version,
        "grammar_hash": grammar_hash,
    }

    return compute_sha256(canonicalize_json(toolchain_content))


class ScenarioCompiler:
    """
    Compiles a parsed PSDLScenario into executable ScenarioIR.

    Compilation steps:
    1. Resolve all signals with metadata
    2. Parse trend expressions and extract signal dependencies
    3. Parse logic expressions and extract trend/logic dependencies
    4. Build dependency DAG with topological sort
    5. Compute content hashes for reproducibility
    """

    def compile(
        self,
        scenario: PSDLScenario,
        source_yaml: str = "",
        dataset_spec: Optional[Dict[str, Any]] = None,
        mode: str = "strict",
    ) -> ScenarioIR:
        """
        Compile scenario to IR.

        Args:
            scenario: Parsed PSDL scenario (ScenarioSpec - validated input model)
            source_yaml: Original YAML source (for hash/audit)
            dataset_spec: Optional dataset specification for binding validation
            mode: Compilation mode - "strict" (default) or "lenient"

        Returns:
            Compiled ScenarioIR (compiled executable model) with resolved dependencies and DAG

        Compilation modes:
            - strict: Enforces all v0.3 constraints (no comparisons in trends, etc.)
            - lenient: Allows some legacy syntax with warnings

        Hashing (per spec/hashing.yaml):
            - spec_hash: SHA-256 of canonical scenario specification
            - ir_hash: SHA-256 of normalized IR with DAG
            - toolchain_hash: SHA-256 of compilation toolchain

        Dataset binding (Enhancement A):
            - Without dataset_spec: Only semantic validation (refs format, dependencies)
            - With dataset_spec: Additional binding validation (refs exist, types match)
        """
        # Initialize structured diagnostics
        diagnostics = CompilationDiagnostics(success=True)
        dep_analysis = DependencyAnalysis()
        type_analysis = TypeAnalysis()

        # Step 1: Resolve signals
        signals = self._resolve_signals_with_diagnostics(scenario, diagnostics, type_analysis)

        # Step 2: Resolve trends with dependencies
        trends = self._resolve_trends_with_diagnostics(
            scenario, signals, diagnostics, dep_analysis, type_analysis
        )

        # Step 3: Resolve logic with dependencies
        logic = self._resolve_logic_with_diagnostics(
            scenario, trends, diagnostics, dep_analysis, type_analysis
        )

        # Step 4: Build dependency DAG
        dag = self._build_dag_with_diagnostics(signals, trends, logic, diagnostics, dep_analysis)

        # Step 5: Dataset binding validation (if dataset_spec provided)
        if dataset_spec:
            self._validate_dataset_binding(signals, dataset_spec, diagnostics)

        # Step 6: Compute hashes (per spec/hashing.yaml)
        spec_hash = compute_spec_hash(scenario)
        ir_hash = compute_ir_hash(signals, trends, logic, dag)
        toolchain_hash = compute_toolchain_hash()

        # Step 7: Detect unused entities
        self._detect_unused_entities(signals, trends, logic, dep_analysis, diagnostics)

        # Attach analysis to diagnostics
        diagnostics.dependency_analysis = dep_analysis
        diagnostics.type_analysis = type_analysis

        return ScenarioIR(
            scenario_name=scenario.name,
            scenario_version=scenario.version,
            psdl_version=psdl.__version__,
            compiled_at=datetime.utcnow(),
            spec_hash=spec_hash,
            ir_hash=ir_hash,
            toolchain_hash=toolchain_hash,
            signals=signals,
            trends=trends,
            logic=logic,
            dag=dag,
            compilation=diagnostics,
            source_yaml=source_yaml,
            scenario=scenario,
        )

    # =========================================================================
    # New methods with structured diagnostics
    # =========================================================================

    def _resolve_signals_with_diagnostics(
        self,
        scenario: PSDLScenario,
        diagnostics: CompilationDiagnostics,
        type_analysis: TypeAnalysis,
    ) -> Dict[str, ResolvedSignal]:
        """Resolve signal definitions with structured diagnostics."""
        signals = {}
        for name, signal in scenario.signals.items():
            signals[name] = ResolvedSignal(
                name=name,
                ref=signal.ref,
                concept_id=signal.concept_id,
                unit=signal.unit,
                domain=signal.domain.value if signal.domain else "measurement",
            )
            # Type analysis: signals produce timeseries
            type_analysis.signal_types[name] = "timeseries"
        return signals

    def _resolve_trends_with_diagnostics(
        self,
        scenario: PSDLScenario,
        signals: Dict[str, ResolvedSignal],
        diagnostics: CompilationDiagnostics,
        dep_analysis: DependencyAnalysis,
        type_analysis: TypeAnalysis,
    ) -> Dict[str, ResolvedTrend]:
        """Parse trend expressions with structured diagnostics."""
        trends = {}

        for name, trend in scenario.trends.items():
            signals_used, trends_used = self._extract_trend_deps(trend, signals, trends)

            # Validate signal references
            for sig in signals_used:
                if sig not in signals:
                    diagnostics.add_error(
                        code=DiagnosticCode.TREND_UNKNOWN_SIGNAL,
                        message=f"Trend '{name}' references unknown signal '{sig}'",
                        location=SourceLocation(node_path=f"trends.{name}.expr"),
                        related_nodes=[sig],
                        suggestion=f"Define signal '{sig}' in the signals section",
                    )

            # Track dependencies
            for sig in signals_used:
                if sig not in dep_analysis.signal_to_trends:
                    dep_analysis.signal_to_trends[sig] = set()
                dep_analysis.signal_to_trends[sig].add(name)

            trends[name] = ResolvedTrend(
                name=name,
                raw_expr=trend.raw_expr,
                ast=trend.ast,
                signals_used=signals_used,
                trends_used=trends_used,
                return_type="numeric",
            )
            # Type analysis: trends produce numeric
            type_analysis.trend_types[name] = "numeric"

        return trends

    def _resolve_logic_with_diagnostics(
        self,
        scenario: PSDLScenario,
        trends: Dict[str, ResolvedTrend],
        diagnostics: CompilationDiagnostics,
        dep_analysis: DependencyAnalysis,
        type_analysis: TypeAnalysis,
    ) -> Dict[str, ResolvedLogic]:
        """Parse logic expressions with structured diagnostics."""
        logic = {}

        for name, logic_expr in scenario.logic.items():
            trends_used, logic_used = self._extract_logic_deps(logic_expr, trends, logic)

            logic[name] = ResolvedLogic(
                name=name,
                raw_expr=logic_expr.expr,
                ast=logic_expr.ast,
                trends_used=trends_used,
                logic_used=logic_used,
                severity=logic_expr.severity.value if logic_expr.severity else None,
            )

            # Track dependencies
            for t in trends_used:
                if t not in dep_analysis.trend_to_logic:
                    dep_analysis.trend_to_logic[t] = set()
                dep_analysis.trend_to_logic[t].add(name)
            for logic_ref in logic_used:
                if logic_ref not in dep_analysis.logic_to_logic:
                    dep_analysis.logic_to_logic[logic_ref] = set()
                dep_analysis.logic_to_logic[logic_ref].add(name)

            # Type analysis: logic produces boolean
            type_analysis.logic_types[name] = "boolean"

        # Second pass: validate all references
        all_terms = set(trends.keys()) | set(logic.keys())
        for name, resolved in logic.items():
            for term in resolved.trends_used | resolved.logic_used:
                if term not in all_terms:
                    diagnostics.add_error(
                        code=DiagnosticCode.LOGIC_UNKNOWN_TERM,
                        message=f"Logic '{name}' references unknown term '{term}'",
                        location=SourceLocation(node_path=f"logic.{name}.when"),
                        related_nodes=[term],
                        suggestion=f"Define '{term}' as a trend or logic rule",
                    )

        return logic

    def _build_dag_with_diagnostics(
        self,
        signals: Dict[str, ResolvedSignal],
        trends: Dict[str, ResolvedTrend],
        logic: Dict[str, ResolvedLogic],
        diagnostics: CompilationDiagnostics,
        dep_analysis: DependencyAnalysis,
    ) -> DependencyDAG:
        """Build DAG with cycle detection and structured diagnostics."""
        signal_order = list(signals.keys())

        # Sort trends
        trend_deps = {name: t.trends_used for name, t in trends.items()}
        trend_order, trend_cycles = self._topological_sort_with_cycles(trend_deps)
        for cycle in trend_cycles:
            diagnostics.add_error(
                code=DiagnosticCode.DAG_CIRCULAR_DEPENDENCY,
                message=f"Circular dependency in trends: {' -> '.join(cycle)}",
                related_nodes=cycle,
            )
            dep_analysis.circular_refs.append(cycle)

        # Sort logic
        logic_deps = {name: l.trends_used | l.logic_used for name, l in logic.items()}
        logic_only_deps = {name: deps & set(logic.keys()) for name, deps in logic_deps.items()}
        logic_order, logic_cycles = self._topological_sort_with_cycles(logic_only_deps)
        for cycle in logic_cycles:
            diagnostics.add_error(
                code=DiagnosticCode.DAG_CIRCULAR_DEPENDENCY,
                message=f"Circular dependency in logic: {' -> '.join(cycle)}",
                related_nodes=cycle,
            )
            dep_analysis.circular_refs.append(cycle)

        return DependencyDAG(
            signal_order=signal_order,
            trend_order=trend_order,
            logic_order=logic_order,
        )

    def _topological_sort_with_cycles(
        self, deps: Dict[str, Set[str]]
    ) -> Tuple[List[str], List[List[str]]]:
        """Topological sort that returns both order and detected cycles."""
        result = []
        visited = set()
        temp_visited = set()
        cycles = []
        path = []

        def visit(node: str) -> bool:
            if node in temp_visited:
                # Found cycle - extract it
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return False
            if node in visited:
                return True
            temp_visited.add(node)
            path.append(node)
            for dep in deps.get(node, set()):
                if dep in deps:
                    if not visit(dep):
                        pass  # Continue to find other cycles
            path.pop()
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
            return True

        for node in deps:
            if node not in visited:
                visit(node)

        return result, cycles

    def _validate_dataset_binding(
        self,
        signals: Dict[str, ResolvedSignal],
        dataset_spec: Dict[str, Any],
        diagnostics: CompilationDiagnostics,
    ) -> None:
        """Validate signal bindings against dataset specification (Enhancement A)."""
        dataset_refs = dataset_spec.get("refs", {})
        dataset_types = dataset_spec.get("types", {})

        for name, signal in signals.items():
            ref = signal.ref
            if ref and ref not in dataset_refs:
                diagnostics.add_warning(
                    code="W200",  # Dataset binding warning
                    message=f"Signal '{name}' ref '{ref}' not found in dataset spec",
                    location=SourceLocation(node_path=f"signals.{name}.ref"),
                    suggestion="Verify the ref exists in your dataset or update the dataset spec",
                )
            elif ref and ref in dataset_types:
                expected_type = dataset_types.get(ref)
                if signal.unit and expected_type.get("unit") != signal.unit:
                    diagnostics.add_warning(
                        code="W201",
                        message=f"Signal '{name}' unit mismatch: expected '{expected_type.get('unit')}', got '{signal.unit}'",
                        location=SourceLocation(node_path=f"signals.{name}.unit"),
                    )

    def _detect_unused_entities(
        self,
        signals: Dict[str, ResolvedSignal],
        trends: Dict[str, ResolvedTrend],
        logic: Dict[str, ResolvedLogic],
        dep_analysis: DependencyAnalysis,
        diagnostics: CompilationDiagnostics,
    ) -> None:
        """Detect unused signals and trends (warnings)."""
        # Check for unused signals
        used_signals = set()
        for trend in trends.values():
            used_signals.update(trend.signals_used)
        for signal_name in signals:
            if signal_name not in used_signals:
                dep_analysis.unused_signals.add(signal_name)
                diagnostics.add_warning(
                    code=DiagnosticCode.UNUSED_SIGNAL,
                    message=f"Signal '{signal_name}' is defined but never used",
                    location=SourceLocation(node_path=f"signals.{signal_name}"),
                )

        # Check for unused trends
        used_trends = set()
        for lg in logic.values():
            used_trends.update(lg.trends_used)
        for trend_name in trends:
            if trend_name not in used_trends:
                dep_analysis.unused_trends.add(trend_name)
                diagnostics.add_warning(
                    code=DiagnosticCode.UNUSED_TREND,
                    message=f"Trend '{trend_name}' is defined but never used in logic",
                    location=SourceLocation(node_path=f"trends.{trend_name}"),
                )

    # =========================================================================
    # Legacy methods (kept for backwards compatibility)
    # =========================================================================

    def _resolve_signals(
        self, scenario: PSDLScenario, errors: List[str]
    ) -> Dict[str, ResolvedSignal]:
        """Resolve signal definitions with metadata."""
        signals = {}
        for name, signal in scenario.signals.items():
            signals[name] = ResolvedSignal(
                name=name,
                ref=signal.ref,
                concept_id=signal.concept_id,
                unit=signal.unit,
                domain=signal.domain.value if signal.domain else "measurement",
            )
        return signals

    def _resolve_trends(
        self,
        scenario: PSDLScenario,
        signals: Dict[str, ResolvedSignal],
        errors: List[str],
        warnings: List[str],
    ) -> Dict[str, ResolvedTrend]:
        """Parse trend expressions and extract dependencies."""
        trends = {}

        for name, trend in scenario.trends.items():
            signals_used, trends_used = self._extract_trend_deps(trend, signals, trends)

            # Validate signal references
            for sig in signals_used:
                if sig not in signals:
                    errors.append(f"Trend '{name}' references unknown signal '{sig}'")

            trends[name] = ResolvedTrend(
                name=name,
                raw_expr=trend.raw_expr,
                ast=trend.ast,
                signals_used=signals_used,
                trends_used=trends_used,
                return_type="numeric",
            )

        return trends

    def _resolve_logic(
        self,
        scenario: PSDLScenario,
        trends: Dict[str, ResolvedTrend],
        errors: List[str],
        warnings: List[str],
    ) -> Dict[str, ResolvedLogic]:
        """Parse logic expressions and extract dependencies."""
        logic = {}

        for name, logic_expr in scenario.logic.items():
            trends_used, logic_used = self._extract_logic_deps(logic_expr, trends, logic)

            # Validate references
            for term in trends_used:
                if term not in trends and term not in logic:
                    # Could be forward reference to logic, check later
                    pass

            logic[name] = ResolvedLogic(
                name=name,
                raw_expr=logic_expr.expr,
                ast=logic_expr.ast,
                trends_used=trends_used,
                logic_used=logic_used,
                severity=logic_expr.severity.value if logic_expr.severity else None,
            )

        # Second pass: validate all references
        all_terms = set(trends.keys()) | set(logic.keys())
        for name, resolved in logic.items():
            for term in resolved.trends_used | resolved.logic_used:
                if term not in all_terms:
                    errors.append(f"Logic '{name}' references unknown term '{term}'")

        return logic

    def _build_dag(
        self,
        signals: Dict[str, ResolvedSignal],
        trends: Dict[str, ResolvedTrend],
        logic: Dict[str, ResolvedLogic],
        errors: List[str],
    ) -> DependencyDAG:
        """Build and topologically sort dependency graph."""
        # Signals have no internal dependencies
        signal_order = list(signals.keys())

        # Sort trends by dependencies (trends can depend on other trends via ArithExpr)
        trend_deps = {name: t.trends_used for name, t in trends.items()}
        trend_order = self._topological_sort(trend_deps, errors, "trend")

        # Sort logic by dependencies
        logic_deps = {name: l.trends_used | l.logic_used for name, l in logic.items()}
        # Filter to only include logic-to-logic deps for sorting
        # (trends are always evaluated before logic)
        logic_only_deps = {name: deps & set(logic.keys()) for name, deps in logic_deps.items()}
        logic_order = self._topological_sort(logic_only_deps, errors, "logic")

        return DependencyDAG(
            signal_order=signal_order,
            trend_order=trend_order,
            logic_order=logic_order,
        )

    def _topological_sort(
        self,
        deps: Dict[str, Set[str]],
        errors: List[str],
        layer: str,
    ) -> List[str]:
        """Topological sort with cycle detection."""
        result = []
        visited = set()
        temp_visited = set()

        def visit(node: str) -> bool:
            if node in temp_visited:
                errors.append(f"Circular dependency detected in {layer}: {node}")
                return False
            if node in visited:
                return True
            temp_visited.add(node)
            for dep in deps.get(node, set()):
                if dep in deps:  # Only visit nodes in this layer
                    if not visit(dep):
                        return False
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
            return True

        for node in deps:
            if node not in visited:
                visit(node)

        return result

    def _extract_trend_deps(
        self,
        trend: TrendExpr,
        signals: Dict[str, ResolvedSignal],
        trends: Dict[str, ResolvedTrend],
    ) -> Tuple[Set[str], Set[str]]:
        """Extract signal and trend dependencies from trend expression."""
        signals_used: Set[str] = set()
        trends_used: Set[str] = set()

        def visit(node: Any) -> None:
            if node is None:
                return

            if isinstance(node, TrendExpression):
                if node.temporal:
                    signals_used.add(node.temporal.signal)
            elif isinstance(node, TemporalCall):
                signals_used.add(node.signal)
            elif isinstance(node, ArithExpr):
                visit(node.left)
                visit(node.right)
            # NumberLiteral, float, int don't have dependencies

        # Handle simple signal reference
        if trend.signal:
            signals_used.add(trend.signal)

        # Handle AST for compound expressions
        if trend.ast is not None:
            visit(trend.ast)

        return signals_used, trends_used

    def _extract_logic_deps(
        self,
        logic: LogicExpr,
        trends: Dict[str, ResolvedTrend],
        logic_dict: Dict[str, ResolvedLogic],
    ) -> Tuple[Set[str], Set[str]]:
        """Extract trend and logic dependencies from logic expression."""
        trends_used: Set[str] = set()
        logic_used: Set[str] = set()

        def visit(node: Any) -> None:
            if node is None:
                return

            if isinstance(node, TermRef):
                term = node.name
                if term in trends:
                    trends_used.add(term)
                elif term in logic_dict:
                    logic_used.add(term)
                else:
                    # Could be forward reference, add to trends as default
                    trends_used.add(term)
            elif isinstance(node, AndExpr):
                for operand in node.operands:
                    visit(operand)
            elif isinstance(node, OrExpr):
                for operand in node.operands:
                    visit(operand)
            elif isinstance(node, NotExpr):
                visit(node.operand)
            elif isinstance(node, ComparisonExpr):
                visit(node.left)
                visit(node.right)

        # Use parsed AST if available
        if logic.ast is not None:
            visit(logic.ast)
        else:
            # Fallback: use extracted terms from parser
            for term in logic.terms:
                if term in trends:
                    trends_used.add(term)
                elif term in logic_dict:
                    logic_used.add(term)
                else:
                    trends_used.add(term)

        return trends_used, logic_used


def compile_scenario(source: str) -> ScenarioIR:
    """
    Convenience function to compile a PSDL scenario.

    Args:
        source: Either a file path (ending in .yaml/.yml) or YAML content string

    Returns:
        Compiled ScenarioIR with resolved dependencies and DAG
    """
    from psdl.core.parser import parse_scenario

    # Determine if source is file path or YAML content
    if source.endswith(".yaml") or source.endswith(".yml"):
        with open(source, "r") as f:
            source_yaml = f.read()
    else:
        source_yaml = source

    # Parse scenario
    scenario = parse_scenario(source_yaml)

    # Compile to IR
    compiler = ScenarioCompiler()
    return compiler.compile(scenario, source_yaml)
