# PSDL Glossary

> Terminology and definitions for the Patient Scenario Definition Language

---

## Core Concepts

### PSDL
**Patient Scenario Definition Language**

A declarative, vendor-neutral language for expressing clinical scenarios. PSDL defines WHAT to detect, not HOW to compute it.

*Analogy: What SQL is for data queries, PSDL is for clinical logic.*

---

### Scenario

A complete PSDL definition that describes a clinical situation to detect. Contains signals, trends, logic, **audit block (required)**, and optionally population filters and state machine.

**Examples:** `AKI_Detection`, `Sepsis_Screening`, `ICU_Deterioration`

**File format:** YAML or JSON

**Required sections:** `scenario`, `version`, `audit`, `signals`, `logic`

---

### Audit Block (First-Citizen)

**Required** metadata that makes every scenario traceable and accountable. This is PSDL's first-citizen feature.

| Field | Purpose | Example |
|-------|---------|---------|
| `intent` | WHAT is being detected | "Detect early acute kidney injury" |
| `rationale` | WHY it matters clinically | "Early detection enables intervention" |
| `provenance` | WHAT evidence supports it | "KDIGO Guidelines 2012" |

```yaml
audit:
  intent: "Detect early AKI using KDIGO criteria"
  rationale: "Early detection enables timely intervention"
  provenance: "KDIGO Clinical Practice Guideline for AKI (2012)"
```

**This is not optional.** Every PSDL scenario must include an audit block.

---

### Clinical Accountability

PSDL's **first-citizen principle**. Every clinical decision must be traceable: WHO wrote it, WHY it matters, and WHAT evidence supports it.

Clinical accountability is what makes PSDL regulatory-ready (FDA, EU MDR).

---

### State Machine

Optional component for tracking clinical state progression over time. Unlike signals/trends/logic (which are stateless point-in-time evaluations), state machines maintain history.

**Components:**
- `initial`: Starting state
- `states`: List of possible states
- `transitions`: Rules for moving between states (from, to, when)

```yaml
state:
  initial: normal
  states: [normal, elevated, critical]
  transitions:
    - from: normal
      to: elevated
      when: aki_stage1
```

---

### Signal

A binding from a logical name to a clinical data source. Signals represent time-series clinical data like labs, vitals, or observations.

**Examples:** `Cr` (creatinine), `HR` (heart rate), `MAP` (mean arterial pressure)

**Properties:** `source`, `concept_id`, `unit`, `domain`

---

### Trend

A temporal computation over a signal that produces a boolean result. Trends apply operators to signals and compare against thresholds.

**Example:** `delta(Cr, 48h) > 0.3` (creatinine rise in 48 hours)

**Components:** operator, signal, window, comparator, threshold

---

### Logic

Boolean expressions that combine trends into clinical states. Uses AND, OR, NOT operators.

**Example:** `aki_stage1 AND NOT recovering`

**Properties:** `expr`, `severity`, `description`

---

### Population

Criteria defining which patients a scenario applies to. Contains include and exclude filters.

**Example:** `include: [age >= 18, unit == 'ICU']`, `exclude: [comfort_care_only]`

---

### Operator

A function that computes a value from time-series signal data. Operators are the computational primitives of PSDL.

| Type | Operators |
|------|-----------|
| **Windowed** | `delta`, `slope`, `sma`, `ema`, `min`, `max`, `count`, `first`, `std` |
| **Pointwise** | `last`, `exists`, `missing` |

---

### Window

A time duration that defines the lookback period for windowed operators.

**Format:** `<integer><unit>`

| Unit | Meaning |
|------|---------|
| `s` | seconds |
| `m` | minutes |
| `h` | hours |
| `d` | days |
| `w` | weeks |

**Examples:** `6h` (6 hours), `48h` (48 hours), `7d` (7 days)

---

## Architecture Components

### Specification

The formal definition of PSDL - what the language IS. Includes schema, grammar, operator semantics, and constraints. This is the **source of truth**.

**Location:** `spec/`

**Files:**
- `schema.json` - JSON Schema for scenario structure
- `grammar/expression.lark` - Lark grammar for expressions
- `operators.yaml` - Operator semantic definitions

---

### IR (Intermediate Representation)

The in-memory data structure representing a parsed and validated scenario. IR is independent of execution method - it can be compiled to SQL, Flink, or evaluated in Python.

**Types:** `PSDLScenario`, `Signal`, `Trend`, `Logic`, `AuditBlock`, `StateMachine`, `StateTransition`

---

### Parser

Component that transforms YAML/JSON scenario files into IR. Uses Lark grammar for expression parsing and JSON Schema for structure validation.

**Input:** YAML/JSON file
**Output:** `ScenarioIR`

---

### Validator

Component that checks if an IR is semantically valid. Verifies signal references, operator usage, circular dependencies, etc.

**Input:** `ScenarioIR`
**Output:** List of validation errors or success

---

### Compiler

Component that transforms IR into executable code for a specific runtime. Each runtime has its own compiler.

| Compiler | Output |
|----------|--------|
| SQL Compiler | SQL query |
| Flink Compiler | Flink DataStream job |

---

### Codegen (Code Generation)

The process of automatically generating code from specification files. PSDL generates:
- Python types from JSON Schema
- Parsers from Lark grammar
- Operator implementations from `operators.yaml`

