"""
Tests for PSDL Parser

Run with: pytest tests/test_parser.py -v
"""

from pathlib import Path

import pytest

from psdl.parser import Domain, PSDLParseError, PSDLParser, Severity, WindowSpec


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
    source: creatinine
    unit: mg/dL
logic:
  simple_check:
    expr: Cr > 1.0
"""
        parser = PSDLParser()
        # This will fail validation because Cr is not defined as a trend
        # but the parser should still parse the structure
        with pytest.raises(PSDLParseError):
            parser.parse_string(yaml_content)

    def test_full_scenario(self):
        yaml_content = """
scenario: Test_Full
version: "0.1.0"
description: "A test scenario"
population:
  include:
    - age >= 18
  exclude:
    - status == "DNR"
signals:
  Cr:
    source: creatinine
    concept_id: 3016723
    unit: mg/dL
    domain: measurement
trends:
  cr_high:
    expr: last(Cr) > 1.5
    description: "Creatinine above normal"
logic:
  renal_issue:
    expr: cr_high
    severity: medium
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert scenario.name == "Test_Full"
        assert scenario.version == "0.1.0"
        assert scenario.description == "A test scenario"
        assert len(scenario.signals) == 1
        assert len(scenario.trends) == 1
        assert len(scenario.logic) == 1

    def test_missing_required_field(self):
        yaml_content = """
version: "0.1.0"
signals:
  Cr:
    source: creatinine
logic:
  test:
    expr: Cr > 1.0
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        assert "scenario" in str(exc_info.value)


class TestSignalParsing:
    """Tests for signal parsing."""

    def test_signal_shorthand(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr: creatinine
trends:
  cr_check:
    expr: last(Cr) > 1.0
logic:
  test:
    expr: cr_check
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert "Cr" in scenario.signals
        assert scenario.signals["Cr"].source == "creatinine"

    def test_signal_full_spec(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Lact:
    source: lactate
    concept_id: 3047181
    unit: mmol/L
    domain: measurement
trends:
  lact_check:
    expr: last(Lact) > 2.0
logic:
  test:
    expr: lact_check
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        lact = scenario.signals["Lact"]
        assert lact.source == "lactate"
        assert lact.concept_id == 3047181
        assert lact.unit == "mmol/L"
        assert lact.domain == Domain.MEASUREMENT


class TestTrendParsing:
    """Tests for trend expression parsing."""

    def test_trend_with_comparison(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  cr_rising:
    expr: delta(Cr, 6h) > 0.3
logic:
  test:
    expr: cr_rising
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["cr_rising"]
        assert trend.operator == "delta"
        assert trend.signal == "Cr"
        assert trend.window.value == 6
        assert trend.window.unit == "h"
        assert trend.comparator == ">"
        assert trend.threshold == 0.3

    def test_trend_last_operator(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Lact:
    source: lactate
trends:
  lact_high:
    expr: last(Lact) > 2.0
logic:
  test:
    expr: lact_high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["lact_high"]
        assert trend.operator == "last"
        assert trend.signal == "Lact"
        assert trend.window is None
        assert trend.threshold == 2.0

    def test_trend_slope(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Lact:
    source: lactate
trends:
  lact_rising:
    expr: slope(Lact, 3h) > 0
logic:
  test:
    expr: lact_rising
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        trend = scenario.trends["lact_rising"]
        assert trend.operator == "slope"
        assert trend.window.seconds == 10800  # 3 hours

    def test_trend_invalid_signal_reference(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  invalid:
    expr: delta(UnknownSignal, 6h) > 0.3
logic:
  test:
    expr: invalid
"""
        parser = PSDLParser()
        with pytest.raises(PSDLParseError) as exc_info:
            parser.parse_string(yaml_content)
        assert "UnknownSignal" in str(exc_info.value)


class TestLogicParsing:
    """Tests for logic expression parsing."""

    def test_logic_and(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
  Lact:
    source: lactate
trends:
  cr_high:
    expr: last(Cr) > 1.5
  lact_high:
    expr: last(Lact) > 2.0
logic:
  both_high:
    expr: cr_high AND lact_high
    severity: high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["both_high"]
        assert "cr_high" in logic.terms
        assert "lact_high" in logic.terms
        assert "AND" in logic.operators
        assert logic.severity == Severity.HIGH

    def test_logic_or(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  cr_high:
    expr: last(Cr) > 1.5
  cr_very_high:
    expr: last(Cr) > 3.0
logic:
  cr_abnormal:
    expr: cr_high OR cr_very_high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["cr_abnormal"]
        assert "OR" in logic.operators

    def test_logic_nested(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  A:
    source: signal_a
  B:
    source: signal_b
  C:
    source: signal_c
trends:
  a_high:
    expr: last(A) > 1
  b_high:
    expr: last(B) > 1
  c_high:
    expr: last(C) > 1
logic:
  complex:
    expr: (a_high AND b_high) OR c_high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        logic = scenario.logic["complex"]
        assert "a_high" in logic.terms
        assert "b_high" in logic.terms
        assert "c_high" in logic.terms


class TestPopulationParsing:
    """Tests for population filter parsing."""

    def test_population_include_exclude(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
population:
  include:
    - age >= 18
    - unit == "ICU"
  exclude:
    - status == "DNR"
signals:
  Cr:
    source: creatinine
trends:
  cr_check:
    expr: last(Cr) > 1.0
logic:
  test:
    expr: cr_check
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert len(scenario.population.include) == 2
        assert len(scenario.population.exclude) == 1
        assert "age >= 18" in scenario.population.include

    def test_no_population(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  cr_check:
    expr: last(Cr) > 1.0
logic:
  test:
    expr: cr_check
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        assert scenario.population is None


class TestScenarioValidation:
    """Tests for semantic validation."""

    def test_validate_success(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  cr_high:
    expr: last(Cr) > 1.5
logic:
  renal:
    expr: cr_high
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml_content)

        errors = scenario.validate()
        assert len(errors) == 0

    def test_logic_references_unknown_trend(self):
        yaml_content = """
scenario: Test
version: "0.1.0"
signals:
  Cr:
    source: creatinine
trends:
  cr_high:
    expr: last(Cr) > 1.5
logic:
  bad_logic:
    expr: cr_high AND unknown_trend
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
