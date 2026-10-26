"""Learning-path service: projection of the knowledge graph for one learner.

Port of the Django path endpoints (``path_generate`` / ``path_current`` /
``next_node`` / ``path_progress`` / ``paths``) plus the shared stale-path
reconciliation helpers reused by the subject and graph endpoints.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain import record_learning_event, subject_graph
from core.graph.validator import validate_dag
from core.helpers import bool_value, path_node_concept_id
from module_assessment.service.mastery_service import (
    MasteryService,
    build_learning_path_nodes,
)
from module_knowledge.entity.do.concept_do import KpConcept
from module_learning.entity.do.learning_path_do import KpLearningPath
from module_subject.entity.do.subject_do import KpSubject


def recompute_path_node_states(nodes, edges):
    """Keep persisted path state in sync after a node is completed."""
    rows = [node for node in (nodes or []) if isinstance(node, dict)]
    by_id = {
        str(path_node_concept_id(node)): node
        for node in rows
        if path_node_concept_id(node) is not None
    }
    prerequisites = {key: set() for key in by_id}
    for source, target in edges or []:
        source, target = str(source), str(target)
        if target in prerequisites and source in by_id:
            prerequisites[target].add(source)
    completed = {
        key for key, node in by_id.items()
        if bool_value(node.get('completed'), default=False)
    }
    ready = [
        key for key in by_id
        if key not in completed and prerequisites[key] <= completed
    ]
    current = ready[0] if ready else None
    for key, node in by_id.items():
        if key in completed:
            node['state'] = node['status'] = 'completed'
            node['reason_codes'] = ['COMPLETED_PREVIOUSLY']
        elif key == current:
            node['state'] = node['status'] = 'current'
            node['reason_codes'] = ['PREREQUISITES_SATISFIED']
        elif key in ready:
            node['state'] = node['status'] = 'pending'
            node['reason_codes'] = ['PREREQUISITES_SATISFIED']
        else:
            node['state'] = node['status'] = 'blocked'
            node['reason_codes'] = ['PREREQUISITES_INCOMPLETE']
    return rows


def path_payload(path):
    """Build the wire payload for a persisted learning path."""
    nodes = [node for node in (path.nodes or []) if isinstance(node, dict)]
    completed = sum(1 for node in nodes if bool_value(node.get('completed'), default=False))
    current = next((node for node in nodes if node.get('state') == 'current' or node.get('status') == 'current'), None)
    current = current or next((node for node in nodes if not bool_value(node.get('completed'), default=False)), None)
    total = len(nodes)
    return {
        'id': path.path_id,
        'title': path.title,
        'nodes': path.nodes or [],
        'status': path.status,
        'progress': round(completed / total, 4) if total else None,
        'completed': completed,
        'total': total,
        'current_node': current,
    }


class LearningService:
    """异步学习路径服务层。"""

    @classmethod
    async def latest_path(cls, db: AsyncSession, user_id: int, subject_id: int) -> KpLearningPath | None:
        return (
            await db.execute(
                select(KpLearningPath)
                .where(
                    KpLearningPath.user_id == user_id,
                    KpLearningPath.subject_id == subject_id,
                    KpLearningPath.status != 'superseded',
                )
                .order_by(KpLearningPath.create_time.desc(), KpLearningPath.path_id.desc())
            )
        ).scalars().first()

    @classmethod
    async def refresh_stale_path(cls, db: AsyncSession, path: KpLearningPath | None, subject_id: int, user_id: int):
        """Repair a current path whose node set is out of sync with the graph."""
        if path is None:
            return None
        concepts, edges = await subject_graph(db, subject_id)
        if not concepts:
            return path
        active_ids = {str(concept.concept_id) for concept in concepts}
        path_ids = {
            str(path_node_concept_id(node))
            for node in (path.nodes or [])
            if isinstance(node, dict) and path_node_concept_id(node) is not None
        }
        node_rows = [
            node for node in (path.nodes or [])
            if isinstance(node, dict) and path_node_concept_id(node) is not None
        ]
        if path_ids == active_ids and len(path_ids) == len(node_rows):
            original = [dict(node) if isinstance(node, dict) else node for node in (path.nodes or [])]
            refreshed = recompute_path_node_states(path.nodes, edges)
            if refreshed != original:
                path.nodes = refreshed
                path.status = 'completed' if refreshed and all(
                    bool_value(node.get('completed'), default=False) for node in refreshed
                ) else 'active'
                await db.commit()
            return path
        if not validate_dag([concept.concept_id for concept in concepts], edges):
            return path
        nodes, status = build_learning_path_nodes(
            concepts,
            edges,
            await MasteryService.mastery_values(db, user_id, subject_id),
            path.nodes,
        )
        path.nodes = nodes
        path.status = status
        await db.commit()
        return path

    @classmethod
    async def supersede(cls, db: AsyncSession, user_id: int, subject_id: int) -> None:
        await db.execute(
            update(KpLearningPath)
            .where(
                KpLearningPath.user_id == user_id,
                KpLearningPath.subject_id == subject_id,
                KpLearningPath.status != 'superseded',
            )
            .values(status='superseded')
        )

    @classmethod
    async def generate(cls, db: AsyncSession, user_id: int, subject_id: int, data: dict):
        concepts, edges = await subject_graph(db, subject_id)
        values = await MasteryService.mastery_values(db, user_id, subject_id)
        if not validate_dag([c.concept_id for c in concepts], edges):
            return {'code': 'INVALID_GRAPH', 'message': 'latest knowledge graph contains a cycle'}, 422
        previous = await cls.latest_path(db, user_id, subject_id)
        nodes, status = build_learning_path_nodes(
            concepts, edges, values, previous.nodes if previous else None
        )
        if not nodes:
            return {
                'code': 'NO_CONCEPTS',
                'message': 'Create or build concepts before generating a path.',
            }, 409
        await cls.supersede(db, user_id, subject_id)
        title = str(data.get('title') or 'Learning path').strip()[:255] or 'Learning path'
        path = KpLearningPath(user_id=user_id, subject_id=subject_id, title=title, nodes=nodes, status=status)
        db.add(path)
        await db.commit()
        payload = path_payload(path)
        payload['path'] = dict(payload)
        return payload, 201

    @classmethod
    async def next_node(cls, db: AsyncSession, user_id: int, subject_id: int):
        path = await cls.latest_path(db, user_id, subject_id)
        if not path:
            return {'next': None}, 200
        path = await cls.refresh_stale_path(db, path, subject_id, user_id)
        nodes = path.nodes or []
        completed_ids = {
            str(path_node_concept_id(n))
            for n in nodes
            if isinstance(n, dict) and bool_value(n.get('completed'), default=False)
        }
        _, edges = await subject_graph(db, subject_id)
        by_id = {
            str(path_node_concept_id(n)): n
            for n in nodes
            if isinstance(n, dict) and path_node_concept_id(n) is not None
        }
        nxt = next(
            (
                n for n in nodes
                if isinstance(n, dict)
                and not bool_value(n.get('completed'), default=False)
                and all(str(a) in completed_ids or str(a) not in by_id for a, b in edges if str(b) == str(path_node_concept_id(n)))
            ),
            None,
        )
        if nxt is not None:
            concept_id = path_node_concept_id(nxt)
            concept = (
                await db.execute(
                    select(KpConcept).where(KpConcept.concept_id == concept_id, KpConcept.subject_id == subject_id)
                )
            ).scalars().first()
            await record_learning_event(
                db, user_id, 'path_node_open',
                subject_id=subject_id,
                concept_id=concept.concept_id if concept else None,
                metadata={'path_id': path.path_id, 'node_id': concept_id},
            )
            await db.commit()
        payload = path_payload(path)
        payload.update({'path_id': path.path_id, 'next': nxt})
        return payload, 200

    @classmethod
    async def progress(cls, db: AsyncSession, user_id: int, path_id: int, data: dict):
        path = (
            await db.execute(
                select(KpLearningPath).where(
                    KpLearningPath.path_id == path_id, KpLearningPath.user_id == user_id
                )
            )
        ).scalars().first()
        if path is None:
            return {'code': 'NOT_FOUND'}, 404
        if path.status == 'superseded':
            return {
                'code': 'PATH_SUPERSEDED',
                'message': 'This learning path has been replaced by a newer version.',
            }, 409
        from core.domain import normalize_duration

        try:
            event_duration_sec = normalize_duration(data.get('duration_sec', data.get('duration', 0)))
        except ValueError as exc:
            return {'code': 'VALIDATION_ERROR', 'message': str(exc)}, 400
        node_id = data.get('node_id')
        if node_id is None:
            return {'code': 'VALIDATION_ERROR', 'message': 'node_id_required'}, 400
        nodes = path.nodes or []
        target = None
        for n in nodes:
            if not isinstance(n, dict):
                continue
            candidate_ids = {str(n.get('id'))}
            concept_id = n.get('concept_id')
            if concept_id is None:
                raw_id = str(n.get('id', '')).strip()
                if raw_id.lower().startswith('concept-'):
                    concept_id = raw_id[8:]
            if concept_id is not None:
                candidate_ids.update({str(concept_id), f'concept-{concept_id}'})
            if str(node_id) in candidate_ids:
                target = n
                break
        if target is None:
            return {'code': 'NOT_FOUND', 'message': 'node_not_found'}, 404
        completing = bool_value(data.get('completed', True), default=True)
        if completing:
            _, edges = await subject_graph(db, path.subject_id)
            done = {
                str(path_node_concept_id(n))
                for n in nodes
                if isinstance(n, dict) and bool_value(n.get('completed'), default=False)
            }
            target_cid = str(path_node_concept_id(target))
            missing = sorted({str(a) for a, b in edges if str(b) == target_cid and str(a) not in done})
            if missing:
                return {
                    'code': 'PREREQUISITES_INCOMPLETE',
                    'message': 'complete prerequisite nodes first',
                    'prerequisite_concept_ids': missing,
                }, 409
        target['completed'] = completing
        _, edges = await subject_graph(db, path.subject_id)
        path.nodes = recompute_path_node_states(nodes, edges)
        path.status = 'completed' if nodes and all(
            isinstance(n, dict) and bool_value(n.get('completed'), default=False) for n in nodes
        ) else 'active'
        if completing:
            concept_id = path_node_concept_id(target)
            concept = (
                await db.execute(
                    select(KpConcept).where(
                        KpConcept.concept_id == concept_id, KpConcept.subject_id == path.subject_id
                    )
                )
            ).scalars().first()
            await record_learning_event(
                db, user_id, 'path_node_complete',
                subject_id=path.subject_id,
                concept_id=concept.concept_id if concept else None,
                duration_sec=event_duration_sec,
                metadata={'path_id': path.path_id, 'node_id': concept_id},
            )
        await db.commit()
        return path_payload(path), 200

    @classmethod
    async def list_paths(cls, db: AsyncSession, user_id: int):
        paths = (
            await db.execute(
                select(KpLearningPath)
                .where(KpLearningPath.user_id == user_id)
                .order_by(KpLearningPath.create_time.desc(), KpLearningPath.path_id.desc())
            )
        ).scalars().all()
        return [
            {
                'id': p.path_id,
                'title': p.title,
                'subject_id': p.subject_id,
                'nodes': p.nodes,
                'status': p.status,
            }
            for p in paths
        ]

    @classmethod
    async def create(cls, db: AsyncSession, user_id: int, data: dict):
        subject_id = data.get('subject_id')
        subject = (
            await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
        ).scalars().first() if subject_id else None
        if subject is None:
            return {'error': 'subject_not_found'}, 404
        nodes = data.get('nodes', [])
        if not isinstance(nodes, list):
            return {'error': 'nodes_must_be_array'}, 400
        path = KpLearningPath(
            user_id=user_id,
            subject_id=subject.subject_id,
            title=str(data.get('title', '学习路径'))[:255],
            nodes=nodes,
        )
        db.add(path)
        await db.commit()
        return {
            'id': path.path_id,
            'title': path.title,
            'subject_id': path.subject_id,
            'nodes': path.nodes,
            'status': path.status,
        }, 201
