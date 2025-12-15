"""
Tests for PSDL Benchmarking Suite.

Tests data generation, benchmark scenarios, and the benchmark runner.
"""

import pytest

from psdl.benchmarks import (
    BENCHMARK_SCENARIOS,
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkSuite,
    SyntheticDataConfig,
    generate_synthetic_data,
    get_benchmark_scenario,
)
from psdl.benchmarks.data_generator import generate_aki_scenario_data, generate_sepsis_scenario_data
from psdl.benchmarks.scenarios import get_scenario_complexity, list_benchmark_scenarios


class TestSyntheticDataConfig:
    """Test synthetic data configuration."""

    def test_default_config(self):
        config = SyntheticDataConfig()
        assert config.num_patients == 100
        assert config.duration_hours == 72
        assert "HR" in config.signals
        assert "Cr" in config.signals

    def test_custom_config(self):
        config = SyntheticDataConfig(
            num_patients=50,
            duration_hours=24,
            seed=42,
        )
        assert config.num_patients == 50
        assert config.duration_hours == 24
        assert config.seed == 42


class TestGenerateSyntheticData:
    """Test synthetic data generation."""

    def test_generate_default(self):
        data = generate_synthetic_data(num_patients=10)
        assert len(data) == 10
        assert all(patient_id.startswith("P") for patient_id in data.keys())

    def test_generate_has_expected_signals(self):
        data = generate_synthetic_data(num_patients=5)
        patient_data = list(data.values())[0]
        assert "HR" in patient_data
        assert "Cr" in patient_data
        assert "Lactate" in patient_data

    def test_generate_reproducible(self):
        config = SyntheticDataConfig(num_patients=5, seed=42)
        data1 = generate_synthetic_data(num_patients=5, config=config)

        config = SyntheticDataConfig(num_patients=5, seed=42)
        data2 = generate_synthetic_data(num_patients=5, config=config)

        # Same seed should produce same data
        for patient_id in data1.keys():
            assert patient_id in data2
            for signal in data1[patient_id].keys():
                assert len(data1[patient_id][signal]) == len(data2[patient_id][signal])

    def test_data_has_datapoints(self):
        data = generate_synthetic_data(num_patients=3)
        patient_data = list(data.values())[0]

        for signal_name, datapoints in patient_data.items():
            assert len(datapoints) > 0
            for dp in datapoints:
                assert hasattr(dp, "timestamp")
                assert hasattr(dp, "value")
                assert isinstance(dp.value, (int, float))


class TestGenerateAKIData:
    """Test AKI-specific data generation."""

    def test_generate_aki_data(self):
        data = generate_aki_scenario_data(num_patients=10, aki_rate=0.3, seed=42)
        assert len(data) == 10

    def test_aki_rate(self):
        # With fixed seed, aki_rate should be approximately correct
        data = generate_aki_scenario_data(num_patients=100, aki_rate=0.2, seed=42)

        # Check that some patients have rising creatinine
        rising_cr_count = 0
        for patient_data in data.values():
            cr_values = [dp.value for dp in patient_data["Cr"]]
            if len(cr_values) >= 2:
                # Check if creatinine is generally rising
                if cr_values[-1] > cr_values[0] + 0.3:
                    rising_cr_count += 1

        # Should have some AKI patients
        assert rising_cr_count > 0


class TestGenerateSepsisData:
    """Test sepsis-specific data generation."""

    def test_generate_sepsis_data(self):
        data = generate_sepsis_scenario_data(num_patients=10, sepsis_rate=0.2, seed=42)
        assert len(data) == 10

    def test_sepsis_patterns(self):
        data = generate_sepsis_scenario_data(num_patients=50, sepsis_rate=0.3, seed=42)

        # Check that some patients have sepsis patterns
        elevated_lactate_count = 0
        for patient_data in data.values():
            lactate_values = [dp.value for dp in patient_data["Lactate"]]
            if any(v > 2.0 for v in lactate_values):
                elevated_lactate_count += 1

        # Should have some patients with elevated lactate
        assert elevated_lactate_count > 0


