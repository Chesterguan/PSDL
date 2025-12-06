# OMOP CDM Backend

Connect PSDL to [OMOP Common Data Model](https://ohdsi.github.io/CommonDataModel/) databases for retrospective research and real-time clinical decision support.

## Overview

The OMOP backend allows PSDL scenarios to query clinical data from any OMOP CDM database, enabling:

- **Retrospective Research**: Identify historical cohorts matching clinical scenarios
- **Real-time Monitoring**: Evaluate scenarios against live patient data
- **Multi-site Portability**: Same scenario works across institutions using OMOP

## Supported Versions

| CDM Version | Status | Notes |
|-------------|--------|-------|
| **v5.4** | Recommended | Current standard, full OHDSI tool support |
| **v5.3** | Supported | Legacy support |
| **v6.0** | Not Supported | [Not recommended by OHDSI](https://ohdsi.github.io/CommonDataModel/cdm54.html) |

## Installation

```bash
# Core PSDL
pip install pyyaml

# OMOP backend requirements
pip install sqlalchemy

# Database drivers (choose one)
pip install psycopg2        # PostgreSQL
pip install pyodbc          # SQL Server
pip install cx_Oracle       # Oracle
```

## Quick Start

```python
from runtime.python import PSDLParser, PSDLEvaluator
from runtime.python.backends import OMOPBackend, OMOPConfig

# 1. Configure connection
config = OMOPConfig(
    connection_string="postgresql://user:password@localhost:5432/synthea",
    cdm_schema="public",
    cdm_version="5.4"
)

# 2. Create backend
backend = OMOPBackend(config)

# 3. Parse scenario
parser = PSDLParser()
scenario = parser.parse_file("examples/aki_detection.yaml")

# 4. Evaluate
evaluator = PSDLEvaluator(scenario, backend)
result = evaluator.evaluate_patient(patient_id=12345)

if result.is_triggered:
    print(f"Triggered: {result.triggered_logic}")
```

## Configuration

### OMOPConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_string` | str | Required | SQLAlchemy connection string |
| `cdm_schema` | str | `"cdm"` | Schema containing CDM tables |
| `vocab_schema` | str | Same as cdm_schema | Schema for vocabulary tables |
| `cdm_version` | str | `"5.4"` | CDM version (`"5.3"` or `"5.4"`) |
| `use_datetime` | bool | `True` | Use datetime vs date fields |
| `concept_mappings` | dict | `{}` | Override concept IDs per signal |

### Connection String Examples

```python
# PostgreSQL
"postgresql://user:pass@localhost:5432/omop_db"

# SQL Server
"mssql+pyodbc://user:pass@server/database?driver=ODBC+Driver+17+for+SQL+Server"

# SQLite (for testing)
"sqlite:///path/to/omop.db"

# Oracle
"oracle+cx_oracle://user:pass@host:1521/service"
```

### Concept ID Mapping

You can override concept IDs at the config level:

```python
config = OMOPConfig(
    connection_string="postgresql://localhost/omop",
    cdm_schema="cdm",
    concept_mappings={
        "Cr": 3016723,      # Creatinine
        "Lact": 3047181,    # Lactate
        "HR": 3027018,      # Heart rate
    }
)
```

This is useful when:
- Your scenario uses generic signal names
- Different sites map to different concept IDs
- You want to test with alternative concepts

## Domain Mapping

PSDL signals map to OMOP tables based on domain:

| PSDL Domain | OMOP Table | Value Column |
|-------------|------------|--------------|
| `measurement` | `measurement` | `value_as_number` |
| `observation` | `observation` | `value_as_number` |
| `condition` | `condition_occurrence` | Presence (1.0) |
| `drug` | `drug_exposure` | Presence (1.0) |
| `procedure` | `procedure_occurrence` | Presence (1.0) |

## Research Workflows

### Finding Patients with Data

```python
# Find patients with at least 3 creatinine measurements
signal = scenario.signals["Cr"]
patients = backend.get_patient_ids_with_signal(signal, min_observations=3)
print(f"Found {len(patients)} patients with creatinine data")
```

### Historical Cohort Identification

```python
from datetime import datetime

# Evaluate at a specific historical time
reference_time = datetime(2023, 6, 15, 12, 0, 0)

results = []
for patient_id in patients:
    result = evaluator.evaluate_patient(
        patient_id=patient_id,
        reference_time=reference_time
    )
    if result.is_triggered:
        results.append({
            "patient_id": patient_id,
            "triggered": result.triggered_logic,
            "cr_value": result.trend_values.get("cr_elevated"),
        })

print(f"Found {len(results)} patients matching AKI criteria")
```

### Timeline Scanning (find all trigger points)

```python
from datetime import datetime, timedelta

def scan_patient_timeline(evaluator, patient_id, start, end, step_hours=6):
    """Scan a patient's timeline for all trigger events."""
    triggers = []
    current = start

    while current <= end:
        result = evaluator.evaluate_patient(patient_id, current)
        if result.is_triggered:
            triggers.append({
                "time": current,
                "logic": result.triggered_logic,
                "values": result.trend_values,
            })
        current += timedelta(hours=step_hours)

    return triggers

# Example: Scan 2023 for AKI episodes
triggers = scan_patient_timeline(
    evaluator,
    patient_id=12345,
    start=datetime(2023, 1, 1),
    end=datetime(2023, 12, 31),
    step_hours=12
)
```

### Exporting Results

```python
import csv

with open("aki_cohort.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["patient_id", "trigger_time", "logic", "cr_value"])
    writer.writeheader()

    for patient_id in patients:
        result = evaluator.evaluate_patient(patient_id, reference_time)
        if result.is_triggered:
            writer.writerow({
                "patient_id": patient_id,
                "trigger_time": reference_time.isoformat(),
                "logic": ",".join(result.triggered_logic),
                "cr_value": result.trend_values.get("cr_elevated"),
            })
```

## Common OMOP Concept IDs

Reference table for frequently used clinical signals:

### Laboratory Values

| Signal | Concept ID | LOINC | Unit |
|--------|------------|-------|------|
| Creatinine | 3016723 | 2160-0 | mg/dL |
| BUN | 3013682 | 3094-0 | mg/dL |
| Lactate | 3047181 | 2524-7 | mmol/L |
| Glucose | 3004501 | 2345-7 | mg/dL |
| Potassium | 3023103 | 2823-3 | mEq/L |
| Sodium | 3019550 | 2951-2 | mEq/L |
| Hemoglobin | 3000963 | 718-7 | g/dL |
| WBC | 3010813 | 6690-2 | 10^9/L |
| Platelets | 3024929 | 777-3 | 10^9/L |

### Vital Signs

| Signal | Concept ID | Unit |
|--------|------------|------|
| Heart Rate | 3027018 | beats/min |
| Systolic BP | 3004249 | mmHg |
| Diastolic BP | 3012888 | mmHg |
| MAP | 3027598 | mmHg |
| Respiratory Rate | 3024171 | breaths/min |
| SpO2 | 3016502 | % |
| Temperature | 3020891 | °C |
| GCS | 3032652 | score |

## Troubleshooting

### No Data Returned

```python
# Check if concept_id is correct
from runtime.python.parser import Signal, Domain

signal = Signal(
    name="Cr",
    source="creatinine",
    concept_id=3016723,
    domain=Domain.MEASUREMENT
)

# Verify data exists
data = backend.fetch_signal_data(
    patient_id=12345,
    signal=signal,
    window_seconds=7 * 24 * 3600,  # 7 days
    reference_time=datetime.now()
)
print(f"Found {len(data)} data points")
```

### Connection Issues

```python
# Test connection
try:
    patients = backend.get_patient_ids()
    print(f"Connected! Found {len(patients)} patients")
except Exception as e:
    print(f"Connection failed: {e}")
```

### Date vs DateTime

If your CDM only has date fields (not datetime):

```python
config = OMOPConfig(
    connection_string="...",
    cdm_schema="cdm",
    use_datetime=False  # Use date fields instead
)
```

## Performance Tips

1. **Limit patient cohort** - Don't evaluate all patients unnecessarily
2. **Use appropriate windows** - Smaller time windows = faster queries
3. **Index concept_ids** - Ensure measurement_concept_id is indexed
4. **Connection pooling** - SQLAlchemy handles this automatically

## See Also

- [OHDSI Common Data Model](https://ohdsi.github.io/CommonDataModel/)
- [OMOP Vocabulary](https://athena.ohdsi.org/)
- [PSDL Getting Started](../getting-started.md)
- [Example Scenarios](../../examples/)
