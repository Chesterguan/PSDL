"""
Tests for PSDL Streaming Backend.

Tests the streaming compiler, operators, and evaluation logic.

NOTE: These tests validate the streaming backend logic without requiring Flink.
The actual Flink integration (PyFlink runtime) is optional - these tests
verify the core streaming operators, compiler, and evaluator work correctly.
"""

from datetime import datetime, timedelta

from psdl.execution.streaming import compiler as _compiler
from psdl.execution.streaming import config as _config
from psdl.execution.streaming import operators as _operators

# Import from the psdl package
from psdl.execution.streaming.models import (
    ClinicalEvent,
    Severity,
    StreamingWindowSpec,
    TrendResult,
)

DeltaWindowFunction = _operators.DeltaWindowFunction
SlopeWindowFunction = _operators.SlopeWindowFunction
SMAWindowFunction = _operators.SMAWindowFunction
MinWindowFunction = _operators.MinWindowFunction
MaxWindowFunction = _operators.MaxWindowFunction
CountWindowFunction = _operators.CountWindowFunction
LastProcessFunction = _operators.LastProcessFunction
EMAProcessFunction = _operators.EMAProcessFunction

ExpressionParser = _compiler.ExpressionParser
LogicEvaluator = _compiler.LogicEvaluator
StreamingCompiler = _compiler.StreamingCompiler
LogicJoinFunction = _compiler.LogicJoinFunction
StreamingEvaluator = _compiler.StreamingEvaluator
OperatorType = _compiler.OperatorType

StreamingConfig = _config.StreamingConfig
ExecutionMode = _config.ExecutionMode
CheckpointMode = _config.CheckpointMode


class TestStreamingWindowSpec:
    """Test StreamingWindowSpec parsing and defaults."""

    def test_parse_seconds(self):
        spec = StreamingWindowSpec.from_psdl("30s")
        assert spec.size_ms == 30000

    def test_parse_minutes(self):
        spec = StreamingWindowSpec.from_psdl("5m")
        assert spec.size_ms == 5 * 60 * 1000

    def test_parse_hours(self):
        spec = StreamingWindowSpec.from_psdl("2h")
        assert spec.size_ms == 2 * 60 * 60 * 1000

    def test_parse_days(self):
        spec = StreamingWindowSpec.from_psdl("1d")
        assert spec.size_ms == 24 * 60 * 60 * 1000

    def test_default_slide_small_window(self):
        """Windows < 1m should have 1s slide."""
        spec = StreamingWindowSpec.from_psdl("30s")
        assert spec.slide_ms == 1000

    def test_default_slide_medium_window(self):
        """Windows 1m-10m should have 10s slide."""
        spec = StreamingWindowSpec.from_psdl("5m")
        assert spec.slide_ms == 10000

    def test_default_slide_large_window(self):
        """Windows 1h-24h should have 5m slide."""
        spec = StreamingWindowSpec.from_psdl("2h")
        assert spec.slide_ms == 5 * 60 * 1000

    def test_custom_slide(self):
        """Custom slide interval."""
        spec = StreamingWindowSpec.from_psdl("1h", "30s")
        assert spec.size_ms == 60 * 60 * 1000
        assert spec.slide_ms == 30000


class TestClinicalEvent:
    """Test ClinicalEvent data model."""

    def test_create_event(self):
        event = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime(2024, 1, 15, 10, 30),
            signal_type="HR",
            value=85.0,
            unit="bpm",
            source="monitor",
        )
        assert event.patient_id == "P123"
        assert event.value == 85.0

    def test_to_dict(self):
        event = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime(2024, 1, 15, 10, 30),
            signal_type="HR",
            value=85.0,
            unit="bpm",
            source="monitor",
        )
        d = event.to_dict()
        assert d["patient_id"] == "P123"
        assert d["signal_type"] == "HR"
        assert d["value"] == 85.0

    def test_from_dict(self):
        d = {
            "patient_id": "P123",
            "timestamp": "2024-01-15T10:30:00",
            "signal_type": "HR",
            "value": 85.0,
            "unit": "bpm",
            "source": "monitor",
        }
        event = ClinicalEvent.from_dict(d)
        assert event.patient_id == "P123"
        assert event.value == 85.0


