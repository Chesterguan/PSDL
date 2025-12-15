"""
Auto-generated conformance tests from spec/conformance/
Generated: 2025-12-15T12:25:43.201249

DO NOT EDIT - Regenerate with: python tools/codegen.py --conformance
"""

import pytest

from psdl.expression_parser import (
    AndExpr,
    ArithExpr,
    ComparisonExpr,
    NotExpr,
    OrExpr,
    PSDLExpressionError,
    PSDLExpressionParser,
    TermRef,
    TrendExpression,
    extract_operators,
    extract_terms,
)


@pytest.fixture
def parser():
    """Create parser instance for tests."""
    return PSDLExpressionParser()


# ======================================================================
# VALID PARSE TESTS
# ======================================================================


def test_valid_delta_0(parser):
    """Parse valid delta expression"""
    result = parser.parse_trend("delta(Cr, 6h)")
    assert result is not None
    assert result.temporal.operator == "delta"
    assert result.temporal.signal == "Cr"
    assert result.temporal.window.value == 6
    assert result.temporal.window.unit == "h"


def test_valid_delta_1(parser):
    """Parse valid delta expression"""
    result = parser.parse_trend("delta(HR, 30m)")
    assert result is not None
    assert result.temporal.operator == "delta"
    assert result.temporal.signal == "HR"
    assert result.temporal.window.value == 30
    assert result.temporal.window.unit == "m"


def test_valid_delta_2(parser):
    """Parse valid delta expression"""
    result = parser.parse_trend("delta(Temp, 1d)")
    assert result is not None
    assert result.temporal.operator == "delta"
    assert result.temporal.signal == "Temp"
    assert result.temporal.window.value == 1
    assert result.temporal.window.unit == "d"


def test_valid_slope_3(parser):
    """Parse valid slope expression"""
    result = parser.parse_trend("slope(Lact, 3h)")
    assert result is not None
    assert result.temporal.operator == "slope"
    assert result.temporal.signal == "Lact"
    assert result.temporal.window.value == 3
    assert result.temporal.window.unit == "h"


def test_valid_slope_4(parser):
    """Parse valid slope expression"""
    result = parser.parse_trend("slope(Cr, 24h)")
    assert result is not None
    assert result.temporal.operator == "slope"
    assert result.temporal.signal == "Cr"
    assert result.temporal.window.value == 24
    assert result.temporal.window.unit == "h"


def test_valid_ema_5(parser):
    """Parse valid ema expression"""
    result = parser.parse_trend("ema(HR, 1h)")
    assert result is not None
    assert result.temporal.operator == "ema"
    assert result.temporal.signal == "HR"
    assert result.temporal.window.value == 1
    assert result.temporal.window.unit == "h"


def test_valid_sma_6(parser):
    """Parse valid sma expression"""
    result = parser.parse_trend("sma(SpO2, 30m)")
    assert result is not None
    assert result.temporal.operator == "sma"
    assert result.temporal.signal == "SpO2"
    assert result.temporal.window.value == 30
    assert result.temporal.window.unit == "m"


def test_valid_min_7(parser):
    """Parse valid min expression"""
    result = parser.parse_trend("min(BP_sys, 6h)")
    assert result is not None
    assert result.temporal.operator == "min"
    assert result.temporal.signal == "BP_sys"
    assert result.temporal.window.value == 6
    assert result.temporal.window.unit == "h"


def test_valid_max_8(parser):
    """Parse valid max expression"""
    result = parser.parse_trend("max(Temp, 24h)")
    assert result is not None
    assert result.temporal.operator == "max"
    assert result.temporal.signal == "Temp"
    assert result.temporal.window.value == 24
    assert result.temporal.window.unit == "h"


def test_valid_count_9(parser):
    """Parse valid count expression"""
    result = parser.parse_trend("count(Cr, 48h)")
    assert result is not None
    assert result.temporal.operator == "count"
    assert result.temporal.signal == "Cr"
    assert result.temporal.window.value == 48
    assert result.temporal.window.unit == "h"


