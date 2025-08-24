from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

import uvicorn

from qa_visualizer.server.services.scanner import scan_repo
from qa_visualizer.server.services.graph_builder import build_graph
from qa_visualizer.server.services.store import save_graph


def _abs_repo(path: Optional[str]) -> Path:
    if not path:
        return Path.cwd().resolve()
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        print(f"[error] Not a directory: {p}", file=sys.stderr)
        sys.exit(2)
    return p


def cmd_scan(args: argparse.Namespace) -> None:
    repo = _abs_repo(args.repo)
    files, stats = scan_repo(repo)
    graph = build_graph(repo, repo_name=repo.name, files=files)
    out = save_graph(graph, repo)
    print(f"[ok] scanned: {repo}")
    print(f"     files={stats['files']} classes={stats['classes']} functions={stats['functions']} "
          f"imports={stats['imports']} globals={stats['globals']}")
    print(f"[ok] graph saved -> {out}")


def cmd_serve(args: argparse.Namespace) -> None:
    repo = _abs_repo(args.repo)
    # Expose repo root to the FastAPI app via env (server defaults to cwd, we override)
    os.environ["QA_VIS_REPO"] = str(repo)
    host = args.host or "127.0.0.1"
    port = int(args.port or 8000)
    reload = bool(args.reload)

    print(f"[ok] serving API for repo: {repo}")
    print(f"     -> http://{host}:{port}")
    # FastAPI app is qa_visualizer.server.main:app
    uvicorn.run("qa_visualizer.server.main:app", host=host, port=port, reload=reload)


def cmd_scan_serve(args: argparse.Namespace) -> None:
    # convenience: scan then serve
    cmd_scan(args)
    cmd_serve(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qa-visualizer",
        description="Scan a Python repo into a graph and serve a local API/UI."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # scan
    sp = sub.add_parser("scan", help="Scan a repository and write .qa_visualizer/graph.json")
    sp.add_argument("repo", nargs="?", help="Path to repo (default: current directory)")
    sp.set_defaults(func=cmd_scan)

    # serve
    sp = sub.add_parser("serve", help="Start the FastAPI server for a repo")
    sp.add_argument("repo", nargs="?", help="Path to repo (default: current directory)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", default=8000, type=int)
    sp.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    sp.set_defaults(func=cmd_serve)

    # scan-serve
    sp = sub.add_parser("scan-serve", help="Scan then serve in one step")
    sp.add_argument("repo", nargs="?", help="Path to repo (default: current directory)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", default=8000, type=int)
    sp.add_argument("--reload", action="store_true")
    sp.set_defaults(func=cmd_scan_serve)

    return p


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
