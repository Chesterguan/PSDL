# RFC: Streaming Execution with Apache Flink

- **RFC Number**: 0002
- **Author(s)**: PSDL Community
- **Status**: ✅ Implemented
- **GitHub Issue**: [#1](https://github.com/Chesterguan/PSDL/issues/1)
- **Created**: 2025-12-06
- **Updated**: 2025-12-12

## Summary

This RFC proposes a streaming execution backend for PSDL using Apache Flink (PyFlink). It defines how PSDL scenarios compile to Flink streaming primitives, enabling real-time clinical event processing with millisecond latency for deterioration detection, sepsis alerts, and other time-critical clinical decision support.

---

## ⚠️ Implementation Note (2025-12-12)

**Core streaming functionality is implemented** in `src/psdl/runtimes/streaming/`.

### Clarification: Scenario vs Runtime Config

This RFC originally showed `execution:`, `sources:`, and `sinks:` blocks within scenario files. After RFC-0004 review, this has been **clarified**:

| Block | Belongs In | Rationale |
|-------|-----------|-----------|
| `signals`, `trends`, `logic`, `audit` | **Scenario** | Clinical intent (WHAT) |
| `sources`, `sinks`, `checkpointing` | **Runtime Config** | Infrastructure (HOW) |
| `execution.mode` | **Runtime Config** | Execution choice |

**Scenarios remain pure clinical intent.** Infrastructure configuration lives in separate runtime config files. See [Runtime Configuration Reference](../docs/runtime-config-reference.md) for samples.

The examples below show both scenario (pure) and runtime config (infrastructure) for clarity.

---

## Motivation

PSDL v0.1 supports batch evaluation: scenarios are evaluated against historical patient data to produce point-in-time results. While essential for research and retrospective analysis, healthcare increasingly demands **real-time** evaluation:

| Use Case | Latency Requirement | Current Support |
|----------|---------------------|-----------------|
| ICU deterioration alerts | < 1 second | No |
| Sepsis screening | < 30 seconds | No |
| Medication safety checks | < 5 seconds | No |
| Retrospective research | Minutes-hours | Yes |

### Why Streaming Matters for Clinical AI

1. **Patient Safety**: Deterioration detection loses value with each second of delay
2. **Workflow Integration**: Real-time alerts integrate with clinical workflows
3. **Resource Efficiency**: Process events once as they arrive, not repeatedly in batch
4. **HL7/FHIR Streams**: Modern EHR integrations emit event streams

### Why Apache Flink?

| Criterion | Apache Flink | Spark Structured Streaming |
|-----------|--------------|---------------------------|
| Processing Model | True event-at-a-time | Micro-batch |
| Latency | Milliseconds | Seconds (batch interval) |
| Event Time Support | First-class watermarks | Good, more complex |
| Windowing | Native, flexible | Good |
| State Management | Excellent keyed state | Heavier |
| Python Support | PyFlink (mature since 1.16) | PySpark |
| Healthcare Adoption | Growing (HL7/FHIR processing) | Established |

**Decision**: Flink's event-at-a-time model aligns naturally with PSDL's temporal operators. Clinical deterioration detection requires true streaming, not micro-batches.

## Detailed Design

### 1. Execution Modes

PSDL scenarios gain an explicit execution mode:

```yaml
scenario: ICU_Deterioration
version: "0.2.0"
execution:
  mode: streaming  # or "batch" (default)
  checkpoint_interval: 60s
  late_data_policy: allow_1h
```

| Mode | Description | Backend |
|------|-------------|---------|
| `batch` | Evaluate against historical data (default) | Python evaluator, SQL |
| `streaming` | Continuous evaluation on event streams | Flink |

### 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        PSDL Scenario                            │
│  (YAML: signals, trends, logic, triggers)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     PSDL Compiler                               │
│  - Parse scenario                                               │
│  - Build operator DAG                                           │
│  - Generate Flink job                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Flink Runtime                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Source  │───▶│  Signal  │───▶│  Trend   │───▶│  Logic   │  │
│  │ (Kafka)  │    │ KeyedStr │    │ Windows  │    │  Output  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Output Sinks                               │
│  - Kafka (alerts)                                               │
│  - REST webhooks                                                │
│  - Database (audit log)                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3. PSDL to Flink Operator Mapping

This is the core intellectual contribution: how PSDL's declarative operators compile to Flink streaming primitives.

#### 3.1 Signal → KeyedStream

Each PSDL signal becomes a Flink `KeyedStream` partitioned by patient ID:

```python
# PSDL
signals:
  HR: heart_rate

# Flink (PyFlink)
hr_stream = (
    env.from_source(kafka_source, watermark_strategy, "HR Source")
    .filter(lambda e: e.signal_type == "heart_rate")
    .key_by(lambda e: e.patient_id)
)
```

#### 3.2 Temporal Operators → Window Functions

| PSDL Operator | Flink Primitive | Implementation |
|---------------|-----------------|----------------|
| `last(signal)` | `KeyedProcessFunction` | Stateful, emit on each event |
| `delta(signal, window, [slide])` | `SlidingEventTimeWindow` + `ProcessWindowFunction` | last - first in window |
| `slope(signal, window, [slide])` | `SlidingEventTimeWindow` + `ProcessWindowFunction` | Linear regression |
| `sma(signal, window, [slide])` | `SlidingEventTimeWindow` + `AggregateFunction` | Running average |
| `ema(signal, window)` | `KeyedProcessFunction` | Stateful exponential decay |
| `min(signal, window, [slide])` | `SlidingEventTimeWindow` + `min()` | Built-in |
| `max(signal, window, [slide])` | `SlidingEventTimeWindow` + `max()` | Built-in |
| `count(signal, window, [slide])` | `SlidingEventTimeWindow` + `count()` | Built-in |

#### Configurable Slide Intervals

Window-based operators accept an optional third parameter for slide interval:

```yaml
trends:
  # Default slide (window_size / 10, minimum 1s)
  hr_rise_default:
    expr: delta(HR, 1h) > 20

  # Custom slide interval: evaluate every 30 seconds
  hr_rise_fast:
    expr: delta(HR, 1h, 30s) > 20

  # Tumbling window (slide = window): non-overlapping
  hr_rise_tumbling:
    expr: delta(HR, 1h, 1h) > 20
```

Default slide intervals by window size:

| Window Size | Default Slide |
|-------------|---------------|
| < 1m | 1s |
| 1m - 10m | 10s |
| 10m - 1h | 1m |
| 1h - 24h | 5m |
| > 24h | 15m |

#### 3.3 Example: `delta(HR, 1h)` Compilation

```python
# PSDL
trends:
  hr_rise:
    expr: delta(HR, 1h) > 20

# Compiles to Flink
class DeltaWindowFunction(ProcessWindowFunction):
    def process(self, key, context, elements):
        sorted_elements = sorted(elements, key=lambda e: e.timestamp)
        if len(sorted_elements) >= 2:
            first = sorted_elements[0].value
            last = sorted_elements[-1].value
            delta = last - first
            yield DeltaResult(patient_id=key, value=delta, window_end=context.window().end)

hr_delta_stream = (
    hr_stream
    .window(SlidingEventTimeWindows.of(Time.hours(1), Time.minutes(1)))
    .process(DeltaWindowFunction())
)
```

#### 3.4 Example: `ema(HR, 1h)` Compilation

EMA requires stateful processing (not pure windowing):

```python
# PSDL
trends:
  hr_smoothed:
    expr: ema(HR, 1h) > 100

# Compiles to Flink
class EMAProcessFunction(KeyedProcessFunction):
    def __init__(self, alpha: float):
        self.alpha = alpha  # Decay factor based on window

    def open(self, runtime_context):
        # Initialize state
        self.ema_state = runtime_context.get_state(
            ValueStateDescriptor("ema", Types.FLOAT())
        )

    def process_element(self, value, ctx):
        current_ema = self.ema_state.value()
        if current_ema is None:
            new_ema = value.value
        else:
            new_ema = self.alpha * value.value + (1 - self.alpha) * current_ema

        self.ema_state.update(new_ema)
        yield EMAResult(patient_id=ctx.get_current_key(), value=new_ema, timestamp=value.timestamp)

hr_ema_stream = hr_stream.process(EMAProcessFunction(alpha=0.1))
```

#### 3.5 Logic → Stream Joins

PSDL logic expressions combine multiple trends. In streaming, this requires joining streams:

```python
# PSDL
logic:
  deterioration:
    expr: hr_rise AND bp_drop

# Compiles to Flink (CoProcessFunction for two streams)
class LogicJoinFunction(CoProcessFunction):
    def open(self, runtime_context):
        self.hr_rise_state = runtime_context.get_state(
            ValueStateDescriptor("hr_rise", Types.BOOLEAN())
        )
        self.bp_drop_state = runtime_context.get_state(
            ValueStateDescriptor("bp_drop", Types.BOOLEAN())
        )

    def process_element1(self, hr_rise_event, ctx):
        self.hr_rise_state.update(hr_rise_event.value)
        bp_drop = self.bp_drop_state.value()
        if bp_drop is not None:
            yield LogicResult(
                patient_id=ctx.get_current_key(),
                result=hr_rise_event.value and bp_drop,
                timestamp=hr_rise_event.timestamp
            )

    def process_element2(self, bp_drop_event, ctx):
        self.bp_drop_state.update(bp_drop_event.value)
        hr_rise = self.hr_rise_state.value()
        if hr_rise is not None:
            yield LogicResult(
                patient_id=ctx.get_current_key(),
                result=hr_rise and bp_drop_event.value,
                timestamp=bp_drop_event.timestamp
            )

deterioration_stream = (
    hr_rise_stream
    .connect(bp_drop_stream)
    .key_by(lambda e: e.patient_id, lambda e: e.patient_id)
    .process(LogicJoinFunction())
)
```

For N-way logic (more than 2 trends), we use `KeyedCoProcessFunction` chains or Flink's `PatternStream` CEP.

#### 3.6 Triggers → Flink CEP

PSDL triggers (v0.2) map to Flink's Complex Event Processing:

```python
# PSDL
triggers:
  - when: deterioration
    sustained: 5m
    actions:
      - type: alert
        target: rapid_response

# Compiles to Flink CEP
pattern = (
    Pattern.begin("start")
    .where(lambda e: e.logic_name == "deterioration" and e.result == True)
    .times_or_more(1)
    .consecutive()
    .within(Time.minutes(5))
)

cep_stream = CEP.pattern(logic_stream.key_by(lambda e: e.patient_id), pattern)

alerts = cep_stream.select(lambda pattern_events: Alert(
    patient_id=pattern_events["start"][0].patient_id,
    trigger="deterioration_sustained",
    timestamp=pattern_events["start"][-1].timestamp
))
```

### 4. Data Model

#### 4.1 Event Schema

All events in the streaming pipeline share a common envelope:

```python
@dataclass
class ClinicalEvent:
    patient_id: str
    timestamp: datetime  # Event time (when it occurred)
    signal_type: str     # PSDL signal name
    value: float
    unit: str
    source: str          # HL7, FHIR, manual, etc.

    # Optional metadata
    concept_id: Optional[int] = None  # OMOP concept
    fhir_resource_id: Optional[str] = None
```

#### 4.2 Watermark Strategy

Event time processing requires watermarks to handle late data:

```python
class ClinicalWatermarkStrategy(WatermarkStrategy):
    """
    Clinical events may arrive late due to:
    - Manual entry delays
    - Lab result processing time
    - System integration latency
    """

    def __init__(self, max_out_of_orderness: timedelta = timedelta(minutes=5)):
        self.max_out_of_orderness = max_out_of_orderness

    def create_watermark_generator(self):
        return BoundedOutOfOrdernessWatermarks(self.max_out_of_orderness)
```

Configuration in PSDL:

```yaml
execution:
  mode: streaming
  watermark:
    max_lateness: 5m
    idle_timeout: 30s
```

### 5. Connectors

#### 5.1 Source Connectors

| Source | Use Case | Configuration |
|--------|----------|---------------|
| Kafka | HL7v2/FHIR streams | `bootstrap_servers`, `topic`, `group_id` |
| Kinesis | AWS healthcare streams | `stream_name`, `region` |
| JDBC | Polling from OMOP/EHR | `connection_string`, `poll_interval` |
| FHIR Subscription | FHIR R4 webhooks | `fhir_server`, `subscription_id` |

```yaml
# PSDL connector config
sources:
  vitals:
    type: kafka
    config:
      bootstrap_servers: "kafka:9092"
      topic: "hl7.vitals"
      format: fhir_observation

  labs:
    type: fhir_subscription
    config:
      server: "https://fhir.hospital.org/r4"
      criteria: "Observation?category=laboratory"
```

#### 5.2 Sink Connectors

| Sink | Use Case | Configuration |
|------|----------|---------------|
| Kafka | Alert stream | `topic`, `key` |
| REST Webhook | EHR integration | `url`, `auth` |
| PostgreSQL | Audit log | `connection_string`, `table` |
| Slack/Teams | Notifications | `webhook_url` |

```yaml
sinks:
  alerts:
    type: kafka
    config:
      topic: "psdl.alerts"

  audit:
    type: jdbc
    config:
      connection: "postgresql://..."
      table: "psdl_audit_log"
```

### 6. State Management

Flink provides robust state management essential for clinical streaming:

#### 6.1 Checkpointing

```yaml
execution:
  mode: streaming
  checkpointing:
    interval: 60s
    mode: exactly_once  # or at_least_once
    timeout: 10m
    min_pause: 30s
    storage: "s3://psdl-checkpoints/"
```

#### 6.2 State TTL

Clinical state should expire (patient discharged, scenario no longer relevant):

```python
state_descriptor = ValueStateDescriptor("patient_state", Types.ROW(...))
state_descriptor.enable_time_to_live(
    StateTtlConfig.new_builder(Time.hours(48))
    .set_update_type(StateTtlConfig.UpdateType.OnReadAndWrite)
    .build()
)
```

```yaml
execution:
  state_ttl: 48h  # Default state expiration
```

#### 6.3 Savepoints

For scenario updates without data loss:

```bash
# Take savepoint before update
flink savepoint <job_id> s3://psdl-savepoints/

# Restart with new scenario version
flink run -s s3://psdl-savepoints/<savepoint_id> psdl_job.py
```

### 7. Compiler Implementation

The PSDL compiler transforms scenarios into Flink jobs:

```python
class PSDLFlinkCompiler:
    """Compiles PSDL scenarios to Flink DataStream jobs."""

    def compile(self, scenario: ParsedScenario) -> FlinkJob:
        # 1. Build operator DAG
        dag = self._build_dag(scenario)

        # 2. Generate Flink code
        env = StreamExecutionEnvironment.get_execution_environment()

        # 3. Create source streams
        sources = self._create_sources(env, scenario.signals, scenario.sources)

        # 4. Compile trends to window/process functions
        trend_streams = {}
        for trend_name, trend in scenario.trends.items():
            trend_streams[trend_name] = self._compile_trend(
                sources, trend
            )

        # 5. Compile logic to join functions
        logic_streams = {}
        for logic_name, logic in scenario.logic.items():
            logic_streams[logic_name] = self._compile_logic(
                trend_streams, logic
            )

        # 6. Compile triggers to CEP patterns
        if scenario.triggers:
            self._compile_triggers(logic_streams, scenario.triggers)

        # 7. Add sinks
        self._add_sinks(logic_streams, scenario.sinks)

        return FlinkJob(env, scenario.name)

    def _compile_trend(self, sources: Dict[str, DataStream], trend: Trend) -> DataStream:
        """Compile a PSDL trend to Flink operators."""
        operator = parse_operator(trend.expr)

        if operator.name == "last":
            return self._compile_last(sources, operator)
        elif operator.name == "delta":
            return self._compile_delta(sources, operator)
        elif operator.name == "slope":
            return self._compile_slope(sources, operator)
        elif operator.name == "ema":
            return self._compile_ema(sources, operator)
        # ... etc

    def _compile_delta(self, sources: Dict[str, DataStream], operator: Operator) -> DataStream:
        signal_name = operator.args[0]
        window_size = parse_window(operator.args[1])

        return (
            sources[signal_name]
            .window(SlidingEventTimeWindows.of(
                Time.milliseconds(window_size.total_seconds() * 1000),
                Time.minutes(1)  # Slide interval
            ))
            .process(DeltaWindowFunction())
        )
```

### 8. Deployment

#### 8.1 Standalone Mode

```bash
# Compile scenario to Flink job
psdl compile --streaming scenarios/icu_deterioration.yaml -o job.py

# Submit to Flink cluster
flink run job.py
```

#### 8.2 Session Mode (Development)

```python
# Interactive development
from psdl.streaming import StreamingEvaluator

evaluator = StreamingEvaluator()
job = evaluator.compile("scenarios/icu_deterioration.yaml")
job.execute_async()

# Monitor
job.get_job_status()
```

#### 8.3 Kubernetes (Production)

```yaml
# flink-deployment.yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: psdl-streaming
spec:
  image: psdl/flink-runtime:1.18
  flinkVersion: v1_18
  flinkConfiguration:
    taskmanager.numberOfTaskSlots: "4"
    state.checkpoints.dir: s3://psdl-checkpoints/
  serviceAccount: flink
  jobManager:
    resource:
      memory: "2048m"
      cpu: 1
  taskManager:
    resource:
      memory: "4096m"
      cpu: 2
  job:
    jarURI: local:///opt/psdl/psdl-streaming.jar
    args:
      - "--scenario=/config/icu_deterioration.yaml"
    state: running
```

### 9. Monitoring & Observability

#### 9.1 Metrics

PSDL streaming jobs expose standard Flink metrics plus PSDL-specific ones:

| Metric | Description |
|--------|-------------|
| `psdl.events.processed` | Total events processed |
| `psdl.trends.evaluated` | Trend evaluations per second |
| `psdl.logic.true_count` | Logic conditions triggering |
| `psdl.alerts.generated` | Alerts produced |
| `psdl.latency.e2e` | End-to-end latency (event time to alert) |
| `psdl.watermark.lag` | Current watermark lag |

#### 9.2 Alerting

```yaml
monitoring:
  metrics:
    - name: e2e_latency_p99
      threshold: 5s
      action: page_oncall

    - name: checkpoint_duration
      threshold: 30s
      action: slack_alert
```

#### 9.3 Audit Logging

Every logic evaluation is logged for regulatory compliance:

```json
{
  "timestamp": "2025-12-06T10:30:00.123Z",
  "patient_id": "P12345",
  "scenario": "ICU_Deterioration",
  "scenario_version": "0.2.0",
  "logic": "deterioration",
  "result": true,
  "inputs": {
    "hr_rise": {"value": true, "delta": 25, "window": "1h"},
    "bp_drop": {"value": true, "delta": -15, "window": "30m"}
  },
  "processing_time_ms": 12,
  "flink_task": "Logic-Join-1",
  "checkpoint_id": 42
}
```

### 10. Error Handling

#### 10.1 Data Quality Issues

```yaml
execution:
  error_handling:
    missing_signal: skip  # or: fail, default_value
    invalid_value: log_and_skip
    parse_error: dead_letter_queue

  dead_letter:
    type: kafka
    topic: "psdl.errors"
```

#### 10.2 Processing Failures

```python
class ResilientTrendFunction(ProcessWindowFunction):
    def process(self, key, context, elements):
        try:
            result = self._compute(elements)
            yield result
        except Exception as e:
            # Log but don't fail the job
            self.metrics.counter("trend_errors").inc()
            logger.error(f"Trend computation failed for {key}: {e}")
            # Optionally emit to side output
            context.output(error_tag, ErrorEvent(key, str(e)))
```

### 11. Testing

#### 11.1 Unit Testing Compiled Operators

```python
def test_delta_window_function():
    """Test delta computation in isolation."""
    function = DeltaWindowFunction()

    events = [
        ClinicalEvent(patient_id="P1", timestamp=t0, value=80),
        ClinicalEvent(patient_id="P1", timestamp=t0 + timedelta(minutes=30), value=95),
        ClinicalEvent(patient_id="P1", timestamp=t0 + timedelta(hours=1), value=105),
    ]

    result = list(function.process("P1", mock_context, events))
    assert len(result) == 1
    assert result[0].value == 25  # 105 - 80
```

#### 11.2 Integration Testing with MiniCluster

```python
def test_full_scenario_streaming():
    """Test complete scenario on Flink MiniCluster."""
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    # Compile scenario
    compiler = PSDLFlinkCompiler()
    job = compiler.compile(parse_scenario("icu_deterioration.yaml"))

    # Inject test events
    test_source = env.from_collection([
        ClinicalEvent("P1", t0, "HR", 80),
        ClinicalEvent("P1", t0 + timedelta(hours=1), "HR", 110),
        # ... more events
    ])

    # Collect results
    results = list(job.execute_and_collect())

    assert any(r.logic_name == "deterioration" and r.result == True for r in results)
```

#### 11.3 Equivalence Testing (Batch vs Streaming)

Critical: streaming results must match batch evaluation for the same data:

```python
def test_streaming_batch_equivalence():
    """Verify streaming produces same results as batch."""
    scenario = parse_scenario("icu_deterioration.yaml")
    test_data = load_test_data("patient_timeline.json")

    # Batch evaluation
    batch_evaluator = Evaluator()
    batch_results = batch_evaluator.evaluate(scenario, test_data)

    # Streaming evaluation (replay mode)
    streaming_evaluator = StreamingEvaluator(mode="replay")
    streaming_results = streaming_evaluator.evaluate(scenario, test_data)

    # Results must match
    assert batch_results == streaming_results
```

## Example: Complete Streaming Scenario

```yaml
scenario: ICU_Deterioration_Streaming
version: "0.2.0"
description: "Real-time ICU deterioration detection"

execution:
  mode: streaming
  checkpointing:
    interval: 60s
    mode: exactly_once
  watermark:
    max_lateness: 5m
  state_ttl: 48h

sources:
  vitals:
    type: kafka
    config:
      bootstrap_servers: "kafka:9092"
      topic: "icu.vitals"
      format: fhir_observation

signals:
  HR:
    source: vitals
    filter: code.coding[0].code == "8867-4"  # LOINC heart rate
    unit: bpm

  SBP:
    source: vitals
    filter: code.coding[0].code == "8480-6"  # LOINC systolic BP
    unit: mmHg

  SpO2:
    source: vitals
    filter: code.coding[0].code == "2708-6"  # LOINC O2 sat
    unit: "%"

trends:
  hr_rising:
    expr: delta(HR, 1h) > 20
    description: "Heart rate increased >20 bpm in past hour"

  bp_dropping:
    expr: delta(SBP, 30m) < -15
    description: "Systolic BP dropped >15 mmHg in past 30 min"

  hypoxia:
    expr: last(SpO2) < 92
    description: "Current SpO2 below 92%"

  hr_trend_up:
    expr: slope(HR, 2h) > 5
    description: "Heart rate trending upward"

logic:
  early_warning:
    expr: hr_rising OR bp_dropping
    severity: medium

  deterioration:
    expr: (hr_rising AND bp_dropping) OR (hypoxia AND hr_trend_up)
    severity: high

  critical:
    expr: hypoxia AND bp_dropping AND hr_rising
    severity: critical

triggers:
  - when: deterioration
    sustained: 2m
    actions:
      - type: kafka
        topic: "alerts.deterioration"
      - type: webhook
        url: "https://ehr.hospital.org/api/alerts"

  - when: critical
    actions:
      - type: page
        target: rapid_response_team
        priority: critical

sinks:
  alerts:
    type: kafka
    config:
      topic: "psdl.alerts"

  audit:
    type: jdbc
    config:
      connection: "${AUDIT_DB_URL}"
      table: "psdl_streaming_audit"

monitoring:
  metrics_port: 9090
  health_check: /health
```

## Drawbacks

### 1. Operational Complexity

- Flink clusters require expertise to operate
- Checkpointing, state management add complexity
- More failure modes than batch processing

**Mitigation**: Provide managed deployment options (Kubernetes operator, cloud-native).

### 2. Resource Requirements

- Flink clusters need dedicated compute
- State storage requires durable backends (S3, HDFS)
- Higher infrastructure cost than batch

**Mitigation**: Support serverless Flink (AWS Kinesis Data Analytics, Confluent Cloud).

### 3. Debugging Difficulty

- Distributed system debugging is harder
- Event time vs processing time confusion
- Watermark issues can be subtle

**Mitigation**: Comprehensive logging, replay mode for debugging, clear documentation.

### 4. PyFlink Limitations

- Some advanced features require Java/Scala
- Performance overhead vs JVM native
- Ecosystem smaller than PySpark

**Mitigation**: Python-first for adoption, optional Scala backend for performance-critical deployments.

## Alternatives Considered

### Alternative 1: Spark Structured Streaming

**Pros**: Larger ecosystem, more familiar to data engineers
**Cons**: Micro-batch model adds latency, less natural fit for PSDL operators
**Decision**: Rejected for v0.2, consider for v0.3 as additional backend

### Alternative 2: Kafka Streams

**Pros**: Lightweight, no separate cluster needed
**Cons**: JVM-only, less powerful windowing, harder state management
**Decision**: Rejected, too limited for complex PSDL scenarios

### Alternative 3: Custom Streaming Engine

**Pros**: Perfect fit for PSDL semantics
**Cons**: Massive engineering effort, reinventing the wheel
**Decision**: Rejected, leverage mature streaming infrastructure

### Alternative 4: ksqlDB

**Pros**: SQL-based, easy to use
**Cons**: Limited expressiveness, hard to extend
**Decision**: Rejected, PSDL needs programmatic flexibility

## Design Decisions

1. **Window Slide Intervals**: Configurable per operator. Each temporal operator can specify its own slide interval, defaulting to a sensible value based on window size.

2. **Late Data Handling**: Default `max_lateness: 5m` is reasonable for most clinical environments. Configurable per scenario.

3. **Model Integration**: AI model latency should be configurable in the model declaration (RFC-0001). Streaming evaluation respects model timeout settings.

## Open Questions

1. **Multi-Patient Logic**: Some scenarios may need cross-patient aggregations (outbreak detection). How to support this? See Future Possibilities section for proposed approach.

2. **Backpressure Signals**: Should PSDL expose backpressure as a signal for operational scenarios?

3. **Schema Evolution**: How to handle signal schema changes without restarting jobs?

## Implementation Plan

### Phase 1: Core Streaming (v0.2.0) ✅ Complete
- [x] PyFlink backend infrastructure (`flink_runtime.py`)
- [x] Operator compilation (delta, slope, ema, last, min, max, count, sma)
- [x] Logic join functions
- [x] Kafka source/sink connectors
- [x] Basic checkpointing configuration
- [x] Unit and integration tests (41 tests)

### Phase 2: Production Readiness (v0.2.1)
- [ ] FHIR subscription source
- [ ] Trigger/CEP compilation
- [ ] State TTL management
- [ ] Monitoring/metrics
- [ ] Kubernetes deployment
- [ ] Documentation

### Phase 3: Advanced Features (v0.3.0)
- [ ] Savepoint management
- [ ] Schema evolution support
- [ ] Spark Streaming backend (alternative)
- [ ] AI model integration (with RFC-0001)
- [ ] Performance benchmarks

## Future Possibilities

### Multi-Patient Logic (Outbreak Detection)

Some clinical scenarios require cross-patient aggregations. Proposed syntax for v0.3+:

```yaml
scenario: Outbreak_Detection
version: "0.3.0"

execution:
  mode: streaming
  scope: population  # Enable multi-patient logic

signals:
  Fever:
    source: vitals
    filter: code == "8310-5"  # Body temperature

  Location:
    source: adt
    type: categorical

trends:
  # Per-patient trend
  has_fever:
    expr: last(Fever) > 38.0

logic:
  # Per-patient logic
  febrile_patient:
    expr: has_fever

  # Population-level logic (new)
  population:
    outbreak_suspected:
      expr: count(febrile_patient, group_by=Location, window=4h) >= 5
      description: "5+ febrile patients in same location within 4 hours"
      severity: high

triggers:
  - when: outbreak_suspected
    actions:
      - type: notify
        target: infection_control
```

Implementation approach:
- Population logic uses **global windows** instead of keyed streams
- `group_by` creates sub-aggregations within the global window
- Results fan out to all matching patients (or infection control)

### AI Model Streaming Integration

Coordination with RFC-0001 for real-time inference:

```yaml
models:
  sepsis_predictor:
    type: predict
    name: "sepsis_onset_6h"
    version: "4.2.0"
    inputs: [HR, RR, Temp, SBP]
    output: probability
    streaming:
      timeout: 500ms          # Max latency for streaming
      fallback: last_value    # Use cached prediction if timeout
      cache_ttl: 5m           # How long to cache predictions
      batch_size: 1           # Online inference (no batching)
```

The streaming evaluator will:
1. Invoke model with configured timeout
2. On timeout: use `fallback` strategy (last_value, skip, or default)
3. Cache predictions to reduce inference load
4. Log latency metrics for monitoring

## Prior Art

| System | Approach | Relevance |
|--------|----------|-----------|
| **Apache Flink** | Stream processing engine | Core technology |
| **ksqlDB** | Streaming SQL | Similar declarative approach |
| **Esper** | Complex event processing | CEP patterns |
| **Siddhi** | Stream processor for IoT | Healthcare use cases |
| **Epic Cogito** | Real-time clinical analytics | Proprietary, similar goals |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-06 | PSDL Community | Initial draft |

---

## Discussion

This RFC is open for community feedback. Key discussion points:

1. Is PyFlink the right choice vs JVM-native Flink?
2. Are the operator-to-Flink mappings correct and complete?
3. What additional connectors are needed for healthcare environments?
4. How should we handle the batch/streaming equivalence guarantee?
5. What are the minimum viable features for v0.2.0?

Please open a GitHub Discussion or Issue to provide feedback.
