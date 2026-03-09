# RFC-0008: Vendor-Neutral Foundation Architecture

| Field | Value |
|-------|-------|
| RFC | 0008 |
| Title | Vendor-Neutral Foundation Architecture |
| Author | PSDL Team |
| Status | **IMPLEMENTED** |
| Created | 2026-03-05 |

## Summary

PSDL's stated mission is to be an open, vendor-neutral standard for clinical logic. However, v0.3.2 contains **seven concrete places** where OMOP CDM table names, PostgreSQL syntax, or OMOP-specific identifier conventions leak directly into core interfaces that should be data-model-agnostic. This RFC identifies each violation, proposes a four-phase remediation plan, and defines the neutral contract layer that decouples PSDL's core from any specific backend.

**Core Principle:**
```
PSDL Core  = neutral contract  (data-model-independent semantics)
Dataset Spec = binding layer   (WHERE and HOW to find data)
Adapter    = execution         (backend-specific SQL / REST / etc.)
```

No OMOP concept, PostgreSQL keyword, or vendor-specific identifier should appear in `src/psdl/core/` or `spec/operators.yaml` operator semantics sections.

## Motivation

### Current Problems - Seven Violations

#### Violation 1: `Domain` enum uses OMOP table names

**File:** `src/psdl/core/ir.py`, line 24

```python
class Domain(Enum):
    """OMOP CDM domains for signals."""   # <- docstring admits the coupling

    MEASUREMENT = "measurement"
    CONDITION = "condition"
    DRUG = "drug"
    PROCEDURE = "procedure"
    OBSERVATION = "observation"
```

The values `"measurement"`, `"condition"`, etc. are OMOP CDM table name roots. A FHIR-only institution has no `measurement` table; they have `Observation` resources. An HL7 v2 institution has OBX segments. The core IR should not bake in one vocabulary for clinical domains.

#### Violation 2: `Signal.concept_id` in the core IR

**File:** `src/psdl/core/ir.py`, line 65

```python
@dataclass
class Signal:
    name: str
    ref: str
    concept_id: Optional[int] = None   # <- OMOP-specific identifier
    unit: Optional[str] = None
    domain: Domain = Domain.MEASUREMENT
```

`concept_id` is an OMOP Vocabulary integer. FHIR uses `(system, code)` pairs. LOINC uses string codes. Embedding `concept_id: int` in the core `Signal` dataclass means every non-OMOP adapter must treat this field as always `None` while the compiler serializes it into audit artifacts via `ScenarioIR.to_artifact()`.

#### Violation 3: `FilterSpec.to_filter_expr()` returns SQL strings

**File:** `src/psdl/core/dataset.py`, line 149

```python
def to_filter_expr(self, spec: DatasetSpec) -> str:
    """Convert filter to SQL-like expression."""
    conditions = []
    if self.concept_id is not None:
        if isinstance(self.concept_id, list):
            ids = ", ".join(str(c) for c in self.concept_id)
            conditions.append(f"concept_id IN ({ids})")   # <- raw SQL string
        else:
            conditions.append(f"concept_id = {self.concept_id}")
    ...
    return " AND ".join(conditions) if conditions else "1=1"
```

`to_filter_expr()` lives in `core/dataset.py` — a module that is supposed to be backend-neutral. Yet it produces SQL fragment strings with PostgreSQL column references (`concept_id`, `source_value`) and the literal `1=1`. The `Binding` dataclass stores the result in `filter_expr: str`, hardwiring a SQL string into the neutral contract.

#### Violation 4: `DatasetAdapter` Protocol is separate from `DataBackend` ABC

**Files:** `src/psdl/core/dataset.py` (Protocol) and `src/psdl/runtimes/single/evaluator.py` (ABC)

