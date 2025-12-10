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

### AI Integration (RFC-0001)
- [ ] Model deployment bridge specification
- [ ] `predict()`, `forecast()` operators
- [ ] ONNX model integration
- [ ] Timeout and fallback handling

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
| **0.1.0** | Dec 2025 | Initial release — Core specification, batch execution |
| **0.1.1** | Dec 2025 | Added "Scope and Limitations" section (WHAT vs HOW) |

### Planned Whitepaper Updates

| Version | Target | Content |
|---------|--------|---------|
| **0.2.0** | Phase 2 | Streaming execution, Triggers & Actions |
| **0.3.0** | Phase 3 | AI/ML integration (RFC-0001) |
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
| English (EN) | 0.1.1 | Current |
| 简体中文 (ZH) | 0.1.1 | Current |
| Español (ES) | 0.1.1 | Current |
| Français (FR) | 0.1.1 | Current |
| 日本語 (JA) | 0.1.1 | Current |

---

## RFCs

Major features are proposed through RFCs:

| RFC | Title | Status |
|-----|-------|--------|
| [RFC-0001](../rfcs/0001-ai-integration.md) | AI/LLM Integration | Draft |
| [RFC-0002](../rfcs/0002-streaming.md) | Streaming Execution | Phase 1 Complete |

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

*Last updated: December 2025*