class TestWindowFunctions:
    """Test window-based operators."""

    def create_events(self, values, start_time=None, interval_minutes=10):
        """Helper to create a series of events."""
        if start_time is None:
            start_time = datetime(2024, 1, 15, 10, 0)

        events = []
        for i, value in enumerate(values):
            events.append(
                ClinicalEvent(
                    patient_id="P123",
                    timestamp=start_time + timedelta(minutes=i * interval_minutes),
                    signal_type="HR",
                    value=value,
                    unit="bpm",
                    source="test",
                )
            )
        return events

    def test_delta_rising(self):
        """Test delta with rising values."""
        fn = DeltaWindowFunction("hr_rise", threshold=20, comparison=">")
        events = self.create_events([80, 85, 90, 95, 105])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == 25  # 105 - 80
        assert result.result is True  # 25 > 20

    def test_delta_falling(self):
        """Test delta with falling values."""
        fn = DeltaWindowFunction("bp_drop", threshold=-15, comparison="<")
        events = self.create_events([120, 115, 110, 105, 100])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == -20  # 100 - 120
        assert result.result is True  # -20 < -15

    def test_delta_empty(self):
        """Test delta with no events."""
        fn = DeltaWindowFunction("hr_rise", threshold=20, comparison=">")
        result = fn.process("P123", [], datetime.now(), datetime.now())

        assert result.result is False
        assert result.input_count == 0

    def test_slope_positive(self):
        """Test slope with upward trend."""
        fn = SlopeWindowFunction("hr_trend", threshold=5, comparison=">")
        # Linear increase: 80 -> 100 over 60 minutes = 20/hour
        events = self.create_events([80, 85, 90, 95, 100, 105, 110])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        # Slope should be approximately 30 per hour (5 per 10 min)
        assert result.value > 20
        assert result.result is True

    def test_slope_flat(self):
        """Test slope with flat values."""
        fn = SlopeWindowFunction("hr_trend", threshold=5, comparison=">")
        events = self.create_events([80, 80, 81, 79, 80, 80, 80])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        # Slope should be near 0
        assert abs(result.value) < 5
        assert result.result is False

    def test_min_function(self):
        """Test min window function."""
        fn = MinWindowFunction("hr_low", threshold=60, comparison="<")
        events = self.create_events([80, 75, 65, 70, 85])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == 65
        assert result.result is False  # 65 is not < 60

    def test_max_function(self):
        """Test max window function."""
        fn = MaxWindowFunction("hr_high", threshold=100, comparison=">")
        events = self.create_events([80, 95, 110, 100, 85])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == 110
        assert result.result is True  # 110 > 100

    def test_count_function(self):
        """Test count window function."""
        fn = CountWindowFunction("enough_data", threshold=5, comparison=">=")
        events = self.create_events([80, 85, 90, 95, 100, 105])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == 6
        assert result.result is True

    def test_sma_function(self):
        """Test simple moving average."""
        fn = SMAWindowFunction("hr_avg", threshold=90, comparison=">")
        events = self.create_events([80, 85, 90, 95, 100])

        result = fn.process("P123", events, events[0].timestamp, events[-1].timestamp)

        assert result.value == 90  # (80+85+90+95+100)/5
        assert result.result is False  # 90 is not > 90


