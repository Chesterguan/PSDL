<p align="center">
  <img src="./assets/logo.jpeg" alt="PSDL Logo" width="400"/>
</p>

<h1 align="center">PSDL Whitepaper</h1>
<h3 align="center">Patient Scenario Definition Language</h3>
<h4 align="center">Version 0.1 | December 2025</h4>

<p align="center">
  <em>An Open Standard for Clinical Logic in Healthcare AI</em>
</p>

---

<p align="center">
  <strong>What SQL became for data queries, and ONNX became for ML models —<br/>
  PSDL aims to become for clinical scenario logic.</strong>
</p>

---

## Executive Summary

Healthcare AI has a deployment problem. Despite remarkable advances in predictive modeling, the vast majority of clinical AI systems never reach the bedside. The barrier is not model accuracy — it is the absence of a standard way to express *when*, *where*, and *how* these models should operate in clinical workflows.

**PSDL (Patient Scenario Definition Language)** is an open, vendor-neutral standard that fills this critical gap. It provides a declarative language for expressing clinical scenarios — the logic that connects patient data to clinical actions.

### Key Value Propositions

| Stakeholder | Value |
|-------------|-------|
| **Hospitals** | Portable clinical logic that works across EHR systems |
| **Researchers** | Reproducible scenarios that can be shared and validated |
| **Vendors** | Common format reducing integration complexity |
| **Regulators** | Auditable, version-controlled decision logic |
| **Clinicians** | Transparent rules that can be reviewed and understood |

---

## The Problem: Why Clinical AI Fails to Deploy

<p align="center">
  <img src="./assets/scenario-semantics-gap.png" alt="The Scenario Semantics Gap" width="800"/>
  <br/>
  <em>The gap between ML models and clinical workflows — PSDL bridges this divide</em>
</p>

### The Scenario Semantics Gap

A hospital develops an ML model that predicts patient deterioration with 90% accuracy. Impressive. But then come the questions:

- **When** should this model run? Every hour? On new lab results?
- **On which patients?** All ICU patients? Only those meeting certain criteria?
- **Based on what signals?** Which vitals? Which labs? What time windows?
- **What thresholds trigger action?** Score > 0.7? Combined with other factors?
- **What happens when triggered?** Page a physician? Generate an order?

These are **scenario semantics** — and healthcare has no standard way to express them.

### Current State: Fragmented Clinical Logic

<p align="center">
  <img src="./assets/fragmentation-diagram.png" alt="Clinical Logic Fragmentation" width="800"/>
  <br/>
  <em>Clinical logic today is scattered across incompatible systems</em>
</p>

Today, clinical decision logic is scattered across:

| Implementation | Problems |
|----------------|----------|
| Python scripts | Non-portable, implicit dependencies, hard to audit |
| SQL queries | No temporal semantics, tightly coupled to schema |
| EHR rule editors | Proprietary, vendor-locked, non-exportable |
| Jupyter notebooks | Non-reproducible, no version control semantics |
| Configuration files | Ad-hoc formats, no standardization |

**The result:** Every hospital reinvents the same clinical logic from scratch. Research cannot be reproduced. Regulatory audits require manual documentation. Vendor transitions mean rewriting everything.

---

## The Solution: PSDL

<p align="center">
  <img src="./assets/layers.jpeg" alt="PSDL Architecture" width="800"/>
  <br/>
  <em>PSDL as the semantic layer in the healthcare AI stack</em>
</p>

PSDL introduces a **semantic layer** for clinical scenarios — a structured, declarative format that separates *what* to detect from *how* to compute it.

### Core Concepts

```
Scenario = Population + Signals + Trends + Logic + Triggers
```

| Component | Description | Example |
|-----------|-------------|---------|
| **Population** | Which patients the scenario applies to | `age >= 18 AND unit == "ICU"` |
| **Signals** | Time-series data bindings | `Cr: creatinine (mg/dL)` |
| **Trends** | Temporal computations | `delta(Cr, 6h) > 0.3` |
| **Logic** | Boolean combinations | `cr_rising AND cr_high` |
| **Triggers** | Actions when logic fires | `notify_team("ICU")` |

