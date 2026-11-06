"""Pipeline orchestration: load sources -> resolve entities -> quality report.

The pipeline is the object operators and tests drive: it owns the store,
the ingestor, and the resolver, and every step produces auditable output
(lineage entries, resolution audit, quality report) tied to a snapshot
version.
"""

from __future__ import annotations

from graph_data_platform.ingestion import Ingestor, LoadResult
from graph_data_platform.models import Node
from graph_data_platform.quality import quality_report
from graph_data_platform.resolution import EntityResolver
from graph_data_platform.store import GraphStore


class GraphPipeline:
    """End-to-end graph load pipeline over one versioned store."""

    def __init__(self, fuzzy_threshold: float = 0.85) -> None:
        self.store = GraphStore()
        self.ingestor = Ingestor(self.store)
        self.resolver = EntityResolver(fuzzy_threshold=fuzzy_threshold)

    def load_source(self, source: str, raw_nodes: list[dict], raw_edges: list[dict]) -> LoadResult:
        return self.ingestor.load(source, raw_nodes, raw_edges)

    def resolve_entities(self) -> dict[str, object]:
        """Run entity resolution over the current working graph, rewrite
        edges that pointed at absorbed duplicates, and commit the result
        as a new snapshot version."""
        nodes = list(self.store.nodes.values())
        resolved, pairs = self.resolver.resolve(nodes)
        absorbed = {n.id for n in nodes} - {n.id for n in resolved}
        canonical_by_merged = {
            audit.merged_ids[0]: audit.canonical_id
            for audit in self.resolver.audit
            if audit.action == "merge" and audit.merged_ids
        }
        self.store.nodes = {n.id: n for n in resolved}
        for edge in list(self.store.edges.values()):
            new_source = canonical_by_merged.get(edge.source_id, edge.source_id)
            new_target = canonical_by_merged.get(edge.target_id, edge.target_id)
            if new_source != edge.source_id or new_target != edge.target_id:
                edge.source_id = new_source
                edge.target_id = new_target
        snapshot = self.store.commit(label="entity-resolution")
        return {
            "pairs_found": len(pairs),
            "pairs": pairs,
            "nodes_absorbed": len(absorbed),
            "snapshot_version": snapshot.version,
            "audit": [a.to_dict() for a in self.resolver.audit],
        }

    def quality(self, version: int | None = None) -> dict[str, object]:
        return quality_report(self.store.snapshot(version))

    def lineage(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.ingestor.lineage]

    def quarantine(self) -> list[dict[str, object]]:
        return [q.to_dict() for q in self.ingestor.quarantine]

    def summary(self) -> dict[str, object]:
        snap = self.store.snapshot()
        return {
            "current_version": self.store.current_version,
            "nodes": snap.node_count(),
            "edges": snap.edge_count(),
            "loads": len(self.ingestor.lineage),
            "quarantined": len(self.ingestor.quarantine),
            "merges": sum(1 for a in self.resolver.audit if a.action == "merge"),
            "splits": sum(1 for a in self.resolver.audit if a.action == "split"),
        }
