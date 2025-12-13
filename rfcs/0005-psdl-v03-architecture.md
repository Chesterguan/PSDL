# RFC-0005: PSDL v0.3 Architecture

| Field | Value |
|-------|-------|
| RFC | 0005 |
| Title | PSDL v0.3 Architecture - Signal/Trend/Logic/Output Separation |
| Author | PSDL Team |
| Status | Implemented |
| Priority | HIGH |
| Created | 2025-12-12 |

---

## Summary

Major architectural refactor that establishes clean separation between data layers (Signal → Trend → Logic → Output) and defines PSDL's boundaries with external systems. This is a **breaking change** from v0.2.x.

---

## Motivation

### Current Problems (v0.2.x)

1. **Mixed Concerns in Trends**: Trends can contain both numeric computations AND boolean comparisons
   ```yaml
   # v0.2 allows this (problematic)
   trends:
     cr_rise_48h: delta(Cr, 48h) >= 0.3  # Value + comparison mixed
   ```

2. **No Standardized Output**: Different runtimes return different output formats

3. **Unclear Boundaries**: No clear definition of what belongs in PSDL vs external systems (Workflow, ML, etc.)

### Goals

1. **Clean Layer Separation**: Each layer has ONE responsibility
2. **Standardized Output**: Consistent interface across all runtimes
3. **Clear Boundaries**: Explicit scope of PSDL vs external systems
4. **ML-Friendly**: Easy to extract features for ML pipelines
5. **Audit-Ready**: Evidence trail built into output

---

## Design

### 1. Core Positioning

> **PSDL = Portable, auditable specification for clinical detection logic**

**PSDL IS:**
- Definition of WHAT to detect (clinical intent)
- Human-readable, machine-executable
- Auditable (WHO/WHY/WHAT)
- Deterministic and reproducible

**PSDL IS NOT:**
- A workflow engine (what to do after detection)
- An ML platform (model training/execution)
- A data pipeline (data collection/storage)
- An alerting system (notification delivery)

---

### 2. Four-Layer Data Model

```
┌─────────────────────────────────────────────────┐
│  SIGNAL (Raw Data)                              │
│  - Type: Time series                            │
│  - Source: Data binding                         │
│  - Example: Cr, HR, BP                          │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  TREND (Derived Value)                          │
│  - Type: float, int, timestamp                  │
│  - Computation: Temporal aggregation            │
│  - Example: delta(Cr, 48h) → 0.35               │
│  - ⚠️ NO BOOLEAN - values only!                │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  LOGIC (Predicate)                              │
│  - Type: boolean                                │
│  - Computation: Comparison + combination        │
│  - Example: cr_delta >= 0.3 → true              │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  OUTPUT (Public Interface)                      │
│  - Decision: boolean judgments                  │
│  - Feature: numeric values for ML               │
│  - Evidence: audit trail                        │
└─────────────────────────────────────────────────┘
```

#### Key Principle

> **Boolean comparisons NEVER appear in Trends. They belong in Logic.**

---

### 3. Syntax Changes (Breaking)

#### Before (v0.2.x)

```yaml
signals:
  Cr:
    source: creatinine
    concept_id: 3016723

trends:
  cr_rise_48h:
    expr: delta(Cr, 48h) >= 0.3    # ❌ Mixed value + comparison
    description: "Creatinine rise"

logic:
  aki_stage1:
    expr: cr_rise_48h              # References trend (boolean)
```

#### After (v0.3.0)

```yaml
signals:
  Cr:
    ref: creatinine
    unit: mg/dL

trends:
  cr_delta_48h:
    type: float                    # ✅ Explicit type
    unit: mg/dL
    expr: delta(Cr, 48h)           # ✅ Value only, no comparison

logic:
  aki_by_delta:
    when: cr_delta_48h >= 0.3      # ✅ Comparison in logic
    severity: medium

outputs:
  decision:
    in_cohort:
      type: boolean
      from: logic.aki_by_delta
  features:
    cr_delta_48h:
      type: float
      from: trends.cr_delta_48h
```

---

### 4. Output Schema

Output is the **boundary** between PSDL and external systems.

#### Three Categories

| Category | Purpose | Example |
|----------|---------|---------|
| **Decision** | Boolean judgments | `in_cohort`, `aki_stage` |
| **Feature** | Numeric values for ML/stats | `cr_delta_48h`, `hr_slope` |
| **Evidence** | Audit trail | `index_time`, `matched_rules` |