class TestBenchmarkScenarios:
    """Test benchmark scenario definitions."""

    def test_scenarios_exist(self):
        assert "simple_threshold" in BENCHMARK_SCENARIOS
        assert "medium_aki" in BENCHMARK_SCENARIOS
        assert "complex_sepsis" in BENCHMARK_SCENARIOS
        assert "very_complex_icu" in BENCHMARK_SCENARIOS

    def test_get_scenario(self):
        scenario = get_benchmark_scenario("simple_threshold")
        assert scenario is not None
        assert scenario["scenario"] == "Benchmark_Simple"

    def test_get_unknown_scenario(self):
        scenario = get_benchmark_scenario("nonexistent")
        assert scenario is None

    def test_list_scenarios(self):
        scenarios = list_benchmark_scenarios()
        assert len(scenarios) == 4
        assert "simple_threshold" in scenarios

    def test_get_complexity(self):
        assert get_scenario_complexity("simple_threshold") == "simple"
        assert get_scenario_complexity("medium_aki") == "medium"
        assert get_scenario_complexity("complex_sepsis") == "complex"
        assert get_scenario_complexity("very_complex_icu") == "very_complex"

    def test_scenario_structure(self):
        for name, scenario in BENCHMARK_SCENARIOS.items():
            assert "scenario" in scenario
            assert "version" in scenario
            assert "signals" in scenario
            assert "trends" in scenario
            assert "logic" in scenario


class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""

    def test_create_result(self):
        result = BenchmarkResult(
            scenario_name="test",
            num_patients=100,
            num_iterations=5,
            mean_time=0.5,
            std_time=0.1,
            min_time=0.4,
            max_time=0.6,
            total_time=2.5,
            patients_per_second=200.0,
        )
        assert result.scenario_name == "test"
        assert result.patients_per_second == 200.0

    def test_to_dict(self):
        result = BenchmarkResult(
            scenario_name="test",
            num_patients=100,
            num_iterations=5,
            mean_time=0.5,
            std_time=0.1,
            min_time=0.4,
            max_time=0.6,
            total_time=2.5,
            patients_per_second=200.0,
            complexity="medium",
        )
        d = result.to_dict()
        assert d["scenario"] == "test"
        assert d["mean_time_ms"] == 500.0
        assert d["throughput_patients_per_sec"] == 200.0


class TestBenchmarkSuite:
    """Test BenchmarkSuite collection."""

    def test_create_suite(self):
        suite = BenchmarkSuite(name="Test Suite")
        assert suite.name == "Test Suite"
        assert len(suite.results) == 0

    def test_add_result(self):
        suite = BenchmarkSuite(name="Test")
        result = BenchmarkResult(
            scenario_name="test",
            num_patients=100,
            num_iterations=5,
            mean_time=0.5,
            std_time=0.1,
            min_time=0.4,
            max_time=0.6,
            total_time=2.5,
            patients_per_second=200.0,
        )
        suite.add_result(result)
        assert len(suite.results) == 1

    def test_to_markdown(self):
        suite = BenchmarkSuite(name="Test Suite")
        result = BenchmarkResult(
            scenario_name="test",
            num_patients=100,
            num_iterations=5,
            mean_time=0.5,
            std_time=0.1,
            min_time=0.4,
            max_time=0.6,
            total_time=2.5,
            patients_per_second=200.0,
            complexity="medium",
        )
        suite.add_result(result)
        md = suite.to_markdown()
        assert "PSDL Benchmark Report" in md
        assert "test" in md
        assert "medium" in md


class TestBenchmarkRunner:
    """Test BenchmarkRunner."""

    @pytest.fixture
    def small_data(self):
        """Generate small test dataset."""
        return generate_synthetic_data(
            num_patients=5,
            config=SyntheticDataConfig(
                num_patients=5,
                duration_hours=24,
                seed=42,
            ),
        )

    def test_create_runner(self):
        runner = BenchmarkRunner()
        assert runner.warmup_iterations == 2
        assert runner.benchmark_iterations == 5

    def test_run_scenario(self, small_data):
        runner = BenchmarkRunner(
            warmup_iterations=1,
            benchmark_iterations=2,
            verbose=False,
        )
        result = runner.run_scenario("simple_threshold", small_data)

        assert result.scenario_name == "simple_threshold"
        assert result.num_patients == 5
        assert result.mean_time > 0
        assert result.patients_per_second > 0

    def test_run_all(self, small_data):
        runner = BenchmarkRunner(
            warmup_iterations=1,
            benchmark_iterations=2,
            verbose=False,
        )
        suite = runner.run_all(small_data, scenarios=["simple_threshold", "medium_aki"])

        assert len(suite.results) == 2
        assert suite.results[0].scenario_name == "simple_threshold"
        assert suite.results[1].scenario_name == "medium_aki"

    def test_run_unknown_scenario(self, small_data):
        runner = BenchmarkRunner(verbose=False)
        with pytest.raises(ValueError, match="Unknown benchmark scenario"):
            runner.run_scenario("nonexistent", small_data)
