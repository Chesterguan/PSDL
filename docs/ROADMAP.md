# PSDL Roadmap

> The path from specification to clinical adoption

---

## Overview

PSDL development follows a phased approach, building from a solid semantic foundation toward real-world clinical deployment.

```
Phase 1          Phase 2           Phase 3          Phase 4
Semantic    →    v0.3         →    Production  →    Adoption
Foundation       Architecture      Readiness        & Scale
[Complete]       [Complete]        [Current]        [Future]
```

**Important Distinction:**
- **Specification** (WHAT): Language definition, schema, operator semantics
- **Reference Implementation** (HOW): Python runtime, adapters, tooling

---

## Phase 1: Semantic Foundation ✅ Complete

**Goal**: Establish the core language specification and prove correctness.

### Specification
- [x] Type system definition (Signals, Trends, Logic, Population)
- [x] Operator semantics (delta, slope, ema, sma, min, max, count, last)
- [x] YAML schema (`spec/schema.json`)
- [x] Window format specification (s, m, h, d)

### Reference Implementation
- [x] Python parser with validation
- [x] Temporal operators implementation
- [x] In-memory evaluator (batch mode)
- [x] OMOP CDM data adapter (SQL)
- [x] FHIR R4 data adapter (REST)

### Validation
- [x] 424 unit and integration tests (all passing)
- [x] SQL equivalence proof (100% match)
- [x] Clinical validation against KDIGO guidelines
- [x] Real data validation (Synthea synthetic, MIMIC-IV real)
- [x] Multi-server FHIR integration (HAPI, Firely, etc.)

### Documentation
- [x] Whitepaper in 5 languages (EN, ZH, ES, FR, JA)
- [x] Getting started guide
- [x] Example scenarios (AKI, ICU Deterioration, Sepsis)

---

## Phase 2: v0.3 Architecture ✅ Complete

**Goal**: Clean separation of concerns with Signal → Trend → Logic → Output model.

### Specification (RFC-0005) ✅
- [x] Trend/Logic separation (trends = numeric only, logic = comparisons)
- [x] `ref` field for signals (replaces `source`)
- [x] `when` field for logic (replaces `expr`)
- [x] Output schema definition (Decision/Feature/Evidence categories)
- [x] State machine specification
- [x] Audit block as required field

### Reference Implementation ✅
- [x] Parser updated to v0.3 strict mode
- [x] IR types for Output definitions
- [x] All bundled scenarios migrated to v0.3 format
- [x] EvaluationResult with standard output format

### Packaging ✅
- [x] PyPI publication (`pip install psdl-lang`)
- [x] CLI tool for scenario validation
- [x] Bundled scenarios accessible via `get_scenario()`

---

## Phase 3: Production Readiness 🚧 Current

**Goal**: Production-ready features for real-world deployment.

### Specification Work

#### Output Profiles (Pending)
- [ ] Define profile schema (cohort, ml_features, audit)
- [ ] Profile selection semantics
- [ ] Default profile behavior

#### Dataset Specification (RFC-0004) ✅
> **Status**: Implemented. Portable binding layer for mapping semantic references to physical data locations.
- [x] Dataset Spec schema (`spec/dataset_schema.json`)
- [x] Element binding format with filters (concept_id, source_value, custom)
- [x] Valueset handling (inline codes, file references with SHA-256)
- [x] Unit strategy (strict, allow_declare, backend_specific)
- [x] DatasetSpec loader with mandatory runtime validation
- [x] OMOP adapter integration

### Reference Implementation Work

#### Compilation & Audit (RFC-0006) ✅
- [x] ScenarioIR with DAG-ordered evaluation
- [x] compile_scenario() entry point
- [x] Canonical hashing (spec_hash, ir_hash, toolchain_hash)
- [x] CompilationDiagnostics (unused signal/trend detection)
- [x] SinglePatientEvaluator.from_ir() integration

#### Streaming Support (Architecture Complete, Full Implementation Pending)
> **Note**: Streaming is a runtime concern (HOW), not specification (WHAT). The architecture is defined; full production implementation is optional.
- [x] Streaming models and operators defined
- [x] PyFlink integration (optional dependency)
- [ ] Event-time watermarks
- [ ] Late data handling
- [ ] Production-ready state management

#### Vendor-Neutral Foundation (RFC-0008) ✅
- [x] ClinicalDomain enum (semantic domain names)
- [x] FilterPredicate / FilterPredicateSet (structured filters)
- [x] DataBackend lifecycle and capabilities protocol
- [x] BatchRuntime / SQLBatchRuntime abstractions
- [x] SQL templates extracted to dialect-specific files
- [x] concept_id deprecated from signals and examples