#### Schema Definition

```yaml
outputs:
  # Decision outputs (boolean judgments)
  decision:
    in_cohort:
      type: boolean
      from: logic.aki_stage1
    aki_stage:
      type: enum
      values: [none, stage1, stage2, stage3]
      from: state.current

  # Feature outputs (numeric values for ML)
  features:
    cr_delta_48h:
      type: float
      unit: mg/dL
      from: trends.cr_delta_48h
    cr_ratio:
      type: float
      expr: last(Cr) / cr_baseline

  # Evidence outputs (audit trail)
  evidence:
    index_time:
      type: timestamp
      expr: first_time(in_cohort == true)
    evidence_window:
      type: interval
      expr: window(index_time - 48h, index_time)
    matched_rules:
      type: string[]
      expr: rules_fired()
```

#### Minimal Output (Core)

At minimum, all runtimes MUST return:

```json
{
  "patient_id": "P12345",
  "triggered": true
}
```

Additional fields are optional extensions.

---

### 5. Output Profiles (Runtime Concept)

Profiles select output subsets at runtime, without changing scenario semantics.

```bash
# Minimal output
$ psdl run aki.yaml --profile=cohort
# Returns: patient_id, triggered, index_time

# ML features
$ psdl run aki.yaml --profile=ml_features
# Returns: patient_id, triggered, all feature columns

# Full audit
$ psdl run aki.yaml --profile=audit
# Returns: patient_id, triggered, all evidence fields
```

**Principle**: Profiles select, they don't transform.

---

### 6. State Machine (Retained)

State Machine remains in PSDL because:
- It's part of detection logic (tracking clinical progression)
- No side effects (pure state tracking)
- Auditable (state transitions are logged)

```yaml
state:
  initial: normal
  states: [normal, stage1, stage2, stage3]
  transitions:
    - from: normal
      to: stage1
      when: aki_stage1    # References logic
    - from: stage1
      to: stage2
      when: aki_stage2
```

---

### 7. Triggers/Actions (NOT in PSDL)

**Triggers and Actions are explicitly OUT OF SCOPE.**

Reason: Adding them would turn PSDL into a workflow engine, losing:
- Auditability (actions have side effects)
- Portability (actions are infrastructure-specific)
- Simplicity (workflow logic is complex)

```
PSDL Boundary:
  Input → Detection Logic → Output (EvaluationResult)
                               ↓
                    [Workflow System consumes output]
                               ↓
                    [Workflow decides actions]
```

---

### 8. ML Integration Strategy

**ML is not a special concept in PSDL.**

#### Option A: ML Output as Signal (Upstream)

```yaml
# ML model outputs to database, PSDL reads as signal
signals:
  sepsis_risk:
    ref: ml_sepsis_score    # Just another signal
    unit: probability
```

#### Option B: PSDL Output as ML Input (Downstream)

```yaml
# PSDL exports features for ML consumption
outputs:
  features:
    cr_delta_48h: ...
    hr_slope_6h: ...
    # ML pipeline reads these
```

**Principle**: PSDL doesn't execute ML. It consumes or produces data.

---

### 9. Runtime Interface

All runtimes MUST implement this interface:

```python
class PSDLRuntime(ABC):
    @abstractmethod
    def evaluate(
        self,
        scenario: ParsedScenario,
        patient_id: str,
        reference_time: datetime,
    ) -> EvaluationResult:
        """Evaluate scenario for a single patient."""
        pass

@dataclass
class EvaluationResult:
    # Core (required)
    patient_id: str
    triggered: bool

    # Decision (optional)
    triggered_logic: List[str] = field(default_factory=list)
    current_state: Optional[str] = None

    # Features (optional)
    trend_values: Dict[str, float] = field(default_factory=dict)

    # Evidence (optional)
    logic_results: Dict[str, bool] = field(default_factory=dict)
    index_time: Optional[datetime] = None
```

---

## Migration Path

| Version | Status | Description |
|---------|--------|-------------|
| v0.2.x | Current | Trends can have comparisons |
| v0.3.0 | This RFC | Breaking change: trends = numeric only |

### Migration Steps

1. **Identify trends with comparisons**
   ```bash
   grep -r ">=" scenarios/ | grep "trends:"
   ```

