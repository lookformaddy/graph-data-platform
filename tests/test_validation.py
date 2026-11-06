"""Tests for schema validation and quarantine."""

from graph_data_platform.validation import validate_batch, validate_edge, validate_node


def test_valid_node_accepted():
    node, problem = validate_node(
        {"id": "per-1", "type": "person", "properties": {"name": "Ana Ruiz"}}, "crm"
    )
    assert problem is None and node is not None
    assert node.name == "Ana Ruiz"


def test_node_missing_name_quarantined():
    node, problem = validate_node(
        {"id": "per-1", "type": "person", "properties": {}}, "crm"
    )
    assert node is None
    assert problem is not None and "name" in problem.reason


def test_node_unknown_type_quarantined():
    _, problem = validate_node(
        {"id": "x", "type": "spaceship", "properties": {"name": "X"}}, "crm"
    )
    assert problem is not None and "unknown node type" in problem.reason


def test_node_missing_id_quarantined():
    _, problem = validate_node({"type": "person", "properties": {"name": "Ana"}}, "crm")
    assert problem is not None and "id" in problem.reason


def test_edge_dangling_quarantined():
    _, problem = validate_edge(
        {"id": "e1", "type": "works_at", "source_id": "per-ghost", "target_id": "org-1"},
        "crm", {"org-1"},
    )
    assert problem is not None and "dangling" in problem.reason


def test_edge_self_loop_quarantined():
    _, problem = validate_edge(
        {"id": "e1", "type": "works_at", "source_id": "per-1", "target_id": "per-1"},
        "crm", {"per-1"},
    )
    assert problem is not None and "self-loop" in problem.reason


def test_edge_unknown_type_quarantined():
    _, problem = validate_edge(
        {"id": "e1", "type": "teleports_to", "source_id": "a", "target_id": "b"},
        "crm", {"a", "b"},
    )
    assert problem is not None and "unknown edge type" in problem.reason


def test_batch_validates_nodes_before_edges():
    nodes, edges, quarantined = validate_batch(
        [{"id": "a", "type": "person", "properties": {"name": "A"}},
         {"id": "b", "type": "person", "properties": {}}],
        [{"id": "e1", "type": "works_at", "source_id": "a", "target_id": "b"}],
        "crm",
    )
    assert len(nodes) == 1 and len(edges) == 0
    # b quarantined as a node, and e1 quarantined as dangling (b never accepted)
    assert len(quarantined) == 2
    assert {q.kind for q in quarantined} == {"node", "edge"}
