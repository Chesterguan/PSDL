"""
Configuration for PSDL streaming execution.

Defines settings for Flink runtime, checkpointing, watermarks, and connectors.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ExecutionMode(Enum):
    """PSDL execution mode."""

    BATCH = "batch"
    STREAMING = "streaming"


class CheckpointMode(Enum):
    """Flink checkpoint mode."""

    EXACTLY_ONCE = "exactly_once"
    AT_LEAST_ONCE = "at_least_once"


class LateDataPolicy(Enum):
    """Policy for handling late data."""

    DROP = "drop"
    ALLOW = "allow"
    SIDE_OUTPUT = "side_output"


class ErrorHandling(Enum):
    """Error handling strategy."""

    SKIP = "skip"
    FAIL = "fail"
    DEFAULT_VALUE = "default_value"
    DEAD_LETTER_QUEUE = "dead_letter_queue"


@dataclass
class WatermarkConfig:
    """Watermark configuration for event time processing."""

    max_lateness_ms: int = 5 * 60 * 1000  # 5 minutes default
    idle_timeout_ms: int = 30 * 1000  # 30 seconds

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatermarkConfig":
        """Create from PSDL config dict."""
        max_lateness = data.get("max_lateness", "5m")
        idle_timeout = data.get("idle_timeout", "30s")

        return cls(
            max_lateness_ms=cls._parse_duration(max_lateness),
            idle_timeout_ms=cls._parse_duration(idle_timeout),
        )

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse duration string to milliseconds."""
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("ms"):
            return int(duration_str[:-2])
        elif duration_str.endswith("s"):
            return int(duration_str[:-1]) * 1000
        elif duration_str.endswith("m"):
            return int(duration_str[:-1]) * 60 * 1000
        elif duration_str.endswith("h"):
            return int(duration_str[:-1]) * 60 * 60 * 1000
        else:
            raise ValueError(f"Invalid duration: {duration_str}")


