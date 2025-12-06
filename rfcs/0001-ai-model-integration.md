# RFC: AI Model Integration in PSDL

- **RFC Number**: 0001
- **Author(s)**: PSDL Community
- **Status**: Draft
- **Created**: 2025-12-05
- **Updated**: 2025-12-05

## Summary

This RFC proposes extending PSDL to support integration with AI/ML models as first-class components in clinical scenario definitions. The proposal introduces a new `models` section for declaring AI model dependencies and new operators (`predict`, `forecast`, `classify`, `anomaly`) for incorporating model outputs into trend expressions.

## Motivation

Clinical decision support increasingly relies on machine learning models for tasks like:

- **Risk prediction**: Predicting patient deterioration, mortality, readmission
- **Forecasting**: Projecting vital sign trajectories, lab value trends
- **Classification**: Categorizing patient states, identifying phenotypes
- **Anomaly detection**: Identifying unusual patterns in clinical data

Currently, PSDL focuses on rule-based logic with temporal operators. While powerful for explicit clinical criteria, this approach cannot express scenarios that depend on ML model outputs. Integrating AI models would:

1. Enable hybrid decision support combining explicit rules with ML predictions
2. Provide a standard way to reference models across institutions
3. Maintain PSDL's auditability by making model dependencies explicit
4. Support the growing ecosystem of clinical AI tools

### Example Use Case: Early Deterioration Detection

A hospital has trained a gradient boosting model to predict ICU transfer within 24 hours. They want to combine this prediction with explicit clinical rules:

```yaml
scenario: Hybrid_Deterioration_Alert
version: "0.2.0"

signals:
  HR: heart_rate
  RR: respiratory_rate
  SpO2: oxygen_saturation
  NEWS2: news2_score

models:
  deterioration_model:
    type: predict
    name: "icu_transfer_24h"
    registry: "hospital-models"
    version: "2.1.0"
    inputs: [HR, RR, SpO2, NEWS2]
    output: probability  # 0.0 to 1.0

trends:
  high_model_risk:
    expr: predict(deterioration_model) > 0.7
    description: "AI model predicts >70% ICU transfer probability"

  news2_elevated:
    expr: last(NEWS2) >= 5
    description: "NEWS2 score indicates concern"

  vitals_deteriorating:
    expr: slope(HR, 2h) > 0 AND slope(SpO2, 2h) < 0
    description: "Heart rate rising, oxygen falling"

logic:
  escalation_needed:
    expr: high_model_risk AND (news2_elevated OR vitals_deteriorating)
    severity: high
    description: "AI + rules indicate deterioration risk"
```

## Detailed Design

### 1. Models Section

A new top-level `models` section declares AI model dependencies.

#### Syntax

```yaml
models:
  <model_name>:
    type: predict | forecast | classify | anomaly
    name: <string>              # Model identifier in registry
    registry: <string>          # Optional: model registry/source
    version: <string>           # Semantic version
    inputs: [<signal_list>]     # Input signals
    output: <output_type>       # Output specification
    config: <dict>              # Optional: model-specific config
```

#### Output Types

| Type | Description | Example |
|------|-------------|---------|
| `probability` | Single value 0.0-1.0 | Risk prediction |
| `score` | Unbounded numeric | Severity score |
| `class` | Categorical label | `"high"`, `"low"` |
| `timeseries` | Future values | 24h forecast |
| `boolean` | True/False | Anomaly detected |

#### Examples

**Risk Prediction Model:**
```yaml
models:
  aki_predictor:
    type: predict
    name: "aki_48h_v3"
    registry: "ohdsi-models"
    version: "3.2.1"
    inputs: [Cr, BUN, Age, GFR_baseline]
    output: probability
```

**Time Series Forecast:**
```yaml
models:
  lactate_forecast:
    type: forecast
    name: "lactate_lstm"
    registry: "internal"
    version: "1.0.0"
    inputs: [Lactate]
    output: timeseries
    config:
      horizon_hours: 6
      intervals: 6  # One per hour
```