def test_valid_first_10(parser):
    """Parse valid first expression"""
    result = parser.parse_trend("first(Cr, 24h)")
    assert result is not None
    assert result.temporal.operator == "first"
    assert result.temporal.signal == "Cr"
    assert result.temporal.window.value == 24
    assert result.temporal.window.unit == "h"


def test_valid_std_11(parser):
    """Parse valid std expression"""
    result = parser.parse_trend("std(HR, 1h)")
    assert result is not None
    assert result.temporal.operator == "std"
    assert result.temporal.signal == "HR"
    assert result.temporal.window.value == 1
    assert result.temporal.window.unit == "h"


def test_valid_stddev_12(parser):
    """Parse valid stddev expression"""
    result = parser.parse_trend("stddev(HR, 1h)")
    assert result is not None
    assert result.temporal.operator == "stddev"
    assert result.temporal.signal == "HR"
    assert result.temporal.window.value == 1
    assert result.temporal.window.unit == "h"


def test_valid_percentile_13(parser):
    """Parse valid percentile expression"""
    result = parser.parse_trend("percentile(HR, 1h, 95)")
    assert result is not None
    assert result.temporal.operator == "percentile"
    assert result.temporal.signal == "HR"
    assert result.temporal.window.value == 1
    assert result.temporal.window.unit == "h"


def test_valid_percentile_14(parser):
    """Parse valid percentile expression"""
    result = parser.parse_trend("percentile(BP_sys, 24h, 50)")
    assert result is not None
    assert result.temporal.operator == "percentile"
    assert result.temporal.signal == "BP_sys"
    assert result.temporal.window.value == 24
    assert result.temporal.window.unit == "h"


def test_valid_last_15(parser):
    """Parse valid last expression"""
    result = parser.parse_trend("last(HR)")
    assert result is not None
    assert result.temporal.operator == "last"
    assert result.temporal.signal == "HR"


def test_valid_last_16(parser):
    """Parse valid last expression"""
    result = parser.parse_trend("last(Cr)")
    assert result is not None
    assert result.temporal.operator == "last"
    assert result.temporal.signal == "Cr"


def test_valid_exists_17(parser):
    """Parse valid exists expression"""
    result = parser.parse_trend("exists(Cr)")
    assert result is not None
    assert result.temporal.operator == "exists"
    assert result.temporal.signal == "Cr"


def test_valid_missing_18(parser):
    """Parse valid missing expression"""
    result = parser.parse_trend("missing(Cr)")
    assert result is not None
    assert result.temporal.operator == "missing"
    assert result.temporal.signal == "Cr"


def test_valid_arithmetic_19(parser):
    """Division of two trends"""
    result = parser.parse_trend("last(Cr) / last(Cr_baseline)")
    assert result is not None
    assert isinstance(result, ArithExpr)


def test_valid_arithmetic_20(parser):
    """Addition of two trends"""
    result = parser.parse_trend("delta(Cr, 48h) + delta(Cr, 24h)")
    assert result is not None
    assert isinstance(result, ArithExpr)


def test_valid_arithmetic_21(parser):
    """Subtraction (HR range)"""
    result = parser.parse_trend("max(HR, 1h) - min(HR, 1h)")
    assert result is not None
    assert isinstance(result, ArithExpr)


def test_valid_arithmetic_22(parser):
    """Multiplication with literal"""
    result = parser.parse_trend("delta(Cr, 6h) * 2")
    assert result is not None
    assert isinstance(result, ArithExpr)


def test_valid_logic_23(parser):
    """Simple term reference"""
    result = parser.parse_logic("aki_stage1")
    assert result is not None
    assert isinstance(result, TermRef)
    assert set(extract_terms(result)) == {"aki_stage1"}


def test_valid_logic_24(parser):
    """AND expression"""
    result = parser.parse_logic("aki_stage1 AND aki_stage2")
    assert result is not None
    assert isinstance(result, AndExpr)
    assert set(extract_terms(result)) == {"aki_stage2", "aki_stage1"}


def test_valid_logic_25(parser):
    """OR expression"""
    result = parser.parse_logic("aki_stage1 OR aki_stage2")
    assert result is not None
    assert isinstance(result, OrExpr)
    assert set(extract_terms(result)) == {"aki_stage2", "aki_stage1"}


