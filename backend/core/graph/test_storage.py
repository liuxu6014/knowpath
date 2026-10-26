import os
from .storage import GraphStore


def test_without_neo4j_uses_sqlite_fallback():
    old = (os.environ.pop("NEO4J_URI", None), os.environ.pop("NEO4J_PASSWORD", None))
    try:
        store = GraphStore()
        assert store.backend == "sqlite"
        assert store.save([{"id": "a"}], [{"from": "a", "to": "b"}])["backend"] == "sqlite"
    finally:
        if old[0] is not None: os.environ["NEO4J_URI"] = old[0]
        if old[1] is not None: os.environ["NEO4J_PASSWORD"] = old[1]


class _Tx:
    def __init__(self):
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))


def test_neo4j_write_uses_document_schema_and_subject_scoped_keys():
    tx_a, tx_b = _Tx(), _Tx()
    nodes = [{"id": "same", "name": "Shared concept"}]
    edges = []

    GraphStore._write(tx_a, nodes, edges, graph_id=1, subject_id=10)
    GraphStore._write(tx_b, nodes, edges, graph_id=2, subject_id=20)

    node_call_a = next(call for call in tx_a.calls if "MERGE (n:Concept" in call[0])
    node_call_b = next(call for call in tx_b.calls if "MERGE (n:Concept" in call[0])
    assert node_call_a[1]["uuid"] == "10:same"
    assert node_call_b[1]["uuid"] == "20:same"
    assert "PREREQUISITE_OF" in " ".join(query for query, _ in tx_a.calls)


def test_neo4j_write_persists_prerequisite_of_edges():
    tx = _Tx()
    GraphStore._write(
        tx,
        [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
        [{"from": "a", "to": "b", "confidence": 0.9}],
        subject_id=7,
    )
    edge_call = next(call for call in tx.calls if "PREREQUISITE_OF" in call[0] and "MERGE (a" in call[0])
    assert edge_call[1]["a"] == "7:a"
    assert edge_call[1]["b"] == "7:b"
    assert edge_call[1]["props"]["confidence"] == 0.9
