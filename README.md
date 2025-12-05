<p align="center">
  <img src="docs/assets/logo.jpeg" alt="PSDL Logo" width="400"/>
</p>

<h1 align="center">PSDL</h1>
<h3 align="center">Patient Scenario Definition Language</h3>

<p align="center">
  <em>An Open Standard for Clinical Logic, Real-Time Monitoring & AI Integration</em>
</p>

<p align="center">
  <a href="#specification"><img src="https://img.shields.io/badge/Spec-0.1.0-blue?style=flat-square" alt="Spec Version"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-Apache%202.0-green?style=flat-square" alt="License"></a>
  <a href="#contributing"><img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome"></a>
</p>

---

<p align="center">
  <strong>What SQL became for data queries, PSDL aims to become for clinical logic.</strong>
</p>

---

## The Problem

Despite significant advances in clinical AI and machine learning, **real-time decision support in healthcare remains fragmented, non-portable, non-reproducible, and exceptionally difficult to audit or regulate**.

<p align="center">
  <img src="docs/assets/layers.jpeg" alt="Healthcare AI Semantic Stack" width="800"/>
  <br/>
  <em>PSDL fills the missing semantic layer in the healthcare AI stack</em>
</p>

## What is PSDL?

PSDL (Patient Scenario Definition Language) is a declarative, vendor-neutral language for expressing clinical scenarios. It provides a structured way to define:

| Component | Description |
|-----------|-------------|
| **Signals** | Time-series clinical data bindings (labs, vitals, etc.) |
| **Trends** | Temporal computations over signals (deltas, slopes, averages) |
| **Logic** | Boolean algebra combining trends into clinical states |
| **Population** | Criteria for which patients a scenario applies to |
| **Triggers** | Event-condition-action rules (v0.2) |

<p align="center">
  <img src="docs/assets/semantic langauge.jpeg" alt="How PSDL Works" width="800"/>
  <br/>
  <em>Syntax vs Semantics vs Runtime - How PSDL Works</em>
</p>

## Quick Example

```yaml
# Detect early kidney injury
scenario: AKI_Early_Detection
version: "0.1.0"

signals:
  Cr:
    source: creatinine
    concept_id: 3016723  # OMOP concept
    unit: mg/dL

trends:
  cr_rising:
    expr: delta(Cr, 6h) > 0.3
    description: "Creatinine rise > 0.3 mg/dL in 6 hours"

  cr_high:
    expr: last(Cr) > 1.5
    description: "Current creatinine elevated"

logic:
  aki_risk:
    expr: cr_rising AND cr_high
    severity: high
    description: "Early AKI - rising and elevated creatinine"
```

## Why PSDL?

| Challenge | Without PSDL | With PSDL |
|-----------|--------------|-----------|
| **Portability** | Logic tied to specific hospital systems | Same scenario runs anywhere with mapping |
| **Auditability** | Scattered across Python, SQL, configs | Single structured, version-controlled file |
| **Reproducibility** | Hidden state, implicit dependencies | Deterministic execution, explicit semantics |
| **Regulatory Compliance** | Manual documentation | Built-in audit primitives |
| **Research Sharing** | Cannot validate published scenarios | Portable, executable definitions |

## Installation

```bash
# Clone the repository
git clone https://github.com/psdl-lang/psdl.git
cd psdl

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Parse a Scenario

```python
from runtime.python import PSDLParser

parser = PSDLParser()
scenario = parser.parse_file("examples/aki_detection.yaml")

print(f"Scenario: {scenario.name}")
print(f"Signals: {list(scenario.signals.keys())}")
print(f"Logic rules: {list(scenario.logic.keys())}")
```

### Evaluate Against Patient Data

```python
from runtime.python import PSDLParser, PSDLEvaluator, InMemoryBackend
from runtime.python.operators import DataPoint
from datetime import datetime, timedelta

# Parse scenario
parser = PSDLParser()
scenario = parser.parse_file("examples/aki_detection.yaml")

# Set up data backend
backend = InMemoryBackend()
now = datetime.now()

# Add patient data
backend.add_data(
    patient_id=123,
    signal_name="Cr",
    data=[
        DataPoint(now - timedelta(hours=6), 1.0),
        DataPoint(now - timedelta(hours=3), 1.3),
        DataPoint(now, 1.8),
    ]
)

# Evaluate
evaluator = PSDLEvaluator(scenario, backend)
result = evaluator.evaluate_patient(patient_id=123, reference_time=now)

if result.is_triggered:
    print(f"Patient triggered: {result.triggered_logic}")
    print(f"Trend values: {result.trend_values}")
