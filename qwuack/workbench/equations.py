"""Equation engine — objects with IDs and operations, not loose text.

This is not a CAS that pretends to close Millennium Problems.
It is a provenance graph: every rewrite is an object that remembers why it exists.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from qwuack.workbench.objects import ClaimStatus, MathObject, ObjectKind
from qwuack.workbench.store import ObjectStore


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def _eval_arith(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_arith(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_arith(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval_arith(node.left), _eval_arith(node.right))
    raise ValueError("not a closed arithmetic expression")


def try_simplify(expr: str) -> tuple[str, bool]:
    """Fold a closed arithmetic expression. Leave symbols alone."""
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval_arith(tree)
        if value.is_integer():
            return str(int(value)), True
        return repr(value), True
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return expr, False


def substitute(expr: str, mapping: dict[str, str]) -> str:
    out = expr
    for src, dst in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(src)}(?![A-Za-z0-9_])", f"({dst})", out)
    return out


class EquationEngine:
    def __init__(self, store: ObjectStore) -> None:
        self.store = store

    def create(
        self,
        expr: str,
        problem: str = "",
        derived_from: list[str] | None = None,
        worker: str = "symbolic",
        session: str = "",
    ) -> MathObject:
        return self.store.mint(
            ObjectKind.EQUATION,
            expr,
            problem=problem,
            status=ClaimStatus.OBSERVATION,
            derived_from=list(derived_from or []),
            worker=worker,
            session=session,
            operations=["create"],
        )

    def apply(
        self,
        eq: MathObject,
        op: str,
        *,
        mapping: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> MathObject:
        expr = eq.statement
        notes = list(eq.notes)
        folded = False
        if op == "substitute" and mapping:
            expr = substitute(expr, mapping)
        elif op == "simplify":
            expr, folded = try_simplify(expr)
        elif op in {"differentiate", "integrate", "factor", "expand", "limit", "prove", "disprove"}:
            notes.append(f"{op}_recorded_not_executed")
        else:
            notes.append(f"unknown_op:{op}")
        child = self.store.mint(
            ObjectKind.EQUATION,
            expr,
            problem=eq.problem,
            status=ClaimStatus.OBSERVATION if not folded else ClaimStatus.VERIFIED_DERIVATION,
            derived_from=[eq.id],
            operations=[op],
            worker=eq.worker or "symbolic",
            session=eq.session,
            notes=notes,
            evidence={"parent": eq.id, "op": op, **(mapping or {}), **(extra or {})},
            verification={"symbolic": "PASS" if folded or op == "substitute" else "NOT_RUN"},
        )
        return child
