# PSDL Conformance Specification

**Version**: 0.3.0
**Status**: Draft
**Last Updated**: 2025-12-14

This document defines conformance requirements for PSDL implementations. It uses RFC 2119 keywords (MUST, SHOULD, MAY) to specify requirement levels.

## 1. Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt).

| Term | Definition |
|------|------------|
| **Scenario** | A PSDL document defining clinical detection logic (WHAT to detect) |
| **Dataset Spec** | A binding document mapping semantic refs to physical data (WHERE to find) |
| **Parser** | Component that reads and validates PSDL documents |
| **Evaluator** | Component that executes parsed scenarios against data |
| **Adapter** | Component that connects to data sources using Dataset Specs |

## 2. Conformance Levels

PSDL defines five conformance classes. Implementations MAY claim conformance to one or more classes.

### 2.1 Conformance Classes

| Class | Components | Use Case |
|-------|------------|----------|
| **Core** | Signals, Trends (numeric), Logic (boolean), Audit | Minimum viable implementation |
| **State** | Core + State Machine | Stateful clinical detection |
| **Population** | Core + Population filters | Cohort selection |
| **Streaming** | Core + Watermarks, Windows, Late data | Real-time systems |
| **Full** | All above + Outputs | Complete reference implementation |

### 2.2 Claiming Conformance

An implementation claiming conformance to a class MUST:
1. Pass all conformance tests for that class
2. Document any extensions or deviations
3. Specify the PSDL version (e.g., "PSDL 0.3 Core Conformant")

## 3. Core Conformance Requirements

### 3.1 Document Structure

**[CORE-001]** Parser MUST accept documents conforming to `spec/schema.json`.

**[CORE-002]** Parser MUST reject documents missing required fields (`psdl_version`, `scenario`, `signals`, `logic`, `audit`).

**[CORE-003]** Parser MUST validate `psdl_version` and reject unsupported major versions.

**[CORE-004]** Parser SHOULD provide clear error messages with line numbers for validation failures.

### 3.2 Version Semantics

**[CORE-010]** `psdl_version` determines parser behavior. Parser MUST:
- Accept documents where `psdl_version` major.minor matches supported version
- Reject documents where major version differs
- Accept documents where patch version differs

**[CORE-011]** `scenario.version` is content version. Parser MUST NOT interpret it for parsing behavior.

### 3.3 Signal References

**[CORE-020]** Signals MUST use semantic references only (`ref` field).

**[CORE-021]** Signals MUST NOT contain physical bindings (concept_id, table, column names).

**[CORE-022]** Signal `ref` values MUST be lowercase alphanumeric with underscores.

**[CORE-023]** `expected_unit` is a constraint for validation against Dataset Spec, not a data requirement.

### 3.4 Trend Expressions

**[CORE-030]** Trend expressions MUST produce numeric values only.

**[CORE-031]** Parser MUST reject trend expressions containing comparison operators (`>`, `>=`, `<`, `<=`, `==`, `!=`).

**[CORE-032]** Evaluator MUST implement all windowed operators: `delta`, `slope`, `sma`, `ema`, `min`, `max`, `count`, `first`, `std`/`stddev`.

**[CORE-033]** Evaluator MUST implement all pointwise operators: `last`, `exists`, `missing`.

**[CORE-034]** Operator implementations MUST conform to semantics in `spec/operators.yaml`.

**[CORE-035]** Operators MUST handle null/missing data according to `spec/operators.yaml` null handling rules.

### 3.5 Logic Expressions

**[CORE-040]** Logic expressions MUST produce boolean values.

**[CORE-041]** Logic expressions MUST use `when` field (not `expr`) in v0.3.

**[CORE-042]** Evaluator MUST implement boolean operators: `AND`, `OR`, `NOT`.

**[CORE-043]** Evaluator MUST implement comparison operators: `>`, `>=`, `<`, `<=`, `==`, `!=`.

**[CORE-044]** Logic expressions MAY reference other logic rules by name.

**[CORE-045]** Evaluator MUST detect and reject circular logic references.

### 3.6 Audit Block

**[CORE-050]** Audit block MUST be present and contain `intent`, `rationale`, `provenance`.

**[CORE-051]** `intent` and `rationale` MUST have minimum 10 characters.

**[CORE-052]** Evaluator SHOULD preserve audit information in output for traceability.

### 3.7 Determinism

**[CORE-060]** Evaluation MUST be deterministic: same scenario + same data + same reference time = same result.

**[CORE-061]** Evaluator MUST NOT introduce non-determinism (random values, current time, etc.).

**[CORE-062]** All state MUST be derived from input data, not external sources.

## 4. Dataset Spec Conformance Requirements

