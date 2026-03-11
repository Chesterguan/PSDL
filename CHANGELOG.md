# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-03-11

### Added

#### RFC-0008: Vendor-Neutral Foundation
- **ClinicalDomain enum**: Vendor-neutral replacement for OMOP-specific `Domain` enum (LABORATORY, VITAL_SIGN, CONDITION, MEDICATION, PROCEDURE, DEMOGRAPHIC, SCORING, OTHER)
- **FilterPredicate / FilterPredicateSet**: Structured, vendor-neutral filter types replacing raw SQL strings
- **DataBackend ABC**: Enhanced with `connect()/close()/__enter__/__exit__/capabilities`
- **BatchRuntime / SQLBatchRuntime**: Abstract base classes for vendor-neutral batch execution
- **CohortCompiler → SQLBatchRuntime**: Inherits runtime ABC, `compile()` accepts `dataset_spec` override
- **OMOPBackend → BatchRuntime**: Inherits runtime ABC with `compile()` and `execute()` methods
- **ClinicalEvent.source_ids**: Vendor-neutral metadata dict for streaming events
- **Signal.clinical_domain**: New field set via `ClinicalDomain.from_legacy(domain)`
- **Dataset Spec resolve()**: `load_dataset_spec()` returns structured `FilterPredicateSet` bindings

#### Testing
- Added 115 vendor-neutral tests (test_vendor_neutral.py)
- Total test count: 539 tests (all passing)

### Changed
- OMOPBackend capabilities: `{"dataset_adapter"}` → `{"dataset_adapter", "sql"}`
- CohortCompiler `_resolve_signal_binding()` uses `dataset_spec.resolve()` when available
- SQL templates extracted to `runtimes/cohort/postgresql_templates.yaml`

### Deprecated
- `Signal.concept_id` — use Dataset Spec bindings instead (removal in v0.5.0)
- `Domain` enum — use `ClinicalDomain` instead (removal in v0.5.0)
- `DatasetAdapter` protocol — use `DataBackend` ABC instead
- `ClinicalEvent.concept_id` / `fhir_resource_id` — use `source_ids` dict instead
- `execution/sql_compiler.py` — use `runtimes/cohort/` instead
- `execution/batch.py` — use `runtimes/batch.py` instead

## [0.3.2] - 2026-03-07

### Added

#### RFC-0004: Dataset Specification
- **DatasetSpec loader**: `load_dataset_spec()` with JSON Schema validation
- **Dataset Schema**: `spec/dataset_schema.json` for spec validation
- **OMOP CDM v5.4 bindings**: `dataset_specs/omop_cdm_v54.yaml` standard mapping
- **Element resolution**: `spec.resolve("creatinine")` returns physical binding

#### RFC-0007: Extension Mechanism (Draft)
- Initial RFC draft for PSDL extension mechanism

### Changed
- Import ordering fixed in `__init__.py`

## [0.3.1] - 2026-03-05

### Added

#### RFC-0006: Spec-Driven Compilation
- **ScenarioIR**: Compiled intermediate representation with pre-computed analysis
- **compile_scenario()**: Single entry point for production compilation
- **Canonical Hashing**: SHA-256 hashes for audit trails (`spec_hash`, `ir_hash`, `toolchain_hash`)
- **DAG Ordering**: Dependency-based evaluation order computed at compile time
- **CompilationDiagnostics**: Warnings for unused signals/trends, type analysis
- **SinglePatientEvaluator.from_ir()**: Create evaluator from compiled IR
- **spec/hashing.yaml**: Canonical hashing specification

#### Documentation
- API reference (`wiki/API.md`)
- Updated notebooks to v0.3 syntax (MIMIC, Synthea, PhysioNet demos)

#### Testing
- Added 54 compiler tests (test_compile.py)
- Total test count: 424 tests (all passing)

### Fixed
- flake8 lint errors resolved

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
| 0.4.0 | 2026-03-11 | Vendor-Neutral Foundation (RFC-0008) |
| 0.3.2 | 2026-03-07 | Dataset Specification (RFC-0004) |
| 0.3.1 | 2026-03-05 | Spec-Driven Compilation (RFC-0006) |
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
