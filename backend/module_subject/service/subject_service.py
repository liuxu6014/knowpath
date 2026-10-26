"""Subject CRUD and workspace listing service."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin
from core.domain import active_concepts, iso_time, subject_graph
from core.graph.resolver import latest_usable_graph, restrict_concepts_to_graph
from core.helpers import bool_value, path_node_concept_id
from module_analytics.entity.do.learning_report_do import KpLearningEvent
from module_knowledge.entity.do.concept_do import KpConcept
from module_learning.entity.do.learning_path_do import KpLearningPath
from module_learning.service.learning_service import LearningService
from module_resource.entity.do.resource_do import KpResource
from module_subject.entity.do.subject_do import KpSubject

SUBJECT_TYPES = {'paper', 'course', 'tech', 'topic'}


def _graph_value_keys(value):
    if isinstance(value, dict):
        values = (value.get('id'), value.get('concept_id'), value.get('conceptId'),
                  value.get('name'), value.get('title'), value.get('label'))
    else:
        values = (value,)
    keys = set()
    for item in values:
        if item is None or isinstance(item, (dict, list, tuple, set)):
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


def path_nodes_in_graph(nodes, graph_nodes, concepts):
    """Return path nodes represented by the currently usable graph."""
    if not graph_nodes:
        return nodes
    active_concepts_list = restrict_concepts_to_graph(concepts, graph_nodes)
    active_ids = {str(c.concept_id).strip().casefold() for c in active_concepts_list}
    active_names = set().union(*(_graph_value_keys(c.name) for c in active_concepts_list)) if active_concepts_list else set()

    def matches(node):
        raw_concept_id = node.get('concept_id', node.get('conceptId'))
        if raw_concept_id is not None and str(raw_concept_id).strip():
            value = str(raw_concept_id).strip().casefold()
            if value.startswith('concept-'):
                value = value[8:]
            if value in active_ids:
                return True
            return value in active_names
        raw_id = str(node.get('id', '')).strip()
        if raw_id.casefold().startswith('concept-'):
            return raw_id[8:].casefold() in active_ids
        if raw_id.isdigit():
            return raw_id.casefold() in active_ids
        display = node.get('name', node.get('title', node.get('label', raw_id)))
        return bool(_graph_value_keys(display).intersection(active_names))

    return [node for node in nodes if matches(node)]


class SubjectService:
    """异步学科服务层。"""

    @classmethod
    async def list_subjects(cls, db: AsyncSession, current_user, include_archived: bool):
        user_id = current_user.user.user_id
        query = select(KpSubject)
        if not is_admin(current_user):
            query = query.where(KpSubject.user_id == user_id)
        if not include_archived:
            query = query.where(KpSubject.archived.is_(False))
        subjects = (await db.execute(query.order_by(KpSubject.create_time.desc(), KpSubject.subject_id.desc()))).scalars().all()

        items = []
        for subject in subjects:
            path = await LearningService.latest_path(db, user_id, subject.subject_id)
            _, graph_nodes, _ = await latest_usable_graph(db, subject.subject_id)
            concepts = (
                await db.execute(select(KpConcept).where(KpConcept.subject_id == subject.subject_id))
            ).scalars().all()
            path_nodes = [node for node in (path.nodes or []) if isinstance(node, dict)] if path else []
            nodes = path_nodes_in_graph(path_nodes, graph_nodes, concepts) if path else []
            completed = sum(1 for node in nodes if bool_value(node.get('completed'), default=False))
            expected_nodes = len(graph_nodes) if graph_nodes and path else len(nodes)
            progress = (completed / expected_nodes) if expected_nodes else None
            concept_count = len(graph_nodes) if graph_nodes else len(concepts)
            study_seconds = int(
                (
                    await db.execute(
                        select(func.coalesce(func.sum(KpLearningEvent.duration_sec), 0)).where(
                            KpLearningEvent.user_id == user_id, KpLearningEvent.subject_id == subject.subject_id
                        )
                    )
                ).scalar() or 0
            )
            resource_count = (
                await db.execute(
                    select(func.count()).select_from(KpResource).where(KpResource.subject_id == subject.subject_id)
                )
            ).scalar() or 0
            items.append({
                'id': subject.subject_id,
                'name': subject.name,
                'title': subject.name,
                'description': subject.description,
                'subject_type': subject.subject_type,
                'type': subject.subject_type,
                'learning_goal': subject.learning_goal,
                'archived': subject.archived,
                'progress': progress,
                'path_id': path.path_id if path else None,
                'node_count': expected_nodes,
                'completed_nodes': completed,
                'resource_count': resource_count,
                'concept_count': concept_count,
                'study_seconds': study_seconds,
                'study_minutes': round(study_seconds / 60, 2),
                'duration_sec': study_seconds,
            })
        return items

    @classmethod
    async def create(cls, db: AsyncSession, user_id: int, data: dict):
        name = str(data.get('name', data.get('title', '')) or '').strip()
        if not name:
            return {'code': 'VALIDATION_ERROR', 'message': 'name_required'}, 400
        if len(name) > 120:
            return {'code': 'VALIDATION_ERROR', 'message': 'name_too_long'}, 400
        subject_type = str(data.get('subject_type', data.get('type', 'topic')) or 'topic').strip().lower()
        if subject_type not in SUBJECT_TYPES:
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_subject_type'}, 400
        exists = (
            await db.execute(select(KpSubject.subject_id).where(KpSubject.user_id == user_id, KpSubject.name == name))
        ).scalars().first()
        if exists is not None:
            return {'code': 'DUPLICATE_RESOURCE', 'message': 'subject_name_exists'}, 409
        subject = KpSubject(
            name=name,
            description=str(data.get('description', '') or ''),
            subject_type=subject_type,
            learning_goal=str(data.get('learning_goal', '') or ''),
            user_id=user_id,
        )
        db.add(subject)
        await db.commit()
        return {
            'id': subject.subject_id,
            'name': subject.name,
            'title': subject.name,
            'description': subject.description,
            'subject_type': subject.subject_type,
            'type': subject.subject_type,
            'learning_goal': subject.learning_goal,
            'archived': subject.archived,
        }, 201

    @classmethod
    async def detail(cls, db: AsyncSession, current_user, subject_id: int):
        subject = (
            await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
        ).scalars().first()
        if subject is None or not (is_admin(current_user) or subject.user_id == current_user.user.user_id):
            return {'code': 'NOT_FOUND'}, 404
        user_id = current_user.user.user_id
        path = await LearningService.latest_path(db, user_id, subject_id)
        path = await LearningService.refresh_stale_path(db, path, subject_id, user_id)
        nodes = list(path.nodes or []) if path else []
        completed = sum(1 for node in nodes if isinstance(node, dict) and bool_value(node.get('completed'), default=False))
        _, graph_nodes, _ = await latest_usable_graph(db, subject_id)
        concepts = (
            await db.execute(select(KpConcept).where(KpConcept.subject_id == subject_id))
        ).scalars().all()
        concept_count = len(graph_nodes) if graph_nodes else len(concepts)
        resource_count = (
            await db.execute(
                select(func.count()).select_from(KpResource).where(KpResource.subject_id == subject_id)
            )
        ).scalar() or 0
        return {
            'id': subject.subject_id,
            'name': subject.name,
            'title': subject.name,
            'description': subject.description,
            'subject_type': subject.subject_type,
            'type': subject.subject_type,
            'learning_goal': subject.learning_goal,
            'archived': subject.archived,
            'user_id': subject.user_id,
            'progress': (completed / len(nodes)) if nodes else None,
            'path_id': path.path_id if path else None,
            'node_count': len(nodes),
            'completed_nodes': completed,
            'resource_count': resource_count,
            'concept_count': concept_count,
        }, 200

    @classmethod
    async def update(cls, db: AsyncSession, current_user, subject_id: int, data: dict):
        subject = (
            await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
        ).scalars().first()
        if subject is None:
            return {'code': 'NOT_FOUND'}, 404
        if not (is_admin(current_user) or subject.user_id == current_user.user.user_id):
            return {'code': 'PERMISSION_DENIED'}, 403
        if 'name' in data or 'title' in data:
            name = str(data.get('name', data.get('title')) or '').strip()
            if not name:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_required'}, 400
            if len(name) > 120:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_too_long'}, 400
            subject.name = name
        if 'description' in data:
            subject.description = str(data.get('description') or '')
        if 'subject_type' in data or 'type' in data:
            value = str(data.get('subject_type', data.get('type')) or 'topic').strip().lower()
            if value not in SUBJECT_TYPES:
                return {'code': 'VALIDATION_ERROR', 'message': 'invalid_subject_type'}, 400
            subject.subject_type = value
        if 'learning_goal' in data:
            subject.learning_goal = str(data.get('learning_goal') or '')
        if 'archived' in data:
            subject.archived = bool_value(data.get('archived'))
        await db.commit()
        return {
            'id': subject.subject_id,
            'name': subject.name,
            'title': subject.name,
            'description': subject.description,
            'subject_type': subject.subject_type,
            'type': subject.subject_type,
            'learning_goal': subject.learning_goal,
            'archived': subject.archived,
        }

    @classmethod
    async def archive(cls, db: AsyncSession, current_user, subject_id: int):
        subject = (
            await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
        ).scalars().first()
        if subject is None:
            return {'code': 'NOT_FOUND'}, 404
        if not (is_admin(current_user) or subject.user_id == current_user.user.user_id):
            return {'code': 'PERMISSION_DENIED'}, 403
        subject.archived = True
        await db.commit()
        return {'ok': True, 'archived': True}