### 4.1 Document Structure

**[DATASET-001]** Parser MUST accept documents conforming to `spec/dataset_schema.json`.

**[DATASET-002]** Parser MUST reject documents missing required fields (`psdl_version`, `dataset`, `data_model`, `elements`).

### 4.2 Element Binding

**[DATASET-010]** Elements MUST map semantic refs (lowercase) to physical locations.

**[DATASET-011]** Element names MUST match `signal.ref` values in scenarios.

**[DATASET-012]** Adapter MUST report error if scenario references undefined elements.

### 4.3 Unit Handling

**[DATASET-020]** Default unit strategy MUST be `strict`.

**[DATASET-021]** In `strict` mode, Adapter MUST error if `element.unit` differs from `signal.expected_unit`.

**[DATASET-022]** In `allow_declare` mode, conversions MUST be explicitly declared in Dataset Spec.

**[DATASET-023]** Runtime unit conversion MUST NOT involve external services.

### 4.4 Valueset Handling

**[DATASET-030]** Valuesets MUST be static sets (no runtime expansion).

**[DATASET-031]** External valueset files SHOULD include SHA-256 hash for audit.

**[DATASET-032]** Adapter MUST NOT query online terminology services for valueset expansion.

## 5. State Machine Conformance (State Class)

**[STATE-001]** State machine MUST define `initial` state.

**[STATE-002]** All states in `transitions` MUST be declared in `states` array.

**[STATE-003]** Transition `when` MUST reference a logic rule.

**[STATE-004]** State machine evaluation MUST be deterministic given event order.

**[STATE-005]** State machine MUST NOT have side effects.

## 6. Population Conformance (Population Class)

**[POP-001]** `include` criteria use AND logic (all must be true).

**[POP-002]** `exclude` criteria use OR logic (any excludes patient).

**[POP-003]** Population filter MUST be evaluated before trend/logic evaluation.

## 7. Streaming Conformance (Streaming Class)

**[STREAM-001]** Streaming evaluator MUST support event-time processing.

**[STREAM-002]** Watermarks MUST be configurable via `max_out_of_orderness`.

**[STREAM-003]** Late data handling MUST support policies: `DROP`, `ALLOW`, `SIDE_OUTPUT`.

**[STREAM-004]** Window functions MUST support sliding windows with configurable slide.

## 8. Expression Grammar Conformance

### 8.1 Trend Expression Grammar

Conforming parsers MUST accept expressions matching this grammar:

```ebnf
trend_expr    = numeric_expr ;
numeric_expr  = func_call
              | numeric_expr arith_op numeric_expr
              | "(" numeric_expr ")"
              | NUMBER ;
func_call     = FUNC_NAME "(" signal_ref ")"
              | FUNC_NAME "(" signal_ref "," window ")" ;
signal_ref    = IDENTIFIER ;
window        = NUMBER UNIT ;
arith_op      = "+" | "-" | "*" | "/" ;
FUNC_NAME     = "delta" | "slope" | "sma" | "ema" | "min" | "max"
              | "count" | "first" | "last" | "std" | "stddev"
              | "exists" | "missing" | "percentile" ;
UNIT          = "s" | "m" | "h" | "d" | "w" ;
```

### 8.2 Logic Expression Grammar

Conforming parsers MUST accept expressions matching this grammar:

```ebnf
logic_expr    = comparison
              | logic_ref
              | logic_expr bool_op logic_expr
              | "NOT" logic_expr
              | "(" logic_expr ")" ;
comparison    = numeric_value comp_op numeric_value ;
numeric_value = trend_ref | numeric_expr | NUMBER ;
trend_ref     = IDENTIFIER ;
logic_ref     = IDENTIFIER ;
comp_op       = ">" | ">=" | "<" | "<=" | "==" | "!=" ;
bool_op       = "AND" | "OR" ;
```

### 8.3 Type Checking

**[EXPR-001]** Parser MUST reject trend expressions that would produce boolean values.

**[EXPR-002]** Parser MUST reject logic expressions that would produce numeric values.

**[EXPR-003]** Type errors MUST fail fast at parse time, not runtime.

## 9. Conformance Tests

### 9.1 Test Categories

| Category | Location | Description |
|----------|----------|-------------|
| **Operator Tests** | `spec/conformance/operator_tests.json` | Verify temporal operator semantics |
| **Expression Tests** | `spec/conformance/expression_tests.json` | Verify expression grammar parsing |
| **Scenario Tests** | `spec/conformance/scenario_tests.json` | Scenario structure and evaluation |
| **Dataset Tests** | `spec/conformance/dataset_tests.json` | Dataset binding validation |

