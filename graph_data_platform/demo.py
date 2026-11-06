"""End-to-end demo: ingest two synthetic sources, resolve entities, run a
traversal and a quality report. Deterministic — same output every run.
"""

from __future__ import annotations

from graph_data_platform.engine import GraphPipeline
from graph_data_platform.generator import generate_all
from graph_data_platform.traversal import (
    betweenness_centrality,
    degree_centrality,
    find_cycles,
    k_hop_neighbourhood,
    shortest_path,
)


def run_demo() -> dict[str, object]:
    pipeline = GraphPipeline()
    sources = generate_all()
    print("== Graph Data Platform demo ==")
    for name, payload in sources.items():
        result = pipeline.load_source(name, payload["nodes"], payload["edges"])
        print(
            f"loaded {name}: {result.nodes_accepted} nodes, {result.edges_accepted} edges, "
            f"{len(result.quarantined)} quarantined -> snapshot v{result.snapshot.version}"
        )
    resolution = pipeline.resolve_entities()
    print(
        f"entity resolution: {resolution['pairs_found']} duplicate pairs, "
        f"{resolution['nodes_absorbed']} nodes absorbed -> snapshot v{resolution['snapshot_version']}"
    )
    for audit in resolution["audit"]:  # type: ignore[union-attr]
        print(f"  merge ({audit['method']}, score {audit['score']}): "
              f"{audit['merged_ids']} -> {audit['canonical_id']}")
    snap = pipeline.store.snapshot()
    path = shortest_path(snap, "per-ana", "prod-widget")
    print(f"shortest path per-ana -> prod-widget: {' -> '.join(path) if path else 'none'}")
    neighbours = k_hop_neighbourhood(snap, "org-acme", 2)
    print(f"2-hop neighbourhood of org-acme: {neighbours}")
    centrality = degree_centrality(snap)
    top = sorted(centrality.items(), key=lambda kv: -kv[1])[:3]
    print(f"top degree centrality: {top}")
    print(f"betweenness (top): {sorted(betweenness_centrality(snap).items(), key=lambda kv: -kv[1])[:3]}")
    print(f"cycles found: {len(find_cycles(snap))}")
    report = pipeline.quality()
    print(
        f"quality v{report['version']}: {report['nodes']} nodes, {report['edges']} edges, "
        f"{report['orphan_count']} orphans, {report['dangling_count']} dangling, "
        f"{report['duplicate_count']} duplicates, {report['component_count']} components — "
        f"{report['status']}"
    )
    print(f"lineage: {len(pipeline.lineage())} loads, {len(pipeline.quarantine())} quarantined records")
    print(f"summary: {pipeline.summary()}")
    return {"resolution": resolution, "quality": report, "summary": pipeline.summary()}


if __name__ == "__main__":
    run_demo()
