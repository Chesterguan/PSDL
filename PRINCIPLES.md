# PSDL Principles

> The laws that define what PSDL is and is not.

---

## The Core Law

**PSDL defines WHAT to detect, not HOW to collect or execute.**

This means:
- PSDL defines **WHAT** clinical patterns to detect
- PSDL does NOT define **HOW** to collect data (data collection layer)
- PSDL does NOT define **HOW** to execute computation (runtime layer)
- PSDL does NOT define **HOW** to run triggers (action layer)

---

## First-Citizen: Clinical Accountability

> **Clinical AI doesn't fail because models are weak. It fails because decisions cannot be traced.**

PSDL's primary value is **traceability**. Every scenario MUST answer three questions:

| Question | Audit Field | What It Captures |
|----------|-------------|------------------|
| **WHO** wrote this logic? | `audit.intent` | The clinical detection goal |
| **WHY** does this matter? | `audit.rationale` | The clinical justification |
| **WHAT** evidence supports it? | `audit.provenance` | The source (guidelines, literature, expert consensus) |

**This is not optional.** The `audit` block is REQUIRED in every PSDL scenario.

```yaml
# Every PSDL scenario must include:
audit:
  intent: "Detect early acute kidney injury"
  rationale: "Early AKI detection enables timely intervention"
  provenance: "KDIGO Clinical Practice Guideline for AKI (2012)"
```

### Why Accountability is First-Citizen

| Property | Important? | First-Citizen? | Reason |
|----------|------------|----------------|--------|
| **Accountable** | Yes | **YES** | Unique to PSDL, mandatory, solves regulatory pain |
| Portable | Yes | No | Many tools claim this |
| Reproducible | Yes | No | Expected, not differentiating |
| Declarative | Yes | No | Common pattern |

### What This Enables

- **Regulatory Compliance**: FDA and EU MDR reviewers can trace every clinical decision
- **Institutional Trust**: Hospitals can audit deployed scenarios without reading code
- **Research Validity**: Published scenarios are self-documenting
- **Version Control**: Changes to clinical logic are auditable diffs

---

## First Principles

| # | Principle | Statement |
|---|-----------|-----------|
| **P1** | Specification First | PSDL is a specification, not software. Reference implementations demonstrate it. Multiple implementations can exist; all must conform to the same specification. |
| **P2** | Data Exists | PSDL operates on data that exists. It does not create, collect, or orchestrate data collection. Once data exists (in any form), PSDL can use it. |
| **P3** | Intent vs Implementation | Scenarios express clinical intent (WHAT to detect). Runtimes handle execution details (HOW to compute). |
| **P4** | Deterministic | Same scenario + same data = same result. Always. No hidden state, no side effects, no randomness. |
| **P5** | Vendor Neutral | No proprietary dependencies. No lock-in. Community governed. Works with any data source that provides the required signals. |

---

## Scope Laws: What PSDL DOES

| Law | PSDL Defines... | Example |
|-----|-----------------|---------|
| **S1** | **Signals** - bindings to clinical data sources | `Cr: creatinine (mg/dL)` |
| **S2** | **Trends** - temporal computations over signals | `delta(Cr, 48h) > 0.3` |
| **S3** | **Logic** - boolean combinations of trends | `cr_rising AND cr_elevated` |
| **S4** | **Triggers** - what actions to take when logic fires | `notify_team("nephrology")` |
| **S5** | **Populations** - which patients a scenario applies to | `age >= 18 AND unit == "ICU"` |
| **S6** | **Operator Semantics** - mathematical definitions of temporal operators | `delta`, `slope`, `ema`, `sma`, `min`, `max`, `count`, `last` |

---

## Scope Laws: What PSDL Does NOT Do

