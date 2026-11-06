"""Entity resolution: deterministic + fuzzy matching with merge/split audit.

Two records are the same real-world entity when they share a deterministic
key (normalized name + type + a stable identifier such as email or domain),
or when a fuzzy name match is corroborated by a shared attribute. Merges are
recorded in an audit trail, and every merge can be undone with ``split`` —
resolution is a reversible decision, not a destructive rewrite.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from graph_data_platform.models import Node, ResolutionAudit

# Name tokens that carry no identity (legal suffixes, generic words).
_NOISE_TOKENS = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "the", "group"}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, drop noise tokens, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    tokens = [t for t in cleaned.split() if t not in _NOISE_TOKENS]
    return " ".join(tokens)


def deterministic_key(node: Node) -> str:
    """Stable identity key: type + normalized name + strongest identifier.

    The strongest identifier is the first present of email, domain, then
    external_id. Two nodes with equal keys are the same entity by rule.
    """
    props = node.properties
    identifier = (
        str(props.get("email", "")).lower()
        or str(props.get("domain", "")).lower()
        or str(props.get("external_id", "")).lower()
    )
    return f"{node.type}|{normalize_name(node.name)}|{identifier}"


def name_similarity(a: str, b: str) -> float:
    """Fuzzy name similarity in [0, 1] via difflib on normalized names."""
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def _shared_attribute(a: Node, b: Node) -> bool:
    """True when the two nodes share a corroborating attribute value."""
    for key in ("email", "domain", "external_id", "city", "phone"):
        va, vb = a.properties.get(key), b.properties.get(key)
        if va and vb and str(va).lower() == str(vb).lower():
            return True
    return False


def find_duplicates(nodes: list[Node], fuzzy_threshold: float = 0.85) -> list[dict[str, object]]:
    """Find candidate duplicate pairs.

    Returns a list of ``{"a": id, "b": id, "method": ..., "score": ...}``
    dicts. Deterministic matches (identical key) score 1.0; fuzzy matches
    require name similarity >= threshold *and* a shared attribute, so a
    similar name alone never merges two entities.
    """
    pairs: list[dict[str, object]] = []
    by_key: dict[str, Node] = {}
    for node in nodes:
        key = deterministic_key(node)
        if key in by_key:
            pairs.append({"a": by_key[key].id, "b": node.id, "method": "deterministic", "score": 1.0})
        else:
            by_key[key] = node
    seen = {(str(p["a"]), str(p["b"])) for p in pairs}
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if a.type != b.type or (a.id, b.id) in seen or (b.id, a.id) in seen:
                continue
            score = name_similarity(a.name, b.name)
            if score >= fuzzy_threshold and _shared_attribute(a, b):
                pairs.append({"a": a.id, "b": b.id, "method": "fuzzy", "score": round(score, 3)})
    return pairs


def merge_nodes(canonical: Node, duplicate: Node) -> Node:
    """Merge ``duplicate`` into ``canonical``: properties union (canonical
    wins on conflict), sources recorded, duplicate id kept for audit."""
    merged_props = dict(duplicate.properties)
    merged_props.update(canonical.properties)
    merged_props["_merged_from"] = sorted(
        set(str(duplicate.properties.get("_merged_from", "")).split(",") if duplicate.properties.get("_merged_from") else [])
        | {duplicate.id}
        | set(str(canonical.properties.get("_merged_from", "")).split(",") if canonical.properties.get("_merged_from") else [])
        - {""}
    )
    return Node(
        id=canonical.id, type=canonical.type,
        properties={k: (", ".join(v) if k == "_merged_from" else v) for k, v in merged_props.items()},
        source=f"{canonical.source}+{duplicate.source}",
    )


class EntityResolver:
    """Stateful resolver over a node list, with a full audit trail."""

    def __init__(self, fuzzy_threshold: float = 0.85) -> None:
        self.fuzzy_threshold = fuzzy_threshold
        self.audit: list[ResolutionAudit] = []
        # canonical_id -> list of merged-away node snapshots (for split)
        self._merge_history: dict[str, list[Node]] = {}

    def resolve(self, nodes: list[Node]) -> tuple[list[Node], list[dict[str, object]]]:
        """Resolve duplicates in ``nodes``. Returns (resolved nodes, pairs found)."""
        pairs = find_duplicates(nodes, self.fuzzy_threshold)
        by_id = {n.id: n for n in nodes}
        absorbed: set[str] = set()
        resolved: list[Node] = []
        for pair in pairs:
            a_id, b_id = str(pair["a"]), str(pair["b"])
            if a_id in absorbed or b_id in absorbed:
                continue
            canonical, duplicate = by_id[a_id], by_id[b_id]
            merged = merge_nodes(canonical, duplicate)
            self._merge_history.setdefault(canonical.id, []).append(duplicate)
            self.audit.append(ResolutionAudit(
                action="merge", canonical_id=canonical.id, merged_ids=[duplicate.id],
                method=str(pair["method"]), score=float(pair["score"]),
                reason=f"{pair['method']} match (score {pair['score']}) between {a_id} and {b_id}",
            ))
            by_id[canonical.id] = merged
            absorbed.add(b_id)
        for node in nodes:
            if node.id not in absorbed:
                resolved.append(by_id[node.id])
        return resolved, pairs

    def split(self, canonical_id: str, merged_id: str) -> Node | None:
        """Undo one merge: restore the merged-away node. Returns it, or None
        when no such merge is recorded."""
        history = self._merge_history.get(canonical_id, [])
        for i, node in enumerate(history):
            if node.id == merged_id:
                restored = history.pop(i)
                self.audit.append(ResolutionAudit(
                    action="split", canonical_id=canonical_id, merged_ids=[merged_id],
                    method="manual", score=None,
                    reason=f"manual split of {merged_id} from {canonical_id}",
                ))
                return restored
        return None