```python
# core/dataset.py - RFC-0004 interface
class DatasetAdapter(Protocol):
    def load_dataset_spec(...) -> DatasetSpec: ...
    def resolve_binding(...) -> Binding: ...
    def fetch_events(...) -> Iterator[Event]: ...

# runtimes/single/evaluator.py - single-patient interface
class DataBackend(ABC):
    @abstractmethod
    def fetch_signal_data(
        self, patient_id, signal: Signal, window_seconds: int, reference_time: datetime
    ) -> List[DataPoint]: ...
```

There are now two separate adapter contracts that `OMOPBackend` must satisfy simultaneously. Neither references the other. The RFC-0004 `DatasetAdapter` protocol operates at the `Binding`/`Event` level while `DataBackend` operates at the `Signal`/`DataPoint` level. This dual-protocol split makes it ambiguous which contract governs cross-backend compatibility and places the translation burden on each adapter individually.

#### Violation 5: `CohortCompiler` hardcodes PostgreSQL table names and SQL patterns

**File:** `src/psdl/runtimes/cohort/compiler.py`, line 118

```python
@dataclass
class QueryOptimizationConfig:
    enable_parallel_query: bool = True       # PostgreSQL SET max_parallel_workers
    parallel_workers_per_gather: int = 4     # PostgreSQL-only hint
    include_index_hints: bool = False        # PostgreSQL-specific
```

The compiler generates SQL with hardcoded PostgreSQL-isms (e.g., `INTERVAL '{window_seconds} seconds'`, `REGR_SLOPE`, `PERCENTILE_CONT`, `ROW_NUMBER() OVER`). There is no dialect abstraction layer. Adding DuckDB, BigQuery, or Spark SQL support requires forking the entire compiler rather than swapping a dialect module.

#### Violation 6: `spec/operators.yaml` mixes operator semantics with SQL templates

**File:** `spec/operators.yaml`

```yaml
operators:
  windowed:
    delta:
      description: "Compute absolute change: last_value - first_value in window"
      semantics:
        algorithm: [...]       # <- vendor-neutral: belongs in spec

      implementations:
        python: |              # <- reference implementation: acceptable
          ...
        postgresql: |          # <- PostgreSQL SQL: should NOT be in spec
          {trend_name}_first AS (
              SELECT person_id, {value_col} as value,
                     ROW_NUMBER() OVER (...)
              FROM {table}
              WHERE {filter_cond}
                AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
              ...
          )
        flink_sql: |           # <- Flink SQL: should NOT be in spec
          ...
```

The `spec/` directory is described as the source of truth for the PSDL *specification* — vendor-neutral operator semantics. Embedding PostgreSQL and Flink SQL templates in `spec/operators.yaml` conflates the specification with a specific set of backend implementations. RFC-0006 already identified this problem and proposed separating them into `spec/operators/signatures.yaml` and `spec/operators/backends/postgresql.yaml`, but the split was not executed.

#### Violation 7: Example scenarios embed `concept_id` values

**File:** `src/psdl/examples/*.yaml` (bundled scenarios)

```yaml
# From bundled example scenarios
signals:
  Cr:
    ref: creatinine
    concept_id: 3016723    # <- OMOP concept ID baked into the scenario
```

RFC-0004 established that `concept_id` is a binding detail belonging in Dataset Specs, not scenarios. Several bundled example scenarios still carry `concept_id` in the `signals` block. These are the first examples any new user sees, and they teach the wrong pattern.

### Goals

1. **Neutral core types**: `Domain`, `Signal`, and `Binding` must not reference any specific data model
2. **Unified adapter contract**: One backend protocol governing cross-adapter compatibility
3. **Structured predicates**: Replace SQL string `filter_expr` with a structured `FilterPredicate` type
4. **Dialect separation**: SQL templates belong in `spec/operators/backends/`, not `spec/operators.yaml`
5. **Clean examples**: Bundled scenarios must follow the RFC-0004 pattern with no `concept_id` fields
6. **Zero breaking changes**: All changes are additive or deprecation-based; v0.3.x users are unaffected

## Design

### Architecture: Neutral Contract Layer

