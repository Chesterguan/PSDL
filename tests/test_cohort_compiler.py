"""
Tests for PSDL Cohort Compiler and Query Optimization.

Tests the SQL compilation, batch processing, cost estimation,
and query optimization features.
"""

import pytest
import yaml

from psdl.core import PSDLParser
from psdl.runtimes.cohort import (
    CohortCompiler,
    CompiledSQL,
    QueryComplexity,
    QueryCostEstimate,
    QueryOptimizationConfig,
    parse_trend_expression,
    parse_window,
)


class TestParseWindow:
    """Test window string parsing."""

    def test_parse_seconds(self):
        assert parse_window("30s") == 30

    def test_parse_minutes(self):
        assert parse_window("5m") == 300

    def test_parse_hours(self):
        assert parse_window("2h") == 7200

    def test_parse_days(self):
        assert parse_window("7d") == 604800

    def test_parse_weeks(self):
        assert parse_window("1w") == 604800

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_window("invalid")


class TestParseTrendExpression:
    """Test trend expression parsing."""

    def test_windowed_with_comparison(self):
        op, signal, window, threshold, cmp_op = parse_trend_expression("delta(Cr, 48h) >= 0.3")
        assert op == "delta"
        assert signal == "Cr"
        assert window == "48h"
        assert threshold == 0.3
        assert cmp_op == ">="

    def test_windowed_without_comparison(self):
        op, signal, window, threshold, cmp_op = parse_trend_expression("slope(HR, 6h)")
        assert op == "slope"
        assert signal == "HR"
        assert window == "6h"
        assert threshold is None
        assert cmp_op is None

    def test_pointwise_with_comparison(self):
        op, signal, window, threshold, cmp_op = parse_trend_expression("last(SpO2) < 92")
        assert op == "last"
        assert signal == "SpO2"
        assert window is None
        assert threshold == 92.0
        assert cmp_op == "<"

    def test_pointwise_without_comparison(self):
        op, signal, window, threshold, cmp_op = parse_trend_expression("last(HR)")
        assert op == "last"
        assert signal == "HR"
        assert window is None
        assert threshold is None
        assert cmp_op is None


class TestQueryOptimizationConfig:
    """Test query optimization configuration."""

    def test_default_config(self):
        config = QueryOptimizationConfig()
        assert config.enable_batching is False
        assert config.batch_size == 10000
        assert config.apply_population_filter_early is True
        assert config.enable_parallel_query is True
        assert config.parallel_workers_per_gather == 4

    def test_custom_config(self):
        config = QueryOptimizationConfig(
            enable_batching=True,
            batch_size=5000,
            parallel_workers_per_gather=8,
        )
        assert config.enable_batching is True
        assert config.batch_size == 5000
        assert config.parallel_workers_per_gather == 8


class TestQueryCostEstimate:
    """Test query cost estimation."""

    def test_should_batch_large_cohort(self):
        estimate = QueryCostEstimate(
            complexity=QueryComplexity.LOW,
            estimated_cte_count=3,
            estimated_join_count=2,
            largest_window_seconds=3600,
            logic_depth=1,
        )
        # Large cohort should batch
        assert estimate.should_batch(cohort_size=200000) is True
        # Small cohort should not batch
        assert estimate.should_batch(cohort_size=1000) is False

    def test_should_batch_high_complexity(self):
        estimate = QueryCostEstimate(
            complexity=QueryComplexity.HIGH,
            estimated_cte_count=30,
            estimated_join_count=29,
            largest_window_seconds=604800,
            logic_depth=4,
        )
        # High complexity should always batch
        assert estimate.should_batch(cohort_size=1000) is True

    def test_recommended_batch_size(self):
        low = QueryCostEstimate(
            complexity=QueryComplexity.LOW,
            estimated_cte_count=2,
            estimated_join_count=1,
            largest_window_seconds=3600,
            logic_depth=1,
        )
        assert low.recommended_batch_size() == 50000

        high = QueryCostEstimate(
            complexity=QueryComplexity.HIGH,
            estimated_cte_count=30,
            estimated_join_count=29,
            largest_window_seconds=604800,
            logic_depth=4,
        )
        assert high.recommended_batch_size() == 5000


