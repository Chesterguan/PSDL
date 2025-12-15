# RFC-0004: Dataset Specification

| Field | Value |
|-------|-------|
| RFC | 0004 |
| Title | Dataset Specification - Portable Data Binding Layer |
| Author | PSDL Team |
| Status | Implemented |
| Created | 2025-12-12 |
| Updated | 2025-12-14 |

## Summary

Dataset Specification (Dataset Spec) is a declarative binding layer that maps PSDL semantic references to concrete data source locations. It enables the same PSDL scenario to run across different datasets (OMOP, FHIR, MIMIC, custom) without modification.

**Core Principle:**
```
PSDL Scenario  = intent    (WHAT to detect)
Dataset Spec   = binding   (WHERE to find it)
Adapter        = execution (HOW to run it)
```

### Key Design Decisions (v2)

| # | Decision | Rule |
|---|----------|------|
| 1 | **Adapter loading** | Adapter is "fed" Dataset Spec explicitly (no auto-discovery) |
| 2 | **Signal references** | `signal.ref` is always semantic name; physical bindings forbidden in scenario |
| 3 | **Unit strategy** | Strict mode by default: units must match exactly, no auto-conversion |
| 4 | **Valueset strategy** | Local static files ONLY; no online queries; versioned + SHA-256 hashed |
| 5 | **Audit-first** | All artifacts (scenario, dataset spec, valuesets) have version + hash in manifest |

## Motivation

### Current Problems

1. **Mixed concerns in adapters**: Current adapters (OMOP, FHIR) contain both execution logic AND mapping logic, making them hard to audit and extend.

2. **Non-portable scenarios**: Scenarios often include data-source-specific details (concept_ids, table names), preventing reuse across institutions.

3. **Implicit mappings**: How signals map to data fields is buried in adapter code, not explicitly declared or version-controlled.

4. **Audit gap**: Regulators cannot easily verify "where did this data come from?" without reading adapter source code.

### Goals

1. **Explicit binding contract**: All data mappings declared in a single, auditable file
2. **Scenario portability**: Same scenario runs on MIMIC, institutional OMOP, or FHIR server
3. **Separation of concerns**: Scenarios define intent, Dataset Specs define location, Adapters execute
4. **Version control**: Dataset Specs can be diffed, reviewed, and versioned independently

## Design

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: PSDL Scenario (Intent)                                 │
│                                                                 │
│   signals:                                                      │
│     Cr:                                                         │
│       ref: creatinine          # Semantic reference             │
│       expected_unit: mg/dL     # Constraint (optional)          │
│                                                                 │
│   trends:                                                       │
│     cr_delta_48h:                                               │
│       expr: delta(Cr, 48h)             # Numeric only (v0.3)    │
│                                                                 │
│   logic:                                                        │
│     cr_rising:                                                  │
│       when: cr_delta_48h >= 0.3        # Comparison in logic    │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 2: Dataset Spec (Binding)                                 │
│                                                                 │
│   elements:                                                     │
│     creatinine:                                                 │
│       table: measurement                                        │
│       value_field: value_as_number                             │
│       time_field: measurement_datetime                         │
│       concept_id: [3016723]                                    │
│       unit: mg/dL                                              │
├─────────────────────────────────────────────────────────────────┤
│ LAYER 3: Adapter (Execution)                                    │
│                                                                 │
│   - Loads Dataset Spec                                          │
│   - Resolves signal bindings                                    │
│   - Executes queries / API calls                                │
│   - Returns canonical event stream                              │
└─────────────────────────────────────────────────────────────────┘
```

### Dataset Spec Structure

```yaml
# dataset_specs/mimic_iv_omop.yaml
dataset: mimic_iv_omop
version: "1.0.0"
description: "MIMIC-IV mapped to OMOP CDM v5.4"
data_model: omop  # omop | fhir | custom

# Global conventions
conventions:
  patient_id_field: person_id
  default_time_field: measurement_datetime
  timezone: UTC

# Element bindings (semantic name → physical location)
elements:
  # Lab values
  creatinine:
    kind: lab
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3016723]
    unit: mg/dL
    value_type: numeric

  lactate:
    kind: lab
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3047181]
    unit: mmol/L
    value_type: numeric

  # Vital signs
  heart_rate:
    kind: vital
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3027018]
    unit: bpm
    value_type: numeric

  systolic_bp:
    kind: vital
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    patient_field: person_id
    filter:
      concept_id: [3004249]
    unit: mmHg
    value_type: numeric

  # Demographics (optional)
  age:
    kind: demographic
    table: person
    value_field: year_of_birth
    patient_field: person_id
    value_type: integer
    transform: current_year_minus_value  # Declarative only

