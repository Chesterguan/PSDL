"""
PSDL Expression Parser - Lark-based parser for trend and logic expressions.

This module provides spec-driven parsing of PSDL expressions using the
formal grammar defined in spec/grammar/expression.lark.

v0.3 Changes:
- Grammar loaded from spec/grammar/expression.lark (not embedded)
- Trend expressions produce NUMERIC values only (no comparisons)
- Comparisons only allowed in logic layer
- AST types generated from spec/ast-nodes.yaml
- Transformer auto-generated from spec/ast-nodes.yaml grammar_mappings

Key Advantages over regex-based parsing:
- Proper precedence handling for boolean logic (NOT > AND > OR)
- Better error messages with line/column info
- Extensible grammar derived from formal specification
- Handles nested parentheses correctly
"""

from pathlib import Path
from typing import List

from lark import Lark
from lark.exceptions import LarkError

# Import AST types from generated code (re-exported for public API)
# NOTE: Comparison class removed in v0.3 - comparisons only in Logic layer (ComparisonExpr)
from psdl._generated.ast_types import (
    AndExpr,
    ArithExpr,
    ComparisonExpr,
    LogicNode,
    NotExpr,
    NumberLiteral,
    OrExpr,
    TemporalCall,
    TermRef,
    TrendExpression,
    WindowSpec,
)

# Import auto-generated transformer from spec
from psdl._generated.transformer import PSDLExprTransformer

# Re-export AST types for public API
# NOTE: Comparison class removed in v0.3 - use ComparisonExpr in Logic layer
__all__ = [
    "PSDLExpressionParser",
    "PSDLExpressionError",
    "parse_trend_expression",
    "parse_logic_expression",
    "extract_terms",
    "extract_operators",
    # AST types (v0.3: NO Comparison - use ComparisonExpr)
    "AndExpr",
    "ArithExpr",
    "ComparisonExpr",
    "LogicNode",
    "NotExpr",
    "NumberLiteral",
    "OrExpr",
    "TemporalCall",
    "TermRef",
    "TrendExpression",
    "WindowSpec",
]


def _load_grammar() -> str:
    """Load grammar from spec/grammar/expression.lark."""
    # Try multiple paths to find the grammar file
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "spec" / "grammar" / "expression.lark",
        Path(__file__).parent.parent.parent / "spec" / "grammar" / "expression.lark",
        Path("spec/grammar/expression.lark"),
    ]

    for path in possible_paths:
        if path.exists():
            return path.read_text()

    # Fallback: embedded v0.3 grammar for standalone use
    return _FALLBACK_GRAMMAR


# Fallback grammar (v0.3 STRICT) for when spec file is not available
_FALLBACK_GRAMMAR = r"""
// PSDL Expression Grammar v0.3 STRICT (fallback)
// See spec/grammar/expression.lark for authoritative version
// v0.3: Trends produce numeric ONLY. Comparisons ONLY in Logic layer.

// Terminals (define first for lexer)
WINDOWED_OP: "delta" | "slope" | "ema" | "sma" | "min" | "max" | "count" | "first" | "std" | "stddev"
POINTWISE_OP: "last" | "exists" | "missing"
ARITH_OP: "+" | "-" | "*" | "/"
COMP_OP: "==" | "!=" | "<=" | ">=" | "<" | ">"
WINDOW_UNIT: "s" | "m" | "h" | "d" | "w"
// Keywords have higher priority (2) than IDENTIFIER (default 1)
AND.2: /AND/i
OR.2: /OR/i
NOT.2: /NOT/i
IDENTIFIER: /[A-Za-z][A-Za-z0-9_]*/
INTEGER: /[0-9]+/

// v0.3 STRICT: trend_expr is numeric ONLY - NO comparisons
?trend_expr: numeric_expr -> trend_with_optional_comparison

// NOTE: trend_comparison REMOVED in v0.3 - comparisons ONLY in logic layer

?logic_expr: or_expr

?numeric_expr: temporal_expr
             | numeric_expr arith_op numeric_expr -> arith_expr
             | "(" numeric_expr ")"
             | number

?temporal_expr: windowed_call
              | percentile_call
              | pointwise_call

windowed_call: WINDOWED_OP "(" IDENTIFIER "," window ")"

percentile_call: "percentile" "(" IDENTIFIER "," window "," number ")"

pointwise_call: POINTWISE_OP "(" IDENTIFIER ")"

arith_op: ARITH_OP

window: INTEGER WINDOW_UNIT

number: SIGNED_NUMBER

?or_expr: and_expr (OR and_expr)*

?and_expr: not_expr (AND not_expr)*

?not_expr: NOT not_expr -> not_term
         | primary_expr

?primary_expr: "(" logic_expr ")"
             | comparison_expr
             | IDENTIFIER -> term_ref

comparison_expr: numeric_value COMP_OP numeric_value

?numeric_value: numeric_expr
              | IDENTIFIER -> trend_ref_in_comparison

%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
"""

