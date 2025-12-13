# Runtime Configuration Reference

> Reference samples for PSDL runtime configurations. These are **not part of the PSDL specification** - each runtime defines its own configuration format.

---

## Overview

PSDL separates concerns into three layers:

| Layer | File | Schema | Purpose |
|-------|------|--------|---------|
| **Scenario** | `*.yaml` | `spec/scenario_schema.json` | Clinical intent (WHAT to detect) |
| **Dataset Spec** | `*.yaml` | `spec/dataset_schema.json` | Data binding (WHERE to find it) |
| **Runtime Config** | `*.yaml` | None (runtime-specific) | Execution (HOW to run it) |

Runtime configurations are **intentionally not standardized** because:
- Different runtimes have fundamentally different capabilities
- Infrastructure details vary by deployment (cloud, on-prem, vendor)
- Execution parameters evolve independently from clinical logic

---

## Runtime Types

| Runtime | Use Case | Implementation |
|---------|----------|----------------|
| `single` | One patient, one time point | Python |
| `cohort` | Many patients, batch analysis | SQL |
| `streaming` | Continuous real-time | Apache Flink |

---

## Sample Configurations

### Single Patient Runtime

For testing, debugging, and single-patient evaluation.

```yaml
# runtime/single_patient.yaml
runtime: single
description: "Single patient evaluation for testing"

# Required: which scenario and data binding
scenario: scenarios/aki_detection.yaml
dataset_spec: dataset_specs/test_data.yaml

# Single runtime specific
evaluation:
  patient_id: "P12345"
  reference_time: "2025-01-15T14:30:00Z"
  # OR use "now" for current time
  # reference_time: now

# Optional: output format
output:
  format: json  # json | yaml | table
  include_trend_values: true
  include_signal_data: false
```

**CLI usage:**
```bash
psdl run --config runtime/single_patient.yaml
```

---

### Cohort Runtime (SQL)

For retrospective analysis across many patients.

```yaml
# runtime/cohort_sql.yaml
runtime: cohort
description: "Batch analysis on OMOP database"

# Required
scenario: scenarios/aki_detection.yaml
dataset_spec: dataset_specs/hospital_omop.yaml

# Database connection
connection:
  driver: postgresql  # postgresql | bigquery | snowflake
  host: localhost
  port: 5432
  database: omop_cdm
  # Credentials via environment variables (recommended)
  # username: ${OMOP_USER}
  # password: ${OMOP_PASSWORD}

# Cohort selection
cohort:
  # Time range for analysis
  start_date: "2024-01-01"
  end_date: "2024-12-31"

  # Optional: limit patients
  # patient_ids: [123, 456, 789]
  # sample_size: 1000

# Performance tuning
performance:
  batch_size: 10000
  max_concurrent_queries: 4
  timeout_seconds: 300

# Output
output:
  format: csv  # csv | parquet | json
  path: "results/aki_cohort_2024.csv"
  include_patient_ids: true
```

**CLI usage:**
```bash
psdl run --config runtime/cohort_sql.yaml

# Or with overrides
psdl run --config runtime/cohort_sql.yaml \
  --set cohort.start_date=2025-01-01 \
  --set output.path=results/aki_2025.csv
```

---

### Streaming Runtime (Flink)

For real-time continuous evaluation.

