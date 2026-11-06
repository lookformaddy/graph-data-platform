"""CLI for the graph data platform: load synthetic sources, resolve, query."""

from __future__ import annotations

import argparse
import json
import sys

from graph_data_platform.engine import GraphPipeline
from graph_data_platform.generator import generate_all
from graph_data_platform.traversal import (
    degree_centrality,
    k_hop_neighbourhood,
    shortest_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graph-data-platform", description="Enterprise graph data platform")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run the end-to-end demo on synthetic data")
    load = sub.add_parser("load", help="load a JSON source file")
    load.add_argument("source")
    load.add_argument("path")
    quality = sub.add_parser("quality", help="print the quality report")
    quality.add_argument("--version", type=int, default=None)
    path = sub.add_parser("path", help="shortest path between two nodes")
    path.add_argument("start")
    path.add_argument("goal")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = GraphPipeline()
    if args.command == "demo":
        from graph_data_platform.demo import run_demo

        run_demo()
        return 0
    sources = generate_all()
    for name, payload in sources.items():
        pipeline.load_source(name, payload["nodes"], payload["edges"])
    pipeline.resolve_entities()
    if args.command == "load":
        result = pipeline.ingestor.load_json_file(args.source, args.path)
        print(json.dumps(result.lineage.to_dict(), indent=2))
    elif args.command == "quality":
        print(json.dumps(pipeline.quality(args.version), indent=2))
    elif args.command == "path":
        path = shortest_path(pipeline.store.snapshot(), args.start, args.goal)
        if path is None:
            print(f"no path from {args.start} to {args.goal}", file=sys.stderr)
            return 1
        print(" -> ".join(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
