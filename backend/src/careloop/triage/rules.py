"""Safe evaluation of pack red-flag expressions such as `swelling and fever` or `pain_score >= 8`.

Only boolean logic, comparisons, `in`, names and literals are allowed. A name with no answer
yet evaluates to None, and any comparison involving None is False, so a rule never fires on
missing data.
"""

import ast
import operator
from functools import cache
from typing import Any

_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class RuleError(ValueError):
    pass


@cache
def compile_rule(expr: str) -> ast.Expression:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Compare,
                ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple, *_CMP,
            ),
        ):
            raise RuleError(f"Disallowed syntax {type(node).__name__} in rule {expr!r}")
    return tree


def _eval(node: ast.AST, answers: dict[str, Any]) -> Any:
    match node:
        case ast.Expression(body=body):
            return _eval(body, answers)
        case ast.BoolOp(op=ast.And(), values=values):
            return all(bool(_eval(v, answers)) for v in values)
        case ast.BoolOp(op=ast.Or(), values=values):
            return any(bool(_eval(v, answers)) for v in values)
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            value = _eval(operand, answers)
            return False if value is None else not value
        case ast.Compare(left=left, ops=ops, comparators=comps):
            lhs = _eval(left, answers)
            for op, comp in zip(ops, comps):
                rhs = _eval(comp, answers)
                if lhs is None or rhs is None:
                    return False
                try:
                    if not _CMP[type(op)](lhs, rhs):
                        return False
                except TypeError:
                    return False
                lhs = rhs
            return True
        case ast.Name(id=name):
            return answers.get(name)
        case ast.Constant(value=value):
            return value
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            return [_eval(e, answers) for e in elts]
    raise RuleError(f"Unsupported node {type(node).__name__}")


def evaluate(expr: str, answers: dict[str, Any]) -> bool:
    return bool(_eval(compile_rule(expr), answers))
