# Getting Started with PSDL

This guide will help you get started with PSDL (Patient Scenario Definition Language).

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Install from PyPI (Recommended)

```bash
# Basic installation
pip install psdl-lang

# With OMOP adapter support
pip install psdl-lang[omop]

# With FHIR adapter support
pip install psdl-lang[fhir]

# Full installation (all adapters)
pip install psdl-lang[full]
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/Chesterguan/PSDL.git
cd PSDL

# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"
```

## Quick Start: Use Bundled Scenarios

PSDL comes with bundled clinical scenarios you can use immediately:

```python
from psdl.examples import get_scenario, list_scenarios

# List available scenarios
print(list_scenarios())  # ['aki_detection', 'sepsis_screening', ...]

# Load a bundled scenario
scenario = get_scenario("aki_detection")

print(f"Scenario: {scenario.name}")
print(f"Signals: {list(scenario.signals.keys())}")
print(f"Logic rules: {list(scenario.logic.keys())}")
```

## Your First Scenario (v0.3 Syntax)

Create a file called `my_scenario.yaml`:

```yaml
scenario: My_First_Scenario
version: "0.3.0"
description: "Detect elevated creatinine"

audit:
  intent: "Early detection of kidney dysfunction"
  rationale: "Elevated creatinine indicates potential renal impairment"
  provenance: "Clinical best practices"

signals:
  Cr:
    ref: creatinine        # v0.3: 'ref' instead of 'source'
    concept_id: 3016723
    unit: mg/dL

trends:
  # v0.3: Trends produce numeric values only
  cr_current:
    expr: last(Cr)
    description: "Current creatinine value"

logic:
  # v0.3: Comparisons belong in logic layer with 'when'
  cr_elevated:
    when: cr_current > 1.5
    severity: medium
    description: "Creatinine above normal"
```

## Parse and Validate

```python
from psdl.core import parse_scenario

# Parse from file
scenario = parse_scenario("my_scenario.yaml")

# Or parse from string
yaml_content = """
scenario: Quick_Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_val:
    expr: last(Cr)
logic:
  elevated:
    when: cr_val > 1.5
"""
scenario = parse_scenario(yaml_content)

# Check what was parsed
print(f"Scenario: {scenario.name}")
print(f"Signals: {list(scenario.signals.keys())}")
print(f"Trends: {list(scenario.trends.keys())}")
print(f"Logic: {list(scenario.logic.keys())}")
```

## Evaluate Against Patient Data

```python
from psdl.examples import get_scenario
from psdl.runtimes.single import SinglePatientEvaluator, InMemoryBackend
from datetime import datetime, timedelta

# Load bundled scenario
scenario = get_scenario("aki_detection")

# Set up in-memory data backend
backend = InMemoryBackend()
now = datetime.now()

# Add patient data (using convenience method)
backend.add_observation(123, "Cr", 1.0, now - timedelta(hours=6))
backend.add_observation(123, "Cr", 1.3, now - timedelta(hours=3))
backend.add_observation(123, "Cr", 1.8, now)  # Elevated!

# Evaluate
evaluator = SinglePatientEvaluator(scenario, backend)
result = evaluator.evaluate(patient_id=123, reference_time=now)

# Check results
if result.is_triggered:
    print(f"Alert! Triggered rules: {result.triggered_logic}")
    print(f"Trend values: {result.trend_values}")
else:
    print("No alerts")
```

## Temporal Operators

PSDL provides operators for time-series analysis:

| Operator | Example | Description |
|----------|---------|-------------|
| `last` | `last(Cr)` | Most recent value |
| `delta` | `delta(Cr, 6h)` | Change over window |
| `slope` | `slope(Lact, 3h)` | Trend direction |
| `ema` | `ema(MAP, 30m)` | Exponential moving average |
| `sma` | `sma(HR, 1h)` | Simple moving average |
| `min` | `min(SpO2, 4h)` | Minimum in window |
| `max` | `max(Temp, 24h)` | Maximum in window |
| `count` | `count(Cr, 48h)` | Number of observations |

### Window Formats

- `30s` - 30 seconds
- `5m` - 5 minutes
- `6h` - 6 hours
- `1d` - 1 day
- `7d` - 7 days

## Logic Operators

Combine trends using boolean logic:

```yaml
trends:
  cr_delta:
    expr: delta(Cr, 48h)
  lactate_val:
    expr: last(Lactate)

logic:
  # Compare numeric trends
  cr_rising:
    when: cr_delta > 0.3

  lactate_high:
    when: lactate_val > 2.0

  # AND - both must be true
  both_abnormal:
    when: cr_rising AND lactate_high

  # OR - either can be true
  any_concern:
    when: cr_rising OR lactate_high

  # Nested logic with parentheses
  complex:
    when: (cr_rising AND lactate_high) OR shock_state
```

