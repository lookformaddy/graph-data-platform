"""Deterministic synthetic data generator.

Two overlapping sources describe the same generic enterprise world from
different angles, the way real CRM and ERP feeds do:

* ``crm`` — people and organizations, with employment edges.
* ``erp`` — organizations (with name variants of the CRM ones), products,
  locations, and supply edges.

Overlaps are deliberate: "Acme Corp" in CRM vs "Acme Corporation" in ERP
share a domain, so fuzzy resolution must find them. A few records are
intentionally invalid (missing name, unknown type, dangling edge) so the
quarantine path is exercised. Everything is seeded and deterministic.
"""

from __future__ import annotations

import random
from typing import Any

ORGS = [
    ("org-acme", "Acme Corp", "acme.example.com", "Springfield"),
    ("org-globex", "Globex Inc", "globex.example.com", "Shelbyville"),
    ("org-initech", "Initech LLC", "initech.example.com", "Capital City"),
    ("org-hooli", "Hooli", "hooli.example.com", "Palo Alto"),
    ("org-umbrella", "Umbrella Co", "umbrella.example.com", "Raccoon City"),
]

ORG_VARIANTS = {
    "org-acme": ("org-acme-erp", "Acme Corporation"),
    "org-globex": ("org-globex-erp", "Globex Corporation"),
    "org-initech": ("org-initech-erp", "Initech"),
}

PEOPLE = [
    ("per-ana", "Ana Ruiz", "ana.ruiz@acme.example.com", "org-acme"),
    ("per-ben", "Ben Okafor", "ben.okafor@globex.example.com", "org-globex"),
    ("per-cleo", "Cleo Tanaka", "cleo.tanaka@initech.example.com", "org-initech"),
    ("per-dan", "Dan Petrov", "dan.petrov@hooli.example.com", "org-hooli"),
    ("per-elsa", "Elsa Novak", "elsa.novak@umbrella.example.com", "org-umbrella"),
    ("per-finn", "Finn Gallagher", "finn.gallagher@acme.example.com", "org-acme"),
]

PRODUCTS = [
    ("prod-widget", "Widget Pro", "org-acme"),
    ("prod-gadget", "Gadget Max", "org-globex"),
    ("prod-doodad", "Doodad Lite", "org-initech"),
    ("prod-gizmo", "Gizmo Ultra", "org-hooli"),
]


def _node(node_id: str, node_type: str, props: dict[str, Any], source: str) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "properties": props, "source": source}


def _edge(edge_id: str, edge_type: str, source_id: str, target_id: str, source: str) -> dict[str, Any]:
    return {"id": edge_id, "type": edge_type, "source_id": source_id,
            "target_id": target_id, "properties": {}, "source": source}


def generate_source_crm(seed: int = 42) -> dict[str, list[dict[str, Any]]]:
    """CRM feed: people, organizations, employment + reporting edges."""
    rng = random.Random(seed)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for org_id, name, domain, city in ORGS:
        nodes.append(_node(org_id, "organization",
                           {"name": name, "domain": domain, "city": city}, "crm"))
    for person_id, name, email, org_id in PEOPLE:
        nodes.append(_node(person_id, "person",
                           {"name": name, "email": email, "city": "Springfield"}, "crm"))
        edges.append(_edge(f"e-{person_id}-works", "works_at", person_id, org_id, "crm"))
    edges.append(_edge("e-finn-reports", "reports_to", "per-finn", "per-ana", "crm"))
    edges.append(_edge("e-ben-reports", "reports_to", "per-ben", "per-ana", "crm"))
    # One account per org, owned by the org.
    for org_id, name, _, _ in ORGS:
        acc = f"acc-{org_id[4:]}"
        nodes.append(_node(acc, "account", {"name": f"{name} billing account"}, "crm"))
        edges.append(_edge(f"e-{acc}-owns", "owns", org_id, acc, "crm"))
    # Deliberately invalid records (quarantine path).
    nodes.append({"id": "per-bad", "type": "person", "properties": {}, "source": "crm"})
    nodes.append({"id": "bad-type", "type": "spaceship", "properties": {"name": "X"}, "source": "crm"})
    edges.append(_edge("e-dangling", "works_at", "per-ghost", "org-acme", "crm"))
    rng.shuffle(nodes)
    rng.shuffle(edges)
    return {"nodes": nodes, "edges": edges}


def generate_source_erp(seed: int = 42) -> dict[str, list[dict[str, Any]]]:
    """ERP feed: organizations (name variants), products, locations, supply edges."""
    rng = random.Random(seed + 1)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for org_id, name, domain, city in ORGS:
        erp_id, variant = ORG_VARIANTS.get(org_id, (org_id, name))
        nodes.append(_node(erp_id, "organization",
                           {"name": variant, "domain": domain, "city": city}, "erp"))
    for prod_id, name, org_id in PRODUCTS:
        nodes.append(_node(prod_id, "product", {"name": name, "sku": prod_id.upper()}, "erp"))
        erp_org = ORG_VARIANTS.get(org_id, (org_id, ""))[0]
        edges.append(_edge(f"e-{prod_id}-supplies", "supplies", erp_org, prod_id, "erp"))
    for i, (_, _, _, city) in enumerate(ORGS):
        loc_id = f"loc-{i}"
        nodes.append(_node(loc_id, "location", {"name": f"{city} depot", "city": city}, "erp"))
    # Locations host the orgs that sit in the same city.
    for org_id, _, _, city in ORGS:
        erp_org = ORG_VARIANTS.get(org_id, (org_id, ""))[0]
        loc_id = f"loc-{[c for _, _, _, c in ORGS].index(city)}"
        edges.append(_edge(f"e-{erp_org}-located", "located_in", erp_org, loc_id, "erp"))
    rng.shuffle(nodes)
    rng.shuffle(edges)
    return {"nodes": nodes, "edges": edges}


def generate_all(seed: int = 42) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Both sources, keyed by source name."""
    return {"crm": generate_source_crm(seed), "erp": generate_source_erp(seed)}