```
┌──────────────────────────────────────────────────────────────────────┐
│ SCENARIO (Intent)                                                    │
│                                                                      │
│   signals:                                                           │
│     Cr:                                                              │
│       ref: creatinine        # semantic only - no concept_id        │
│                                                                      │
│   trends:                                                            │
│     cr_delta_48h:                                                    │
│       expr: delta(Cr, 48h)   # operator semantics from spec         │
│                                                                      │
│   logic:                                                             │
│     cr_rising:                                                       │
│       when: cr_delta_48h >= 0.3                                     │
├──────────────────────────────────────────────────────────────────────┤
│ PSDL CORE (Neutral Contract Layer) [THIS RFC]                        │
│                                                                      │
│   ClinicalDomain enum  - universal clinical domains                  │
│   Signal dataclass     - no concept_id, no OMOP assumptions         │
│   FilterPredicate      - structured predicates, not SQL strings      │
│   FilterPredicateSet   - ordered list of predicates                  │
│   Binding              - filter_predicates: FilterPredicateSet       │
│   BatchRuntime(ABC)    - unified adapter contract                    │
├──────────────────────────────────────────────────────────────────────┤
│ DATASET SPEC (Binding Layer - RFC-0004)                              │
│                                                                      │
│   elements:                                                          │
│     creatinine:                                                      │
│       table: measurement                                             │
│       filter:                                                        │
│         concept_id: [3016723]   # OMOP detail lives HERE only       │
├──────────────────────────────────────────────────────────────────────┤
│ ADAPTERS (Execution Layer)                                           │
│                                                                      │
│   OMOPBackend   → translates FilterPredicateSet to SQL WHERE clause  │
│   FHIRBackend   → translates FilterPredicateSet to FHIR search params│
│   DuckDBBackend → translates FilterPredicateSet to DuckDB SQL        │
└──────────────────────────────────────────────────────────────────────┘
```

### Phase 1: Neutral Core Types

**Target files:** `src/psdl/core/ir.py`, `src/psdl/core/dataset.py`

#### 1a. Replace `Domain` with `ClinicalDomain`

```python
# src/psdl/core/ir.py

class ClinicalDomain(Enum):
    """
    Vendor-neutral clinical data domains.

    Values are standard clinical category names, NOT database table names.
    Each adapter translates these to its own physical table or resource type.
    """
    MEASUREMENT = "measurement"    # Labs, vitals, test results
    CONDITION = "condition"        # Diagnoses, problem list
    MEDICATION = "medication"      # Drug exposures, prescriptions
    PROCEDURE = "procedure"        # Clinical procedures
    OBSERVATION = "observation"    # Survey responses, clinical notes
    DEVICE = "device"              # Device measurements and usage
    ENCOUNTER = "encounter"        # Visits, admissions


# Backward compatibility alias - deprecated, removed in v0.5
Domain = ClinicalDomain
```

Adapter-specific translation tables live in the adapters:

```python
# src/psdl/adapters/omop.py

# Adapter owns this mapping - it is not part of core
_OMOP_DOMAIN_TABLE = {
    ClinicalDomain.MEASUREMENT: "measurement",
    ClinicalDomain.CONDITION:   "condition_occurrence",
    ClinicalDomain.MEDICATION:  "drug_exposure",
    ClinicalDomain.PROCEDURE:   "procedure_occurrence",
    ClinicalDomain.OBSERVATION: "observation",
    ClinicalDomain.DEVICE:      "device_exposure",
    ClinicalDomain.ENCOUNTER:   "visit_occurrence",
}
```

#### 1b. Remove `concept_id` from `Signal`

```python
# src/psdl/core/ir.py

@dataclass
class Signal:
    """A signal binding - maps logical name to a semantic data reference."""

    name: str
    ref: str           # Semantic reference resolved via Dataset Spec
    unit: Optional[str] = None
    domain: ClinicalDomain = ClinicalDomain.MEASUREMENT

    # Deprecated in v0.4, removed in v0.5
    # concept_id belongs in Dataset Spec (RFC-0004), not in core IR
    concept_id: Optional[int] = field(default=None, repr=False)
```