```

## Temporal Operators

| Operator | Syntax | Description |
|----------|--------|-------------|
| `delta` | `delta(signal, window)` | Absolute change over window |
| `slope` | `slope(signal, window)` | Linear regression slope |
| `ema` | `ema(signal, window)` | Exponential moving average |
| `sma` | `sma(signal, window)` | Simple moving average |
| `min` | `min(signal, window)` | Minimum value in window |
| `max` | `max(signal, window)` | Maximum value in window |
| `count` | `count(signal, window)` | Observation count |
| `last` | `last(signal)` | Most recent value |

### Window Formats

- `30s` - 30 seconds
- `5m` - 5 minutes
- `6h` - 6 hours
- `1d` - 1 day
- `7d` - 7 days

## Project Structure

```
psdl/
├── README.md              # This file
├── spec/
│   └── schema-v0.1.yaml   # YAML schema specification
├── runtime/
│   └── python/            # Python reference implementation
│       ├── __init__.py
│       ├── parser.py      # YAML parser
│       ├── evaluator.py   # Scenario evaluator
│       └── operators.py   # Temporal operators
├── examples/
│   ├── icu_deterioration.yaml
│   ├── aki_detection.yaml
│   └── sepsis_screening.yaml
├── docs/
│   ├── getting-started.md
│   ├── WHITEPAPER.md      # Full specification document
│   └── assets/            # Images and diagrams
└── tests/
    ├── test_parser.py
    └── test_evaluator.py
```

## Running Tests

```bash
pytest tests/ -v
```

## Example Scenarios

| Scenario | Description | Clinical Use |
|----------|-------------|--------------|
| **ICU Deterioration** | Monitors for early signs of clinical deterioration | Kidney function, lactate trends, hemodynamics |
| **AKI Detection** | KDIGO criteria for Acute Kidney Injury staging | Creatinine-based staging |
| **Sepsis Screening** | qSOFA + lactate-based sepsis screening | Early sepsis identification |

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Declarative** | Define *what* to detect, not *how* to compute it |
| **Portable** | Same scenario runs on any OMOP/FHIR backend with mapping |
| **Auditable** | Structured format enables static analysis and version control |
| **Deterministic** | Predictable execution with no hidden state |
| **Open** | Vendor-neutral, community-governed |

## Roadmap

### Phase 1: Semantic Foundation [Current]
- [x] Type system definition
- [x] Operator specification
- [x] YAML schema
- [x] Python parser
- [x] Temporal operators
- [x] In-memory evaluator
- [x] Example scenarios
- [x] Unit tests

### Phase 2: Enhanced Runtime
- [ ] OMOP SQL backend
- [ ] FHIR backend
- [ ] Conformance test suite
- [ ] Trigger/Action system (v0.2)

### Phase 3: Community
- [ ] Technical blog series
- [ ] Conference presentations
- [ ] Community infrastructure

### Phase 4: Adoption
- [ ] Hospital pilot programs
- [ ] Standards body engagement (OHDSI, HL7)

## Related Standards

| Standard | Relationship |
|----------|--------------|
| **OMOP CDM** | Data model for signals (concept_id references) |
| **FHIR** | Planned runtime target |
| **CQL** | Similar domain, different scope (quality measures) |
| **ONNX** | Inspiration for portable format approach |

## Documentation

| Document | Description |
|----------|-------------|
| [Whitepaper](docs/WHITEPAPER.md) | Full project vision and specification |
| [Getting Started](docs/getting-started.md) | Quick start guide |
| [Schema](spec/schema-v0.1.yaml) | YAML schema definition |
| [Changelog](CHANGELOG.md) | Version history |

### Whitepaper Translations

| Language | Link |
|----------|------|
| English | [WHITEPAPER_EN.md](docs/WHITEPAPER_EN.md) |
| 简体中文 | [WHITEPAPER_ZH.md](docs/WHITEPAPER_ZH.md) |
| Español | [WHITEPAPER_ES.md](docs/WHITEPAPER_ES.md) |
| Français | [WHITEPAPER_FR.md](docs/WHITEPAPER_FR.md) |
| 日本語 | [WHITEPAPER_JA.md](docs/WHITEPAPER_JA.md) |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Ways to Contribute

- **Specification**: Propose language features, operators, semantics
- **Implementation**: Build runtimes, backends, tooling
- **Documentation**: Improve guides, tutorials, examples
- **Testing**: Add conformance tests, find edge cases
- **Adoption**: Share use cases, pilot experiences

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Clinical AI does not fail because models are weak.<br/>
  It fails because scenario semantics are not formalized.</strong>
</p>

<p align="center">
  <sub>An open standard built by the community, for the community.</sub>
</p>
