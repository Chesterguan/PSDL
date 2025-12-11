"""
PSDL Expression Parser - Lark-based parser for trend and logic expressions.

This module provides spec-driven parsing of PSDL expressions using the
formal grammar defined in spec/formal/psdl-expression.lark.

Key Advantages over regex-based parsing:
- Proper precedence handling for boolean logic (NOT > AND > OR)
- Better error messages with line/column info
- Extensible grammar derived from formal specification
- Handles nested parentheses correctly
"""

from dataclasses import dataclass
from typing import List, Optional, Union

from lark import Lark, Transformer, v_args
from lark.exceptions import LarkError

# Grammar embedded from spec/formal/psdl-expression.lark
# This ensures the parser is always in sync with the grammar definition
PSDL_GRAMMAR = r"""
// PSDL Expression Grammar for Lark Parser Generator
// Patient Scenario Definition Language v0.2
//
// Entry points:
//   - trend_expr: For parsing trend expressions (e.g., "delta(Cr, 6h) > 0.3")
//   - logic_expr: For parsing logic expressions (e.g., "aki_stage1 AND NOT recovering")

// ============================================================
// TOP-LEVEL EXPRESSIONS
// ============================================================

// Entry point for trend expressions (e.g., "delta(Cr, 6h) > 0.3")
?trend_expr: temporal_expr comparison?

// Entry point for logic expressions (e.g., "aki_stage1 AND NOT recovering")
?logic_expr: or_expr

// ============================================================
// TEMPORAL EXPRESSIONS
// ============================================================

?temporal_expr: windowed_call
              | pointwise_call

// Operators requiring a time window
windowed_call: WINDOWED_OP "(" IDENTIFIER "," window ")"

WINDOWED_OP: "delta" | "slope" | "ema" | "sma" | "min" | "max" | "count" | "first" | "stddev"

// Operators on current/recent values
pointwise_call: POINTWISE_OP "(" IDENTIFIER ")"

POINTWISE_OP: "last" | "exists" | "missing"

// ============================================================
// TIME WINDOWS
// ============================================================

window: INTEGER WINDOW_UNIT

WINDOW_UNIT: "s" | "m" | "h" | "d" | "w"

// ============================================================
// COMPARISONS
// ============================================================

comparison: COMP_OP number

COMP_OP: "==" | "!=" | "<=" | ">=" | "<" | ">"

// ============================================================
// BOOLEAN LOGIC EXPRESSIONS
// ============================================================

// Precedence: OR (lowest) -> AND -> NOT (highest)
?or_expr: and_expr (OR and_expr)*

?and_expr: not_expr (AND not_expr)*

?not_expr: NOT not_expr -> not_term
         | primary_expr

?primary_expr: "(" logic_expr ")"
             | trend_expr
             | IDENTIFIER -> term_ref

// ============================================================
// LITERALS AND IDENTIFIERS
// ============================================================

number: SIGNED_NUMBER

// Keywords must be defined BEFORE IDENTIFIER to take precedence
AND: /AND/i
OR: /OR/i
NOT: /NOT/i

IDENTIFIER: /(?!(?:AND|OR|NOT)\b)[A-Za-z][A-Za-z0-9_]*/i

INTEGER: /[0-9]+/

// ============================================================
// WHITESPACE AND COMMENTS
// ============================================================

%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
"""


@dataclass
class WindowSpec:
    """Time window specification."""

    value: int
    unit: str  # s, m, h, d, w

    @property
    def seconds(self) -> int:
        """Convert window to seconds."""
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return self.value * multipliers.get(self.unit, 1)

    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


@dataclass
class TemporalCall:
    """A parsed temporal operator call."""

    operator: str  # delta, slope, ema, sma, min, max, count, last, first, exists, missing
    signal: str
    window: Optional[WindowSpec] = None


@dataclass
class Comparison:
    """A comparison operation."""

    operator: str  # <, <=, >, >=, ==, !=
    threshold: float


