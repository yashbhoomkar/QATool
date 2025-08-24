# QATool/qa_visualizer/server/main.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .services.scanner import scan_repo
from .services.graph_builder import build_graph
from .services.store import save_graph, load_graph, read_file_text


# ------------------------ Config ------------------------

def _default_repo_root() -> Path:
    # default to the working directory where you start the server
    return Path(os.getenv("QA_VIS_REPO", ".")).resolve()

ALLOWED_ORIGINS = [
    "http://localhost:5173",   # vite dev server (frontend)
    "http://127.0.0.1:5173",
    "http://localhost:3000",   # optional alt port
    "http://127.0.0.1:3000",
]

app = FastAPI(title="QA Visualizer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------ Models ------------------------

class ScanRequest(BaseModel):
    repo_path: Optional[str] = None  # default: server cwd


class ScanResponse(BaseModel):
    stats: Dict[str, int]
    nodes: int
    edges: int
    graph_path: str


class FileResponse(BaseModel):
    path: str
    text: str


class NodeNeighborhood(BaseModel):
    center: Dict[str, Any]
    neighbors: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


# ------------------------ Helpers ------------------------

def _ensure_under_root(candidate: Path, root: Path) -> bool:
    """Return True if candidate is inside root (prevents path traversal)."""
    try:
        cand = candidate.resolve()
        rootp = root.resolve()
        return os.path.commonpath([str(cand), str(rootp)]) == str(rootp)
    except Exception:
        return False


def _node_index(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def _edges_for(graph: Dict[str, Any], node_id: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    es = []
    neigh_ids: List[str] = []
    for e in graph.get("edges", []):
        if e.get("source") == node_id:
            es.append(e)
            neigh_ids.append(e.get("target"))
        elif e.get("target") == node_id:
            es.append(e)
            neigh_ids.append(e.get("source"))
    return es, neigh_ids


# ------------------------ Routes ------------------------

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/graph")
def get_graph(repo_path: Optional[str] = Query(None, description="Repo root (default server cwd)")):
    root = Path(repo_path).resolve() if repo_path else _default_repo_root()
    graph = load_graph(root)
    # attach absolute root in meta for the UI (helpful)
    graph.setdefault("meta", {}).setdefault("root", str(root))
    return graph


@app.get("/file", response_model=FileResponse)
def get_file(path: str, repo_path: Optional[str] = Query(None)):
    root = Path(repo_path).resolve() if repo_path else _default_repo_root()
    text, abs_path = read_file_text(root, path)
    if not _ensure_under_root(abs_path, root):
        raise HTTPException(status_code=400, detail="Requested path is outside repo root.")
    return FileResponse(path=str(abs_path), text=text)


@app.get("/nodes/{node_id:path}", response_model=NodeNeighborhood)
def get_node_and_neighbors(node_id: str, repo_path: Optional[str] = Query(None)):
    """
    Returns the center node, its immediate neighbor nodes, and the edges among them.
    We use {node_id:path} to allow slashes in IDs like 'file:pkg/mod.py'.
    """
    root = Path(repo_path).resolve() if repo_path else _default_repo_root()
    graph = load_graph(root)
    idx = _node_index(graph)
    center = idx.get(node_id)
    if not center:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    edges, neigh_ids = _edges_for(graph, node_id)
    neighbors = [idx[nid] for nid in neigh_ids if nid in idx]
    return NodeNeighborhood(center=center, neighbors=neighbors, edges=edges)


@app.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest):
    """
    Synchronously scans the repo, rebuilds the graph, and saves it.
    For large repos, we can make this async/streamed later.
    """
    root = Path(req.repo_path).resolve() if req.repo_path else _default_repo_root()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {root}")

    files, stats = scan_repo(root)
    graph = build_graph(root, repo_name=root.name, files=files)
    out_path = save_graph(graph, root)

    return ScanResponse(
        stats=stats,
        nodes=len(graph.get("nodes", [])),
        edges=len(graph.get("edges", [])),
        graph_path=str(out_path),
    )
