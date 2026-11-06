"""Graph quality checks: orphan nodes, dangling edges, duplicate entities,
isolated components, and type distribution. A quality report is a snapshot
of graph health at a version — it never mutates the graph.
"""

from __future__ import annotations

from collections import Counter

from graph_data_platform.resolution import find_duplicates
from graph_data_platform.store import Snapshot
from graph_data_platform.traversal import connected_components


def orphan_nodes(snapshot: Snapshot) -> list[str]:
    """Nodes with no incident edges at all (degree zero, either direction)."""
    incident: set[str] = set()
    for edge in snapshot.edges.values():
        incident.add(edge.source_id)
        incident.add(edge.target_id)
    return sorted(n for n in snapshot.nodes if n not in incident)


def dangling_edges(snapshot: Snapshot) -> list[str]:
    """Edges whose source or target node is missing from the snapshot.
    Should be empty after validation, but the check guards against store
    bugs and manual edits."""
    return sorted(
        e.id for e in snapshot.edges.values()
        if e.source_id not in snapshot.nodes or e.target_id not in snapshot.nodes
    )


def duplicate_entities(snapshot: Snapshot) -> list[dict[str, object]]:
    """Unresolved duplicate pairs still present in the graph."""
    return find_duplicates(list(snapshot.nodes.values()))


def quality_report(snapshot: Snapshot) -> dict[str, object]:
    """Full quality report for one snapshot version."""
    orphans = orphan_nodes(snapshot)
    dangling = dangling_edges(snapshot)
    duplicates = duplicate_entities(snapshot)
    components = connected_components(snapshot)
    type_counts = dict(Counter(n.type for n in snapshot.nodes.values()))
    edge_type_counts = dict(Counter(e.type for e in snapshot.edges.values()))
    total = max(len(snapshot.nodes), 1)
    issues = len(orphans) + len(dangling) + len(duplicates)
    return {
        "version": snapshot.version,
        "nodes": len(snapshot.nodes),
        "edges": len(snapshot.edges),
        "node_types": type_counts,
        "edge_types": edge_type_counts,
        "orphan_nodes": orphans,
        "orphan_count": len(orphans),
        "dangling_edges": dangling,
        "dangling_count": len(dangling),
        "duplicate_entities": duplicates,
        "duplicate_count": len(duplicates),
        "component_count": len(components),
        "largest_component": len(components[0]) if components else 0,
        "orphan_rate": round(len(orphans) / total, 4),
        "issues": issues,
        "status": "HEALTHY" if issues == 0 else ("WARNING" if issues <= 5 else "CRITICAL"),
    }