# Load grammar once at module import
PSDL_GRAMMAR = _load_grammar()


class PSDLExpressionParser:
    """
    Parser for PSDL trend and logic expressions.

    Uses the Lark grammar from spec/formal/psdl-expression.lark
    to provide spec-driven parsing with proper operator precedence.

    Usage:
        parser = PSDLExpressionParser()
        trend = parser.parse_trend("delta(Cr, 6h) > 0.3")
        logic = parser.parse_logic("aki_stage1 AND NOT recovering")
    """

    def __init__(self):
        # Create parsers with different start rules
        self._trend_parser = Lark(
            PSDL_GRAMMAR,
            start="trend_expr",
            parser="lalr",
            transformer=PSDLExprTransformer(),
        )
        self._logic_parser = Lark(
            PSDL_GRAMMAR,
            start="logic_expr",
            parser="lalr",
            transformer=PSDLExprTransformer(),
        )

    def parse_trend(self, expr: str) -> TrendExpression:
        """
        Parse a trend expression.

        Args:
            expr: Expression string like "delta(Cr, 6h) > 0.3" or "last(HR)"

        Returns:
            TrendExpression AST node

        Raises:
            PSDLExpressionError: If parsing fails
        """
        try:
            result = self._trend_parser.parse(expr)
            return result
        except LarkError as e:
            raise PSDLExpressionError(f"Invalid trend expression '{expr}': {e}") from e

    def parse_logic(self, expr: str) -> LogicNode:
        """
        Parse a logic expression.

        Args:
            expr: Expression string like "aki_stage1 AND NOT recovering"

        Returns:
            LogicNode AST node (OrExpr, AndExpr, NotExpr, TermRef, or TrendExpression)

        Raises:
            PSDLExpressionError: If parsing fails
        """
        try:
            result = self._logic_parser.parse(expr)
            return result
        except LarkError as e:
            raise PSDLExpressionError(f"Invalid logic expression '{expr}': {e}") from e


class PSDLExpressionError(Exception):
    """Exception raised for expression parsing errors."""

    pass


def extract_terms(node: LogicNode) -> List[str]:
    """
    Extract all term references from a logic expression AST.

    Args:
        node: Root of the logic AST

    Returns:
        List of term names referenced in the expression
    """
    terms = []

    def visit(n):
        if isinstance(n, TermRef):
            terms.append(n.name)
        elif isinstance(n, TrendExpression):
            # Trend expressions reference signals, not terms
            pass
        elif isinstance(n, ComparisonExpr):
            # v0.3: Extract terms from comparison operands
            visit(n.left)
            visit(n.right)
        elif isinstance(n, NotExpr):
            visit(n.operand)
        elif isinstance(n, AndExpr):
            for op in n.operands:
                visit(op)
        elif isinstance(n, OrExpr):
            for op in n.operands:
                visit(op)
        # Skip float/int literals - they're not terms

    visit(node)
    return terms


def extract_operators(node: LogicNode) -> List[str]:
    """
    Extract all boolean and comparison operators from a logic expression AST.

    Returns operators in depth-first, left-to-right order to match
    how they appear in the expression.

    Args:
        node: Root of the logic AST

    Returns:
        List of operators used (AND, OR, NOT, plus comparison operators)
    """
    operators = []

    def visit(n):
        if isinstance(n, NotExpr):
            operators.append("NOT")
            visit(n.operand)
        elif isinstance(n, AndExpr):
            # Visit children first, then add AND operators between them
            for i, op in enumerate(n.operands):
                visit(op)
                if i < len(n.operands) - 1:
                    operators.append("AND")
        elif isinstance(n, OrExpr):
            # Visit children first, then add OR operators between them
            for i, op in enumerate(n.operands):
                visit(op)
                if i < len(n.operands) - 1:
                    operators.append("OR")
        elif isinstance(n, ComparisonExpr):
            # v0.3: Include comparison operators
            operators.append(n.operator)

    visit(node)
    return operators


# Module-level parser instance for convenience
_parser = None


def get_parser() -> PSDLExpressionParser:
    """Get the singleton parser instance."""
    global _parser
    if _parser is None:
        _parser = PSDLExpressionParser()
    return _parser


def parse_trend_expression(expr: str) -> TrendExpression:
    """Convenience function to parse a trend expression."""
    return get_parser().parse_trend(expr)


def parse_logic_expression(expr: str) -> LogicNode:
    """Convenience function to parse a logic expression."""
    return get_parser().parse_logic(expr)
