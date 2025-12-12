# RFC-0003: Architecture Refactor

| Field | Value |
|-------|-------|
| RFC | 0003 |
| Title | Architecture Refactor - Spec-Driven Code Generation |
| Author | PSDL Team |
| Status | Draft |
| Created | 2025-12-11 |
| Updated | 2025-12-12 |

## Summary

Refactor PSDL codebase to a clean layered architecture where:
1. **Specification files are the source of truth**
2. **Code is generated from specifications** (not hand-written)
3. **Clear separation between layers** (spec, core, runtimes, adapters)

## Motivation

### Current Problems

1. **Mixed concerns**: `operators.py` contains type definitions, Python implementation, AND is referenced by SQL compiler
2. **Inconsistent implementations**: SQL compiler and Python evaluator have diverged (e.g., `count` null handling)
3. **No formal spec**: Operator semantics are implicit in code, leading to drift
4. **Unclear naming**: "execution", "batch", "evaluator" terms used inconsistently
5. **Manual code**: Parser, types, SQL templates all hand-written and can get out of sync

### Goals

1. Single source of truth for all PSDL semantics
2. Automatic code generation from specifications
3. Guaranteed consistency across all runtimes (Python, SQL, Flink)
4. Clear separation of concerns
5. Easier to extend with new operators, runtimes, or adapters

## Design

### Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAYER 0: SPECIFICATION (Source of Truth)                                     │
│                                                                              │
│ spec/                                                                        │
│ ├── schema.json           # JSON Schema - scenario structure                │
│ ├── grammar/                                                                │
│ │   └── expression.lark   # Lark Grammar - expression syntax                │
│ └── operators.yaml        # Operator semantics + implementations            │
├─────────────────────────────────────────────────────────────────────────────┤
│ LAYER 1: GENERATED CODE (Auto-generated, do not edit)                       │
│                                                                              │
│ src/psdl/_generated/                                                         │
│ ├── schema_types.py       # ← from schema.json                              │
│ ├── expression_parser.py  # ← from expression.lark                          │
│ └── operators.py          # ← from operators.yaml                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ LAYER 2: CORE (Parser, IR, Validator)                                        │
│                                                                              │
│ src/psdl/core/                                                               │
│ ├── loader.py             # YAML/JSON → dict                                │
│ ├── parser.py             # dict → IR                                       │
│ ├── ir.py                 # Intermediate Representation                     │
│ └── validator.py          # Validate IR                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ LAYER 3: RUNTIMES (Execution environments)                                   │
│                                                                              │
│ src/psdl/runtimes/                                                           │
│ ├── single/               # Single patient evaluation (Python)              │
│ ├── cohort/               # Batch analysis (SQL)                            │
│ └── streaming/            # Real-time (Flink)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ LAYER 4: ADAPTERS (Data source connections)                                  │
│                                                                              │
│ src/psdl/adapters/                                                           │
│ ├── omop.py               # OMOP CDM                                        │
│ ├── fhir.py               # FHIR R4                                         │
│ └── memory.py             # In-memory (testing)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ LAYER 5: TOOLING (CLI, utilities)                                            │
│                                                                              │
│ src/psdl/cli/                                                                │
│ └── main.py               # psdl validate/run/stream                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Specification Files

#### 1. `spec/schema.json` - Scenario Structure

JSON Schema (Draft-07) defining the structure of PSDL scenario files.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "definitions": {
    "Signal": { ... },
    "Trend": { ... },
    "Logic": { ... },
    "Scenario": { ... }
  }
}
```

**Generates:** Python dataclasses/Pydantic models via `datamodel-codegen`

#### 2. `spec/grammar/expression.lark` - Expression Syntax

Lark grammar defining trend and logic expression syntax. (Already exists)

**Generates:** Parser via Lark's built-in transformer

#### 3. `spec/operators.yaml` - Operator Semantics (NEW)

Formal definition of each operator including:
- Signature
- Semantic description
- Null handling rules
- Implementation templates for each target

```yaml
operators:
  delta:
    category: windowed
    signature: "(signal: str, window: Window) -> float | null"
    semantics:
      description: "Absolute change: last - first in window"
      null_handling: filter
      min_points: 2
    implementations:
      python: |
        non_null = [dp for dp in data if dp.value is not None]
        if len(non_null) < 2:
            return None
        return non_null[-1].value - non_null[0].value
      postgresql: |
        WITH first_last AS (...)
        SELECT last_val - first_val
      flink_sql: |
        LAST_VALUE(val) - FIRST_VALUE(val)
```

**Generates:**
- Python operator functions
- SQL templates
- Flink templates

### Runtime Definitions

| Runtime | Purpose | Input | Output | Implementation |
|---------|---------|-------|--------|----------------|
| **Single** | Evaluate ONE patient | IR + PatientData | Result | Python |
| **Cohort** | Evaluate MANY patients (batch) | IR + Database | Results | SQL |
| **Streaming** | Continuous evaluation | IR + Stream | Alerts | Flink |

### Code Generation Pipeline

```
make codegen
    │
    ├── spec/schema.json
    │   └── datamodel-codegen → _generated/schema_types.py
    │
    ├── spec/grammar/expression.lark
    │   └── (used directly by Lark at runtime)
    │
    └── spec/operators.yaml
        └── tools/codegen.py →
            ├── _generated/operators_python.py
            ├── _generated/operators_sql.py
            └── _generated/operators_flink.py
