# Auto-Generated Code

**⚠️ DO NOT EDIT FILES IN THIS DIRECTORY MANUALLY ⚠️**

All files in `src/psdl/_generated/` are automatically generated from specification files by `tools/codegen.py`.

## Generation Map

| Generated File | Source Spec | Purpose |
|----------------|-------------|---------|
| `ast_types.py` | `spec/ast-nodes.yaml` | AST node dataclasses for expression parsing |
| `transformer.py` | `spec/ast-nodes.yaml` | Lark transformer for AST construction |
| `operators_meta.py` | `spec/operators.yaml` | Operator metadata (signatures, semantics) |
| `sql_templates.py` | `spec/operators.yaml` | SQL generation templates per operator |
| `schema_types.py` | `spec/schema.json` | TypedDict types for scenario structure |
| `conformance_tests.py` | `spec/conformance/*.json` | Test cases for conformance validation |
| `validate.py` | `spec/schema.json` | Schema validation functions |

## How to Regenerate

```bash
# From project root
python tools/codegen.py

# Verify checksums
cat src/psdl/_generated/.checksums
```

## Checksum Verification

The `.checksums` file tracks MD5 hashes of source specs. If a spec changes, codegen will detect the drift and regenerate.

## What is NOT Generated

The following are **manually written** and NOT auto-generated:

| File | Reason |
|------|--------|
| `core/dataset.py` | Runtime YAML loader, validates against JSON Schema at runtime |
| `core/parser.py` | Complex parsing logic beyond what can be generated |
| `core/ir.py` | Core IR types with custom methods |
| `core/compile.py` | Compilation logic |
| `adapters/*.py` | Backend-specific execution code |
| `runtimes/*.py` | Execution runtime code |

## Design Principle

```
Spec files (YAML/JSON) → codegen.py → _generated/*.py
                                      ↓
                              Manual code imports from _generated
```

The spec is the source of truth. Generated code provides type-safe access to spec-defined structures.
