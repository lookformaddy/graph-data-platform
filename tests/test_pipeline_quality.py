"""Tests for graph quality checks and the end-to-end pipeline."""

from graph_data_platform.engine import GraphPipeline
from graph_data_platform.generator import generate_all, generate_source_crm, generate_source_erp
from graph_data_platform.models import Edge, Node
from graph_data_platform.quality import dangling_edges, orphan_nodes, quality_report
from graph_data_platform.store import GraphStore


def _store_with_orphan():
    store = GraphStore()
    store.upsert_node(Node(id="a", type="person", properties={"name": "Ana"}))
    store.upsert_node(Node(id="b", type="person", properties={"name": "Ben"}))
    store.upsert_node(Node(id="c", type="person", properties={"name": "Cleo"}))
    store.upsert_edge(Edge(id="e1", type="works_at", source_id="a", target_id="b"))
    return store.commit()


def test_orphan_nodes():
    assert orphan_nodes(_store_with_orphan()) == ["c"]


def test_dangling_edges_detected():
    store = GraphStore()
    store.upsert_node(Node(id="a", type="person", properties={"name": "Ana"}))
    # Bypass validation: hand-insert a dangling edge to test the check itself.
    store.edges["e1"] = Edge(id="e1", type="works_at", source_id="a", target_id="ghost")
    assert dangling_edges(store.commit()) == ["e1"]


def test_quality_report_healthy():
    store = GraphStore()
    store.upsert_node(Node(id="a", type="person", properties={"name": "Ana"}))
    store.upsert_node(Node(id="b", type="organization", properties={"name": "Acme"}))
    store.upsert_edge(Edge(id="e1", type="works_at", source_id="a", target_id="b"))
    report = quality_report(store.commit())
    assert report["status"] == "HEALTHY"
    assert report["issues"] == 0
    assert report["node_types"] == {"person": 1, "organization": 1}


def test_quality_report_flags_orphans():
    report = quality_report(_store_with_orphan())
    assert report["status"] == "WARNING"
    assert report["orphan_count"] == 1


def test_generator_is_deterministic():
    assert generate_source_crm(7) == generate_source_crm(7)
    # Different seeds only re-shuffle; the record set is identical.
    a = generate_source_crm(7)["nodes"]
    b = generate_source_crm(8)["nodes"]
    assert sorted(n["id"] for n in a) == sorted(n["id"] for n in b)
    crm = generate_source_crm()
    assert len(crm["nodes"]) > 0 and len(crm["edges"]) > 0


def test_pipeline_loads_both_sources_and_quarantines_bad_records():
    pipeline = GraphPipeline()
    sources = generate_all()
    crm = pipeline.load_source("crm", sources["crm"]["nodes"], sources["crm"]["edges"])
    assert crm.nodes_accepted > 0
    assert len(crm.quarantined) == 3  # missing name, unknown type, dangling edge
    erp = pipeline.load_source("erp", sources["erp"]["nodes"], sources["erp"]["edges"])
    assert erp.nodes_accepted > 0
    assert pipeline.store.current_version == 2
    assert len(pipeline.lineage()) == 2
    assert len(pipeline.quarantine()) == 3


def test_pipeline_resolution_merges_erp_org_variants():
    pipeline = GraphPipeline()
    sources = generate_all()
    for name, payload in sources.items():
        pipeline.load_source(name, payload["nodes"], payload["edges"])
    before = pipeline.store.snapshot().node_count()
    result = pipeline.resolve_entities()
    assert result["pairs_found"] == 3  # Acme, Globex, Initech variants
    assert result["nodes_absorbed"] == 3
    assert pipeline.store.snapshot().node_count() == before - 3
    # After resolution, no duplicate entities remain.
    assert pipeline.quality()["duplicate_count"] == 0
    assert pipeline.quality()["status"] == "HEALTHY"


def test_pipeline_time_travel_quality():
    pipeline = GraphPipeline()
    sources = generate_all()
    pipeline.load_source("crm", sources["crm"]["nodes"], sources["crm"]["edges"])
    v1 = pipeline.quality(version=1)
    pipeline.load_source("erp", sources["erp"]["nodes"], sources["erp"]["edges"])
    v2 = pipeline.quality(version=2)
    assert v2["nodes"] > v1["nodes"]
    assert v1["version"] == 1 and v2["version"] == 2


def test_pipeline_cross_load_edge_rescue():
    # An edge in the second load may reference nodes from the first load.
    pipeline = GraphPipeline()
    pipeline.load_source(
        "crm",
        [{"id": "a", "type": "person", "properties": {"name": "Ana"}}],
        [],
    )
    result = pipeline.load_source(
        "erp",
        [{"id": "b", "type": "organization", "properties": {"name": "Acme"}}],
        [{"id": "e1", "type": "works_at", "source_id": "a", "target_id": "b"}],
    )
    assert result.edges_accepted == 1
    assert result.lineage.edges_quarantined == 0


def test_pipeline_summary():
    pipeline = GraphPipeline()
    sources = generate_all()
    for name, payload in sources.items():
        pipeline.load_source(name, payload["nodes"], payload["edges"])
    pipeline.resolve_entities()
    summary = pipeline.summary()
    assert summary["loads"] == 2
    assert summary["merges"] == 3
    assert summary["quarantined"] == 3
