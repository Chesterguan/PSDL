# RFC-0007: PSDL Extension Mechanism

| Field | Value |
|-------|-------|
| RFC | 0007 |
| Title | Extension Mechanism for PSDL |
| Author | PSDL Team |
| Status | DRAFT - Not Started |
| Priority | LOW |
| Created | 2025-12-17 |

---

## Summary

Define an extension mechanism that allows PSDL to remain minimal at its core while supporting optional capabilities (events, sequences, ML integration, etc.) through extensions.

---

## Motivation

### Current Limitation

PSDL Core handles numeric time-series well (labs, vitals), but real clinical scenarios often require:

- **Event data**: Drug exposures, procedures, admissions
- **Event sequences**: "A happened, then B within 7 days, then C within 48 hours"
- **Custom operators**: Domain-specific computations
- **ML integration**: Model outputs as signals

### The Dilemma

Adding everything to core makes PSDL complex. Not adding anything limits usefulness.

### Inspiration: Kubernetes

Kubernetes solved this with:
- Minimal core (Pod, Service, Deployment)
- Extension mechanism (CRDs, Operators)
- Ecosystem fills gaps (Prometheus, Istio, etc.)

---

## Proposed Design

### Core vs Extensions

```
PSDL Core (stable, minimal):
├── Signal (numeric time-series)
├── Trend (delta, slope, ema, sma, min, max, last, count)
├── Logic (AND, OR, NOT, comparisons)
└── Output (decision, features, evidence)

Extensions (optional, pluggable):
├── psdl-events (event signals, time_since, has_event)
├── psdl-sequences (event patterns, A -> B -> C)
├── psdl-ml (model outputs, feature engineering)
└── community extensions...
```

### Syntax (Tentative)

```yaml
psdl_version: "0.3"
extensions:
  - psdl-events@1.0

signals:
  WBC:
    ref: wbc
    unit: "10^9/L"

  Antibiotic:
    ref: broad_spectrum_abx
    kind: event              # Provided by psdl-events

trends:
  wbc_current:
    expr: last(WBC)

  hours_since_abx:
    expr: time_since(Antibiotic)  # Provided by psdl-events

logic:
  leukopenia_post_abx:
    when: wbc_current < 4.0 AND hours_since_abx <= 168
```

### Extension Interface (Tentative)

```python
class PSDLExtension(ABC):
    """Interface for PSDL extensions."""

    @property
    def name(self) -> str:
        """Extension name (e.g., 'psdl-events')."""
        ...

    @property
    def version(self) -> str:
        """Extension version."""
        ...

    @property
    def signal_kinds(self) -> List[str]:
        """New signal kinds provided (e.g., ['event'])."""
        ...

    @property
    def operators(self) -> Dict[str, OperatorSpec]:
        """New operators provided (e.g., {'time_since': ...})."""
        ...

    def validate(self, scenario: PSDLScenario) -> List[str]:
        """Validate extension-specific syntax."""
        ...
```

---

## Potential Extensions

| Extension | Provides | Use Case |
|-----------|----------|----------|
| `psdl-events` | `kind: event`, `time_since()`, `has_event()`, `count_events()` | Drug exposures, procedures |
| `psdl-sequences` | `sequences:` block, pattern matching | Complex temporal patterns |
| `psdl-ml` | ML model outputs as signals | AI integration |
| `psdl-fhir` | FHIR-native signal types | FHIR-first environments |

---

## Open Questions

1. **Discovery**: How do users find available extensions?
2. **Compatibility**: How to handle extension version conflicts?
3. **Validation**: How to validate scenarios with unknown extensions?
4. **Packaging**: PyPI packages? Single repo? Extension registry?

---

## Implementation Plan

Not started. Waiting for:

1. Community feedback on core PSDL (OHDSI, PhysioNet)
2. Real user requests for event/sequence support
3. Design partner with concrete use case

---

## References

- Kubernetes CRD: https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/
- GraphQL Directives: https://graphql.org/learn/queries/#directives
- OHDSI ATLAS Cohort Definitions (alternative approach)

---

## Status Log

| Date | Status | Notes |
|------|--------|-------|
| 2025-12-17 | DRAFT | Initial idea recorded, not started |

---

*This RFC is a placeholder to record the extension mechanism idea. Implementation will be considered after validating core PSDL with the community.*
