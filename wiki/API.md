# PSDL API Reference

> Developer documentation for `psdl-lang` v0.3

## Installation

```bash
pip install psdl-lang          # Core package
pip install psdl-lang[omop]    # With OMOP adapter
pip install psdl-lang[fhir]    # With FHIR adapter
pip install psdl-lang[full]    # All adapters
```

---

## Quick Reference

```python
from psdl import (
    # Parsing
    PSDLParser, PSDLScenario,

    # Compilation (v0.3)
    compile_scenario, ScenarioCompiler, ScenarioIR,

    # Evaluation
    SinglePatientEvaluator, InMemoryBackend,

    # AST types
    parse_trend_expression, parse_logic_expression,
    extract_operators, extract_terms,

    # Adapters
    get_omop_adapter, get_fhir_adapter,

    # Examples
    examples,
)
```

---

## Core API

### `PSDLParser`

Parse PSDL YAML scenarios into `PSDLScenario` objects.

```python
from psdl import PSDLParser

parser = PSDLParser()

# Parse from file
scenario = parser.parse_file("scenario.yaml")

# Parse from string
yaml_content = """
scenario: MyScenario
version: "1.0"
signals:
  HR:
    ref: heart_rate
"""
scenario = parser.parse(yaml_content)
```

**Methods:**
| Method | Returns | Description |
|--------|---------|-------------|
| `parse(yaml_str)` | `PSDLScenario` | Parse YAML string |
| `parse_file(path)` | `PSDLScenario` | Parse YAML file |

---

### `PSDLScenario`

Parsed scenario representation.

```python
scenario = parser.parse_file("scenario.yaml")

print(scenario.name)           # Scenario name
print(scenario.version)        # Version string
print(scenario.signals)        # Dict[str, Signal]
print(scenario.trends)         # Dict[str, TrendExpr]
print(scenario.logic)          # Dict[str, LogicExpr]
print(scenario.population)     # Optional population criteria
print(scenario.audit)          # Audit metadata (intent, rationale, provenance)
```

**Attributes:**
| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Scenario name |
| `version` | `str` | Scenario version |
| `signals` | `Dict[str, Signal]` | Signal definitions |
| `trends` | `Dict[str, TrendExpr]` | Trend definitions |
| `logic` | `Dict[str, LogicExpr]` | Logic rules |
| `population` | `Optional[PopulationCriteria]` | Population filters |
| `audit` | `Optional[AuditBlock]` | Audit metadata |

---

## Compilation API (v0.3)

### `compile_scenario()`

Compile a scenario to IR with cryptographic hashes for audit trails.

```python
from psdl import compile_scenario

# From file path
ir = compile_scenario("scenario.yaml")

# From PSDLScenario object
ir = compile_scenario(scenario)

# Access hashes
print(ir.spec_hash)        # SHA-256 of input YAML
print(ir.ir_hash)          # SHA-256 of compiled IR
print(ir.toolchain_hash)   # SHA-256 of compiler version
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `source` | `str \| PSDLScenario` | File path or parsed scenario |

**Returns:** `ScenarioIR`

---

### `ScenarioIR`

Compiled intermediate representation with DAG ordering and hashes.

```python
ir = compile_scenario("scenario.yaml")

# Metadata
print(ir.scenario_name)
print(ir.scenario_version)
print(ir.psdl_version)
print(ir.compiled_at)      # datetime

# Hashes (for audit)
print(ir.spec_hash)
print(ir.ir_hash)
print(ir.toolchain_hash)

# DAG ordering
print(ir.dag.evaluation_order)  # Ordered list of (type, name)

# Export for audit
artifact = ir.to_artifact()  # Dict for JSON serialization
```

**Key Attributes:**
| Attribute | Type | Description |
|-----------|------|-------------|
| `spec_hash` | `str` | SHA-256 of input specification |
| `ir_hash` | `str` | SHA-256 of compiled IR |
| `toolchain_hash` | `str` | SHA-256 of compiler version |
| `dag` | `DependencyDAG` | Evaluation order |
| `diagnostics` | `CompilationDiagnostics` | Warnings/errors |

---

### `ScenarioCompiler`

Low-level compiler with fine-grained control.

```python
from psdl import ScenarioCompiler, PSDLParser