`concept_id` is retained as a deprecated field for one minor version to allow adapters and tests that currently read `signal.concept_id` to migrate gracefully.

#### 1c. Replace `filter_expr: str` with `FilterPredicate`

Instead of a raw SQL string, `Binding` carries structured predicates that each adapter renders in its own dialect:

```python
# src/psdl/core/dataset.py

from dataclasses import dataclass
from typing import Literal, Union

PredicateOperator = Literal["eq", "in", "like", "custom"]


@dataclass(frozen=True)
class FilterPredicate:
    """
    A single, vendor-neutral filter predicate.

    Adapters translate these to SQL WHERE fragments, FHIR search parameters,
    or any other backend-specific filter representation.
    """
    field: str                        # Logical field name: "concept_id", "code", "source_value"
    operator: PredicateOperator       # "eq", "in", "like", "custom"
    value: Union[int, str, list]      # Scalar or list value
    raw: Optional[str] = None         # Passthrough for "custom" operator


@dataclass(frozen=True)
class FilterPredicateSet:
    """
    An ordered set of predicates combined with AND semantics.

    Replacing the raw SQL string in Binding. Each adapter translates
    this to its own filter representation.
    """
    predicates: tuple[FilterPredicate, ...]

    @classmethod
    def empty(cls) -> "FilterPredicateSet":
        """No-op filter that matches all records."""
        return cls(predicates=())

    @classmethod
    def from_concept_ids(cls, concept_ids: list[int]) -> "FilterPredicateSet":
        """Convenience constructor for OMOP concept_id lists."""
        return cls(predicates=(
            FilterPredicate(field="concept_id", operator="in", value=concept_ids),
        ))

    @classmethod
    def from_loinc_code(cls, code: str) -> "FilterPredicateSet":
        """Convenience constructor for LOINC codes."""
        return cls(predicates=(
            FilterPredicate(field="code", operator="eq", value=code),
            FilterPredicate(field="code_system", operator="eq", value="http://loinc.org"),
        ))
```

`FilterSpec.to_filter_expr()` is removed. Each adapter renders `FilterPredicateSet` directly:

```python
# src/psdl/adapters/omop.py

def _render_filter(self, predicates: FilterPredicateSet) -> str:
    """Render neutral predicates as a PostgreSQL WHERE fragment."""
    if not predicates.predicates:
        return "1=1"
    parts = []
    for p in predicates.predicates:
        if p.operator == "eq":
            parts.append(f"{p.field} = {self._param(p.value)}")
        elif p.operator == "in":
            ids = ", ".join(str(v) for v in p.value)
            parts.append(f"{p.field} IN ({ids})")
        elif p.operator == "custom" and p.raw:
            parts.append(p.raw)
    return " AND ".join(parts)
```

Updated `Binding`:

```python
@dataclass(frozen=True)
class Binding:
    """Resolved binding from Dataset Spec - the neutral contract between spec and adapter."""

    table: str
    value_field: str
    time_field: str
    patient_field: str
    filter_predicates: FilterPredicateSet          # structured - replaces filter_expr
    unit: Optional[str] = None
    value_type: ValueType = "numeric"
    transform: Optional[str] = None

    # Deprecated in v0.4, removed in v0.5
    # Returns a PostgreSQL-style string for backward compatibility only
    @property
    def filter_expr(self) -> str:
        """Deprecated: use filter_predicates. Returns a PostgreSQL-style WHERE fragment."""
        import warnings
        warnings.warn(
            "Binding.filter_expr is deprecated. Adapters should use "
            "filter_predicates (FilterPredicateSet) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._render_pg_compat()

    def _render_pg_compat(self) -> str:
        """Backward-compat PostgreSQL rendering of predicates."""
        if not self.filter_predicates.predicates:
            return "1=1"
        parts = []
        for p in self.filter_predicates.predicates:
            if p.operator == "eq":
                parts.append(f"{p.field} = {p.value!r}")
            elif p.operator == "in":
                ids = ", ".join(str(v) for v in p.value)
                parts.append(f"{p.field} IN ({ids})")
            elif p.operator == "custom" and p.raw:
                parts.append(p.raw)
        return " AND ".join(parts)
```