**Anomaly Detection:**
```yaml
models:
  ecg_anomaly:
    type: anomaly
    name: "ecg_autoencoder"
    registry: "cardiology-ai"
    version: "2.0.0"
    inputs: [ECG_waveform]
    output: boolean
    config:
      threshold: 0.95
```

### 2. AI Operators

New operators to use model outputs in trend expressions.

#### `predict(model, [window])`

Get the model's prediction. Optional window for temporal aggregation.

```yaml
trends:
  high_risk:
    expr: predict(aki_predictor) > 0.5

  sustained_high_risk:
    expr: min(predict(aki_predictor), 4h) > 0.5
    description: "Risk stayed above 50% for 4 hours"
```

#### `forecast(model, horizon)`

Get predicted future value at specified horizon.

```yaml
trends:
  lactate_will_rise:
    expr: forecast(lactate_forecast, 3h) > last(Lactate) * 1.5
    description: "Model predicts 50% lactate increase in 3h"
```

#### `classify(model)`

Get classification result (returns string for comparison).

```yaml
trends:
  high_risk_class:
    expr: classify(sepsis_classifier) == "high"
```

#### `anomaly(model)`

Detect anomalies (returns boolean).

```yaml
trends:
  ecg_abnormal:
    expr: anomaly(ecg_anomaly)
    description: "AI detected ECG anomaly"
```

### 3. Type System Extensions

| Type | Description |
|------|-------------|
| `Model` | Reference to declared model |
| `Probability` | Float constrained to [0.0, 1.0] |
| `Forecast` | Time-indexed array of predictions |
| `Classification` | Categorical string |

### 4. Operator Signatures

```
predict(model: Model) -> Float
predict(model: Model, window: Window) -> Float  # Aggregated

forecast(model: Model, horizon: Window) -> Float

classify(model: Model) -> String

anomaly(model: Model) -> Boolean
```

### 5. Runtime Implementation

#### Model Registry Interface

Runtimes must implement a model registry interface:

```python
class ModelRegistry(ABC):
    @abstractmethod
    def get_model(self, name: str, version: str, registry: str) -> Model:
        """Load a model by name and version."""
        pass

    @abstractmethod
    def predict(self, model: Model, inputs: Dict[str, List[DataPoint]]) -> float:
        """Run prediction and return output."""
        pass

    @abstractmethod
    def forecast(self, model: Model, inputs: Dict[str, List[DataPoint]],
                 horizon: timedelta) -> List[DataPoint]:
        """Run forecast and return time series."""
        pass
```

#### Model Adapter Pattern

To support various model formats (ONNX, PMML, TensorFlow, custom):

```python
class ONNXModelAdapter(ModelAdapter):
    def load(self, path: str) -> onnx.ModelProto:
        return onnx.load(path)

    def predict(self, model, inputs):
        session = onnxruntime.InferenceSession(model)
        return session.run(None, inputs)[0]

class PMMLModelAdapter(ModelAdapter):
    def load(self, path: str):
        return PMMLPipeline.load(path)
```

### 6. Execution Semantics

1. **Lazy Evaluation**: Model predictions are computed only when referenced
2. **Caching**: Predictions are cached per evaluation cycle
3. **Error Handling**: Model failures are treated as missing data (trends evaluate to False)
4. **Timeouts**: Model inference must complete within configured timeout

```python
# Example evaluation flow
def evaluate_trend(trend, context):
    if has_model_reference(trend.expr):
        model_ref = extract_model_ref(trend.expr)
        model = context.registry.get_model(
            model_ref.name,
            model_ref.version,
            model_ref.registry
        )

        # Gather inputs
        inputs = {}
        for signal_name in model_ref.inputs:
            inputs[signal_name] = context.get_signal_data(signal_name)

        # Run prediction (with timeout)
        try:
            result = context.registry.predict(model, inputs, timeout=5.0)
            context.cache[model_ref] = result
        except TimeoutError:
            return None  # Treat as missing

        # Evaluate expression with result
        return evaluate_expression(trend.expr, result)
```

