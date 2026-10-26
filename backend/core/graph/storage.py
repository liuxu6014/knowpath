"""Graph persistence with an optional Neo4j backend and SQLite fallback."""
from __future__ import annotations
import os
import re
from typing import Any

from .validator import is_prerequisite_edge, relation_name


class GraphStore:
    """Write/read graphs; Neo4j is used only when configured and available."""
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "").strip()
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        self._driver = None
        if self.uri and self.password:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
                self._driver.verify_connectivity()
            except Exception:
                self._driver = None

    @property
    def backend(self) -> str:
        return "neo4j" if self._driver else "sqlite"

    def save(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        *,
        graph_id: int | None = None,
        subject_id: int | str | None = None,
    ) -> dict[str, Any]:
        if not self._driver:
            return {"backend": "sqlite", "nodes": len(nodes), "edges": len(edges)}
        with self._driver.session() as s:
            s.execute_write(self._write, nodes, edges, graph_id, subject_id)
        return {"backend": "neo4j", "nodes": len(nodes), "edges": len(edges)}

    @staticmethod
    def _write(tx, nodes, edges, graph_id=None, subject_id=None):
        # Concept ids from imported snapshots are only stable inside a
        # learning object.  Namespace the Neo4j key while retaining the raw
        # id as a property for API/debugging clients.
        scope = str(subject_id).strip() if subject_id is not None else "global"

        def node_uuid(raw_id):
            return f"{scope}:{str(raw_id).strip()}"

        def properties(node, *, raw_id):
            props = {
                key: value
                for key, value in node.items()
                if key != "id" and isinstance(value, (str, int, float, bool))
            }
            name = str(node.get("canonical_name") or node.get("name") or raw_id).strip()
            props.setdefault("canonical_name", name)
            props.setdefault("normalized_name", name.casefold())
            props["source_id"] = str(raw_id)
            props["subject_id"] = scope
            if graph_id is not None:
                props["graph_id"] = int(graph_id)
            return props

        # The SQL snapshot is authoritative for the current subject graph.
        # Replace every relationship for this subject so inferred containment
        # edges cannot linger after a rebuild.
        if subject_id is not None:
            tx.run(
                "MATCH (a:Concept {subject_id:$subject_id})-[r:PREREQUISITE_OF]->"
                "(b:Concept {subject_id:$subject_id}) DELETE r",
                subject_id=scope,
            )
            tx.run(
                "MATCH (a:Concept {subject_id:$subject_id})-[r]->"
                "(b:Concept {subject_id:$subject_id}) DELETE r",
                subject_id=scope,
            )
        for n in nodes:
            nid = str(n.get("id", ""))
            if not nid:
                continue
            tx.run(
                "MERGE (n:Concept {uuid:$uuid}) SET n += $props",
                uuid=node_uuid(nid),
                props=properties(n, raw_id=nid),
            )
        for e in edges:
            source = str(e.get("from", e.get("source", ""))).strip()
            target = str(e.get("to", e.get("target", ""))).strip()
            if not source or not target or source == target:
                continue
            relation = "PREREQUISITE_OF" if is_prerequisite_edge(e) else relation_name(e, default="related").upper()
            relation = {
                "RELATED": "RELATED_TO",
                "PREREQUISITES": "PREREQUISITE_OF",
                "PREREQ": "PREREQUISITE_OF",
            }.get(relation, relation)
            # Neo4j relationship labels are identifiers, not parameters.  Keep
            # provider relation names bounded to a safe identifier and fall
            # back to RELATED_TO for malformed/custom values.
            relation = re.sub(r"[^A-Z0-9_]", "_", relation)
            if not relation or not relation[0].isalpha():
                relation = "RELATED_TO"
            tx.run(
                f"MATCH (a:Concept {{uuid:$a}}),(b:Concept {{uuid:$b}}) "
                f"MERGE (a)-[r:{relation}]->(b) SET r += $props",
                a=node_uuid(source),
                b=node_uuid(target),
                props={
                    k: v
                    for k, v in e.items()
                    if k not in ("from", "to", "source", "target")
                    and isinstance(v, (str, int, float, bool))
                },
            )

    def close(self):
        if self._driver:
            self._driver.close()


def graph_store() -> GraphStore:
    return GraphStore()