parser = PSDLParser()
scenario = parser.parse_file("scenario.yaml")

compiler = ScenarioCompiler()
ir = compiler.compile(scenario)

# Access diagnostics
for warning in ir.diagnostics.warnings:
    print(f"Warning: {warning.message}")
```

---

## Evaluation API

### `SinglePatientEvaluator`

Evaluate a scenario against single patient data.

```python
from psdl import SinglePatientEvaluator, InMemoryBackend, compile_scenario
from datetime import datetime, timedelta

# Setup backend with data
backend = InMemoryBackend()
now = datetime.now()
backend.add_observation(123, "Cr", 1.0, now - timedelta(hours=6))
backend.add_observation(123, "Cr", 1.5, now)

# From compiled IR (recommended)
ir = compile_scenario("scenario.yaml")
evaluator = SinglePatientEvaluator.from_ir(ir, backend)

# Or from scenario directly
evaluator = SinglePatientEvaluator(scenario, backend)

# Evaluate
result = evaluator.evaluate(patient_id=123, reference_time=now)

print(result.is_triggered)      # bool
print(result.triggered_logic)   # List[str]
print(result.trend_values)      # Dict[str, float]
print(result.logic_values)      # Dict[str, bool]
```

**Methods:**
| Method | Returns | Description |
|--------|---------|-------------|
| `evaluate(patient_id, reference_time)` | `EvaluationResult` | Evaluate scenario |
| `from_ir(ir, backend)` | `SinglePatientEvaluator` | Create from compiled IR |

---

### `InMemoryBackend`

In-memory data backend for testing and development.

```python
from psdl import InMemoryBackend, DataPoint
from datetime import datetime

backend = InMemoryBackend()

# Add single observation
backend.add_observation(
    patient_id=123,
    signal_name="Cr",
    value=1.5,
    timestamp=datetime.now()
)

# Add multiple data points
backend.add_patient_data(123, {
    "Cr": [
        DataPoint(timestamp=datetime(2024, 1, 1, 10, 0), value=1.0),
        DataPoint(timestamp=datetime(2024, 1, 1, 16, 0), value=1.5),
    ],
    "HR": [
        DataPoint(timestamp=datetime(2024, 1, 1, 10, 0), value=72),
    ]
})

# Query data
data = backend.get_signal_data(123, "Cr", window_seconds=3600)
```

**Methods:**
| Method | Description |
|--------|-------------|
| `add_observation(patient_id, signal_name, value, timestamp)` | Add single data point |
| `add_patient_data(patient_id, data_dict)` | Add multiple signals |
| `get_signal_data(patient_id, signal_name, window_seconds)` | Query data |

---

### `EvaluationResult`

Result of scenario evaluation.

```python
result = evaluator.evaluate(patient_id=123)

# Basic results
print(result.is_triggered)       # Any logic rule triggered?
print(result.triggered_logic)    # List of triggered rule names
print(result.highest_severity)   # Highest severity level

# Detailed values
print(result.trend_values)       # {"cr_delta": 0.5, ...}
print(result.logic_values)       # {"aki_risk": True, ...}

# v0.3: Standardized output
standard = result.to_standard_result()
```

---

## Expression Parsing API

### `parse_trend_expression()`

Parse a trend expression into AST.

```python
from psdl import parse_trend_expression

ast = parse_trend_expression("delta(Cr, 6h)")
print(ast.temporal.operator)   # "delta"
print(ast.temporal.signal)     # "Cr"
print(ast.temporal.window)     # WindowSpec(value=6, unit='h')
```

---

### `parse_logic_expression()`

Parse a logic expression into AST.

```python
from psdl import parse_logic_expression

ast = parse_logic_expression("cr_rising AND cr_high")
# Returns AndExpr with operands

ast = parse_logic_expression("cr_delta > 0.3")
# Returns ComparisonExpr
```

---

### `extract_operators()`

Extract operator calls from an expression string.

```python
from psdl import extract_operators

