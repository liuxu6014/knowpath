_PREREQUISITE_RELATIONS = frozenset({
    "prerequisite",
    "prerequisites",
    "prerequisite_of",
    "prerequisiteof",
    "prereq",
    "prereq_of",
    "prereqof",
})


def relation_name(edge, default="prerequisite"):
    """Return a stable relation name while keeping legacy edges compatible."""

    if isinstance(edge, dict):
        value = edge.get("relation", edge.get("type", edge.get("kind")))
    else:
        value = None
    if value is None or not str(value).strip():
        return default
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def is_prerequisite_edge(edge):
    """Whether an edge participates in learning-path prerequisite semantics.

    Legacy snapshots omitted ``relation``; those edges retain the historical
    prerequisite meaning.  Explicit ``contains``/``related`` edges never
    participate in path locking or ordering.
    """

    return relation_name(edge) in _PREREQUISITE_RELATIONS


def prerequisite_edges(edges):
    """Filter graph edges to the directed prerequisite relation only."""

    return [edge for edge in (edges or []) if is_prerequisite_edge(edge)]


def normalize_graph(nodes, edges):
    """Return a stable graph payload containing only well-formed edges.

    Knowledge extraction is intentionally best effort.  Providers can emit
    duplicate nodes, use ``source``/``target`` instead of ``from``/``to``, or
    mention a node that was not included in the node batch.  The API should
    not persist those malformed relations.  Normalising at the boundary also
    gives the rebuild endpoint a reliable way to tell whether it extracted a
    *usable* graph before replacing a previous snapshot.

    Node identifiers are represented as strings because extracted identifiers
    and imported snapshots otherwise tend to compare differently (``1`` vs
    ``"1"``).  Node fields are preserved for callers that want descriptions or
    concept metadata.
    """
    clean_nodes = []
    node_ids = set()
    for raw in nodes or []:
        if isinstance(raw, dict):
            item = dict(raw)
            raw_id = item.get("id")
            if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
                raw_id = item.get("concept_id")
            if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
                raw_id = item.get("name")
        else:
            item = {"id": raw, "name": raw}
            raw_id = raw
        if raw_id is None:
            continue
        node_id = str(raw_id).strip()
        if not node_id or node_id in node_ids:
            continue
        item["id"] = node_id
        node_ids.add(node_id)
        clean_nodes.append(item)

    casefold_ids = {node_id.casefold(): node_id for node_id in node_ids}
    for item in clean_nodes:
        name = item.get("name")
        if name is not None:
            alias = str(name).strip().casefold()
            if alias:
                casefold_ids.setdefault(alias, item["id"])
    clean_edges = []
    seen_edges = set()
    for raw in edges or []:
        if isinstance(raw, dict):
            source = raw.get("from")
            target = raw.get("to")
            if source is None or (isinstance(source, str) and not source.strip()):
                source = raw.get("source")
            if target is None or (isinstance(target, str) and not target.strip()):
                target = raw.get("target")
            edge = dict(raw)
        else:
            try:
                source, target = raw
            except (TypeError, ValueError):
                continue
            edge = {}
        source = "" if source is None else str(source).strip()
        target = "" if target is None else str(target).strip()
        source = source if source in node_ids else casefold_ids.get(source.casefold(), source)
        target = target if target in node_ids else casefold_ids.get(target.casefold(), target)
        # Keep distinct directed relation types between the same concepts;
        # a section ``contains`` a concept while a separate edge can still
        # express that the same concept is a learning prerequisite.
        key = (source, target, relation_name(edge))
        if not source or not target or source == target:
            continue
        if source not in node_ids or target not in node_ids or key in seen_edges:
            continue
        seen_edges.add(key)
        # Canonicalise the relation endpoints while retaining relation and
        # any provider metadata.
        edge.pop("source", None)
        edge.pop("target", None)
        edge["from"] = source
        edge["to"] = target
        clean_edges.append(edge)
    return clean_nodes, clean_edges