@dataclass
class TrendExpression:
    """A complete trend expression (temporal call + optional comparison)."""

    temporal: TemporalCall
    comparison: Optional[Comparison] = None

    @property
    def operator(self) -> str:
        return self.temporal.operator

    @property
    def signal(self) -> str:
        return self.temporal.signal

    @property
    def window(self) -> Optional[WindowSpec]:
        return self.temporal.window

    @property
    def comparator(self) -> Optional[str]:
        return self.comparison.operator if self.comparison else None

    @property
    def threshold(self) -> Optional[float]:
        return self.comparison.threshold if self.comparison else None


@dataclass
class TermRef:
    """Reference to a named term (trend or logic)."""

    name: str


@dataclass
class NotExpr:
    """Logical NOT expression."""

    operand: "LogicNode"


@dataclass
class AndExpr:
    """Logical AND expression."""

    operands: List["LogicNode"]


@dataclass
class OrExpr:
    """Logical OR expression."""

    operands: List["LogicNode"]


# Union type for logic AST nodes
LogicNode = Union[TrendExpression, TermRef, NotExpr, AndExpr, OrExpr]


class PSDLExprTransformer(Transformer):
    """Transform Lark parse tree into PSDL AST objects."""

    @v_args(inline=True)
    def window(self, value, unit):
        return WindowSpec(value=int(value), unit=str(unit))

    @v_args(inline=True)
    def windowed_call(self, op, identifier, window):
        temporal = TemporalCall(operator=str(op), signal=str(identifier), window=window)
        return TrendExpression(temporal=temporal, comparison=None)

    @v_args(inline=True)
    def pointwise_call(self, op, identifier):
        temporal = TemporalCall(operator=str(op), signal=str(identifier), window=None)
        return TrendExpression(temporal=temporal, comparison=None)

    @v_args(inline=True)
    def comparison(self, op, number):
        return Comparison(operator=str(op), threshold=number)

    @v_args(inline=True)
    def number(self, value):
        return float(value)

    def trend_expr(self, items):
        # Handle case where temporal_expr already returns TrendExpression
        if len(items) == 1:
            item = items[0]
            # Already a TrendExpression from windowed_call/pointwise_call
            if isinstance(item, TrendExpression):
                return item
            # Wrap TemporalCall in TrendExpression if needed (shouldn't happen now)
            if isinstance(item, TemporalCall):
                return TrendExpression(temporal=item, comparison=None)
            return item
        else:
            # First item is TrendExpression, second is Comparison
            trend_expr = items[0]
            comparison = items[1]
            if isinstance(trend_expr, TrendExpression):
                # Update the comparison
                return TrendExpression(temporal=trend_expr.temporal, comparison=comparison)
            return TrendExpression(temporal=trend_expr, comparison=comparison)

    @v_args(inline=True)
    def term_ref(self, identifier):
        return TermRef(name=str(identifier))

    def not_term(self, items):
        # Grammar: NOT not_expr -> not_term
        # items contains [NOT token, operand]
        operand = items[-1]  # Last item is the actual operand
        return NotExpr(operand=operand)

    def and_expr(self, items):
        # Filter out AND tokens
        operands = [x for x in items if not hasattr(x, "type") or x.type != "AND"]
        if len(operands) == 1:
            return operands[0]
        return AndExpr(operands=operands)

    def or_expr(self, items):
        # Filter out OR tokens
        operands = [x for x in items if not hasattr(x, "type") or x.type != "OR"]
        if len(operands) == 1:
            return operands[0]
        return OrExpr(operands=operands)


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
            PSDL_GRAMMAR, start="trend_expr", parser="lalr", transformer=PSDLExprTransformer()
        )
        self._logic_parser = Lark(
            PSDL_GRAMMAR, start="logic_expr", parser="lalr", transformer=PSDLExprTransformer()
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
        elif isinstance(n, NotExpr):
            visit(n.operand)
        elif isinstance(n, AndExpr):
            for op in n.operands:
                visit(op)
        elif isinstance(n, OrExpr):
            for op in n.operands:
                visit(op)

    visit(node)
    return terms


def extract_operators(node: LogicNode) -> List[str]:
    """
    Extract all boolean operators from a logic expression AST.

    Returns operators in depth-first, left-to-right order to match
    how they appear in the expression.

    Args:
        node: Root of the logic AST

    Returns:
        List of operators used (AND, OR, NOT)
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