See `spec/conformance/README.md` for detailed documentation on test structure and running tests.

### 9.2 Test Format

Tests follow a standardized JSON format aligned with HL7 (CQL/FHIRPath) patterns:

**Expression Test Example:**
```json
{
  "id": "trend_invalid_001",
  "name": "Comparison in trend (v0.3 violation)",
  "expression": "delta(Cr, 48h) >= 0.3",
  "invalid": "syntax",
  "errorCode": "E001",
  "explanation": "v0.3: Comparisons not allowed in trend expressions"
}
```

**Operator Test Example:**
```json
{
  "id": "delta_001",
  "name": "Normal case - positive delta",
  "input": {
    "signal": "Cr",
    "data": [
      {"timestamp": "2024-01-01T00:00:00Z", "value": 1.0},
      {"timestamp": "2024-01-01T12:00:00Z", "value": 1.5}
    ],
    "expression": "delta(Cr, 48h)",
    "evaluationTime": "2024-01-01T12:00:00Z"
  },
  "expected": 0.5,
  "invalid": "false",
  "explanation": "1.5 - 1.0 = 0.5"
}
```

**Scenario Evaluation Test Example:**
```json
{
  "id": "e2e_001",
  "name": "AKI Stage 1 detection - positive",
  "scenario": {
    "psdl_version": "0.3",
    "scenario": {"name": "aki_simple", "version": "1.0.0"},
    "audit": {...},
    "signals": {"Cr": {"ref": "creatinine"}},
    "trends": {"cr_delta_48h": {"type": "float", "expr": "delta(Cr, 48h)"}},
    "logic": {"aki_stage1": {"when": "cr_delta_48h >= 0.3"}}
  },
  "input": {
    "patient_id": "P001",
    "evaluationTime": "2024-01-01T12:00:00Z",
    "data": {"creatinine": [...]}
  },
  "expected": {
    "trends": {"cr_delta_48h": 0.5},
    "logic": {"aki_stage1": true}
  },
  "invalid": "false",
  "explanation": "Creatinine rose 0.5 mg/dL, exceeds 0.3 threshold"
}
```

**Validity Status Values:**
- `"false"` - Valid input, should parse/evaluate successfully
- `"syntax"` - Syntax error, must be rejected at parse time
- `"semantic"` - Semantic error, must be rejected at validation time

### 9.3 Running Conformance Tests

```bash
# Run all conformance tests
psdl conformance --all

# Run specific class
psdl conformance --class core

# Generate conformance report
psdl conformance --report conformance_report.json
```

## 10. Error Codes

| Code | Description | Requirement |
|------|-------------|-------------|
| E001 | Comparison operator in trend expression | CORE-031 |
| E002 | Missing required field | CORE-002 |
| E003 | Unsupported PSDL version | CORE-003 |
| E004 | Physical binding in scenario | CORE-021 |
| E005 | Circular logic reference | CORE-045 |
| E006 | Undefined element reference | DATASET-012 |
| E007 | Unit mismatch in strict mode | DATASET-021 |
| E008 | Invalid state transition | STATE-002 |

## 11. Implementation Notes

### 11.1 Reference Implementation

The Python reference implementation in `src/psdl/` demonstrates Full conformance. Use it as a reference for:
- Expression parsing (`src/psdl/core/expression_parser.py`)
- Operator semantics (`src/psdl/operators.py`)
- Evaluation (`src/psdl/runtimes/single/evaluator.py`)

### 11.2 Extending PSDL

Implementations MAY add extensions if they:
1. Do not change semantics of conformant features
2. Are clearly documented as extensions
3. Use a namespace prefix (e.g., `x-myvendor-feature`)

### 11.3 Deprecation Policy

Features deprecated in one minor version MUST be supported for at least one additional minor version before removal.

## Appendix A: Conformance Checklist

```
□ CORE Class
  □ CORE-001: Schema validation
  □ CORE-002: Required fields validation
  □ CORE-003: Version validation
  □ CORE-020-023: Signal reference validation
  □ CORE-030-035: Trend expression validation
  □ CORE-040-045: Logic expression validation
  □ CORE-050-052: Audit block validation
  □ CORE-060-062: Determinism requirements

□ DATASET Class
  □ DATASET-001-002: Schema validation
  □ DATASET-010-012: Element binding
  □ DATASET-020-023: Unit handling
  □ DATASET-030-032: Valueset handling

□ STATE Class
  □ STATE-001-005: State machine requirements

□ POPULATION Class
  □ POP-001-003: Population filter requirements

□ STREAMING Class
  □ STREAM-001-004: Streaming requirements
```

## Appendix B: Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.3.0 | 2025-12-14 | Initial conformance specification |
