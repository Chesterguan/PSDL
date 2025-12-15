# PSDL Development Workflow

Last Updated: 2025-12-14

## Overview

PSDL follows a **spec-first development** approach where specifications are the source of truth, and implementation code is generated or derived from specs.

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPEC (Source of Truth)                       │
├─────────────────────────────────────────────────────────────────┤
│  spec/schema.json        → Scenario structure (JSON Schema)      │
│  spec/operators.yaml     → Operator definitions                  │
│  spec/ast-nodes.yaml     → AST node definitions                  │
│  spec/grammar/*.lark     → Expression syntax (Lark grammar)      │
│  spec/conformance/*.json → Operator conformance tests            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ codegen (industry-standard tools)
┌─────────────────────────────────────────────────────────────────┐
│                     GENERATED CODE                               │
├─────────────────────────────────────────────────────────────────┤
│  src/psdl/_generated/                                            │
│    schema_types.py   ← datamodel-code-generator (schema.json)    │
│    operators_meta.py ← Jinja2 template (operators.yaml)          │
│    sql_templates.py  ← Jinja2 template (operators.yaml)          │
│    ast_types.py      ← Jinja2 template (ast-nodes.yaml)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ import & extend
┌─────────────────────────────────────────────────────────────────┐
│                     MANUAL CODE (High-Quality)                   │
├─────────────────────────────────────────────────────────────────┤
│  src/psdl/core/                                                  │
│    parser.py         → YAML parsing logic                        │
│    ir.py             → Runtime-only types (EvaluationResult)     │
│    expression_parser.py → Lark transformer (semantic mapping)    │
│                                                                  │
│  src/psdl/runtimes/                                              │
│    single/evaluator.py   → Single patient evaluation             │
│    cohort/compiler.py    → SQL compilation logic                 │
│    streaming/            → Streaming evaluation                  │
│                                                                  │
│  src/psdl/operators.py   → Operator implementations              │
└─────────────────────────────────────────────────────────────────┘
```

## Development Cycle

### 1. Spec Changes

When changing PSDL behavior, **always start with the spec**:

```bash
# 1. Edit the relevant spec file
vim spec/schema.json           # For scenario structure
vim spec/operators.yaml        # For operator definitions
vim spec/ast-nodes.yaml        # For AST node types
vim spec/grammar/expression.lark  # For expression syntax

# 2. Update conformance tests if needed
vim spec/conformance/operators.json
```

### 2. Regenerate Code

After spec changes, regenerate all derived code:

```bash
# Regenerate everything
python tools/codegen.py --all

# Or regenerate specific parts
python tools/codegen.py --types      # schema.json → schema_types.py
python tools/codegen.py --operators  # operators.yaml → operators_meta.py
python tools/codegen.py --sql        # operators.yaml → sql_templates.py
python tools/codegen.py --ast        # ast-nodes.yaml → ast_types.py

# Validate implementations match spec
python tools/codegen.py --validate
```

### 3. Update Manual Code

If spec changes require manual code updates:

```bash
# Parser changes
vim src/psdl/core/parser.py

# Expression transformer (Lark → AST semantic mapping)
vim src/psdl/expression_parser.py

# Operator implementations
vim src/psdl/operators.py

# Evaluation logic
vim src/psdl/runtimes/single/evaluator.py
```

### 4. Update Tests

```bash
# Run all tests
pytest tests/ -v

# Run conformance tests specifically
pytest tests/test_conformance.py -v

# Run with coverage
pytest tests/ --cov=src/psdl --cov-report=html
```

### 5. CI Check

Before committing:

```bash
# Check if regeneration is needed
python tools/codegen.py --check

# Format code
black src tests
isort src tests

# Lint
flake8 src tests --max-line-length=120 --ignore=E501,W503,E712,F541
```

## Code Generation Tools

| Tool | Input | Output | Purpose |
|------|-------|--------|---------|
| `datamodel-code-generator` | schema.json | schema_types.py | JSON Schema → Python dataclasses |
| Jinja2 | operators.yaml | operators_meta.py | Operator metadata |
| Jinja2 | operators.yaml | sql_templates.py | PostgreSQL CTE templates |
| Jinja2 | ast-nodes.yaml | ast_types.py | AST node dataclasses |

## Spec Files

| File | Format | Purpose |
|------|--------|---------|
| `spec/schema.json` | JSON Schema | PSDL scenario structure |
| `spec/operators.yaml` | YAML | Operator definitions (signature, semantics, SQL) |
| `spec/ast-nodes.yaml` | YAML | AST node type definitions |
| `spec/grammar/expression.lark` | Lark | Expression syntax grammar |
| `spec/conformance/*.json` | JSON | Conformance test cases |

## Quality Standards

### Generated Code
- **NEVER edit** files in `src/psdl/_generated/`
- Regenerate using `python tools/codegen.py --all`
- Check with `--check` flag in CI

### Manual Code
- **High-quality**: Clear, well-documented, tested
- **Minimal**: Only semantic/algorithmic logic
- **Spec-aligned**: Import from generated types where possible
- **No duplication**: Don't redefine types that exist in generated code

## Example: Adding a New Operator

```bash
# 1. Add to spec/operators.yaml
vim spec/operators.yaml
# Add under operators.windowed or operators.pointwise

# 2. Add conformance tests
vim spec/conformance/operators.json

# 3. Regenerate
python tools/codegen.py --all

# 4. Implement in operators.py
vim src/psdl/operators.py

# 5. Run tests
pytest tests/ -v
```

## Example: Adding a New AST Node Type

```bash
# 1. Add to spec/ast-nodes.yaml
vim spec/ast-nodes.yaml
# Add under nodes section with fields and type info

# 2. Regenerate AST types
python tools/codegen.py --ast

# 3. Import in expression_parser.py if needed for Lark transformer
# Types are already exported via psdl._generated.ast_types

# 4. Run tests
pytest tests/ -v
```

## Type Consolidation Pattern

Generated types are the single source of truth. Manual code imports from generated modules:

```python
# expression_parser.py - imports AST types
from psdl._generated.ast_types import (
    WindowSpec, TemporalCall, TrendExpression, ComparisonExpr,
    TermRef, AndExpr, OrExpr, NotExpr, LogicNode
)

# ir.py - imports shared types
from psdl._generated.ast_types import WindowSpec, LogicNode
```

This ensures:
- No duplicate type definitions
- Type consistency across modules
- Changes propagate automatically via regeneration

## Example: Changing Scenario Schema

```bash
# 1. Update JSON schema
vim spec/schema.json

# 2. Regenerate types
python tools/codegen.py --types

# 3. Update parser if needed
vim src/psdl/core/parser.py

# 4. Update tests
pytest tests/test_parser.py -v
```
