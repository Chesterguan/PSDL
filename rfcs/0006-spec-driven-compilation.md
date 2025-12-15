# RFC: Spec-Driven Compilation Architecture

- **RFC Number**: 0006
- **Author(s)**: PSDL Team
- **Status**: Draft
- **Created**: 2025-12-15
- **Updated**: 2025-12-15

## Summary

This RFC proposes a refined architecture that cleanly separates three distinct layers:
1. **ScenarioSpec** - Input validation (generated from schema)
2. **ScenarioIR** - Compiled intermediate representation (manual, runtime contract)
3. **EvaluationResult** - Runtime output

It also introduces two critical mechanisms for audit/reproducibility:
- **Compiled artifacts** with immutable snapshots for IRB/audit
- **Conformance tests** auto-generated from spec to prevent behavioral drift

## Motivation

The current architecture has three issues that will cause pain as PSDL scales:

### Issue 1: YAML Type Inference Breaks Determinism

JSON Schema validates JSON data models, but YAML has richer type inference:

```yaml
# These YAML inputs produce unexpected Python types
version: 1.0        # → float(1.0), not string "1.0"
date: 2024-01-01    # → datetime object, not string
enabled: yes        # → bool True, not string "yes"
```

Different YAML parsers or minor syntax variations can produce different types, breaking determinism.

### Issue 2: operators.yaml Becoming a God File

Currently `operators.yaml` mixes multiple concerns:
- Operator signatures (name, args, return type)
- SQL templates (PostgreSQL)
- Human documentation
- Future: multiple SQL dialects (DuckDB, BigQuery, Spark SQL)

This will become unmaintainable as we add dialects.

### Issue 3: Conflating Input Schema with Compiled IR

The plan to "merge IR into schema.json and delete ir.py" conflates two fundamentally different things:

| Concept | Purpose | Lifecycle |
|---------|---------|-----------|
| ScenarioSpec | Validate user input | Parse-time |
| ScenarioIR | Executable representation | Compile-time |

The IR must contain what the input spec doesn't:
- Dependency DAG (topologically sorted execution order)
- Resolved references (which signals each trend uses)
- Type inference results (verified units, types)
- Validation state (errors, warnings)
- Compiled artifact hash for reproducibility

### Example Use Case: Multi-Site Clinical Trial

A pharma company runs the same AKI detection scenario across 5 hospitals. For FDA submission, they need:

1. **Exact reproducibility**: Same scenario version produces identical results
2. **Audit trail**: Hash of scenario + spec versions + PSDL version
3. **Provenance**: Which signals were used, dependency graph, validation state

Without a proper compiled artifact, this is impossible to guarantee.

