from .validator import is_prerequisite_edge


def topological_order(nodes, edges, mastery=None, include_mastered=True):
    """Return a deterministic prerequisite-first order.

    ``edges`` use the graph convention ``(prerequisite, dependent)``. Nodes
    are sorted by mastery (weakest first) whenever several are available.
    """
    items = list(dict.fromkeys(nodes or []))
    rank = mastery or {}
    deps = {n: set() for n in items}
    children = {n: set() for n in items}
    for edge in edges or []:
        if isinstance(edge, dict):
            if not is_prerequisite_edge(edge):
                continue
            a, b = edge.get("from", edge.get("source")), edge.get("to", edge.get("target"))
        else:
            try: a, b = edge
            except (TypeError, ValueError): continue
        if a in deps and b in deps and a != b:
            deps[b].add(a); children[a].add(b)
    # Break ties by mastery, then stable string representation.
    ready = [n for n in items if not deps[n]]
    out = []
    while ready:
        ready.sort(key=lambda n: (float(rank.get(n, 0)), str(n)))
        n = ready.pop(0); out.append(n)
        for child in children[n]:
            deps[child].discard(n)
            if not deps[child]: ready.append(child)
    # Cycles should be rejected by callers; retain deterministic remainder for
    # defensive use by legacy callers.
    if len(out) != len(items):
        out.extend(n for n in items if n not in out)
    return out


def plan(nodes, edges, mastered=()):
    mastered=set(mastered); deps={n:set() for n in nodes}
    for edge in edges:
        if isinstance(edge, dict):
            if not is_prerequisite_edge(edge):
                continue
            a, b = edge.get("from", edge.get("source")), edge.get("to", edge.get("target"))
        else:
            try: a, b = edge
            except (TypeError, ValueError): continue
        if b in deps: deps[b].add(a)
    return [n for n in nodes if n not in mastered and deps[n] <= mastered]