def _detail(code, message, **extra):
    """Build the small, stable diagnostic shape exposed by graph validation."""
    return {
        'code': code,
        'type': code,
        'message': message,
        **extra,
    }


def _node_value(raw):
    """Return the identifier and display name accepted by ``normalize_graph``."""
    if isinstance(raw, dict):
        raw_id = raw.get('id')
        if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
            raw_id = raw.get('concept_id')
        if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
            raw_id = raw.get('name')
        name = raw.get('name')
    else:
        raw_id, name = raw, raw
    if raw_id is None or isinstance(raw_id, (dict, list, tuple, set)):
        return None, name
    value = str(raw_id).strip()
    return (value or None), name


def _edge_values(raw):
    """Read both current and legacy endpoint names without coercing containers."""
    if isinstance(raw, dict):
        source = raw.get('from')
        target = raw.get('to')
        if source is None or (isinstance(source, str) and not source.strip()):
            source = raw.get('source')
        if target is None or (isinstance(target, str) and not target.strip()):
            target = raw.get('target')
    else:
        if not isinstance(raw, (list, tuple)):
            return None, None
        try:
            source, target = raw
        except (TypeError, ValueError):
            return None, None
    values = []
    for value in (source, target):
        if value is None or isinstance(value, (dict, list, tuple, set)):
            values.append(None)
        else:
            text = str(value).strip()
            values.append(text or None)
    return values


def _find_cycle(node_ids, edge_records):
    """Return one deterministic cycle as ``(node_path, edge_indexes)``."""
    adjacency = {node_id: [] for node_id in node_ids}
    for source, target, edge_index in edge_records:
        adjacency[source].append((target, edge_index))

    state = {}
    stack_nodes = []
    stack_edges = []

    def visit(node_id):
        state[node_id] = 1
        stack_nodes.append(node_id)
        for target, edge_index in adjacency[node_id]:
            target_state = state.get(target, 0)
            if target_state == 0:
                stack_edges.append(edge_index)
                found = visit(target)
                if found:
                    return found
                stack_edges.pop()
            elif target_state == 1:
                start = stack_nodes.index(target)
                return (
                    stack_nodes[start:] + [target],
                    stack_edges[start:] + [edge_index],
                )
        stack_nodes.pop()
        state[node_id] = 2
        return None

    for node_id in node_ids:
        if state.get(node_id, 0) == 0:
            found = visit(node_id)
            if found:
                return found
    return None


