# RFC-0009: Signal Groups

| Field | Value |
|-------|-------|
| RFC | 0009 |
| Title | Signal Groups - Bulk Data Requests and Custom Panels |
| Author | PSDL Team |
| Status | **PROPOSED** |
| Priority | MEDIUM |
| Created | 2026-04-10 |
| Target Version | v0.5.0 |
| Related Issue | #10 |

---

## Summary

Add an optional top-level `signal_groups:` section to PSDL scenarios. A signal group is either (a) a **domain-level** bulk data request ("give me all labs for these patients") or (b) a **custom panel** naming a subset of individually defined signals ("renal panel = creatinine + hemoglobin + dialysis_active"). Groups are a data-extraction declaration for the Dataset Spec layer. They have **zero interaction with trends or logic** — only individually defined signals feed into the detection chain.

---

## Motivation

### Current Limitation

Real-world clinical teams request data by **domain** or by meaningful **clinical subsets**, not by individual data elements. PSDL v0.4 requires every data element to be declared as a signal, which:

1. Forces authors to enumerate every lab, med, or procedure they need extracted
2. Offers no way to express "all labs for these patients"
3. Does not match how data requests are actually organized in clinical workflows
4. Makes Dataset Spec mapping tedious — each signal must be bound individually

### Real-World Trigger

A perioperative surgical cohort definition (exercised in psdl-inspector) required 11 data domains: encounters, OR cases, labs, diagnoses, dialysis, procedures, mortality, billing, vitals, meds, providers. Most were bulk extraction requests, not individually reasoned-about signals. Expressing this in PSDL v0.4 would mean inventing dozens of single-use signal declarations with no trend or logic attached.

### Prior Art

| Platform | Fixed Domains | Custom Groups |
|----------|---------------|---------------|
| OHDSI Atlas | OMOP Domain tables | Concept Sets |
| FHIR | Observation Category | ValueSets |
| TriNetX | Data categories | N/A |

PSDL already has `ClinicalDomain` (RFC-0008) — LABORATORY, VITAL_SIGN, CONDITION, MEDICATION, PROCEDURE, OBSERVATION, DEMOGRAPHIC — but it is classification metadata on individual signals, not a request mechanism.

**Chosen model:** OHDSI Concept Sets — the natural fit given psdl-inspector's existing OMOP vocabulary anchoring.

---

## Design

### Phase 1 — `signal_groups` as a Top-Level Section

A new optional YAML section. A group is **either** a domain-level bulk request **or** a named custom panel; the two forms are mutually exclusive in Phase 1.

#### YAML

```yaml
# (abbreviated — a runnable scenario also needs audit, trends, logic, outputs)
psdl_version: "0.5"
scenario: Perioperative_Surgical_Cohort
version: "0.1.0"

signal_groups:
  # Domain-level: bulk data extraction
  all_labs:
    domain: laboratory
    description: "All lab results for cohort patients"

  all_meds:
    domain: medication
    description: "All medication orders and administrations"

  # Custom panel: named subset of individually defined signals
  renal_panel:
    members: [creatinine, hemoglobin, dialysis_active]
    description: "Renal function monitoring panel"

signals:
  creatinine:
    ref: creatinine
    description: "Serum creatinine"
  # ...
```

#### Validation Rules

1. `domain` and `members` are **mutually exclusive** (Phase 1).
2. Every group must have exactly one of `domain` or `members`.
3. `description` is required.
4. `domain` must be a valid `ClinicalDomain` enum value.
5. `members` must be a list; every entry must reference a signal defined in the scenario's `signals:` section.
6. The entire `signal_groups` section is optional. Scenarios without it remain valid with zero changes.

#### Separation from Trends and Logic

```
signal_groups ──> Dataset Spec   (tells the site "I need this data")
signals ──> trends ──> logic     (the detection / reasoning chain)
```

A domain-level group like `all_labs` means "extract all lab data for these patients" but defines no trends or rules over that bulk data. Only individually defined signals feed the detection chain.