# Metadata
metadata:
  source: "PhysioNet MIMIC-IV v2.2"
  omop_version: "5.4"
  created: "2025-12-12"
  maintainer: "PSDL Team"
```

### Scenario Signal References

Scenarios reference elements by semantic name only:

```yaml
# scenarios/aki_detection.yaml
psdl_version: "0.3"

scenario:
  name: aki_detection
  version: "1.0.0"

audit:
  intent: "Detect AKI using KDIGO criteria"
  rationale: "Early detection enables intervention"
  provenance: "KDIGO 2012 Guidelines"

signals:
  Cr:
    ref: creatinine           # ← Semantic reference (resolved by Dataset Spec)
    expected_unit: mg/dL      # ← Optional constraint
    description: "Serum creatinine"

  Lactate:
    ref: lactate
    expected_unit: mmol/L

trends:
  cr_delta_48h:
    type: float
    expr: delta(Cr, 48h)      # ← Numeric only (v0.3)
    description: "Creatinine change over 48h"

logic:
  cr_rising:
    when: cr_delta_48h >= 0.3  # ← Comparison in logic layer (v0.3)
    description: "Creatinine rise >= 0.3 mg/dL in 48h"

  aki_stage1:
    when: cr_rising
    severity: medium
```

**Key Rule**: `signal.ref` is ALWAYS a semantic name. Physical bindings (table/field/concept_id) are FORBIDDEN in scenarios.

### What Dataset Spec Defines (In-Scope)

| Category | Examples | Purpose |
|----------|----------|---------|
| **Location binding** | table, field, path | Where to find the data |
| **Encoding binding** | concept_id, LOINC code, valueset | How to filter/identify |
| **Type declaration** | value_type, unit | What format to expect |
| **Time axis** | time_field, timezone | Temporal semantics |
| **Patient axis** | patient_field, visit_field | Identity semantics |

### What Dataset Spec Does NOT Define (Out-of-Scope)

| Category | Belongs To | Reason |
|----------|------------|--------|
| Thresholds (> 1.5) | Scenario | Clinical logic |
| Window functions (delta, slope) | Scenario | Temporal logic |
| State machines | Scenario | Clinical progression |
| Triggers/actions | Scenario | Response logic |
| JOIN strategies | Adapter | Execution optimization |
| Caching, batching | Adapter | Runtime performance |
| Connection pooling | Adapter | Infrastructure |

### Unit Handling Strategy

**v2 Default: Strict Mode**

| Strategy | Behavior | When to Use |
|----------|----------|-------------|
| **Strict** (default) | Units must match exactly, else error | Production, audit-critical |
| Allow-declare | Dataset Spec may declare static conversion table | Cross-institution portability |
| Backend-specific | Adapter handles conversion | Legacy systems |

**Strict Mode Example:**
```yaml
# Scenario declares expectation
signals:
  Cr:
    ref: creatinine
    expected_unit: mg/dL

# Dataset Spec declares actual unit
elements:
  creatinine:
    unit: mg/dL  # ✅ Matches - OK

# OR
elements:
  creatinine:
    unit: μmol/L  # ❌ Mismatch - ERROR at validation time
```

**Allow-declare Mode (Optional):**
```yaml
# Dataset Spec with conversion
elements:
  creatinine:
    unit: μmol/L
    unit_conversions:
      - to: mg/dL
        factor: 0.0113  # μmol/L × 0.0113 = mg/dL
