# PSDL Mapping Files

This directory contains mapping files that translate PSDL logical signal names to institution-specific terminology codes.

## How Mappings Work

PSDL separates **clinical logic** (scenarios) from **local terminology** (mappings):

```
PSDL Scenario (portable)     +     Mapping File (local)     =     Execution
─────────────────────────          ───────────────────           ──────────
signals:                           signals:
  Cr: { source: creatinine }         creatinine:                 SELECT ... WHERE
                                       source_value: "CREAT"      source_value = 'CREAT'
```

## Available Mappings

| File | Dataset | Description |
|------|---------|-------------|
| `mimic_iv.yaml` | MIMIC-IV | PhysioNet ICU data (unmapped OMOP) |
| `synthea.yaml` | Synthea | Synthetic patient data (standard OMOP) |
| `hospital_template.yaml` | Template | Starting point for your institution |

## Quick Start

### Using Pre-built Mappings

```python
from reference.python.mapping import load_mapping
from reference.python.adapters.omop import OMOPBackend, OMOPConfig

# Load MIMIC-IV mapping
mapping = load_mapping("mappings/mimic_iv.yaml")

# Configure your database
config = OMOPConfig(
    connection_string="postgresql://user:pass@localhost/mimic",
    cdm_schema="public"
)

# Create backend with mapping
backend = OMOPBackend(config, mapping=mapping)
```

### Creating Your Own Mapping

1. **Copy the template:**
   ```bash
   cp mappings/hospital_template.yaml mappings/my_hospital.yaml
   ```

2. **Find your local codes** (run in your OMOP database):
   ```sql
   SELECT DISTINCT
       measurement_concept_id,
       measurement_source_value,
       COUNT(*) as count
   FROM measurement
   GROUP BY measurement_concept_id, measurement_source_value
   ORDER BY count DESC
   LIMIT 50;
   ```

3. **Update the mapping file:**
   ```yaml
   institution: "My Hospital"
   use_source_values: true  # or false if you have concept IDs

   signals:
     creatinine:
       source_value: "CREAT_SERUM"  # Your local code
       unit: "mg/dL"
   ```

4. **Use your mapping:**
   ```python
   mapping = load_mapping("mappings/my_hospital.yaml")
   backend = OMOPBackend(config, mapping=mapping)
   ```

## Mapping File Format

```yaml
# Metadata
institution: "Hospital Name"
description: "Brief description"
data_source: "OMOP CDM 5.4"  # or "FHIR R4"

# Whether to use source_value (true) or concept_id (false)
use_source_values: false

# Signal mappings
signals:
  # For standard OMOP (mapped concepts)
  creatinine:
    concept_id: 3016723
    loinc_code: "2160-0"  # Optional, for reference
    unit: "mg/dL"
    description: "Serum creatinine"

  # For unmapped OMOP (use source values)
  potassium:
    source_value: "K+"
    loinc_code: "2823-3"
    unit: "mEq/L"
    description: "Serum potassium"
```

## Built-in Mapping Functions

For convenience, PSDL provides programmatic access to common mappings:

```python
from reference.python.mapping import get_mimic_iv_mapping, get_synthea_mapping

# Get MIMIC-IV mapping without loading a file
mapping = get_mimic_iv_mapping()

# Get Synthea mapping
mapping = get_synthea_mapping()
```

## Contributing Mappings

If you create a mapping for a public dataset, consider contributing it:

1. Create a well-documented YAML file
2. Test with real data
3. Submit a pull request

## Questions?

- See [Getting Started Guide](../docs/getting-started.md)
- Check [OMOP Adapter Documentation](../docs/adapters/omop.md)
