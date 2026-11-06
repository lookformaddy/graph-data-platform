"""Tests for traversal queries: shortest path, k-hop, centrality, cycles."""

from graph_data_platform.models import Edge, Node
from graph_data_platform.store import GraphStore
from graph_data_platform.traversal import (
    betweenness_centrality,
    connected_components,
    degree_centrality,
    find_cycles,
    k_hop_neighbourhood,
    shortest_path,
)


def _build_chain():
    """a -> b -> c -> d, plus a side branch b -> e."""
    store = GraphStore()
    for nid in "abcde":
        store.upsert_node(Node(id=nid, type="person", properties={"name": nid}))
    for i, (a, b) in enumerate([("a", "b"), ("b", "c"), ("c", "d"), ("b", "e")]):
        store.upsert_edge(Edge(id=f"e{i}", type="works_at", source_id=a, target_id=b))
    return store.commit()


def test_shortest_path():
    snap = _build_chain()
    assert shortest_path(snap, "a", "d") == ["a", "b", "c", "d"]
    assert shortest_path(snap, "a", "e") == ["a", "b", "e"]
    assert shortest_path(snap, "d", "a") is None  # directed: no way back
    assert shortest_path(snap, "a", "a") == ["a"]


def test_shortest_path_unknown_node():
    snap = _build_chain()
    assert shortest_path(snap, "a", "zzz") is None


def test_k_hop_neighbourhood():
    snap = _build_chain()
    assert k_hop_neighbourhood(snap, "b", 1) == {1: ["a", "c", "e"]}
    assert k_hop_neighbourhood(snap, "b", 2) == {1: ["a", "c", "e"], 2: ["d"]}
    assert k_hop_neighbourhood(snap, "zzz", 1) == {}


def test_degree_centrality():
    snap = _build_chain()
    centrality = degree_centrality(snap)
    # b touches a, c, e -> degree 3 of 4 possible
    assert centrality["b"] == 0.75
    assert centrality["d"] == 0.25
    assert all(0.0 <= v <= 1.0 for v in centrality.values())


def test_betweenness_centrality():
    snap = _build_chain()
    centrality = betweenness_centrality(snap)
    # b lies on every a->c/d/e route; d lies on none
    assert centrality["b"] > centrality["d"]
    assert centrality["d"] == 0.0


def test_find_cycles():
    store = GraphStore()
    for nid in "abc":
        store.upsert_node(Node(id=nid, type="person", properties={"name": nid}))
    for i, (a, b) in enumerate([("a", "b"), ("b", "c"), ("c", "a")]):
        store.upsert_edge(Edge(id=f"e{i}", type="reports_to", source_id=a, target_id=b))
    snap = store.commit()
    cycles = find_cycles(snap)
    assert len(cycles) == 1
    assert cycles[0][0] == cycles[0][-1] == "a"
    assert set(cycles[0]) == {"a", "b", "c"}


def test_no_cycles_in_dag():
    snap = _build_chain()
    assert find_cycles(snap) == []


def test_connected_components():
    store = GraphStore()
    for nid in "abcd":
        store.upsert_node(Node(id=nid, type="person", properties={"name": nid}))
    store.upsert_edge(Edge(id="e1", type="works_at", source_id="a", target_id="b"))
    store.upsert_edge(Edge(id="e2", type="works_at", source_id="c", target_id="d"))
    snap = store.commit()
    assert connected_components(snap) == [["a", "b"], ["c", "d"]]
