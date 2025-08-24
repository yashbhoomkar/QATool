from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple, Dict

from .parser import parse_python_file, FileEntities

# Default directories to skip
DEFAULT_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "myvenv"
}

IGNORE_FILES = [".gitignore", ".qa-visualizerignore"]


def _read_ignore_patterns(root: Path) -> List[str]:
    patterns: List[str] = []
    for fname in IGNORE_FILES:
        p = root / fname
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)
    return patterns


def _is_ignored(rel_path: str, is_dir: bool, patterns: List[str]) -> bool:
    """
    Very simple pattern filter:
    - exact directory names from DEFAULT_IGNORED_DIRS are always ignored
    - support trailing '/*' or simple glob '*' in ignore patterns (best-effort)
    """
    parts = rel_path.split("/")
    if is_dir and parts[-1] in DEFAULT_IGNORED_DIRS:
        return True

    # Fast-path: ignore common virtualenv names even if not in patterns
    if is_dir and parts[-1] in {"env", ".env"}:
        return True

    # Naive glob checks (good enough for MVP)
    for pat in patterns:
        if pat.endswith("/*"):
            base = pat[:-2]
            if rel_path == base or rel_path.startswith(base + "/"):
                return True
        elif "*" in pat:
            # convert very simply: '*' -> '.*' and match
            import re

            rx = "^" + re.escape(pat).replace("\\*", ".*") + "$"
            if re.match(rx, rel_path):
                return True
        else:
            if rel_path == pat or rel_path.startswith(pat + "/"):
                return True
    return False


def _module_name_from_path(root: Path, file_path: Path) -> str:
    """
    Compute a dotted module path from a file path relative to root.
    Handles packages by skipping '__init__.py' in the name.
    Example:
      root=/repo, file=/repo/emailrouter/main.py -> 'emailrouter.main'
      root=/repo, file=/repo/pkg/__init__.py    -> 'pkg'
    """
    rel = file_path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]  # strip .py
    # Remove trailing '__init__'
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p)


def iter_python_files(root: Path) -> Iterable[Path]:
    patterns = _read_ignore_patterns(root)
    for dirpath, dirnames, filenames in os.walk(root):
        # normalize paths
        dir_rel = Path(dirpath).relative_to(root).as_posix() if Path(dirpath) != root else ""
        # prune ignored dirs in-place
        keep: List[str] = []
        for d in dirnames:
            rel = (Path(dir_rel) / d).as_posix() if dir_rel else d
            if not _is_ignored(rel, is_dir=True, patterns=patterns) and d not in DEFAULT_IGNORED_DIRS:
                keep.append(d)
        dirnames[:] = keep

        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            rel_file = (Path(dir_rel) / fn).as_posix() if dir_rel else fn
            if _is_ignored(rel_file, is_dir=False, patterns=patterns):
                continue
            yield Path(dirpath) / fn


def scan_repo(repo_path: str | Path) -> Tuple[List[FileEntities], Dict[str, int]]:
    """
    Walk repo_path, parse each .py file, and return (entities_per_file, stats).
    Stats include counts for files, classes, functions, imports, globals.
    """
    root = Path(repo_path).resolve()
    assert root.exists() and root.is_dir(), f"Not a directory: {root}"

    all_entities: List[FileEntities] = []
    stats = {"files": 0, "classes": 0, "functions": 0, "imports": 0, "globals": 0}

    for p in iter_python_files(root):
        module_name = _module_name_from_path(root, p)
        fe = parse_python_file(str(p), module_name=module_name)
        all_entities.append(fe)
        stats["files"] += 1
        stats["classes"] += len(fe.classes)
        stats["functions"] += len(fe.functions)
        stats["imports"] += len(fe.imports)
        stats["globals"] += len(fe.globals)

    return all_entities, stats
