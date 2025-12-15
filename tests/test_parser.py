"""
Tests for PSDL Parser

Run with: pytest tests/test_parser.py -v
"""

from pathlib import Path

import pytest

from psdl.core import PSDLParser
from psdl.core.ir import Domain, Severity, WindowSpec
from psdl.core.parser import PSDLParseError


class TestWindowSpec:
    """Tests for WindowSpec parsing."""

    def test_seconds(self):
        ws = WindowSpec(30, "s")
        assert ws.seconds == 30

    def test_minutes(self):
        ws = WindowSpec(5, "m")
        assert ws.seconds == 300

    def test_hours(self):
        ws = WindowSpec(6, "h")
        assert ws.seconds == 21600

    def test_days(self):
        ws = WindowSpec(1, "d")
        assert ws.seconds == 86400

    def test_str(self):
        ws = WindowSpec(6, "h")
        assert str(ws) == "6h"


class TestPSDLParserBasic:
    """Basic parser tests."""

    def test_minimal_scenario(self):
        yaml_content = """
scenario: Test_Minimal
version: "0.1.0"
signals:
  Cr:
    ref: creatinine
    unit: mg/dL
logic:
  simple_check:
    when: Cr > 1.0
"""
        parser = PSDLParser()
        # This will fail validation because Cr is not defined as a trend
        # but the parser should still parse the structure
        with pytest.raises(PSDLParseError):
            parser.parse_string(yaml_content)

    def test_full_scenario(self):
        """Test v0.3 syntax: trends produce numeric, logic handles comparisons."""
        yaml_content = """
scenario: Test_Full
version: "0.3.0"
description: "A test scenario"
population:
  include:
    - age >= 18
  exclude:
    - status == "DNR"
signals:
  Cr:
    ref: creatinine
    concept_id: 3016723
    unit: mg/dL
    domain: measurement
trends:
  cr_value:
    expr: last(Cr)
    description: "Current creatinine value"
logic:
  cr_high:
    when: cr_value > 1.5
    severity: medium
    description: "Creatinine above normal"
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert scenario.name == "Test_Full"
        assert scenario.version == "0.3.0"
        assert scenario.description == "A test scenario"
        assert len(scenario.signals) == 1
        assert len(scenario.trends) == 1
        assert len(scenario.logic) == 1

    def test_missing_required_field(self):
        yaml_content = """
version: "0.1.0"
signals:
  Cr:
    ref: creatinine
logic:
  test:
    when: Cr > 1.0
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        assert "scenario" in str(exc_info.value)


class TestSignalParsing:
    """Tests for signal parsing (v0.3)."""

    def test_signal_shorthand(self):
        """v0.3: Signal shorthand with numeric trend and comparison in logic."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  cr_check:
    when: cr_value > 1.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert "Cr" in scenario.signals
        assert scenario.signals["Cr"].source == "creatinine"

    def test_signal_full_spec(self):
        """v0.3: Full signal spec with numeric trend."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Lact:
    ref: lactate
    concept_id: 3047181
    unit: mmol/L
    domain: measurement
trends:
  lact_value:
    expr: last(Lact)
logic:
  lact_check:
    when: lact_value > 2.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        lact = scenario.signals["Lact"]
        assert lact.source == "lactate"
        assert lact.concept_id == 3047181
        assert lact.unit == "mmol/L"
        assert lact.domain == Domain.MEASUREMENT


class TestTrendParsing:
    """Tests for trend expression parsing (v0.3: numeric only, no comparisons)."""

    def test_trend_numeric_only(self):
        """v0.3: Trends produce numeric values, comparisons in logic."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_delta:
    expr: delta(Cr, 6h)
logic:
  cr_rising:
    when: cr_delta > 0.3
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["cr_delta"]
        assert trend.operator == "delta"
        assert trend.signal == "Cr"
        assert trend.window.value == 6
        assert trend.window.unit == "h"
        # v0.3: No comparator/threshold in trend
        assert trend.comparator is None
        assert trend.threshold is None

    def test_trend_last_operator(self):
        """v0.3: last() returns numeric value."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Lact:
    ref: lactate
trends:
  lact_value:
    expr: last(Lact)
logic:
  lact_high:
    when: lact_value > 2.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["lact_value"]
        assert trend.operator == "last"
        assert trend.signal == "Lact"
        assert trend.window is None
        # v0.3: No threshold in trend
        assert trend.threshold is None

    def test_trend_slope(self):
        """v0.3: slope() returns numeric slope value."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Lact:
    ref: lactate
trends:
  lact_slope:
    expr: slope(Lact, 3h)
logic:
  lact_rising:
    when: lact_slope > 0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["lact_slope"]
        assert trend.operator == "slope"
        assert trend.window.seconds == 10800  # 3 hours

    def test_trend_comparison_rejected(self):
        """v0.3 STRICT: Comparisons in trend expressions MUST be rejected."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  invalid:
    expr: delta(Cr, 6h) > 0.3
