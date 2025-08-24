# QATool/qa_visualizer/server/services/parser.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

import libcst as cst
from libcst import MetadataWrapper
from libcst.metadata import PositionProvider

# ---------- Data shapes ----------

@dataclass
class ClassInfo:
    name: str
    qname: str                # e.g., "pkg.module:ClassName"
    start: int
    end: int
    source: str               # exact slice (preserve whitespace)

@dataclass
class ClassAttr:
    name: str
    qname: str                # e.g., "pkg.mod:Class.attr"
    class_qname: str          # e.g., "pkg.mod:Class"
    annotation: Optional[str]
    value_preview: Optional[str]
    start: int
    end: int
    source: str               # exact slice

@dataclass
class FunctionInfo:
    name: str
    qname: str                # e.g., "pkg.module:func" or "pkg.module:Class.method"
    is_method: bool
    signature: str            # textual signature (best-effort)
    docstring: Optional[str]
    start: int
    end: int
    source: str               # exact slice

@dataclass
class ImportInfo:
    kind: str                 # "import" | "from"
    module: str               # "os", "pathlib", ".utils", "pkg.sub"
    name: Optional[str]       # for "from X import name as alias"; None for bare "import X"
    alias: Optional[str]
    is_relative: bool
    level: int                # 0 for absolute; 1..N for relative (dots)

@dataclass
class GlobalVar:
    name: str
    annotation: Optional[str]     # textual annotation if any (e.g., "dict[str, int]")
    value_preview: Optional[str]  # first ~80 chars of assigned value (not executed)

@dataclass
class FileEntities:
    path: str
    module: str                    # dotted module path if known; else ""
    classes: List[ClassInfo]
    functions: List[FunctionInfo]
    imports: List[ImportInfo]
    globals: List[GlobalVar]
    class_attrs: List[ClassAttr]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "module": self.module,
            "classes": [asdict(x) for x in self.classes],
            "functions": [asdict(x) for x in self.functions],
            "imports": [asdict(x) for x in self.imports],
            "globals": [asdict(x) for x in self.globals],
            "class_attrs": [asdict(x) for x in self.class_attrs],
        }

# ---------- Helpers ----------

def _slice_source_lines(src: str, start_line: int, end_line: int) -> str:
    """Inclusive line slice, preserves original whitespace."""
    lines = src.splitlines(keepends=True)
    # LibCST line numbers are 1-based
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    return "".join(lines[start_idx:end_idx])

def _full_attr_name(node: cst.BaseExpression) -> str:
    """Turn a Name or Attribute into a dotted string."""
    parts: List[str] = []
    cur: Optional[cst.CSTNode] = node
    while isinstance(cur, cst.Attribute):
        parts.append(cur.attr.value)          # rightmost
        cur = cur.value
    if isinstance(cur, cst.Name):
        parts.append(cur.value)
    return ".".join(reversed(parts)) if parts else ""

def _first_docstring_from_body(body: cst.IndentedBlock) -> Optional[str]:
    # A docstring is the very first statement: SimpleStatementLine(Expr(SimpleString))
    if not body.body:
        return None
    first = body.body[0]
    if isinstance(first, cst.SimpleStatementLine) and first.body:
        expr = first.body[0]
        if isinstance(expr, cst.Expr) and isinstance(expr.value, cst.SimpleString):
            return getattr(expr.value, "evaluated_value", expr.value.raw_value)
    return None

def _params_signature(params: cst.Parameters) -> str:
    """Return readable signature like 'a, b=..., *args, **kwargs'."""
    def name_of(p: cst.Param) -> str:
        return p.name.value

    parts: List[str] = []

    # Positional-only
    for p in params.posonly_params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))
    if params.posonly_params:
        parts.append("/")

    # Positional-or-keyword
    for p in params.params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))

    # *args or bare *
    if isinstance(params.star_arg, cst.Param):
        parts.append("*" + name_of(params.star_arg))
    elif params.kwonly_params:
        parts.append("*")

    # Keyword-only
    for p in params.kwonly_params:
        parts.append(name_of(p) + ("=..." if p.default is not None else ""))

    # **kwargs
    if isinstance(params.star_kwarg, cst.Param):
        parts.append("**" + name_of(params.star_kwarg))

    return ", ".join(parts)

# ---------- CST Visitor ----------

