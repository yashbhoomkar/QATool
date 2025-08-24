from __future__ import annotations

from typing import List, Optional
import libcst as cst


def slice_source_lines(src: str, start_line: int, end_line: int) -> str:
    """Inclusive line slice, preserves original whitespace."""
    lines = src.splitlines(keepends=True)
    start_idx = max(0, start_line - 1)  # LibCST is 1-based
    end_idx = min(len(lines), end_line)
    return "".join(lines[start_idx:end_idx])


def full_attr_name(node: cst.BaseExpression) -> str:
    """Turn a Name or Attribute into a dotted string."""
    parts: List[str] = []
    cur = node
    while isinstance(cur, cst.Attribute):
        parts.append(cur.attr.value)    # rightmost
        cur = cur.value
    if isinstance(cur, cst.Name):
        parts.append(cur.value)
    return ".".join(reversed(parts)) if parts else ""


def first_docstring_from_body(body: cst.IndentedBlock) -> Optional[str]:
    """Return docstring from the first statement in a body if present."""
    if not body.body:
        return None
    first = body.body[0]
    if isinstance(first, cst.SimpleStatementLine) and first.body:
        expr = first.body[0]
        if isinstance(expr, cst.Expr) and isinstance(expr.value, cst.SimpleString):
            return getattr(expr.value, "evaluated_value", expr.value.raw_value)
    return None


def params_signature(params: cst.Parameters) -> str:
    """Readable signature like 'a, b=..., *args, **kwargs'."""
    def name_of(p: cst.Param) -> str:
        return p.name.value

    parts: List[str] = []

    # positional-only
    for p in params.posonly_params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))
    if params.posonly_params:
        parts.append("/")

    # positional-or-keyword
    for p in params.params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))

    # *args or bare *
    if isinstance(params.star_arg, cst.Param):
        parts.append("*" + name_of(params.star_arg))
    elif params.kwonly_params:
        parts.append("*")

    # keyword-only
    for p in params.kwonly_params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))

    # **kwargs
    if isinstance(params.star_kwarg, cst.Param):
        parts.append("**" + name_of(params.star_kwarg))

    return ", ".join(parts)
