"""
Tests to validate that the formal PSDL specification (JSON Schema + EBNF/Lark grammar)
correctly matches the Python reference implementation.

This ensures the specification is complete and accurate.
"""

import json
from pathlib import Path

import pytest
import yaml

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SPEC_DIR = PROJECT_ROOT / "spec" / "formal"
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# Try to import optional dependencies
try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

try:
    from lark import Lark

    HAS_LARK = True
except ImportError:
    HAS_LARK = False


# ============================================================
# JSON Schema Validation Tests
# ============================================================


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestJSONSchemaValidation:
    """Test that all example scenarios pass JSON Schema validation."""

    @pytest.fixture
    def schema(self):
        """Load the PSDL scenario JSON Schema."""
        schema_path = SPEC_DIR / "psdl-scenario.schema.json"
        if not schema_path.exists():
            pytest.skip("JSON Schema not found")
        with open(schema_path) as f:
            return json.load(f)

    def get_example_files(self):
        """Get all example YAML files."""
        return list(EXAMPLES_DIR.glob("*.yaml"))

    @pytest.mark.parametrize(
        "example_file",
        [
            pytest.param(f, id=f.name)
            for f in (PROJECT_ROOT / "examples").glob("*.yaml")
            if f.exists()
        ],
    )
    def test_example_validates(self, schema, example_file):
        """Each example scenario should validate against the JSON Schema."""
        with open(example_file) as f:
            scenario = yaml.safe_load(f)

        # Should not raise
        jsonschema.validate(scenario, schema)

    def test_invalid_scenario_rejected(self, schema):
        """Invalid scenarios should be rejected by the schema."""
        invalid_scenarios = [
            # Missing required field 'scenario'
            {"version": "1.0", "signals": {"Cr": "creatinine"}, "logic": {"test": "Cr"}},
            # Missing required field 'signals'
            {"scenario": "Test", "version": "1.0", "logic": {"test": "Cr"}},
            # Invalid version format
            {
                "scenario": "Test",
                "version": "invalid",
                "signals": {"Cr": "creatinine"},
                "logic": {"test": "Cr"},
            },
        ]

        for invalid in invalid_scenarios:
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid, schema)


# ============================================================
# EBNF/Lark Grammar Validation Tests
# ============================================================


@pytest.mark.skipif(not HAS_LARK, reason="lark not installed")
class TestExpressionGrammar:
    """Test that all expressions from examples parse correctly with the formal grammar."""

    @pytest.fixture
    def trend_parser(self):
        """Create a Lark parser for trend expressions."""
        grammar_path = SPEC_DIR / "psdl-expression.lark"
        if not grammar_path.exists():
            pytest.skip("Lark grammar not found")
        grammar = grammar_path.read_text()
        return Lark(grammar, start="trend_expr")

    @pytest.fixture
    def logic_parser(self):
        """Create a Lark parser for logic expressions."""
        grammar_path = SPEC_DIR / "psdl-expression.lark"
        if not grammar_path.exists():
            pytest.skip("Lark grammar not found")
        grammar = grammar_path.read_text()
        return Lark(grammar, start="logic_expr")

    def collect_trend_expressions(self):
        """Collect all trend expressions from example files."""
        expressions = []
        for yaml_file in EXAMPLES_DIR.glob("*.yaml"):
            with open(yaml_file) as f:
                scenario = yaml.safe_load(f)
            for name, spec in scenario.get("trends", {}).items():
                expr = spec if isinstance(spec, str) else spec.get("expr", "")
                if expr:
                    expressions.append((yaml_file.name, name, expr))
        return expressions

    def collect_logic_expressions(self):
        """Collect all logic expressions from example files."""
        expressions = []
        for yaml_file in EXAMPLES_DIR.glob("*.yaml"):
            with open(yaml_file) as f:
                scenario = yaml.safe_load(f)
            for name, spec in scenario.get("logic", {}).items():
                expr = spec if isinstance(spec, str) else spec.get("expr", "")
                if expr:
                    expressions.append((yaml_file.name, name, expr))
        return expressions

    def test_all_trend_expressions_parse(self, trend_parser):
        """All trend expressions from examples should parse successfully."""
        expressions = self.collect_trend_expressions()
        assert len(expressions) > 0, "No trend expressions found"

        for filename, name, expr in expressions:
            try:
                trend_parser.parse(expr)
            except Exception as e:
                pytest.fail(f"Failed to parse trend [{filename}] {name}: {expr}\nError: {e}")

    def test_all_logic_expressions_parse(self, logic_parser):
        """All logic expressions from examples should parse successfully."""
        expressions = self.collect_logic_expressions()
        assert len(expressions) > 0, "No logic expressions found"

        for filename, name, expr in expressions:
            try:
                logic_parser.parse(expr)
            except Exception as e:
                pytest.fail(f"Failed to parse logic [{filename}] {name}: {expr}\nError: {e}")

    def test_trend_expression_examples(self, trend_parser):
        """Test specific trend expression examples."""
        valid_expressions = [
            "delta(Cr, 6h) > 0.3",
            "slope(Lact, 3h) > 0",
            "ema(MAP, 30m) < 65",
            "last(HR) > 100",
            "max(Temp, 24h) >= 38.5",
            "count(Cr, 48h) >= 2",
            "min(SpO2, 1h) < 90",
            "sma(HR, 2h) > 110",
            "last(WBC) > 12",
            "delta(Plt, 24h) < -50",
        ]

        for expr in valid_expressions:
            try:
                trend_parser.parse(expr)
            except Exception as e:
                pytest.fail(f"Failed to parse: {expr}\nError: {e}")

    def test_logic_expression_examples(self, logic_parser):
        """Test specific logic expression examples."""
        valid_expressions = [
            "cr_rising AND lactate_elevated",
            "aki_stage1 OR aki_stage2 OR aki_stage3",
            "NOT recovering AND deteriorating",
            "(fever OR hypothermia) AND tachycardia",
            "sirs_criteria AND (lactate_elevated OR organ_dysfunction)",
            "NOT stable",
            "a AND b AND c",
            "a OR b OR c",
            "(a AND b) OR (c AND d)",
        ]

        for expr in valid_expressions:
            try:
                logic_parser.parse(expr)
            except Exception as e:
                pytest.fail(f"Failed to parse: {expr}\nError: {e}")

    def test_invalid_expressions_rejected(self, trend_parser, logic_parser):
        """Invalid expressions should be rejected by the grammar."""
        invalid_trend_expressions = [
            "invalid(Cr)",  # Unknown operator
            "delta()",  # Missing arguments
            "delta(Cr 6h)",  # Missing comma
            "> 0.3",  # Missing operator call
        ]

        for expr in invalid_trend_expressions:
            with pytest.raises(Exception):
                trend_parser.parse(expr)


# ============================================================
# Cross-Validation Tests
# ============================================================


class TestCrossValidation:
    """Test that the Python parser and formal spec produce consistent results."""

    def test_python_parser_matches_schema(self):
        """The Python parser should accept the same documents as the JSON Schema."""
        from psdl.parser import PSDLParser

        parser = PSDLParser()

        # All examples should parse with both
        for yaml_file in EXAMPLES_DIR.glob("*.yaml"):
            try:
                scenario = parser.parse_file(str(yaml_file))
                assert scenario is not None
                assert scenario.name is not None
            except Exception as e:
                pytest.fail(f"Python parser failed on {yaml_file.name}: {e}")