```

### Valueset Strategy

**v2 Default: Local Static Files Only**

v2 uses the most conservative, auditable approach. No runtime terminology service queries.

| Rule | Description |
|------|-------------|
| **Static set** | Valueset is a static set of codes/concepts, no runtime expansion |
| **Local files only** | All valuesets must be local files (no online queries) |
| **Scenario isolation** | Scenarios do NOT reference codes directly; Dataset Spec references valuesets |
| **No hierarchy expansion** | No logical expressions or parent/child expansion in v2 |
| **Versioned + hashed** | Every valueset file has version and SHA-256 in audit manifest |

**v2 Allowed Valueset Sources (Only 2):**

| Source | Description | Audit |
|--------|-------------|-------|
| **Local static file** | JSON/CSV/YAML created by team | version + SHA-256 |
| **External snapshot** | Athena/institutional terminology export, saved locally | source_uri + export_date + SHA-256 |

**v3 Future (NOT v2):**
- Online terminology service queries (FHIR $expand, Athena API)
- Hierarchy expansion (get all children of concept X)
- These break determinism and introduce environment dependencies

**Valueset File Format:**
```json
{
  "name": "creatinine_codes",
  "version": "1.0.0",
  "description": "All creatinine measurement concepts",
  "source": {
    "type": "athena_export",
    "export_date": "2025-12-01",
    "vocabulary_version": "v5.0 20231001"
  },
  "code_system": "OMOP",
  "codes": [
    { "code": "3016723", "display": "Creatinine serum/plasma" },
    { "code": "3020564", "display": "Creatinine urine" },
    { "code": "3022243", "display": "Creatinine 24h urine" }
  ]
}
```

**Dataset Spec Reference:**
```yaml
elements:
  creatinine:
    table: measurement
    filter:
      valueset: "valuesets/creatinine_codes.vs.json"
    unit: mg/dL
```

**Audit Manifest Entry:**
```json
{
  "valuesets": [
    {
      "uri": "valuesets/creatinine_codes.vs.json",
      "sha256": "a1b2c3d4...",
      "version": "1.0.0"
    }
  ]
}
```

### Adapter Interface Contract

Adapters MUST implement:

```python
from typing import Protocol, Iterator
from dataclasses import dataclass

@dataclass
class Binding:
    """Resolved binding from Dataset Spec"""
    table: str
    value_field: str
    time_field: str
    patient_field: str
    filter_expr: str  # e.g., "concept_id IN (3016723)"
    unit: str

@dataclass
class Event:
    """Canonical event format"""
    patient_id: str
    timestamp: datetime
    signal_ref: str
    value: float | str | bool | None
    unit: str

class DatasetAdapter(Protocol):
    """Interface that all adapters must implement"""

    def load_dataset_spec(self, uri_or_path: str) -> DatasetSpec:
        """Load and validate a Dataset Spec file"""
        ...

    def resolve_binding(self, signal_ref: str, spec: DatasetSpec) -> Binding:
        """Resolve a semantic reference to a physical binding"""
        ...

    def fetch_events(
        self,
        binding: Binding,
        patient_ids: list[str] | None,
        time_range: tuple[datetime, datetime] | None
    ) -> Iterator[Event]:
        """Fetch events from data source, return canonical stream"""
        ...
```

### Runtime Invocation

**Option A (Recommended): CLI Parameter**
```bash
psdl run \
  --scenario scenarios/aki_detection.yaml \
  --dataset dataset_specs/mimic_iv_omop.yaml \
  --adapter omop_sql \
  --connection "postgresql://..."
```

**Option B (Optional): Scenario Reference**
```yaml
# In scenario (not recommended as default)
scenario: aki_detection
dataset: "dataset://mimic_iv_omop@v1"  # Optional explicit binding
```

**Key Design Decision**: Adapter does NOT "discover" Dataset Spec. Adapter is "fed" Dataset Spec explicitly. This ensures:
- Full auditability (you know exactly which mapping was used)
- No environment coupling (no magic config files)
- Reproducibility (same inputs → same behavior)

## Files Required for Deployment

When deploying PSDL at a new institution or data source, users need to create/provide these files:

```
project/
├── scenarios/
│   └── aki_detection.yaml          # [1] Scenario (usually unchanged)
│
├── dataset_specs/
│   └── <site>.<backend>.yaml       # [2] Dataset Spec (MUST write)
│
├── runtime/
│   └── <backend>.yaml              # [3] Runtime Config (MUST write)
│
└── valuesets/
    └── *.vs.json                   # [4] Valuesets (write if needed)
```

| File | Required | When to Create |
|------|----------|----------------|
| **[1] Scenario** | Provided | Usually reuse existing scenarios; only customize if clinical logic differs |
| **[2] Dataset Spec** | MUST write | Always required for new data source; maps semantic refs to physical locations |
| **[3] Runtime Config** | MUST write | Connection strings, credentials, performance tuning |
| **[4] Valuesets** | As needed | Only when elements need code/concept sets (e.g., multiple LOINC codes for same lab) |

**Example Runtime Config:**
```yaml
# runtime/omop_sql.yaml
adapter: omop_sql
connection:
  driver: postgresql
  host: localhost
  port: 5432
  database: omop_cdm
  # credentials via environment variables
