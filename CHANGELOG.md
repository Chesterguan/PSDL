# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-12-12

### Added

#### Clinical Accountability (First-Citizen)
- **Mandatory Audit Block**: Every scenario now requires `audit:` with `intent`, `rationale`, and `provenance` fields
- **Traceability by Design**: WHO wrote this logic, WHY it matters, WHAT evidence supports it
- Updated JSON Schema to enforce audit block as required
- Added `AuditBlock` to IR types

#### State Machine (Optional)
- **Stateful Clinical Progression**: Track patient states over time (e.g., normal → elevated → critical)
- New `state:` block with `initial`, `states`, and `transitions` definitions
- Added `StateMachine` and `StateTransition` to IR types

#### Dataset Specification (RFC-0004)
- **Three-Layer Architecture**: Scenario (intent) → Dataset Spec (binding) → Adapter (execution)
- Declarative binding layer that maps semantic references to physical data locations
- Element bindings, encoding bindings, type declarations, time axis conventions
- Conservative valueset strategy: local static files only, versioned + SHA-256 hashed
- Full specification in `rfcs/0004-dataset-specification.md`

#### Documentation
- **Whitepaper v0.2**: Updated with accountability messaging across all languages
- **Hero Statement**: "Accountable Clinical AI — Traceable by Design"
- **GLOSSARY.md**: Added Audit Block, Clinical Accountability, State Machine, Dataset Spec
- **glossary.json**: Machine-readable terminology with `first_citizen` flags
- **PRINCIPLES.md**: Added "First-Citizen: Clinical Accountability" section with N8: Not a Query Language

#### Visual Assets
- `psdl-value-proposition.jpeg`: Before/After PSDL value comparison
- `psdl-problem-solution.jpeg`: Current state vs PSDL solution paths
- `psdl-core-constructs.jpeg`: PSDL core constructs diagram

### Changed
- Whitepaper version: 0.1 → 0.2
- README: Added accountability hero statement with WHO/WHY/WHAT table
- Removed redundant mermaid diagrams replaced by new images
- Test suite: 284 tests (all passing)
- Code quality: black, isort, flake8 compliant

### Fixed
- Unused imports in test fixtures and streaming tests
- F-string syntax issues in test fixtures
- TYPE_CHECKING guard for MappingProvider in OMOP adapter
- Line length issues in test files
- Documentation date inconsistencies (2024 → 2025)

## [0.1.0] - 2025-12-05

### Added
- **Specification**
  - YAML schema definition (v0.1)
  - Core type system: Signals, Trends, Logic
  - Temporal operators: delta, slope, ema, sma, min, max, count, last
  - Window specification format (s, m, h, d)
  - Severity levels: low, medium, high, critical

- **Python Reference Implementation**
  - YAML parser with schema validation
  - Expression parser for trends and logic
  - In-memory evaluator for testing
  - Temporal operator implementations

- **Examples**
  - ICU Deterioration Detection scenario
  - AKI (Acute Kidney Injury) Detection scenario
  - Sepsis Screening scenario

- **Documentation**
  - Whitepaper (EN, ZH, ES, FR, JA)
  - Getting Started guide
  - CONTRIBUTING guidelines
  - CODE_OF_CONDUCT

- **Testing**
  - Parser unit tests
  - Evaluator unit tests

### Known Limitations
- No triggers/actions system (planned for v0.2)
- Mapping layer for concept portability (planned)

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.2.0 | 2025-12-12 | Clinical Accountability, State Machine, Dataset Spec |
| 0.1.0 | 2025-12-05 | Initial release - Semantic Foundation |

---

## Upcoming

### v0.3.0 (Planned)
- Triggers and Actions system
- Audit bundle generation (manifest.json, normalized artifacts)
- Performance benchmarking suite

### v0.4.0 (Planned)
- Multi-language support (TypeScript, Rust)
- Language-agnostic conformance test suite
- WebAssembly compilation
