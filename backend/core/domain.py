"""Shared domain helpers for the KnowPath controllers.

Port of the small cross-cutting functions that lived in Django's
``config/views.py`` and ``apps/analytics/services.py``: subject/resource
access checks, learning-event telemetry, audit logging, and graph-scoped
concept resolution.  Everything here is async SQLAlchemy 2.0.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.graph.resolver import latest_usable_graph, restrict_concepts_to_graph
from core.graph.validator import is_prerequisite_edge
from module_analytics.entity.do.learning_report_do import KpLearningEvent
from module_knowledge.entity.do.concept_do import KpConcept
from module_subject.entity.do.subject_do import KpSubject
from module_system.entity.do.system_do import KpAuditLog

MAX_EVENT_DURATION_SEC = 24 * 60 * 60


def iso_time(value):
    """Format a stored datetime for the JSON wire contract."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except (AttributeError, ValueError):
        return None


def normalize_duration(value, *, default=0):
    """Normalize a client supplied duration without accepting negative/huge values."""
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        raise ValueError('duration_sec must be a non-negative integer')
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('duration_sec must be a non-negative integer')
    if not 0 <= value <= MAX_EVENT_DURATION_SEC:
        raise ValueError('duration_sec must be between 0 and 86400')
    return value


def can_access_subject(current_user, subject) -> bool:
    """Django's ``owner`` visibility rule, mapped onto RuoYi admin convention."""
    if subject is None:
        return False
    from core.api import is_admin

    return bool(current_user and (is_admin(current_user) or subject.user_id == getattr(current_user, 'user_id', None) or subject.user_id == getattr(getattr(current_user, 'user', None), 'user_id', None)))


def subject_owner_id(current_user):
    """Return the resolved user id for a current-user model, or ``None``."""
    from core.api import user_id_of

    return user_id_of(current_user)


async def subject_for(db: AsyncSession, subject_id):
    """Fetch a subject by primary key, tolerating malformed identifiers."""
    try:
        subject_id = int(subject_id)
    except (TypeError, ValueError):
        return None
    return (
        await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
    ).scalars().first()


async def active_concepts(db: AsyncSession, subject_id, graph_nodes=None):
    """Return the relational catalog aligned with the active graph snapshot."""
    concepts = (
        await db.execute(
            select(KpConcept).where(KpConcept.subject_id == subject_id).order_by(KpConcept.concept_id)
        )
    ).scalars().all()
    if graph_nodes is None:
        _, graph_nodes, _ = await latest_usable_graph(db, subject_id)
    return restrict_concepts_to_graph(concepts, graph_nodes)


async def subject_graph(db: AsyncSession, subject_id):
    """Resolve snapshot node identifiers to relational concept ids + edges."""
    _, graph_nodes, snapshot_edges = await latest_usable_graph(db, subject_id)
    concepts = await active_concepts(db, subject_id, graph_nodes)
    by_key = {}
    for concept in concepts:
        variants = {
            str(concept.concept_id).strip().lower(),
            f'concept-{concept.concept_id}'.lower(),
            str(concept.name).strip().lower(),
            re.sub(r'\s+', '-', str(concept.name).strip().lower()),
        }
        for variant in variants:
            if variant:
                by_key.setdefault(variant, concept.concept_id)
    edges = []
    for edge in snapshot_edges:
        if not isinstance(edge, dict) or not is_prerequisite_edge(edge):
            continue
        a = by_key.get(str(edge.get('from', edge.get('source', ''))).strip().lower())
        b = by_key.get(str(edge.get('to', edge.get('target', ''))).strip().lower())
        if a and b and a != b:
            edges.append((a, b))
    return concepts, edges


async def record_learning_event(
    db: AsyncSession,
    user_id,
    event_type,
    *,
    subject_id=None,
    concept_id=None,
    duration_sec=0,
    metadata=None,
    trace_id=None,
):
    """Best-effort activity telemetry; business requests must remain usable."""
    try:
        event_type = str(event_type or '').strip().lower()
        if not event_type or len(event_type) > 64:
            return None
        if any(not (char.isalnum() or char in '._:-') for char in event_type):
            return None
        duration_sec = normalize_duration(duration_sec)
        metadata = metadata if isinstance(metadata, dict) else {}
        if trace_id is not None:
            trace_id = str(trace_id).strip()[:64] or None
        db.add(
            KpLearningEvent(
                user_id=user_id,
                event_type=event_type,
                subject_id=subject_id,
                concept_id=concept_id,
                duration_sec=duration_sec,
                metadata_json=metadata,
                trace_id=trace_id,
            )
        )
        await db.flush()
        return True
    except (TypeError, ValueError):
        return None


async def audit(db: AsyncSession, current_user, action, path, detail=None):
    """Persist an audit row for the authenticated user, best effort."""
    from core.api import user_id_of

    db.add(
        KpAuditLog(
            user_id=user_id_of(current_user),
            action=action,
            path=path,
            detail=detail or {},
        )
    )
    await db.flush()