**Command:** `make codegen`

---

### Conformance Test

Tests that verify all runtimes produce identical results for the same scenario and data. Ensures SQL output matches Python output matches Flink output.

**Location:** `tests/conformance/`

---

## Runtimes

### Runtime

An execution environment that evaluates scenarios against patient data. Different runtimes exist for different use cases.

| Runtime | Use Case | Implementation |
|---------|----------|----------------|
| Single | Testing, debugging | Python |
| Cohort | Retrospective analysis | SQL |
| Streaming | Real-time monitoring | Apache Flink |

---

### Single Runtime

Evaluates a scenario for **ONE patient** at a specific point in time. Used for testing, debugging, and small-scale evaluation.

**Use case:** Development, testing, single-patient alerts
**Implementation:** Python

---

### Cohort Runtime

Evaluates a scenario for **MANY patients** in batch mode. Used for retrospective analysis and research. Compiles PSDL to SQL for efficient database execution.

**Use case:** Retrospective studies, cohort screening, research
**Implementation:** SQL (PostgreSQL, BigQuery, etc.)

---

### Streaming Runtime

Evaluates a scenario **CONTINUOUSLY** as new data arrives. Used for real-time monitoring and alerts. Compiles PSDL to Apache Flink jobs.

**Use case:** Real-time ICU monitoring, live alerts
**Implementation:** Apache Flink

---

## Data Models & Sources

### Dataset Spec (Dataset Specification)

A declarative binding layer that maps PSDL semantic references to concrete data source locations. Enables the same scenario to run across different datasets (OMOP, FHIR, MIMIC) without modification.

**Core principle:**
```
Scenario   = intent  (WHAT to detect)
Dataset Spec = binding (WHERE to find it)
Adapter    = execution (HOW to run it)
```

**Contents:**
- Element bindings (semantic name → table/field/path)
- Encoding bindings (concept_id, LOINC codes, valuesets)
- Type declarations (unit, value_type)
- Time axis conventions (time_field, timezone)

**File format:** YAML

See [RFC-0004](../rfcs/0004-dataset-specification.md) for full specification.

---

### Adapter

Component that connects PSDL to a specific data source. Adapters load Dataset Specs and execute queries against data infrastructure.

| Adapter | Data Source |
|---------|-------------|
| `OMOPAdapter` | OMOP CDM databases |
| `FHIRAdapter` | FHIR R4 servers |
| `InMemoryAdapter` | In-memory data (testing) |

---

### OMOP (Observational Medical Outcomes Partnership)

A common data model (CDM) for observational healthcare data. PSDL uses OMOP concept_ids for portable signal definitions.

**Link:** https://ohdsi.org/omop/

---

### FHIR (Fast Healthcare Interoperability Resources)

A standard for healthcare data exchange. PSDL can consume FHIR resources as signal data sources.

**Version:** R4
**Link:** https://hl7.org/fhir/

---

### DataPoint

A single observation in a time series. Contains a timestamp and an optional value.

```
DataPoint {
  timestamp: datetime
  value: float | null
}
```

---

### Reference Time

The point in time at which a scenario is evaluated. All windows are calculated relative to this time.

- **Real-time:** now
- **Retrospective:** a specific historical moment

**Example:** `2024-01-15T14:30:00Z`

---

## Clinical Terms

### Trigger

When a logic expression evaluates to TRUE, the scenario is said to "trigger" for that patient. A triggered scenario typically results in an alert or action.

**Result:** `EvaluationResult` with `is_triggered=True`

---

### Severity

Clinical importance level assigned to logic expressions. Used for alert prioritization.

| Level | Description |
|-------|-------------|
| `low` | Informational |
| `medium` | Warrants attention |
| `high` | Requires prompt action |
| `critical` | Immediate action required |

---

### AKI (Acute Kidney Injury)

A sudden decline in kidney function. PSDL example scenarios detect AKI using creatinine trends based on KDIGO criteria.

| Stage | Criteria |
|-------|----------|
| Stage 1 | Cr rise >= 0.3 mg/dL in 48h |
| Stage 2 | Cr 2x baseline |
| Stage 3 | Cr 3x baseline or >= 4.0 mg/dL |

---

### KDIGO (Kidney Disease: Improving Global Outcomes)

Clinical practice guidelines for kidney disease. PSDL AKI detection scenarios implement KDIGO staging criteria.

**Link:** https://kdigo.org/

---

## Quick Reference

### File Extensions

| Extension | Purpose |
|-----------|---------|
| `.yaml` | Scenario definitions |
| `.json` | Alternative scenario format, schemas |
| `.lark` | Grammar definitions |
| `.ebnf` | Grammar documentation |

### Directory Structure

| Directory | Contents |
|-----------|----------|
| `spec/` | Specification files (source of truth) |
| `src/psdl/core/` | Parser, IR, Validator |
| `src/psdl/runtimes/` | Single, Cohort, Streaming |
| `src/psdl/adapters/` | OMOP, FHIR, InMemory |
| `src/psdl/_generated/` | Auto-generated code |

### CLI Commands

| Command | Purpose |
|---------|---------|
| `psdl validate <file>` | Validate a scenario |
| `psdl run <file>` | Execute batch analysis |
| `psdl stream <file>` | Deploy streaming job |
| `psdl compile <file>` | Show generated code |
