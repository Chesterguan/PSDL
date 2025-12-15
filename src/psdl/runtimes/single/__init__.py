"""
PSDL Single Patient Runtime - Python-based single patient evaluation.

This runtime evaluates PSDL scenarios for individual patients using
in-memory Python computation. It's optimized for:
- Real-time alerting (low latency)
- Interactive evaluation
- Testing and development
- ScenarioIR integration for DAG-ordered evaluation

Usage:
    from psdl.runtimes.single import SinglePatientEvaluator, InMemoryBackend

    backend = InMemoryBackend()
    backend.add_data(patient_id=1, signal_name="Cr", data=[...])

    evaluator = SinglePatientEvaluator(scenario, backend)
    result = evaluator.evaluate(patient_id=1)

    if result.is_triggered:
        print(f"Alert: {result.triggered_logic}")

    # v0.3: From compiled IR (recommended for production/audit)
    from psdl.core.compile import compile_scenario
    ir = compile_scenario("scenario.yaml")
    evaluator = SinglePatientEvaluator.from_ir(ir, backend)
    result = evaluator.evaluate(patient_id=1)
    print(f"Hashes: {result.compilation_hashes}")
"""

from .evaluator import (
    CompilationHashes,
    DataBackend,
    EvaluationContext,
    EvaluationResult,
    InMemoryBackend,
    SinglePatientEvaluator,
)

# Legacy alias
PSDLEvaluator = SinglePatientEvaluator

__all__ = [
    "SinglePatientEvaluator",
    "PSDLEvaluator",
    "InMemoryBackend",
    "DataBackend",
    "EvaluationResult",
    "EvaluationContext",
    "CompilationHashes",
]