#### Query Generation
- [x] Basic SQL generation (CohortCompiler)
- [ ] Query optimization for large datasets
- [ ] Explain/debug mode

#### Performance (Implementation Concern)
- [ ] Benchmarking suite
- [ ] Memory optimization
- [ ] Parallel evaluation

#### Deployment
- [ ] Docker images
- [ ] Kubernetes deployment guide

---

## Phase 4: Adoption & Scale 🔮 Future

**Goal**: Drive real-world clinical adoption.

### Hospital Pilots
- [ ] Partner with 2-3 health systems
- [ ] Gather feedback on real-world usage
- [ ] Document deployment patterns

### Standards Engagement
- [ ] OHDSI working group collaboration
- [ ] HL7 FHIR Clinical Reasoning alignment
- [ ] Potential Arden Syntax convergence

### Community
- [ ] Technical blog series
- [ ] Conference presentations (OHDSI, AMIA, HL7)
- [ ] VS Code extension
- [ ] Scenario library/registry

### Enterprise Features
- [ ] Multi-tenant scenario management
- [ ] Role-based access control

---

## Design Boundaries

> See [BOUNDARIES.md](./BOUNDARIES.md) and [PRINCIPLES.md](../PRINCIPLES.md)

When planning features, always ask:

| Question | If YES | If NO |
|----------|--------|-------|
| Does this define WHAT to detect? | Core PSDL spec | Not spec |
| Does this define HOW to execute? | Reference implementation | Not spec |
| Does this define workflow/actions? | Out of scope | ✓ Correct |

**Examples:**
- Output profiles → **Spec** (defines WHAT output structure)
- Flink watermarks → **Implementation** (defines HOW to handle time)
- Alert routing → **Out of scope** (workflow concern)

---

## RFCs

| RFC | Title | Status | Phase |
|-----|-------|--------|-------|
| [RFC-0001](../rfcs/0001-ai-model-integration.md) | AI/ML Integration | ❌ Withdrawn | - |
| [RFC-0002](../rfcs/0002-streaming-execution.md) | Streaming Execution | ✅ Architecture | 3 |
| [RFC-0003](../rfcs/0003-architecture-refactor.md) | Architecture Refactor | ✅ Implemented | 2 |
| [RFC-0004](../rfcs/0004-dataset-specification.md) | Dataset Specification | ✅ Implemented | 3 |
| [RFC-0005](../rfcs/0005-psdl-v03-architecture.md) | PSDL v0.3 Architecture | ✅ Implemented | 2 |
| [RFC-0006](../rfcs/0006-spec-driven-compilation.md) | Spec-Driven Compilation | ✅ Implemented | 3 |
| [RFC-0007](../rfcs/0007-extension-mechanism.md) | Extension Mechanism | 📋 Draft | Future |
| [RFC-0008](../rfcs/0008-vendor-neutral-foundation.md) | Vendor-Neutral Foundation | ✅ Implemented | 3 |

---

## Whitepaper Versioning

### Version History

| Version | Date | Changes |
|---------|------|---------|
| **0.3.0** | Dec 2025 | v0.3 Architecture, Signal/Trend/Logic/Output separation |
| **0.2.0** | Dec 2025 | Clinical Accountability, State Machine, Dataset Spec draft |
| **0.1.0** | Dec 2025 | Initial release |

### Translation Status

| Language | Version | Status |
|----------|---------|--------|
| English (EN) | 0.3.0 | ✅ Current |
| 简体中文 (ZH) | 0.1.0 | ⚠️ Needs Update (2 versions behind) |
| Español (ES) | 0.1.0 | ⚠️ Needs Update (2 versions behind) |
| Français (FR) | 0.1.0 | ⚠️ Needs Update (2 versions behind) |
| 日本語 (JA) | 0.1.0 | ⚠️ Needs Update (2 versions behind) |

---

## Timeline

> Note: Timelines are indicative and depend on community contributions.

| Phase | Status |
|-------|--------|
| Phase 1: Semantic Foundation | ✅ Complete (Dec 2025) |
| Phase 2: v0.3 Architecture | ✅ Complete (Dec 2025) |
| Phase 3: Production Readiness | 🚧 In Progress |
| Phase 4: Adoption & Scale | 🔮 Future |

---

*Last updated: March 7, 2026*
