# PSDL Formal Specification

This directory contains the machine-readable formal specification for PSDL (Patient Scenario Definition Language) v0.1.

## Specification Components

| File | Format | Purpose |
|------|--------|---------|
| `psdl-scenario.schema.json` | JSON Schema (2020-12) | Document structure validation |
| `psdl-expression.ebnf` | ISO EBNF | Expression grammar definition |

## Architecture

PSDL uses a two-layer specification approach (similar to SQL):

```
┌─────────────────────────────────────────────────────────────┐
│                    PSDL Scenario Document                    │
│                    (YAML or JSON format)                     │
├─────────────────────────────────────────────────────────────┤
│  Document Structure          │  Expression Language          │
│  ────────────────────        │  ────────────────────         │
│  Validated by:               │  Validated by:                │
│  JSON Schema                 │  EBNF Grammar                 │
│                              │                               │
│  • scenario name             │  • Temporal operators         │
│  • version                   │    delta, slope, ema, etc.    │
│  • signals section           │  • Comparisons                │
│  • trends section            │    >, <, >=, <=, ==, !=       │
│  • logic section             │  • Boolean logic              │
│  • mapping section           │    AND, OR, NOT               │
└─────────────────────────────────────────────────────────────┘
```

## JSON Schema Usage

### Validation with Python

```python
import json
import jsonschema
import yaml

# Load schema
with open('psdl-scenario.schema.json') as f:
    schema = json.load(f)

# Load and validate a PSDL scenario
with open('../../examples/aki_detection.yaml') as f:
    scenario = yaml.safe_load(f)

jsonschema.validate(scenario, schema)
print("Scenario is valid!")
```

### Validation with CLI tools

```bash
# Using ajv (npm install -g ajv-cli)
ajv validate -s psdl-scenario.schema.json -d ../../examples/aki_detection.yaml

# Using check-jsonschema (pip install check-jsonschema)
check-jsonschema --schemafile psdl-scenario.schema.json ../../examples/aki_detection.yaml
```

## EBNF Grammar Usage

The EBNF grammar defines the syntax for trend and logic expressions. It can be used to:

1. **Generate parsers** using tools like:
   - ANTLR (convert EBNF to ANTLR4 grammar)
   - Lark (Python parser generator)
   - PEG.js (JavaScript parser generator)

2. **Validate expressions** before runtime evaluation

3. **Document the language** formally for other implementations

### Example Expressions

**Trend Expressions:**
```
delta(Cr, 6h) > 0.3       # Creatinine change over 6 hours
slope(Lact, 3h) > 0       # Lactate trend direction
last(HR) > 100            # Current heart rate
count(Cr, 48h) >= 2       # Number of measurements
```

**Logic Expressions:**
```
cr_rising AND lactate_elevated
aki_stage1 OR aki_stage2 OR aki_stage3
NOT recovering AND deteriorating
(fever OR hypothermia) AND tachycardia
```

## Conformance Levels

A PSDL implementation can claim conformance at different levels:

| Level | Requirements |
|-------|--------------|
| **Level 1: Document** | Validates documents against JSON Schema |
| **Level 2: Expression** | Parses expressions per EBNF grammar |
| **Level 3: Semantic** | Validates signal/trend/logic references |
| **Level 4: Runtime** | Correctly evaluates all operators |

The Python reference implementation is Level 4 conformant.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2024-12 | Initial formal specification |

## Related Standards

- **JSON Schema**: https://json-schema.org/
- **ISO EBNF**: ISO/IEC 14977:1996
- **OMOP CDM**: https://ohdsi.github.io/CommonDataModel/
- **FHIR R4**: https://hl7.org/fhir/R4/
