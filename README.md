# Graph Data Platform

An enterprise graph data platform: ingest nodes and edges from multiple
sources with fail-closed schema validation and quarantine, resolve duplicate
entities (deterministic + fuzzy matching with a merge/split audit trail),
store every load as an immutable versioned snapshot with time-travel reads,
and query the graph with traversals and quality checks — behind a FastAPI
query/ingest surface.

All data is synthetic and deterministic. No employer code, data, or
proprietary design is used anywhere in this project.

## The enterprise problem

Enterprises hold the same real-world entities in many systems — a customer
in the CRM, a supplier in the ERP, a counterparty in a risk feed — each with
its own spelling, keys, and quality. Answering "who is connected to whom,
and can I trust this graph?" needs four things most graph stores leave to
glue code:

1. **Governed ingestion** — bad records must be quarantined with a reason,
   never silently dropped or silently loaded.
2. **Entity resolution** — the same organization spelled three ways must
   become one node, reversibly, with an audit trail.
3. **Versioned history** — every load is a snapshot; analysts must be able
   to re-run a query against last week's graph.
4. **Trust signals** — orphan nodes, dangling edges, and unresolved
   duplicates must be measurable, not assumed away.

This project implements all four in a small, readable, dependency-light
codebase.

## Architecture

```
sources (CRM / ERP JSON) ──▶ validation ──▶ quarantine (reason-carrying)
                                │                    │
                                ▼                    ▼
                          GraphStore ──▶ snapshots (v1, v2, ...) ──▶ time-travel reads
                                │
                     entity resolution ──▶ merge/split audit
                                │
              traversal (BFS, k-hop, centrality, cycles) + quality report
                                │
                          FastAPI service + CLI
```

See [docs/architecture.md](docs/architecture.md) for the full design,
including the architecture diagram description and trade-offs.

### Components

| Module | Responsibility |
| --- | --- |
| `graph_data_platform/models.py` | Node / Edge / quarantine / lineage dataclasses |
| `graph_data_platform/validation.py` | Fail-closed schema validation, quarantine |
| `graph_data_platform/ingestion.py` | Batch loads, lineage entries, cross-load edge rescue |
| `graph_data_platform/resolution.py` | Deterministic + fuzzy matching, merge/split audit |
| `graph_data_platform/store.py` | Versioned store, immutable snapshots, time travel |
| `graph_data_platform/traversal.py` | BFS shortest path, k-hop, centrality, cycles |
| `graph_data_platform/quality.py` | Orphans, dangling edges, duplicates, health report |
| `graph_data_platform/generator.py` | Deterministic synthetic CRM + ERP sources |
| `graph_data_platform/engine.py` | Pipeline orchestration (load → resolve → quality) |
| `graph_data_platform/api.py` | FastAPI query/ingest surface |
| `graph_data_platform/cli.py` | CLI (`demo`, `load`, `quality`, `path`) |
| `graph_data_platform/demo.py` | End-to-end demo on synthetic data |

## How to run

```bash
python -m venv /tmp/gdp-venv
source /tmp/gdp-venv/bin/activate
pip install -r requirements.txt

# End-to-end demo: ingest CRM + ERP, resolve entities, traverse, report
python -m graph_data_platform.demo

# CLI
python -m graph_data_platform.cli demo
python -m graph_data_platform.cli quality
python -m graph_data_platform.cli path per-ana prod-widget

# API (FastAPI + uvicorn)
uvicorn graph_data_platform.api:app --reload --port 8000
# GET /health, POST /ingest, POST /resolve, GET /nodes, GET /traversal/...
```

Or with Docker:

```bash
docker build -t graph-data-platform .
docker run --rm -p 8000:8000 graph-data-platform
```

## Demo output (deterministic)

```
loaded crm: 16 nodes, 13 edges, 3 quarantined -> snapshot v1
loaded erp: 14 nodes, 9 edges, 0 quarantined -> snapshot v2
entity resolution: 3 duplicate pairs, 3 nodes absorbed -> snapshot v3
shortest path per-ana -> prod-widget: per-ana -> org-acme -> prod-widget
quality v3: 25 nodes, 22 edges, 0 orphans, 0 dangling, 0 duplicates, 4 components — HEALTHY
```

## Key design decisions and trade-offs

- **Fail-closed validation.** An invalid record is quarantined with a
  reason, never coerced. This costs a little ingestion throughput and
  produces quarantine queues that need operating — but silent data loss is
  worse than a visible queue.
- **Immutable snapshots, not a mutable graph with history.** Time travel
  is a plain version lookup, and a bad load is rolled back by reading the
  previous version. The trade-off is memory: every snapshot deep-copies
  the graph. For production scale this becomes copy-on-write or a
  persistent store; the snapshot interface is unchanged by that swap.
- **Fuzzy matching requires corroboration.** A similar name alone never
  merges two entities — a shared attribute (domain, email, city, phone)
  must agree. This deliberately favours precision over recall: a missed
  merge is a quality-report finding, a wrong merge corrupts the graph.
- **Merges are reversible.** Every merge is audited and `split` restores
  the merged-away node. Resolution is a decision with an undo button.
- **Pure-stdlib core.** Validation, resolution, store, traversal, and
  quality use only the standard library. FastAPI is an optional surface
  (the API tests auto-skip without it); the core never depends on it.
- **Deterministic synthetic data.** Seeded generators with deliberate
  overlaps (name variants sharing a domain) and deliberate defects
  (missing name, unknown type, dangling edge) so every code path —
  including quarantine and fuzzy resolution — is exercised by the demo.
- **Cross-load edges are rescued, not rejected.** An edge whose endpoints
  live in the store from an earlier load is accepted; only genuinely
  dangling edges are quarantined.

## What it demonstrates

Multi-source graph ingestion with schema enforcement and quarantine,
deterministic + fuzzy entity resolution with a reversible audit trail,
versioned graph storage with snapshot/time-travel reads, graph traversal
(BFS shortest path, k-hop neighbourhood, degree/betweenness centrality,
cycle detection), graph quality checks (orphans, dangling edges, duplicate
entities, components), load lineage, and a typed FastAPI service — built
the way an enterprise data platform team would build it, at small scale.

## Tests

```bash
python -m pytest -q
```

## Configuration

See `.env.example`. The demo needs no configuration; the variables control
the API host/port and the fuzzy-match threshold.

## License

MIT — see [LICENSE](LICENSE).