def validate_graph(nodes, edges):
    """Validate a raw graph and return ``{'valid': bool, 'details': [...]}``.

    Unlike ``normalize_graph``, this function deliberately does not discard
    malformed input.  It is the diagnostic boundary used by the API, while
    internal graph consumers can continue using the legacy boolean helper.
    """
    details = []
    node_ids = []
    aliases = {}
    id_indexes = {}
    name_indexes = {}

    for node_index, raw in enumerate(nodes or []):
        node_id, name = _node_value(raw)
        if node_id is None:
            details.append(_detail(
                'invalid_node',
                f'node at index {node_index} has no usable identifier',
                kind='node', index=node_index, node_index=node_index,
            ))
            continue
        key = node_id.casefold()
        if key in id_indexes:
            details.append(_detail(
                'duplicate_node',
                f"node '{node_id}' duplicates node at index {id_indexes[key][0]}",
                kind='node', index=node_index, node_index=node_index,
                node_id=node_id, duplicate_of=id_indexes[key][0],
                node_indexes=id_indexes[key] + [node_index], field='id',
            ))
            id_indexes[key].append(node_index)
        else:
            id_indexes[key] = [node_index]
            node_ids.append(node_id)
            aliases[key] = node_id

        if name is not None and not isinstance(name, (dict, list, tuple, set)):
            name_text = str(name).strip()
            if name_text:
                name_key = name_text.casefold()
                previous = name_indexes.get(name_key)
                if previous is None:
                    name_indexes[name_key] = (node_index, node_id)
                    aliases.setdefault(name_key, node_id)
                elif previous[1].casefold() != key:
                    details.append(_detail(
                        'duplicate_node',
                        f"node name '{name_text}' duplicates node at index {previous[0]}",
                        kind='node', index=node_index, node_index=node_index,
                        node_id=node_id, name=name_text,
                        duplicate_of=previous[0],
                        node_indexes=[previous[0], node_index], field='name',
                    ))

    edge_records = []
    seen_edges = {}
    for edge_index, raw in enumerate(edges or []):
        source, target = _edge_values(raw)
        if source is None or target is None:
            details.append(_detail(
                'invalid_edge',
                f'edge at index {edge_index} must provide from and to',
                kind='edge', index=edge_index, edge_index=edge_index,
                missing=[name for name, value in (('from', source), ('to', target)) if value is None],
            ))
            continue
        source_id = aliases.get(source.casefold())
        target_id = aliases.get(target.casefold())
        unknown = []
        if source_id is None:
            unknown.append({'endpoint': 'from', 'node_id': source})
        if target_id is None:
            unknown.append({'endpoint': 'to', 'node_id': target})
        if unknown:
            for item in unknown:
                details.append(_detail(
                    'unknown_node',
                    f"edge at index {edge_index} references unknown node '{item['node_id']}'",
                    kind='edge', index=edge_index, edge_index=edge_index,
                    endpoint=item['endpoint'], node_id=item['node_id'],
                ))
            continue
        if source_id == target_id:
            details.append(_detail(
                'self_loop',
                f"edge at index {edge_index} links node '{source_id}' to itself",
                kind='edge', index=edge_index, edge_index=edge_index,
                node_id=source_id, from_id=source_id, to_id=target_id,
            ))
            continue
        relation = ''
        if isinstance(raw, dict):
            relation = raw.get('relation', raw.get('type', raw.get('kind', '')))
        if isinstance(relation, (dict, list, tuple, set)):
            relation = ''
        relation = str(relation).strip().casefold()
        # Two endpoints may carry different directed relation types.  Only
        # the same relation is a duplicate (the common relation-less form
        # naturally uses an empty key).
        key = (source_id.casefold(), target_id.casefold(), relation)
        if key in seen_edges:
            details.append(_detail(
                'duplicate_edge',
                f"edge at index {edge_index} duplicates edge at index {seen_edges[key]}",
                kind='edge', index=edge_index, edge_index=edge_index,
                from_id=source_id, to_id=target_id,
                relation=relation or None, duplicate_of=seen_edges[key],
            ))
            continue
        seen_edges[key] = edge_index
        edge_records.append((source_id, target_id, edge_index))

    cycle = _find_cycle(node_ids, edge_records)
    if cycle:
        cycle_nodes, cycle_edges = cycle
        details.append(_detail(
            'cycle',
            f"graph contains a cycle: {' -> '.join(cycle_nodes)}",
            kind='graph', index=None, node_ids=cycle_nodes, path=cycle_nodes,
            edge_indexes=cycle_edges,
        ))

    # Keep the status decision at the API boundary; callers of this pure
    # helper only need to know whether every reported issue was cleared.
    return {'valid': not details, 'details': details}


def validate_dag(nodes, edges):
    try:
        ids = set(nodes)
    except TypeError:
        return False
    records = []
    edge_list = list(edges or [])
    for index, edge in enumerate(edge_list):
        try:
            if isinstance(edge, dict):
                source, target = edge.get('from', edge.get('source')), edge.get('to', edge.get('target'))
            else:
                if not isinstance(edge, (list, tuple)):
                    return False
                source, target = edge
        except (TypeError, ValueError):
            return False
        if (
            isinstance(source, (dict, list, tuple, set))
            or isinstance(target, (dict, list, tuple, set))
            or source not in ids
            or target not in ids
            or source == target
        ):
            return False
        records.append((source, target, index))
    return _find_cycle(list(ids), records) is None
