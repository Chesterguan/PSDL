"""
PSDL Flink Runtime - PyFlink Integration

This module provides the actual PyFlink integration for PSDL streaming scenarios.
It transforms compiled PSDL operators into executable Flink DataStream jobs.

Requirements:
    pip install apache-flink>=1.18

Usage:
    from psdl.streaming import FlinkRuntime

    runtime = FlinkRuntime()
    job = runtime.create_job("scenarios/icu_deterioration.yaml")
    job.execute()
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .compiler import (  # noqa: F401
    CompiledScenario,
    CompiledTrend,
    LogicJoinFunction,
    OperatorType,
    StreamingCompiler,
)
from .config import CheckpointMode, LateDataPolicy, StreamingConfig
from .models import ClinicalEvent, TrendResult

logger = logging.getLogger(__name__)

# Late data output tag (for side output)
LATE_DATA_TAG = "late-clinical-events"

# Try to import PyFlink - graceful fallback if not installed
try:
    from pyflink.common import Types, WatermarkStrategy
    from pyflink.common.serialization import SimpleStringSchema
    from pyflink.common.time import Time
    from pyflink.common.typeinfo import TypeInformation
    from pyflink.common.watermark_strategy import TimestampAssigner
    from pyflink.datastream import (
        DataStream,
        KeyedProcessFunction,
        OutputTag,
        RuntimeContext,
        StreamExecutionEnvironment,
    )
    from pyflink.datastream.connectors.kafka import (
        KafkaOffsetsInitializer,
        KafkaRecordSerializationSchema,
        KafkaSink,
        KafkaSource,
    )
    from pyflink.datastream.state import ValueStateDescriptor

    PYFLINK_AVAILABLE = True
except ImportError:
    PYFLINK_AVAILABLE = False
    # Define stubs for type hints when PyFlink not available
    KeyedProcessFunction = object
    RuntimeContext = Any
    TimestampAssigner = object
    DataStream = Any
    StreamExecutionEnvironment = Any
    OutputTag = Any
    TypeInformation = Any
    Types = None
    WatermarkStrategy = None
    ValueStateDescriptor = None
    logger.warning("PyFlink not installed. Install with: pip install apache-flink>=1.18")


class ClinicalEventTimestampAssigner(TimestampAssigner if PYFLINK_AVAILABLE else object):
    """Extract event time from ClinicalEvent for watermarking."""

    def extract_timestamp(self, value: ClinicalEvent, record_timestamp: int) -> int:
        """Return event timestamp in milliseconds."""
        return int(value.timestamp.timestamp() * 1000)


def create_watermark_strategy(max_lateness_ms: int = 300000) -> "WatermarkStrategy":
    """
    Create watermark strategy for clinical events.

    Args:
        max_lateness_ms: Maximum out-of-orderness in milliseconds (default 5 minutes)

    Returns:
        WatermarkStrategy configured for clinical event processing
    """
    if not PYFLINK_AVAILABLE:
        raise RuntimeError("PyFlink not installed")

    return WatermarkStrategy.for_bounded_out_of_orderness(
        Time.milliseconds(max_lateness_ms)
    ).with_timestamp_assigner(ClinicalEventTimestampAssigner())


class FlinkTrendProcessFunction(KeyedProcessFunction if PYFLINK_AVAILABLE else object):
    """
    PyFlink KeyedProcessFunction for PSDL trend evaluation.

    Handles both window-based operators (delta, slope, etc.) and
    stateful operators (last, ema) using Flink's keyed state.

    Supports late data handling via side output when configured.
    """

    # Output tag for late data side output
    LATE_DATA_OUTPUT_TAG = None

    @classmethod
    def get_late_data_output_tag(cls) -> "OutputTag":
        """Get the OutputTag for late data side output."""
        if cls.LATE_DATA_OUTPUT_TAG is None and PYFLINK_AVAILABLE:
            cls.LATE_DATA_OUTPUT_TAG = OutputTag(LATE_DATA_TAG, Types.STRING())
        return cls.LATE_DATA_OUTPUT_TAG

    def __init__(
        self,
        compiled_trend: "CompiledTrend",
        window_ms: int,
        late_data_policy: LateDataPolicy = LateDataPolicy.DROP,
        allowed_lateness_ms: int = 0,
    ):
        """
        Initialize trend process function.

        Args:
            compiled_trend: Compiled PSDL trend
            window_ms: Window size in milliseconds
            late_data_policy: How to handle late data (DROP, ALLOW, SIDE_OUTPUT)
            allowed_lateness_ms: Additional lateness allowed beyond watermark
        """
        self.compiled_trend = compiled_trend
        self.window_ms = window_ms
        self.trend_name = compiled_trend.name
        self.late_data_policy = late_data_policy
        self.allowed_lateness_ms = allowed_lateness_ms
        self._late_data_count = 0
        self._processed_count = 0

    def open(self, runtime_context: RuntimeContext):
        """Initialize Flink state."""
        # State for windowed events (list of events within window)
        self.events_state = runtime_context.get_list_state(
            ValueStateDescriptor("events", Types.STRING())
        )
        # State for EMA value
        self.ema_state = runtime_context.get_state(ValueStateDescriptor("ema", Types.FLOAT()))
        # State for last value
        self.last_state = runtime_context.get_state(ValueStateDescriptor("last", Types.FLOAT()))
        # State to track current watermark (for late data detection)
        self.watermark_state = runtime_context.get_state(
            ValueStateDescriptor("watermark", Types.LONG())
        )

    def _is_late_data(self, event_time_ms: int, ctx: Any) -> bool:
        """
        Check if the event is considered late based on current watermark.

        Args:
            event_time_ms: Event timestamp in milliseconds
            ctx: Process function context

        Returns:
            True if the event is late (arrived after watermark + allowed_lateness)
        """
        # Get current watermark from timer service
        current_watermark = ctx.timer_service().current_watermark()

        # Event is late if its timestamp is before (watermark - allowed_lateness)
        # Note: Flink watermark represents "no events earlier than this will arrive"
        deadline = current_watermark - self.allowed_lateness_ms
        return event_time_ms < deadline

    def _handle_late_data(self, event: ClinicalEvent, ctx: Any) -> bool:
        """
        Handle late data according to configured policy.

        Args:
            event: The late clinical event
            ctx: Process function context

        Returns:
            True if processing should continue, False if event should be skipped
        """
        self._late_data_count += 1

        if self.late_data_policy == LateDataPolicy.DROP:
            logger.debug(
                f"Dropping late event for trend {self.trend_name}: "
                f"patient={event.patient_id}, time={event.timestamp}"
            )
            return False

        elif self.late_data_policy == LateDataPolicy.SIDE_OUTPUT:
            # Emit to side output for late data handling
            event_json = json.dumps(
                {
                    "patient_id": event.patient_id,
                    "timestamp": event.timestamp.isoformat(),
                    "signal_type": event.signal_type,
                    "value": event.value,
                    "unit": event.unit or "",
                    "source": event.source or "",
                    "trend_name": self.trend_name,
                    "late_data": True,
                    "late_count": self._late_data_count,
                }
            )
            ctx.output(self.get_late_data_output_tag(), event_json)
            logger.debug(
                f"Emitting late event to side output for trend {self.trend_name}: "
                f"patient={event.patient_id}"
            )
            return False

        else:  # LateDataPolicy.ALLOW
            logger.debug(
                f"Allowing late event for trend {self.trend_name}: "
                f"patient={event.patient_id}, time={event.timestamp}"
            )
            return True

    def process_element(self, value: ClinicalEvent, ctx: Any):
        """Process incoming clinical event."""
        patient_id = ctx.get_current_key()
        current_time_ms = int(value.timestamp.timestamp() * 1000)
        self._processed_count += 1

        # Check for late data
        if self._is_late_data(current_time_ms, ctx):
            if not self._handle_late_data(value, ctx):
                return  # Skip processing for dropped/side-output late data

        if self.compiled_trend.operator_type == OperatorType.PROCESS:
            # Stateful processing (last, ema)
            yield from self._process_stateful(value, patient_id, current_time_ms)
        else:
            # Window-based processing (delta, slope, etc.)
            yield from self._process_windowed(value, patient_id, current_time_ms, ctx)

    def _process_stateful(self, event: ClinicalEvent, patient_id: str, current_time_ms: int):
        """Process stateful operators (last, ema)."""
        if self.compiled_trend.process_function:
            # Get current state
            state = {}
            if self.compiled_trend.process_function.__class__.__name__ == "EMAProcessFunction":
                ema_val = self.ema_state.value()
                if ema_val is not None:
                    state["ema"] = ema_val
            else:
                last_val = self.last_state.value()
                if last_val is not None:
                    state["last_value"] = last_val

            # Process event
            result, new_state = self.compiled_trend.process_function.process_element(event, state)

            # Update state
            if "ema" in new_state:
                self.ema_state.update(new_state["ema"])
            if "last_value" in new_state:
                self.last_state.update(new_state["last_value"])

            yield result

    def _process_windowed(self, event: ClinicalEvent, patient_id: str, current_time_ms: int, ctx):
        """Process windowed operators (delta, slope, min, max, count, sma)."""
        # Add event to state (serialize to JSON string)
        event_json = json.dumps(
            {
                "patient_id": event.patient_id,
                "timestamp": event.timestamp.isoformat(),
                "signal_type": event.signal_type,
                "value": event.value,
                "unit": event.unit or "",
                "source": event.source or "",
            }
        )
        self.events_state.add(event_json)

        # Register timer to clean old events
        ctx.timer_service().register_event_time_timer(current_time_ms + self.window_ms)

        # Collect events from state
        events = []
        cutoff_ms = current_time_ms - self.window_ms
        new_events = []

        for event_str in self.events_state.get():
            event_dict = json.loads(event_str)
            event_ts = datetime.fromisoformat(event_dict["timestamp"])
            event_ts_ms = int(event_ts.timestamp() * 1000)

            if event_ts_ms >= cutoff_ms:
                new_events.append(event_str)
                events.append(
                    ClinicalEvent(
                        patient_id=event_dict["patient_id"],
                        timestamp=event_ts,
                        signal_type=event_dict["signal_type"],
                        value=event_dict["value"],
                        unit=event_dict.get("unit"),
                        source=event_dict.get("source"),
                    )
                )

        # Update state with filtered events
        self.events_state.clear()
        for e in new_events:
            self.events_state.add(e)

        # Compute window result
        if events and self.compiled_trend.window_function:
            window_start = min(e.timestamp for e in events)
            window_end = max(e.timestamp for e in events)
            result = self.compiled_trend.window_function.process(
                patient_id, events, window_start, window_end
            )
            yield result

    def on_timer(self, timestamp: int, ctx: Any):
        """Timer callback to clean up old events."""
        # Clean events older than window
        cutoff_ms = timestamp - self.window_ms
        new_events = []

        for event_str in self.events_state.get():
            event_dict = json.loads(event_str)
            event_ts = datetime.fromisoformat(event_dict["timestamp"])
            event_ts_ms = int(event_ts.timestamp() * 1000)

            if event_ts_ms >= cutoff_ms:
                new_events.append(event_str)

        self.events_state.clear()
        for e in new_events:
            self.events_state.add(e)


class FlinkLogicProcessFunction(KeyedProcessFunction if PYFLINK_AVAILABLE else object):
    """
    PyFlink KeyedProcessFunction for PSDL logic evaluation.

    Joins multiple trend streams and evaluates logic expressions.
    """

    def __init__(self, logic_join_fn: LogicJoinFunction, trend_names: List[str]):
        """
        Initialize logic process function.

        Args:
            logic_join_fn: Logic join function from compiler
            trend_names: List of trend names to track
        """
        self.logic_join_fn = logic_join_fn
        self.trend_names = trend_names

    def open(self, runtime_context: RuntimeContext):
        """Initialize Flink state for each trend."""
        self.trend_states = {}
        for trend_name in self.trend_names:
            self.trend_states[trend_name] = runtime_context.get_state(
                ValueStateDescriptor(f"trend_{trend_name}", Types.STRING())
            )

    def process_element(self, value: TrendResult, ctx: Any):
        """Process incoming trend result."""
        patient_id = ctx.get_current_key()

        # Update state for this trend
        if value.trend_name in self.trend_states:
            self.trend_states[value.trend_name].update(
                json.dumps(
                    {
                        "result": value.result,
                        "value": value.value,
                        "timestamp": value.timestamp.isoformat(),
                    }
                )
            )

        # Collect all trend results
        trend_results = {}
        for trend_name, state in self.trend_states.items():
            state_value = state.value()
            if state_value:
                data = json.loads(state_value)
                trend_results[trend_name] = TrendResult(
                    patient_id=patient_id,
                    trend_name=trend_name,
                    value=data["value"],
                    result=data["result"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                )

        # Evaluate logic if all trends present
        result = self.logic_join_fn.process(patient_id, trend_results, value.timestamp)
        if result:
            yield result


class FlinkJob:
    """
    Executable Flink job for a PSDL scenario.

    This class wraps a compiled PSDL scenario into an executable
    Flink DataStream job.
    """

    def __init__(
        self,
        env: "StreamExecutionEnvironment",
        compiled: CompiledScenario,
        name: str,
    ):
        """
        Initialize Flink job.

        Args:
            env: Flink StreamExecutionEnvironment
            compiled: Compiled PSDL scenario
            name: Job name
        """
        self.env = env
        self.compiled = compiled
        self.name = name
        self._job_client = None

    def execute(self) -> Any:
        """Execute the Flink job synchronously."""
        return self.env.execute(self.name)

    def execute_async(self) -> Any:
        """Execute the Flink job asynchronously."""
        self._job_client = self.env.execute_async(self.name)
        return self._job_client

    def get_job_status(self) -> Optional[str]:
        """Get current job status."""
        if self._job_client:
            return str(self._job_client.get_job_status().result())
        return None

    def cancel(self):
        """Cancel the running job."""
        if self._job_client:
            self._job_client.cancel().result()


class FlinkRuntime:
    """
    PSDL Flink Runtime - creates executable Flink jobs from PSDL scenarios.

    This is the main entry point for deploying PSDL scenarios as Flink jobs.
    """

    def __init__(self, parallelism: int = 1, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Flink runtime.

        Args:
            parallelism: Default parallelism for jobs
            config: Additional Flink configuration
        """
        if not PYFLINK_AVAILABLE:
            raise RuntimeError(
                "PyFlink not installed. Install with: pip install apache-flink>=1.18"
            )

        self.parallelism = parallelism
        self.config = config or {}
        self.compiler = StreamingCompiler()

    def create_environment(self) -> "StreamExecutionEnvironment":
        """Create and configure Flink StreamExecutionEnvironment."""
        env = StreamExecutionEnvironment.get_execution_environment()
        env.set_parallelism(self.parallelism)

        # Apply additional configuration
        for key, value in self.config.items():
            env.get_config().set_string(key, str(value))

        return env

    def create_job(
        self,
        scenario: Dict[str, Any],
        kafka_config: Optional[Dict[str, str]] = None,
    ) -> FlinkJob:
        """
        Create a Flink job from a PSDL scenario.

        Args:
            scenario: Parsed PSDL scenario dict
            kafka_config: Kafka connection configuration

        Returns:
            FlinkJob ready for execution
        """
        # Compile the scenario
        compiled = self.compiler.compile(scenario)

        # Create environment
        env = self.create_environment()

        # Configure checkpointing
        self._configure_checkpointing(env, compiled.config)

        # Create the datastream pipeline
        self._build_pipeline(env, compiled, kafka_config)

        return FlinkJob(env, compiled, compiled.name)

    def _configure_checkpointing(self, env: "StreamExecutionEnvironment", config: StreamingConfig):
        """Configure Flink checkpointing from PSDL config."""
        cp_config = config.checkpointing

        if cp_config.interval_ms > 0:
            env.enable_checkpointing(cp_config.interval_ms)

            if cp_config.mode == CheckpointMode.EXACTLY_ONCE:
                from pyflink.datastream import CheckpointingMode

                env.get_checkpoint_config().set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)

            if cp_config.timeout_ms:
                env.get_checkpoint_config().set_checkpoint_timeout(cp_config.timeout_ms)

            if cp_config.min_pause_ms:
                env.get_checkpoint_config().set_min_pause_between_checkpoints(
                    cp_config.min_pause_ms
                )

    def _build_pipeline(
        self,
        env: "StreamExecutionEnvironment",
        compiled: CompiledScenario,
        kafka_config: Optional[Dict[str, str]],
    ):
        """Build the Flink DataStream pipeline."""
        # For now, create a simple test source
        # In production, this would be a Kafka source

        if kafka_config:
            source = self._create_kafka_source(kafka_config, compiled)
        else:
            # Create a test source for local development
            logger.warning("No Kafka config provided, creating test source")
            source = env.from_collection([])

        # Apply watermark strategy
        watermark_strategy = create_watermark_strategy(compiled.config.watermark.max_lateness_ms)

        events_stream = source.assign_timestamps_and_watermarks(watermark_strategy)

        # Create trend streams for each signal
        trend_streams = {}
        late_data_streams = {}  # Collect late data side outputs

        for trend_name, trend in compiled.trends.items():
            signal_name = trend.signal

            # Filter events for this signal
            signal_stream = events_stream.filter(lambda e, sig=signal_name: e.signal_type == sig)

            # Key by patient
            keyed_stream = signal_stream.key_by(lambda e: e.patient_id)

            # Apply trend operator with late data handling
            window_ms = trend.window_spec.size_ms if trend.window_spec else 3600000
            trend_fn = FlinkTrendProcessFunction(
                compiled_trend=trend,
                window_ms=window_ms,
                late_data_policy=compiled.config.late_data_policy,
                allowed_lateness_ms=compiled.config.allowed_lateness_ms,
            )

            trend_stream = keyed_stream.process(trend_fn)
            trend_streams[trend_name] = trend_stream

            # Collect late data side output if policy is SIDE_OUTPUT
            if compiled.config.late_data_policy == LateDataPolicy.SIDE_OUTPUT:
                late_output = trend_stream.get_side_output(
                    FlinkTrendProcessFunction.get_late_data_output_tag()
                )
                late_data_streams[trend_name] = late_output

        # Union all trend streams and evaluate logic
        if trend_streams:
            all_trends = None
            for stream in trend_streams.values():
                if all_trends is None:
                    all_trends = stream
                else:
                    all_trends = all_trends.union(stream)

            # Evaluate logic expressions
            for logic_name, logic in compiled.logic.items():
                logic_join_fn = LogicJoinFunction(logic, compiled.name, compiled.version)
                logic_fn = FlinkLogicProcessFunction(logic_join_fn, logic.trend_refs)

                logic_stream = all_trends.key_by(lambda t: t.patient_id).process(logic_fn)

                # Add sink for logic results
                logic_stream.print()  # For debugging; replace with Kafka sink in production

        # Handle late data side outputs (if any)
        if late_data_streams:
            # Union all late data streams
            all_late_data = None
            for stream in late_data_streams.values():
                if all_late_data is None:
                    all_late_data = stream
                else:
                    all_late_data = all_late_data.union(stream)

            if all_late_data:
                # For debugging; in production, this would go to a separate Kafka topic
                all_late_data.print().name("late-data-sink")
                logger.info(
                    f"Late data side output configured for {len(late_data_streams)} trend streams"
                )

    def _create_kafka_source(
        self, kafka_config: Dict[str, str], compiled: CompiledScenario
    ) -> DataStream:
        """Create Kafka source for clinical events."""
        bootstrap_servers = kafka_config.get("bootstrap_servers", "localhost:9092")
        topic = kafka_config.get("topic", "clinical-events")
        group_id = kafka_config.get("group_id", f"psdl-{compiled.name}")

        source = (
            KafkaSource.builder()
            .set_bootstrap_servers(bootstrap_servers)
            .set_topics(topic)
            .set_group_id(group_id)
            .set_starting_offsets(KafkaOffsetsInitializer.earliest())
            .set_value_only_deserializer(SimpleStringSchema())
            .build()
        )

        return source