| Law | PSDL Does NOT... | Use Instead |
|-----|------------------|-------------|
| **N1** | Collect data from patients | Nursing apps, tablets, devices |
| **N2** | Execute ML/AI models | ONNX Runtime, model servers |
| **N3** | Orchestrate clinical workflows | EHR workflow engines |
| **N4** | Define data storage schemas | FHIR servers, databases |
| **N5** | Replace OMOP or FHIR | PSDL *consumes* these standards |
| **N6** | Define how triggers execute | Runtime's responsibility |
| **N7** | Handle interactive dialogue | Clinical decision support systems |
| **N8** | Generate queries or optimize SQL | Execution backends (SQL/Flink/DuckDB) |

> **PSDL is not a query language.** It outputs intent (IR). Backends handle execution.

---

## Boundary Decisions

Quick reference for common questions:

| Scenario | PSDL? | Reason |
|----------|:-----:|--------|
| Lab result triggers alert | **Yes** | Lab data exists in EHR |
| ML model output triggers alert | **Yes** | Model output becomes data |
| Pain score (after documented) triggers alert | **Yes** | It's now structured data |
| Collect pain score from patient | No | Data collection (outside PSDL) |
| Run an ML model | No | Runtime concern |
| Poll an API for results | No | Implementation detail |
| Display alert in EHR | No | Trigger execution (runtime) |
| Perform mental status exam | No | Data collection |
| Mental status findings (after charted) triggers alert | **Yes** | It's documented data |
| Write SQL query | No | Execution backend's job |
| Optimize query performance | No | Runtime concern |
| Define table schema | No | Dataset specification (external) |

**Key Insight**: Once data exists, PSDL can use it - regardless of how it was collected.

**Key Insight**: PSDL outputs IR (intent). Backends convert IR to queries.

---

## Specification vs Implementation

| Aspect | Specification | Reference Implementation |
|--------|---------------|-------------------------|
| **Purpose** | Define the language | Demonstrate one way to run it |
| **Scope** | Detection logic only | May add conveniences |
| **Portability** | Must be portable | Python-specific |
| **Triggers** | Declares WHAT action | HOW to execute is runtime's job |
| **Location** | `spec/` | `src/psdl/` |
| **Audience** | All implementers | Python developers |

The reference implementation can do many things, but **PSDL the specification remains elegant and focused** on expressing detection logic.

---

## Design Principles

| Principle | Law Statement |
|-----------|---------------|
| **Declarative** | Scenarios declare *what* to detect, never *how* to compute |
| **Portable** | Same scenario runs on any conformant backend with appropriate mappings |
| **Auditable** | Every scenario is a version-controlled, human-readable document |
| **Deterministic** | Identical inputs always produce identical outputs |
| **Open** | No vendor owns PSDL. The community governs the specification |

---

## Architecture: Clean Separation

```
+----------------------------------+-----------------------------------+
|   DATA COLLECTION LAYER          |   PSDL DETECTION LAYER            |
|   (Outside PSDL Scope)           |   (PSDL Specification)            |
|                                  |                                   |
|   Tablet -> Pain Score ----+     |   signals:                        |
|                            |     |     pain: pain_score              |
|   Nurse -> Assessment -----+---> |   trends:                         |
|                            |     |     pain_high: last(pain) > 7     |
|   ML Model -> Prediction --+     |   logic:                          |
|                            |     |     needs_eval: pain_high         |
|   Lab System -> Results ---+     |                                   |
|                                  |                                   |
|   [HOW data gets there]          |   [WHAT to detect]                |
+----------------------------------+-----------------------------------+
```

---

## Summary

> **PSDL declares WHAT to detect - it does not orchestrate HOW to collect data or execute logic.**

This clean separation enables:
- **Deterministic execution** - same data always produces same result
- **Regulatory clarity** - auditors see exactly what triggers alerts
- **Portability** - scenarios work across any system with the data
- **Runtime flexibility** - any conformant runtime can execute the same scenario
- **Elegance** - the specification stays simple and focused

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [WHITEPAPER](docs/WHITEPAPER_EN.md) | Full specification and vision |
| [README](README.md) | Project overview and quick start |
| [GLOSSARY](docs/GLOSSARY.md) | Terminology definitions |
| [ROADMAP](docs/ROADMAP.md) | Development phases |

---

*PSDL Principles v1.0 | December 2025 | Apache 2.0 License*