### Example: Early AKI Detection

```yaml
scenario: AKI_Early_Detection
version: "0.1.0"
description: "Detect early acute kidney injury based on creatinine trends"

population:
  include:
    - age >= 18
    - unit == "ICU"

signals:
  Cr:
    source: creatinine
    concept_id: 3016723    # OMOP standard concept
    unit: mg/dL

trends:
  cr_rising:
    expr: delta(Cr, 6h) > 0.3
    description: "Creatinine increased >0.3 mg/dL in 6 hours"

  cr_elevated:
    expr: last(Cr) > 1.5
    description: "Current creatinine above normal"

logic:
  aki_stage1:
    expr: cr_rising AND cr_elevated
    severity: high
    description: "Early AKI - KDIGO Stage 1 criteria"

triggers:
  - when: aki_stage1
    actions:
      - type: notify_team
        target: nephrology_consult
        priority: high
```

This single YAML file replaces hundreds of lines of scattered Python, SQL, and configuration code — and it's portable, auditable, and version-controlled.

---

## Why an Open Standard?

PSDL follows the precedent of successful open standards:

| Standard | Domain | What It Standardized |
|----------|--------|---------------------|
| **SQL** | Data | Query language for databases |
| **ONNX** | ML | Model interchange format |
| **FHIR** | Healthcare | Clinical data exchange |
| **CQL** | Quality | Clinical quality measures |
| **PSDL** | Scenarios | Clinical decision logic |

### Benefits of Openness

<p align="center">
  <img src="./assets/psdl-ecosystem.png" alt="PSDL Ecosystem" width="600"/>
  <br/>
  <em>PSDL connects all stakeholders in the clinical AI ecosystem</em>
</p>

| Principle | Benefit |
|-----------|---------|
| **Vendor Neutral** | No lock-in; any hospital can adopt freely |
| **Community Governed** | Evolution driven by real clinical needs |
| **Implementation Freedom** | Multiple runtimes can be conformant |
| **Reproducibility** | Researchers can share exact scenario definitions |
| **Regulatory Clarity** | Standard format enables systematic auditing |

---

## Technical Architecture

### The PSDL Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    CLINICAL APPLICATIONS                     │
│         (Alerts, Dashboards, Order Suggestions)             │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
┌─────────────────────────────────────────────────────────────┐
│                     PSDL SEMANTIC LAYER                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Signals │→ │ Trends  │→ │  Logic  │→ │Triggers │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
└─────────────────────────────────────────────────────────────┘
                              ▲
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │   OMOP   │        │   FHIR   │        │  Stream  │
    │  Runtime │        │  Runtime │        │  Runtime │
    └──────────┘        └──────────┘        └──────────┘
          ▲                   ▲                   ▲
          │                   │                   │
