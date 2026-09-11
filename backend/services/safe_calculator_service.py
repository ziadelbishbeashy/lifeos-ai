"""Deterministic calculator used by Ask LifeOS.

The LLM may suggest a mathematical expression, but this module is the only
component allowed to evaluate it.  It uses a tiny AST allow-list rather than
``eval``/``exec`` so calculations cannot become code execution.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Callable


MAX_CALCULATOR_EXPRESSION_CHARACTERS = 500
MAX_CALCULATOR_AST_NODES = 80
MAX_ABS_RESULT = 1e100
MAX_POWER_EXPONENT = 12


class SafeCalculatorError(ValueError):
    """Raised when a calculator expression is invalid or unsafe."""


@dataclass(frozen=True)
class CalculationResult:
    expression: str
    result: float | int
    formatted_result: str

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "result": self.result,
            "formatted_result": self.formatted_result,
            "deterministic": True,
            "code_execution": False,
        }


_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_ALLOWED_FUNCTIONS: dict[str, Callable[..., float | int]] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "degrees": math.degrees,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}


def _clean_expression(value: str) -> str:
    expression = " ".join(str(value or "").strip().split())
    if not expression:
        raise SafeCalculatorError("A calculator expression is required.")
    if len(expression) > MAX_CALCULATOR_EXPRESSION_CHARACTERS:
        raise SafeCalculatorError("The calculator expression is too long.")
    # Friendly normalization for expressions produced by a model/user.
    return (
        expression
        .replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("^", "**")
    )


def _ensure_number(value: object) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeCalculatorError("The calculator only supports numeric results.")
    if not math.isfinite(float(value)):
        raise SafeCalculatorError("The calculation produced a non-finite result.")
    if abs(float(value)) > MAX_ABS_RESULT:
        raise SafeCalculatorError("The calculation result is outside the supported range.")
    return value


def _evaluate(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise SafeCalculatorError("Only numeric constants are allowed.")
        return _ensure_number(node.value)

    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_CONSTANTS:
            raise SafeCalculatorError(f'Unknown calculator name "{node.id}".')
        return _ALLOWED_CONSTANTS[node.id]

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate(node.operand)
        return _ensure_number(+operand if isinstance(node.op, ast.UAdd) else -operand)

    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        try:
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.FloorDiv):
                value = left // right
            elif isinstance(node.op, ast.Mod):
                value = left % right
            elif isinstance(node.op, ast.Pow):
                if abs(float(right)) > MAX_POWER_EXPONENT:
                    raise SafeCalculatorError("The exponent is outside the supported range.")
                value = left ** right
            else:
                raise SafeCalculatorError("That calculator operator is not allowed.")
        except (ArithmeticError, OverflowError, ValueError) as error:
            raise SafeCalculatorError("The calculation could not be completed safely.") from error
        return _ensure_number(value)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise SafeCalculatorError("That calculator function is not allowed.")
        if node.keywords:
            raise SafeCalculatorError("Calculator keyword arguments are not allowed.")
        if len(node.args) > 8:
            raise SafeCalculatorError("Too many calculator function arguments.")
        args = [_evaluate(item) for item in node.args]
        try:
            value = _ALLOWED_FUNCTIONS[node.func.id](*args)
        except (ArithmeticError, OverflowError, TypeError, ValueError) as error:
            raise SafeCalculatorError("The calculator function could not be evaluated.") from error
        return _ensure_number(value)

    # Explicitly reject attribute access, indexing, comprehensions, lambdas,
    # strings, containers, comparisons, booleans, assignments, etc.
    raise SafeCalculatorError("The calculator expression contains unsupported syntax.")


def _format_result(value: float | int) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    rounded = float(value)
    if rounded.is_integer() and abs(rounded) < 1e15:
        return f"{int(rounded):,}"
    if abs(rounded) >= 1e9 or (0 < abs(rounded) < 1e-6):
        return f"{rounded:.10g}"
    return f"{rounded:.10f}".rstrip("0").rstrip(".")


def calculate_expression(expression: str) -> CalculationResult:
    cleaned = _clean_expression(expression)
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as error:
        raise SafeCalculatorError("The calculator expression is not valid.") from error

    if sum(1 for _ in ast.walk(tree)) > MAX_CALCULATOR_AST_NODES:
        raise SafeCalculatorError("The calculator expression is too complex.")

    result = _ensure_number(_evaluate(tree))
    return CalculationResult(
        expression=cleaned,
        result=result,
        formatted_result=_format_result(result),
    )
