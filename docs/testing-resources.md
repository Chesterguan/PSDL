# Public Testing Resources

This document lists public OMOP CDM databases and FHIR servers available for testing PSDL scenarios.

## OMOP CDM Test Databases

### 1. Eunomia (OHDSI Recommended)

The official OHDSI synthetic data project for testing and development.

**Features:**
- Multiple dataset sizes available
- CDM v5.3 and v5.4 support
- Synthea-generated synthetic patients
- CMS SynPUF data available

**Installation (Python):**
```bash
pip install eunomia
```

**Usage:**
```python
# Eunomia provides R packages primarily, but data can be exported
# See: https://ohdsi.github.io/Eunomia/
```

**Resources:**
- [Eunomia GitHub](https://github.com/OHDSI/Eunomia)
- [Eunomia Documentation](https://ohdsi.github.io/Eunomia/)

### 2. OMOP-Lite

A containerized OMOP CDM with synthetic data, easy to deploy.

**Features:**
- PostgreSQL and SQL Server support
- 100 or 1000 synthetic patients
- Docker-based deployment

**Quick Start:**
```bash
# Clone the repo
git clone https://github.com/Health-Informatics-UoN/omop-lite

# Run with synthetic data
docker-compose up -d
```

**Connection:**
```python
from runtime.python.backends import OMOPBackend, OMOPConfig

config = OMOPConfig(
    connection_string="postgresql://postgres:password@localhost:5432/omop",
    cdm_schema="cdm"
)
backend = OMOPBackend(config)
```

**Resources:**
- [OMOP-Lite GitHub](https://github.com/Health-Informatics-UoN/omop-lite)

### 3. CMS SynPUF (2.33M Patients)

Large-scale synthetic Medicare claims data mapped to OMOP CDM.

**Features:**
- 2.33 million synthetic patients
- Based on real Medicare claims patterns
- Available on Redivis

**Resources:**
- [CMS SynPUF on Redivis](https://redivis.com/Demo/datasets/1709)
- [ETL-CMS GitHub](https://github.com/OHDSI/ETL-CMS)

### 4. Synthea + ETL-Synthea

Generate your own synthetic OMOP data.

**Features:**
- Customizable patient populations
- Realistic disease progressions
- Geographic and demographic control

**Quick Start:**
```bash
# Generate synthetic patients
java -jar synthea-with-dependencies.jar -p 1000 --exporter.fhir.export=false

# Convert to OMOP using ETL-Synthea
# See: https://github.com/OHDSI/ETL-Synthea
```

**Resources:**
- [Synthea](https://synthetichealth.github.io/synthea/)
- [ETL-Synthea](https://github.com/OHDSI/ETL-Synthea)

---

## FHIR R4 Test Servers

### 1. HAPI FHIR Public Server (Recommended for Testing)

The most widely used public FHIR test server.

**Server URL:** `https://hapi.fhir.org/baseR4`

**Features:**
- Full FHIR R4 support
- Pre-populated with test data
- No authentication required
- Regularly reset with fresh data

**Usage:**
```python
from runtime.python.backends import FHIRBackend, FHIRConfig

config = FHIRConfig(
    base_url="https://hapi.fhir.org/baseR4"
)
backend = FHIRBackend(config)

# Get patient IDs
patients = backend.get_patient_ids()
print(f"Found {len(patients)} patients")

# Fetch patient data
patient = backend.get_patient(patients[0])
```

**Resources:**
- [HAPI FHIR](https://hapi.fhir.org/)

### 2. HL7 Public Test Servers

Multiple servers maintained by the FHIR community.

| Server | URL | Notes |
|--------|-----|-------|
| Grahame's Test Server | http://test.fhir.org/r4 | All resources, full operations |
| AEGIS WildFHIR | https://wildfhir.wildfhir.org/r4 | R4 v4.0.1, all operations |

**Resources:**
- [HL7 Public Test Servers](https://confluence.hl7.org/spaces/FHIR/pages/35718859/Public+Test+Servers)

### 3. Logica Health Sandbox

SMART on FHIR enabled sandbox for app development.

**Features:**
- SMART on FHIR authentication
- Pre-installed apps
- Patient context launch

**Resources:**
- [Logica Sandbox](https://sandbox.logicahealth.org/)

### 4. Epic Sandbox

For testing Epic-specific integrations.

**Features:**
- Simulates Epic EHR environment
- SMART on FHIR support
- Requires developer registration

**Resources:**
- [Epic on FHIR](https://open.epic.com/)

### 5. Crucible Testing Tools

FHIR conformance testing and synthetic data generation.

**Features:**
- Conformance testing
- Patient record scoring
- Synthetic data generation

**Resources:**
- [Crucible](https://projectcrucible.org/)

---

## Testing with PSDL

### Quick Test: HAPI FHIR

```python
from runtime.python import PSDLParser, PSDLEvaluator
from runtime.python.backends import FHIRBackend, FHIRConfig
from datetime import datetime

# Connect to public HAPI server
config = FHIRConfig(base_url="https://hapi.fhir.org/baseR4")
backend = FHIRBackend(config)

# Parse a scenario
scenario = PSDLParser().parse_file("examples/aki_detection.yaml")
evaluator = PSDLEvaluator(scenario, backend)

# Find patients with creatinine data
patients = backend.search_patients_with_observation(
    loinc_code="2160-0",  # Creatinine
    min_count=2
)

print(f"Found {len(patients)} patients with creatinine data")

# Evaluate each patient
for patient_id in patients[:5]:  # First 5
    result = evaluator.evaluate_patient(
        patient_id=patient_id,
        reference_time=datetime.now()
    )
    if result.is_triggered:
        print(f"Patient {patient_id}: ALERT - {result.triggered_logic}")
```

### Docker-Based OMOP Testing

```yaml
# docker-compose.yml for local OMOP testing
version: '3'
services:
  omop-db:
    image: ghcr.io/health-informatics-uon/omop-lite:latest
    environment:
      - SYNTHETIC=true
      - SYNTHETIC_NUMBER=1000
    ports:
      - "5432:5432"
```

```python
from runtime.python.backends import OMOPBackend, OMOPConfig

config = OMOPConfig(
    connection_string="postgresql://postgres:postgres@localhost:5432/omop",
    cdm_schema="cdm"
)
backend = OMOPBackend(config)

# Get available patients
patients = backend.get_patient_ids()
print(f"Found {len(patients)} synthetic patients")
```

---

## Important Notes

1. **Public servers may be slow** - They handle many requests from developers worldwide
2. **Data is not persistent** - Public servers are regularly purged
3. **No PHI** - Never upload real patient data to public servers
4. **Rate limits** - Some servers have rate limits; implement retry logic
5. **Testing only** - These resources are for development and testing, not production

## Recommended Testing Strategy

1. **Unit Tests**: Use `InMemoryBackend` with controlled test data
2. **Integration Tests**: Use local Docker-based OMOP/FHIR
3. **Smoke Tests**: Validate against public servers
4. **Performance Tests**: Use Synthea to generate large datasets locally
