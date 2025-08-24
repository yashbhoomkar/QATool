# QATool/qa_visualizer/server/services/graph_builder.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Any, Set

from .parser import FileEntities, ClassInfo, FunctionInfo, ImportInfo, GlobalVar


def _node_id_repo(name: str) -> str:
    return f"repo:{name}"


def _node_id_dir(rel_dir: str) -> str:
    # rel_dir is POSIX-style relative directory path ('' allowed for root)
    return f"dir:{rel_dir or '/'}"


def _node_id_file(rel_file: str) -> str:
    return f"file:{rel_file}"


def _node_id_class(qname: str) -> str:
    return f"class:{qname}"


def _node_id_func(qname: str) -> str:
    return f"func:{qname}"


def _node_id_var(file_rel: str, name: str) -> str:
    # globals are file-scoped
    return f"var:{file_rel}#{name}"


def _node_id_import(file_rel: str, index: int) -> str:
    # import sites are unique per file by index
    return f"import:{file_rel}#{index}"


def _edge_id(source: str, target: str, etype: str) -> str:
    return f"edge:{etype}:{source}->{target}"


def _ensure_node(nodes: Dict[str, Dict[str, Any]], node: Dict[str, Any]) -> None:
    nid = node["id"]
    if nid not in nodes:
        nodes[nid] = node


def _ensure_edge(edges: Dict[str, Dict[str, Any]], edge: Dict[str, Any]) -> None:
    eid = edge["id"]
    if eid not in edges:
        edges[eid] = edge


def _posix_rel(root: Path, full_path: Path) -> str:
    return full_path.resolve().relative_to(root.resolve()).as_posix()


