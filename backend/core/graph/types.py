from dataclasses import dataclass
@dataclass(frozen=True)
class Edge: source: str; target: str
@dataclass
class Graph: nodes: list[str]; edges: list[Edge]
