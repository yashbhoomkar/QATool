from __future__ import annotations

from typing import Optional, List
import libcst as cst
from libcst import MetadataWrapper
from libcst.metadata import PositionProvider

from .entities import (
    FileEntities, ClassInfo, ClassAttr, FunctionInfo, ImportInfo, GlobalVar
)
from .helpers import (
    slice_source_lines, full_attr_name, first_docstring_from_body, params_signature
)


class _EntitiesCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, module_name: str, source_text: str):
        self.module_name = module_name
        self.src = source_text
        self.class_stack: List[str] = []
        self.in_function: int = 0
        self.classes: List[ClassInfo] = []
        self.functions: List[FunctionInfo] = []
        self.imports: List[ImportInfo] = []
        self.globals: List[GlobalVar] = []
        self.class_attrs: List[ClassAttr] = []

    # ---- Classes ----
    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        qual = ".".join(self.class_stack + [node.name.value])
        qname = f"{self.module_name}:{qual}" if self.module_name else qual
        src = slice_source_lines(self.src, pos.start.line, pos.end.line)
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
        doc = first_docstring_from_body(node.body)
        sig = params_signature(node.params)
        sig_text = f"({sig})" if sig else "()"
        src = slice_source_lines(self.src, pos.start.line, pos.end.line)
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
            mod = full_attr_name(alias.name)
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
        base_module = full_attr_name(node.module) if node.module is not None else ""
        is_rel = level > 0
        module_str = ("." * level) + base_module if is_rel else base_module

        if isinstance(node.names, cst.ImportStar):
            self.imports.append(
                ImportInfo(kind="from", module=module_str, name="*", alias=None, is_relative=is_rel, level=level)
            )
        else:
            for alias in node.names:
                name = full_attr_name(alias.name)
                al = alias.asname.name.value if alias.asname else None  # type: ignore[union-attr]
                self.imports.append(
                    ImportInfo(kind="from", module=module_str, name=name, alias=al, is_relative=is_rel, level=level)
                )
        return True

    # ---- Assignments (globals & class attributes) ----
    def visit_Assign(self, node: cst.Assign) -> Optional[bool]:
        pos = self.get_metadata(PositionProvider, node)
        # class attribute(s)
        if self.in_function == 0 and self.class_stack:
            class_q = ".".join(self.class_stack)
            class_qname = f"{self.module_name}:{class_q}" if self.module_name else class_q
            src = slice_source_lines(self.src, pos.start.line, pos.end.line)
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

        # top-level globals
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
        # class attribute with annotation
        if self.in_function == 0 and self.class_stack and isinstance(node.target, cst.Name):
            class_q = ".".join(self.class_stack)
            class_qname = f"{self.module_name}:{class_q}" if self.module_name else class_q
            ann = cst.Module([]).code_for_node(node.annotation.annotation)
            preview = None
            if node.value is not None:
                code = cst.Module([]).code_for_node(node.value)
                preview = (code[:80] + "…") if len(code) > 80 else code
            src = slice_source_lines(self.src, pos.start.line, pos.end.line)
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

        # top-level annotated global
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


def parse_python_source(source: str, *, file_path: str, module_name: str = "") -> FileEntities:
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