### Phase 2: Adapter and Runtime Protocols

**Target files:** `src/psdl/core/dataset.py`, `src/psdl/runtimes/single/evaluator.py`

#### 2a. Enhance `DataBackend` to cover the full lifecycle

The current `DataBackend` ABC only covers `fetch_signal_data()`. The `DatasetAdapter` Protocol in `core/dataset.py` covers binding and event fetching. These should converge into a single, layered contract.

```python
# src/psdl/runtimes/single/evaluator.py

class DataBackend(ABC):
    """
    Abstract base class for PSDL data backends.

    Backends implement at minimum fetch_signal_data(). Backends that support
    RFC-0004 Dataset Specs additionally implement resolve_binding() and
    fetch_events() via the BatchRuntime mixin.
    """

    @abstractmethod
    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """Fetch time-series data for a signal within a time window."""
        ...
```

```python
# src/psdl/runtimes/batch.py  (new file)

from abc import ABC, abstractmethod
from typing import Iterator, List, Optional, Tuple
from datetime import datetime

from ..core.dataset import Binding, DatasetSpec, Event, FilterPredicateSet


class BatchRuntime(ABC):
    """
    Protocol for backends that support Dataset Spec-based batch execution.

    Implements the RFC-0004 adapter contract using the neutral Binding type.
    Backends that satisfy this ABC are compatible with CohortCompiler and
    the batch evaluation pipeline regardless of their underlying data model.
    """

    @abstractmethod
    def resolve_binding(self, signal_ref: str, spec: DatasetSpec) -> Binding:
        """
        Resolve a semantic reference to a physical Binding.

        The returned Binding uses FilterPredicateSet, not raw SQL strings,
        so the same binding can be rendered by any dialect.
        """
        ...

    @abstractmethod
    def fetch_events(
        self,
        binding: Binding,
        patient_ids: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> Iterator[Event]:
        """
        Fetch events using a resolved Binding.

        Adapters render binding.filter_predicates in their own dialect.
        """
        ...
```

`OMOPBackend` inherits from both `DataBackend` and `BatchRuntime`. The `DatasetAdapter` Protocol in `core/dataset.py` is deprecated in favor of `BatchRuntime`.

#### 2b. Add `SQLBatchRuntime` for SQL-capable backends

```python
# src/psdl/runtimes/batch.py

class SQLBatchRuntime(BatchRuntime, ABC):
    """
    Extension of BatchRuntime for backends that generate SQL.

    Provides the dialect abstraction hook that CohortCompiler uses.
    """

    @property
    @abstractmethod
    def sql_dialect(self) -> str:
        """
        SQL dialect identifier. Used by CohortCompiler to select templates.

        Return values must match keys in spec/operators/backends/:
            "postgresql", "duckdb", "bigquery", "spark"
        """
        ...

    @abstractmethod
    def render_filter(self, predicates: FilterPredicateSet) -> str:
        """Render FilterPredicateSet as a dialect-appropriate WHERE fragment."""
        ...
```

`OMOPBackend.sql_dialect` returns `"postgresql"`. A future `DuckDBBackend.sql_dialect` returns `"duckdb"`. `CohortCompiler` uses `backend.sql_dialect` to load the matching template set from `spec/operators/backends/`.

### Phase 3: Specification Cleanup

**Target files:** `spec/operators.yaml`, new `spec/operators/` directory

RFC-0006 proposed splitting `spec/operators.yaml` but did not execute the split. This phase implements it.

