from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class ClassInfo:
    name: str
    qname: str                  # e.g., "pkg.module:ClassName"
    start: int
    end: int
    source: str                 # exact slice (preserve whitespace)


@dataclass
class ClassAttr:
    name: str
    qname: str                  # e.g., "pkg.mod:Class.attr"
    class_qname: str            # e.g., "pkg.mod:Class"
    annotation: Optional[str]
    value_preview: Optional[str]
    start: int
    end: int
    source: str                 # exact slice


@dataclass
class FunctionInfo:
    name: str
    qname: str                  # "pkg.module:func" or "pkg.module:Class.method"
    is_method: bool
    signature: str              # textual signature (best-effort)
    docstring: Optional[str]
    start: int
    end: int
    source: str                 # exact slice


@dataclass
class ImportInfo:
    kind: str                   # "import" | "from"
    module: str                 # "os", "pathlib", ".utils", "pkg.sub"
    name: Optional[str]         # for "from X import name"; None for bare "import X"
    alias: Optional[str]
    is_relative: bool
    level: int                  # 0 for absolute; 1.. for relative (dots)


@dataclass
class GlobalVar:
    name: str
    annotation: Optional[str]       # textual annotation if any
    value_preview: Optional[str]    # first ~80 chars (not executed)


@dataclass
class FileEntities:
    path: str
    module: str                      # dotted module path (optional)
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
