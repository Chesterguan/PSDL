# PSDL Roadmap

> The path from specification to clinical adoption

---

## Overview

PSDL development follows a phased approach, building from a solid semantic foundation toward real-world clinical deployment.

```
Phase 1          Phase 2           Phase 3          Phase 4
Semantic    →    Enhanced     →    Community   →    Adoption
Foundation       Runtime           Growth           & Scale
[Complete]       [Current]         [Planned]        [Future]
```

---

## Phase 1: Semantic Foundation ✅ Complete

**Goal**: Establish the core language specification and prove correctness.

### Specification
- [x] Type system definition (Signals, Trends, Logic, Population)
- [x] Operator semantics (delta, slope, ema, sma, min, max, count, last)
- [x] YAML schema (`spec/schema-v0.1.yaml`)
- [x] Window format specification (s, m, h, d)

### Reference Implementation
- [x] Python parser with validation
- [x] Temporal operators implementation
- [x] In-memory evaluator (batch mode)
- [x] OMOP CDM data adapter (SQL)
- [x] FHIR R4 data adapter (REST)

### Validation
- [x] 234 unit and integration tests (all passing)
- [x] SQL equivalence proof (100% match)
- [x] Clinical validation against KDIGO guidelines
- [x] Real data validation (Synthea synthetic, MIMIC-IV real)
- [x] Multi-server FHIR integration (HAPI, Firely, etc.)

### Documentation
- [x] Whitepaper in 5 languages (EN, ZH, ES, FR, JA)
- [x] Getting started guide
- [x] Example scenarios (AKI, ICU Deterioration, Sepsis)

---

## Phase 2: Enhanced Runtime 🚧 In Progress

**Goal**: Enable real-time execution and production-ready features.

### v0.3 Architecture (RFC-0005) ✅ Complete
- [x] Trend/Logic separation schema and IR types
- [x] Output schema (Decision/Feature/Evidence categories)
- [x] Strict mode parser (v0.2 syntax no longer accepted)
- [x] Output section parsing in parser
- [x] Evaluator returns EvaluationResult (via to_standard_result())
- [x] All example scenarios migrated to v0.3 format
- [ ] Output profiles (cohort, ml_features, audit)

### Streaming Execution (RFC-0002)
- [x] Streaming adapter architecture (Phase 1 backend complete)
- [ ] Apache Flink integration
- [ ] Event-time watermarks
- [ ] Late data handling
- [ ] State management for temporal operators

### Query Generation
- [ ] SQL query generation from PSDL scenarios
- [ ] Query optimization for large datasets
- [ ] Explain/debug mode for generated queries

### Triggers & Actions (v0.2)
- [ ] Event-condition-action rule syntax
- [ ] Action types (notify, log, order_suggestion)
- [ ] Trigger chaining and dependencies
- [ ] Cooldown and rate limiting

### Performance
- [ ] Benchmarking suite
- [ ] Memory optimization for large patient cohorts
- [ ] Parallel evaluation support

### Packaging
- [ ] Python package (`pip install psdl`)
- [ ] CLI tool for scenario validation
- [ ] Docker images for quick start

---

## Phase 3: Community Growth 📋 Planned

**Goal**: Build an active community and ecosystem.

### Content & Outreach
- [ ] Technical blog series
  - Introduction to PSDL
  - Deep dive: Temporal operators
  - PSDL vs CQL comparison
  - Real-world case studies
- [ ] Conference presentations (OHDSI, AMIA, HL7)
- [ ] Video tutorials and demos

### Community Infrastructure
- [ ] Discussion forum / Discord
- [ ] Regular community calls
- [ ] Contributor recognition program
- [ ] Scenario library / registry

### Ecosystem
- [ ] VS Code extension (syntax highlighting, validation)
- [ ] Jupyter notebook integration
- [ ] Additional language implementations (Java, TypeScript)

---

## Phase 4: Adoption & Scale 🔮 Future

**Goal**: Drive real-world clinical adoption.

