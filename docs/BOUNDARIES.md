# PSDL Design Boundaries (Q&A)

> Quick reference for architectural decisions. Review this when in doubt.
>
> Last Updated: December 12, 2025

---

## Q1: What should PSDL do?

**A**: Define clinical detection logic (WHAT to detect), output auditable detection results.

PSDL is:
- **Definition of clinical intent** - human-readable, machine-executable
- **Auditable** - WHO/WHY/WHAT are traceable
- **Deterministic** - same input always produces same output
- **Portable** - works across institutions and systems

---

## Q2: What should PSDL NOT do?

**A**:
- Workflow orchestration (what to do after detection)
- ML model execution (training, inference)
- Data collection/storage (ETL pipelines)
- Alert/notification delivery (messaging systems)
- Infrastructure concerns (scaling, deployment)

**Principle**: PSDL outputs a result. What happens next is someone else's job.

---

## Q3: Can Trends contain comparison operators?

**A**: **NO**. Trends produce numeric values only. Comparisons belong in Logic layer.

```yaml
# WRONG (v0.2 allowed this, v0.3 does not)
trends:
  cr_rise: delta(Cr, 48h) >= 0.3  # Mixed value + comparison

# CORRECT (v0.3)
trends:
  cr_delta:
    type: float
    expr: delta(Cr, 48h)          # Value only

logic:
  cr_rise:
    when: cr_delta >= 0.3         # Comparison here
```

**Why?**
- Clear separation of concerns
- Trends are reusable (same trend, different thresholds)
- ML pipelines can use trend values directly as features

---

## Q4: Does Output belong to PSDL or Workflow?

**A**: Output is the **BOUNDARY** between PSDL and Workflow.

```
PSDL produces Output → Workflow consumes Output
```

Output has three categories:
| Category | Type | Purpose |
|----------|------|---------|
| **Decision** | boolean | Clinical judgments (in_cohort, stage) |
| **Feature** | numeric | ML/stats values (cr_delta, hr_slope) |
| **Evidence** | various | Audit trail (index_time, matched_rules) |

---

## Q5: Should Triggers/Actions be in PSDL?

**A**: **NO**. This would turn PSDL into a Workflow engine.

Adding triggers/actions would lose:
- **Auditability** - actions have side effects
- **Portability** - actions are infrastructure-specific
- **Simplicity** - workflow logic is complex

PSDL outputs `EvaluationResult`. Workflow systems decide what to do with it.

---

## Q6: Does State Machine belong in PSDL?

**A**: **YES**. State tracking is part of detection logic.

Reasons:
- Tracks clinical progression (normal → stage1 → stage2)
- **No side effects** - pure state computation
- **Auditable** - state transitions are logged
- Part of WHAT to detect, not HOW to respond

```yaml
state:
  initial: normal
  states: [normal, stage1, stage2, stage3]
  transitions:
    - from: normal
      to: stage1
      when: aki_stage1    # References logic
```

---

## Q7: How should ML integrate with PSDL?

**A**: ML is not a special concept in PSDL.

**Option A: ML Output as Signal (Upstream)**
```yaml
signals:
  sepsis_risk:
    ref: ml_sepsis_score    # ML model writes to DB, PSDL reads
    unit: probability
```

**Option B: PSDL Output as ML Input (Downstream)**
```yaml
outputs:
  features:
    cr_delta_48h: ...       # ML pipeline consumes these
    hr_slope_6h: ...
```

**Principle**: PSDL doesn't execute ML. It consumes or produces data.

---

## Q8: Should PSDL provide a complete Runtime?

**A**: Provide **Reference Runtime**, not all implementations.

PSDL defines:
- Specification (JSON Schema + Grammar)
- Reference Implementation (Python)
- Clear interfaces for community to extend

Others build:
- Enterprise runtimes (Java, C#)
- Streaming runtimes (Flink, Kafka)
- Cloud-native deployments

---

## Q9: How complex should Output format be?

**A**: Core is minimal. Complexity is optional extension.

**Minimal (Required)**:
```json
{
  "patient_id": "P12345",
  "triggered": true
}
```

**Extended (Optional)**:
```json
{
  "patient_id": "P12345",
  "triggered": true,
  "triggered_logic": ["aki_stage1"],
  "current_state": "stage1",
  "trend_values": {"cr_delta_48h": 0.35},
  "index_time": "2025-01-15T08:30:00Z"
}
```

**Output Profiles** select subsets at runtime without changing semantics.

---

## Q10: Why did Kubernetes succeed? What can PSDL learn?

**A**: Kubernetes succeeded because of:
1. **Minimal core** - small, focused API
2. **Clear boundaries** - knows what it does and doesn't do
3. **Standard interfaces** - CRI, CNI, CSI for extensibility
4. **Declarative** - describe desired state, not imperative steps

**PSDL should follow this pattern**:
- Minimal core (Signal → Trend → Logic → Output)
- Clear boundaries (detection only, not workflow)
- Standard interfaces (Runtime, Adapter, Output)
- Declarative (describe WHAT, not HOW)

---

## Summary Table

| Question | Answer |
|----------|--------|
| What does PSDL do? | Define clinical detection logic |
| Trends with comparisons? | NO - numeric only |
| Triggers/Actions? | NO - workflow concern |
| State Machine? | YES - part of detection |
| ML integration? | Wrapper pattern (signal in, feature out) |
| Output complexity? | Minimal core, optional extensions |

---

## See Also

- [RFC-0005: PSDL v0.3 Architecture](../rfcs/0005-psdl-v03-architecture.md)
- [PRINCIPLES.md](../PRINCIPLES.md) - Core laws governing PSDL
- [WHITEPAPER.md](./WHITEPAPER.md) - Full specification
