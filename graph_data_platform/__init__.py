"""Graph Data Platform — enterprise graph data platform.

Ingestion of nodes/edges from multiple sources with schema validation and
quarantine, entity resolution, a versioned graph store with snapshot /
time-travel reads, traversal queries, graph quality checks, lineage of graph
loads, and a FastAPI query/ingest surface.

All data in this package is synthetic or generic sample data. No employer
code, data, or proprietary design is used.
"""

from graph_data_platform.models import Edge, Node, QuarantineRecord
from graph_data_platform.store import GraphStore

__all__ = ["Edge", "GraphStore", "Node", "QuarantineRecord"]
__version__ = "0.1.0"