class TestProcessFunctions:
    """Test stateful process functions."""

    def test_last_function(self):
        """Test last value function."""
        fn = LastProcessFunction("hypoxia", threshold=92, comparison="<")

        event = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now(),
            signal_type="SpO2",
            value=88.0,
            unit="%",
            source="test",
        )

        result, state = fn.process_element(event, {})

        assert result.value == 88.0
        assert result.result is True  # 88 < 92
        assert state["last_value"] == 88.0

    def test_ema_function(self):
        """Test exponential moving average."""
        # 1 hour window -> alpha = 2/(60+1) ≈ 0.0328
        fn = EMAProcessFunction(
            "hr_smoothed", window_ms=60 * 60 * 1000, threshold=100, comparison=">"
        )

        state = {}

        # First event initializes EMA
        event1 = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now(),
            signal_type="HR",
            value=80.0,
            unit="bpm",
            source="test",
        )
        result1, state = fn.process_element(event1, state)
        assert result1.value == 80.0  # First value = EMA

        # Second event updates EMA
        event2 = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now() + timedelta(minutes=1),
            signal_type="HR",
            value=120.0,
            unit="bpm",
            source="test",
        )
        result2, state = fn.process_element(event2, state)

        # EMA = alpha * 120 + (1-alpha) * 80
        expected_ema = fn.alpha * 120 + (1 - fn.alpha) * 80
        assert abs(result2.value - expected_ema) < 0.01


class TestExpressionParser:
    """Test PSDL expression parsing."""

    def test_parse_delta_expr(self):
        parser = ExpressionParser()
        op = parser.parse_trend_expr("delta(HR, 1h) > 20")

        assert op.name == "delta"
        assert op.signal == "HR"
        assert op.window == "1h"
        assert op.threshold == 20.0
        assert op.comparison == ">"
        assert op.operator_type == OperatorType.WINDOW

    def test_parse_delta_with_slide(self):
        parser = ExpressionParser()
        op = parser.parse_trend_expr("delta(HR, 1h, 30s) > 20")

        assert op.name == "delta"
        assert op.window == "1h"
        assert op.slide == "30s"

    def test_parse_last_expr(self):
        parser = ExpressionParser()
        op = parser.parse_trend_expr("last(SpO2) < 92")

        assert op.name == "last"
        assert op.signal == "SpO2"
        assert op.window is None
        assert op.threshold == 92.0
        assert op.comparison == "<"
        assert op.operator_type == OperatorType.PROCESS

    def test_parse_ema_expr(self):
        parser = ExpressionParser()
        op = parser.parse_trend_expr("ema(HR, 1h) > 100")

        assert op.name == "ema"
        assert op.signal == "HR"
        assert op.window == "1h"
        assert op.operator_type == OperatorType.PROCESS

    def test_parse_logic_expr(self):
        parser = ExpressionParser()
        refs = parser.parse_logic_expr("hr_rising AND bp_dropping")

        assert refs == ["hr_rising", "bp_dropping"]

    def test_parse_complex_logic(self):
        parser = ExpressionParser()
        refs = parser.parse_logic_expr("(a AND b) OR (c AND d)")

        assert set(refs) == {"a", "b", "c", "d"}


class TestLogicEvaluator:
    """Test logic expression evaluation."""

    def test_and_true(self):
        result = LogicEvaluator.evaluate("a AND b", {"a": True, "b": True})
        assert result is True

    def test_and_false(self):
        result = LogicEvaluator.evaluate("a AND b", {"a": True, "b": False})
        assert result is False

    def test_or_true(self):
        result = LogicEvaluator.evaluate("a OR b", {"a": True, "b": False})
        assert result is True

    def test_complex_expression(self):
        result = LogicEvaluator.evaluate("(a AND b) OR c", {"a": False, "b": True, "c": True})
        assert result is True

    def test_not_expression(self):
        result = LogicEvaluator.evaluate("a AND NOT b", {"a": True, "b": False})
        assert result is True