```

## Migration Plan

### Phase 1: Create Specification Files (Week 1)

1. Create `spec/schema.json` from existing `schema-v0.1.yaml`
2. Create `spec/operators.yaml` with all operator definitions
3. Ensure existing `expression.lark` is complete

### Phase 2: Set Up Code Generation (Week 2)

1. Add `datamodel-codegen` dependency
2. Create `tools/codegen.py` for operators
3. Create `Makefile` targets
4. Generate initial `_generated/` files

### Phase 3: Refactor Core (Week 3)

1. Create `src/psdl/core/` directory
2. Move/refactor `parser.py` → `core/parser.py`
3. Create `core/ir.py` with clean IR dataclasses
4. Create `core/validator.py`
5. Update imports throughout codebase

### Phase 4: Refactor Runtimes (Week 4)

1. Create `src/psdl/runtimes/` directory structure
2. Move single evaluation → `runtimes/single/`
3. Move SQL compiler → `runtimes/cohort/`
4. Move Flink code → `runtimes/streaming/`
5. Each runtime uses generated operators

### Phase 5: Update Tests & Docs (Week 5)

1. Add conformance tests (verify all runtimes match)
2. Update test imports
3. Update documentation
4. Update notebooks

## Directory Structure (After)

```
psdl-lang/
├── spec/                           # SPECIFICATION
│   ├── schema.json                 # Scenario structure (JSON Schema)
│   ├── grammar/
│   │   ├── expression.lark         # Expression grammar
│   │   └── expression.ebnf         # Human-readable grammar
│   ├── operators.yaml              # Operator semantics
│   └── VERSION                     # Spec version
│
├── src/psdl/
│   ├── __init__.py                 # Public API
│   ├── _version.py
│   │
│   ├── _generated/                 # AUTO-GENERATED (do not edit)
│   │   ├── __init__.py
│   │   ├── schema_types.py         # ← from schema.json
│   │   ├── operators_python.py     # ← from operators.yaml
│   │   ├── operators_sql.py        # ← from operators.yaml
│   │   └── operators_flink.py      # ← from operators.yaml
│   │
│   ├── core/                       # CORE LIBRARY
│   │   ├── __init__.py
│   │   ├── loader.py               # YAML/JSON loading
│   │   ├── parser.py               # Parsing to IR
│   │   ├── ir.py                   # Intermediate Representation
│   │   └── validator.py            # IR validation
│   │
│   ├── runtimes/                   # EXECUTION RUNTIMES
│   │   ├── __init__.py
│   │   ├── single/                 # Single patient (Python)
│   │   │   ├── __init__.py
│   │   │   └── evaluator.py
│   │   ├── cohort/                 # Batch (SQL)
│   │   │   ├── __init__.py
│   │   │   ├── compiler.py
│   │   │   ├── dialects/
│   │   │   │   ├── postgresql.py
│   │   │   │   └── bigquery.py
│   │   │   └── executor.py
│   │   └── streaming/              # Real-time (Flink)
│   │       ├── __init__.py
│   │       ├── compiler.py
│   │       └── runner.py
│   │
│   ├── adapters/                   # DATA ADAPTERS
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── omop.py
│   │   ├── fhir.py
│   │   └── memory.py
│   │
│   ├── cli/                        # COMMAND LINE
│   │   ├── __init__.py
│   │   └── main.py
│   │
│   └── examples/                   # BUILT-IN EXAMPLES
│       ├── __init__.py
│       └── *.yaml
│
├── tools/                          # DEVELOPMENT TOOLS (not packaged)
│   ├── codegen.py                  # Code generator
│   └── sync_spec.py                # Sync spec versions
│
├── tests/
│   ├── spec/                       # Spec validation tests
│   ├── core/                       # Core library tests
│   ├── runtimes/                   # Runtime tests
│   ├── adapters/                   # Adapter tests
│   └── conformance/                # Cross-runtime consistency
│
├── docs/
│   ├── GLOSSARY.md                 # Terminology
│   └── ...
│
├── rfcs/                           # Design documents
│   ├── 0001-ai-integration.md
│   ├── 0002-streaming.md
│   └── 0003-architecture-refactor.md  # This RFC
│
├── pyproject.toml
├── Makefile
└── README.md
```

## Backward Compatibility

### Breaking Changes

1. Import paths change:
   - `from psdl.execution.batch import PSDLEvaluator` → `from psdl.runtimes.single import evaluate`
   - `from psdl.operators import DataPoint` → `from psdl.core.ir import DataPoint`

2. Class names change:
   - `PSDLEvaluator` → split into runtime-specific classes
   - `InMemoryBackend` → `InMemoryAdapter`

### Migration Path

1. Version 0.2.x: Add deprecation warnings for old imports
2. Version 0.3.0: Remove old imports, new structure only

## Alternatives Considered

### 1. Keep Current Structure, Just Fix Bugs

**Pros:** Less work, no breaking changes
**Cons:** Will continue to drift, hard to maintain

**Decision:** Rejected - technical debt will grow

### 2. Generate Everything (Including IR)

**Pros:** Maximum consistency
**Cons:** Less flexibility, harder to customize

**Decision:** Rejected - IR needs to be usable by human-written code

### 3. Separate Packages (psdl-spec, psdl-python, psdl-sql)

**Pros:** Clear separation
**Cons:** Complex dependency management, harder for users

**Decision:** Rejected - single package is simpler for users

## Open Questions

1. Should `operators.yaml` include formal mathematical notation?
2. Should we support multiple SQL dialects from day one, or start with PostgreSQL only?
3. How to handle operators that are impossible in some runtimes (e.g., EMA in SQL)?

## References

- [JSON Schema](https://json-schema.org/)
- [Lark Parser](https://lark-parser.readthedocs.io/)
- [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)
- [ONNX Operators](https://onnx.ai/onnx/operators/) - Similar approach for ML operators
