# PSDL Conformance Test Suite

Last Updated: 2025-12-14

This directory contains the official PSDL v0.3 conformance test suite. These tests define the expected behavior of any PSDL-compliant implementation.

## Overview

The conformance tests are organized into JSON files, each covering a specific aspect of the PSDL specification:

| File | Description | Test Count |
|------|-------------|------------|
| `operator_tests.json` | Temporal operator behavior tests | ~60 tests |
| `expression_tests.json` | Expression grammar parsing tests | ~44 tests |
| `scenario_tests.json` | Scenario document and evaluation tests | ~40 tests |
| `dataset_tests.json` | Dataset specification binding tests | ~27 tests |

## Test Categories

### 1. Operator Tests (`operator_tests.json`)

Tests for all temporal operators defined in `operators.yaml`:

- **Windowed Operators**: `delta`, `slope`, `sma`, `ema`, `min`, `max`, `count`, `first`, `std`/`stddev`, `percentile`
- **Pointwise Operators**: `last`, `exists`, `missing`

Each operator test validates:
- Normal case behavior
- Edge cases (empty data, single value, all nulls)
- Boundary conditions
- Error handling

### 2. Expression Tests (`expression_tests.json`)

Tests for the expression grammar (see `grammar/expression.lark`):

- **Valid Trend Expressions**: Must parse and return numeric values
- **Invalid Trend Expressions**: Must be rejected (v0.3: no comparisons in trends)
- **Valid Logic Expressions**: Boolean predicates with comparisons and operators
- **Invalid Logic Expressions**: Syntax errors that must be rejected

### 3. Scenario Tests (`scenario_tests.json`)

Tests for complete scenario documents:

- **Document Validation**: Required fields, version checking, audit block
- **Semantic Validation**: Undefined references, circular dependencies
- **End-to-End Evaluation**: Full scenario execution with input data
- **State Machine**: State definition and transition evaluation
- **Population Filter**: Include/exclude criteria evaluation
- **Output Definitions**: Output structure and reference validation

### 4. Dataset Tests (`dataset_tests.json`)

Tests for dataset specification documents:

- **Document Validation**: Required fields, data model, element structure
- **Element Definitions**: Table, filter, unit configurations
- **FHIR Data Model**: FHIR-specific binding patterns
- **Valueset Definitions**: Inline and external valueset references
- **Unit Conversions**: Conversion declarations and validation
- **Scenario Binding**: Scenario-to-dataset binding resolution

## Test Format

All tests follow a standardized JSON format aligned with HL7 (CQL/FHIRPath) patterns:

```json
{
  "id": "unique_test_id",
  "name": "Human-readable test name",
  "expression": "delta(Cr, 48h)",          // For expression/operator tests
  "scenario": { ... },                      // For scenario tests
  "dataset": { ... },                       // For dataset tests
  "input": {                                // For evaluation tests
    "patient_id": "P001",
    "evaluationTime": "2024-01-01T12:00:00Z",
    "data": { ... }
  },
  "expected": { ... },                      // Expected output
  "invalid": "false|syntax|semantic",       // Validity status
  "errorCode": "E001",                      // Optional error code
  "explanation": "Why this test exists"
}
```

### Validity Status

- `"false"` - Test input is valid, should parse/evaluate successfully
- `"syntax"` - Test input has syntax errors, must be rejected at parse time
- `"semantic"` - Test input has semantic errors, must be rejected at validation time

### Error Codes

| Code | Description |
|------|-------------|
| E001 | Syntax error (invalid grammar) |
| E002 | Missing required field |
| E003 | Invalid enum value |
| E004 | Physical binding in scenario (forbidden) |
| E005 | Circular reference |
| E006 | Invalid state machine reference |
| E007 | Missing binding in dataset |
| E008 | Unit mismatch (strict mode) |

## Conformance Levels

Tests are organized by conformance level (see `CONFORMANCE.md`):

| Level | Description | Required For |
|-------|-------------|--------------|
| 1 | Document parsing | All implementations |
| 2 | Expression parsing | All implementations |
| 3 | Semantic validation | All implementations |
| 4 | Single evaluation | Evaluators |
| 5 | Batch evaluation | Batch runtimes |
| 6 | Streaming | Streaming runtimes |

## Running Tests

### Python Reference Implementation

```bash
# Run all conformance tests
pytest tests/test_conformance.py -v

# Run specific test file
pytest tests/test_conformance.py -k "operator" -v

# Run with coverage
pytest tests/test_conformance.py --cov=src/psdl -v
```

### Implementing Your Own Runner

1. Parse each test file as JSON
2. For each test in each group:
   - If `invalid` is `"false"`: expect success, validate `expected` output
   - If `invalid` is `"syntax"`: expect parse error
   - If `invalid` is `"semantic"`: expect validation error
3. Report pass/fail with explanations

## Contributing Tests

When adding new tests:

1. Use descriptive `id` with prefix matching the group (e.g., `sma_001`, `sm_003`)
2. Include clear `name` and `explanation`
3. Cover normal cases, edge cases, and error conditions
4. Validate JSON syntax before committing
5. Update this README with new test counts

## Schema Validation

Tests can be validated against the schema:

```bash
# Validate test file against schema
python -c "
import json
import jsonschema

schema = json.load(open('spec/conformance/conformance-tests.schema.json'))
tests = json.load(open('spec/conformance/operator_tests.json'))
jsonschema.validate(tests, schema)
print('✓ Valid')
"
```

## References

- [PSDL Specification](../README.md)
- [CONFORMANCE.md](../CONFORMANCE.md) - Conformance requirements
- [operators.yaml](../operators.yaml) - Operator definitions
- [schema.json](../schema.json) - Scenario schema
- [dataset_schema.json](../dataset_schema.json) - Dataset schema