#### 3a. Extract operator signatures to `spec/operators/signatures.yaml`

```yaml
# spec/operators/signatures.yaml
# Vendor-neutral operator semantics only.
# No SQL. No backend references.

version: "0.4.0"

operators:
  windowed:
    delta:
      signature: "(signal: Signal, window: Window) -> float | null"
      description: "Compute absolute change: last_value - first_value in window"
      semantics:
        null_handling: filter
        min_points: 2
        algorithm:
          - "Filter data points to [reference_time - window, reference_time]"
          - "Remove null values"
          - "If fewer than 2 points remain, return null"
          - "Return: last_non_null.value - first_non_null.value"
        mathematical_definition: "δ(S,W) = S[t_max] - S[t_min]"
      edge_cases:
        empty_window: null
        single_value: null
        all_nulls: null
      implementations:
        python: |
          def delta(data, window_seconds, reference_time):
              ...
    slope:
      ...
```

#### 3b. Move SQL templates to `spec/operators/backends/`

```yaml
# spec/operators/backends/postgresql.yaml
# PostgreSQL-specific SQL templates.
# Referenced by codegen.py; NOT part of the PSDL specification.

version: "0.4.0"
dialect: postgresql
min_version: "12"

templates:
  delta: |
    {trend_name}_first AS (
        SELECT person_id, {value_col} as value,
               ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY {datetime_col} ASC) as rn
        FROM {table}
        WHERE {filter_cond}
          AND {datetime_col} >= :reference_time - INTERVAL '{window_seconds} seconds'
          AND {datetime_col} <= :reference_time
          AND {value_col} IS NOT NULL
    ),
    ...
```

```yaml
# spec/operators/backends/duckdb.yaml  (v0.4 placeholder - full implementation follows)
version: "0.4.0"
dialect: duckdb
```

`codegen.py --all` generates dialect-specific Python modules under `_generated/sql/`:

```
_generated/
  sql/
    postgresql.py    # from spec/operators/backends/postgresql.yaml
    duckdb.py        # from spec/operators/backends/duckdb.yaml (future)
```

`CohortCompiler` imports the active dialect module:

```python
from psdl._generated.sql import postgresql as _sql_dialect
```

#### 3c. Remove `implementations.postgresql` and `implementations.flink_sql` from `spec/operators.yaml`

The existing `spec/operators.yaml` retains operator semantics and Python implementations but has all SQL template blocks removed. The file is renamed to `spec/operators/signatures.yaml`. A shim `spec/operators.yaml` is preserved for one minor version pointing to the new location, then removed in v0.5.

### Phase 4: Example Migration and Version Bump

**Target files:** `src/psdl/examples/*.yaml`, `src/psdl/__init__.py`, `pyproject.toml`, `CLAUDE.md`, `wiki/API.md`

#### 4a. Remove `concept_id` from bundled example scenarios

Each bundled scenario that currently carries `concept_id` in its `signals` block is updated to use `ref:` only, and a companion dataset spec is added alongside it:

```yaml
# src/psdl/examples/aki_detection.yaml  (after migration)
signals:
  Cr:
    ref: creatinine        # No concept_id here
    expected_unit: mg/dL
```

```yaml
# src/psdl/examples/dataset_specs/synthea_omop.yaml  (new companion)
psdl_version: "0.4"
dataset:
  name: synthea_omop
  version: "1.0.0"
data_model: omop
elements:
  creatinine:
    table: measurement
    value_field: value_as_number
    time_field: measurement_datetime
    filter:
      concept_id: [3016723]
    unit: mg/dL
```

#### 4b. Version bump to v0.4.0

This RFC introduces neutral core types that change the public API surface. Per semantic versioning, this is a minor version increment (all changes are additive or deprecation-based; nothing is removed):

