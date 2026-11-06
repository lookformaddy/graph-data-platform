"""API tests. Auto-skip when FastAPI is not installed; the full suite
(including these) runs in CI and in the venv check."""

import pytest

try:
    from fastapi.testclient import TestClient

    from graph_data_platform.api import HAS_FASTAPI, app
except Exception:  # pragma: no cover - FastAPI optional
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


@pytest.fixture(autouse=True)
def fresh_pipeline():
    """Reset the API's global pipeline so each test is self-contained."""
    import graph_data_platform.api as api_module
    from graph_data_platform.engine import GraphPipeline

    api_module.pipeline = GraphPipeline()
    yield
    api_module.pipeline = GraphPipeline()


def test_health():
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}


def test_demo_seed_ingest_and_query():
    c = TestClient(app)
    r = c.post("/demo-seed")
    assert r.status_code == 200
    summary = r.json()
    assert summary["nodes"] > 0 and summary["edges"] > 0
    nodes = c.get("/nodes").json()
    assert nodes["count"] == summary["nodes"]
    orgs = c.get("/nodes", params={"node_type": "organization"}).json()
    # 5 CRM orgs + 3 ERP name-variant orgs (merged only after /resolve)
    assert orgs["count"] == 8
    assert c.get("/nodes/per-ana").status_code == 200
    assert c.get("/nodes/no-such-node").status_code == 404


def test_ingest_validates_and_quarantines():
    c = TestClient(app)
    c.post("/demo-seed")  # org-acme must exist for the cross-load edge below
    r = c.post("/ingest", json={
        "source": "test",
        "nodes": [{"id": "t1", "type": "person", "properties": {"name": "Test One"}},
                  {"id": "t2", "type": "person", "properties": {}}],
        # Cross-load edge: org-acme already exists from the earlier demo seed.
        "edges": [{"id": "te1", "type": "works_at", "source_id": "t1", "target_id": "org-acme"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["nodes_accepted"] == 1
    assert body["edges_accepted"] == 1
    assert len(body["quarantined"]) == 1


def test_traversal_and_quality_endpoints():
    c = TestClient(app)
    c.post("/demo-seed")
    c.post("/resolve")
    r = c.get("/traversal/shortest-path", params={"start": "per-ana", "goal": "prod-widget"})
    assert r.status_code == 200
    assert r.json()["path"] == ["per-ana", "org-acme", "prod-widget"]
    assert c.get("/traversal/shortest-path",
                 params={"start": "per-ana", "goal": "nope"}).status_code == 404
    neighbours = c.get("/traversal/neighbours",
                       params={"node_id": "org-acme", "hops": 1}).json()
    assert "org-acme" not in neighbours["neighbourhood"].get("1", [])
    quality = c.get("/quality").json()
    assert quality["status"] == "HEALTHY"
    assert c.get("/quality", params={"version": 999}).status_code == 404


def test_snapshots_and_lineage_endpoints():
    c = TestClient(app)
    c.post("/demo-seed")
    snaps = c.get("/snapshots").json()["snapshots"]
    assert len(snaps) == 2
    v1 = c.get("/snapshots/1").json()
    assert v1["version"] == 1 and len(v1["nodes"]) > 0
    assert c.get("/snapshots/999").status_code == 404
    lineage = c.get("/lineage").json()
    assert len(lineage["loads"]) == 2
    assert len(lineage["quarantine"]) == 3