ops = extract_operators("delta(Cr, 6h) > 0.3")
# [TemporalCall(operator='delta', signal='Cr', window=WindowSpec(6, 'h'))]
```

---

### `extract_terms()`

Extract term references from a logic expression.

```python
from psdl import extract_terms

terms = extract_terms("cr_rising AND bp_low OR shock_index")
# ['cr_rising', 'bp_low', 'shock_index']
```

---

## AST Types

### Expression AST Nodes

```python
from psdl import (
    # Trend expressions
    TrendExpression,    # Wrapper for temporal call
    TemporalCall,       # delta(Cr, 6h)
    WindowSpec,         # 6h, 30m, etc.

    # Logic expressions
    LogicNode,          # Union type for all logic nodes
    TermRef,            # Reference to a trend/logic name
    ComparisonExpr,     # cr_delta > 0.3
    AndExpr,            # a AND b AND c
    OrExpr,             # a OR b
    NotExpr,            # NOT a
)
```

**`TemporalCall`:**
```python
@dataclass
class TemporalCall:
    operator: str      # delta, slope, ema, sma, min, max, count, last
    signal: str        # Signal name
    window: Optional[WindowSpec]
    percentile: Optional[int]  # For percentile operator
```

**`WindowSpec`:**
```python
@dataclass
class WindowSpec:
    value: int         # Numeric value
    unit: str          # 's', 'm', 'h', 'd', 'w'

    @property
    def seconds(self) -> int:
        """Window duration in seconds"""
```

---

## Data Adapters

### OMOP Adapter

```python
from psdl import get_omop_adapter

OMOPAdapter = get_omop_adapter()

adapter = OMOPAdapter(
    connection_string="postgresql://user:pass@host/db",
    cdm_schema="cdm",
    vocab_schema="vocab"
)

# Use with evaluator
evaluator = SinglePatientEvaluator(scenario, adapter)
```

---

### FHIR Adapter

```python
from psdl import get_fhir_adapter

FHIRAdapter = get_fhir_adapter()

adapter = FHIRAdapter(
    base_url="http://hapi.fhir.org/baseR4",
    auth_token="optional_bearer_token"
)

# Use with evaluator
evaluator = SinglePatientEvaluator(scenario, adapter)
```

---

## Built-in Examples

```python
from psdl import examples

# List available scenarios
print(examples.list_scenarios())
# ['aki_detection', 'sepsis_screening', 'hyperkalemia_detection', ...]

# Load a scenario
scenario = examples.get_scenario("aki_detection")

# Get scenario file path
path = examples.get_scenario_path("aki_detection")
```

---

## Type Reference

### Core Types

| Type | Description |
|------|-------------|
| `Signal` | Signal definition (ref, concept_id, unit) |
| `TrendExpr` | Trend expression with metadata |
| `LogicExpr` | Logic rule with severity |
| `DataPoint` | Single observation (timestamp, value) |
| `EvaluationResult` | Evaluation output |

### AST Types

| Type | Description |
|------|-------------|
| `WindowSpec` | Time window (value + unit) |
| `TemporalCall` | Operator call (delta, slope, etc.) |
| `TrendExpression` | Numeric trend expression |
| `ComparisonExpr` | Comparison (>, <, ==, etc.) |
| `AndExpr` | Logical AND |
| `OrExpr` | Logical OR |
| `NotExpr` | Logical NOT |
| `TermRef` | Reference to named term |
| `LogicNode` | Union of all logic AST types |

### Compiler Types

| Type | Description |
|------|-------------|
| `ScenarioIR` | Compiled intermediate representation |
| `DependencyDAG` | Evaluation order graph |
| `CompilationDiagnostics` | Warnings and errors |

---

## Version History

| Version | Changes |
|---------|---------|
| 0.3.0 | v0.3 architecture, compile_scenario(), AST exposure |
| 0.2.0 | Streaming support, FHIR adapter |
| 0.1.0 | Initial release |

---

*Last updated: December 15, 2025*