### Hospital Pilots
- [ ] Partner with 2-3 health systems for pilot implementations
- [ ] Gather feedback on real-world usage
- [ ] Document deployment patterns and best practices

### Standards Engagement
- [ ] OHDSI working group collaboration
- [ ] HL7 FHIR Clinical Reasoning alignment
- [ ] Potential Arden Syntax convergence discussions

### AI/ML Integration
> **Note**: RFC-0001 was withdrawn. ML model outputs are now treated as regular signals via Dataset Spec bindings, consistent with PSDL's "WHAT not HOW" philosophy.

- [ ] ML output as signal binding (via Dataset Spec)
- [ ] Model registry integration patterns
- [ ] Sample configurations for common ML frameworks

### Enterprise Features
- [ ] Multi-tenant scenario management
- [ ] Audit logging and compliance reporting
- [ ] Role-based access control for scenarios

---

## How to Contribute

Each phase has opportunities for contribution:

| Phase | Contribution Areas |
|-------|-------------------|
| **Phase 1** | Bug fixes, documentation improvements, test coverage |
| **Phase 2** | Streaming implementation, SQL generation, packaging |
| **Phase 3** | Blog posts, tutorials, tooling, translations |
| **Phase 4** | Pilot feedback, standards work, enterprise features |

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

---

## Whitepaper Versioning

The whitepaper evolves with the specification. Major updates are versioned to maintain translation synchronization.

### Version History

| Version | Date | Changes |
|---------|------|---------|
| **0.2.0** | Dec 2025 | Clinical Accountability (audit block), State Machine, Dataset Spec (RFC-0004) |
| **0.1.1** | Dec 2025 | Added "Scope and Limitations" section (WHAT vs HOW) |
| **0.1.0** | Dec 2025 | Initial release — Core specification, batch execution |

### Planned Whitepaper Updates

| Version | Target | Content |
|---------|--------|---------|
| **0.2.0** | Phase 2 | ✅ Clinical Accountability, Dataset Spec, State Machine |
| **0.3.0** | Phase 2 | 🔴 RFC-0005: Signal/Trend/Logic/Output separation (BREAKING CHANGE) |
| **1.0.0** | Phase 4 | Production-ready specification |

### Translation Sync Policy

When the English whitepaper is updated:
1. Update `docs/WHITEPAPER.md` (index) with new translation status
2. All translations should be updated within 2 weeks
3. Mark translations as "Needs Update" if behind English version
4. Critical sections (Scope, Core Concepts) prioritized for sync

### Current Translation Status

| Language | Version | Status |
|----------|---------|--------|
| English (EN) | 0.2.0 | Current |
| 简体中文 (ZH) | 0.2.0 | Current |
| Español (ES) | 0.2.0 | Current |
| Français (FR) | 0.2.0 | Current |
| 日本語 (JA) | 0.2.0 | Current |

---

## RFCs

Major features are proposed through RFCs:

| RFC | Title | Status |
|-----|-------|--------|
| [RFC-0001](../rfcs/0001-ai-model-integration.md) | AI/ML Integration | ❌ Withdrawn |
| [RFC-0002](../rfcs/0002-streaming-execution.md) | Streaming Execution | ✅ Implemented |
| [RFC-0003](../rfcs/0003-architecture-refactor.md) | Architecture Refactor | ✅ Implemented |
| [RFC-0004](../rfcs/0004-dataset-specification.md) | Dataset Specification | Draft |
| [RFC-0005](../rfcs/0005-psdl-v03-architecture.md) | PSDL v0.3 Architecture | ✅ Implemented |

---

## Timeline

> Note: Timelines are indicative and depend on community contributions.

| Phase | Target |
|-------|--------|
| Phase 1 | ✅ Complete (Dec 2025) |
| Phase 2 | Q1-Q2 2026 |
| Phase 3 | Q3-Q4 2026 |
| Phase 4 | 2027+ |

---

*Last updated: December 12, 2025*
