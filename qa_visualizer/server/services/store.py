from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


# Where we keep the generated graph
DATA_DIRNAME = ".qa_visualizer"
GRAPH_FILENAME = "graph.json"


def ensure_data_dir(repo_root: str | Path) -> Path:
    """Create .qa_visualizer under the repo root if missing."""
    root = Path(repo_root).resolve()
    data_dir = root / DATA_DIRNAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def graph_file_path(repo_root: str | Path) -> Path:
    """Absolute path to the graph.json under .qa_visualizer."""
    return ensure_data_dir(repo_root) / GRAPH_FILENAME


def save_graph(graph: Dict[str, Any], repo_root: str | Path) -> Path:
    """Write graph JSON to .qa_visualizer/graph.json (pretty-printed)."""
    out = graph_file_path(repo_root)
    out.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return out


def load_graph(repo_root: str | Path) -> Dict[str, Any]:
    """Read graph JSON if present; otherwise return an empty graph shape."""
    fp = graph_file_path(repo_root)
    if not fp.exists():
        # minimal empty shape the frontend can handle
        return {"nodes": [], "edges": [], "meta": {"repo": Path(repo_root).name}}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        # corrupted file — return empty so UI still loads
        return {"nodes": [], "edges": [], "meta": {"repo": Path(repo_root).name}}


def read_file_text(repo_root: str | Path, path: str) -> Tuple[str, Path]:
    """
    Return (text, abs_path) for a file.
    - If `path` is absolute, use it.
    - If `path` is relative, treat it as relative to repo_root.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(repo_root) / path
    p = p.resolve()
    text = p.read_text(encoding="utf-8", errors="replace")
    return text, p
