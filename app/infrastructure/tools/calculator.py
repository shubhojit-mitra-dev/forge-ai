"""Safe AST-based arithmetic calculator tool."""

from __future__ import annotations

import ast
import operator
from typing import TYPE_CHECKING, Any

from app.domain.value_objects.enums import ToolName

if TYPE_CHECKING:
    from collections.abc import Callable

_BINARY_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MAX_EXPONENT = 1000


def _eval_node(node: ast.AST) -> int | float:
    """Recursively evaluate a whitelisted AST arithmetic node."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric literals are allowed.")
        return node.value

    if isinstance(node, ast.UnaryOp):
        unary_fn = _UNARY_OPS.get(type(node.op))
        if unary_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        operand = _eval_node(node.operand)
        return unary_fn(operand)

    if isinstance(node, ast.BinOp):
        binary_fn = _BINARY_OPS.get(type(node.op))
        if binary_fn is None:
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
            raise ValueError("Division or modulo by zero is not allowed.")
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"Exponent magnitude exceeds limit ({_MAX_EXPONENT}).")
        return binary_fn(left, right)

    raise ValueError(f"Disallowed expression construct: {type(node).__name__}")


def safe_eval_math(expression: str) -> int | float:
    """Safely evaluate a mathematical expression using Python's AST."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expression must be a non-empty string.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid mathematical expression: {exc.msg}") from exc
    return _eval_node(tree)


class CalculatorTool:
    """Deterministic safe math evaluator supporting +, -, *, /, **, %, and parentheses."""

    @property
    def name(self) -> ToolName:
        return ToolName.CALCULATOR

    @property
    def description(self) -> str:
        return (
            "Evaluate basic arithmetic expressions (+, -, *, /, **, %, parentheses) "
            "safely without executing arbitrary code."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression to evaluate, e.g. '(12 + 8) * 1.5'.",
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        """Evaluate the `expression` keyword argument and return the numeric result as text."""
        expression = kwargs.get("expression")
        if not isinstance(expression, str):
            raise ValueError("Argument 'expression' must be a string.")
        result = safe_eval_math(expression)
        return str(result)
