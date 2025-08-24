# QATool/qa_visualizer/main.py
import json
from pathlib import Path
from qa_visualizer.server.services.parser import parse_python_file
from qa_visualizer.server.services.scanner import scan_repo
from qa_visualizer.server.services.graph_builder import build_graph
from qa_visualizer.server.services.store import save_graph


FILE_NAME = "/Users/yashbhoomkar/Desktop/Projects/QATool/qa_visualizer/server/services/parser.py"
REPO = "/Users/yashbhoomkar/Desktop/Projects/QATool"


# if __name__ == "__main__":
#     data = parse_python_file(FILE_NAME).to_dict()
#     print(json.dumps(data, indent=2))

# if __name__ == "__main__":
#     files, stats = scan_repo(REPO)
#     print(json.dumps(stats, indent=2))

# if __name__ == "__main__":
#     files, stats = scan_repo(REPO)
#     print("Stats:", json.dumps(stats, indent=2))

#     graph = build_graph(REPO, repo_name=Path(REPO).name, files=files)
#     print("Graph sample:", len(graph["nodes"]), "nodes,", len(graph["edges"]), "edges")

#     # Save to disk for the frontend later
#     out = Path("/Users/yashbhoomkar/Desktop/Projects/QATool/.qa_visualizer")
#     out.mkdir(parents=True, exist_ok=True)
#     (out / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
#     print("Wrote", out / "graph.json")


if __name__ == "__main__":
    files, stats = scan_repo(REPO)
    print("Stats:", json.dumps(stats, indent=2))
    graph = build_graph(REPO, repo_name=Path(REPO).name, files=files)
    out = save_graph(graph, REPO)
    print("Wrote", out)