def test_valid_logic_26(parser):
    """NOT expression"""
    result = parser.parse_logic("NOT recovering")
    assert result is not None
    assert isinstance(result, NotExpr)
    assert set(extract_terms(result)) == {"recovering"}


def test_valid_logic_27(parser):
    """Combined AND and NOT"""
    result = parser.parse_logic("aki_stage1 AND NOT recovering")
    assert result is not None
    assert set(extract_terms(result)) == {"recovering", "aki_stage1"}


def test_valid_logic_28(parser):
    """Parenthesized expression"""
    result = parser.parse_logic("(fever OR hypothermia) AND tachycardia")
    assert result is not None
    assert set(extract_terms(result)) == {"fever", "tachycardia", "hypothermia"}


def test_valid_logic_29(parser):
    """Lowercase AND"""
    result = parser.parse_logic("a and b")
    assert result is not None
    assert isinstance(result, AndExpr)


def test_valid_logic_30(parser):
    """Lowercase OR"""
    result = parser.parse_logic("a or b")
    assert result is not None
    assert isinstance(result, OrExpr)


def test_valid_logic_31(parser):
    """Lowercase NOT"""
    result = parser.parse_logic("not a")
    assert result is not None
    assert isinstance(result, NotExpr)


def test_valid_logic_comparison_32(parser):
    """Comparison with term reference"""
    result = parser.parse_logic("cr_delta >= 0.3")
    assert result is not None
    assert isinstance(result, ComparisonExpr)
    assert result.operator == ">="


def test_valid_logic_comparison_33(parser):
    """Simple comparison with term"""
    result = parser.parse_logic("cr_ratio >= 1.5")
    assert result is not None
    assert isinstance(result, ComparisonExpr)
    assert result.operator == ">="


def test_valid_logic_comparison_34(parser):
    """Range check with two comparisons"""
    result = parser.parse_logic("cr_ratio >= 1.5 AND cr_ratio < 2.0")
    assert result is not None
    assert isinstance(result, AndExpr)


# ======================================================================
# INVALID PARSE TESTS
# ======================================================================


def test_invalid_delta_0(parser):
    """Reject invalid delta expression: Missing window argument"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("delta(Cr)")


def test_invalid_delta_1(parser):
    """Reject invalid delta expression: Missing signal and window"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("delta()")


def test_invalid_delta_2(parser):
    """Reject invalid delta expression: Missing parentheses"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("delta Cr, 6h")


def test_invalid_slope_3(parser):
    """Reject invalid slope expression: Missing window argument"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("slope(Lact)")


def test_invalid_percentile_4(parser):
    """Reject invalid percentile expression: Missing percentile argument"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("percentile(HR, 1h)")


def test_invalid_percentile_5(parser):
    """Reject invalid percentile expression: Missing window and percentile arguments"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("percentile(HR)")


def test_invalid_last_6(parser):
    """Reject invalid last expression: Pointwise operator does not take window"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("last(HR, 6h)")


def test_invalid_last_7(parser):
    """Reject invalid last expression: Missing signal argument"""
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("last()")


# ======================================================================
# V0.3 STRICT COMPARISON REJECTION TESTS
# ======================================================================
# v0.3 STRICT: Comparisons in trend expressions MUST cause parse errors
# Comparisons belong ONLY in the Logic layer (ComparisonExpr)


def test_comparison_in_trend_rejected_delta_0(parser):
    """Reject delta with comparison (v0.3): Comparison operator not allowed in trend (v0.3)"""
    # v0.3 STRICT: Comparisons in trend expressions MUST be rejected
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("delta(Cr, 6h) > 0")


def test_comparison_in_trend_rejected_delta_1(parser):
    """Reject delta with comparison (v0.3): Comparison operator not allowed in trend (v0.3)"""
    # v0.3 STRICT: Comparisons in trend expressions MUST be rejected
    with pytest.raises(PSDLExpressionError):
        parser.parse_trend("delta(Cr, 6h) >= 0.3")