┌─────────────────────────────────────────────────────────────┐
│                      CLINICAL DATA                           │
│            (EHR, Lab Systems, Monitoring Devices)            │
└─────────────────────────────────────────────────────────────┘
```

### Temporal Operators

PSDL provides first-class support for time-series clinical data:

| Operator | Description | Example |
|----------|-------------|---------|
| `delta(signal, window)` | Change over time window | `delta(Cr, 6h) > 0.3` |
| `slope(signal, window)` | Linear trend | `slope(lactate, 3h) > 0` |
| `ema(signal, window)` | Exponential moving average | `ema(MAP, 30m) < 65` |
| `sma(signal, window)` | Simple moving average | `sma(HR, 1h) > 100` |
| `min/max(signal, window)` | Extremes in window | `max(temp, 24h) > 38.5` |
| `last(signal)` | Most recent value | `last(SpO2) < 92` |
| `count(signal, window)` | Observation count | `count(Cr, 24h) >= 2` |

### Multi-Runtime Support

PSDL scenarios are runtime-agnostic. The same scenario can execute on:

| Runtime | Use Case | Data Source |
|---------|----------|-------------|
| **OMOP SQL** | Retrospective research | CDM databases |
| **FHIR** | Real-time EHR integration | FHIR servers |
| **Python** | Development & testing | DataFrames |
| **Stream** | Real-time monitoring | Kafka/Flink |

---

## Comparison: Before and After PSDL

<p align="center">
  <img src="./assets/before-after-psdl.png" alt="Before and After PSDL" width="700"/>
  <br/>
  <em>PSDL dramatically simplifies clinical logic management</em>
</p>

| Aspect | Before PSDL | After PSDL |
|--------|-------------|------------|
| **Lines of Code** | ~300+ Python/SQL | ~50 lines YAML |
| **Portability** | Tied to specific systems | Runs anywhere with mapping |
| **Auditability** | Manual documentation | Built-in, version-controlled |
| **Reproducibility** | "Works on my machine" | Deterministic execution |
| **Sharing** | Copy-paste with modifications | Publish exact definitions |
| **Regulatory** | Ad-hoc compliance | Systematic audit support |

---

## Regulatory Alignment

PSDL is designed with regulatory requirements in mind:

| Requirement | FDA | EU MDR | NIST AI RMF | PSDL Support |
|-------------|:---:|:------:|:-----------:|:------------:|
| Deterministic Execution | ✓ | ✓ | ✓ | Built-in |
| Explainability | ✓ | ✓ | ✓ | Declarative logic |
| Auditability | ✓ | ✓ | ✓ | Version control |
| Traceability | ✓ | ✓ | ✓ | Audit primitives |
| Reproducibility | ✓ | ✓ | ✓ | Portable definitions |

---

## Roadmap

<p align="center">
  <img src="./assets/roadmap-timeline.png" alt="PSDL Roadmap" width="900"/>
  <br/>
  <em>PSDL development phases</em>
</p>

### Phase 1: Semantic Foundation [Current]
- Type system and operator specification
- YAML schema definition
- Python reference implementation
- Example clinical scenarios
- Conformance test suite

### Phase 2: Enhanced Runtime
- OMOP CDM SQL backend
- FHIR R4 runtime
- Trigger/Action system (v0.2)
- Performance optimization

### Phase 3: Community Building
- Technical documentation
- Conference presentations
- Community infrastructure (Discord, forums)
- Third-party implementations

### Phase 4: Adoption
- Hospital pilot programs
- Standards body engagement (OHDSI, HL7)
- Vendor partnerships
- Certification program

---

## Get Involved

PSDL is an open, community-driven project. We welcome contributions from:

- **Clinical Informaticists** — Define real-world scenarios and requirements
- **Software Engineers** — Build runtimes, tools, and integrations
- **Researchers** — Validate portability and reproducibility
- **Healthcare Organizations** — Pilot implementations and provide feedback
- **Standards Bodies** — Help align with existing healthcare standards

### Quick Links

| Resource | Link |
|----------|------|
| GitHub Repository | [github.com/psdl-lang/psdl](https://github.com/psdl-lang/psdl) |
| Documentation | [Getting Started Guide](./getting-started.md) |
| Examples | [Example Scenarios](../examples/) |
| RFCs | [Proposals](../rfcs/) |

---

## Conclusion

Healthcare AI deployment is blocked not by model quality, but by the absence of scenario semantics. PSDL fills this gap with:

- **A declarative language** for expressing clinical scenarios
- **Vendor-neutral portability** across institutions and systems
- **Built-in auditability** for regulatory compliance
- **Community governance** ensuring the standard evolves with real needs

The path from ML model to bedside impact requires a semantic layer. PSDL provides it.

---

<p align="center">
  <strong>Clinical AI doesn't fail because models are weak.<br/>
  It fails because scenario semantics aren't formalized.</strong>
</p>

<p align="center">
  <em>PSDL changes that.</em>
</p>

---

<p align="center">
  <strong>Join us in building the standard for clinical decision logic.</strong>
  <br/><br/>
  <a href="https://github.com/psdl-lang/psdl">GitHub</a> ·
  <a href="./getting-started.md">Get Started</a> ·
  <a href="../CONTRIBUTING.md">Contribute</a>
</p>

---

## Appendix A: Full Scenario Example

```yaml
# ICU Deterioration Detection Scenario
# PSDL v0.1.0

