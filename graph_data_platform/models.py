"""Core graph models: nodes, edges, quarantine records, lineage entries.

Pure stdlib, fully typed. Nodes and edges are plain dataclasses so they can
be serialized to JSON for storage, API responses, and audit trails without
any third-party dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Node types the platform understands. Deliberately generic enterprise
# entity kinds; new types are added here, not ad hoc in ingestion code.
NODE_TYPES = frozenset({"person", "organization", "product", "location", "account"})

# Edge types the platform understands.
EDGE_TYPES = frozenset(
    {"works_at", "supplies", "located_in", "owns", "transacts_with", "reports_to", "part_of"}
)

# Properties that must be present (non-empty) for each node type.
REQUIRED_NODE_PROPS: dict[str, tuple[str, ...]] = {
    "person": ("name",),
    "organization": ("name",),
    "product": ("name",),
    "location": ("name",),
    "account": ("name",),
}

# Edge types that must never be self-loops.
NO_SELF_LOOP = frozenset({"works_at", "reports_to", "supplies", "transacts_with"})


@dataclass
class Node:
    """A graph node: a typed entity with free-form properties."""

    id: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "properties": dict(self.properties),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Node":
        return cls(
            id=str(raw.get("id", "")),
            type=str(raw.get("type", "")),
            properties=dict(raw.get("properties") or {}),
            source=str(raw.get("source", "unknown")),
        )

    @property
    def name(self) -> str:
        """Display name, falling back to the id when no name property exists."""
        value = self.properties.get("name")
        return str(value) if value else self.id


@dataclass
class Edge:
    """A directed, typed relationship between two nodes."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": dict(self.properties),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Edge":
        return cls(
            id=str(raw.get("id", "")),
            type=str(raw.get("type", "")),
            source_id=str(raw.get("source_id", "")),
            target_id=str(raw.get("target_id", "")),
            properties=dict(raw.get("properties") or {}),
            source=str(raw.get("source", "unknown")),
        )


@dataclass
class QuarantineRecord:
    """A record rejected at ingestion, kept with its reason — never dropped silently."""

    record: dict[str, Any]
    reason: str
    source: str
    kind: str  # "node" or "edge"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": self.record,
            "reason": self.reason,
            "source": self.source,
            "kind": self.kind,
        }


@dataclass
class LoadRecord:
    """Lineage entry for one ingested source batch."""

    source: str
    snapshot_version: int
    nodes_accepted: int
    edges_accepted: int
    nodes_quarantined: int
    edges_quarantined: int
    checksum: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "snapshot_version": self.snapshot_version,
            "nodes_accepted": self.nodes_accepted,
            "edges_accepted": self.edges_accepted,
            "nodes_quarantined": self.nodes_quarantined,
            "edges_quarantined": self.edges_quarantined,
            "checksum": self.checksum,
            "timestamp": self.timestamp,
        }


@dataclass
class ResolutionAudit:
    """One entity-resolution decision, kept for merge/split audit."""

    action: str  # "merge" or "split"
    canonical_id: str
    merged_ids: list[str]
    method: str  # "deterministic" or "fuzzy"
    score: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "canonical_id": self.canonical_id,
            "merged_ids": list(self.merged_ids),
            "method": self.method,
            "score": self.score,
            "reason": self.reason,
        }
