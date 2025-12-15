"""
PSDL Benchmark Runner.

Provides utilities for running and reporting benchmark results.
"""

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from psdl.core import PSDLParser
from psdl.operators import DataPoint
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

from .scenarios import BENCHMARK_SCENARIOS, get_scenario_complexity


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    scenario_name: str
    num_patients: int
    num_iterations: int

    # Timing results (in seconds)
    mean_time: float
    std_time: float
    min_time: float
    max_time: float
    total_time: float

    # Throughput
    patients_per_second: float

    # Memory (if tracked)
    peak_memory_mb: Optional[float] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    runtime: str = "single_patient"
    complexity: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "scenario": self.scenario_name,
            "complexity": self.complexity,
            "num_patients": self.num_patients,
            "iterations": self.num_iterations,
            "mean_time_ms": self.mean_time * 1000,
            "std_time_ms": self.std_time * 1000,
            "min_time_ms": self.min_time * 1000,
            "max_time_ms": self.max_time * 1000,
            "total_time_s": self.total_time,
            "throughput_patients_per_sec": self.patients_per_second,
            "runtime": self.runtime,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""

    name: str
    results: List[BenchmarkResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def add_result(self, result: BenchmarkResult):
        """Add a benchmark result."""
        self.results.append(result)

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# PSDL Benchmark Report",
            f"",
            f"**Suite**: {self.name}",
            f"**Date**: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Summary",
            f"",
            f"| Scenario | Complexity | Patients | Mean (ms) | Std (ms) | Throughput |",
            f"|----------|------------|----------|-----------|----------|------------|",
        ]

        for r in self.results:
            lines.append(
                f"| {r.scenario_name} | {r.complexity} | {r.num_patients} | "
                f"{r.mean_time * 1000:.2f} | {r.std_time * 1000:.2f} | "
                f"{r.patients_per_second:.1f}/s |"
            )

        lines.extend(
            [
                "",
                "## Details",
                "",
            ]
        )

        for r in self.results:
            lines.extend(
                [
                    f"### {r.scenario_name}",
                    f"",
                    f"- **Complexity**: {r.complexity}",
                    f"- **Patients**: {r.num_patients}",
                    f"- **Iterations**: {r.num_iterations}",
                    f"- **Mean time**: {r.mean_time * 1000:.2f} ms",
                    f"- **Std deviation**: {r.std_time * 1000:.2f} ms",
                    f"- **Min time**: {r.min_time * 1000:.2f} ms",
                    f"- **Max time**: {r.max_time * 1000:.2f} ms",
                    f"- **Total time**: {r.total_time:.2f} s",
                    f"- **Throughput**: {r.patients_per_second:.1f} patients/sec",
                    "",
                ]
            )

        return "\n".join(lines)