class TestCohortCompiler:
    """Test PSDL to SQL compilation."""

    @pytest.fixture
    def simple_scenario(self):
        """Simple test scenario."""
        parser = PSDLParser()
        scenario_dict = {
            "scenario": "Test_AKI",
            "version": "0.3.0",
            "signals": {
                "Cr": {
                    "ref": "creatinine",
                    "concept_id": 3016723,
                }
            },
            "trends": {
                "cr_delta": {
                    "expr": "delta(Cr, 48h)",
                    "type": "float",
                }
            },
            "logic": {
                "aki_stage1": {
                    "when": "cr_delta >= 0.3",
                    "severity": "medium",
                }
            },
        }
        return parser.parse_string(yaml.dump(scenario_dict))

    @pytest.fixture
    def complex_scenario(self):
        """Complex test scenario with many trends."""
        parser = PSDLParser()
        signals = {}
        trends = {}
        for i in range(25):
            signals[f"Signal{i}"] = {"ref": f"signal_{i}", "concept_id": 3000000 + i}
            trends[f"trend_{i}"] = {"expr": f"delta(Signal{i}, 48h)", "type": "float"}

        scenario_dict = {
            "scenario": "Complex_Test",
            "version": "0.3.0",
            "signals": signals,
            "trends": trends,
            "logic": {
                "alert": {
                    "when": " AND ".join([f"trend_{i} > 0" for i in range(5)]),
                    "severity": "high",
                }
            },
        }
        return parser.parse_string(yaml.dump(scenario_dict))

    def test_compile_simple(self, simple_scenario):
        compiler = CohortCompiler()
        result = compiler.compile(simple_scenario)

        assert isinstance(result, CompiledSQL)
        assert "cr_delta" in result.sql
        assert "WITH" in result.sql
        assert len(result.trend_columns) == 1

    def test_estimate_cost_simple(self, simple_scenario):
        compiler = CohortCompiler()
        cost = compiler.estimate_cost(simple_scenario)

        # 48h window triggers MEDIUM complexity (> 1 day)
        assert cost.complexity == QueryComplexity.MEDIUM
        assert cost.estimated_cte_count == 1
        assert cost.estimated_join_count == 0
        assert cost.largest_window_seconds == 172800  # 48h

    def test_estimate_cost_complex(self, complex_scenario):
        compiler = CohortCompiler()
        cost = compiler.estimate_cost(complex_scenario)

        assert cost.complexity in (QueryComplexity.HIGH, QueryComplexity.VERY_HIGH)
        assert cost.estimated_cte_count == 25
        assert len(cost.recommendations) > 0

    def test_compile_batched_no_total(self, simple_scenario):
        compiler = CohortCompiler()
        batches = list(compiler.compile_batched(simple_scenario, batch_size=1000))

        assert len(batches) == 1
        assert batches[0].batch_info["parameterized"] is True
        assert "OFFSET" in batches[0].sql
        assert "LIMIT" in batches[0].sql

    def test_compile_batched_with_total(self, simple_scenario):
        compiler = CohortCompiler()
        batches = list(
            compiler.compile_batched(
                simple_scenario,
                batch_size=100,
                total_patients=350,
            )
        )

        assert len(batches) == 4  # 350 / 100 = 4 batches
        assert batches[0].batch_info["batch_number"] == 0
        assert batches[0].batch_info["offset"] == 0
        assert batches[3].batch_info["batch_number"] == 3
        assert batches[3].batch_info["offset"] == 300

    def test_add_parallel_hints(self, simple_scenario):
        compiler = CohortCompiler()
        result = compiler.compile(simple_scenario)
        sql_with_hints = compiler.add_parallel_hints(result.sql)

        assert "max_parallel_workers_per_gather" in sql_with_hints
        assert "SET" in sql_with_hints

    def test_add_parallel_hints_custom_workers(self, simple_scenario):
        compiler = CohortCompiler()
        result = compiler.compile(simple_scenario)
        sql_with_hints = compiler.add_parallel_hints(result.sql, workers=8)

        assert "max_parallel_workers_per_gather = 8" in sql_with_hints

    def test_custom_optimization_config(self, simple_scenario):
        config = QueryOptimizationConfig(
            enable_batching=True,
            batch_size=5000,
            parallel_workers_per_gather=8,
        )
        compiler = CohortCompiler(optimization=config)

        batches = list(compiler.compile_batched(simple_scenario))
        assert batches[0].parameters["batch_limit"] == 5000


class TestCompiledSQL:
    """Test CompiledSQL dataclass."""

    def test_basic_fields(self):
        result = CompiledSQL(
            sql="SELECT * FROM test",
            parameters={"ref_time": "NOW()"},
            trend_columns=["trend1"],
            logic_columns=["logic1"],
        )
        assert result.sql == "SELECT * FROM test"
        assert result.cost_estimate is None
        assert result.batch_info is None

    def test_with_cost_estimate(self):
        cost = QueryCostEstimate(
            complexity=QueryComplexity.LOW,
            estimated_cte_count=1,
            estimated_join_count=0,
            largest_window_seconds=3600,
            logic_depth=1,
        )
        result = CompiledSQL(
            sql="SELECT * FROM test",
            parameters={},
            trend_columns=[],
            logic_columns=[],
            cost_estimate=cost,
        )
        assert result.cost_estimate.complexity == QueryComplexity.LOW

    def test_with_batch_info(self):
        result = CompiledSQL(
            sql="SELECT * FROM test OFFSET 0 LIMIT 100",
            parameters={},
            trend_columns=[],
            logic_columns=[],
            batch_info={
                "batch_number": 0,
                "total_batches": 10,
                "offset": 0,
                "limit": 100,
            },
        )
        assert result.batch_info["batch_number"] == 0
        assert result.batch_info["total_batches"] == 10
