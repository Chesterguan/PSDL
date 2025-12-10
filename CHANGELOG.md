# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Test suite cleanup: 234 tests now all passing (removed external dependency tests)
- Code quality improvements: fixed all flake8 linting errors
- Code formatting: applied black and isort to entire codebase
- Documentation updates: synchronized test counts across all docs

### Fixed
- Unused imports in test fixtures and streaming tests
- F-string syntax issues in test fixtures
- TYPE_CHECKING guard for MappingProvider in OMOP adapter
- Line length issues in test files

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
| 0.1.0 | 2025-12-05 | Initial release - Semantic Foundation |

---

## Upcoming

### v0.2.0 (Planned)
- Triggers and Actions system
- Conformance test suite
- Python package (pip install psdl)

### v0.3.0 (Planned)
- Mapping layer for portability
- Performance optimizations
- Additional temporal operators