class TestStreamingCompiler:
    """Test PSDL scenario compilation."""

    def test_compile_simple_scenario(self):
        scenario = {
            "scenario": "Test_Scenario",
            "version": "0.2.0",
            "execution": {"mode": "streaming"},
            "signals": {"HR": {"source": "heart_rate"}},
            "trends": {
                "hr_rising": {
                    "expr": "delta(HR, 1h) > 20",
                    "description": "Heart rate rising",
                }
            },
            "logic": {"alert": {"expr": "hr_rising", "severity": "high"}},
        }

        compiler = StreamingCompiler()
        compiled = compiler.compile(scenario)

        assert compiled.name == "Test_Scenario"
        assert compiled.version == "0.2.0"
        assert "hr_rising" in compiled.trends
        assert "alert" in compiled.logic
        assert compiled.logic["alert"].severity == Severity.HIGH

    def test_compile_multiple_trends(self):
        scenario = {
            "scenario": "ICU_Deterioration",
            "version": "0.2.0",
            "signals": {
                "HR": {"source": "heart_rate"},
                "SBP": {"source": "systolic_bp"},
            },
            "trends": {
                "hr_rising": {"expr": "delta(HR, 1h) > 20"},
                "bp_dropping": {"expr": "delta(SBP, 30m) < -15"},
            },
            "logic": {
                "deterioration": {
                    "expr": "hr_rising AND bp_dropping",
                    "severity": "critical",
                }
            },
        }

        compiler = StreamingCompiler()
        compiled = compiler.compile(scenario)

        assert len(compiled.trends) == 2
        assert compiled.logic["deterioration"].trend_refs == [
            "hr_rising",
            "bp_dropping",
        ]


class TestStreamingEvaluator:
    """Test streaming evaluation."""

    def test_evaluate_single_event(self):
        scenario = {
            "scenario": "Test",
            "version": "0.1.0",
            "signals": {"SpO2": {}},
            "trends": {"hypoxia": {"expr": "last(SpO2) < 92", "description": "Low oxygen"}},
            "logic": {"alert": {"expr": "hypoxia", "severity": "high"}},
        }

        evaluator = StreamingEvaluator()
        compiled = evaluator.compile(scenario)

        event = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now(),
            signal_type="SpO2",
            value=88.0,
            unit="%",
            source="test",
        )

        state = {}
        trend_results, logic_results, state = evaluator.evaluate_event(compiled, event, state)

        assert len(trend_results) == 1
        assert trend_results[0].trend_name == "hypoxia"
        assert trend_results[0].result is True

        assert len(logic_results) == 1
        assert logic_results[0].logic_name == "alert"
        assert logic_results[0].result is True

    def test_evaluate_multi_trend_logic(self):
        scenario = {
            "scenario": "Test",
            "version": "0.1.0",
            "signals": {"HR": {}, "SpO2": {}},
            "trends": {
                "tachycardia": {"expr": "last(HR) > 100"},
                "hypoxia": {"expr": "last(SpO2) < 92"},
            },
            "logic": {"critical": {"expr": "tachycardia AND hypoxia", "severity": "critical"}},
        }

        evaluator = StreamingEvaluator()
        compiled = evaluator.compile(scenario)
        state = {}

        # First event: high HR
        event1 = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now(),
            signal_type="HR",
            value=110.0,
            unit="bpm",
            source="test",
        )
        _, logic1, state = evaluator.evaluate_event(compiled, event1, state)

        # Logic should not fire yet (missing SpO2)
        assert len(logic1) == 0 or not logic1[0].result

        # Second event: low SpO2
        event2 = ClinicalEvent(
            patient_id="P123",
            timestamp=datetime.now() + timedelta(seconds=30),
            signal_type="SpO2",
            value=88.0,
            unit="%",
            source="test",
        )
        _, logic2, state = evaluator.evaluate_event(compiled, event2, state)

        # Now both conditions met
        assert len(logic2) == 1
        assert logic2[0].result is True
        assert logic2[0].severity == Severity.CRITICAL


class TestStreamingConfig:
    """Test streaming configuration parsing."""

    def test_default_config(self):
        config = StreamingConfig()
        assert config.mode == ExecutionMode.STREAMING
        assert config.watermark.max_lateness_ms == 5 * 60 * 1000

    def test_from_scenario(self):
        scenario = {
            "execution": {
                "mode": "streaming",
                "state_ttl": "24h",
                "watermark": {"max_lateness": "10m"},
                "checkpointing": {"interval": "30s", "mode": "exactly_once"},
            }
        }

        config = StreamingConfig.from_scenario(scenario)

        assert config.mode == ExecutionMode.STREAMING
        assert config.state_ttl_ms == 24 * 60 * 60 * 1000
        assert config.watermark.max_lateness_ms == 10 * 60 * 1000
        assert config.checkpointing.interval_ms == 30 * 1000
        assert config.checkpointing.mode == CheckpointMode.EXACTLY_ONCE


