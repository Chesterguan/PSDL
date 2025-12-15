"""
Data models for PSDL streaming execution.

Defines the event schema and result types used throughout the streaming pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import Severity from core IR (single source of truth)
from psdl.core.ir import Severity


@dataclass
class ClinicalEvent:
    """
    Base event type for clinical data in streaming pipeline.

    All events share this common envelope for consistent processing.
    Maps to Flink's event schema requirements.
    """

    patient_id: str
    timestamp: datetime
    signal_type: str
    value: float
    unit: str
    source: str = "unknown"

    # Optional metadata
    concept_id: Optional[int] = None  # OMOP concept ID
    fhir_resource_id: Optional[str] = None
    location: Optional[str] = None

    # Processing metadata
    ingestion_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patient_id": self.patient_id,
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "concept_id": self.concept_id,
            "fhir_resource_id": self.fhir_resource_id,
            "location": self.location,
            "ingestion_time": self.ingestion_time.isoformat() if self.ingestion_time else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClinicalEvent":
        """Create from dictionary."""
        return cls(
            patient_id=data["patient_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            signal_type=data["signal_type"],
            value=float(data["value"]),
            unit=data.get("unit", ""),
            source=data.get("source", "unknown"),
            concept_id=data.get("concept_id"),
            fhir_resource_id=data.get("fhir_resource_id"),
            location=data.get("location"),
            ingestion_time=(
                datetime.fromisoformat(data["ingestion_time"])
                if data.get("ingestion_time")
                else None
            ),
        )


@dataclass
class TrendResult:
    """
    Result of evaluating a PSDL trend.

    Emitted by window/process functions after computing temporal operators.
    """

    patient_id: str
    trend_name: str
    value: float  # Computed value (e.g., delta, slope, ema)
    result: bool  # Whether the trend condition is satisfied
    timestamp: datetime
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None

    # Debug info
    input_count: int = 0
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patient_id": self.patient_id,
            "trend_name": self.trend_name,
            "value": self.value,
            "result": self.result,
            "timestamp": self.timestamp.isoformat(),
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "input_count": self.input_count,
            "description": self.description,
        }


@dataclass
class LogicResult:
    """
    Result of evaluating a PSDL logic expression.

    Emitted after combining multiple trend results.
    """

    patient_id: str
    logic_name: str
    result: bool
    severity: Severity
    timestamp: datetime

    # Contributing trends
    trend_inputs: Dict[str, bool] = field(default_factory=dict)

    # Metadata
    description: Optional[str] = None
    scenario_name: Optional[str] = None
    scenario_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patient_id": self.patient_id,
            "logic_name": self.logic_name,
            "result": self.result,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "trend_inputs": self.trend_inputs,
            "description": self.description,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
        }


@dataclass
class Alert:
    """
    Alert generated when a trigger fires.

    Final output of the streaming pipeline for clinical action.
    """

    alert_id: str
    patient_id: str
    trigger_name: str
    logic_name: str
    severity: Severity
    timestamp: datetime

    # Context
    message: Optional[str] = None
    actions: List[str] = field(default_factory=list)

    # Audit trail
    scenario_name: Optional[str] = None
    scenario_version: Optional[str] = None
    logic_result: Optional[LogicResult] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "patient_id": self.patient_id,
            "trigger_name": self.trigger_name,
            "logic_name": self.logic_name,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "actions": self.actions,
            "scenario_name": self.scenario_name,
            "scenario_version": self.scenario_version,
            "logic_result": self.logic_result.to_dict() if self.logic_result else None,
        }


@dataclass
class StreamingWindowSpec:
    """
    Window specification for Flink streaming operators.

    Different from AST WindowSpec - this is for Flink window configuration.
    Parsed from PSDL expressions like delta(HR, 1h, 30s).
    """

    size_ms: int  # Window size in milliseconds
    slide_ms: int  # Slide interval in milliseconds

    @classmethod
    def from_psdl(cls, window_str: str, slide_str: Optional[str] = None) -> "StreamingWindowSpec":
        """
        Parse window specification from PSDL syntax.

        Args:
            window_str: Window size (e.g., "1h", "30m", "24h")
            slide_str: Optional slide interval (e.g., "30s", "1m")

        Returns:
            WindowSpec with size and slide in milliseconds
        """
        size_ms = cls._parse_duration(window_str)

        if slide_str:
            slide_ms = cls._parse_duration(slide_str)
        else:
            # Default slide based on window size
            slide_ms = cls._default_slide(size_ms)

        return cls(size_ms=size_ms, slide_ms=slide_ms)

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
            raise ValueError(f"Invalid duration format: {duration_str}")

    @staticmethod
    def _default_slide(window_ms: int) -> int:
        """
        Calculate default slide interval based on window size.

        From RFC-0002:
        | Window Size | Default Slide |
        |-------------|---------------|
        | < 1m        | 1s            |
        | 1m - 10m    | 10s           |
        | 10m - 1h    | 1m            |
        | 1h - 24h    | 5m            |
        | > 24h       | 15m           |
        """
        ONE_MINUTE = 60 * 1000
        TEN_MINUTES = 10 * 60 * 1000
        ONE_HOUR = 60 * 60 * 1000
        ONE_DAY = 24 * 60 * 60 * 1000

        if window_ms < ONE_MINUTE:
            return 1000  # 1s
        elif window_ms < TEN_MINUTES:
            return 10 * 1000  # 10s
        elif window_ms < ONE_HOUR:
            return ONE_MINUTE  # 1m
        elif window_ms < ONE_DAY:
            return 5 * ONE_MINUTE  # 5m
        else:
            return 15 * ONE_MINUTE  # 15m