def build_graph(
    repo_root: str | Path,
    repo_name: str,
    files: List[FileEntities],
) -> Dict[str, Any]:
    """
    Build a normalized graph dict:
    {
      "nodes": [ ... ],
      "edges": [ ... ],
      "meta": { "repo": repo_name }
    }
    """
    root = Path(repo_root).resolve()

    node_map: Dict[str, Dict[str, Any]] = {}
    edge_map: Dict[str, Dict[str, Any]] = {}

    # Repository node
    repo_node_id = _node_id_repo(repo_name)
    _ensure_node(
        node_map,
        {"id": repo_node_id, "type": "Repository", "label": repo_name, "attrs": {"root": str(root)}},
    )

    # Track created dir nodes to avoid duplicates, and parent links
    created_dirs: Set[str] = set()

    def ensure_dir_nodes_for(rel_file: str) -> None:
        # For rel path like "pkg/sub/file.py", create dir nodes for "pkg" and "pkg/sub"
        parts = rel_file.split("/")[:-1]  # directories only
        cur = []
        for part in parts:
            cur.append(part)
            rel_dir = "/".join(cur) if cur else ""
            dir_id = _node_id_dir(rel_dir)
            if dir_id not in created_dirs:
                created_dirs.add(dir_id)
                # Create Directory node
                _ensure_node(
                    node_map,
                    {"id": dir_id, "type": "Directory", "label": rel_dir or "/", "attrs": {"path": rel_dir or "/"}},
                )
                # Connect repo->top or parent->child
                if len(cur) == 1:
                    # top-level dir under repo
                    _ensure_edge(
                        edge_map,
                        {"id": _edge_id(repo_node_id, dir_id, "CONTAINS"),
                         "type": "CONTAINS", "source": repo_node_id, "target": dir_id}
                    )
                else:
                    parent_rel = "/".join(cur[:-1]) or "/"
                    parent_id = _node_id_dir(parent_rel)
                    _ensure_edge(
                        edge_map,
                        {"id": _edge_id(parent_id, dir_id, "CONTAINS"),
                         "type": "CONTAINS", "source": parent_id, "target": dir_id}
                    )

    for fe in files:
        full_path = Path(fe.path)
        rel_file = _posix_rel(root, full_path)

        # Directory chain
        ensure_dir_nodes_for(rel_file)

        # File node
        file_id = _node_id_file(rel_file)
        _ensure_node(
            node_map,
            {
                "id": file_id,
                "type": "File",
                "label": rel_file.split("/")[-1],
                "attrs": {"path": rel_file, "module": fe.module or ""},
            },
        )

        # Link file under its directory (or repo if at root)
        parent_dir_rel = rel_file.rsplit("/", 1)[0] if "/" in rel_file else "/"
        parent_dir_id = _node_id_dir(parent_dir_rel)
        if parent_dir_id not in node_map:
            # file at root: ensure root directory node exists
            _ensure_node(
                node_map,
                {"id": parent_dir_id, "type": "Directory", "label": "/", "attrs": {"path": "/"}},
            )
            _ensure_edge(
                edge_map,
                {"id": _edge_id(repo_node_id, parent_dir_id, "CONTAINS"),
                 "type": "CONTAINS", "source": repo_node_id, "target": parent_dir_id},
            )

        _ensure_edge(
            edge_map,
            {"id": _edge_id(parent_dir_id, file_id, "CONTAINS"),
             "type": "CONTAINS", "source": parent_dir_id, "target": file_id},
        )

        # Declarations inside file
        for cls in fe.classes:
            cid = _node_id_class(cls.qname)
            _ensure_node(
                node_map,
                {
                    "id": cid,
                    "type": "Class",
                    "label": cls.name,
                    "attrs": {"qname": cls.qname, "start": cls.start, "end": cls.end},
                },
            )
            _ensure_edge(
                edge_map,
                {"id": _edge_id(file_id, cid, "DECLARES"),
                 "type": "DECLARES", "source": file_id, "target": cid},
            )

        for fn in fe.functions:
            fid = _node_id_func(fn.qname)
            _ensure_node(
                node_map,
                {
                    "id": fid,
                    "type": "Function",
                    "label": fn.name,
                    "attrs": {
                        "qname": fn.qname,
                        "is_method": fn.is_method,
                        "signature": fn.signature,
                        "docstring": fn.docstring or "",
                        "start": fn.start,
                        "end": fn.end,
                    },
                },
            )
            # function declared in file OR under class (we’ll keep it simple: file -> function)
            _ensure_edge(
                edge_map,
                {"id": _edge_id(file_id, fid, "DECLARES"),
                 "type": "DECLARES", "source": file_id, "target": fid},
            )

        # Globals
        for gv in fe.globals:
            vid = _node_id_var(rel_file, gv.name)
            _ensure_node(
                node_map,
                {
                    "id": vid,
                    "type": "Variable",
                    "label": gv.name,
                    "attrs": {"annotation": gv.annotation or "", "value_preview": gv.value_preview or ""},
                },
            )
            _ensure_edge(
                edge_map,
                {"id": _edge_id(file_id, vid, "DECLARES"),
                 "type": "DECLARES", "source": file_id, "target": vid},
            )

        # Imports (as use-sites)
        for idx, imp in enumerate(fe.imports):
            iid = _node_id_import(rel_file, idx)
            _ensure_node(
                node_map,
                {
                    "id": iid,
                    "type": "Import",
                    "label": (imp.name or imp.module),
                    "attrs": {
                        "kind": imp.kind,
                        "module": imp.module,
                        "name": imp.name or "",
                        "alias": imp.alias or "",
                        "is_relative": bool(imp.is_relative),
                        "level": imp.level,
                    },
                },
            )
            _ensure_edge(
                edge_map,
                {"id": _edge_id(file_id, iid, "IMPORTS"),
                 "type": "IMPORTS", "source": file_id, "target": iid},
            )

    # Materialize
    graph = {
        "nodes": list(node_map.values()),
        "edges": list(edge_map.values()),
        "meta": {"repo": repo_name},
    }
    return graph