logic:
  test:
    when: invalid
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        # Should reject comparison in trend expression
        assert ">" in str(exc_info.value) or "Invalid trend" in str(exc_info.value)

    def test_trend_invalid_signal_reference(self):
        """Unknown signal reference should be rejected."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  invalid:
    expr: delta(UnknownSignal, 6h)
logic:
  test:
    when: invalid > 0.3
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        assert "UnknownSignal" in str(exc_info.value)


class TestLogicParsing:
    """Tests for logic expression parsing (v0.3: comparisons in logic layer)."""

    def test_logic_and(self):
        """v0.3: Logic can combine trend refs with AND, comparisons in when clause."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
  Lact:
    ref: lactate
trends:
  cr_value:
    expr: last(Cr)
  lact_value:
    expr: last(Lact)
logic:
  both_high:
    when: cr_value > 1.5 AND lact_value > 2.0
    severity: high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["both_high"]
        assert "cr_value" in logic.terms
        assert "lact_value" in logic.terms
        assert "AND" in logic.operators
        assert logic.severity == Severity.HIGH

    def test_logic_or(self):
        """v0.3: Logic can use OR with comparisons."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  cr_abnormal:
    when: cr_value > 1.5 OR cr_value > 3.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["cr_abnormal"]
        assert "OR" in logic.operators

    def test_logic_nested(self):
        """v0.3: Nested logic with parentheses and comparisons."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  A:
    ref: signal_a
  B:
    ref: signal_b
  C:
    ref: signal_c
trends:
  a_value:
    expr: last(A)
  b_value:
    expr: last(B)
  c_value:
    expr: last(C)
logic:
  complex:
    when: (a_value > 1 AND b_value > 1) OR c_value > 1
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["complex"]
        assert "a_value" in logic.terms
        assert "b_value" in logic.terms
        assert "c_value" in logic.terms


class TestPopulationParsing:
    """Tests for population filter parsing."""

    def test_population_include_exclude(self):
        """v0.3: Population filters with trends producing numeric, logic with comparison."""
        yaml_content = """
scenario: Test
version: "0.3.0"
population:
  include:
    - age >= 18
    - unit == "ICU"
  exclude:
    - status == "DNR"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  test:
    when: cr_value > 1.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert len(scenario.population.include) == 2
        assert len(scenario.population.exclude) == 1
        assert "age >= 18" in scenario.population.include

    def test_no_population(self):
        """v0.3: Scenario without population filter."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  test:
    when: cr_value > 1.0
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert scenario.population is None


class TestScenarioValidation:
    """Tests for semantic validation (v0.3)."""

    def test_validate_success(self):
        """v0.3: Valid scenario with numeric trends and logic comparisons."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  renal:
    when: cr_value > 1.5
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        errors = scenario.validate()
        assert len(errors) == 0

    def test_logic_references_unknown_trend(self):
        """v0.3: Logic referencing unknown trend should be rejected."""
        yaml_content = """
scenario: Test
version: "0.3.0"
signals:
  Cr:
    ref: creatinine
trends:
  cr_value:
    expr: last(Cr)
logic:
  bad_logic:
    when: cr_value > 1.5 AND unknown_trend > 0
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        assert "unknown_trend" in str(exc_info.value)


class TestExampleScenarios:
    """Test parsing of example scenario files."""

    @pytest.fixture
    def examples_dir(self):
        return Path(__file__).parent.parent / "examples"

    def test_parse_icu_deterioration(self, examples_dir):
        filepath = examples_dir / "icu_deterioration.yaml"
        if filepath.exists():
            parser = PSDLParser()
            scenario = parser.parse_file(str(filepath))

            assert scenario.name == "ICU_Deterioration_v1"
            assert len(scenario.signals) >= 5
            assert len(scenario.trends) >= 5
            assert len(scenario.logic) >= 3

    def test_parse_aki_detection(self, examples_dir):
        filepath = examples_dir / "aki_detection.yaml"
        if filepath.exists():
            parser = PSDLParser()
            scenario = parser.parse_file(str(filepath))

            assert scenario.name == "AKI_KDIGO_Detection"
            assert "Cr" in scenario.signals
            assert "aki_stage1" in scenario.logic

    def test_parse_sepsis_screening(self, examples_dir):
        filepath = examples_dir / "sepsis_screening.yaml"
        if filepath.exists():
            parser = PSDLParser()
            scenario = parser.parse_file(str(filepath))

            assert scenario.name == "Sepsis_Screening_v1"
            assert "qsofa_2" in scenario.logic
            assert "sepsis_screen_positive" in scenario.logic


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