## Detailed Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SPEC FILES (Source of Truth)             │
├─────────────────────────────────────────────────────────────────┤
│ schema.json           → Scenario YAML structure                 │
│ ast-nodes.yaml        → Expression AST + grammar mappings       │
│ operators/                                                      │
│   ├── signatures.yaml → Core operator definitions               │
│   └── backends/       → SQL dialects (postgres, duckdb, etc.)   │
│ conformance/          → Test definitions (auto-generates tests) │
│ grammar/*.lark        → Expression grammar                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ codegen.py
┌─────────────────────────────────────────────────────────────────┐
│                    GENERATED CODE                               │
├─────────────────────────────────────────────────────────────────┤
│ _generated/scenario_spec.py    ← Pydantic input validation      │
│ _generated/ast_types.py        ← Expression AST dataclasses     │
│ _generated/transformer.py      ← Lark transformer               │
│ _generated/operators_meta.py   ← Operator signatures            │
│ _generated/sql/postgresql.py   ← PostgreSQL templates           │
│ _generated/sql/duckdb.py       ← DuckDB templates (future)      │
│ _generated/conformance_tests.py← Auto-generated tests           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MANUAL CODE (Algorithms Only)                │
├─────────────────────────────────────────────────────────────────┤
│ core/compile.py    → ScenarioSpec + AST → ScenarioIR            │
│ core/ir.py         → ScenarioIR (compiled artifact definition)  │
│ core/normalize.py  → YAML normalization layer                   │
│ operators.py       → Runtime operator implementations           │
│ runtimes/          → Execution engines                          │
│ adapters/          → Data source adapters                       │
└─────────────────────────────────────────────────────────────────┘
```

### Layer 1: Input Normalization

```python
# core/normalize.py
"""YAML normalization to ensure deterministic parsing."""

from typing import Any, Dict
import yaml
from datetime import date, datetime

class PSDLYAMLLoader(yaml.SafeLoader):
    """Custom YAML loader that enforces deterministic types."""
    pass

def _string_constructor(loader, node):
    """Force certain patterns to remain strings."""
    return loader.construct_scalar(node)

# Disable automatic date parsing
PSDLYAMLLoader.add_constructor(
    'tag:yaml.org,2002:timestamp',
    _string_constructor
)

def normalize_yaml(content: str) -> Dict[str, Any]:
    """
    Parse YAML with deterministic type handling.

    Rules:
    1. Dates remain strings (no datetime objects)
    2. Version fields are always strings
    3. YAML tags (!!set, !!python) are rejected
    4. Anchors/aliases are expanded
    """
    data = yaml.load(content, Loader=PSDLYAMLLoader)
    return _normalize_types(data)

def _normalize_types(obj: Any) -> Any:
    """Recursively normalize types for determinism."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            # Force version to string
            if k == 'version' and not isinstance(v, str):
                result[k] = str(v)
            else:
                result[k] = _normalize_types(v)
        return result
    elif isinstance(obj, list):
        return [_normalize_types(item) for item in obj]
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    else:
        return obj
```

### Layer 2: Separated Operator Specs

**Current** (monolithic):
```yaml
# spec/operators.yaml - everything mixed together
operators:
  windowed:
    delta:
      description: "Change over window"
      args: [signal, window]
      returns: numeric
      implementations:
        postgresql: "..."
        # Future: duckdb, bigquery, spark...
```

**Proposed** (separated):
```yaml
# spec/operators/signatures.yaml - Core definitions only
version: "0.3.0"

operators:
  windowed:
    delta:
      description: "Change in signal value over time window"
      args:
        - name: signal
          type: Signal
        - name: window
          type: WindowSpec
      returns: numeric
      deterministic: true

    slope:
      description: "Linear regression slope over window"
      args:
        - name: signal
          type: Signal
        - name: window
          type: WindowSpec
      returns: numeric
      deterministic: true

  pointwise:
    last:
      description: "Most recent signal value"
      args:
        - name: signal
          type: Signal
      returns: numeric
      deterministic: false  # Depends on data timing
```

```yaml
# spec/operators/backends/postgresql.yaml
version: "0.3.0"
dialect: postgresql

templates:
  delta: |
    (SELECT value FROM {table}
     WHERE person_id = {person_id}
       AND measurement_concept_id = {concept_id}
       AND measurement_datetime <= {eval_time}
     ORDER BY measurement_datetime DESC LIMIT 1)
    -
    (SELECT value FROM {table}
     WHERE person_id = {person_id}
       AND measurement_concept_id = {concept_id}
       AND measurement_datetime <= {eval_time} - INTERVAL '{window}'
     ORDER BY measurement_datetime DESC LIMIT 1)

  slope: |
    (SELECT regr_slope(value, EXTRACT(EPOCH FROM measurement_datetime))
     FROM {table}
     WHERE person_id = {person_id}
       AND measurement_concept_id = {concept_id}
       AND measurement_datetime BETWEEN {eval_time} - INTERVAL '{window}' AND {eval_time})

  last: |
    (SELECT value FROM {table}
     WHERE person_id = {person_id}
       AND measurement_concept_id = {concept_id}
       AND measurement_datetime <= {eval_time}
     ORDER BY measurement_datetime DESC LIMIT 1)
```

```yaml
# spec/operators/backends/duckdb.yaml (future)
version: "0.3.0"
dialect: duckdb

templates:
  delta: |
    -- DuckDB-specific syntax
    ...
```

### Layer 3: Compiled IR (ScenarioIR)

```python
# core/ir.py - Compiled intermediate representation

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime
import hashlib
import json

@dataclass
class ResolvedSignal:
    """Signal with resolved references."""
    name: str
    ref: str
    concept_id: Optional[int]
    unit: Optional[str]

@dataclass
class ResolvedTrend:
    """Trend with parsed AST and resolved dependencies."""
    name: str
    ast: "TrendExpression"  # Parsed expression AST
    signals_used: Set[str]  # Which signals this trend depends on
    trends_used: Set[str]   # Which other trends this depends on (for ArithExpr)
    return_type: str        # "numeric"

@dataclass
class ResolvedLogic:
    """Logic rule with parsed AST and resolved dependencies."""
    name: str
    ast: "LogicNode"        # Parsed expression AST
    trends_used: Set[str]   # Which trends this logic depends on
    logic_used: Set[str]    # Which other logic rules this depends on
    severity: Optional[str]

@dataclass
class DependencyDAG:
    """Topologically sorted dependency graph."""
    signal_order: List[str]      # Order to fetch signals
    trend_order: List[str]       # Order to evaluate trends
    logic_order: List[str]       # Order to evaluate logic

    def get_evaluation_order(self) -> List[str]:
        """Return full evaluation order."""
        return self.signal_order + self.trend_order + self.logic_order

@dataclass
class CompilationResult:
    """Result of validation/compilation."""
    success: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass
class ScenarioIR:
    """
    Compiled intermediate representation of a PSDL scenario.

    This is the executable artifact - immutable after compilation.
    Used for:
    - Runtime evaluation
    - Audit/reproducibility (serializable snapshot)
    - Multi-site deployment (hash verification)
    """
    # Metadata
    scenario_name: str
    scenario_version: str
    psdl_version: str
    compiled_at: datetime

    # Content hash for reproducibility
    spec_hash: str          # Hash of original YAML
    ir_hash: str            # Hash of compiled IR

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
            },
            "dag": {
                "signal_order": self.dag.signal_order,
                "trend_order": self.dag.trend_order,
                "logic_order": self.dag.logic_order,
            },
            "signals": {
                name: {"ref": s.ref, "concept_id": s.concept_id, "unit": s.unit}
                for name, s in self.signals.items()
            },
            "trends": {
                name: {
                    "signals_used": list(t.signals_used),
                    "trends_used": list(t.trends_used),
                    "return_type": t.return_type,
                }
                for name, t in self.trends.items()
            },
            "logic": {
                name: {
                    "trends_used": list(l.trends_used),
                    "logic_used": list(l.logic_used),
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
        with open(path, 'w') as f:
            json.dump(self.to_artifact(), f, indent=2)

    @staticmethod
    def compute_hash(content: str) -> str:
        """Compute deterministic hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
```

### Layer 4: Compiler

```python
# core/compile.py - Compiles ScenarioSpec to ScenarioIR

from datetime import datetime
from typing import Dict, List, Set, Tuple
import psdl
from psdl._generated.scenario_spec import ScenarioSpec  # Generated from schema
from psdl.expression_parser import parse_trend_expression, parse_logic_expression
from psdl.core.ir import (
    ScenarioIR, ResolvedSignal, ResolvedTrend, ResolvedLogic,
    DependencyDAG, CompilationResult
)

class ScenarioCompiler:
    """
    Compiles a validated ScenarioSpec into executable ScenarioIR.

    Compilation steps:
    1. Parse all expressions into ASTs
    2. Resolve all references (signals, trends, logic)
    3. Build dependency DAG
    4. Topologically sort for evaluation order
    5. Compute hashes for reproducibility
    """

    def compile(self, spec: ScenarioSpec, source_yaml: str) -> ScenarioIR:
        """Compile scenario spec to IR."""
        errors: List[str] = []
        warnings: List[str] = []

        # Step 1: Resolve signals
        signals = self._resolve_signals(spec, errors)

        # Step 2: Parse and resolve trends
        trends = self._resolve_trends(spec, signals, errors, warnings)

        # Step 3: Parse and resolve logic
        logic = self._resolve_logic(spec, trends, errors, warnings)

        # Step 4: Build dependency DAG
        dag = self._build_dag(signals, trends, logic, errors)

        # Step 5: Compute hashes
        spec_hash = ScenarioIR.compute_hash(source_yaml)
        ir_content = self._serialize_for_hash(signals, trends, logic, dag)
        ir_hash = ScenarioIR.compute_hash(ir_content)

        compilation = CompilationResult(
            success=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

        return ScenarioIR(
            scenario_name=spec.scenario,
            scenario_version=spec.version,
            psdl_version=psdl.__version__,
            compiled_at=datetime.utcnow(),
            spec_hash=spec_hash,
            ir_hash=ir_hash,
            signals=signals,
            trends=trends,
            logic=logic,
            dag=dag,
            compilation=compilation,
            source_yaml=source_yaml,
        )

    def _resolve_signals(self, spec: ScenarioSpec, errors: List[str]) -> Dict[str, ResolvedSignal]:
        """Resolve signal definitions."""
        signals = {}
        for name, signal_def in (spec.signals or {}).items():
            signals[name] = ResolvedSignal(
                name=name,
                ref=signal_def.ref,
                concept_id=getattr(signal_def, 'concept_id', None),
                unit=getattr(signal_def, 'unit', None),
            )
        return signals

    def _resolve_trends(
        self,
        spec: ScenarioSpec,
        signals: Dict[str, ResolvedSignal],
        errors: List[str],
        warnings: List[str],
    ) -> Dict[str, ResolvedTrend]:
        """Parse trend expressions and resolve dependencies."""
        trends = {}

        for name, trend_def in (spec.trends or {}).items():
            try:
                ast = parse_trend_expression(trend_def.expr)
                signals_used, trends_used = self._extract_trend_deps(ast, signals, trends)

                # Validate signal references exist
                for sig in signals_used:
                    if sig not in signals:
                        errors.append(f"Trend '{name}' references unknown signal '{sig}'")

                trends[name] = ResolvedTrend(
                    name=name,
                    ast=ast,
                    signals_used=signals_used,
                    trends_used=trends_used,
                    return_type="numeric",
                )
            except Exception as e:
                errors.append(f"Failed to parse trend '{name}': {e}")

        return trends

    def _resolve_logic(
        self,
        spec: ScenarioSpec,
        trends: Dict[str, ResolvedTrend],
        errors: List[str],
        warnings: List[str],
    ) -> Dict[str, ResolvedLogic]:
        """Parse logic expressions and resolve dependencies."""
        logic = {}

        for name, logic_def in (spec.logic or {}).items():
            try:
                ast = parse_logic_expression(logic_def.when)
                trends_used, logic_used = self._extract_logic_deps(ast, trends, logic)

                # Validate trend references exist
                for trend in trends_used:
                    if trend not in trends:
                        # Might be a logic reference, check later
                        pass

                logic[name] = ResolvedLogic(
                    name=name,
                    ast=ast,
                    trends_used=trends_used,
                    logic_used=logic_used,
                    severity=getattr(logic_def, 'severity', None),
                )
            except Exception as e:
                errors.append(f"Failed to parse logic '{name}': {e}")

        return logic

    def _build_dag(
        self,
        signals: Dict[str, ResolvedSignal],
        trends: Dict[str, ResolvedTrend],
        logic: Dict[str, ResolvedLogic],
        errors: List[str],
    ) -> DependencyDAG:
        """Build and topologically sort dependency graph."""
        # Simple topological sort based on dependencies
        signal_order = list(signals.keys())

        # Sort trends by dependencies
        trend_order = self._topological_sort(
            {name: t.signals_used | t.trends_used for name, t in trends.items()},
            errors,
            "trend",
        )

        # Sort logic by dependencies
        logic_order = self._topological_sort(
            {name: l.trends_used | l.logic_used for name, l in logic.items()},
            errors,
            "logic",
        )

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

        def visit(node: str):
            if node in temp_visited:
                errors.append(f"Circular dependency detected in {layer}: {node}")
                return
            if node in visited:
                return
            temp_visited.add(node)
            for dep in deps.get(node, set()):
                if dep in deps:  # Only visit nodes in this layer
                    visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)

        for node in deps:
            if node not in visited:
                visit(node)

        return result

    def _extract_trend_deps(self, ast, signals, trends) -> Tuple[Set[str], Set[str]]:
        """Extract signal and trend dependencies from trend AST."""
        signals_used = set()
        trends_used = set()
        # Walk AST to find TemporalCall.signal references
        # ... implementation
        return signals_used, trends_used

    def _extract_logic_deps(self, ast, trends, logic) -> Tuple[Set[str], Set[str]]:
        """Extract trend and logic dependencies from logic AST."""
        trends_used = set()
        logic_used = set()
        # Walk AST to find TermRef.name references
        # ... implementation
        return trends_used, logic_used

    def _serialize_for_hash(self, signals, trends, logic, dag) -> str:
        """Serialize IR content for deterministic hashing."""
        # Canonical JSON serialization
        # ... implementation
        return ""
```

### Layer 5: Conformance Tests

```yaml
# spec/conformance/operators.yaml
version: "0.3.0"

tests:
  # Windowed operators
  delta:
    valid_parse:
      - expr: "delta(Cr, 6h)"
        expected_signal: "Cr"
        expected_window: "6h"
      - expr: "delta(HR, 30m)"
        expected_signal: "HR"
        expected_window: "30m"
    invalid_parse:
      - expr: "delta(Cr)"
        reason: "Missing window argument"
      - expr: "delta(Cr, 6h) > 0"
        reason: "Comparison not allowed in trend (v0.3)"
    return_type: numeric

  slope:
    valid_parse:
      - expr: "slope(Lact, 3h)"
        expected_signal: "Lact"
        expected_window: "3h"
    return_type: numeric

  # Pointwise operators
  last:
    valid_parse:
      - expr: "last(HR)"
        expected_signal: "HR"
    invalid_parse:
      - expr: "last(HR, 6h)"
        reason: "Pointwise operator does not take window"
    return_type: numeric

  exists:
    valid_parse:
      - expr: "exists(Cr)"
        expected_signal: "Cr"
    return_type: boolean

# Logic expressions
logic_tests:
  valid_parse:
    - expr: "aki_stage1 AND NOT recovering"
      expected_terms: ["aki_stage1", "recovering"]
      expected_operators: ["AND", "NOT"]
    - expr: "cr_delta >= 0.3"
      expected_comparison: ">="
    - expr: "(fever OR hypothermia) AND tachycardia"
      expected_structure: "AND(OR(...), ...)"

  invalid_parse:
    - expr: "aki_stage1 &&"
      reason: "Invalid operator (use AND not &&)"
```

Code generator addition:

```python
# In codegen.py

def generate_conformance_tests() -> bool:
    """Generate pytest tests from conformance spec."""
    print("Generating conformance tests from spec/conformance/...")

    # Load conformance specs
    conformance_dir = SPEC_DIR / "conformance"
    if not conformance_dir.exists():
        print("  No conformance specs found")
        return True

    # Generate test file
    tests = []
    for spec_file in conformance_dir.glob("*.yaml"):
        spec = yaml.safe_load(spec_file.read_text())
        tests.extend(_generate_tests_from_spec(spec))

    # Write test file
    content = _render_conformance_tests(tests)
    output_file = GENERATED_DIR / "conformance_tests.py"
    output_file.write_text(content)

    print(f"  Generated: {output_file.relative_to(PROJECT_ROOT)}")
    print(f"    - {len(tests)} test cases")
    return True
```

## API Changes

### New Public API

```python
# Compile scenario
from psdl import compile_scenario

ir = compile_scenario("path/to/scenario.yaml")

# Access compiled artifact
print(ir.dag.get_evaluation_order())
print(ir.spec_hash)

# Save artifact for audit
ir.save_artifact("scenario.compiled.json")

# Evaluate using IR
from psdl import SinglePatientEvaluator

evaluator = SinglePatientEvaluator(ir, backend)
result = evaluator.evaluate(patient_id)
```

### Inspector Integration

```python
from psdl import Inspector

inspector = Inspector("scenario.yaml")

# Validate (existing)
validation = inspector.validate()

# Compile (new)
ir = inspector.compile()

# Full artifact (new)
artifact = inspector.to_artifact()
artifact.save("scenario.compiled.json")
```

## Migration Path

### Phase 1: Add Normalization (Non-Breaking)
- Add `core/normalize.py`
- Integrate into parser
- No API changes

### Phase 2: Refactor Operators (Non-Breaking)
- Split `operators.yaml` into signatures + backends
- Update codegen to handle new structure
- Generated code unchanged

### Phase 3: Add Compiler (Additive)
- Add `core/compile.py` and new `core/ir.py`
- Add `compile_scenario()` function
- Existing API unchanged

### Phase 4: Add Conformance Tests (Additive)
- Add `spec/conformance/` directory
- Add `codegen.py --conformance`
- CI integration

## Drawbacks

1. **Increased complexity**: Three-layer architecture is more complex than current two-layer
2. **Migration effort**: Existing code needs refactoring
3. **Serialization overhead**: Compiled artifacts add storage

## Alternatives

### Alternative 1: Keep IR as Input Mirror
Rejected because it loses dependency DAG, validation state, and audit capabilities.

### Alternative 2: Generate IR from Schema
Rejected because IR contains computed properties (DAG, resolved refs) that can't be expressed in JSON Schema.

### Alternative 3: Single operators.yaml with Nested Structure
Considered, but separate files are cleaner for multi-dialect support and code ownership.

## Prior Art

| System | Approach | Relevance |
|--------|----------|-----------|
| LLVM | IR as compiled artifact | Same concept of IR between source and execution |
| GraphQL | Schema → Compiled resolvers | Spec-driven compilation |
| Terraform | Plan → State | Compiled artifact for reproducibility |
| CQL | ELM (Expression Logical Model) | Clinical logic IR |

## Open Questions

1. Should the compiled artifact include the full source YAML or just a hash?
2. What's the versioning strategy for artifact format changes?
3. How to handle IR migration when spec versions change?

## Future Possibilities

1. **Remote IR execution**: Send compiled IR to remote runtime
2. **IR optimization**: Optimize dependency graph before execution
3. **IR caching**: Cache compiled IR to skip recompilation
4. **Multi-language IR**: Same IR format for Python/TypeScript/Rust runtimes

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-15 | PSDL Team | Initial draft |