performance:
  batch_size: 10000
  max_concurrent: 4
```

**Minimal Deployment (Single Lab):**
```bash
# If your site only has creatinine with ONE concept_id, no valueset needed
psdl run \
  --scenario scenarios/aki.yaml \
  --dataset dataset_specs/mysite_omop.yaml \
  --runtime runtime/omop_sql.yaml
```

## Migration Plan

### Phase 1: Define Spec Format (Week 1)
1. Add `spec/dataset_schema.json` - JSON Schema for Dataset Spec
2. Create example Dataset Specs for existing adapters (OMOP, FHIR, PhysioNet)

### Phase 2: Update IR (Week 2)
1. Add `DatasetSpec` dataclass to `src/psdl/core/ir.py`
2. Add `signal.ref` field (semantic reference)
3. Add validation: scenario cannot contain physical bindings

### Phase 3: Refactor Adapters (Week 3-4)
1. Extract mapping logic from adapters into Dataset Spec files
2. Update adapter interface to accept Dataset Spec
3. Implement `resolve_binding()` and `fetch_events()`

### Phase 4: Update CLI (Week 5)
1. Add `--dataset` parameter to CLI
2. Update existing notebooks and examples
3. Documentation

## Examples

### Example 1: Same Scenario, Different Datasets

**Scenario (unchanged):**
```yaml
scenario: sepsis_screening
signals:
  HR:
    ref: heart_rate
  Temp:
    ref: temperature
  WBC:
    ref: white_blood_cell_count
```

**Dataset Spec A (MIMIC-IV OMOP):**
```yaml
dataset: mimic_iv_omop
elements:
  heart_rate:
    table: measurement
    concept_id: [3027018]
  temperature:
    table: measurement
    concept_id: [3020891]
  white_blood_cell_count:
    table: measurement
    concept_id: [3010813]
```

**Dataset Spec B (FHIR Server):**
```yaml
dataset: hospital_fhir
data_model: fhir
elements:
  heart_rate:
    resource: Observation
    code_system: http://loinc.org
    code: 8867-4
  temperature:
    resource: Observation
    code_system: http://loinc.org
    code: 8310-5
  white_blood_cell_count:
    resource: Observation
    code_system: http://loinc.org
    code: 6690-2
```

**Run with different datasets:**
```bash
# Same scenario, MIMIC data
psdl run --scenario sepsis.yaml --dataset mimic_iv_omop.yaml

# Same scenario, hospital FHIR server
psdl run --scenario sepsis.yaml --dataset hospital_fhir.yaml
```

### Example 2: Valueset Reference

```yaml
# dataset_specs/uf_health_omop.yaml
dataset: uf_health_omop
version: "1.0.0"

valuesets:
  creatinine_codes:
    description: "All creatinine measurement concepts"
    concepts:
      - 3016723  # Creatinine serum/plasma
      - 3020564  # Creatinine urine
      - 3022243  # Creatinine 24h urine

elements:
  creatinine:
    table: measurement
    filter:
      concept_id: { valueset: creatinine_codes }
    unit: mg/dL
```

## Alternatives Considered

### 1. Embed Mappings in Scenario

**Approach:** Keep concept_id, table names in scenario files.

**Rejected because:**
- Scenarios become non-portable
- Mixing intent with implementation
- Hard to audit "where did data come from?"

### 2. Implicit Adapter Discovery

**Approach:** Adapter auto-discovers Dataset Spec from environment/config.

**Rejected because:**
- "Magic" behavior reduces auditability
- Different environments may have different defaults
- Harder to reproduce exact execution

### 3. Full Query DSL in Dataset Spec

**Approach:** Allow SQL/JOINs/complex logic in Dataset Spec.

**Rejected because:**
- Dataset Spec becomes a second query language
- Violates separation of concerns
- Execution optimization belongs in Adapter

## Open Questions

1. **Inheritance**: Can one Dataset Spec extend another (e.g., `extends: base_omop.yaml`)?
2. **Validation strictness**: Should missing elements error or warn?
3. **Cross-dataset valuesets**: Can multiple Dataset Specs share a common valueset library?

## References

- [RFC-0003: Architecture Refactor](0003-architecture-refactor.md)
- [OMOP CDM Specification](https://ohdsi.github.io/CommonDataModel/)
- [FHIR R4 Observation](https://hl7.org/fhir/observation.html)
- [LOINC](https://loinc.org/)