def create_kafka_sink(
    bootstrap_servers: str,
    topic: str,
) -> "KafkaSink":
    """
    Create Kafka sink for PSDL alerts.

    Args:
        bootstrap_servers: Kafka bootstrap servers
        topic: Output topic name

    Returns:
        KafkaSink configured for PSDL output
    """
    if not PYFLINK_AVAILABLE:
        raise RuntimeError("PyFlink not installed")

    return (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )


def create_late_data_kafka_sink(
    bootstrap_servers: str,
    topic: str = "psdl-late-data",
) -> "KafkaSink":
    """
    Create Kafka sink for late clinical events.

    Late data events are clinical events that arrived after the watermark deadline.
    These can be processed separately or used for monitoring/alerting.

    Args:
        bootstrap_servers: Kafka bootstrap servers
        topic: Output topic name (default: psdl-late-data)

    Returns:
        KafkaSink configured for late data output
    """
    if not PYFLINK_AVAILABLE:
        raise RuntimeError("PyFlink not installed")

    return (
        KafkaSink.builder()
        .set_bootstrap_servers(bootstrap_servers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .build()
    )


# Convenience function for quick job creation
def run_scenario(
    scenario_path: str,
    kafka_bootstrap_servers: str = "localhost:9092",
    kafka_topic: str = "clinical-events",
) -> FlinkJob:
    """
    Convenience function to run a PSDL scenario as a Flink job.

    Args:
        scenario_path: Path to PSDL scenario YAML file
        kafka_bootstrap_servers: Kafka bootstrap servers
        kafka_topic: Input Kafka topic

    Returns:
        Running FlinkJob
    """
    import yaml

    with open(scenario_path, "r") as f:
        scenario = yaml.safe_load(f)

    runtime = FlinkRuntime()
    job = runtime.create_job(
        scenario,
        kafka_config={
            "bootstrap_servers": kafka_bootstrap_servers,
            "topic": kafka_topic,
        },
    )

    return job
