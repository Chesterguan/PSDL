"""
PSDL Benchmarking Suite

Provides utilities for benchmarking PSDL scenario evaluation performance
across different runtimes and dataset sizes.

Features:
- Timing utilities with statistical analysis
- Synthetic patient data generation
- Pre-built benchmark scenarios of varying complexity
- Performance reporting

Usage:
    from psdl.benchmarks import BenchmarkRunner, generate_synthetic_data

    # Generate synthetic patient data
    data = generate_synthetic_data(num_patients=1000)

    # Run benchmarks
    runner = BenchmarkRunner()
    results = runner.run_all(data)
    runner.print_report(results)
"""

from .data_generator import SyntheticDataConfig, generate_synthetic_data
from .runner import BenchmarkResult, BenchmarkRunner, BenchmarkSuite
from .scenarios import BENCHMARK_SCENARIOS, get_benchmark_scenario

__all__ = [
    "BenchmarkRunner",
    "BenchmarkResult",
    "BenchmarkSuite",
    "generate_synthetic_data",
    "SyntheticDataConfig",
    "BENCHMARK_SCENARIOS",
    "get_benchmark_scenario",
]
