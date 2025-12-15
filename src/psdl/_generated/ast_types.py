"""
Auto-generated AST types from spec/ast-nodes.yaml
Generated: 2025-12-15T12:25:43.173116

DO NOT EDIT - Regenerate with: python tools/codegen.py --ast
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Union

# =============================================================================
# SPEC VERSION
# =============================================================================

AST_SPEC_VERSION = "0.3.0"


# =============================================================================
# ENUMS (Primitive Types)
# =============================================================================


class WindowUnit(str, Enum):
    """Time window unit (seconds, minutes, hours, days, weeks)"""

    S = "s"
    M = "m"
    H = "h"
    D = "d"
    W = "w"


class ComparisonOp(str, Enum):
    """Comparison operators"""

    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    EQ = "=="
    NE = "!="


class BooleanOp(str, Enum):
    """Boolean logic operators"""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class ArithmeticOp(str, Enum):
    """Arithmetic operators"""

    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"


# =============================================================================
# TYPE ALIASES (Forward References)
# =============================================================================

# These are string forward references for recursive types
# Actual type checking is handled by TYPE_CHECKING block below

# Union type for numeric AST nodes (v0.3: trends produce numeric only)
# Union type for logic AST nodes (v0.3: NO TrendExpression)
# Union type for any expression node

# =============================================================================
# AST NODE DATACLASSES
# =============================================================================


@dataclass
class WindowSpec:
    """
    Time window specification (e.g., 6h, 30m, 1d)
    """

    value: int  # Numeric value of the window
    unit: str  # Time unit (s, m, h, d, w)

    @property
    def seconds(self) -> int:
        """Window duration in seconds"""
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        return self.value * multipliers.get(self.unit, 1)

    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


@dataclass
class TemporalCall:
    """
    A parsed temporal operator call (windowed or pointwise)
    """

    operator: str  # Operator name (delta, slope, ema, sma, min, max, count, last, first, exists, missing, std, stddev, percentile)
    signal: str  # Signal name being operated on
    window: Optional[WindowSpec] = (
        None  # Time window (required for windowed operators, null for pointwise)
    )
    percentile: Optional[int] = None  # Percentile value (0-100) for percentile operator


@dataclass
class NumberLiteral:
    """
    A numeric literal value
    """

    value: float  # The numeric value


@dataclass
class ArithExpr:
    """
    Arithmetic expression combining numeric values
    """

    operator: str  # Arithmetic operator (+, -, *, /)
    left: Union["TemporalCall", "ArithExpr", "NumberLiteral", float]  # Left operand
    right: Union["TemporalCall", "ArithExpr", "NumberLiteral", float]  # Right operand


@dataclass
class TrendExpression:
    """
    A numeric trend expression (v0.3: NO comparison field)
    """

    temporal: TemporalCall  # The temporal operator call producing a numeric value

    @property
    def operator(self) -> str:
        """Shortcut to temporal.operator"""
        return self.temporal.operator

    @property
    def signal(self) -> str:
        """Shortcut to temporal.signal"""
        return self.temporal.signal

    @property
    def window(self) -> WindowSpec:
        """Shortcut to temporal.window"""
        return self.temporal.window


@dataclass
class TermRef:
    """
    Reference to a named term (trend or logic rule)
    """

    name: str  # Name of the referenced term


@dataclass
class ComparisonExpr:
    """
    Comparison expression in logic layer (v0.3)
    """

    operator: str  # Comparison operator (<, <=, >, >=, ==, !=)
    left: Union[
        "TemporalCall", "ArithExpr", "NumberLiteral", float, "TermRef"
    ]  # Left operand (trend ref, temporal call, or literal)
    right: Union[
        "TemporalCall", "ArithExpr", "NumberLiteral", float, "TermRef"
    ]  # Right operand (usually a numeric literal)


@dataclass
class NotExpr:
    """
    Logical NOT expression
    """

    operand: "LogicNode"  # Expression to negate


@dataclass
class AndExpr:
    """
    Logical AND expression
    """

    operands: List["LogicNode"]  # List of expressions to AND together


@dataclass
class OrExpr:
    """
    Logical OR expression
    """

    operands: List["LogicNode"]  # List of expressions to OR together


# =============================================================================
# TYPE ALIASES (Union Types)
# =============================================================================

# Union type for numeric AST nodes (v0.3: trends produce numeric only)
NumericNode = Union[TemporalCall, ArithExpr, NumberLiteral, float]

# Union type for logic AST nodes (v0.3: NO TrendExpression)
LogicNode = Union[TermRef, ComparisonExpr, NotExpr, AndExpr, OrExpr]

# Union type for any expression node
ExpressionNode = Union[NumericNode, LogicNode]
