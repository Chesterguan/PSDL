# FHIR R4 Data Adapter

The FHIR R4 adapter enables PSDL to connect to FHIR-compliant Electronic Health Record (EHR) systems for real-time clinical data access.

## Overview

FHIR (Fast Healthcare Interoperability Resources) is the modern standard for healthcare data exchange. The PSDL FHIR adapter:

- Connects to FHIR R4 compliant servers
- Maps PSDL signals to FHIR resources via LOINC codes
- Supports Bearer token and Basic authentication
- Handles Observation, Condition, MedicationAdministration, and Procedure resources

## Installation

The FHIR adapter requires the `requests` library:

```bash
pip install requests
```

## Quick Start

```python
from psdl import PSDLParser, PSDLEvaluator
from psdl.adapters import FHIRBackend, FHIRConfig

# Configure FHIR connection
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token="your-bearer-token"
)

# Create backend and evaluator
backend = FHIRBackend(config)
scenario = PSDLParser().parse_file("my_scenario.yaml")
evaluator = PSDLEvaluator(scenario, backend)

# Evaluate a patient
result = evaluator.evaluate_patient(patient_id="patient-uuid-123")

if result.is_triggered:
    print(f"Alert triggered: {result.triggered_logic}")
```

## Configuration

### FHIRConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | str | required | FHIR server base URL (e.g., `https://fhir.hospital.org/r4`) |
| `auth_token` | str | None | Authentication token |
| `auth_type` | str | "bearer" | Authentication type: "bearer", "basic", or "none" |
| `timeout` | int | 30 | Request timeout in seconds |
| `verify_ssl` | bool | True | Verify SSL certificates |
| `headers` | dict | {} | Additional HTTP headers |
| `loinc_mappings` | dict | {} | Custom signal-to-LOINC mappings |

### Authentication Examples

**Bearer Token (OAuth2, SMART on FHIR):**
```python
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1...",
    auth_type="bearer"
)
```

**Basic Authentication:**
```python
import base64

credentials = base64.b64encode(b"username:password").decode()
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token=credentials,
    auth_type="basic"
)
```

**API Key (via headers):**
```python
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    headers={"X-API-Key": "your-api-key"}
)
```

## Signal Mapping

PSDL signals are mapped to FHIR resources based on their domain:

| PSDL Domain | FHIR Resource |
|-------------|---------------|
| measurement | Observation |
| observation | Observation |
| condition | Condition |
| drug | MedicationAdministration |
| procedure | Procedure |

### LOINC Code Mapping

The backend uses LOINC codes to query for specific clinical measurements. Common mappings are built-in:

| Signal Source | LOINC Code | Description |
|---------------|------------|-------------|
| creatinine | 2160-0 | Serum creatinine |
| lactate | 2524-7 | Blood lactate |
| glucose | 2345-7 | Blood glucose |
| heart_rate | 8867-4 | Heart rate |
| respiratory_rate | 9279-1 | Respiratory rate |
| oxygen_saturation | 2708-6 | SpO2 |
| systolic_blood_pressure | 8480-6 | Systolic BP |
| diastolic_blood_pressure | 8462-4 | Diastolic BP |
| body_temperature | 8310-5 | Body temperature |
| hemoglobin | 718-7 | Hemoglobin |
| potassium | 2823-3 | Serum potassium |
| sodium | 2951-2 | Serum sodium |
| bun | 3094-0 | Blood urea nitrogen |
| wbc | 6690-2 | White blood cell count |
| platelets | 777-3 | Platelet count |
| gcs | 9269-2 | Glasgow Coma Scale |

### Custom LOINC Mappings

For signals not in the built-in list, provide custom mappings:

```python
config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token="your-token",
    loinc_mappings={
        "procalcitonin": "75241-0",
        "bnp": "42637-9",
        "troponin_i": "10839-9"
    }
)
```

### Direct LOINC Code Reference

You can also use LOINC codes directly as the signal source:

```yaml
signals:
  Procalcitonin:
    source: "75241-0"  # LOINC code format
    unit: ng/mL
```

## Usage Examples

### Real-Time ICU Monitoring

```python
from psdl import PSDLParser, PSDLEvaluator
from psdl.adapters import FHIRBackend, FHIRConfig
from datetime import datetime

# FHIR connection
config = FHIRConfig(
    base_url="https://fhir.icu.hospital.org/r4",
    auth_token="smart-on-fhir-token",
    timeout=10  # Faster timeout for real-time
)
backend = FHIRBackend(config)

# Load scenario
scenario = PSDLParser().parse_file("icu_deterioration.yaml")
evaluator = PSDLEvaluator(scenario, backend)

# Monitor specific patient
patient_id = "550e8400-e29b-41d4-a716-446655440000"
result = evaluator.evaluate_patient(
    patient_id=patient_id,
    reference_time=datetime.now()
)

if result.is_triggered:
    for rule_name in result.triggered_logic:
        severity = scenario.logic[rule_name].severity
        print(f"[{severity.upper()}] {rule_name}: {result.trend_values}")
```

### Batch Processing Multiple Patients

