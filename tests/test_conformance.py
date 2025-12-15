"""
PSDL Conformance Test Runner

Executes the conformance test suite (spec/conformance/operator_tests.json)
against the Python reference implementation to validate spec correctness.

This is a critical part of the spec-first development approach:
    SPEC (foundation) → Conformance Tests (executable spec) → Implementation
"""

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest

# Import the implementation to test
from psdl.operators import DataPoint, TemporalOperators

# Optional: JSON Schema validation
try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

# Path to conformance tests
CONFORMANCE_TESTS_PATH = (
    Path(__file__).parent.parent / "spec" / "conformance" / "operator_tests.json"
)
CONFORMANCE_SCHEMA_PATH = (
    Path(__file__).parent.parent / "spec" / "conformance" / "conformance-tests.schema.json"
)

# Window unit to seconds mapping
WINDOW_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def parse_window(window_str: str) -> int:
    """Parse window string like '6h' into seconds."""
    match = re.match(r"(\d+)([smhdw])", window_str)
    if not match:
        raise ValueError(f"Invalid window format: {window_str}")

    value = int(match.group(1))
    unit = match.group(2)

    return value * WINDOW_UNITS[unit]


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 timestamp."""
    # Handle Z suffix (UTC)
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    return datetime.fromisoformat(ts_str)


def create_datapoints(data: List[Dict]) -> List[DataPoint]:
    """Convert test data to DataPoint objects, including nulls."""
    result = []
    for item in data:
        ts = parse_timestamp(item["timestamp"])
        value = item["value"]  # Can be None - DataPoint.value is now Optional[float]
        result.append(DataPoint(timestamp=ts, value=value))
    return result


def create_all_datapoints(data: List[Dict]) -> List[DataPoint]:
    """Convert all test data to DataPoint objects (alias for create_datapoints)."""
    return create_datapoints(data)


def parse_simple_expression(
    expression: str,
) -> Tuple[str, Optional[str], str, Optional[int]]:
    """
    Parse simple expression like 'delta(Cr, 6h)' or 'last(HR)' or 'percentile(HR, 1h, 50)'.
    Returns (operator_name, window_str or None, signal_name, extra_arg or None)
    """
    # Try percentile pattern first (3 arguments)
    percentile_match = re.match(r"(\w+)\((\w+),\s*(\d+[smhdw]),\s*(\d+)\)", expression)
    if percentile_match:
        operator = percentile_match.group(1)
        signal = percentile_match.group(2)
        window = percentile_match.group(3)
        extra = int(percentile_match.group(4))
        return operator, window, signal, extra

    # Standard pattern (1 or 2 arguments)
    match = re.match(r"(\w+)\((\w+)(?:,\s*(\d+[smhdw]))?\)", expression)
    if not match:
        raise ValueError(f"Cannot parse expression: {expression}")

    operator = match.group(1)
    signal = match.group(2)
    window = match.group(3)

    return operator, window, signal, None


def parse_comparison_expression(expression: str) -> Tuple[str, str, float]:
    """
    Parse comparison expression like 'delta(Cr, 6h) > 0.3'.
    Returns (operator_call, comparison_op, threshold)
    """
    match = re.match(r"(.+?)\s*([><=!]+)\s*(-?\d+(?:\.\d+)?)", expression)
    if not match:
        raise ValueError(f"Cannot parse comparison: {expression}")

    return match.group(1).strip(), match.group(2), float(match.group(3))


def execute_operator(
    operator: str,
    datapoints: List[DataPoint],
    window_seconds: Optional[int],
    eval_time: datetime,
    has_null_values: bool = False,
    extra_arg: Optional[int] = None,
) -> Optional[Union[float, int, bool]]:
    """Execute a single operator and return the result."""
    if operator == "delta":
        return TemporalOperators.delta(datapoints, window_seconds, eval_time)
    elif operator == "slope":
        return TemporalOperators.slope(datapoints, window_seconds, eval_time)
    elif operator == "last":
        filtered_data = [dp for dp in datapoints if dp.timestamp <= eval_time]
        return TemporalOperators.last(filtered_data)
    elif operator == "count":
        return TemporalOperators.count(datapoints, window_seconds, eval_time)
    elif operator == "min":
        return TemporalOperators.min_val(datapoints, window_seconds, eval_time)
    elif operator == "max":
        return TemporalOperators.max_val(datapoints, window_seconds, eval_time)
    elif operator == "sma":
        return TemporalOperators.sma(datapoints, window_seconds, eval_time)
    elif operator == "ema":
        return TemporalOperators.ema(datapoints, window_seconds, eval_time)
    elif operator == "first":
        return TemporalOperators.first(datapoints, window_seconds, eval_time)
    elif operator in ("std", "stddev"):
        return TemporalOperators.std(datapoints, window_seconds, eval_time)
    elif operator == "percentile":
        if extra_arg is None:
            raise ValueError("percentile requires a percentile value argument")
        return TemporalOperators.percentile(datapoints, window_seconds, extra_arg, eval_time)
    elif operator == "exists":
        return len(datapoints) > 0 or has_null_values
    elif operator == "missing":
        return len(datapoints) == 0 and not has_null_values
    else:
        raise ValueError(f"Unknown operator: {operator}")


def apply_comparison(value: Optional[float], op: str, threshold: float) -> bool:
    """Apply comparison operator with null handling (null comparison always returns False)."""
    if value is None:
        return False

    if op == ">":
        return value > threshold
    elif op == ">=":
        return value >= threshold
    elif op == "<":
        return value < threshold
    elif op == "<=":
        return value <= threshold
    elif op == "==" or op == "=":
        return math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
    elif op == "!=":
        return not math.isclose(value, threshold, rel_tol=1e-9, abs_tol=1e-9)
    else:
        raise ValueError(f"Unknown comparison operator: {op}")


def evaluate_boolean_expression(expression: str, trends: Dict[str, bool]) -> bool:
    """Evaluate a boolean expression with trend references."""
    # Replace trend references with their boolean values
    expr = expression

    # Handle parentheses properly by evaluating from Python's perspective
    # Replace NOT, AND, OR with Python operators
    expr = re.sub(r"\bNOT\b", "not", expr)
    expr = re.sub(r"\bAND\b", "and", expr)
    expr = re.sub(r"\bOR\b", "or", expr)

    # Replace trend names with their values
    for trend_name, trend_value in trends.items():
        expr = re.sub(rf"\b{trend_name}\b", str(trend_value), expr)

    # Evaluate the expression
    return eval(expr)


def compare_results(actual: Any, expected: Any, tolerance: float = 1e-6) -> Tuple[bool, str]:
    """Compare actual vs expected result with appropriate tolerance."""
    # Handle None/null
    if expected is None and actual is None:
        return True, ""
    if expected is None or actual is None:
        return False, f"Null mismatch: expected {expected}, got {actual}"

    # Handle special expected format for slope ({"type": "positive", "approximation": value})
    if isinstance(expected, dict):
        if "type" in expected and "approximation" in expected:
            expected_type = expected["type"]
            expected_approx = expected["approximation"]

            if expected_type == "positive" and actual <= 0:
                return False, f"Expected positive slope, got {actual}"
            if expected_type == "negative" and actual >= 0:
                return False, f"Expected negative slope, got {actual}"
            if expected_type == "zero" and not math.isclose(actual, 0, abs_tol=tolerance):
                return False, f"Expected zero slope, got {actual}"

            # Check approximation is close
            if not math.isclose(actual, expected_approx, rel_tol=0.01, abs_tol=1e-6):
                return (
                    False,
                    f"Slope approximation mismatch: expected ~{expected_approx}, got {actual}",
                )

            return True, ""

        # Handle range expected format ({"type": "range", "min": X, "max": Y})
        if expected.get("type") == "range" and "min" in expected and "max" in expected:
            min_val = expected["min"]
            max_val = expected["max"]
            if actual is None:
                return False, f"Expected range [{min_val}, {max_val}], got None"
            if min_val <= actual <= max_val:
                return True, ""
            return (
                False,
                f"Value {actual} outside expected range [{min_val}, {max_val}]",
            )

    # Handle booleans
    if isinstance(expected, bool):
        return (
            actual == expected,
            f"Expected {expected}, got {actual}" if actual != expected else "",
        )

    # Handle numeric comparison
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
            return True, ""
        return False, f"Value mismatch: expected {expected}, got {actual}"

    # Default comparison
    return (
        actual == expected,
        f"Expected {expected}, got {actual}" if actual != expected else "",
    )


def run_operator_test(test_case: Dict) -> Tuple[bool, Any, Any, str]:
    """
    Run a single operator test case.
    Returns (passed, actual_result, expected_result, error_message)
    """
    test_input = test_case["input"]
    expected = test_case["expected"]
    expression = test_input.get("expression", "")

    try:
        # Handle boolean logic tests (trends-based)
        if "trends" in test_input:
            trends = test_input["trends"]
            actual = evaluate_boolean_expression(expression, trends)
            passed, err = compare_results(actual, expected)
            return passed, actual, expected, err

        # Handle comparison tests (expression with comparison operator)
        if any(op in expression for op in [" > ", " < ", " >= ", " <= ", " == ", " != "]):
            operator_call, comp_op, threshold = parse_comparison_expression(expression)
            operator, window_str, signal, extra_arg = parse_simple_expression(operator_call)

            data = test_input.get("data", [])
            eval_time = parse_timestamp(test_input["evaluationTime"])
            window_seconds = parse_window(window_str) if window_str else None

            has_null_values = any(d["value"] is None for d in data)
            datapoints = (
                create_all_datapoints(data) if operator == "count" else create_datapoints(data)
            )

            operator_result = execute_operator(
                operator,
                datapoints,
                window_seconds,
                eval_time,
                has_null_values,
                extra_arg,
            )
            actual = apply_comparison(operator_result, comp_op, threshold)

            passed, err = compare_results(actual, expected)
            return passed, actual, expected, err

        # Handle simple operator tests
        operator, window_str, signal, extra_arg = parse_simple_expression(expression)
        data = test_input.get("data", [])
        eval_time = parse_timestamp(test_input["evaluationTime"])
        window_seconds = parse_window(window_str) if window_str else None

        has_null_values = any(d["value"] is None for d in data)

        # For count operator, include all data points (including nulls per spec)
        if operator == "count":
            datapoints = create_all_datapoints(data)
        else:
            datapoints = create_datapoints(data)

        actual = execute_operator(
            operator, datapoints, window_seconds, eval_time, has_null_values, extra_arg
        )

        passed, err = compare_results(actual, expected)
        return passed, actual, expected, err

    except Exception as e:
        import traceback

        return False, None, expected, f"Exception: {str(e)}\n{traceback.format_exc()}"


def load_conformance_tests() -> Dict:
    """Load the conformance test suite."""
    with open(CONFORMANCE_TESTS_PATH, "r") as f:
        return json.load(f)


def get_all_operator_tests() -> List[Tuple[str, str, Dict]]:
    """Get all operator test cases as (group_name, test_id, test_case) tuples."""
    tests = load_conformance_tests()
    result = []

    # New format: groups is an array
    for group in tests.get("groups", []):
        group_name = group.get("name", "unknown")
        for test_case in group.get("tests", []):
            result.append((group_name, test_case["id"], test_case))

    return result


# Helper function for generating test IDs (not a test itself)
def _test_id_generator(val):
    """Generate readable test IDs for parametrized tests."""
    if isinstance(val, tuple) and len(val) == 3:
        return f"{val[0]}::{val[1]}"
    return str(val)


class TestConformance:
    """Conformance test suite for PSDL operators."""

    @pytest.fixture(scope="class")
    def conformance_tests(self):
        """Load conformance tests once per test class."""
        return load_conformance_tests()

    def test_conformance_file_exists(self):
        """Verify conformance test file exists."""
        assert (
            CONFORMANCE_TESTS_PATH.exists()
        ), f"Conformance tests not found at {CONFORMANCE_TESTS_PATH}"

    def test_conformance_file_valid(self, conformance_tests):
        """Verify conformance test file is valid JSON with expected structure."""
        assert "groups" in conformance_tests, "Missing 'groups' array"
        assert "version" in conformance_tests, "Missing 'version' field"
        assert "name" in conformance_tests, "Missing 'name' field"
        assert conformance_tests["version"] == "0.3.0"
        assert isinstance(conformance_tests["groups"], list), "'groups' should be an array"

    @pytest.mark.skipif(not JSONSCHEMA_AVAILABLE, reason="jsonschema not installed")
    def test_conformance_file_matches_schema(self, conformance_tests):
        """Validate conformance test file against JSON Schema."""
        assert CONFORMANCE_SCHEMA_PATH.exists(), f"Schema not found at {CONFORMANCE_SCHEMA_PATH}"

        with open(CONFORMANCE_SCHEMA_PATH, "r") as f:
            schema = json.load(f)

        # This will raise ValidationError if invalid
        jsonschema.validate(conformance_tests, schema)

    @pytest.mark.skipif(not JSONSCHEMA_AVAILABLE, reason="jsonschema not installed")
    def test_all_conformance_files_match_schema(self):
        """Validate all conformance test files against JSON Schema."""
        conformance_dir = CONFORMANCE_TESTS_PATH.parent
        test_files = [
            conformance_dir / "operator_tests.json",
            conformance_dir / "expression_tests.json",
            conformance_dir / "scenario_tests.json",
        ]

        with open(CONFORMANCE_SCHEMA_PATH, "r") as f:
            schema = json.load(f)

        for test_file in test_files:
            if test_file.exists():
                with open(test_file, "r") as f:
                    tests = json.load(f)
                try:
                    jsonschema.validate(tests, schema)
                except jsonschema.ValidationError as e:
                    pytest.fail(f"{test_file.name} failed validation: {e.message}")


# Dynamically generate test cases from conformance suite
@pytest.mark.parametrize(
    "suite_name,test_id,test_case",
    get_all_operator_tests(),
    ids=lambda x: f"{x[1]}" if isinstance(x, tuple) and len(x) >= 2 else str(x),
)
def test_operator_conformance(suite_name: str, test_id: str, test_case: Dict):
    """
    Run individual conformance test case.

    Each test validates that the implementation matches the spec-defined behavior.
    """
    passed, actual, expected, error_msg = run_operator_test(test_case)

    test_name = test_case.get("name", test_id)
    explanation = test_case.get("explanation", "")

    assert passed, (
        f"\n  Test: {test_name}"
        f"\n  Expression: {test_case['input']['expression']}"
        f"\n  Expected: {expected}"
        f"\n  Actual: {actual}"
        f"\n  Explanation: {explanation}"
        f"\n  Error: {error_msg}"
    )


class TestComparisonConformance:
    """Test comparison operator conformance."""

    @pytest.fixture
    def conformance_tests(self):
        return load_conformance_tests()

    @pytest.mark.parametrize(
        "left,op,right,expected",
        [
            (3.0, ">", 2.0, True),
            (2.0, ">", 3.0, False),
            (2.0, "==", 2.0, True),
            (None, ">", 5, False),
            (None, "==", None, False),
            (5, ">=", 5, True),
            (5, "<=", 5, True),
            (5, "!=", 5, False),
            (5, "!=", 6, True),
        ],
    )
    def test_comparison_operators(self, left, op, right, expected):
        """Test comparison operators with null handling."""
        # Per spec: Any comparison involving null returns false
        if left is None or right is None:
            actual = False
        elif op == ">":
            actual = left > right
        elif op == ">=":
            actual = left >= right
        elif op == "<":
            actual = left < right
        elif op == "<=":
            actual = left <= right
        elif op == "==":
            actual = left == right
        elif op == "!=":
            actual = left != right
        else:
            raise ValueError(f"Unknown operator: {op}")

        assert actual == expected, f"{left} {op} {right} should be {expected}, got {actual}"


class TestBooleanLogicConformance:
    """Test boolean logic conformance."""

    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ],
    )
    def test_and_operator(self, a, b, expected):
        """Test AND truth table."""
        assert (a and b) == expected

    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (True, True, True),
            (True, False, True),
            (False, True, True),
            (False, False, False),
        ],
    )
    def test_or_operator(self, a, b, expected):
        """Test OR truth table."""
        assert (a or b) == expected

    @pytest.mark.parametrize(
        "a,expected",
        [
            (True, False),
            (False, True),
        ],
    )
    def test_not_operator(self, a, expected):
        """Test NOT truth table."""
        assert (not a) == expected

    def test_precedence(self):
        """Test operator precedence: NOT > AND > OR."""
        # NOT has highest precedence
        assert (not False and True) is True  # (not False) and True = True
        assert (not True or True) is True  # (not True) or True = True

        # AND has higher precedence than OR
        assert (True or False and False) is True  # True or (False and False)
        assert (False or True and True) is True  # False or (True and True)
        assert (False and True or True) is True  # (False and True) or True


class TestConformanceSummary:
    """Generate summary of conformance test results."""

    def test_generate_summary(self, capsys):
        """Print summary of all conformance tests (always passes, for reporting)."""
        tests = get_all_operator_tests()

        results = {"passed": 0, "failed": 0, "errors": []}

        for suite_name, test_id, test_case in tests:
            passed, actual, expected, error_msg = run_operator_test(test_case)
            if passed:
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "id": test_id,
                        "name": test_case.get("name"),
                        "expected": expected,
                        "actual": actual,
                        "error": error_msg,
                    }
                )

        total = results["passed"] + results["failed"]

        print(f"\n{'='*60}")
        print("PSDL Conformance Test Summary")
        print(f"{'='*60}")
        print(f"Total tests: {total}")
        print(f"Passed: {results['passed']}")
        print(f"Failed: {results['failed']}")
        print(f"Pass rate: {results['passed']/total*100:.1f}%")

        if results["errors"]:
            print("\nFailed tests:")
            for err in results["errors"]:
                print(f"  - {err['id']}: {err['name']}")
                print(f"    Expected: {err['expected']}, Got: {err['actual']}")
                if err["error"]:
                    print(f"    Error: {err['error']}")

        print(f"{'='*60}\n")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "--tb=short"])
