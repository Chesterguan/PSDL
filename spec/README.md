# PSDL Specification v0.2

> **PSDL is not a query language.** It defines clinical detection intent, not execution.
> PSDL outputs IR (Intermediate Representation). Backends (SQL/Flink) handle execution.

This directory contains the **source of truth** for the Patient Scenario Definition Language (PSDL).

## Directory Structure

```
spec/
├── VERSION                     # Current specification version (0.2.0)
├── schema.json                 # JSON Schema for scenario documents
├── operators.yaml              # Operator semantics + implementation templates
├── grammar/
│   ├── expression.lark         # Lark grammar for parsing expressions
│   └── expression.ebnf         # Human-readable EBNF grammar
└── conformance/
    └── operator_tests.json     # Conformance test cases
```

## Specification Files

### `schema.json` - Scenario Structure

JSON Schema (Draft 2020-12) defining the structure of PSDL scenario files.

**Usage:**
```python
import json
import jsonschema
import yaml

with open('spec/schema.json') as f:
    schema = json.load(f)

with open('examples/aki_detection.yaml') as f:
    scenario = yaml.safe_load(f)

jsonschema.validate(scenario, schema)
```

**Code Generation:**
```bash
# Generate Python types using datamodel-codegen
pip install datamodel-code-generator
datamodel-codegen --input spec/schema.json --output src/psdl/_generated/schema_types.py
```

### `operators.yaml` - Operator Semantics

Formal definition of all PSDL temporal operators including:
- Type signatures
- Semantic descriptions
- Null handling rules
- Implementation templates for Python, PostgreSQL, and Flink SQL

**Operators Defined:**

| Category | Operators |
|----------|-----------|
| **Windowed** | `delta`, `slope`, `sma`, `ema`, `min`, `max`, `count`, `first`, `std`/`stddev`, `percentile` |
| **Pointwise** | `last`, `exists`, `missing` |
| **Comparison** | `==`, `!=`, `<`, `<=`, `>`, `>=` |
| **Boolean** | `AND`, `OR`, `NOT` |

### `grammar/expression.lark` - Expression Syntax

Lark grammar for parsing trend and logic expressions.

**Usage:**
```python
from lark import Lark

with open('spec/grammar/expression.lark') as f:
    parser = Lark(f.read(), start='trend_expr')

tree = parser.parse("delta(Cr, 48h) >= 0.3")
```

## Code Generation Pipeline

```
spec/schema.json         → datamodel-codegen → _generated/schema_types.py
spec/grammar/*.lark      → Lark runtime      → Parser (no codegen needed)
spec/operators.yaml      → tools/codegen.py  → _generated/operators_*.py
```

Run code generation:
```bash
make codegen
```

## Conformance Levels

| Level | What it validates | Tool |
|-------|-------------------|------|
| **Level 1** | Document structure | JSON Schema |
| **Level 2** | Expression syntax | Lark grammar |
| **Level 3** | Semantic validity | Validator |
| **Level 4** | Operator behavior | Conformance tests |

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.2.0 | 2025-12 | Added operators.yaml, percentile operator, std/stddev aliases, audit block, state machine |
| 0.1.0 | 2025-12 | Initial specification |

## Related Files

- `docs/GLOSSARY.md` - Terminology definitions
- `docs/glossary.json` - Machine-readable terminology
- `rfcs/0003-architecture-refactor.md` - Architecture design document
