# Getting Started with PSDL

This guide will help you get started with PSDL (Patient Scenario Definition Language).

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Install from Source

```bash
# Clone the repository
git clone https://github.com/Chesterguan/PSDL.git
cd psdl

# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Your First Scenario

Create a file called `my_scenario.yaml`:

```yaml
scenario: My_First_Scenario
version: "0.1.0"
description: "Detect elevated creatinine"

signals:
  Cr:
    source: creatinine
    concept_id: 3016723
    unit: mg/dL

trends:
  cr_high:
    expr: last(Cr) > 1.5
    description: "Creatinine above normal"

logic:
  renal_concern:
    expr: cr_high
    severity: medium
    description: "Potential kidney issue"
```

## Parse and Validate

```python
from reference.python import PSDLParser

# Parse the scenario
parser = PSDLParser()
scenario = parser.parse_file("my_scenario.yaml")

# Check what was parsed
print(f"Scenario: {scenario.name}")
print(f"Signals: {list(scenario.signals.keys())}")
print(f"Trends: {list(scenario.trends.keys())}")
print(f"Logic: {list(scenario.logic.keys())}")
```

## Evaluate Against Data

```python
from reference.python import PSDLParser, PSDLEvaluator
from reference.python.execution.batch import InMemoryBackend
from reference.python.operators import DataPoint
from datetime import datetime, timedelta

# Parse scenario
parser = PSDLParser()
scenario = parser.parse_file("my_scenario.yaml")

# Set up in-memory data backend
backend = InMemoryBackend()
now = datetime.now()

# Add patient data
backend.add_data(
    patient_id=123,
    signal_name="Cr",
    data=[
        DataPoint(now - timedelta(hours=6), 1.0),
        DataPoint(now - timedelta(hours=3), 1.3),
        DataPoint(now, 1.8),  # Elevated!
    ]
)

# Evaluate
evaluator = PSDLEvaluator(scenario, backend)
result = evaluator.evaluate_patient(patient_id=123, reference_time=now)

# Check results
if result.is_triggered:
    print(f"Alert! Triggered rules: {result.triggered_logic}")
    print(f"Creatinine value: {result.trend_values['cr_high']}")
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
| `ema` | `ema(MAP, 30m)` | Smoothed average |
| `sma` | `sma(HR, 1h)` | Simple average |
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
logic:
  # AND - both must be true
  both_abnormal:
    expr: cr_high AND lactate_high

  # OR - either can be true
  any_concern:
    expr: kidney_issue OR liver_issue

  # Nested logic with parentheses
  complex:
    expr: (cr_high AND lactate_rising) OR shock_state
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
- **Hospitals** create a mapping file for their local codes (no code)
- **Adapters** are shared infrastructure (OMOP, FHIR)

## Using with OMOP CDM

### Step 1: Choose or Create a Mapping File

PSDL includes pre-built mappings for common datasets:

```bash
mappings/
├── mimic_iv.yaml         # MIMIC-IV (unmapped OMOP)
├── synthea.yaml          # Synthea synthetic data
└── hospital_template.yaml # Template for your institution
```

### Step 2: Connect with Mapping (Recommended)

```python
from reference.python import PSDLParser, PSDLEvaluator
from reference.python.mapping import load_mapping
from reference.python.adapters.omop import OMOPBackend, OMOPConfig

# Load your institution's mapping
mapping = load_mapping("mappings/mimic_iv.yaml")

# Configure database connection
config = OMOPConfig(
    connection_string="postgresql://user:pass@localhost/mimic",
    cdm_schema="public"
)

# Create backend with mapping
backend = OMOPBackend(config, mapping=mapping)

# Parse and evaluate scenario (uses logical signal names!)
scenario = PSDLParser().parse_file("examples/aki_detection.yaml")
evaluator = PSDLEvaluator(scenario, backend)
result = evaluator.evaluate_patient(patient_id=12345)
```

### Step 3: Create Your Own Mapping

Copy the template and customize for your institution:

```bash
cp mappings/hospital_template.yaml mappings/my_hospital.yaml
```

Edit `mappings/my_hospital.yaml`:

```yaml
institution: "My Hospital"
description: "Mapping for My Hospital OMOP database"
data_source: "OMOP CDM 5.4"

# Set to true if your database has unmapped concepts (concept_id = 0)
use_source_values: false

signals:
  creatinine:
    concept_id: 3016723      # Your local concept ID
    unit: "mg/dL"

  potassium:
    concept_id: 3023103
    unit: "mEq/L"

  # For unmapped databases, use source_value instead:
  # creatinine:
  #   source_value: "CREAT_SERUM"  # Your local lab code
  #   unit: "mg/dL"
```

### Finding Your Local Codes

Run this SQL to discover your codes:

```sql
-- Find measurement concept IDs and source values
SELECT DISTINCT
    measurement_concept_id,
    measurement_source_value,
    c.concept_name,
    COUNT(*) as count
FROM measurement m
LEFT JOIN concept c ON m.measurement_concept_id = c.concept_id
WHERE LOWER(measurement_source_value) LIKE '%creatinine%'
GROUP BY measurement_concept_id, measurement_source_value, c.concept_name
ORDER BY count DESC;
```

### Pre-built Dataset Support

**MIMIC-IV** (PhysioNet):
```python
from reference.python.mapping import get_mimic_iv_mapping

mapping = get_mimic_iv_mapping()  # Built-in mapping
backend = OMOPBackend(config, mapping=mapping)
```

**Synthea** (Synthetic):
```python
from reference.python.mapping import get_synthea_mapping

mapping = get_synthea_mapping()  # Built-in mapping
backend = OMOPBackend(config, mapping=mapping)
```

See [OMOP Adapter Documentation](./adapters/omop.md) for detailed setup instructions.

## Using with FHIR R4

For EHR integration using FHIR:

```python
from reference.python import PSDLParser, PSDLEvaluator
from reference.python.adapters import FHIRBackend, FHIRConfig

# Configure FHIR connection
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token="your-token-here"
)

backend = FHIRBackend(config)
scenario = PSDLParser().parse_file("my_scenario.yaml")
evaluator = PSDLEvaluator(scenario, backend)

# Evaluate patient from FHIR server
result = evaluator.evaluate_patient(patient_id="patient-uuid")
```

See [FHIR Adapter Documentation](./adapters/fhir.md) for detailed setup instructions.

## Next Steps

- Browse [example scenarios](../examples/) for clinical use cases
- Read the [language specification](../spec/schema-v0.1.yaml)
- Connect to [OMOP CDM](./adapters/omop.md) for research
- Connect to [FHIR R4](./adapters/fhir.md) for EHR integration
- Contribute your own scenarios!

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_parser.py -v
pytest tests/test_evaluator.py -v
pytest tests/test_omop_backend.py -v
```
