"""Traversal queries over a graph snapshot: BFS shortest path, k-hop
neighbourhood, degree centrality, betweenness centrality (Brandes), and
cycle detection. All pure stdlib; all queries run against an immutable
snapshot so results are reproducible for a given version.
"""

from __future__ import annotations

from collections import defaultdict, deque

from graph_data_platform.models import Edge, Node
from graph_data_platform.store import Snapshot


def adjacency(snapshot: Snapshot, directed: bool = True) -> dict[str, set[str]]:
    """Node id -> set of neighbour ids. Undirected mode adds reverse edges."""
    adj: dict[str, set[str]] = defaultdict(set)
    for node_id in snapshot.nodes:
        adj.setdefault(node_id, set())
    for edge in snapshot.edges.values():
        adj[edge.source_id].add(edge.target_id)
        if not directed:
            adj[edge.target_id].add(edge.source_id)
    return dict(adj)


def shortest_path(snapshot: Snapshot, start: str, goal: str) -> list[str] | None:
    """BFS shortest path (fewest hops). Returns node ids, or None if unreachable."""
    if start not in snapshot.nodes or goal not in snapshot.nodes:
        return None
    if start == goal:
        return [start]
    adj = adjacency(snapshot)
    prev: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in sorted(adj.get(current, set())):
            if neighbour not in prev:
                prev[neighbour] = current
                if neighbour == goal:
                    path = [goal]
                    while prev[path[-1]] is not None:
                        path.append(str(prev[path[-1]]))
                    return list(reversed(path))
                queue.append(neighbour)
    return None


def k_hop_neighbourhood(snapshot: Snapshot, start: str, hops: int) -> dict[int, list[str]]:
    """Nodes reachable within ``hops`` steps, grouped by hop distance."""
    if start not in snapshot.nodes or hops < 1:
        return {}
    adj = adjacency(snapshot, directed=False)
    seen = {start}
    frontier = {start}
    result: dict[int, list[str]] = {}
    for depth in range(1, hops + 1):
        nxt: set[str] = set()
        for node_id in frontier:
            nxt |= adj.get(node_id, set()) - seen
        if not nxt:
            break
        result[depth] = sorted(nxt)
        seen |= nxt
        frontier = nxt
    return result


def degree_centrality(snapshot: Snapshot) -> dict[str, float]:
    """Normalized degree centrality: degree / (n - 1)."""
    n = len(snapshot.nodes)
    if n <= 1:
        return {node_id: 0.0 for node_id in snapshot.nodes}
    adj = adjacency(snapshot, directed=False)
    return {node_id: len(adj.get(node_id, set())) / (n - 1) for node_id in snapshot.nodes}


def betweenness_centrality(snapshot: Snapshot) -> dict[str, float]:
    """Brandes' algorithm on the undirected graph, normalized to [0, 1]."""
    adj = adjacency(snapshot, directed=False)
    nodes = sorted(snapshot.nodes)
    centrality = {v: 0.0 for v in nodes}
    for source in nodes:
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in nodes}
        sigma = {v: 0 for v in nodes}
        sigma[source] = 1
        dist = {v: -1 for v in nodes}
        dist[source] = 0
        queue: deque[str] = deque([source])
        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in sorted(adj.get(v, set())):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != source:
                centrality[w] += delta[w]
    n = len(nodes)
    if n > 2:
        norm = 1.0 / ((n - 1) * (n - 2) / 2)
        centrality = {k: round(v * norm / 2, 4) for k, v in centrality.items()}
    return centrality


def find_cycles(snapshot: Snapshot, max_cycles: int = 10) -> list[list[str]]:
    """Directed cycles via DFS with a recursion stack. Returns up to
    ``max_cycles`` cycles (each a list of node ids, start repeated at end)."""
    adj = adjacency(snapshot, directed=True)
    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()

    def dfs(node_id: str) -> None:
        if len(cycles) >= max_cycles:
            return
        visited.add(node_id)
        stack.append(node_id)
        on_stack.add(node_id)
        for neighbour in sorted(adj.get(node_id, set())):
            if neighbour in on_stack:
                idx = stack.index(neighbour)
                cycles.append(stack[idx:] + [neighbour])
                if len(cycles) >= max_cycles:
                    return
            elif neighbour not in visited:
                dfs(neighbour)
                if len(cycles) >= max_cycles:
                    return
        stack.pop()
        on_stack.discard(node_id)

    for node_id in sorted(snapshot.nodes):
        if node_id not in visited:
            dfs(node_id)
        if len(cycles) >= max_cycles:
            break
    return cycles


def connected_components(snapshot: Snapshot) -> list[list[str]]:
    """Weakly connected components (undirected reachability)."""
    adj = adjacency(snapshot, directed=False)
    seen: set[str] = set()
    components: list[list[str]] = []
    for node_id in sorted(snapshot.nodes):
        if node_id in seen:
            continue
        component: set[str] = set()
        queue: deque[str] = deque([node_id])
        seen.add(node_id)
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbour in adj.get(current, set()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        components.append(sorted(component))
    return components
