# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### RFC-0006: Spec-Driven Compilation
- **ScenarioIR**: Compiled intermediate representation with pre-computed analysis
- **compile_scenario()**: Single entry point for production compilation
- **Canonical Hashing**: SHA-256 hashes for audit trails (`spec_hash`, `ir_hash`, `toolchain_hash`)
- **DAG Ordering**: Dependency-based evaluation order computed at compile time
- **CompilationDiagnostics**: Warnings for unused signals/trends, type analysis
- **SinglePatientEvaluator.from_ir()**: Create evaluator from compiled IR
- **spec/hashing.yaml**: Canonical hashing specification

#### Testing
- Added 54 compiler tests (test_compile.py)
- Total test count: 424 tests (all passing)

#### Documentation
- Updated notebooks to v0.3 syntax (MIMIC, Synthea, PhysioNet demos)
- Added compile_scenario usage to README
- Updated GLOSSARY.md with ScenarioIR documentation

## [0.3.0] - 2025-12-12

### Added

#### v0.3 Architecture (RFC-0005)
- **Signal/Trend/Logic/Output Separation**: Clean four-layer data model
- **Trends Produce Numeric Values Only**: Comparisons now belong in Logic layer
- **`ref` Field for Signals**: Replaces v0.2 `source` field
- **`when` Field for Logic**: Replaces v0.2 `expr` field
- **Output Schema**: Three categories - Decision, Features, Evidence
- **Bundled Scenarios**: 7 clinical scenarios included with `pip install psdl-lang`
- **Canonical Imports**: `from psdl.core import parse_scenario`, `from psdl.examples import get_scenario`

#### Packaging
- **PyPI Publication**: `pip install psdl-lang`
- **Optional Dependencies**: `[omop]`, `[fhir]`, `[full]` extras

#### Infrastructure
- **Reorganized Examples**: `examples/notebooks/` for Colab demos, `examples/data/` for sample data
- **RFC-0003 Architecture**: Refactored to `src/psdl/` layout with runtimes, adapters, examples modules

### Changed
- **BREAKING**: Trends no longer accept comparison operators (use Logic layer)
- **BREAKING**: Signal `source:` renamed to `ref:`
- **BREAKING**: Logic `expr:` renamed to `when:`
- Removed triggers/actions from scope (workflow systems consume PSDL output)
- Updated all documentation to v0.3 syntax
- Spec badge: 0.2.0 → 0.3.0

### Removed
- Triggers/actions system (moved to workflow layer per BOUNDARIES.md)

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
- Mapping layer for concept portability (planned)

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.3.0 | 2025-12-12 | v0.3 Architecture, PyPI publication, RFC-0005 |
| 0.2.0 | 2025-12-12 | Clinical Accountability, State Machine, Dataset Spec |
| 0.1.0 | 2025-12-05 | Initial release - Semantic Foundation |

---

## Upcoming

### v1.0.0 (Planned)
- Production-ready specification
- Full conformance test suite
- Hospital pilot validation

### Future
- Multi-language support (TypeScript, Rust)
- Language-agnostic conformance test suite
- WebAssembly compilation