| Component | Before | After |
|-----------|--------|-------|
| `pyproject.toml` version | `0.3.2` | `0.4.0` |
| `src/psdl/__init__.py` `__version__` | `"0.3.2"` | `"0.4.0"` |
| `spec/operators/signatures.yaml` version | — | `"0.4.0"` |

## Migration Guide

### `concept_id` in Scenarios (Violations 2 and 7)

**Before (v0.3.x):**
```yaml
signals:
  Cr:
    ref: creatinine
    concept_id: 3016723    # deprecated
```

**After (v0.4.0):**
```yaml
# scenarios/aki.yaml
signals:
  Cr:
    ref: creatinine        # no concept_id

# dataset_specs/my_omop.yaml
elements:
  creatinine:
    table: measurement
    filter:
      concept_id: [3016723]
```

`Signal.concept_id` emits a `DeprecationWarning` in v0.4 when accessed and will be removed in v0.5. The parser continues to load it silently.

### `Binding.filter_expr` (Violation 3)

**Before (v0.3.x, custom adapters):**
```python
binding = spec.resolve("creatinine")
where_clause = binding.filter_expr   # raw SQL string
query = f"SELECT ... FROM {binding.table} WHERE {where_clause}"
```

**After (v0.4.0):**
```python
binding = spec.resolve("creatinine")
where_clause = self.render_filter(binding.filter_predicates)  # adapter renders
query = f"SELECT ... FROM {binding.table} WHERE {where_clause}"
```

`Binding.filter_expr` emits a `DeprecationWarning` in v0.4 and is removed in v0.5.

### `Domain` enum (Violation 1)

**Before:**
```python
from psdl.core.ir import Domain
signal.domain = Domain.MEASUREMENT
```

**After:**
```python
from psdl.core.ir import ClinicalDomain
signal.domain = ClinicalDomain.MEASUREMENT

# Or via alias (deprecated, removed in v0.5):
from psdl.core.ir import Domain   # DeprecationWarning
```

### Custom Adapters implementing `DatasetAdapter` (Violation 4)

**Before:**
```python
class MyAdapter:
    def load_dataset_spec(self, uri): ...
    def resolve_binding(self, ref, spec): ...
    def fetch_events(self, binding, ...): ...
```

**After:**
```python
from psdl.runtimes.batch import BatchRuntime

class MyAdapter(DataBackend, BatchRuntime):
    def fetch_signal_data(self, ...): ...   # DataBackend
    def resolve_binding(self, ref, spec): ...  # BatchRuntime
    def fetch_events(self, binding, ...): ...  # BatchRuntime
```

`DatasetAdapter` Protocol remains importable in v0.4 for backward compatibility but is marked deprecated. It is removed in v0.5.

## Backward Compatibility

All changes in this RFC are strictly additive or deprecation-based. No existing public API is removed in v0.4.0.

| Change | v0.4.0 | v0.5.0 |
|--------|--------|--------|
| `Domain` enum | Alias for `ClinicalDomain`, `DeprecationWarning` | Removed |
| `Signal.concept_id` | `DeprecationWarning` on access | Removed |
| `Binding.filter_expr` | `DeprecationWarning` on access | Removed |
| `FilterSpec.to_filter_expr()` | `DeprecationWarning` | Removed |
| `DatasetAdapter` Protocol | `DeprecationWarning` | Removed |
| `spec/operators.yaml` SQL blocks | Moved to `spec/operators/backends/` | `spec/operators.yaml` removed |
| `concept_id` in scenario YAML | Parser warning, ignored | Parser error |

Tests for deprecated behavior are tagged `@pytest.mark.deprecated` and run in CI to confirm warnings are emitted. They are removed together with the deprecated code in v0.5.

## Implementation Plan

