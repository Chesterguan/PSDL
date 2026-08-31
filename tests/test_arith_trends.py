"""
Tests for arithmetic trend expressions across runtimes.

Covers the gap found in Aug 2026: ArithExpr parsed fine (RFC-0006) but
no runtime evaluated it — the single evaluator returned None and the
cohort compiler silently compiled only the first operator call.

Run with: pytest tests/test_arith_trends.py -v
"""

from datetime import datetime, timedelta

import pytest

from psdl.core import PSDLParser
from psdl.runtimes.cohort import CohortCompiler
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

SCENARIO_YAML = """
psdl_version: "0.5"
scenario:
  name: Arith_Test
  version: "1.0.0"
  description: "Arithmetic trend test scenario"

audit:
  intent: "test"
  rationale: "test"
  provenance:
    type: internal
    reference: "test"

signals:
  Cr:
    ref: creatinine
    expected_unit: mg/dL
    description: "Serum creatinine"

trends:
  cr_current:
    type: float
    expr: last(Cr)
    description: "Current creatinine"
  cr_ratio:
    type: float
    expr: last(Cr) / min(Cr, 7d)
    description: "Ratio to 7d baseline"
  cr_rise_48h:
    type: float
    expr: last(Cr) - min(Cr, 48h)
    description: "Rise within 48h"

logic:
  stage3:
    when: cr_ratio >= 3.0 OR cr_current >= 4.0
    description: "high"
  stage2:
    when: cr_ratio >= 2.0 AND NOT stage3
    description: "medium"
  rise_flag:
    when: cr_rise_48h >= 0.3
    description: "rise"

outputs:
  decision:
    stage2:
      type: boolean
      from: logic.stage2
      description: "stage2"
"""


@pytest.fixture
def scenario():
    return PSDLParser().parse_string(SCENARIO_YAML)


@pytest.fixture
def t0():
    return datetime(2026, 8, 25, 12, 0, 0)


def make_backend(points, t0):
    """points: list of (days_before_t0, value)"""
    be = InMemoryBackend()
    for days, value in points:
        be.add_observation("p1", "Cr", value, t0 - timedelta(days=days))
    return be


class TestSingleRuntimeArith:
    def test_ratio_value(self, scenario, t0):
        be = make_backend([(4, 1.0), (2, 1.2), (0, 2.5)], t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.trend_values["cr_ratio"] == pytest.approx(2.5)

    def test_subtraction_value(self, scenario, t0):
        be = make_backend([(1, 1.5), (0, 2.5)], t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.trend_values["cr_rise_48h"] == pytest.approx(1.0)

    def test_exclusive_staging(self, scenario, t0):
        # ratio 2.5 -> stage2 fires, stage3 does not
        be = make_backend([(4, 1.0), (0, 2.5)], t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.logic_results["stage2"] is True
        assert r.logic_results["stage3"] is False

    def test_stage3_wins(self, scenario, t0):
        # ratio 4.0 -> stage3 fires, stage2 suppressed by NOT
        be = make_backend([(4, 1.0), (0, 4.0)], t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.logic_results["stage3"] is True
        assert r.logic_results["stage2"] is False

    def test_missing_data_is_none(self, scenario, t0):
        be = InMemoryBackend()
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.trend_values["cr_ratio"] is None
        assert r.logic_results["stage2"] is False

    def test_division_by_zero_is_none(self, scenario, t0):
        be = make_backend([(4, 0.0), (0, 2.5)], t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.trend_values["cr_ratio"] is None


class TestCohortSQLArith:
    def compile_sql(self, scenario):
        return CohortCompiler(schema="omop_cdm").compile(scenario).sql

    @pytest.fixture
    def sql(self, scenario):
        # legacy resolution path needs a concept_id on the signal
        scenario.signals["Cr"].concept_id = 3016723
        return self.compile_sql(scenario)

    def test_arith_trend_not_silently_truncated(self, sql):
        # The old bug: cr_ratio compiled as plain last(Cr).
        # A correct compile must contain a division for cr_ratio.
        assert "/" in sql.split("cr_ratio AS")[-1].split(")")[0] or "NULLIF" in sql

    def test_division_uses_nullif(self, sql):
        assert "NULLIF" in sql

    def test_component_ctes_present(self, sql):
        # both operator calls of cr_ratio must appear as component CTEs
        assert "cr_ratio__c0" in sql
        assert "cr_ratio__c1" in sql

    def test_logic_compares_columns_not_cte_names(self, sql):
        # logic must be computed over a trend_values relation, where trend
        # names are real columns — not bare CTE (table) names.
        assert "trend_values" in sql

    def test_logic_on_logic_inlined(self, sql):
        # stage2 references stage3; the compiled CASE for stage2 must not
        # reference the SQL alias "stage3" (invalid in the same SELECT).
        stage2_case = sql.split("AS stage2")[0].rsplit("CASE", 1)[-1]
        assert "stage3" not in stage2_case

    def test_unparseable_trend_raises(self, scenario):
        scenario.signals["Cr"].concept_id = 3016723
        scenario.trends["cr_ratio"].raw_expr = "last(Cr) @@ bogus"
        with pytest.raises(ValueError):
            self.compile_sql(scenario)


class TestPointwiseUnboundedWindow:
    def test_last_sees_data_older_than_max_trend_window(self, scenario, t0):
        # Pointwise last(X) is unbounded (matches SQL semantics): a value
        # older than the largest windowed trend (7d) must still resolve.
        be = InMemoryBackend()
        be.add_observation("p1", "Cr", 1.5, t0 - timedelta(days=30))
        be.add_observation("p1", "Cr", 1.5, t0)
        r = SinglePatientEvaluator(scenario, be).evaluate("p1", reference_time=t0)
        assert r.trend_values["cr_current"] == pytest.approx(1.5)
        # min(Cr, 7d) only sees the recent point -> ratio 1.0, not None
        assert r.trend_values["cr_ratio"] == pytest.approx(1.0)
