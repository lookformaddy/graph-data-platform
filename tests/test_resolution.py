"""Tests for entity resolution: deterministic + fuzzy matching, merge/split."""

from graph_data_platform.models import Node
from graph_data_platform.resolution import (
    EntityResolver,
    deterministic_key,
    find_duplicates,
    merge_nodes,
    name_similarity,
    normalize_name,
)


def _node(node_id, name, **props):
    return Node(id=node_id, type="organization",
                properties={"name": name, **props}, source="crm")


def test_normalize_name_drops_noise_tokens():
    assert normalize_name("Acme Corporation") == "acme"
    assert normalize_name("Globex, Inc.") == "globex"
    assert normalize_name("Umbrella Co") == "umbrella"


def test_deterministic_key_matches_name_variants():
    a = _node("o1", "Acme Corp", domain="acme.example.com")
    b = _node("o2", "Acme Corporation", domain="acme.example.com")
    assert deterministic_key(a) == deterministic_key(b)


def test_deterministic_key_differs_on_domain():
    a = _node("o1", "Acme Corp", domain="acme.example.com")
    b = _node("o2", "Acme Corp", domain="other.example.com")
    assert deterministic_key(a) != deterministic_key(b)


def test_name_similarity_bounds():
    assert name_similarity("Acme Corp", "Acme Corporation") > 0.9
    assert name_similarity("Acme", "Globex") < 0.5


def test_fuzzy_match_requires_shared_attribute():
    a = _node("o1", "Acme Corp", domain="acme.example.com")
    b = _node("o2", "Acme Corporation", domain="different.example.com")
    # Similar names but no shared attribute -> no pair (deterministic keys
    # also differ, so the fuzzy gate is what blocks it).
    assert find_duplicates([a, b]) == []


def test_fuzzy_match_with_shared_city():
    a = Node(id="o1", type="organization",
             properties={"name": "Acme Corp", "domain": "acme.example.com",
                         "city": "Springfield"}, source="crm")
    b = Node(id="o2", type="organization",
             properties={"name": "Acme Corporation", "domain": "other.example.com",
                         "city": "Springfield"}, source="erp")
    # Different domains, so the deterministic keys differ; the shared city
    # is what corroborates the fuzzy name match.
    pairs = find_duplicates([a, b])
    assert len(pairs) == 1 and pairs[0]["method"] == "fuzzy"


def test_resolver_merges_and_audits():
    nodes = [
        _node("o1", "Acme Corp", domain="acme.example.com"),
        _node("o2", "Acme Corporation", domain="acme.example.com"),
        _node("o3", "Globex Inc", domain="globex.example.com"),
    ]
    resolver = EntityResolver()
    resolved, pairs = resolver.resolve(nodes)
    assert len(resolved) == 2
    assert len(pairs) == 1 and pairs[0]["method"] == "deterministic"
    assert len(resolver.audit) == 1
    assert resolver.audit[0].action == "merge"
    assert resolver.audit[0].canonical_id == "o1"


def test_merge_preserves_canonical_properties():
    canonical = _node("o1", "Acme Corp", domain="acme.example.com", city="Springfield")
    duplicate = _node("o2", "Acme Corporation", domain="acme.example.com", founded="1990")
    merged = merge_nodes(canonical, duplicate)
    assert merged.id == "o1"
    assert merged.properties["city"] == "Springfield"
    assert merged.properties["founded"] == "1990"
    assert "o2" in merged.properties["_merged_from"]


def test_split_restores_merged_node():
    nodes = [
        _node("o1", "Acme Corp", domain="acme.example.com"),
        _node("o2", "Acme Corporation", domain="acme.example.com"),
    ]
    resolver = EntityResolver()
    resolver.resolve(nodes)
    restored = resolver.split("o1", "o2")
    assert restored is not None and restored.id == "o2"
    assert resolver.audit[-1].action == "split"
    assert resolver.split("o1", "o2") is None  # already split: nothing to undo
