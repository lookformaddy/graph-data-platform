"""FastAPI surface for the graph data platform.

Fail-closed: ingestion endpoints validate before writing anything, and
unknown snapshot versions return 404 instead of silently serving latest.
The module degrades gracefully when FastAPI is not installed (``HAS_FASTAPI``
is False) so the core library and its tests still run anywhere.
"""

from __future__ import annotations

from graph_data_platform.engine import GraphPipeline
from graph_data_platform.generator import generate_all
from graph_data_platform.traversal import (
    betweenness_centrality,
    degree_centrality,
    k_hop_neighbourhood,
    shortest_path,
)

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    HAS_FASTAPI = True
except Exception:  # pragma: no cover - FastAPI optional at import time
    FastAPI = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment]
    HAS_FASTAPI = False

pipeline = GraphPipeline()


if HAS_FASTAPI:
    app = FastAPI(title="Graph Data Platform", version="0.1.0")

    class IngestRequest(BaseModel):
        source: str
        nodes: list[dict] = []
        edges: list[dict] = []

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ingest")
    def ingest(req: IngestRequest) -> dict:
        result = pipeline.load_source(req.source, req.nodes, req.edges)
        return {
            "source": req.source,
            "snapshot_version": result.snapshot.version,
            "nodes_accepted": result.nodes_accepted,
            "edges_accepted": result.edges_accepted,
            "quarantined": [q.to_dict() for q in result.quarantined],
            "lineage": result.lineage.to_dict(),
        }

    @app.post("/resolve")
    def resolve() -> dict:
        return pipeline.resolve_entities()

    @app.get("/nodes/{node_id}")
    def get_node(node_id: str) -> dict:
        snap = pipeline.store.snapshot()
        node = snap.nodes.get(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"node not found: {node_id}")
        return node.to_dict()

    @app.get("/nodes")
    def list_nodes(node_type: str | None = None) -> dict:
        snap = pipeline.store.snapshot()
        nodes = [n.to_dict() for n in snap.nodes.values()
                 if node_type is None or n.type == node_type]
        return {"nodes": nodes, "count": len(nodes), "version": snap.version}

    @app.get("/traversal/shortest-path")
    def api_shortest_path(start: str, goal: str) -> dict:
        path = shortest_path(pipeline.store.snapshot(), start, goal)
        if path is None:
            raise HTTPException(status_code=404, detail="no path found")
        return {"path": path, "hops": len(path) - 1}

    @app.get("/traversal/neighbours")
    def api_neighbours(node_id: str, hops: int = 1) -> dict:
        snap = pipeline.store.snapshot()
        if node_id not in snap.nodes:
            raise HTTPException(status_code=404, detail=f"node not found: {node_id}")
        return {"node_id": node_id, "neighbourhood": k_hop_neighbourhood(snap, node_id, hops)}

    @app.get("/traversal/centrality")
    def api_centrality() -> dict:
        snap = pipeline.store.snapshot()
        return {
            "degree": degree_centrality(snap),
            "betweenness": betweenness_centrality(snap),
        }

    @app.get("/quality")
    def api_quality(version: int | None = None) -> dict:
        try:
            return pipeline.quality(version)  # type: ignore[return-value]
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/snapshots")
    def api_snapshots() -> dict:
        return {"snapshots": pipeline.store.versions()}

    @app.get("/snapshots/{version}")
    def api_snapshot(version: int) -> dict:
        try:
            snap = pipeline.store.snapshot(version)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"version": snap.version, "label": snap.label,
                "nodes": [n.to_dict() for n in snap.nodes.values()],
                "edges": [e.to_dict() for e in snap.edges.values()]}

    @app.get("/lineage")
    def api_lineage() -> dict:
        return {"loads": pipeline.lineage(), "quarantine": pipeline.quarantine()}

    @app.post("/demo-seed")
    def demo_seed() -> dict:
        sources = generate_all()
        for name, payload in sources.items():
            pipeline.load_source(name, payload["nodes"], payload["edges"])
        return pipeline.summary()  # type: ignore[return-value]
else:  # pragma: no cover
    app = None  # type: ignore[assignment]