#### Hashing & Compilation

Signal groups are **not** part of the canonical scenario hash produced by `ScenarioCompiler` (RFC-0006). Two scenarios with identical `signals`/`trends`/`logic` but different `signal_groups` produce the same evaluation output per patient, so they share a hash. `ScenarioIR` does not carry a signal-groups field; the compile path ignores the section entirely. If a future use case demands group-aware hashing (e.g. cache keys for bulk extraction), it can be added non-breakingly by bumping the hash algorithm version.

### Phase 2 — Hybrid Groups (Deferred)

In a future release, `domain` and `members` could coexist for domain-constrained panels:

```yaml
signal_groups:
  renal_labs:
    members: [creatinine, bun, urine_output]
    domain: laboratory    # constraint: all members must belong to the laboratory domain
    description: "Renal lab panel"
```

This adds a validation check that every member belongs to the declared domain, catching miscategorization. Deferred to keep Phase 1 simple. Any change needed to enable Phase 2 is additive over Phase 1.

---

## Relationship to RFC-0007 (Extension Mechanism)

RFC-0007 defines "extension" as a pluggable package (e.g. `psdl-events@1.0`) that ships new signal kinds, new operators, and its own validator through a `PSDLExtension` interface. Signal groups **do not fit that shape**:

| RFC-0007 extension | Signal groups |
|---|---|
| Separate pip package | Lives in `src/psdl/core/ir.py` |
| Declared via `extensions: [psdl-events@1.0]` | No declaration required |
| Adds new operators / signal kinds | Adds none |
| Implements `PSDLExtension` ABC | Plain dataclass in core IR |
| Pluggable / unloadable | Always present |

Signal groups is therefore a **core language addition** — another optional top-level section alongside `population:`, `state:`, `outputs:` — and not an RFC-0007 extension.

---

## Data Model

### Core IR (`src/psdl/core/ir.py`)

```python
@dataclass
class SignalGroup:
    """A named collection of signals or a domain-level data request (RFC-0009).

    Phase 1: domain and members are mutually exclusive, and exactly one must be set.
    - domain: bulk data request for a clinical domain (all_labs, all_meds)
    - members: explicit list of signal names (custom panel)
    """
    name: str
    description: str
    domain: Optional[ClinicalDomain] = None
    members: Optional[List[str]] = None

    def __post_init__(self):
        if self.domain is not None and self.members:
            raise ValueError(
                f"SignalGroup '{self.name}': 'domain' and 'members' are mutually exclusive"
            )
        if self.domain is None and not self.members:
            raise ValueError(
                f"SignalGroup '{self.name}': must have either 'domain' or a non-empty 'members'"
            )
```

Add a field to `PSDLScenario`:

```python
signal_groups: Dict[str, SignalGroup] = field(default_factory=dict)
```

Extend `PSDLScenario.validate()` to check member references:

```python
for group_name, group in self.signal_groups.items():
    if group.members:
        for signal_name in group.members:
            if signal_name not in self.signals:
                errors.append(
                    f"Signal group '{group_name}' references unknown signal '{signal_name}'"
                )
```

Domain-level groups skip that check (no members to validate). Note: `PSDLParser.parse_string` already calls `scenario.validate()` and raises `PSDLParseError` when any errors are returned, so callers of the parser see unknown-member references as **parse-time errors**, consistent with how `trend` and `logic` member errors surface today. Direct consumers who construct `PSDLScenario` programmatically still get the errors via `validate()`.

### Parser (`src/psdl/core/parser.py`)

Add a `_parse_signal_groups` method and call it from `parse_string` between population parsing and signals parsing. The method enforces the validation rules above at parse time and raises `PSDLParseError` with a clear message for each violation.

### JSON Schema (`spec/schema.json`)

The schema root has `additionalProperties: false`, so strict validators reject unknown top-level keys. The schema must be updated to teach validators about `signal_groups`:

