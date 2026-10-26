"""Helpers for selecting a safe knowledge graph snapshot.

Snapshots are append-only history.  A provider failure can still leave a
newer row containing no relations (or malformed data), so consumers should
select the newest *usable* DAG rather than blindly reading the newest row.
"""

from .validator import normalize_graph, prerequisite_edges, validate_dag


def _value_keys(value):
    """Return stable lookup keys for graph and relational concept values."""
    if isinstance(value, dict):
        values = (value.get('id'), value.get('concept_id'), value.get('conceptId'),
                  value.get('name'), value.get('title'), value.get('label'))
    else:
        values = (value,)
    keys = set()
    for item in values:
        if item is None:
            continue
        key = str(item).strip().casefold()
        if not key:
            continue
        keys.add(key)
        if key.startswith('concept-'):
            keys.add(key[8:])
        else:
            keys.add('concept-' + key)
    return keys


def _node_identity_parts(node):
    """Split explicit graph identifiers from legacy name-only nodes.

    ``normalize_graph`` gives every node an ``id`` for API stability.  That
    synthesized id is the node name when an importer did not provide a real
    identifier, so treating every ``id`` as authoritative would make legacy
    name snapshots impossible to resolve.  Numeric/prefixed ids (and ids that
    differ from the display name) are considered explicit; equal name/id
    pairs remain a name fallback.
    """
    if isinstance(node, dict):
        raw_id = node.get('id')
        concept_id = node.get('concept_id', node.get('conceptId'))
        names = tuple(node.get(key) for key in ('name', 'title', 'label'))
    else:
        raw_id = node
        concept_id = None
        names = (node,)
    explicit_values = []
    if concept_id is not None and str(concept_id).strip():
        explicit_values.append(concept_id)
    if raw_id is not None and str(raw_id).strip():
        raw_key = str(raw_id).strip().casefold()
        name_keys = {
            str(value).strip().casefold()
            for value in names
            if value is not None and str(value).strip()
        }
        # Numeric/concept-prefixed ids are unambiguous.  For arbitrary ids,
        # only treat a value as explicit when it differs from its display
        # name; ``{"id": "Softmax", "name": "Softmax"}`` is legacy.
        if (
            raw_key.isdigit()
            or raw_key.startswith('concept-')
            or raw_key not in name_keys
        ):
            explicit_values.append(raw_id)
    name_values = [value for value in names if value is not None and str(value).strip()]
    return explicit_values, name_values


def restrict_concepts_to_graph(concepts, graph_nodes):
    """Keep the relational catalog aligned with the active graph snapshot.

    A rebuild may discover a draft term that is not part of the accepted
    snapshot.  Such a term should not silently become a path node or a mastery
    item.  When no graph nodes exist, preserve the catalog for first-run
    flows that create concepts before a snapshot is available.
    """
    concepts = list(concepts or [])
    graph_nodes = list(graph_nodes or [])
    if not graph_nodes:
        return concepts
    # Prefer exact identifiers whenever the snapshot provides them.  Falling
    # back to names for every node makes a stale duplicate such as Concept 48
    # ("Softmax") look active when the graph explicitly contains Concept 2.
    explicit_keys = set()
    fallback_names = []
    node_parts = []
    for node in graph_nodes:
        explicit_values, name_values = _node_identity_parts(node)
        explicit = set().union(*(_value_keys(value) for value in explicit_values)) if explicit_values else set()
        names = set().union(*(_value_keys(value) for value in name_values)) if name_values else set()
        explicit_keys.update(explicit)
        node_parts.append((explicit, names))

    matched_ids = set()
    matched_name_keys = set()
    concept_keys = []
    for concept in concepts:
        identity = {
            'id': getattr(concept, 'concept_id', None),
            'name': getattr(concept, 'name', None),
        }
        id_keys = _value_keys(getattr(concept, 'concept_id', None))
        concept_keys.append((concept, id_keys, _value_keys(identity)))
        if id_keys.intersection(explicit_keys):
            matched_ids.add(getattr(concept, 'concept_id', None))
            matched_name_keys.update(_value_keys(getattr(concept, 'name', None)))

    for explicit, names in node_parts:
        # A node whose explicit id already resolved is authoritative.  Its
        # name must not pull in another relational concept with the same name.
        if explicit and any(
            id_keys.intersection(explicit)
            for _, id_keys, _ in concept_keys
        ):
            continue
        fallback_names.append(names)

    fallback_keys = set().union(*fallback_names) if fallback_names else set()
    if fallback_keys:
        for concept, id_keys, all_keys in concept_keys:
            concept_id = getattr(concept, 'concept_id', None)
            if concept_id in matched_ids or not all_keys.intersection(fallback_keys):
                continue
            # If a name is already represented by an exact graph id, retain
            # that exact concept and ignore same-name stale rows.
            if all_keys.intersection(matched_name_keys):
                continue
            matched_ids.add(concept_id)
            matched_name_keys.update(_value_keys(getattr(concept, 'name', None)))

    return [concept for concept in concepts if getattr(concept, 'concept_id', None) in matched_ids]


async def latest_usable_graph(db, subject_id):
    """Return ``(snapshot, nodes, edges)`` for the newest usable graph.

    Relation-bearing snapshots are preferred because they preserve prerequisite
    semantics.  A valid node-only snapshot remains a fallback for a subject
    that has never had any relations.  Invalid and empty rows are ignored.

    FastAPI/SQLAlchemy adaptation of the Django original: takes an
    ``AsyncSession`` and a subject id instead of an ORM model instance.
    """

    # Import lazily so this pure helper can be imported by core code without
    # requiring the ORM module during utility/tests startup.
    from sqlalchemy import select

    from module_knowledge.entity.do.graph_snapshot_do import KpGraphSnapshot

    fallback = None
    snapshots = (
        await db.execute(
            select(KpGraphSnapshot)
            .where(KpGraphSnapshot.subject_id == subject_id)
            .order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc())
        )
    ).scalars().all()
    for snapshot in snapshots:
        nodes, edges = normalize_graph(snapshot.nodes, snapshot.edges)
        if not nodes:
            continue
        edge_pairs = [(edge['from'], edge['to']) for edge in edges]
        if not validate_dag([node['id'] for node in nodes], edge_pairs):
            continue
        if fallback is None:
            fallback = (snapshot, nodes, edges)
        if prerequisite_edges(edges):
            return snapshot, nodes, edges
    return fallback if fallback is not None else (None, [], [])