## Architecture: Scenarios + Mappings

PSDL separates **clinical logic** from **local terminology**:

```
┌─────────────────────────────────────────────────────────────────┐
│  PSDL Scenario (Portable)                                       │
│  - Clinical logic: "detect creatinine rise > 0.3 in 48h"        │
│  - Uses logical signal names: "creatinine", "potassium"         │
│  - Shared across institutions                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Mapping File (Institution-Specific)                            │
│  - Translates: "creatinine" → concept_id: 3016723               │
│  - Or: "creatinine" → source_value: "CREATININE_SERUM"          │
│  - Each hospital creates their own mapping                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Adapter (Shared Code)                                          │
│  - OMOP Adapter: Handles OMOP database structure                │
│  - FHIR Adapter: Handles FHIR server communication              │
│  - No code changes needed per institution                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Hospital Database                                              │
└─────────────────────────────────────────────────────────────────┘
```

This means:
- **Researchers** write scenarios using logical names (portable)
- **Hospitals** create a Dataset Spec for their local codes (no code)
- **Adapters** are shared infrastructure (OMOP, FHIR)

## Dataset Specifications (RFC-0004)

Dataset Specs formalize the mapping layer, making scenarios truly portable:

```python
from psdl import load_dataset_spec

# Load institution-specific mapping
spec = load_dataset_spec("dataset_specs/my_hospital_omop.yaml")

# Resolve a logical signal to physical binding
binding = spec.resolve("creatinine")
print(binding.table)        # "measurement"
print(binding.filter_expr)  # "concept_id = 3016723"
```

**Dataset Spec YAML format:**

```yaml
psdl_version: "0.3"
dataset:
  name: "My Hospital OMOP"
  version: "1.0.0"

data_model: omop

conventions:
  patient_id_field: person_id
  schema: cdm

elements:
  creatinine:
    table: measurement
    value_field: value_as_number
    filter:
      concept_id: 3016723
    unit: mg/dL
    kind: lab

  heart_rate:
    table: measurement
    value_field: value_as_number
    filter:
      concept_id: 3027018
    unit: beats/min
    kind: vital
```

> **Important**: Always use `load_dataset_spec()` to load specs. This validates against the JSON schema and enables the `resolve()` method.

## Using with OMOP CDM

```python
from psdl.core import parse_scenario
from psdl.adapters.omop import OMOPAdapter

# Configure database connection
adapter = OMOPAdapter(
    connection_string="postgresql://user:pass@localhost/omop",
    cdm_schema="public"
)

# Load scenario
scenario = parse_scenario("scenarios/aki_detection.yaml")

# Query patient data
patient_data = adapter.get_patient_data(
    patient_id=12345,
    signals=scenario.signals
)
```

## Using with FHIR R4

For EHR integration using FHIR:

```python
from psdl.core import parse_scenario
from psdl.adapters.fhir import FHIRAdapter

# Configure FHIR connection
adapter = FHIRAdapter(
    base_url="https://fhir.hospital.org/r4",
    auth_token="your-token-here"  # Optional
)

# Load and evaluate
scenario = parse_scenario("my_scenario.yaml")
patient_data = adapter.get_patient_data(
    patient_id="patient-uuid",
    signals=scenario.signals
)
```

## Try It in Google Colab

Run PSDL in your browser with zero installation:

| Notebook | Data | Description |
|----------|------|-------------|
| [Synthea Demo](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/examples/notebooks/PSDL_Colab_Synthea.ipynb) | Synthetic | Quick demo (2 min) |
| [MIMIC-IV Demo](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/examples/notebooks/PSDL_Colab_MIMIC_Demo.ipynb) | Real ICU | 100 patients |
| [PhysioNet Sepsis](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/examples/notebooks/PSDL_PhysioNet_Demo.ipynb) | Sepsis | 40,000+ patients |

## Next Steps

- Browse [example scenarios](../src/psdl/examples/scenarios/) for clinical use cases
- Read the [language specification](../spec/schema.json)
- Review the [Whitepaper](./WHITEPAPER.md) for full documentation
- Check the [Roadmap](./ROADMAP.md) for project status
- Contribute your own scenarios!

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_parser.py -v
pytest tests/test_evaluator.py -v
```

---

*Last updated: December 17, 2025*
