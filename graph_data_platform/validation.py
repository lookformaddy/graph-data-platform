"""Schema validation and quarantine for incoming graph records.

Fail-closed: any record that does not satisfy the schema is quarantined with
a human-readable reason and never enters the graph. The validator is pure
stdlib and operates on plain dicts so it can run before any model object
is constructed.
"""

from __future__ import annotations

from typing import Any

from graph_data_platform.models import (
    EDGE_TYPES,
    NO_SELF_LOOP,
    NODE_TYPES,
    REQUIRED_NODE_PROPS,
    Edge,
    Node,
    QuarantineRecord,
)


def validate_node(raw: dict[str, Any], source: str) -> tuple[Node | None, QuarantineRecord | None]:
    """Validate one raw node record. Returns (node, None) or (None, quarantine)."""
    if not isinstance(raw, dict):
        return None, QuarantineRecord(record={}, reason="node record is not an object", source=source, kind="node")
    node_id = raw.get("id")
    if not isinstance(node_id, str) or not node_id.strip():
        return None, QuarantineRecord(record=raw, reason="missing or empty node id", source=source, kind="node")
    node_type = raw.get("type")
    if node_type not in NODE_TYPES:
        return None, QuarantineRecord(
            record=raw, reason=f"unknown node type: {node_type!r}", source=source, kind="node"
        )
    props = raw.get("properties")
    if props is None:
        props = {}
    if not isinstance(props, dict):
        return None, QuarantineRecord(record=raw, reason="node properties must be an object", source=source, kind="node")
    for required in REQUIRED_NODE_PROPS.get(str(node_type), ()):
        value = props.get(required)
        if not isinstance(value, str) or not value.strip():
            return None, QuarantineRecord(
                record=raw, reason=f"missing required property {required!r} for type {node_type!r}",
                source=source, kind="node",
            )
    return Node(id=node_id.strip(), type=str(node_type), properties=dict(props), source=source), None


def validate_edge(
    raw: dict[str, Any], source: str, known_node_ids: set[str]
) -> tuple[Edge | None, QuarantineRecord | None]:
    """Validate one raw edge record against the set of known node ids.

    Dangling edges (endpoint not in the graph or in the same batch) are
    quarantined, not silently dropped — a dangling edge is a data-quality
    signal about the source, not a detail to hide.
    """
    if not isinstance(raw, dict):
        return None, QuarantineRecord(record={}, reason="edge record is not an object", source=source, kind="edge")
    edge_id = raw.get("id")
    if not isinstance(edge_id, str) or not edge_id.strip():
        return None, QuarantineRecord(record=raw, reason="missing or empty edge id", source=source, kind="edge")
    edge_type = raw.get("type")
    if edge_type not in EDGE_TYPES:
        return None, QuarantineRecord(
            record=raw, reason=f"unknown edge type: {edge_type!r}", source=source, kind="edge"
        )
    source_id, target_id = raw.get("source_id"), raw.get("target_id")
    if not isinstance(source_id, str) or not source_id.strip():
        return None, QuarantineRecord(record=raw, reason="missing or empty edge source_id", source=source, kind="edge")
    if not isinstance(target_id, str) or not target_id.strip():
        return None, QuarantineRecord(record=raw, reason="missing or empty edge target_id", source=source, kind="edge")
    if edge_type in NO_SELF_LOOP and source_id == target_id:
        return None, QuarantineRecord(
            record=raw, reason=f"self-loop not allowed for edge type {edge_type!r}", source=source, kind="edge"
        )
    if source_id not in known_node_ids:
        return None, QuarantineRecord(
            record=raw, reason=f"dangling edge: source node {source_id!r} not found", source=source, kind="edge"
        )
    if target_id not in known_node_ids:
        return None, QuarantineRecord(
            record=raw, reason=f"dangling edge: target node {target_id!r} not found", source=source, kind="edge"
        )
    props = raw.get("properties") or {}
    if not isinstance(props, dict):
        return None, QuarantineRecord(record=raw, reason="edge properties must be an object", source=source, kind="edge")
    return (
        Edge(
            id=edge_id.strip(), type=str(edge_type),
            source_id=source_id.strip(), target_id=target_id.strip(),
            properties=dict(props), source=source,
        ),
        None,
    )


def validate_batch(
    raw_nodes: list[dict[str, Any]], raw_edges: list[dict[str, Any]], source: str
) -> tuple[list[Node], list[Edge], list[QuarantineRecord]]:
    """Validate a whole batch. Nodes are validated first so edges can be
    checked against the union of accepted node ids in the same batch."""
    nodes: list[Node] = []
    quarantined: list[QuarantineRecord] = []
    for raw in raw_nodes:
        node, problem = validate_node(raw, source)
        if problem is not None:
            quarantined.append(problem)
        else:
            nodes.append(node)  # type: ignore[arg-type]
    known_ids = {n.id for n in nodes}
    edges: list[Edge] = []
    for raw in raw_edges:
        edge, problem = validate_edge(raw, source, known_ids)
        if problem is not None:
            quarantined.append(problem)
        else:
            edges.append(edge)  # type: ignore[arg-type]
    return nodes, edges, quarantined