1. **Tighten the `PSDLVersion` pattern** from `^0\.3(\.\d+)?$` to `^0\.5(\.\d+)?$`. This is a deliberate **breaking change** — only `psdl_version: "0.5"` (and patch suffixes like `"0.5.1"`) is accepted. Every bundled example, test fixture, and conformance test case currently declaring `"0.3"` is bumped straight to `"0.5"`. See the scope table for the migration list.
2. Add `signal_groups` as an optional top-level property referencing `#/$defs/SignalGroupDefinitions`.
3. Add `SignalGroupDefinitions` — a dict whose values match `SignalGroup`.
4. Add `SignalGroup`. The XOR constraint on `domain`/`members` is expressed via a top-level `oneOf` sibling to `properties`; `description` stays in the object's normal `required` list (it's required regardless of which branch matches):
   ```json
   "SignalGroup": {
     "type": "object",
     "required": ["description"],
     "additionalProperties": false,
     "properties": {
       "description": { "type": "string" },
       "domain": { "enum": ["laboratory", "vital_sign", "condition", "medication", "procedure", "observation", "demographic"] },
       "members": { "type": "array", "items": { "type": "string" }, "minItems": 1 }
     },
     "oneOf": [
       { "required": ["domain"], "not": { "required": ["members"] } },
       { "required": ["members"], "not": { "required": ["domain"] } }
     ]
   }
   ```
5. Bump `x-psdl-schema-version` to `0.5.0`, `$id` to `.../schema/v0.5/scenario`, and update the top-of-file `$comment` field (currently `"Schema version 0.3.0 (2025-12-14). Breaking change from v0.2: trends cannot contain comparison operators."`) to a v0.5 dated comment noting the addition of `signal_groups` and the tightened version pattern.
6. Bump `spec/VERSION` to `0.5.0`.

### Public API (`src/psdl/__init__.py`)

Export `SignalGroup` from the `.core.ir` import block and add it to `__all__` next to `Signal` and `ClinicalDomain`.

### Dataset Spec Interaction (Design Note — Not Implemented Here)

Signal groups are designed to enable bulk bindings at the Dataset Spec layer:

```yaml
# Without groups: map each signal individually
bindings:
  creatinine: { table: lab_results, column: result_value, filter: "loinc = '2160-0'" }
  hemoglobin: { table: lab_results, column: result_value, filter: "loinc = '718-7'" }
  # ... many more ...

# With groups: map entire domain at once
group_bindings:
  all_labs: { table: lab_results, value_column: result_value, code_column: loinc_code }
```

`group_bindings` is **not** implemented in this RFC. It is mentioned only to show the design intent. A follow-up RFC can add it when a real binding consumer appears.

---

## Implementation Scope

### In Scope (v0.5.0)

| Area | Change |
|------|--------|
| `src/psdl/core/ir.py` | Add `SignalGroup` dataclass, add `signal_groups` field on `PSDLScenario`, extend `validate()` |
| `src/psdl/core/parser.py` | Add `_parse_signal_groups`, wire into `parse_string` |
| `src/psdl/__init__.py` | Export `SignalGroup`, bump `__version__` to `0.5.0`, update docstring `v0.4` → `v0.5` |
| `spec/schema.json` | Add `signal_groups` + `SignalGroupDefinitions` + `SignalGroup` defs, tighten `PSDLVersion` pattern, bump schema version |
| `spec/VERSION` | Bump to `0.5.0` |
| `tests/test_signal_groups.py` | New file (~25 tests) covering dataclass (5), PSDLScenario (5), parser (10), schema (5) |
| `rfcs/0009-signal-groups.md` | This document |
| `CHANGELOG.md` | New `[0.5.0]` section |
| `pyproject.toml` | Bump version to `0.5.0` |
| `CLAUDE.md` | Update version markers and RFC status table |
| **Migration: `psdl_version: "0.3"` → `"0.5"`** | |
| `src/psdl/examples/sepsis_screening.yaml` | Bump header to `"0.5"` |
| `spec/conformance/scenario_tests.json` | Bump every `"psdl_version": "0.3"` occurrence to `"0.5"` (leave the `"99.0"` unsupported-version fixture alone — it still proves pattern rejection) |
| `spec/conformance/dataset_tests.json` | Bump every `"psdl_version": "0.3"` occurrence to `"0.5"` |
| `tests/test_compile.py` | Bump inline fixtures to `"0.5"` |
| `tests/test_vendor_neutral.py` | Bump inline fixtures to `"0.5"` |
| `tests/test_dataset_spec.py` | Bump inline fixtures to `"0.5"` |