2. **Split into trend + logic**
   ```yaml
   # Before
   trends:
     cr_rise: delta(Cr, 48h) >= 0.3

   # After
   trends:
     cr_delta:
       type: float
       expr: delta(Cr, 48h)
   logic:
     cr_rise:
       when: cr_delta >= 0.3
   ```

3. **Add explicit types**

4. **Add outputs section**

---

## Files to Update

| File | Change |
|------|--------|
| `spec/schema.json` | New schema with separated layers |
| `src/psdl/core/ir.py` | New IR types for Trend, Output |
| `src/psdl/core/parser.py` | Parse new format |
| `src/psdl/runtimes/single/evaluator.py` | Return standardized output |
| `examples/*.yaml` | Migrate to new format |
| `tests/` | Update test cases |

---

## Backward Compatibility

This is a **breaking change**. As an early-stage project (pre-1.0), we prioritize clean architecture over backward compatibility.

**v0.3 Strict Mode (Default)**:
- Parser only accepts v0.3 syntax
- `ref` required (v0.2 `source` no longer accepted)
- `when` required in logic (v0.2 `expr` no longer accepted)
- Trends must be numeric only (comparisons belong in logic)

**Migration**: All example scenarios have been migrated to v0.3 format. Migration tooling will be considered for v1.0.

---

## Alternatives Considered

### 1. Keep Trends as-is, Add Separate "Computations"

**Rejected**: Adds complexity without solving the mixed-type problem.

### 2. Make Output Optional

**Rejected**: Standardized output is essential for ecosystem interoperability.

### 3. Add Triggers in PSDL with "declarative actions"

**Rejected**: Even declarative actions blur the boundary between detection and workflow.

---

## References

- [RFC-0003: Architecture Refactor](./0003-architecture-refactor.md)
- [RFC-0004: Dataset Specification](./0004-dataset-specification.md)
- [TempoQL Paper](https://arxiv.org/abs/2511.09337) - Inspiration for clean layer separation
- [Kubernetes Design Principles](https://kubernetes.io/docs/concepts/overview/) - Minimal core, clear interfaces

---

## Appendix: Complete Example

```yaml
# PSDL v0.3 Scenario Example
scenario: AKI_KDIGO_Detection
version: "0.3.0"

audit:
  intent: "Detect and stage Acute Kidney Injury using KDIGO criteria"
  rationale: "Early AKI detection enables timely intervention"
  provenance: "KDIGO Clinical Practice Guideline for AKI (2012)"

signals:
  Cr:
    ref: creatinine
    unit: mg/dL

trends:
  cr_delta_48h:
    type: float
    unit: mg/dL
    expr: delta(Cr, 48h)
    description: "Absolute creatinine change over 48 hours"

  cr_baseline:
    type: float
    unit: mg/dL
    expr: min(Cr, 7d)
    description: "Baseline creatinine (7-day minimum)"

  cr_ratio:
    type: float
    expr: last(Cr) / cr_baseline
    description: "Current/baseline creatinine ratio"

logic:
  aki_by_delta:
    when: cr_delta_48h >= 0.3
    severity: medium
    description: "AKI by absolute rise criterion"

  aki_by_ratio:
    when: cr_ratio >= 1.5
    severity: medium
    description: "AKI by ratio criterion"

  aki_stage1:
    when: aki_by_delta OR aki_by_ratio
    severity: medium

  aki_stage2:
    when: cr_ratio >= 2.0
    severity: high

  aki_stage3:
    when: cr_ratio >= 3.0 OR last(Cr) >= 4.0
    severity: critical

state:
  initial: normal
  states: [normal, stage1, stage2, stage3]
  transitions:
    - from: normal
      to: stage1
      when: aki_stage1
    - from: stage1
      to: stage2
      when: aki_stage2
    - from: stage2
      to: stage3
      when: aki_stage3
    - from: stage1
      to: normal
      when: NOT aki_stage1

outputs:
  decision:
    in_cohort:
      type: boolean
      from: logic.aki_stage1
    aki_stage:
      type: enum
      values: [none, stage1, stage2, stage3]
      from: state.current

  features:
    cr_delta_48h:
      type: float
      from: trends.cr_delta_48h
    cr_ratio:
      type: float
      from: trends.cr_ratio
    cr_baseline:
      type: float
      from: trends.cr_baseline

  evidence:
    index_time:
      type: timestamp
      expr: first_time(aki_stage1 == true)
    matched_rules:
      type: string[]
      expr: rules_fired()
```