@dataclass
class CheckpointConfig:
    """Checkpoint configuration for fault tolerance."""

    interval_ms: int = 60 * 1000  # 60 seconds
    mode: CheckpointMode = CheckpointMode.EXACTLY_ONCE
    timeout_ms: int = 10 * 60 * 1000  # 10 minutes
    min_pause_ms: int = 30 * 1000  # 30 seconds
    storage_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointConfig":
        """Create from PSDL config dict."""
        return cls(
            interval_ms=cls._parse_duration(data.get("interval", "60s")),
            mode=CheckpointMode(data.get("mode", "exactly_once")),
            timeout_ms=cls._parse_duration(data.get("timeout", "10m")),
            min_pause_ms=cls._parse_duration(data.get("min_pause", "30s")),
            storage_path=data.get("storage"),
        )

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse duration string to milliseconds."""
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("ms"):
            return int(duration_str[:-2])
        elif duration_str.endswith("s"):
            return int(duration_str[:-1]) * 1000
        elif duration_str.endswith("m"):
            return int(duration_str[:-1]) * 60 * 1000
        elif duration_str.endswith("h"):
            return int(duration_str[:-1]) * 60 * 60 * 1000
        else:
            raise ValueError(f"Invalid duration: {duration_str}")


@dataclass
class KafkaSourceConfig:
    """Kafka source connector configuration."""

    bootstrap_servers: str
    topic: str
    group_id: str = "psdl-streaming"
    format: str = "json"  # json, fhir_observation, hl7v2
    starting_offset: str = "latest"  # latest, earliest, timestamp

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KafkaSourceConfig":
        """Create from PSDL config dict."""
        return cls(
            bootstrap_servers=data["bootstrap_servers"],
            topic=data["topic"],
            group_id=data.get("group_id", "psdl-streaming"),
            format=data.get("format", "json"),
            starting_offset=data.get("starting_offset", "latest"),
        )


@dataclass
class KafkaSinkConfig:
    """Kafka sink connector configuration."""

    bootstrap_servers: str
    topic: str
    key_field: str = "patient_id"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KafkaSinkConfig":
        """Create from PSDL config dict."""
        return cls(
            bootstrap_servers=data["bootstrap_servers"],
            topic=data["topic"],
            key_field=data.get("key_field", "patient_id"),
        )


@dataclass
class JDBCSinkConfig:
    """JDBC sink connector configuration for audit logging."""

    connection_string: str
    table: str
    batch_size: int = 100
    flush_interval_ms: int = 5000

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JDBCSinkConfig":
        """Create from PSDL config dict."""
        return cls(
            connection_string=data["connection"],
            table=data["table"],
            batch_size=data.get("batch_size", 100),
            flush_interval_ms=data.get("flush_interval_ms", 5000),
        )


@dataclass
class ErrorHandlingConfig:
    """Error handling configuration."""

    missing_signal: ErrorHandling = ErrorHandling.SKIP
    invalid_value: ErrorHandling = ErrorHandling.SKIP
    parse_error: ErrorHandling = ErrorHandling.DEAD_LETTER_QUEUE
    dead_letter_topic: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorHandlingConfig":
        """Create from PSDL config dict."""
        return cls(
            missing_signal=ErrorHandling(data.get("missing_signal", "skip")),
            invalid_value=ErrorHandling(data.get("invalid_value", "skip")),
            parse_error=ErrorHandling(data.get("parse_error", "dead_letter_queue")),
            dead_letter_topic=data.get("dead_letter", {}).get("topic"),
        )


@dataclass
class StreamingConfig:
    """
    Complete streaming configuration for a PSDL scenario.

    Parsed from the `execution` section of a PSDL scenario file.
    """

    mode: ExecutionMode = ExecutionMode.STREAMING
    parallelism: int = 1
    state_ttl_ms: int = 48 * 60 * 60 * 1000  # 48 hours

    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)
    checkpointing: CheckpointConfig = field(default_factory=CheckpointConfig)
    error_handling: ErrorHandlingConfig = field(default_factory=ErrorHandlingConfig)

    # Late data handling
    late_data_policy: LateDataPolicy = LateDataPolicy.DROP
    allowed_lateness_ms: int = 0  # Additional lateness beyond watermark

    # Source configs (keyed by source name)
    sources: Dict[str, Any] = field(default_factory=dict)

    # Sink configs (keyed by sink name)
    sinks: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_scenario(cls, scenario: Dict[str, Any]) -> "StreamingConfig":
        """
        Create StreamingConfig from parsed PSDL scenario.

        Args:
            scenario: Parsed PSDL scenario dict

        Returns:
            StreamingConfig instance
        """
        execution = scenario.get("execution", {})

        config = cls(
            mode=ExecutionMode(execution.get("mode", "streaming")),
            parallelism=execution.get("parallelism", 1),
        )

        # Parse state TTL
        if "state_ttl" in execution:
            config.state_ttl_ms = config._parse_duration(execution["state_ttl"])

        # Parse late data handling
        late_data = execution.get("late_data", {})
        if "policy" in late_data:
            config.late_data_policy = LateDataPolicy(late_data["policy"])
        if "allowed_lateness" in late_data:
            config.allowed_lateness_ms = config._parse_duration(late_data["allowed_lateness"])

        # Parse watermark config
        if "watermark" in execution:
            config.watermark = WatermarkConfig.from_dict(execution["watermark"])

        # Parse checkpoint config
        if "checkpointing" in execution:
            config.checkpointing = CheckpointConfig.from_dict(execution["checkpointing"])

        # Parse error handling
        if "error_handling" in execution:
            config.error_handling = ErrorHandlingConfig.from_dict(execution["error_handling"])

        # Parse sources
        for name, source_config in scenario.get("sources", {}).items():
            source_type = source_config.get("type", "kafka")
            if source_type == "kafka":
                config.sources[name] = KafkaSourceConfig.from_dict(source_config.get("config", {}))
            # Add other source types as needed

        # Parse sinks
        for name, sink_config in scenario.get("sinks", {}).items():
            sink_type = sink_config.get("type", "kafka")
            if sink_type == "kafka":
                config.sinks[name] = KafkaSinkConfig.from_dict(sink_config.get("config", {}))
            elif sink_type == "jdbc":
                config.sinks[name] = JDBCSinkConfig.from_dict(sink_config.get("config", {}))
            # Add other sink types as needed

        return config

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse duration string to milliseconds."""
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("ms"):
            return int(duration_str[:-2])
        elif duration_str.endswith("s"):
            return int(duration_str[:-1]) * 1000
        elif duration_str.endswith("m"):
            return int(duration_str[:-1]) * 60 * 1000
        elif duration_str.endswith("h"):
            return int(duration_str[:-1]) * 60 * 60 * 1000
        elif duration_str.endswith("d"):
            return int(duration_str[:-1]) * 24 * 60 * 60 * 1000
        else:
            raise ValueError(f"Invalid duration: {duration_str}")