## Regulatory Considerations

AI integration adds regulatory complexity. PSDL addresses this through:

### 1. Explicit Model Declaration

All model dependencies are visible in the scenario definition:

```yaml
models:
  my_model:
    name: "fda_cleared_model"
    version: "2.1.0"  # Specific approved version
    registry: "vendor-models"
```

### 2. Version Pinning

Scenarios reference specific model versions, enabling reproducibility:

```yaml
# Bad: Could change behavior unexpectedly
version: "latest"

# Good: Reproducible, auditable
version: "2.1.0"
```

### 3. Audit Trail

Model invocations are logged with inputs and outputs:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "patient_id": "12345",
  "scenario": "Hybrid_Deterioration_Alert",
  "model": "icu_transfer_24h:2.1.0",
  "inputs": {
    "HR": [{"t": "...", "v": 95}, ...],
    "RR": [{"t": "...", "v": 22}, ...]
  },
  "output": 0.73,
  "trend_result": true
}
```

### 4. Fallback Behavior

Scenarios can define behavior when models fail:

```yaml
models:
  risky_model:
    ...
    on_error: skip  # or: alert, default_value

trends:
  model_based:
    expr: predict(risky_model) > 0.5
    fallback: false  # If model fails, trend is false
```

## Drawbacks

### 1. Increased Complexity

- Scenarios become harder to understand
- Runtime must handle model loading, inference, caching
- More failure modes to handle

### 2. Portability Challenges

- Models may not be available across institutions
- Model registries vary (ONNX, PMML, proprietary)
- Input normalization may differ

### 3. Performance Impact

- Model inference adds latency
- Large models may require GPU
- Real-time scenarios may be affected

### 4. Regulatory Burden

- FDA clearance may be required for clinical use
- Model changes require revalidation
- Audit requirements increase

## Alternatives

### Alternative 1: External Signal Source

Treat model outputs as pre-computed signals:

```yaml
signals:
  AKI_Risk:
    source: aki_model_output  # Pre-computed by external system
    unit: probability
```

**Why rejected:** Loses the semantic connection between model and scenario. Model versioning and inputs are not captured. Less auditable.

### Alternative 2: Plugin System

Allow arbitrary code via plugins:

```yaml
plugins:
  - name: model_plugin
    path: ./plugins/model_plugin.py

trends:
  risk:
    expr: plugin.predict("aki_model", Cr, BUN)
```

**Why rejected:** Too flexible, loses type safety. Arbitrary code is harder to audit. No standard interface.

### Alternative 3: DSL Extension for ML

Create a full ML DSL within PSDL:

```yaml
models:
  my_model:
    architecture: gradient_boosting
    features:
      - signal: Cr
        transform: delta(6h)
      - signal: Age
    target: aki_48h
```

**Why rejected:** Scope creep. PSDL should reference models, not define them. Model development has its own ecosystem.

## Prior Art

| System | Approach | Differences |
|--------|----------|-------------|
| **CQL** | External functions via FHIRPath | Less explicit about model semantics |
| **PMML** | Standardized model format | Data format, not scenario language |
| **ONNX** | Model interchange format | Runtime format, no clinical semantics |
| **MLFlow** | Model registry and serving | Infrastructure, not clinical logic |
| **Epic Predictive Model** | Integrated model execution | Proprietary, EHR-specific |

## Open Questions

1. **Model Registry Standard**: Should PSDL define a standard registry interface, or defer to existing standards (MLFlow, ONNX Model Zoo)?

2. **Input Preprocessing**: How should signal transformations for model inputs be specified? In the model declaration or elsewhere?

3. **Ensemble Support**: Should PSDL support combining multiple models explicitly?
   ```yaml
   trends:
     consensus_risk:
       expr: (predict(model_a) + predict(model_b)) / 2 > 0.6
   ```

4. **Explainability**: Should PSDL support model explainability outputs (SHAP, LIME)?

5. **Real-time vs Batch**: Different execution semantics for streaming vs retrospective evaluation?

6. **Model Validation**: Should scenarios include validation constraints?
   ```yaml
   models:
     my_model:
       validation:
         auc_min: 0.75
         calibration_error_max: 0.1
   ```

## Future Possibilities

### Phase 1 (v0.2)
- Basic `predict` operator
- Model declaration syntax
- ONNX/PMML adapters

### Phase 2 (v0.3)
- `forecast`, `classify`, `anomaly` operators
- Model registry interface
- Caching and timeout handling

### Phase 3 (v0.4)
- Ensemble operators
- Explainability integration
- Streaming inference support

### Phase 4 (v1.0)
- Standard model registry protocol
- Regulatory compliance toolkit
- Performance benchmarks

---

## Example: Complete Hybrid Scenario

```yaml
scenario: Sepsis_AI_Enhanced
version: "0.2.0"
description: "AI-enhanced sepsis detection combining ML predictions with clinical rules"

