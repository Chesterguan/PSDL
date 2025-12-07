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
| GitHub Repository | [github.com/Chesterguan/PSDL](https://github.com/Chesterguan/PSDL) |
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
  <a href="https://github.com/Chesterguan/PSDL">GitHub</a> ·
  <a href="./getting-started.md">Get Started</a> ·
  <a href="../CONTRIBUTING.md">Contribute</a>
</p>

---

## Related Work

PSDL builds upon decades of research in clinical decision support languages and healthcare informatics. Understanding this landscape helps position PSDL's unique contributions and identifies opportunities for future integration.

### Historical Foundation: Arden Syntax

[Arden Syntax](https://en.wikipedia.org/wiki/Arden_syntax) (HL7, 1992) is the foundational clinical rule language. Its Medical Logic Modules (MLMs) introduced the event-trigger-action paradigm for clinical alerts. Arden Syntax demonstrated that clinical knowledge could be encoded in shareable, executable form.

**What PSDL learns:** The event-trigger model, patient data binding, and rule-to-action flow directly influence PSDL's trigger system. However, Arden Syntax focuses on individual rules, while PSDL emphasizes **scenario composition** — combining multiple signals, trends, and logic into cohesive clinical scenarios.

| Aspect | Arden Syntax | PSDL |
|--------|--------------|------|
| Unit of Knowledge | Medical Logic Module (single rule) | Scenario (composed logic) |
| Temporal Operators | Limited | First-class (`delta`, `slope`, `ema`) |
| Data Binding | Direct patient data | Abstract signals with mapping layer |
| Focus | Alert generation | Scenario semantics |

### Clinical Pathway DSLs: Acadela

[Acadela](https://wwwmatthes.in.tum.de/pages/a8yka1dz1gsa/Acadela-A-Domain-Specific-Language-for-Modeling-Clinical-Pathways) (TU München, 2023) is a text-based DSL for modeling clinical pathways. It covers workflow, responsibilities, data visualization, and external system communication.

**What PSDL learns:** Acadela demonstrates the value of a low-tech, text-based approach that enables collaboration between medical and technical experts. Its user studies validate that clinical professionals find declarative DSLs intuitive.

**Key difference:** Acadela models **pathways** (treatment procedures over time), while PSDL models **scenarios** (detection logic at a point in time). These are complementary — PSDL scenarios could trigger Acadela pathways.

### Scenario-Based Modeling: SBRM-DSL

[SBRM-DSL](https://ieeexplore.ieee.org/document/8817187/) (ICWS 2019) introduces a four-element model for crossover healthcare services:

```
WHO → SCENARIO → PROCESS → RULE
```

This framework explicitly models multi-actor scenarios in healthcare, where patients, doctors, nurses, and systems interact.

**What PSDL learns:** The WHO-SCENARIO-PROCESS-RULE structure provides a template for PSDL's future extensions into multi-role scenarios. Currently PSDL focuses on patient-centric detection; future versions may incorporate care team roles.

### Quality Measures: Clinical Quality Language (CQL)

[Clinical Quality Language](https://cql.hl7.org/) (HL7) is a high-level language for clinical quality measures and decision support. CQL integrates with FHIR and supports complex clinical logic.

**PSDL's relationship to CQL:**

| Aspect | CQL | PSDL |
|--------|-----|------|
| Primary Focus | Quality measurement, cohort definition | Real-time scenario detection |
| Temporal Operators | Good support | First-class, streaming-native |
| Runtime Model | Query-based | Event-driven + query |
| Complexity | Higher learning curve | Simpler, YAML-based |
| Adoption | Established standard | Emerging |

PSDL complements CQL rather than competing. CQL excels at quality measurement and reporting; PSDL excels at real-time clinical detection with explicit temporal semantics.

### Clinical Scores: DSML4ClinicalScores

[DSML4ClinicalScores](https://www.researchgate.net/publication/339125394_Model-Driven_Development_Applied_to_Mobile_Health_and_Clinical_Scores) (2020) uses model-driven development to generate mHealth apps from clinical score specifications. Analyzing 89 clinical scores, it creates a metamodel for risk assessment tools.

**Future PSDL integration:** Clinical scores (SOFA, APACHE, NEWS2) could be first-class concepts in PSDL:

```yaml
# Potential future syntax
scores:
  NEWS2:
    type: clinical_score
    source: news2_score

trends:
  news2_critical:
    expr: last(NEWS2) >= 7
```

### Prescription DSL: GME Framework

[Prescription DSL](https://www.researchgate.net/publication/344327532_A_Domain_Specific_Modeling_Language_Framework_DSL_for_Representative_Medical_Prescription_by_using_Generic_Modeling_Environment_GME) (2020) uses Generic Modeling Environment (GME) to model medical prescriptions with dosage, frequency, and validation rules.

**Future PSDL integration:** Medication scenarios could become a PSDL module:

```yaml
# Potential future syntax
medications:
  metformin:
    drug_id: RxNorm:6809
    current_dose: last(metformin_dose)

trends:
  dose_interaction_risk:
    expr: taking(metformin) AND last(Cr) > 1.5
```

### Virtual Patients: LLM-Based Simulation

Recent advances in [LLM-based virtual patients](https://pubmed.ncbi.nlm.nih.gov/38992981/) (2024-2025) enable scalable, low-cost clinical simulation. Systems like [AIPatient](https://arxiv.org/abs/2409.18924) use retrieval-augmented generation with real patient data (MIMIC-III).

**Future PSDL integration:** PSDL scenarios could drive virtual patient behavior:

```yaml
# Virtual patient scenario
scenario: Virtual_Sepsis_Case
mode: simulation

progression:
  hour_0:
    vitals: { HR: 88, RR: 18, Temp: 37.0 }
  hour_4:
    vitals: { HR: 105, RR: 22, Temp: 38.5 }
    trigger: qsofa_positive
```

This would enable standardized, reproducible clinical simulations for education.

---

## Vision: The PSDL Ecosystem

PSDL's current focus on **scenario semantics** (Signals → Trends → Logic → Triggers) establishes a foundation. The long-term vision encompasses a complete clinical AI stack.

### Layered Architecture Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                      PSDL ECOSYSTEM (Future)                     │
├─────────────────────────────────────────────────────────────────┤
│  PSDL.Simulation  │  Virtual patients, case generation          │
├───────────────────┼─────────────────────────────────────────────┤
│  PSDL.Pathway     │  Multi-step clinical protocols              │
├───────────────────┼─────────────────────────────────────────────┤
│  PSDL.Model       │  AI/ML model integration (RFC-0001)         │
├───────────────────┼─────────────────────────────────────────────┤
│  PSDL.Core        │  Scenarios (current focus) ← WE ARE HERE    │
├───────────────────┼─────────────────────────────────────────────┤
│  PSDL.Data        │  Signal abstraction, mappings               │
└─────────────────────────────────────────────────────────────────┘
```

### What PSDL Will NOT Do

Being clear about scope is essential. PSDL is designed to excel at:

| In Scope | Out of Scope |
|----------|--------------|
| Scenario definition | Model training |
| Temporal logic | Data warehousing |
| Event detection | EHR workflow |
| Alert triggering | User interface |
| Cross-platform portability | Protocol implementation |

PSDL intentionally does not replace:
- **FHIR/OMOP** — Data standards (PSDL uses them)
- **CQL** — Quality measures (complementary)
- **Arden Syntax** — Simple rules (PSDL adds composition)
- **Pathway languages** — Treatment protocols (future integration)

### Integration Philosophy

Rather than reinventing, PSDL integrates:

```
┌──────────────────────────────────────────────────────┐
│                   PSDL Scenario                       │
│  ┌──────────────────────────────────────────────┐   │
│  │ Signals → Trends → Logic → Triggers          │   │
│  └──────────────────────────────────────────────┘   │
│         ▲              ▲              ▲              │
│         │              │              │              │
│    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐         │
│    │  FHIR   │   │   CQL   │   │  ONNX   │         │
│    │  OMOP   │   │ (logic) │   │ (models)│         │
│    └─────────┘   └─────────┘   └─────────┘         │
└──────────────────────────────────────────────────────┘
```

### Research Opportunities

Based on related work, we identify research directions:

1. **Formal Verification** — Can PSDL scenarios be formally proven safe?
2. **Scenario Composition** — How do multiple scenarios interact?
3. **Temporal Extensions** — What operators are missing for clinical use?
4. **Cross-Institution Portability** — How well do scenarios transfer?
5. **LLM Integration** — Can LLMs generate/validate PSDL scenarios?

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