### Phase 1: Neutral Core Types (Week 1-2)
1. Add `ClinicalDomain` to `src/psdl/core/ir.py`; alias `Domain = ClinicalDomain`
2. Add `FilterPredicate` and `FilterPredicateSet` to `src/psdl/core/dataset.py`
3. Deprecate `Signal.concept_id` (add `DeprecationWarning`, keep field)
4. Deprecate `FilterSpec.to_filter_expr()` (add `DeprecationWarning`)
5. Update `DatasetSpec.resolve()` to populate `Binding.filter_predicates`
6. Deprecate `Binding.filter_expr` property with backward-compat rendering

### Phase 2: Adapter and Runtime Protocols (Week 3-4)
1. Create `src/psdl/runtimes/batch.py` with `BatchRuntime` and `SQLBatchRuntime` ABCs
2. Deprecate `DatasetAdapter` Protocol in `core/dataset.py`
3. Update `OMOPBackend` to inherit `BatchRuntime`, add `render_filter()`, add `sql_dialect`
4. Update `CohortCompiler` to use `backend.sql_dialect` for template selection

### Phase 3: Specification Cleanup (Week 5-6)
1. Create `spec/operators/` directory
2. Write `spec/operators/signatures.yaml` from existing semantics sections
3. Write `spec/operators/backends/postgresql.yaml` from existing SQL blocks
4. Create `spec/operators/backends/duckdb.yaml` (empty placeholder)
5. Update `codegen.py` to read from new structure; write to `_generated/sql/`
6. Preserve `spec/operators.yaml` as a redirect shim for one release

### Phase 4: Example Migration and Docs (Week 7)
1. Remove `concept_id` from all bundled example scenarios in `src/psdl/examples/`
2. Add `src/psdl/examples/dataset_specs/` with companion Dataset Specs
3. Version bump to v0.4.0 in `pyproject.toml` and `__init__.py`
4. Update `wiki/API.md` with new types and deprecation notices
5. Update `CLAUDE.md` to reflect v0.4.0 status

## Alternatives Considered

### 1. Keep `filter_expr: str` but standardize the SQL dialect

**Approach:** Define a canonical SQL subset (e.g., ANSI SQL) for `filter_expr` and require all adapters to translate from it.

**Rejected because:** Parsing SQL strings is fragile, introduces a hidden mini-DSL, and makes it impossible to represent FHIR search parameters or gRPC filter expressions without SQL shims.

### 2. One adapter Protocol, no ABC

**Approach:** Replace both `DataBackend` ABC and `DatasetAdapter` Protocol with a single Protocol.

**Rejected because:** `DataBackend` is an ABC used in `isinstance()` checks throughout the codebase. Switching to a Protocol-only approach would silently break adapters that rely on ABC enforcement.

### 3. Separate packages: `psdl-core` and `psdl-omop`

**Approach:** Split the repository so OMOP-specific code lives in a separate installable package.

**Rejected because:** The overhead of multi-package maintenance is premature at this stage. Deprecation discipline within a single package is sufficient to enforce the neutral boundary. Separate packages remain a valid Phase 5 option after v0.4.0 proves out the architecture.

## Open Questions

1. Should `FilterPredicateSet` support OR semantics (for multi-domain queries) or remain AND-only?
2. Should `ClinicalDomain` include `IMAGING` and `GENOMICS` domains now, or defer to a future RFC?
3. Should `spec/operators/backends/duckdb.yaml` be a v0.4.0 deliverable or a stretch goal?

## References

- [RFC-0004: Dataset Specification](0004-dataset-specification.md) - established the binding layer pattern
- [RFC-0005: PSDL v0.3 Architecture](0005-psdl-v03-architecture.md) - introduced the current Signal/Trend/Logic model
- [RFC-0006: Spec-Driven Compilation](0006-spec-driven-compilation.md) - proposed the operator signature/backend split (not yet executed)
- [OMOP CDM Specification](https://ohdsi.github.io/CommonDataModel/)
- [FHIR R4 Observation](https://hl7.org/fhir/observation.html)
- [GraphQL SDL](https://spec.graphql.org/) - reference model for vendor-neutral specification

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-03-05 | PSDL Team | Initial draft |