### Out of Scope (Deferred)

- **Phase 2 hybrid groups** — domain + members coexistence as a constraint
- **`group_bindings` in Dataset Spec** — follow-up RFC
- **ScenarioCompiler / ScenarioIR awareness of groups** — compile path ignores `signal_groups` entirely
- **`spec/hashing.yaml` changes** — groups excluded from the scenario hash
- **`spec/conformance/*.json` additions** — no new operators, no new AST nodes, no new semantic behavior, so the conformance suite gains only the version-bump migration above. New conformance cases for `signal_groups` can be added in a later pass.
- **`_generated/` changes** — no codegen needed; the new dataclass is manual. Running `tools/codegen.py --all` after this work should produce zero diff, which is a good sanity check.
- **Runtime / adapter changes** — no runtime consumes groups yet
- **psdl-inspector vendored patch removal** — the inspector currently carries an in-`.venv` modification of `psdl-lang 0.4.0`. After this RFC ships to PyPI as `psdl-lang 0.5.0`, a follow-up PR on psdl-inspector will bump its requirement and delete the patched files. That cleanup is out of scope for this RFC.

---

## Breaking Changes and Compatibility

**Breaking:** `psdl_version: "0.3"` is no longer a valid scenario version. Every scenario must declare `"0.5"`. The in-tree migration (bundled example, conformance tests, unit-test fixtures) is listed in the scope table; out-of-tree consumers must update their scenario files to `"0.5"`.

Rationale: v0.3.2 has been the effective scenario version since late 2025 and the jump through v0.4 (RFC-0008) was a non-user-facing package refactor that never touched the YAML surface. Rather than widen the pattern to accept `"0.3" | "0.4" | "0.5"` — which perpetuates the drift between package version and declared scenario version — we cut cleanly to a single valid value. After this release, package version, schema version, and declared scenario version are all `0.5.x`.

**Non-breaking:**
- `signal_groups:` is an optional section. Scenarios without it remain valid with zero content changes (only the `psdl_version` header changes).
- The public Python API is unchanged — `SignalGroup` is a pure addition to `psdl.core.ir` and `psdl.__init__`.
- `ScenarioIR` hashing is unchanged, so cached compile outputs for existing scenarios remain valid after the version-header bump.
- The JSON schema change is additive on the properties side (new optional top-level key + three new `$def`s).

---

## Test Plan

New file `tests/test_signal_groups.py`:

**`SignalGroup` dataclass**
- Construct domain-level group (members defaults to None)
- Construct custom panel (domain defaults to None)
- Constructing with both `domain` and `members` raises `ValueError` mentioning "mutually exclusive"
- Constructing with neither `domain` nor non-empty `members` raises `ValueError` mentioning "must have either"
- Constructing with `members=[]` raises `ValueError` (empty list treated as no members)

**`PSDLScenario.signal_groups`**
- Default is empty dict when the section is absent
- Populated correctly when the section is present
- `validate()` returns no group-related errors for valid members
- `validate()` returns an error naming the unknown signal when a member is invalid
- `validate()` skips member-checking for domain-only groups