```python
# Get all ICU patients
patient_ids = backend.get_patient_ids()

# Or find patients with specific observations
patients_with_creatinine = backend.search_patients_with_observation(
    loinc_code="2160-0",  # Creatinine
    min_count=2
)

# Evaluate each patient
results = []
for patient_id in patients_with_creatinine:
    result = evaluator.evaluate_patient(patient_id=patient_id)
    if result.is_triggered:
        results.append({
            "patient_id": patient_id,
            "triggered": result.triggered_logic,
            "values": result.trend_values
        })

print(f"Found {len(results)} patients with alerts")
```

### SMART on FHIR Integration

```python
# After SMART on FHIR OAuth flow
access_token = oauth_response["access_token"]
patient_id = oauth_response["patient"]  # Patient in context

config = FHIRConfig(
    base_url="https://fhir.hospital.org/r4",
    auth_token=access_token,
    auth_type="bearer"
)

backend = FHIRBackend(config)
evaluator = PSDLEvaluator(scenario, backend)

# Evaluate the patient in context
result = evaluator.evaluate_patient(patient_id=patient_id)
```

## Scenario Example

```yaml
scenario: Sepsis_Early_Warning
version: "0.1.0"
description: "Early sepsis detection using qSOFA criteria"

signals:
  RR:
    source: respiratory_rate
    unit: breaths/min

  SBP:
    source: systolic_blood_pressure
    unit: mmHg

  GCS:
    source: gcs
    unit: points

  Lactate:
    source: lactate
    unit: mmol/L

trends:
  tachypnea:
    expr: last(RR) >= 22
    description: "Respiratory rate >= 22"

  hypotension:
    expr: last(SBP) <= 100
    description: "Systolic BP <= 100 mmHg"

  altered_mental:
    expr: last(GCS) < 15
    description: "GCS < 15"

  lactate_elevated:
    expr: last(Lactate) > 2.0
    description: "Lactate > 2.0 mmol/L"

logic:
  qsofa_positive:
    expr: (tachypnea AND hypotension) OR (tachypnea AND altered_mental) OR (hypotension AND altered_mental)
    severity: high
    description: "qSOFA >= 2 - sepsis screening positive"

  sepsis_likely:
    expr: qsofa_positive AND lactate_elevated
    severity: critical
    description: "qSOFA positive with elevated lactate"
```

## Error Handling

The backend handles errors gracefully:

```python
# Connection errors return empty data
result = evaluator.evaluate_patient(patient_id="nonexistent")
# result.trend_values will be empty, no exception raised

# Check for data availability
for signal_name in scenario.signals:
    data = backend.fetch_signal_data(
        patient_id=patient_id,
        signal=scenario.signals[signal_name],
        window_seconds=86400,
        reference_time=datetime.now()
    )
    if not data:
        print(f"Warning: No data for {signal_name}")
```

## Supported FHIR Servers

The backend has been tested with:

| Server | Notes |
|--------|-------|
| HAPI FHIR | Reference implementation |
| Microsoft Azure FHIR | Cloud-hosted |
| Google Cloud Healthcare API | Cloud-hosted |
| Epic FHIR | Requires SMART on FHIR |
| Cerner FHIR | Requires SMART on FHIR |
| SMART Health IT Sandbox | Testing only |

## Troubleshooting

### Common Issues

**401 Unauthorized:**
- Check that your token is valid and not expired
- Verify auth_type matches your authentication method
- For SMART on FHIR, ensure proper scopes

**Empty Results:**
- Verify the patient ID format matches your server (UUID vs numeric)
- Check that LOINC codes are correct for your data
- Ensure the time window is appropriate for your data frequency

**Timeout Errors:**
- Increase timeout in config for slow servers
- Consider narrower time windows
- Check network connectivity

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Requests library will log HTTP details
```

## Performance Considerations

For high-volume processing:

1. **Reuse Backend Instances**: Create one backend and reuse it
2. **Appropriate Time Windows**: Narrower windows = faster queries
3. **Batch Patient Lists**: Fetch patient lists once, then iterate
4. **Connection Pooling**: The requests Session handles this automatically

```python
# Good: Reuse backend
backend = FHIRBackend(config)
for patient_id in patient_ids:
    result = evaluator.evaluate_patient(patient_id)

# Bad: Create new backend each time
for patient_id in patient_ids:
    backend = FHIRBackend(config)  # Slow!
    result = evaluator.evaluate_patient(patient_id)
```

## API Reference

### FHIRBackend Methods

| Method | Description |
|--------|-------------|
| `fetch_signal_data(patient_id, signal, window_seconds, reference_time)` | Fetch time-series data for a signal |
| `get_patient_ids(population_include, population_exclude)` | Get list of patient IDs |
| `get_patient(patient_id)` | Get patient resource |
| `search_patients_with_observation(loinc_code, min_count)` | Find patients with specific observations |
| `close()` | Close HTTP session |

### Convenience Functions

```python
from reference.python.adapters import create_fhir_backend

# Quick setup
backend = create_fhir_backend(
    base_url="https://fhir.hospital.org/r4",
    auth_token="your-token"
)
```

## Related Documentation

- [FHIR R4 Specification](https://hl7.org/fhir/R4/)
- [SMART on FHIR](https://docs.smarthealthit.org/)
- [LOINC Database](https://loinc.org/)
- [OMOP Adapter](./omop.md) - For research databases
- [Getting Started](../getting-started.md) - PSDL basics
