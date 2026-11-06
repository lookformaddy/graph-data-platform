# Architecture — Graph Data Platform

## Overview

The platform is a layered, dependency-light Python service. The core
(validation → ingestion → resolution → store → traversal / quality) is
pure stdlib; FastAPI and the CLI are thin surfaces over the same
`GraphPipeline` object.

## Architecture diagram (description)

```
┌─────────────────────────────┐   ┌─────────────────────────────┐
│  Source: CRM (JSON)         │   │  Source: ERP (JSON)         │
│  people, orgs, accounts,    │   │  orgs (name variants),      │
│  works_at / reports_to /    │   │  products, locations,       │
│  owns edges                 │   │  supplies / located_in      │
└──────────────┬──────────────┘   └──────────────┬──────────────┘
               │                                 │
               ▼                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  validation.py — fail-closed schema checks                       │
│  • node type in {person, organization, product, location,        │
│    account}; required properties present                         │
│  • edge type known; endpoints exist; no forbidden self-loops     │
│  • failures → QuarantineRecord (record + reason + source)        │
└──────────────────────────────────────────────────────────────────┘
               │ accepted records            │ quarantined records
               ▼                             ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│  ingestion.py — Ingestor    │   │  Quarantine queue           │
│  • upserts nodes (property  │   │  (in-memory list; lineage   │
│    merge on conflict)       │   │  records the counts)        │
│  • rescues cross-load edges │   └─────────────────────────────┘
│    whose endpoints are      │
│    already in the store     │
│  • commits a snapshot +     │
│    writes a LoadRecord      │
│    (lineage: source, counts,│
│    checksum, timestamp)     │
└──────────────┬──────────────┘
               ▼
┌──────────────────────────────────────────────────────────────────┐
│  store.py — GraphStore: working graph + immutable snapshots      │
│  • commit() deep-copies the working graph into Snapshot vN       │
│  • snapshot(version) = time-travel read; version 0 = empty       │
│  • history is append-only; rollback = read the previous version  │
└──────────────┬──────────────┘
               ▼
┌──────────────────────────────────────────────────────────────────┐
│  resolution.py — EntityResolver                                  │
│  • deterministic key: type + normalized name + email/domain/     │
│    external_id → exact matches score 1.0                         │
│  • fuzzy: difflib name similarity ≥ threshold AND a shared       │
│    attribute (email/domain/city/phone) → candidate pair          │
│  • merge: property union, canonical wins; audit entry recorded   │
│  • split: restores a merged-away node from merge history         │
│  • pipeline rewrites edges that pointed at absorbed duplicates   │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│  traversal.py               │   │  quality.py                 │
│  • BFS shortest path        │   │  • orphan nodes (degree 0)  │
│  • k-hop neighbourhood      │   │  • dangling edges           │
│  • degree centrality        │   │  • duplicate entities       │
│  • betweenness (Brandes)    │   │  • components, type counts  │
│  • directed cycle detection │   │  • HEALTHY / WARNING /      │
│  • connected components     │   │    CRITICAL report          │
└──────────────┬──────────────┘   └──────────────┬──────────────┘
               │                                 │
               ▼                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  engine.py — GraphPipeline: load_source → resolve_entities →     │
│  quality / lineage / quarantine / summary                        │
└──────────────────────────────────────────────────────────────────┘
               │                                 │
               ▼                                 ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│  api.py — FastAPI           │   │  cli.py — CLI               │
│  /health /ingest /resolve   │   │  demo / load / quality /    │
│  /nodes /traversal/*        │   │  path                       │
│  /quality /snapshots/*      │   └─────────────────────────────┘
│  /lineage /demo-seed        │
└─────────────────────────────┘
```

## Data flow

1. **Load.** `Ingestor.load(source, nodes, edges)` validates the batch
   (nodes first, so edges can be checked against the batch), upserts the
   accepted records, commits a snapshot, and writes a lineage entry. The
   snapshot version is the load's identity: every later read can name it.
2. **Resolve.** `GraphPipeline.resolve_entities()` finds duplicate pairs,
   merges them (property union, canonical id kept), rewrites edges that
   referenced absorbed ids, and commits a new snapshot. The audit trail
   records method, score, and reason per merge; `split` undoes one.
3. **Query.** Traversal and quality functions take a `Snapshot`, never
   the mutable store, so results are reproducible for a version.
4. **Observe.** `quality()` and `lineage()` are the operator's views:
   health status, orphan/dangling/duplicate counts, and per-load lineage.

## Design decisions

- **Snapshots are deep copies.** Simple, obviously correct, and fast
  enough at this scale. The documented production evolution is
  copy-on-write / persistent storage behind the same `snapshot(version)`
  interface.
- **Validation before storage, always.** No code path writes an
  unvalidated record. The quarantine queue is first-class output, not a
  log line.
- **Fuzzy matching is corroborated.** Name similarity alone never
  merges; a shared attribute must agree. Precision over recall, by
  design — a wrong merge is harder to detect than a missed one.
- **Traversal runs on snapshots.** Queries never observe a half-loaded
  graph, and the same version always yields the same answer.
- **Stdlib core, optional FastAPI.** The platform's logic has no
  third-party runtime dependency; the API layer degrades gracefully
  (`HAS_FASTAPI`) and its tests auto-skip without FastAPI.

## Failure modes and handling

| Failure | Handling |
| --- | --- |
| Invalid node/edge record | Quarantined with reason; load continues |
| Dangling edge (endpoint missing) | Quarantined; rescued only if the endpoint exists in the store from an earlier load |
| Duplicate entities across sources | Merged with audit; reversible via split |
| Bad load committed | Read the previous snapshot version (time travel); no data is rewritten |
| Unknown snapshot version | `ValueError` in the core, HTTP 404 in the API |
| Unknown node in a traversal | `None` (path) / empty result / HTTP 404 |

## Scaling notes (what changes at production scale)

- Replace in-memory dicts with a persistent graph store (e.g. a graph
  database or Parquet-backed adjacency) behind the same snapshot API.
- Replace deep-copy snapshots with copy-on-write or delta snapshots.
- Move the quarantine queue and lineage log to durable storage (table /
  object store) with an operator UI.
- Add blocking keys / indexes so duplicate detection is not O(n²).
- Add auth, per-tenant isolation, and rate limits to the API surface.