**Parser**
- Scenario without `signal_groups` parses; `scenario.signal_groups == {}`
- Scenario with a single domain group parses; `.domain` is the `ClinicalDomain` enum value
- Scenario with a single custom panel parses; `.members` is a list
- Scenario with multiple groups of mixed types parses
- Missing `description` raises `PSDLParseError`
- Both `domain` and `members` raises `PSDLParseError` mentioning "mutually exclusive"
- Neither `domain` nor `members` raises `PSDLParseError` mentioning "must have either"
- Unknown `domain` value raises `PSDLParseError` mentioning "unknown domain"
- `members` not a list raises `PSDLParseError` mentioning "must be a list"
- **Scenario whose group references an unknown signal raises `PSDLParseError` at parse time** (surfaced by `PSDLScenario.validate()` which the parser invokes before returning)

**Schema (via direct `jsonschema.validate`)**
- A scenario declaring `psdl_version: "0.3"` is **rejected** (pattern-tightening regression guard)
- A scenario declaring `psdl_version: "0.4"` is **rejected** (same guard)
- A scenario declaring `psdl_version: "0.5"` without `signal_groups` validates
- A scenario declaring `psdl_version: "0.5"` with one domain group and one custom panel validates
- A `signal_groups` entry with both `domain` and `members` fails schema validation
- A `signal_groups` entry with an empty `members` list fails schema validation

**Regression**
- All 539 existing tests must continue to pass after the bulk `0.3` → `0.5` header bump in the six files listed in the scope table. The upgrade is purely mechanical (a version string change) and no test logic should need to move.

---

## Release Notes (CHANGELOG v0.5.0)

- **BREAKING:** `psdl_version: "0.3"` is no longer accepted. Scenarios must declare `"0.5"`. All bundled examples and test fixtures have been bumped.
- **Added:** `signal_groups:` top-level section for bulk data requests and custom panels (RFC-0009)
- **Added:** `SignalGroup` dataclass exported from `psdl` and `psdl.core.ir`
- **Added:** `PSDLScenario.signal_groups` field with member-reference validation
- **Added:** JSON Schema support for `signal_groups` (`spec/schema.json` v0.5, including `SignalGroupDefinitions` and `SignalGroup` defs with XOR on `domain`/`members`)
- **Changed:** `psdl-lang` package version bumped to `0.5.0`
- **Changed:** `spec/schema.json` version bumped to `0.5.0`, `$id` path updated to `.../schema/v0.5/scenario`
- **Changed:** `spec/VERSION` bumped to `0.5.0`

---

## Open Questions

1. **Should domain-level groups support filtering?** E.g. `all_labs: { domain: laboratory, filter: "last 7 days" }`. Deferred — filtering is a Dataset Spec concern, not a scenario-level concern.
2. **Can groups reference other groups?** E.g. `comprehensive_panel: { members_from: [renal_panel, coag_panel] }`. Deferred to avoid Phase 1 complexity.
3. **Inspector UX — auto-suggest groups?** E.g. propose a domain-level group when 5+ signals share a `ClinicalDomain`. Out of scope for psdl-lang; an Inspector feature request.

---

## References

- Issue #10 — RFC: Add `signal_groups` section for bulk data requests and custom panels
- RFC-0004 — Dataset Specification (binding layer that groups will inform)
- RFC-0006 — Spec-Driven Compilation (hash model that groups are excluded from)
- RFC-0007 — Extension Mechanism (DRAFT; signal groups is *not* an RFC-0007 extension)
- RFC-0008 — Vendor-Neutral Foundation (source of `ClinicalDomain` used by domain-level groups)
- OHDSI Concept Sets — https://ohdsi.github.io/TheBookOfOhdsi/StandardizedVocabularies.html
- psdl-inspector prototype — `docs/superpowers/specs/2026-04-09-signal-groups-design.md`

---

## Status Log

| Date | Status | Notes |
|------|--------|-------|
| 2026-04-10 | PROPOSED | RFC drafted for v0.5.0 port from psdl-inspector prototype |