```yaml
# runtime/streaming_flink.yaml
runtime: streaming
description: "Real-time ICU monitoring with Flink"

# Required
scenario: scenarios/icu_deterioration.yaml
dataset_spec: dataset_specs/hospital_fhir.yaml

# Flink execution settings
flink:
  parallelism: 4

  # Checkpointing (fault tolerance)
  checkpointing:
    enabled: true
    interval_ms: 60000
    mode: exactly_once  # exactly_once | at_least_once
    timeout_ms: 600000
    storage: "s3://psdl-checkpoints/icu/"

  # State management
  state:
    backend: rocksdb  # rocksdb | hashmap
    ttl_hours: 48     # Expire state after patient discharge

# Event time handling
watermark:
  max_out_of_orderness_ms: 300000  # 5 minutes
  idle_timeout_ms: 30000

# Data sources
sources:
  vitals:
    type: kafka
    config:
      bootstrap_servers: "kafka-1:9092,kafka-2:9092"
      topic: "icu.vitals.fhir"
      group_id: "psdl-icu-deterioration"
      auto_offset_reset: latest

    # Signal mapping (which signals come from this source)
    signals: [heart_rate, systolic_bp, respiratory_rate, spo2]

    # Message format
    format: fhir_observation  # fhir_observation | json | avro

  labs:
    type: kafka
    config:
      bootstrap_servers: "kafka-1:9092,kafka-2:9092"
      topic: "lab.results.fhir"
      group_id: "psdl-icu-deterioration"
    signals: [creatinine, lactate]
    format: fhir_observation

# Output sinks
sinks:
  alerts:
    type: kafka
    config:
      bootstrap_servers: "kafka-1:9092,kafka-2:9092"
      topic: "psdl.alerts.icu"
    # Which logic outputs trigger this sink
    triggers: [deterioration, critical]

  audit:
    type: jdbc
    config:
      driver: postgresql
      url: "jdbc:postgresql://audit-db:5432/psdl_audit"
      table: streaming_audit_log
    # Log all evaluations (not just triggers)
    log_all: true

# Monitoring
monitoring:
  metrics:
    enabled: true
    port: 9090
    reporter: prometheus

  health_check:
    enabled: true
    path: /health
    port: 8081

# Error handling
error_handling:
  missing_signal: skip        # skip | fail | default_value
  parse_error: dead_letter    # dead_letter | skip | fail
  dead_letter_topic: "psdl.errors.icu"
```

**CLI usage:**
```bash
# Compile and deploy to Flink cluster
psdl stream --config runtime/streaming_flink.yaml

# Or step by step
psdl compile --config runtime/streaming_flink.yaml -o job.py
flink run job.py
```

---

## Environment Variables

Runtime configs support environment variable substitution:

```yaml
connection:
  host: ${DB_HOST}
  password: ${DB_PASSWORD}

sinks:
  alerts:
    config:
      bootstrap_servers: ${KAFKA_BROKERS}
```

**Best practice**: Never hardcode credentials. Use:
- Environment variables
- Secret managers (AWS Secrets Manager, HashiCorp Vault)
- Kubernetes secrets

---

## Configuration Precedence

When using CLI overrides:

1. CLI `--set` flags (highest priority)
2. Runtime config file
3. Environment variables
4. Defaults (lowest priority)

```bash
# Override specific values
psdl run --config runtime/cohort.yaml \
  --set connection.host=prod-db.example.com \
  --set performance.batch_size=50000
```

---

## Validation

Runtimes validate their own configurations at startup:

```bash
# Validate config without running
psdl validate-config --config runtime/streaming_flink.yaml

# Output:
# ✓ Runtime config valid
# ✓ Scenario exists: scenarios/icu_deterioration.yaml
# ✓ Dataset spec exists: dataset_specs/hospital_fhir.yaml
# ✓ Kafka connection: kafka-1:9092 (reachable)
# ✗ Kafka connection: kafka-2:9092 (unreachable)
# ⚠ Warning: checkpoint storage not configured for production
```

---

## Sample Directory Structure

```
project/
├── scenarios/
│   ├── aki_detection.yaml          # Clinical intent
│   └── icu_deterioration.yaml
│
├── dataset_specs/
│   ├── hospital_omop.yaml          # Data binding
│   └── hospital_fhir.yaml
│
├── runtime/
│   ├── dev/
│   │   ├── single_test.yaml        # Local testing
│   │   └── cohort_sample.yaml      # Small batch
│   │
│   ├── staging/
│   │   ├── cohort_full.yaml        # Full retrospective
│   │   └── streaming_test.yaml     # Stream with test topic
│   │
│   └── prod/
│       ├── cohort_daily.yaml       # Daily batch job
│       └── streaming_icu.yaml      # Production streaming
│
└── valuesets/
    └── creatinine_codes.vs.json
```

---

## See Also

- [RFC-0002: Streaming Execution](../rfcs/0002-streaming-execution.md)
- [RFC-0003: Architecture Refactor](../rfcs/0003-architecture-refactor.md)
- [RFC-0004: Dataset Specification](../rfcs/0004-dataset-specification.md)
