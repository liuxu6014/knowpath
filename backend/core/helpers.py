"""Small pure helpers shared across the KnowPath domain modules."""


def bool_value(value, default=False):
    """Normalize loosely-typed booleans accepted by the original API."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value) if value is not None else default


def safe_float(value, default=0.0):
    """Return a finite float, falling back to ``default``."""
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if value != value or abs(value) == float('inf'):
        return default
    return value


def path_node_concept_id(node):
    """Resolve the concept identity used by current and legacy path nodes."""
    if not isinstance(node, dict):
        return None
    value = node.get('concept_id', node.get('conceptId'))
    if value is not None and str(value).strip():
        return value
    raw_id = str(node.get('id', '')).strip()
    if raw_id.casefold().startswith('concept-'):
        return raw_id[8:]
    return raw_id or None


def graph_key(value):
    """Return the whitespace-collapsed key accepted by graph identity lookups."""
    import re

    return re.sub(r'\s+', '-', str(value or '').strip().casefold())


def text_fragments(value, limit=4):
    """Split source text into short teaching fragments."""
    import re

    text = str(value or '').strip()
    if not text:
        return []
    parts = [part.strip(' -\t') for part in re.split(r'\r?\n+|(?<=[。！？!?；;.])\s*', text) if part.strip()]
    return parts[:max(1, int(limit))]
