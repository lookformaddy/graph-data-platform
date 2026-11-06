"""Ingestion: load node/edge records from a named source into the store.

Each load is a single atomic-feeling step: validate the whole batch (nodes
first, then edges against the accepted nodes plus the existing graph),
upsert the accepted records, commit a new snapshot version, and write a
lineage entry. Quarantined records never reach the graph, and the lineage
entry records exactly what was accepted, rejected, and why.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from graph_data_platform.models import LoadRecord, QuarantineRecord
from graph_data_platform.store import GraphStore, Snapshot
from graph_data_platform.validation import validate_batch


@dataclass
class LoadResult:
    """Outcome of one source load."""

    source: str
    snapshot: Snapshot
    lineage: LoadRecord
    quarantined: list[QuarantineRecord] = field(default_factory=list)

    @property
    def nodes_accepted(self) -> int:
        return self.lineage.nodes_accepted

    @property
    def edges_accepted(self) -> int:
        return self.lineage.edges_accepted


class Ingestor:
    """Loads validated batches into a GraphStore, keeping lineage + quarantine."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store
        self.lineage: list[LoadRecord] = []
        self.quarantine: list[QuarantineRecord] = []

    def load(
        self,
        source: str,
        raw_nodes: list[dict],
        raw_edges: list[dict],
    ) -> LoadResult:
        nodes, edges, quarantined = validate_batch(raw_nodes, raw_edges, source)
        # Edges may also reference nodes already in the store (cross-load
        # edges). Re-check dangling edges against the union of accepted
        # batch nodes and existing store nodes, rescuing any edge whose
        # endpoints exist in the store.
        rescued: list[dict] = []
        still_quarantined: list[QuarantineRecord] = []
        for record in quarantined:
            if record.kind != "edge" or not str(record.reason).startswith("dangling edge"):
                still_quarantined.append(record)
                continue
            raw = record.record
            batch_ids = {n.id for n in nodes}
            if (raw.get("source_id") in self.store.nodes or raw.get("source_id") in batch_ids) and (
                raw.get("target_id") in self.store.nodes or raw.get("target_id") in batch_ids
            ):
                rescued.append(raw)
            else:
                still_quarantined.append(record)
        if rescued:
            from graph_data_platform.validation import validate_edge

            known = {n.id for n in nodes} | set(self.store.nodes)
            for raw in rescued:
                edge, problem = validate_edge(raw, source, known)
                if problem is not None:
                    still_quarantined.append(problem)
                else:
                    edges.append(edge)  # type: ignore[arg-type]
        for node in nodes:
            self.store.upsert_node(node)
        for edge in edges:
            self.store.upsert_edge(edge)
        snapshot = self.store.commit(label=f"load:{source}")
        checksum = hashlib.sha256(
            json.dumps({"nodes": raw_nodes, "edges": raw_edges}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        lineage = LoadRecord(
            source=source,
            snapshot_version=snapshot.version,
            nodes_accepted=len(nodes),
            edges_accepted=len(edges),
            nodes_quarantined=sum(1 for q in still_quarantined if q.kind == "node"),
            edges_quarantined=sum(1 for q in still_quarantined if q.kind == "edge"),
            checksum=checksum,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.lineage.append(lineage)
        self.quarantine.extend(still_quarantined)
        return LoadResult(source=source, snapshot=snapshot, lineage=lineage, quarantined=still_quarantined)

    def load_json_file(self, source: str, path: str) -> LoadResult:
        """Load a JSON file shaped as {"nodes": [...], "edges": [...]}."""
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return self.load(source, payload.get("nodes", []), payload.get("edges", []))
