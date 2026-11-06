"""Versioned graph store with snapshot / time-travel reads.

The store keeps an immutable snapshot per committed version. Readers ask for
a version (or the latest) and get a read-only view of exactly that graph;
writers mutate a working copy and commit it as the next version. History is
never rewritten, so a bad load can be rolled back to by simply reading the
previous version — the core of the platform's time-travel guarantee.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from graph_data_platform.models import Edge, Node


@dataclass(frozen=True)
class Snapshot:
    """An immutable point-in-time view of the graph."""

    version: int
    nodes: dict[str, Node]
    edges: dict[str, Edge]
    created_at: str
    label: str = ""

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)


@dataclass
class GraphStore:
    """Working graph plus its append-only snapshot history."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    snapshots: list[Snapshot] = field(default_factory=list)

    # -- mutation (working copy) -------------------------------------------
    def upsert_node(self, node: Node) -> None:
        """Insert or replace a node. Replacement merges properties so a later
        source can enrich, not wipe, an earlier record."""
        existing = self.nodes.get(node.id)
        if existing is not None:
            merged = dict(existing.properties)
            merged.update(node.properties)
            self.nodes[node.id] = Node(
                id=node.id, type=node.type, properties=merged, source=node.source
            )
        else:
            self.nodes[node.id] = node

    def upsert_edge(self, edge: Edge) -> None:
        self.edges[edge.id] = edge

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        for edge_id in [e for e, ed in self.edges.items() if ed.source_id == node_id or ed.target_id == node_id]:
            del self.edges[edge_id]

    # -- versioning ---------------------------------------------------------
    def commit(self, label: str = "") -> Snapshot:
        """Freeze the working copy as a new immutable snapshot."""
        snapshot = Snapshot(
            version=len(self.snapshots) + 1,
            nodes=copy.deepcopy(self.nodes),
            edges=copy.deepcopy(self.edges),
            created_at=datetime.now(timezone.utc).isoformat(),
            label=label,
        )
        self.snapshots.append(snapshot)
        return snapshot

    @property
    def current_version(self) -> int:
        return len(self.snapshots)

    def snapshot(self, version: int | None = None) -> Snapshot:
        """Read a snapshot by version (time travel). ``None`` = latest.

        Before any commit, version 0 is the empty working graph.
        """
        if version is None:
            if not self.snapshots:
                return Snapshot(version=0, nodes=copy.deepcopy(self.nodes),
                                edges=copy.deepcopy(self.edges),
                                created_at=datetime.now(timezone.utc).isoformat(), label="working")
            return self.snapshots[-1]
        if version == 0:
            return Snapshot(version=0, nodes={}, edges={},
                            created_at="", label="empty")
        if version < 1 or version > len(self.snapshots):
            raise ValueError(f"unknown snapshot version: {version}")
        return self.snapshots[version - 1]

    def versions(self) -> list[dict[str, object]]:
        return [
            {"version": s.version, "label": s.label, "created_at": s.created_at,
             "nodes": s.node_count(), "edges": s.edge_count()}
            for s in self.snapshots
        ]