class _EntitiesCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, module_name: str, source_text: str):
        self.module_name = module_name
        self.src = source_text
        self.class_stack: List[str] = []
        self.in_function: int = 0  # depth counter
        self.classes: List[ClassInfo] = []
        self.functions: List[FunctionInfo] = []
        self.imports: List[ImportInfo] = []
        self.globals: List[GlobalVar] = []
        self.class_attrs: List[ClassAttr] = []

    # ---- Classes ----
    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        q = ".".join(self.class_stack + [node.name.value])
        qname = f"{self.module_name}:{q}" if self.module_name else q
        src = _slice_source_lines(self.src, pos.start.line, pos.end.line)
        self.classes.append(
            ClassInfo(
                name=node.name.value,
                qname=qname,
                start=pos.start.line,
                end=pos.end.line,
                source=src,
            )
        )
        self.class_stack.append(node.name.value)
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self.class_stack.pop()

    # ---- Functions (free + methods) ----
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        is_method = len(self.class_stack) > 0
        qual = ".".join(self.class_stack + [node.name.value]) if self.class_stack else node.name.value
        qname = f"{self.module_name}:{qual}" if self.module_name else qual
        doc = _first_docstring_from_body(node.body)
        sig = _params_signature(node.params)
        sig_text = f"({sig})" if sig else "()"
        src = _slice_source_lines(self.src, pos.start.line, pos.end.line)
        self.functions.append(
            FunctionInfo(
                name=node.name.value,
                qname=qname,
                is_method=bool(is_method),
                signature=sig_text,
                docstring=doc,
                start=pos.start.line,
                end=pos.end.line,
                source=src,
            )
        )
        self.in_function += 1
        return True

    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        self.in_function -= 1

    # ---- Imports ----
    def visit_Import(self, node: cst.Import) -> Optional[bool]:
        for alias in node.names:
            mod = _full_attr_name(alias.name)
            self.imports.append(
                ImportInfo(
                    kind="import",
                    module=mod,
                    name=None,
                    alias=alias.asname.name.value if alias.asname else None,  # type: ignore[union-attr]
                    is_relative=False,
                    level=0,
                )
            )
        return True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> Optional[bool]:
        level = len(node.relative) if node.relative else 0
        base_module = _full_attr_name(node.module) if node.module is not None else ""
        is_rel = level > 0
        module_str = ("." * level) + base_module if is_rel else base_module

        if isinstance(node.names, cst.ImportStar):
            self.imports.append(
                ImportInfo(kind="from", module=module_str, name="*", alias=None, is_relative=is_rel, level=level)
            )
        else:
            for alias in node.names:
                name = _full_attr_name(alias.name)
                al = alias.asname.name.value if alias.asname else None  # type: ignore[union-attr]
                self.imports.append(
                    ImportInfo(kind="from", module=module_str, name=name, alias=al, is_relative=is_rel, level=level)
                )
        return True

    # ---- Assignments (globals & class attributes) ----
    def visit_Assign(self, node: cst.Assign) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        # Inside a class body (but not inside function): class attribute(s)
        if self.in_function == 0 and self.class_stack:
            class_q = ".".join(self.class_stack)
            class_qname = f"{self.module_name}:{class_q}" if self.module_name else class_q
            src = _slice_source_lines(self.src, pos.start.line, pos.end.line)
            for t in node.targets:
                if isinstance(t.target, cst.Name):
                    preview = cst.Module([]).code_for_node(node.value)
                    if len(preview) > 80:
                        preview = preview[:80] + "…"
                    qname = f"{class_qname}.{t.target.value}"
                    self.class_attrs.append(
                        ClassAttr(
                            name=t.target.value,
                            qname=qname,
                            class_qname=class_qname,
                            annotation=None,
                            value_preview=preview,
                            start=pos.start.line,
                            end=pos.end.line,
                            source=src,
                        )
                    )
            return True

        # Top-level globals (module scope)
        if self.in_function == 0 and not self.class_stack:
            for t in node.targets:
                target = t.target
                if isinstance(target, cst.Name):
                    preview = cst.Module([]).code_for_node(node.value)
                    self.globals.append(
                        GlobalVar(
                            name=target.value,
                            annotation=None,
                            value_preview=(preview[:80] + "…") if len(preview) > 80 else preview,
                        )
                    )
        return True

    def visit_AnnAssign(self, node: cst.AnnAssign) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        # Class attribute with annotation
        if self.in_function == 0 and self.class_stack and isinstance(node.target, cst.Name):
            class_q = ".".join(self.class_stack)
            class_qname = f"{self.module_name}:{class_q}" if self.module_name else class_q
            ann = cst.Module([]).code_for_node(node.annotation.annotation)
            preview = None
            if node.value is not None:
                code = cst.Module([]).code_for_node(node.value)
                preview = (code[:80] + "…") if len(code) > 80 else code
            src = _slice_source_lines(self.src, pos.start.line, pos.end.line)
            qname = f"{class_qname}.{node.target.value}"
            self.class_attrs.append(
                ClassAttr(
                    name=node.target.value,
                    qname=qname,
                    class_qname=class_qname,
                    annotation=ann,
                    value_preview=preview,
                    start=pos.start.line,
                    end=pos.end.line,
                    source=src,
                )
            )
            return True

        # Top-level global with annotation
        if self.in_function == 0 and not self.class_stack and isinstance(node.target, cst.Name):
            ann = cst.Module([]).code_for_node(node.annotation.annotation)
            preview = None
            if node.value is not None:
                code = cst.Module([]).code_for_node(node.value)
                preview = (code[:80] + "…") if len(code) > 80 else code
            self.globals.append(
                GlobalVar(
                    name=node.target.value,
                    annotation=ann,
                    value_preview=preview,
                )
            )
        return True

# ---------- Public API ----------

def parse_python_source(source: str, *, file_path: str, module_name: str = "") -> FileEntities:
    """Parse one Python file worth of source and return extracted entities."""
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module)
    visitor = _EntitiesCollector(module_name=module_name, source_text=source)
    wrapper.visit(visitor)
    return FileEntities(
        path=file_path,
        module=module_name,
        classes=visitor.classes,
        functions=visitor.functions,
        imports=visitor.imports,
        globals=visitor.globals,
        class_attrs=visitor.class_attrs,
    )

def parse_python_file(path: str, *, module_name: str = "") -> FileEntities:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        src = f.read()
    return parse_python_source(src, file_path=path, module_name=module_name)
