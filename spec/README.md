# PSDL Specification v0.3

> **PSDL is not a query language.** It defines clinical detection intent, not execution.
> PSDL outputs IR (Intermediate Representation). Backends (SQL/Flink) handle execution.

This directory contains the **source of truth** for the Patient Scenario Definition Language (PSDL).

## Three-Layer Architecture (RFC-0004)

PSDL uses a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: PSDL Scenario (WHAT to detect)                            │
│  File: scenarios/aki_detection.yaml                                 │
│  Schema: spec/schema.json                                           │
│                                                                     │
│  • Abstract signal references (semantic names only)                 │
│  • Trends (numeric computations)                                    │
│  • Logic (boolean predicates)                                       │
│  • Audit information                                                │
│  • 100% portable, deterministic                                     │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2: Dataset Spec (WHERE to find data)                         │
│  File: dataset_specs/mimic_iv_omop.yaml                             │
│  Schema: spec/dataset_schema.json                                   │
│                                                                     │
│  • Maps semantic refs → physical locations                          │
│  • Table names, fields, concept_ids                                 │
│  • Site-specific, version-controlled                                │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 3: Adapter/Runtime (HOW to execute)                          │
│  Code: src/psdl/adapters/, src/psdl/runtimes/                       │
│                                                                     │
│  • Loads Scenario + Dataset Spec                                    │
│  • Resolves bindings, executes queries                              │
│  • Returns evaluation results                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Why This Separation?

| Benefit | Explanation |
|---------|-------------|
| **Portability** | Same scenario runs on MIMIC, OHDSI Synthea, or hospital FHIR server |
| **Auditability** | Clear chain: scenario defines logic, dataset spec defines data source |
| **Determinism** | Scenarios are pure logic, no hidden data dependencies |
| **Separation of Concerns** | Clinical teams own scenarios, data teams own dataset specs |

## Breaking Changes in v0.3 (RFC-0005)

### 1. Trends Produce Numeric Values Only

Comparisons belong in Logic layer, not Trends.

```yaml
# v0.2 (INVALID in v0.3)
trends:
  cr_rise: delta(Cr, 48h) >= 0.3    # ❌ Mixed value + comparison

# v0.3 (CORRECT)
trends:
  cr_delta:
    type: float
    expr: delta(Cr, 48h)             # ✅ Numeric only

logic:
  cr_rise:
    when: cr_delta >= 0.3            # ✅ Comparison here
```

### 2. Version Fields Separated

```yaml
# v0.3 structure
psdl_version: "0.3"              # Spec version (determines parser behavior)
scenario:
  name: AKI_Detection
  version: "1.2.0"               # Content version (tracks clinical logic changes)
```

### 3. Signals Use Abstract References Only

```yaml
# v0.3: Abstract refs only (NO physical bindings)
signals:
  Cr:
    ref: creatinine              # ← Semantic name
    expected_unit: mg/dL         # ← Constraint (validated against Dataset Spec)

# Physical bindings go in Dataset Spec, NOT in scenario
```

See [RFC-0005](../rfcs/0005-psdl-v03-architecture.md) for full details.

## Directory Structure

```
spec/
├── VERSION                      # Current specification version (0.3.0)
├── schema.json                  # Scenario schema (WHAT to detect)
├── dataset_schema.json          # Dataset Spec schema (WHERE to find)
├── CONFORMANCE.md               # RFC-style conformance requirements
├── operators.yaml               # Operator semantics + implementation templates
├── grammar/
│   ├── expression.lark          # Lark grammar for parsing expressions
│   └── expression.ebnf          # Human-readable EBNF grammar
└── conformance/
    └── operator_tests.json      # Conformance test cases
```

## Specification Files

### `schema.json` - Scenario Structure

JSON Schema (Draft 2020-12) defining PSDL scenario documents.

**Key Rules:**
- Signals use `ref` (semantic names) - NO physical bindings
- Trends produce numeric values - NO comparisons
- Logic uses `when` field for boolean expressions
- Audit block is required

**Usage:**
```python
import json
import jsonschema
import yaml

with open('spec/schema.json') as f:
    schema = json.load(f)

with open('scenarios/aki_detection.yaml') as f:
    scenario = yaml.safe_load(f)

jsonschema.validate(scenario, schema)  # Raises on invalid
```

### `dataset_schema.json` - Dataset Spec Structure

JSON Schema defining Dataset Specification documents.

**Key Rules:**
- Elements map semantic refs to physical locations
- Valuesets are static (no runtime expansion)
- Unit strategy defaults to `strict`

**Usage:**
```python
with open('spec/dataset_schema.json') as f:
    dataset_schema = json.load(f)

with open('dataset_specs/mimic_iv_omop.yaml') as f:
    dataset_spec = yaml.safe_load(f)

jsonschema.validate(dataset_spec, dataset_schema)
```

### `CONFORMANCE.md` - Conformance Requirements

