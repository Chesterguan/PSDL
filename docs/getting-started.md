# Getting Started with PSDL

This guide will help you get started with PSDL (Patient Scenario Definition Language).

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Install from Source

```bash
# Clone the repository
git clone https://github.com/psdl-lang/psdl.git
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
from runtime.python import PSDLParser

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
from runtime.python import PSDLParser, PSDLEvaluator
from runtime.python.evaluator import InMemoryBackend
from runtime.python.operators import DataPoint
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

## Next Steps

- Browse [example scenarios](../examples/) for clinical use cases
- Read the [language specification](../spec/schema-v0.1.yaml)
- Learn about [temporal operators](../spec/operators.md)
- Contribute your own scenarios!

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_parser.py -v
pytest tests/test_evaluator.py -v
```
