"""
Auto-generated Lark Transformer from spec/ast-nodes.yaml grammar_mappings
Generated: 2025-12-15T12:25:43.187958

DO NOT EDIT - Regenerate with: python tools/codegen.py --transformer
"""

from __future__ import annotations

from typing import Any, List, Union

from lark import Transformer, v_args

# Import AST types from generated code
# NOTE: Comparison class removed in v0.3 - comparisons only in Logic layer (ComparisonExpr)
from psdl._generated.ast_types import (
    AndExpr,
    ArithExpr,
    ComparisonExpr,
    NotExpr,
    NumberLiteral,
    OrExpr,
    TemporalCall,
    TermRef,
    TrendExpression,
    WindowSpec,
)


class PSDLExprTransformer(Transformer):
    """
    Transform Lark parse tree into PSDL AST objects.

    Auto-generated from spec/ast-nodes.yaml grammar_mappings.
    Version: 0.3.0
    """

    @v_args(inline=True)
    def window(self, *args) -> WindowSpec:
        """Transform 'window' grammar rule."""
        return WindowSpec(value=int(args[0]), unit=str(args[1]))

    @v_args(inline=True)
    def windowed_call(self, *args) -> TrendExpression:
        """Transform 'windowed_call' grammar rule."""
        temporal = TemporalCall(operator=str(args[0]), signal=str(args[1]), window=args[2])
        return TrendExpression(temporal=temporal)

    @v_args(inline=True)
    def pointwise_call(self, *args) -> TrendExpression:
        """Transform 'pointwise_call' grammar rule."""
        temporal = TemporalCall(operator=str(args[0]), signal=str(args[1]), window=None)
        return TrendExpression(temporal=temporal)

    @v_args(inline=True)
    def percentile_call(self, *args) -> TrendExpression:
        """Transform 'percentile_call' grammar rule."""
        temporal = TemporalCall(
            operator="percentile",
            signal=str(args[0]),
            window=args[1],
            percentile=int(args[2]),
        )
        return TrendExpression(temporal=temporal)

    @v_args(inline=True)
    def number(self, *args) -> float:
        """Transform 'number' grammar rule."""
        return float(args[0])

    @v_args(inline=True)
    def arith_op(self, *args) -> str:
        """Transform 'arith_op' grammar rule."""
        return str(args[0])

    @v_args(inline=True)
    def term_ref(self, *args) -> TermRef:
        """Transform 'term_ref' grammar rule."""
        return TermRef(name=str(args[0]))

    @v_args(inline=True)
    def trend_ref_in_comparison(self, *args) -> TermRef:
        """Transform 'trend_ref_in_comparison' grammar rule."""
        return TermRef(name=str(args[0]))

    def arith_expr(self, items: List[Any]) -> ArithExpr:
        """Transform 'arith_expr' grammar rule."""
        left = items[0]
        op = items[1]
        right = items[2]
        return ArithExpr(operator=op, left=left, right=right)

    def comparison_expr(self, items: List[Any]) -> ComparisonExpr:
        """Transform 'comparison_expr' grammar rule."""
        left = items[0]
        op = str(items[1])
        right = items[2]
        return ComparisonExpr(operator=op, left=left, right=right)

    def not_term(self, items: List[Any]) -> NotExpr:
        """Transform 'not_term' grammar rule."""
        operand = items[-1]  # Last item is the actual operand
        return NotExpr(operand=operand)

    def and_expr(self, items: List[Any]) -> Union[AndExpr, Any]:
        """
        Transform 'and_expr' grammar rule (variadic mode).
        Filters out tokens: AND
        Returns single item unwrapped if only one operand.
        """
        operands = [x for x in items if not hasattr(x, "type") or x.type != "AND"]
        if len(operands) == 1:
            return operands[0]
        return AndExpr(operands=operands)

    def or_expr(self, items: List[Any]) -> Union[OrExpr, Any]:
        """
        Transform 'or_expr' grammar rule (variadic mode).
        Filters out tokens: OR
        Returns single item unwrapped if only one operand.
        """
        operands = [x for x in items if not hasattr(x, "type") or x.type != "OR"]
        if len(operands) == 1:
            return operands[0]
        return OrExpr(operands=operands)

    def trend_with_optional_comparison(self, items: List[Any]) -> Union[TrendExpression, ArithExpr]:
        """Transform 'trend_with_optional_comparison' grammar rule (conditional mode)."""
        # v0.3: Trends produce numeric only, no comparison
        if len(items) == 1:
            item = items[0]
            if isinstance(item, TrendExpression):
                return item
            if isinstance(item, ArithExpr):
                return item
            if isinstance(item, TemporalCall):
                return TrendExpression(temporal=item)
            return item
        # v0.3: Multiple items means arithmetic, not comparison
        return items[0]

    def trend_expr(self, items: List[Any]) -> Union[TrendExpression]:
        """Transform 'trend_expr' grammar rule (conditional mode)."""
        # v0.3: Trends produce numeric only
        item = items[0]
        if isinstance(item, TrendExpression):
            return item
        if isinstance(item, TemporalCall):
            return TrendExpression(temporal=item)
        return item