class BenchmarkRunner:
    """
    Run PSDL benchmarks.

    Example usage:
        runner = BenchmarkRunner()
        data = generate_synthetic_data(1000)
        results = runner.run_all(data)
        runner.print_report(results)
    """

    def __init__(
        self,
        warmup_iterations: int = 2,
        benchmark_iterations: int = 5,
        verbose: bool = True,
    ):
        """
        Initialize benchmark runner.

        Args:
            warmup_iterations: Number of warmup runs before timing
            benchmark_iterations: Number of timed iterations
            verbose: Print progress during benchmarking
        """
        self.warmup_iterations = warmup_iterations
        self.benchmark_iterations = benchmark_iterations
        self.verbose = verbose
        self.parser = PSDLParser()

    def run_scenario(
        self,
        scenario_name: str,
        data: Dict[str, Dict[str, List[DataPoint]]],
        reference_time: Optional[datetime] = None,
    ) -> BenchmarkResult:
        """
        Run benchmark for a single scenario.

        Args:
            scenario_name: Name of benchmark scenario
            data: Patient data dictionary
            reference_time: Reference time for evaluation

        Returns:
            BenchmarkResult with timing statistics
        """
        scenario_dict = BENCHMARK_SCENARIOS.get(scenario_name)
        if scenario_dict is None:
            raise ValueError(f"Unknown benchmark scenario: {scenario_name}")

        if self.verbose:
            print(f"  Running {scenario_name}...")

        # Parse scenario
        import yaml

        scenario = self.parser.parse_string(yaml.dump(scenario_dict))

        # Set reference time
        if reference_time is None:
            # Use latest timestamp from data
            all_timestamps = []
            for patient_data in data.values():
                for signal_data in patient_data.values():
                    for dp in signal_data:
                        all_timestamps.append(dp.timestamp)
            reference_time = max(all_timestamps) if all_timestamps else datetime.now()

        # Warmup runs
        for _ in range(self.warmup_iterations):
            self._run_evaluation(scenario, data, reference_time)

        # Timed runs
        times = []
        for _ in range(self.benchmark_iterations):
            start = time.perf_counter()
            self._run_evaluation(scenario, data, reference_time)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        # Calculate statistics
        mean_time = statistics.mean(times)
        std_time = statistics.stdev(times) if len(times) > 1 else 0.0
        min_time = min(times)
        max_time = max(times)
        total_time = sum(times)

        num_patients = len(data)
        patients_per_second = num_patients / mean_time if mean_time > 0 else 0

        return BenchmarkResult(
            scenario_name=scenario_name,
            num_patients=num_patients,
            num_iterations=self.benchmark_iterations,
            mean_time=mean_time,
            std_time=std_time,
            min_time=min_time,
            max_time=max_time,
            total_time=total_time,
            patients_per_second=patients_per_second,
            complexity=get_scenario_complexity(scenario_name),
        )

    def _run_evaluation(
        self,
        scenario: Any,
        data: Dict[str, Dict[str, List[DataPoint]]],
        reference_time: datetime,
    ) -> Dict[str, Any]:
        """Run scenario evaluation on all patients."""
        results = {}

        for patient_id, patient_data in data.items():
            # Create backend and populate with patient data
            backend = InMemoryBackend()
            for signal_name, datapoints in patient_data.items():
                backend.add_data(patient_id, signal_name, datapoints)

            # Create evaluator with scenario and backend
            evaluator = SinglePatientEvaluator(scenario, backend)
            result = evaluator.evaluate(patient_id, reference_time)
            results[patient_id] = result

        return results

    def run_all(
        self,
        data: Dict[str, Dict[str, List[DataPoint]]],
        scenarios: Optional[List[str]] = None,
    ) -> BenchmarkSuite:
        """
        Run all benchmark scenarios.

        Args:
            data: Patient data dictionary
            scenarios: List of scenario names (None = all)

        Returns:
            BenchmarkSuite with all results
        """
        if scenarios is None:
            scenarios = list(BENCHMARK_SCENARIOS.keys())

        suite = BenchmarkSuite(name=f"PSDL Benchmark ({len(data)} patients)")

        if self.verbose:
            print(f"Running PSDL benchmarks on {len(data)} patients...")
            print(f"Scenarios: {scenarios}")
            print()

        for scenario_name in scenarios:
            result = self.run_scenario(scenario_name, data)
            suite.add_result(result)

            if self.verbose:
                print(f"    Mean: {result.mean_time * 1000:.2f} ms")
                print(f"    Throughput: {result.patients_per_second:.1f} patients/sec")
                print()

        return suite

    def print_report(self, suite: BenchmarkSuite):
        """Print benchmark report to console."""
        print()
        print("=" * 70)
        print(f"PSDL Benchmark Report: {suite.name}")
        print("=" * 70)
        print()
        print(f"{'Scenario':<25} {'Complexity':<12} {'Mean (ms)':<12} {'Throughput':<15}")
        print("-" * 70)

        for r in suite.results:
            print(
                f"{r.scenario_name:<25} {r.complexity:<12} "
                f"{r.mean_time * 1000:>10.2f}  {r.patients_per_second:>10.1f}/s"
            )

        print("-" * 70)
        print()


def run_quick_benchmark(num_patients: int = 100) -> BenchmarkSuite:
    """
    Run a quick benchmark with synthetic data.

    This is a convenience function for quick testing.

    Args:
        num_patients: Number of synthetic patients to generate

    Returns:
        BenchmarkSuite with results
    """
    from .data_generator import generate_synthetic_data

    data = generate_synthetic_data(num_patients)
    runner = BenchmarkRunner()
    return runner.run_all(data)