RFC-style specification of conformance requirements using MUST/SHOULD/MAY.

**Conformance Classes:**

| Class | Components | Use Case |
|-------|------------|----------|
| **Core** | Signals, Trends, Logic, Audit | Minimum viable |
| **State** | Core + State Machine | Stateful detection |
| **Population** | Core + Population filters | Cohort selection |
| **Streaming** | Core + Watermarks, Windows | Real-time |
| **Full** | All above + Outputs | Reference impl |

### `operators.yaml` - Operator Semantics

Formal definition of all PSDL temporal operators including:
- Type signatures
- Semantic descriptions
- Null handling rules
- Implementation templates for Python, PostgreSQL, and Flink SQL

**Operators:**

| Category | Operators |
|----------|-----------|
| **Windowed** | `delta`, `slope`, `sma`, `ema`, `min`, `max`, `count`, `first`, `std`/`stddev`, `percentile` |
| **Pointwise** | `last`, `exists`, `missing` |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` (Logic layer only) |
| **Boolean** | `AND`, `OR`, `NOT` |

### `grammar/expression.lark` - Expression Syntax

Lark grammar for parsing trend and logic expressions.

**Usage:**
```python
from lark import Lark

with open('spec/grammar/expression.lark') as f:
    parser = Lark(f.read(), start='trend_expr')

tree = parser.parse("delta(Cr, 48h)")  # Valid trend
# parser.parse("delta(Cr, 48h) >= 0.3")  # ERROR in trend context
```

## Code Generation Pipeline

```
spec/schema.json           → datamodel-codegen → _generated/schema_types.py
spec/dataset_schema.json   → datamodel-codegen → _generated/dataset_types.py
spec/grammar/*.lark        → Lark runtime      → Parser (no codegen needed)
spec/operators.yaml        → tools/codegen.py  → _generated/operators_*.py
```

Run code generation:
```bash
make codegen
```

## Validation Levels

| Level | What it validates | Tool |
|-------|-------------------|------|
| **Level 1** | Document structure | JSON Schema |
| **Level 2** | Expression syntax | Lark grammar |
| **Level 3** | Semantic validity | Validator |
| **Level 4** | Operator behavior | Conformance tests |
| **Level 5** | Dataset binding | Runtime validation |

## Example: Complete Flow

### 1. Scenario (WHAT to detect)

```yaml
# scenarios/aki_detection.yaml
psdl_version: "0.3"

scenario:
  name: AKI_Detection
  version: "1.0.0"
  description: "Detect AKI Stage 1 using KDIGO criteria"

audit:
  intent: "Detect acute kidney injury early to enable intervention"
  rationale: "Early AKI detection reduces progression to dialysis"
  provenance: "KDIGO 2012 Clinical Practice Guideline"

signals:
  Cr:
    ref: creatinine
    expected_unit: mg/dL
    description: "Serum creatinine"

trends:
  cr_delta_48h:
    type: float
    unit: mg/dL
    expr: delta(Cr, 48h)

logic:
  aki_stage1:
    when: cr_delta_48h >= 0.3
    severity: medium
    description: "AKI Stage 1 by KDIGO delta criterion"
```

### 2. Dataset Spec (WHERE to find data)

```yaml
# dataset_specs/mimic_iv_omop.yaml
psdl_version: "0.3"

dataset:
  name: mimic_iv_omop
  version: "1.0.0"
  description: "MIMIC-IV mapped to OMOP CDM v5.4"

data_model: omop

conventions:
  patient_id_field: person_id
  default_time_field: measurement_datetime
  timezone: UTC

elements:
  creatinine:
    kind: lab
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3016723]
    unit: mg/dL
    value_type: numeric

metadata:
  source: "PhysioNet MIMIC-IV v2.2"
  omop_version: "5.4"
  created: "2025-12-14"
```

### 3. Runtime Execution

```bash
psdl run \
  --scenario scenarios/aki_detection.yaml \
  --dataset dataset_specs/mimic_iv_omop.yaml \
  --adapter omop_sql \
  --connection "postgresql://localhost/mimic"
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.3.0 | 2025-12 | **BREAKING**: Three-layer architecture, Trend/Logic separation, Dataset Spec (RFC-0004, RFC-0005) |
| 0.2.0 | 2025-12 | Added operators.yaml, percentile operator, std/stddev aliases, audit block, state machine |
| 0.1.0 | 2025-12 | Initial specification |

## Related Documents

- [RFC-0004: Dataset Specification](../rfcs/0004-dataset-specification.md) - Portable data binding layer
- [RFC-0005: PSDL v0.3 Architecture](../rfcs/0005-psdl-v03-architecture.md) - Trend/Logic separation
- [CONFORMANCE.md](CONFORMANCE.md) - RFC-style conformance requirements
- [docs/GLOSSARY.md](../docs/GLOSSARY.md) - Terminology definitions
