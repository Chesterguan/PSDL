# PSDL - Patient Scenario Definition Language

[![Tests](https://github.com/Chesterguan/PSDL/actions/workflows/ci.yml/badge.svg)](https://github.com/Chesterguan/PSDL/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/psdl-lang.svg)](https://badge.fury.io/py/psdl-lang)
[![Python 3.8-3.12](https://img.shields.io/badge/Python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://opensource.org/licenses/Apache-2.0)

**An open, vendor-neutral standard for expressing clinical scenarios in healthcare AI.**

> *What SQL became for data queries, ONNX for ML models, and GraphQL for APIs — PSDL is becoming the semantic layer for clinical AI.*

## Installation

```bash
pip install psdl-lang

# With OMOP adapter
pip install psdl-lang[omop]

# With FHIR adapter
pip install psdl-lang[fhir]

# Full installation
pip install psdl-lang[full]
```

## Quick Start

```python
from psdl import PSDLParser, PSDLEvaluator, InMemoryBackend, DataPoint
from psdl.examples import get_scenario, list_scenarios
from datetime import datetime, timedelta

# List available built-in scenarios
print(list_scenarios())
# ['aki_detection', 'hyperkalemia_detection', 'lactic_acidosis', 'sepsis_screening']

# Load a built-in scenario
scenario = get_scenario("aki_detection")
print(f"Loaded: {scenario.name}")

# Set up data backend and add patient data
backend = InMemoryBackend()
now = datetime.now()

backend.add_data(
    patient_id="patient_123",
    signal_name="Cr",
    data=[
        DataPoint(now - timedelta(hours=6), 1.0),
        DataPoint(now - timedelta(hours=3), 1.3),
        DataPoint(now, 1.8),
    ]
)

# Evaluate
evaluator = PSDLEvaluator(scenario, backend)
result = evaluator.evaluate_patient(patient_id="patient_123", reference_time=now)

if result.is_triggered:
    print(f"Alert: {result.triggered_logic}")
```

## Define Your Own Scenario

```yaml
scenario: AKI_Early_Detection
version: "0.1.0"

signals:
  Cr:
    source: creatinine
    concept_id: 3016723  # OMOP concept
    unit: mg/dL

trends:
  cr_rising:
    expr: delta(Cr, 6h) > 0.3
    description: "Creatinine rise > 0.3 mg/dL in 6 hours"

  cr_high:
    expr: last(Cr) > 1.5
    description: "Current creatinine elevated"

logic:
  aki_risk:
    expr: cr_rising AND cr_high
    severity: high
    description: "Early AKI - rising and elevated creatinine"
```

```python
from psdl import PSDLParser

parser = PSDLParser()
scenario = parser.parse_file("my_scenario.yaml")
# or parse from string
scenario = parser.parse(yaml_content)
```

## Temporal Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `delta` | `delta(Cr, 6h) > 0.3` | Change over time window |
| `slope` | `slope(HR, 1h) > 5` | Linear trend (regression) |
| `last` | `last(Cr) > 1.5` | Most recent value |
| `min/max` | `max(Temp, 24h) > 38.5` | Min/max in window |
| `sma/ema` | `ema(BP, 2h) < 90` | Moving averages |
| `count` | `count(Cr, 24h) >= 2` | Observation count |

**Window formats:** `30s`, `5m`, `6h`, `1d`, `7d`

## Data Adapters

### OMOP CDM
```python
from psdl import get_omop_adapter

OMOPAdapter = get_omop_adapter()
adapter = OMOPAdapter(connection_string="postgresql://...")
```

### FHIR R4
```python
from psdl import get_fhir_adapter

FHIRAdapter = get_fhir_adapter()
adapter = FHIRAdapter(base_url="https://hapi.fhir.org/baseR4")
```

## Why PSDL?

| Challenge | Without PSDL | With PSDL |
|-----------|--------------|-----------|
| **Portability** | Logic tied to hospital systems | Same scenario runs anywhere |
| **Auditability** | Scattered across code/configs | Single version-controlled file |
| **Reproducibility** | Hidden state, implicit deps | Deterministic execution |
| **Compliance** | Manual documentation | Built-in audit primitives |

## Links

- **GitHub**: [github.com/Chesterguan/PSDL](https://github.com/Chesterguan/PSDL)
- **Documentation**: [Whitepaper](https://github.com/Chesterguan/PSDL/blob/main/docs/WHITEPAPER_EN.md)
- **Examples**: [Example Scenarios](https://github.com/Chesterguan/PSDL/tree/main/examples)
- **Try in Colab**: [Interactive Notebook](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/notebooks/PSDL_Colab_Synthea.ipynb)

## License

Apache 2.0 - See [LICENSE](https://github.com/Chesterguan/PSDL/blob/main/LICENSE) for details.
