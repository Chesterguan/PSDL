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
from psdl.examples import get_scenario, list_scenarios
from psdl.runtimes.single import SinglePatientEvaluator, InMemoryBackend
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

backend.add_observation(123, "Cr", 1.0, now - timedelta(hours=6))
backend.add_observation(123, "Cr", 1.3, now - timedelta(hours=3))
backend.add_observation(123, "Cr", 1.8, now)

# Evaluate
evaluator = SinglePatientEvaluator(scenario, backend)
result = evaluator.evaluate(patient_id=123, reference_time=now)

if result.is_triggered:
    print(f"Alert: {result.triggered_logic}")
```

## Define Your Own Scenario

```yaml
scenario: AKI_Early_Detection
version: "0.3.0"

audit:
  intent: "Detect early acute kidney injury using creatinine trends"
  rationale: "Early AKI detection enables timely intervention"
  provenance: "KDIGO Clinical Practice Guideline for AKI (2012)"

signals:
  Cr:
    ref: creatinine        # Semantic reference (resolved via Dataset Spec)
    unit: mg/dL

trends:
  # v0.3: Trends produce numeric values only
  cr_delta:
    expr: delta(Cr, 6h)
    description: "Creatinine change over 6 hours"

  cr_current:
    expr: last(Cr)
    description: "Current creatinine value"

logic:
  # v0.3: Comparisons belong in logic layer
  cr_rising:
    when: cr_delta > 0.3
    description: "Rising creatinine"

  cr_high:
    when: cr_current > 1.5
    description: "Elevated creatinine"

  aki_risk:
    when: cr_rising AND cr_high
    severity: high
    description: "Early AKI - rising and elevated creatinine"
```

```python
from psdl.core import parse_scenario

scenario = parse_scenario("my_scenario.yaml")
# or parse from string
scenario = parse_scenario(yaml_content)
```

## Temporal Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `delta` | `delta(Cr, 6h)` | Change over time window |
| `slope` | `slope(HR, 1h)` | Linear trend (regression) |
| `last` | `last(Cr)` | Most recent value |
| `min/max` | `max(Temp, 24h)` | Min/max in window |
| `sma/ema` | `ema(BP, 2h)` | Moving averages |
| `count` | `count(Cr, 24h)` | Observation count |

**Window formats:** `30s`, `5m`, `6h`, `1d`, `7d`

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
- **Try in Colab**: [Interactive Notebook](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/examples/notebooks/PSDL_Colab_Synthea.ipynb)

## License

Apache 2.0 - See [LICENSE](https://github.com/Chesterguan/PSDL/blob/main/LICENSE) for details.
