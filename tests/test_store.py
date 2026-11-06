"""Tests for the versioned graph store and snapshot / time-travel reads."""

import pytest

from graph_data_platform.models import Edge, Node
from graph_data_platform.store import GraphStore


def _node(node_id, name="N"):
    return Node(id=node_id, type="person", properties={"name": name})


def _edge(edge_id, a, b):
    return Edge(id=edge_id, type="works_at", source_id=a, target_id=b)


def test_commit_creates_immutable_snapshot():
    store = GraphStore()
    store.upsert_node(_node("a", "Ana"))
    snap1 = store.commit(label="v1")
    assert snap1.version == 1 and snap1.node_count() == 1
    store.upsert_node(_node("b", "Ben"))
    snap2 = store.commit(label="v2")
    assert snap2.version == 2 and snap2.node_count() == 2
    # v1 is untouched by the later write
    assert store.snapshot(1).node_count() == 1
    assert store.snapshot(2).node_count() == 2


def test_time_travel_read_returns_earlier_graph():
    store = GraphStore()
    store.upsert_node(_node("a"))
    store.commit()
    store.upsert_node(_node("b"))
    store.upsert_edge(_edge("e1", "a", "b"))
    store.commit()
    v1 = store.snapshot(1)
    assert "b" not in v1.nodes and len(v1.edges) == 0
    assert store.snapshot().node_count() == 2  # latest


def test_unknown_version_raises():
    store = GraphStore()
    store.commit()
    with pytest.raises(ValueError):
        store.snapshot(99)


def test_upsert_merges_properties():
    store = GraphStore()
    store.upsert_node(Node(id="a", type="person", properties={"name": "Ana", "city": "X"}))
    store.upsert_node(Node(id="a", type="person", properties={"name": "Ana", "email": "a@x.com"}))
    node = store.nodes["a"]
    assert node.properties["city"] == "X" and node.properties["email"] == "a@x.com"


def test_remove_node_removes_incident_edges():
    store = GraphStore()
    store.upsert_node(_node("a"))
    store.upsert_node(_node("b"))
    store.upsert_edge(_edge("e1", "a", "b"))
    store.remove_node("a")
    assert "a" not in store.nodes and "e1" not in store.edges


def test_versions_listing():
    store = GraphStore()
    store.commit(label="first")
    store.commit(label="second")
    versions = store.versions()
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["label"] == "first"