class TestLogicJoinFunction:
    """Test logic join functionality."""

    def test_join_all_trends_present(self):
        from psdl.execution.streaming.compiler import CompiledLogic

        logic = CompiledLogic(
            name="test_logic",
            expr="a AND b",
            trend_refs=["a", "b"],
            severity=Severity.HIGH,
        )

        join_fn = LogicJoinFunction(logic, "TestScenario", "0.1.0")

        trend_results = {
            "a": TrendResult(
                patient_id="P123",
                trend_name="a",
                value=1.0,
                result=True,
                timestamp=datetime.now(),
            ),
            "b": TrendResult(
                patient_id="P123",
                trend_name="b",
                value=1.0,
                result=True,
                timestamp=datetime.now(),
            ),
        }

        result = join_fn.process("P123", trend_results, datetime.now())

        assert result is not None
        assert result.result is True
        assert result.logic_name == "test_logic"

    def test_join_missing_trend(self):
        from psdl.execution.streaming.compiler import CompiledLogic

        logic = CompiledLogic(
            name="test_logic",
            expr="a AND b",
            trend_refs=["a", "b"],
            severity=Severity.HIGH,
        )

        join_fn = LogicJoinFunction(logic, "TestScenario", "0.1.0")

        # Only 'a' is present
        trend_results = {
            "a": TrendResult(
                patient_id="P123",
                trend_name="a",
                value=1.0,
                result=True,
                timestamp=datetime.now(),
            )
        }

        result = join_fn.process("P123", trend_results, datetime.now())

        # Should return None when not all trends present
        assert result is None


class TestLateDataHandling:
    """Test late data handling configuration."""

    def test_default_late_data_policy(self):
        """Test default late data policy is DROP."""
        from psdl.execution.streaming.config import LateDataPolicy

        config = StreamingConfig()
        assert config.late_data_policy == LateDataPolicy.DROP
        assert config.allowed_lateness_ms == 0

    def test_late_data_policy_from_scenario(self):
        """Test parsing late data policy from scenario config."""
        from psdl.execution.streaming.config import LateDataPolicy

        scenario = {
            "execution": {
                "mode": "streaming",
                "late_data": {
                    "policy": "side_output",
                    "allowed_lateness": "2m",
                },
            }
        }

        config = StreamingConfig.from_scenario(scenario)

        assert config.late_data_policy == LateDataPolicy.SIDE_OUTPUT
        assert config.allowed_lateness_ms == 2 * 60 * 1000

    def test_late_data_policy_allow(self):
        """Test ALLOW policy configuration."""
        from psdl.execution.streaming.config import LateDataPolicy

        scenario = {
            "execution": {
                "mode": "streaming",
                "late_data": {
                    "policy": "allow",
                    "allowed_lateness": "5m",
                },
            }
        }

        config = StreamingConfig.from_scenario(scenario)

        assert config.late_data_policy == LateDataPolicy.ALLOW
        assert config.allowed_lateness_ms == 5 * 60 * 1000

    def test_late_data_output_tag_constant(self):
        """Test late data output tag is defined."""
        from psdl.execution.streaming.flink_runtime import LATE_DATA_TAG

        assert LATE_DATA_TAG == "late-clinical-events"

    def test_watermark_config_default(self):
        """Test default watermark configuration."""
        from psdl.execution.streaming.config import WatermarkConfig

        config = WatermarkConfig()
        assert config.max_lateness_ms == 5 * 60 * 1000  # 5 minutes
        assert config.idle_timeout_ms == 30 * 1000  # 30 seconds

    def test_watermark_config_custom(self):
        """Test custom watermark configuration."""
        from psdl.execution.streaming.config import WatermarkConfig

        config = WatermarkConfig.from_dict(
            {
                "max_lateness": "10m",
                "idle_timeout": "60s",
            }
        )

        assert config.max_lateness_ms == 10 * 60 * 1000
        assert config.idle_timeout_ms == 60 * 1000