scenario: ICU_Deterioration_Detection
version: "0.1.0"
description: |
  Comprehensive monitoring for early signs of clinical deterioration
  in adult ICU patients. Combines kidney function, lactate trends,
  and hemodynamic stability markers.

metadata:
  author: Clinical Informatics Team
  institution: Example Health System
  created: 2025-12-01
  references:
    - "KDIGO AKI Guidelines 2012"
    - "Surviving Sepsis Campaign 2021"

population:
  include:
    - age >= 18
    - unit IN ["MICU", "SICU", "CCU"]
    - admission_type == "inpatient"
  exclude:
    - status == "comfort_care_only"
    - dnr_dni == true

signals:
  # Renal markers
  Cr:
    source: creatinine
    concept_id: 3016723
    unit: mg/dL
    domain: measurement

  BUN:
    source: blood_urea_nitrogen
    concept_id: 3013682
    unit: mg/dL

  # Metabolic markers
  Lactate:
    source: lactate
    concept_id: 3047181
    unit: mmol/L

  # Hemodynamic markers
  MAP:
    source: mean_arterial_pressure
    concept_id: 3027598
    unit: mmHg

  HR:
    source: heart_rate
    concept_id: 3027018
    unit: bpm

trends:
  # Renal trends
  cr_rising:
    expr: delta(Cr, 6h) > 0.3
    description: "Creatinine increase >0.3 mg/dL over 6 hours"

  cr_elevated:
    expr: last(Cr) > 1.5
    description: "Current creatinine above normal range"

  # Metabolic trends
  lactate_rising:
    expr: slope(Lactate, 3h) > 0
    description: "Positive lactate trajectory"

  lactate_elevated:
    expr: last(Lactate) > 2.0
    description: "Lactate above normal (>2 mmol/L)"

  # Hemodynamic trends
  hypotension:
    expr: ema(MAP, 30m) < 65
    description: "Sustained MAP below 65 mmHg"

  tachycardia:
    expr: sma(HR, 1h) > 100
    description: "Sustained heart rate >100 bpm"

logic:
  # Renal deterioration
  aki_risk:
    expr: cr_rising AND cr_elevated
    severity: high
    description: "Acute kidney injury risk - KDIGO Stage 1"

  # Metabolic deterioration
  metabolic_stress:
    expr: lactate_rising AND lactate_elevated
    severity: high
    description: "Metabolic stress with rising lactate"

  # Hemodynamic instability
  hemodynamic_instability:
    expr: hypotension OR (tachycardia AND NOT hypotension)
    severity: medium
    description: "Hemodynamic instability"

  # Combined deterioration
  deterioration:
    expr: aki_risk OR metabolic_stress
    severity: high
    description: "Clinical deterioration detected"

  # Critical state
  shock_risk:
    expr: deterioration AND hemodynamic_instability
    severity: critical
    description: "High risk of shock - immediate attention required"

triggers:
  - when: deterioration
    actions:
      - type: notify_team
        target: primary_team
        priority: high
        message: "Patient showing signs of clinical deterioration"
      - type: log_event
        category: clinical_alert

  - when: shock_risk
    actions:
      - type: page_physician
        target: attending
        escalation: immediate
      - type: order_suggestion
        protocol: sepsis_bundle
        reason: "Shock risk detected - consider sepsis workup"

audit:
  enabled: true
  retention: 7y
  include_patient_context: false
  log_all_evaluations: true
```

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Signal** | A binding between a logical name and a clinical data source |
| **Trend** | A temporal computation over a signal (e.g., delta, slope) |
| **Logic** | A boolean expression combining trends |
| **Trigger** | An event-condition-action rule |
| **Scenario** | A complete PSDL definition combining all components |
| **Runtime** | An execution environment that evaluates PSDL scenarios |
| **Mapping** | Configuration that adapts a scenario to a specific data source |

---

*PSDL Whitepaper v0.1 | December 2025 | Apache 2.0 License*