population:
  include:
    - age >= 18
    - unit IN ["ICU", "ED", "Medicine"]

signals:
  # Vitals
  HR:
    source: heart_rate
    concept_id: 3027018
    unit: bpm
  RR:
    source: respiratory_rate
    concept_id: 3024171
    unit: breaths/min
  Temp:
    source: body_temperature
    concept_id: 3020891
    unit: C
  SBP:
    source: systolic_bp
    concept_id: 3004249
    unit: mmHg

  # Labs
  WBC:
    source: wbc_count
    concept_id: 3000905
    unit: 10^9/L
  Lactate:
    source: lactate
    concept_id: 3047181
    unit: mmol/L

models:
  sepsis_predictor:
    type: predict
    name: "sepsis_onset_6h"
    registry: "hospital-ai"
    version: "4.2.0"
    inputs: [HR, RR, Temp, SBP, WBC, Lactate]
    output: probability
    config:
      threshold: 0.6

  lactate_forecaster:
    type: forecast
    name: "lactate_lstm_v2"
    registry: "hospital-ai"
    version: "2.0.1"
    inputs: [Lactate]
    output: timeseries
    config:
      horizon_hours: 6

trends:
  # AI-based trends
  ai_sepsis_risk:
    expr: predict(sepsis_predictor) > 0.6
    description: "AI predicts >60% sepsis probability in 6h"

  ai_lactate_rising:
    expr: forecast(lactate_forecaster, 3h) > last(Lactate) * 1.3
    description: "AI forecasts 30% lactate increase in 3h"

  # Rule-based trends (qSOFA)
  tachypnea:
    expr: last(RR) >= 22
    description: "Respiratory rate >= 22"

  hypotension:
    expr: last(SBP) <= 100
    description: "Systolic BP <= 100 mmHg"

  fever:
    expr: last(Temp) > 38.0 OR last(Temp) < 36.0
    description: "Temperature abnormal"

  lactate_elevated:
    expr: last(Lactate) > 2.0
    description: "Lactate > 2.0 mmol/L"

logic:
  qsofa_positive:
    expr: (tachypnea AND hypotension) OR (tachypnea AND fever) OR (hypotension AND fever)
    severity: medium
    description: "qSOFA >= 2"

  ai_enhanced_sepsis:
    expr: ai_sepsis_risk AND (qsofa_positive OR lactate_elevated)
    severity: high
    description: "AI risk + clinical criteria positive"

  imminent_sepsis:
    expr: ai_enhanced_sepsis AND ai_lactate_rising
    severity: critical
    description: "High AI risk with predicted lactate rise"

triggers:
  - when: imminent_sepsis
    actions:
      - type: notify_team
        target: rapid_response
        priority: critical
        message: "AI + clinical criteria indicate imminent sepsis"
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-05 | PSDL Community | Initial draft |

---

## Discussion

This RFC is open for community feedback. Key discussion points:

1. Is the proposed syntax intuitive for clinical informaticists?
2. Are there model types not covered by `predict/forecast/classify/anomaly`?
3. What model registries should be supported first?
4. How should regulatory requirements influence the design?

Please open a GitHub Discussion or Issue to provide feedback.
