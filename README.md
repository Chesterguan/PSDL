<p align="center">
  <img src="docs/assets/logo.jpeg" alt="PSDL Logo" width="400"/>
</p>

<h1 align="center">PSDL</h1>
<h3 align="center">Patient Scenario Definition Language</h3>

<p align="center">
  <em>An Open Standard for Clinical Logic, Real-Time Monitoring & AI Integration</em>
</p>

<p align="center">
  <a href="https://github.com/Chesterguan/PSDL/actions/workflows/ci.yml"><img src="https://github.com/Chesterguan/PSDL/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
  <a href="#specification"><img src="https://img.shields.io/badge/Spec-0.1.0-blue?style=flat-square" alt="Spec Version"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-Apache%202.0-green?style=flat-square" alt="License"></a>
  <a href="#contributing"><img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome"></a>
  <img src="https://img.shields.io/badge/Python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.8-3.12">
</p>

<p align="center">
  <strong>What SQL became for data queries, ONNX for ML models, and GraphQL for APIs —<br/>
  PSDL is becoming the <em>semantic layer</em> for clinical AI.</strong>
</p>

<p align="center">
  📄 <strong>Read the Whitepaper:</strong>
  <a href="docs/WHITEPAPER_EN.md">English</a> ·
  <a href="docs/WHITEPAPER_ZH.md">简体中文</a> ·
  <a href="docs/WHITEPAPER_ES.md">Español</a> ·
  <a href="docs/WHITEPAPER_FR.md">Français</a> ·
  <a href="docs/WHITEPAPER_JA.md">日本語</a>
</p>

---

## Try It Now (No Setup Required)

Run PSDL in your browser with Google Colab - zero installation, real clinical data:

| Notebook | Data | Description |
|----------|------|-------------|
| [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/notebooks/PSDL_Colab_Synthea.ipynb) | **Synthetic** | Quick demo with generated patient data (2 min) |
| [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/notebooks/PSDL_Colab_MIMIC_Demo.ipynb) | **MIMIC-IV Demo** | 100 real ICU patients, ICD diagnoses |
| [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Chesterguan/PSDL/blob/main/notebooks/PSDL_Colab_Sepsis_Challenge.ipynb) | **PhysioNet Sepsis** | 40,000+ patients with labeled sepsis |

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
git clone https://github.com/Chesterguan/PSDL.git
cd psdl

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Parse a Scenario

```python
from psdl import PSDLParser

parser = PSDLParser()
scenario = parser.parse_file("examples/aki_detection.yaml")

print(f"Scenario: {scenario.name}")
print(f"Signals: {list(scenario.signals.keys())}")
print(f"Logic rules: {list(scenario.logic.keys())}")
```

### Evaluate Against Patient Data

```python
from psdl import PSDLParser, PSDLEvaluator, InMemoryBackend
from psdl.operators import DataPoint
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

PSDL follows industry-standard patterns (like GraphQL, CQL, ONNX): 
 - **Specification** defines WHAT
 - **Reference Implementation** shows HOW.

```
psdl/
├── README.md              # This file
├── spec/                  # SPECIFICATION
│   └── schema-v0.1.yaml   # YAML schema + operator semantics
├── src/psdl/              # REFERENCE IMPLEMENTATION (Python)
│   ├── __init__.py
│   ├── parser.py          # YAML parser
│   ├── evaluator.py       # Batch execution mode
│   ├── operators.py       # Temporal operators
│   ├── execution/         # Execution Modes
│   │   ├── batch.py       # Batch mode + SQL compiler
│   │   └── streaming/     # Streaming mode (Flink)
│   └── adapters/          # Data Adapters
│       ├── omop.py        # OMOP CDM adapter (SQL)
│       └── fhir.py        # FHIR R4 adapter (REST)
├── examples/              # Example scenarios
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

| Component | Description |
|-----------|-------------|
| **Specification** | PSDL language definition (YAML schema + operator semantics) |
| **Reference Implementation** | Python implementation demonstrating the spec |
| **Parser** | Parses PSDL YAML into internal representation |
| **Evaluator** | Executes parsed scenarios (batch mode) |
| **Data Adapter** | Interface to clinical data sources (OMOP, FHIR) |

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with verbose output
pytest tests/ -v -s
```

### Test Coverage: 234 Tests (All Passing)

- **Unit Tests**: Parser, evaluator, operators, scenarios
- **Integration Tests**: FHIR adapter, OMOP backend with population filtering
- **Validation**: SQL equivalence (100% match), KDIGO clinical guidelines
- **Streaming Tests**: Window functions, logic evaluation, Flink compiler

See [tests/TEST_VALIDATION.md](tests/TEST_VALIDATION.md) for detailed methodology.

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

| Phase | Status | Focus |
|-------|--------|-------|
| **Phase 1: Semantic Foundation** | ✅ Complete | Spec, parser, operators, OMOP/FHIR adapters, 234 tests |
| **Phase 2: Enhanced Runtime** | 🚧 Current | ✅ Streaming, ✅ SQL generation, triggers, packaging |
| **Phase 3: Community** | 📋 Planned | Blog series, conferences, tooling ecosystem |
| **Phase 4: Adoption** | 🔮 Future | Hospital pilots, standards engagement |

📍 **[View Full Roadmap →](docs/ROADMAP.md)**

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
| [Whitepaper](docs/WHITEPAPER.md) | Full project vision and specification (5 languages) |
| [Getting Started](docs/getting-started.md) | Quick start guide |
| [Roadmap](docs/ROADMAP.md) | Development phases and timeline |
| [Schema](spec/schema-v0.1.yaml) | YAML schema definition |
| [Changelog](CHANGELOG.md) | Version history |

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
  <strong>Clinical AI doesn't fail because models are weak.<br/>
  It fails because there's no semantic layer to express clinical logic portably.</strong>
</p>

<p align="center">
  <em>PSDL is the semantic layer for clinical AI — like SQL for databases.</em>
</p>

<p align="center">
  <sub>An open standard built by the community, for the community.</sub>
</p>
