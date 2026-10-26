"""Knowledge graph build/display, relations, snapshots, notes, lesson, chat.

Port of the Django knowledge endpoints (``knowledge_build``, ``graph``,
``graph_validate``, ``knowledge_profile``, ``knowledge_concept_update``,
relations, snapshots, lesson, chat, notes) to async SQLAlchemy.
"""
import hashlib
import json
import re
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin, user_id_of
from core.domain import (
    active_concepts,
    audit,
    iso_time,
    record_learning_event,
    subject_for,
    subject_graph,
)
from core.graph.resolver import latest_usable_graph, restrict_concepts_to_graph
from core.graph.storage import graph_store
from core.graph.validator import (
    is_prerequisite_edge,
    normalize_graph,
    prerequisite_edges,
    validate_dag,
    validate_graph,
)
from core.helpers import bool_value, graph_key, path_node_concept_id, safe_float, text_fragments
from core.retrieval import search as retrieval_search
from module_ai.service.ai_service import AiService
from module_assessment.service.mastery_service import MasteryService, _mastery_value
from module_knowledge.entity.do.concept_do import KpConcept, KpNote
from module_knowledge.entity.do.graph_snapshot_do import KpGraphSnapshot
from module_learning.entity.do.learning_path_do import KpLearningPath
from module_learning.service.learning_service import LearningService
from module_resource.entity.do.resource_do import KpChunk, KpProcessingTask, KpResource
from module_subject.entity.do.subject_do import KpSubject


def _concept_evidence(subject, concept, snapshot, raw_edges, concepts):
    """Return direct prerequisite/dependent edges for one current concept."""
    by_key = {}
    for item in concepts:
        for key in (item.concept_id, f'concept-{item.concept_id}', item.name, graph_key(item.name)):
            normalized = graph_key(key)
            if normalized:
                by_key.setdefault(normalized, item)
    rows = []
    for index, raw in enumerate(raw_edges or []):
        if not isinstance(raw, dict):
            continue
        source = by_key.get(graph_key(raw.get('from', raw.get('source'))))
        target = by_key.get(graph_key(raw.get('to', raw.get('target'))))
        if source is None or target is None or (source.concept_id != concept.concept_id and target.concept_id != concept.concept_id):
            continue
        edge_ref = raw.get('id') or f'{snapshot.snapshot_id if snapshot else subject.subject_id}-{index}'
        evidence_id = f'graph-edge-{edge_ref}'
        relation = str(raw.get('relation', raw.get('type', 'PREREQUISITE_OF')) or 'PREREQUISITE_OF').upper()
        rows.append({
            'type': 'graph_relation',
            'id': evidence_id,
            'evidence_id': evidence_id,
            'source': source.name,
            'source_id': source.concept_id,
            'relation': relation,
            'inferred': bool(raw.get('inferred', False)),
            'reason': raw.get('reason'),
            'evidence': raw.get('evidence'),
            'target': target.name,
            'target_id': target.concept_id,
            'subject_id': subject.subject_id,
            'confidence': raw.get('confidence'),
            'edge_id': raw.get('id'),
        })
    return rows


async def _resource_evidence(db: AsyncSession, subject, query, limit=4):
    """Retrieve bounded snippets from resources belonging to this subject."""
    chunks = (
        await db.execute(
            select(KpChunk)
            .join(KpResource, KpResource.resource_id == KpChunk.resource_id)
            .where(KpResource.subject_id == subject.subject_id)
            .order_by(KpChunk.resource_id, KpChunk.seq_no)
        )
    ).scalars().all()
    selected = []
    if chunks:
        try:
            documents = [{'id': f'chunk-{chunk.chunk_id}', 'text': chunk.content or ''} for chunk in chunks]
            hits = retrieval_search(str(query or ''), documents, top_k=limit)
            by_id = {f'chunk-{chunk.chunk_id}': chunk for chunk in chunks}
            seen = set()
            for hit in hits:
                chunk = by_id.get(str(hit.get('id')))
                if chunk is not None and chunk.chunk_id not in seen:
                    seen.add(chunk.chunk_id)
                    selected.append((chunk, hit.get('score', 0)))
        except Exception:
            selected = []
        if not selected:
            selected = [(chunk, 0) for chunk in chunks[:limit]]
    else:
        resources = (
            await db.execute(
                select(KpResource).where(KpResource.subject_id == subject.subject_id).order_by(KpResource.resource_id)
            )
        ).scalars().all()
        selected = [(resource, 0) for resource in resources[:limit] if resource.content]

    evidence = []
    for source, score in selected[:max(1, int(limit))]:
        if isinstance(source, KpChunk):
            resource = (
                await db.execute(select(KpResource).where(KpResource.resource_id == source.resource_id))
            ).scalars().first()
            metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
            evidence_id = f'chunk-{source.chunk_id}'
            evidence.append({
                'type': 'chunk',
                'id': evidence_id,
                'evidence_id': evidence_id,
                'chunk_id': source.chunk_id,
                'resource_id': source.resource_id,
                'resource_title': resource.title if resource else None,
                'source': resource.title if resource else None,
                'source_type': 'resource',
                'snippet': str(source.content or '').strip()[:600],
                'heading': metadata.get('heading') or metadata.get('heading_path'),
                'page': metadata.get('page') or metadata.get('page_start'),
                'score': round(float(score or 0), 6),
            })
        else:
            evidence_id = f'resource-{source.resource_id}'
            evidence.append({
                'type': 'resource',
                'id': evidence_id,
                'evidence_id': evidence_id,
                'resource_id': source.resource_id,
                'resource_title': source.title,
                'source': source.title,
                'source_type': 'resource',
                'snippet': str(source.content or '').strip()[:600],
                'score': round(float(score or 0), 6),
            })
    return evidence


async def _evidence_for(db: AsyncSession, subject, concept, query):
    snapshot, _nodes, raw_edges = await latest_usable_graph(db, subject.subject_id)
    concepts, _ = await subject_graph(db, subject.subject_id)
    evidence = [{
        'type': 'concept',
        'id': f'concept-{concept.concept_id}',
        'evidence_id': f'concept-{concept.concept_id}',
        'concept_id': concept.concept_id,
        'source': concept.name,
        'source_type': 'concept',
        'snippet': concept.description or concept.name,
    }]
    evidence.extend(await _resource_evidence(db, subject, query))
    evidence.extend(_concept_evidence(subject, concept, snapshot, raw_edges, concepts))
    return evidence


def _lesson_fallback(concept, evidence):
    """Build a complete LessonSchema-compatible payload offline."""
    subject = concept.subject if hasattr(concept, 'subject') else None
    subject_name = subject.name if subject else '当前学习对象'
    definition = str(concept.description or '').strip() or f'{concept.name} 是当前学习对象中的一个核心知识点。'
    graph_rows = [row for row in evidence if row.get('type') == 'graph_relation' and is_prerequisite_edge(row)]
    prerequisites = [row['source'] for row in graph_rows if row.get('target_id') == concept.concept_id and row.get('source')]
    snippets = [row.get('snippet') for row in evidence if row.get('type') in {'chunk', 'resource'} and row.get('snippet')]
    examples = []
    for snippet in snippets:
        for fragment in text_fragments(snippet, 2):
            if fragment and fragment.casefold() != definition.casefold():
                examples.append(fragment)
            if len(examples) >= 3:
                break
        if len(examples) >= 3:
            break
    if not examples:
        examples = [f'示例：在“{subject_name}”中，把“{concept.name}”应用到一个具体任务，再观察输入、处理过程和输出。']
    key_points = text_fragments(definition, 3)
    if prerequisites:
        key_points.append(f'学习前先掌握：{"、".join(prerequisites)}。')
    key_points = list(dict.fromkeys(key_points))[:5]
    summary = [f'{concept.name} 的核心是：{definition}', '结合示例完成一次练习，再用自己的话复述关键步骤。']
    evidence_ids = [row['id'] for row in evidence if row.get('id')]
    sections = [
        {'title': '定义', 'markdown': definition},
        {'title': '示例', 'markdown': '\n'.join(f'- {item}' for item in examples)},
        {'title': '重点', 'markdown': '\n'.join(f'- {item}' for item in key_points)},
        {'title': '小结', 'markdown': '\n'.join(f'- {item}' for item in summary)},
    ]
    content = {
        'text': definition + '\n\n' + '\n'.join(summary),
        'definition': definition,
        'examples': examples,
        'prerequisites': prerequisites,
        'key_points': key_points,
        'summary': summary,
        'evidence': evidence,
        'evidence_ids': evidence_ids,
        'sections': sections,
    }
    return {
        'concept_name': concept.name,
        'learning_objectives': [f'能用自己的话解释{concept.name}。', f'能结合示例应用{concept.name}。'],
        'definition': definition,
        'examples': examples,
        'prerequisites': prerequisites,
        'key_points': key_points,
        'summary': summary,
        'common_mistakes': [f'只记住“{concept.name}”的名称，却没有说明它解决的问题。'],
        'check_questions': [f'请用自己的话解释“{concept.name}”，并举一个应用场景。'],
        'sections': sections,
        'evidence': evidence,
        'evidence_ids': evidence_ids,
        'content': content,
        'source': 'offline',
    }


async def _provider_lesson(db: AsyncSession, concept, fallback):
    """Use the existing provider when available and preserve offline fields."""
    context = '\n'.join(row.get('snippet') or f"{row.get('source')}: {row.get('relation', '')}" for row in fallback['evidence'])[:5000]
    prompt = ('Return JSON only with definition, examples, prerequisites, key_points, summary, '
              'learning_objectives, common_mistakes, check_questions and sections. '
              f'Concept: {concept.name}\n<retrieved_context>\n{context}\n</retrieved_context>')
    try:
        raw = await AiService.chat(
            db,
            [
                {'role': 'system', 'content': 'You are a careful tutor. Use only the supplied context.'},
                {'role': 'user', 'content': prompt},
            ],
            prompt_code='generate_lesson',
            concept=concept.name,
            context=context,
        )
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get('lesson'), dict):
            value = value['lesson']
        if not isinstance(value, dict):
            return fallback
        result = dict(fallback)
        used_provider = False
        for key in ('definition', 'examples', 'prerequisites', 'key_points', 'summary',
                    'learning_objectives', 'common_mistakes', 'check_questions', 'sections'):
            candidate = value.get(key)
            if key == 'definition' and isinstance(candidate, str) and candidate.strip():
                result[key] = candidate.strip()
                used_provider = True
            elif key == 'sections' and isinstance(candidate, list):
                sections = [
                    {'title': str(item.get('title')).strip(), 'markdown': str(item.get('markdown')).strip()}
                    for item in candidate
                    if isinstance(item, dict) and str(item.get('title', '')).strip() and str(item.get('markdown', '')).strip()
                ]
                if sections:
                    result[key] = sections
                    used_provider = True
            elif key != 'definition' and isinstance(candidate, list):
                values = [str(item).strip() for item in candidate if str(item).strip()]
                if values:
                    result[key] = values
                    used_provider = True
        if not used_provider:
            return fallback
        result['source'] = 'provider'
        result['content'] = dict(fallback['content'])
        result['content'].update({key: result[key] for key in ('definition', 'examples', 'prerequisites', 'key_points', 'summary', 'sections')})
        result['content']['text'] = result['definition'] + '\n\n' + '\n'.join(map(str, result['summary']))
        return result
    except Exception:
        return fallback


async def _lesson_response(db: AsyncSession, concept):
    evidence = await _evidence_for(db, concept.subject, concept, f'{concept.name} {concept.description}')
    fallback = _lesson_fallback(concept, evidence)
    lesson_data = await _provider_lesson(db, concept, fallback)
    concept_data = {'id': concept.concept_id, 'name': concept.name, 'description': concept.description}
    nested = dict(lesson_data)
    nested['concept'] = concept_data
    nested['subject_id'] = concept.subject_id
    return {
        'lesson': nested,
        'concept': concept_data,
        'content': lesson_data['content'],
        'content_text': lesson_data['content'].get('text', concept.description or concept.name),
        'legacy_content': concept.description or concept.name,
        **{key: lesson_data[key] for key in (
            'definition', 'examples', 'prerequisites', 'key_points', 'summary', 'evidence',
            'evidence_ids', 'sections', 'learning_objectives', 'common_mistakes',
            'check_questions', 'concept_name', 'source',
        )},
        'subject_id': concept.subject_id,
        'trace_id': f'lesson-{uuid.uuid4().hex}',
    }


def _relation_node_aliases(nodes):
    aliases = {}
    for raw in nodes or []:
        if not isinstance(raw, dict):
            raw = {'id': raw, 'name': raw}
        node_id = raw.get('id', raw.get('concept_id'))
        if node_id is None or not str(node_id).strip():
            continue
        canonical = str(node_id).strip()
        values = (canonical, raw.get('concept_id'), raw.get('conceptId'),
                  raw.get('name'), raw.get('title'), raw.get('label'))
        for value in values:
            if value is not None and str(value).strip():
                aliases.setdefault(str(value).strip().casefold(), canonical)
    return aliases


def _relation_payload(snapshot, edge, index):
    edge = dict(edge) if isinstance(edge, dict) else {'from': '', 'to': ''}
    relation_id = str(edge.get('id') or f'{snapshot.snapshot_id}:{index}')
    return {
        'id': relation_id,
        'relation_id': relation_id,
        'snapshot_id': snapshot.snapshot_id,
        'subject_id': snapshot.subject_id,
        'index': index,
        'from': edge.get('from', edge.get('source')),
        'to': edge.get('to', edge.get('target')),
        'relation': edge.get('relation', edge.get('type', 'PREREQUISITE_OF')),
        'confidence': edge.get('confidence'),
        'inferred': bool(edge.get('inferred', False)),
        'reason': edge.get('reason'),
        'evidence': edge.get('evidence'),
        'source': edge.get('source_name', edge.get('source_type', edge.get('source'))),
        'evidence_ids': edge.get('evidence_ids', []),
        'verified': bool(edge.get('verified', False)),
        'review_status': edge.get('review_status', 'verified' if edge.get('verified') else 'pending'),
    }


def _relation_copy_edges(edges):
    copied = []
    for raw in edges or []:
        if isinstance(raw, dict):
            copied.append(dict(raw))
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            copied.append({'from': raw[0], 'to': raw[1]})
    return copied


def _relation_fields(edge, data, aliases, *, creating=False):
    source = data.get('from', data.get('source', edge.get('from', edge.get('source'))))
    target = data.get('to', data.get('target', edge.get('to', edge.get('target'))))
    source_key = str(source).strip().casefold() if source is not None else ''
    target_key = str(target).strip().casefold() if target is not None else ''
    source_id = aliases.get(source_key)
    target_id = aliases.get(target_key)
    if not source_id or not target_id:
        return None, ('UNKNOWN_NODE', 'relation endpoint does not belong to this graph')
    if source_id == target_id:
        return None, ('SELF_LOOP', 'a relation cannot point to itself')
    edge['from'], edge['to'] = source_id, target_id
    edge.pop('source', None)
    edge.pop('target', None)
    if 'relation' in data or 'type' in data:
        relation = str(data.get('relation', data.get('type')) or '').strip().upper()
        if not relation or len(relation) > 64:
            return None, ('VALIDATION_ERROR', 'invalid relation type')
        if relation in {'PREREQUISITE', 'PREREQUISITE_OF'}:
            relation = 'PREREQUISITE_OF'
        edge['relation'] = relation
    elif creating:
        edge['relation'] = 'PREREQUISITE_OF'
    if 'confidence' in data:
        try:
            confidence = float(data.get('confidence'))
        except (TypeError, ValueError, OverflowError):
            return None, ('VALIDATION_ERROR', 'confidence must be between 0 and 1')
        if not 0 <= confidence <= 1:
            return None, ('VALIDATION_ERROR', 'confidence must be between 0 and 1')
        edge['confidence'] = confidence
    if 'evidence_ids' in data:
        evidence_ids = data.get('evidence_ids')
        if not isinstance(evidence_ids, list) or any(isinstance(item, (dict, list, tuple, set)) for item in evidence_ids):
            return None, ('VALIDATION_ERROR', 'evidence_ids must be an array')
        edge['evidence_ids'] = [str(item) for item in evidence_ids[:100]]
    if 'inferred' in data:
        edge['inferred'] = bool_value(data.get('inferred'), default=False)
    if 'verified' in data:
        edge['verified'] = bool_value(data.get('verified'), default=False)
        edge['review_status'] = 'verified' if edge['verified'] else 'pending'
    elif 'review_status' in data:
        status = str(data.get('review_status') or '').strip().lower()
        if status not in {'pending', 'verified', 'rejected'}:
            return None, ('VALIDATION_ERROR', 'invalid review_status')
        edge['review_status'] = status
        edge['verified'] = status == 'verified'
    for key in ('reason', 'evidence', 'source_name', 'source_type'):
        if key in data:
            value = data.get(key)
            edge[key] = value if key == 'evidence' and isinstance(value, (dict, list)) else str(value or '')[:500]
    return edge, None


class KnowledgeService:
    """异步知识图谱服务层。"""

    @classmethod
    async def build(cls, db: AsyncSession, current_user, subject_id: int):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        resources = (
            await db.execute(select(KpResource).where(KpResource.subject_id == subject_id))
        ).scalars().all()
        for resource in resources:
            task = (
                await db.execute(
                    select(KpProcessingTask)
                    .where(KpProcessingTask.resource_id == resource.resource_id)
                    .order_by(KpProcessingTask.create_time.desc(), KpProcessingTask.task_id.desc())
                )
            ).scalars().first()
            chunk_exists = (
                await db.execute(select(KpChunk.chunk_id).where(KpChunk.resource_id == resource.resource_id).limit(1))
            ).scalars().first() is not None
            if task is None or task.status != 'succeeded' or not chunk_exists:
                if task is None:
                    task = KpProcessingTask(resource_id=resource.resource_id)
                    db.add(task)
                    await db.flush()
                from module_resource.service.resource_service import ResourceService
                await ResourceService.process_resource(db, resource, task)
        text = '\n'.join(r.content or '' for r in resources)
        try:
            data, source = await AiService.extract(db, text)
        except Exception:
            from core.knowledge import extract_knowledge
            data, source = extract_knowledge(text), 'offline'
        if not isinstance(data, dict):
            data = {}
        raw_nodes = data.get('nodes', [])
        raw_edges = data.get('edges', [])
        if not isinstance(raw_nodes, list):
            raw_nodes = []
        if not isinstance(raw_edges, list):
            raw_edges = []
        nodes, edges = normalize_graph(raw_nodes, raw_edges)
        node_ids = [str(node.get('id')) for node in nodes if node.get('id')]
        edge_pairs = [(edge['from'], edge['to']) for edge in edges]
        if not validate_dag(node_ids, edge_pairs):
            return {'code': 'INVALID_GRAPH', 'message': 'knowledge graph must be acyclic', 'source': source}, 422
        preserved, preserved_nodes, preserved_edges = await latest_usable_graph(db, subject_id)
        if preserved and prerequisite_edges(preserved_edges) and not prerequisite_edges(edges):
            return {
                'snapshot_id': preserved.snapshot_id,
                'nodes': preserved_nodes,
                'edges': preserved_edges,
                'version': preserved.version,
                'status': 'succeeded',
                'created': False,
                'preserved': True,
                'warning': 'NO_VALID_EDGES',
                'source': source,
            }, 200
        if not nodes:
            if preserved:
                return {
                    'snapshot_id': preserved.snapshot_id,
                    'nodes': preserved_nodes,
                    'edges': preserved_edges,
                    'version': preserved.version,
                    'status': 'succeeded',
                    'created': False,
                    'preserved': True,
                    'warning': 'NO_CONCEPTS',
                    'source': source,
                }, 200
            return {'code': 'NO_CONCEPTS', 'message': 'No concepts could be extracted.', 'source': source}, 409
        for node in nodes:
            name = str(node.get('name') or node.get('id') or '').strip()
            if name:
                description = node.get('description', '') or ''
                if not isinstance(description, str):
                    description = str(description)
                concept = (
                    await db.execute(
                        select(KpConcept)
                        .where(KpConcept.subject_id == subject_id, func.lower(KpConcept.name) == name.casefold())
                        .order_by(KpConcept.concept_id)
                    )
                ).scalars().first()
                if concept is None:
                    db.add(KpConcept(subject_id=subject_id, name=name[:200], description=description))
                elif description and not concept.description:
                    concept.description = description
        latest = (
            await db.execute(
                select(KpGraphSnapshot)
                .where(KpGraphSnapshot.subject_id == subject_id)
                .order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc())
            )
        ).scalars().first()
        if latest and latest.nodes == nodes and latest.edges == edges:
            return {
                'snapshot_id': latest.snapshot_id,
                'nodes': latest.nodes,
                'edges': latest.edges,
                'version': latest.version,
                'status': 'succeeded',
                'created': False,
                'source': source,
            }, 200
        version = (latest.version + 1) if latest else 1
        snapshot = KpGraphSnapshot(subject_id=subject_id, user_id=user_id_of(current_user), nodes=nodes, edges=edges, version=version)
        db.add(snapshot)
        await db.flush()
        sync = graph_store().save(snapshot.nodes, snapshot.edges, graph_id=snapshot.snapshot_id, subject_id=subject_id)
        await db.commit()
        return {
            'snapshot_id': snapshot.snapshot_id,
            'nodes': snapshot.nodes,
            'edges': snapshot.edges,
            'version': snapshot.version,
            'graph': sync,
            'status': 'succeeded',
            'created': True,
            'source': source,
        }, 201

    @classmethod
    async def graph(cls, db: AsyncSession, current_user, subject_id: int):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        snapshot, graph_nodes, graph_edges = await latest_usable_graph(db, subject_id)
        if not snapshot:
            return {
                'nodes': [], 'edges': [], 'version': 0,
                'stats': {'node_count': 0, 'edge_count': 0, 'mastered_count': 0,
                          'learning_count': 0, 'locked_count': 0},
            }, 200
        concepts = (
            await db.execute(select(KpConcept).where(KpConcept.subject_id == subject_id).order_by(KpConcept.concept_id))
        ).scalars().all()
        concept_by_key = {}
        for concept in concepts:
            concept_by_key[str(concept.concept_id).strip().lower()] = concept
            concept_by_key[f'concept-{concept.concept_id}'.lower()] = concept
            name_key = str(concept.name).strip().lower()
            if name_key:
                concept_by_key.setdefault(name_key, concept)
                concept_by_key.setdefault(re.sub(r'\s+', '-', name_key), concept)
        values = await MasteryService.mastery_values(db, user_id_of(current_user), subject_id)
        current_path = await LearningService.latest_path(db, user_id_of(current_user), subject_id)
        current_path = await LearningService.refresh_stale_path(db, current_path, subject_id, user_id_of(current_user))
        path_completed_ids = {
            str(path_node_concept_id(node)).strip()
            for node in (current_path.nodes or []) if isinstance(node, dict)
            and bool_value(node.get('completed'), default=False)
            and path_node_concept_id(node) is not None
        } if current_path else set()
        nodes = []
        for raw in graph_nodes:
            node = dict(raw) if isinstance(raw, dict) else {'id': raw, 'name': raw}
            key_name = str(node.get('name') or '').strip().lower()
            key_id = str(node.get('id') or '').strip().lower()
            concept = concept_by_key.get(key_name) or concept_by_key.get(key_id)
            if concept:
                node.setdefault('name', concept.name)
                node.setdefault('concept_id', concept.concept_id)
                node.setdefault('description', concept.description)
                node['mastery'] = round(max(0.0, min(100.0, _mastery_value(values, concept.concept_id))), 2)
                node.setdefault('mastery_percent', node['mastery'])
            nodes.append(node)
        by_node_key = {}
        for index, node in enumerate(nodes):
            for key in (node.get('id'), node.get('concept_id'), node.get('name')):
                if key is None:
                    continue
                text_key = str(key).strip().lower()
                if text_key:
                    by_node_key.setdefault(text_key, index)
                    by_node_key.setdefault(re.sub(r'\s+', '-', text_key), index)
        incoming = {index: [] for index in range(len(nodes))}
        outgoing = {index: [] for index in range(len(nodes))}
        for edge in graph_edges:
            if not is_prerequisite_edge(edge):
                continue
            source_key = str(edge.get('from', edge.get('source', ''))).strip().lower()
            target_key = str(edge.get('to', edge.get('target', ''))).strip().lower()
            source_index = by_node_key.get(source_key, by_node_key.get(re.sub(r'\s+', '-', source_key)))
            target_index = by_node_key.get(target_key, by_node_key.get(re.sub(r'\s+', '-', target_key)))
            if source_index is None or target_index is None or source_index == target_index:
                continue
            outgoing[source_index].append(nodes[target_index])
            incoming[target_index].append(nodes[source_index])
        mastered_ids = {
            str(node.get('concept_id', node.get('id'))).strip()
            for node in nodes
            if safe_float(node.get('mastery', 0)) >= 80
        }
        mastered_ids.update(path_completed_ids)
        for index, node in enumerate(nodes):
            prerequisites = incoming[index]
            dependents = outgoing[index]
            node['prerequisite_concept_ids'] = [item.get('concept_id', item.get('id')) for item in prerequisites]
            node['dependent_concept_ids'] = [item.get('concept_id', item.get('id')) for item in dependents]
            score = safe_float(node.get('mastery', 0))
            ready = all(
                str(item.get('concept_id', item.get('id'))).strip() in mastered_ids
                for item in prerequisites
            )
            concept_key = str(node.get('concept_id', node.get('id'))).strip()
            node['status'] = (
                'completed' if concept_key in path_completed_ids else
                'mastered' if score >= 80 else
                'learning' if score > 0 and ready else
                'locked' if prerequisites and not ready else
                'unknown'
            )
            node['completed'] = concept_key in path_completed_ids or score >= 80
            node['is_locked'] = node['status'] == 'locked'
        return {
            'nodes': nodes,
            'edges': graph_edges,
            'version': snapshot.version,
            'stats': {
                'node_count': len(nodes),
                'edge_count': len(graph_edges),
                'mastered_count': sum(1 for node in nodes if node.get('status') == 'mastered'),
                'completed_count': sum(1 for node in nodes if node.get('status') == 'completed'),
                'learning_count': sum(1 for node in nodes if node.get('status') == 'learning'),
                'locked_count': sum(1 for node in nodes if node.get('status') == 'locked'),
            },
        }, 200

    @classmethod
    async def validate(cls, data: dict):
        if not isinstance(data, dict):
            return {
                'valid': False,
                'error': 'invalid_graph',
                'details': [{'code': 'invalid_graph', 'type': 'invalid_graph',
                             'message': 'request body must be a JSON object'}],
            }, 400
        nodes, edges = data.get('nodes', []), data.get('edges', [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            missing = [name for name, value in (('nodes', nodes), ('edges', edges)) if not isinstance(value, list)]
            return {
                'valid': False,
                'error': 'nodes_and_edges_must_be_arrays',
                'details': [{'code': 'nodes_and_edges_must_be_arrays', 'type': 'nodes_and_edges_must_be_arrays',
                             'message': 'nodes and edges must be arrays', 'fields': missing}],
            }, 400
        report = validate_graph(nodes, edges)
        payload = {'valid': report['valid'], 'details': report['details']}
        if not report['valid']:
            payload['error'] = report['details'][0]['code']
        status = 200 if report['valid'] else (
            400 if any(item['code'] in {'invalid_graph', 'invalid_node', 'invalid_edge', 'unknown_node'}
                       for item in report['details']) else 422
        )
        return payload, status

    @classmethod
    async def profile(cls, db: AsyncSession, current_user):
        from module_assessment.entity.do.assessment_do import KpMasteryRecord

        user_id = user_id_of(current_user)
        rows = (
            await db.execute(
                select(KpMasteryRecord)
                .join(KpConcept, KpConcept.concept_id == KpMasteryRecord.concept_id)
                .where(KpMasteryRecord.user_id == user_id)
                .order_by(KpMasteryRecord.update_time.desc(), KpConcept.name, KpMasteryRecord.concept_id)
            )
        ).scalars().all()
        groups = {}
        for record in rows:
            concept = (
                await db.execute(select(KpConcept).where(KpConcept.concept_id == record.concept_id))
            ).scalars().first()
            if concept is None:
                continue
            name = str(concept.name or '').strip()
            if not name:
                continue
            key = ''.join(name.casefold().split())
            bucket = groups.setdefault(key, {
                'name': name,
                'mastery_values': [],
                'evidence_count': 0,
                'subjects': {},
                'concept_ids': [],
                'last_evidence_at': None,
            })
            if len(name) < len(str(bucket['name'])):
                bucket['name'] = name
            bucket['mastery_values'].append(float(record.mastery or 0))
            bucket['evidence_count'] += int(record.evidence_count or 0)
            bucket['concept_ids'].append(record.concept_id)
            subject = (
                await db.execute(select(KpSubject).where(KpSubject.subject_id == concept.subject_id))
            ).scalars().first()
            subject_name = subject.name if subject else '未命名对象'
            bucket['subjects'][str(subject.subject_id if subject else '')] = {
                'id': subject.subject_id if subject else None,
                'name': subject_name,
                'mastery': round(float(record.mastery or 0), 4),
                'status': record.status,
                'evidence_count': int(record.evidence_count or 0),
            }
            if record.last_evidence_at:
                current = bucket['last_evidence_at']
                iso = record.last_evidence_at.isoformat()
                if current is None or iso > current:
                    bucket['last_evidence_at'] = iso
        items = []
        for bucket in groups.values():
            values = bucket.pop('mastery_values')
            mastery = round(sum(values) / len(values), 4) if values else 0
            subjects = list(bucket.pop('subjects').values())
            items.append({
                'name': bucket['name'],
                'mastery': mastery,
                'mastery_percent': round(mastery * 100, 2),
                'status': (
                    'mastered' if mastery >= .8 else
                    'learning' if mastery >= .6 else
                    'weak' if mastery >= .3 else 'unknown'
                ),
                'evidence_count': bucket['evidence_count'],
                'subjects': subjects,
                'subject_count': len(subjects),
                'concept_ids': bucket['concept_ids'],
                'last_evidence_at': bucket['last_evidence_at'],
            })
        items.sort(key=lambda item: (-item['mastery'], item['name'].casefold()))
        counts = {status: 0 for status in ('mastered', 'learning', 'weak', 'unknown')}
        for item in items:
            counts[item['status']] += 1
        return {
            'items': items,
            'count': len(items),
            'summary': {
                'concept_count': len(items),
                'mastered_count': counts['mastered'],
                'learning_count': counts['learning'],
                'weak_count': counts['weak'],
                'unknown_count': counts['unknown'],
                'average_mastery': round(sum(item['mastery'] for item in items) / len(items), 4) if items else None,
            },
        }, 200

    @classmethod
    async def concept_update(cls, db: AsyncSession, current_user, concept_id: int, data: dict):
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
        ).scalars().first()
        if concept is None:
            return {'code': 'NOT_FOUND', 'message': 'concept not found'}, 404
        name = data.get('name', data.get('title'))
        description = data.get('description')
        if name is None and description is None:
            return {'code': 'VALIDATION_ERROR', 'message': 'name_or_description_required'}, 400
        old_name = concept.name
        if name is not None:
            name = str(name).strip()
            if not name:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_required'}, 400
            if len(name) > 200:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_too_long'}, 400
            concept.name = name
        if description is not None:
            concept.description = str(description or '')
        dup = (
            await db.execute(
                select(KpConcept.concept_id)
                .where(KpConcept.subject_id == concept.subject_id, func.lower(KpConcept.name) == concept.name.casefold())
                .where(KpConcept.concept_id != concept.concept_id)
            )
        ).scalars().first()
        if dup is not None:
            return {'code': 'DUPLICATE_CONCEPT', 'message': 'concept_name_exists'}, 409
        snapshot_id = None
        changed_nodes = 0
        snapshot, graph_nodes, graph_edges = await latest_usable_graph(db, concept.subject_id)
        if snapshot:
            updated_nodes = []
            for raw in graph_nodes:
                node = dict(raw) if isinstance(raw, dict) else {'id': raw, 'name': raw}
                keys = {str(node.get(key)).strip().casefold() for key in ('id', 'concept_id', 'conceptId', 'name', 'title', 'label')
                        if node.get(key) is not None}
                concept_keys = {str(concept.concept_id), str(old_name).strip().casefold(), f'concept-{concept.concept_id}'}
                if keys & {value.casefold() for value in concept_keys}:
                    if name is not None:
                        node['name'] = concept.name
                        if 'title' in node:
                            node['title'] = concept.name
                        if 'label' in node:
                            node['label'] = concept.name
                    if description is not None:
                        node['description'] = concept.description
                    changed_nodes += 1
                updated_nodes.append(node)
            if changed_nodes:
                latest = (
                    await db.execute(
                        select(KpGraphSnapshot)
                        .where(KpGraphSnapshot.subject_id == concept.subject_id)
                        .order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc())
                    )
                ).scalars().first()
                version = (latest.version + 1) if latest else snapshot.version + 1
                created = KpGraphSnapshot(
                    subject_id=concept.subject_id, user_id=user_id_of(current_user),
                    nodes=updated_nodes, edges=graph_edges, version=version,
                )
                db.add(created)
                await db.flush()
                graph_store().save(created.nodes, created.edges, graph_id=created.snapshot_id, subject_id=concept.subject_id)
                snapshot_id = created.snapshot_id
        await audit(db, current_user, 'knowledge.concept.update', '/api/v1/knowledge/concepts/', {
            'concept_id': concept.concept_id, 'subject_id': concept.subject_id,
            'snapshot_id': snapshot_id, 'changed_nodes': changed_nodes,
        })
        await db.commit()
        return {
            'id': concept.concept_id, 'subject_id': concept.subject_id,
            'name': concept.name, 'description': concept.description,
            'snapshot_id': snapshot_id, 'changed_nodes': changed_nodes,
        }, 200

    @classmethod
    async def relation_create(cls, db: AsyncSession, current_user, data: dict):
        subject_id = data.get('subject_id')
        subject = await subject_for(db, subject_id)
        if subject is None:
            return {'code': 'NOT_FOUND', 'message': 'subject not found'}, 404
        snapshot, graph_nodes, graph_edges = await latest_usable_graph(db, subject.subject_id)
        if snapshot is None:
            return {'code': 'NO_GRAPH', 'message': 'build a knowledge graph before editing relations'}, 409
        edges = _relation_copy_edges(snapshot.edges)
        edge, error = _relation_fields({}, data, _relation_node_aliases(graph_nodes), creating=True)
        if error:
            return {'code': error[0], 'message': error[1]}, 422 if error[0] == 'SELF_LOOP' else 400
        edges.append(edge)
        report = validate_graph(snapshot.nodes, edges)
        if not report['valid']:
            return {'code': 'GRAPH_INVALID', 'message': 'relation would make the graph invalid', 'details': report['details']}, 422
        nodes, edges = normalize_graph(snapshot.nodes, edges)
        latest = (
            await db.execute(
                select(KpGraphSnapshot)
                .where(KpGraphSnapshot.subject_id == subject.subject_id)
                .order_by(KpGraphSnapshot.version.desc(), KpGraphSnapshot.snapshot_id.desc())
            )
        ).scalars().first()
        created = KpGraphSnapshot(
            subject_id=subject.subject_id, user_id=user_id_of(current_user),
            nodes=nodes, edges=edges, version=(latest.version + 1) if latest else snapshot.version + 1,
        )
        db.add(created)
        await db.flush()
        sync = graph_store().save(created.nodes, created.edges, graph_id=created.snapshot_id, subject_id=created.subject_id)
        index = len(edges) - 1
        await audit(db, current_user, 'knowledge.relation.create', '/api/v1/knowledge/relations/', {
            'snapshot_id': created.snapshot_id, 'subject_id': subject.subject_id,
            'from': edge['from'], 'to': edge['to'], 'relation': edge.get('relation'),
        })
        await db.commit()
        return {
            'relation': _relation_payload(created, edges[index], index),
            'snapshot_id': created.snapshot_id, 'version': created.version, 'graph': sync,
        }, 201

    @classmethod
    async def relation_update(cls, db: AsyncSession, current_user, relation_id: str, data: dict, *, deleting: bool):
        snapshot, index = await cls._relation_snapshot_ref(db, relation_id)
        if snapshot is None or index is None:
            return {'code': 'NOT_FOUND', 'message': 'relation not found'}, 404
        raw_edges = _relation_copy_edges(snapshot.edges)
        if index < 0 or index >= len(raw_edges):
            return {'code': 'NOT_FOUND', 'message': 'relation not found'}, 404
        current = raw_edges[index]
        if deleting:
            del raw_edges[index]
        else:
            edge, error = _relation_fields(current, data, _relation_node_aliases(snapshot.nodes))
            if error:
                return {'code': error[0], 'message': error[1]}, 422 if error[0] == 'SELF_LOOP' else 400
            raw_edges[index] = edge
        report = validate_graph(snapshot.nodes, raw_edges)
        if not report['valid']:
            return {'code': 'GRAPH_INVALID', 'message': 'relation update would make the graph invalid', 'details': report['details']}, 422
        nodes, edges = normalize_graph(snapshot.nodes, raw_edges)
        latest = (
            await db.execute(
                select(KpGraphSnapshot)
                .where(KpGraphSnapshot.subject_id == snapshot.subject_id)
                .order_by(KpGraphSnapshot.version.desc(), KpGraphSnapshot.snapshot_id.desc())
            )
        ).scalars().first()
        created = KpGraphSnapshot(
            subject_id=snapshot.subject_id, user_id=user_id_of(current_user),
            nodes=nodes, edges=edges, version=(latest.version + 1) if latest else snapshot.version + 1,
        )
        db.add(created)
        await db.flush()
        sync = graph_store().save(created.nodes, created.edges, graph_id=created.snapshot_id, subject_id=created.subject_id)
        await audit(db, current_user, 'knowledge.relation.delete' if deleting else 'knowledge.relation.update', '/api/v1/knowledge/relations/', {
            'relation_id': str(relation_id), 'source_snapshot_id': snapshot.snapshot_id,
            'snapshot_id': created.snapshot_id, 'subject_id': snapshot.subject_id,
        })
        await db.commit()
        payload = {'snapshot_id': created.snapshot_id, 'version': created.version, 'graph': sync, 'deleted': deleting}
        if not deleting:
            payload['relation'] = _relation_payload(created, edges[index], index)
        return payload, 200

    @classmethod
    async def _relation_snapshot_ref(cls, db: AsyncSession, relation_id):
        value = str(relation_id or '').strip()
        if not value:
            return None, None
        match = re.fullmatch(r'(\d+):(\d+)', value)
        if match:
            snapshot = (
                await db.execute(select(KpGraphSnapshot).where(KpGraphSnapshot.snapshot_id == int(match.group(1))))
            ).scalars().first()
            return (snapshot, int(match.group(2))) if snapshot else (None, None)
        snapshots = (
            await db.execute(
                select(KpGraphSnapshot).order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc())
            )
        ).scalars().all()
        for snapshot in snapshots:
            for index, edge in enumerate(snapshot.edges or []):
                if isinstance(edge, dict) and str(edge.get('id', '')).strip() == value:
                    return snapshot, index
        return None, None

    @classmethod
    async def list_snapshots(cls, db: AsyncSession, current_user):
        query = select(KpGraphSnapshot)
        if not is_admin(current_user):
            owned_subjects = select(KpSubject.subject_id).where(KpSubject.user_id == user_id_of(current_user))
            query = query.where(KpGraphSnapshot.subject_id.in_(owned_subjects))
        snapshots = (
            await db.execute(query.order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc()))
        ).scalars().all()
        return [
            {'id': g.snapshot_id, 'subject_id': g.subject_id, 'nodes': g.nodes, 'edges': g.edges, 'version': g.version}
            for g in snapshots
        ]

    @classmethod
    async def create_snapshot(cls, db: AsyncSession, current_user, data: dict):
        subject_id = data.get('subject_id')
        if not subject_id:
            return {'error': 'subject_id_required'}, 400
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'error': 'subject_not_found'}, 404
        nodes, edges = data.get('nodes', []), data.get('edges', [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return {'error': 'nodes_and_edges_must_be_arrays'}, 400
        nodes, edges = normalize_graph(nodes, edges)
        node_ids = [node['id'] for node in nodes]
        edge_pairs = [(edge['from'], edge['to']) for edge in edges]
        if not validate_dag(node_ids, edge_pairs):
            return {'error': 'invalid_graph', 'code': 'INVALID_GRAPH'}, 422
        if data.get('nodes') and not nodes:
            return {'error': 'valid_nodes_required'}, 400
        if data.get('edges') and not edges:
            return {'error': 'valid_edges_required'}, 400
        latest = (
            await db.execute(
                select(KpGraphSnapshot)
                .where(KpGraphSnapshot.subject_id == subject.subject_id)
                .order_by(KpGraphSnapshot.create_time.desc(), KpGraphSnapshot.snapshot_id.desc())
            )
        ).scalars().first()
        version = (latest.version + 1) if latest else 1
        if latest and latest.nodes == nodes and latest.edges == edges:
            sync = graph_store().save(latest.nodes, latest.edges, graph_id=latest.snapshot_id, subject_id=latest.subject_id)
            return {'id': latest.snapshot_id, 'version': latest.version, 'nodes': latest.nodes, 'edges': latest.edges,
                    'graph': sync, 'created': False}, 200
        for node in nodes:
            name = str(node.get('name') or node.get('title') or node.get('label') or node.get('id') or '').strip()
            if not name:
                continue
            description = node.get('description', node.get('content', ''))
            if not isinstance(description, str):
                description = str(description or '')
            concept = (
                await db.execute(
                    select(KpConcept)
                    .where(KpConcept.subject_id == subject.subject_id, func.lower(KpConcept.name) == name.casefold())
                    .order_by(KpConcept.concept_id)
                )
            ).scalars().first()
            if concept is None:
                db.add(KpConcept(subject_id=subject.subject_id, name=name[:200], description=description))
            elif description and not concept.description:
                concept.description = description
        snapshot = KpGraphSnapshot(subject_id=subject.subject_id, user_id=user_id_of(current_user), nodes=nodes, edges=edges, version=version)
        db.add(snapshot)
        await db.flush()
        sync = graph_store().save(snapshot.nodes, snapshot.edges, graph_id=snapshot.snapshot_id, subject_id=subject.subject_id)
        await audit(db, current_user, 'graph.snapshot', '/api/v1/graph/snapshots/', {'id': snapshot.snapshot_id, 'backend': sync['backend']})
        await db.commit()
        return {'id': snapshot.snapshot_id, 'version': snapshot.version, 'nodes': snapshot.nodes, 'edges': snapshot.edges,
                'graph': sync, 'created': True}, 201

    @classmethod
    async def sync_snapshot(cls, db: AsyncSession, current_user, snapshot_id: int):
        snapshot = (
            await db.execute(select(KpGraphSnapshot).where(KpGraphSnapshot.snapshot_id == snapshot_id))
        ).scalars().first()
        if snapshot is None:
            return {'error': 'not_found'}, 404
        subject = await subject_for(db, snapshot.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'error': 'forbidden'}, 403
        result = graph_store().save(snapshot.nodes, snapshot.edges, graph_id=snapshot.snapshot_id, subject_id=snapshot.subject_id)
        return {'id': snapshot.snapshot_id, 'graph': result}, 200

    @classmethod
    async def lesson(cls, db: AsyncSession, current_user, concept_id: int, *, duration_sec=0, metadata=None):
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
        ).scalars().first()
        if concept is None:
            return {'code': 'NOT_FOUND'}, 404
        subject = await subject_for(db, concept.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        concept.subject = subject
        await record_learning_event(
            db, user_id_of(current_user), 'lesson_open',
            subject_id=concept.subject_id, concept_id=concept.concept_id,
            duration_sec=duration_sec, metadata=metadata if isinstance(metadata, dict) else {},
        )
        payload = await _lesson_response(db, concept)
        await db.commit()
        return payload, 200

    @classmethod
    async def chat(cls, db: AsyncSession, current_user, concept_id: int, data: dict):
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
        ).scalars().first()
        if concept is None:
            return {'code': 'NOT_FOUND'}, 404
        subject = await subject_for(db, concept.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        concept.subject = subject
        requested_subject = data.get('subject_id')
        if requested_subject not in (None, '', str(concept.subject_id), concept.subject_id):
            return {'code': 'NOT_FOUND'}, 404
        question = str(data.get('question') or data.get('message') or '').strip()
        if not question:
            return {'code': 'VALIDATION_ERROR', 'message': 'question_required'}, 400
        evidence = await _evidence_for(db, subject, concept, f'{concept.name} {question}')
        context = []
        for row in evidence:
            if row.get('type') in {'chunk', 'resource', 'concept'}:
                context.append(f"[{row.get('source')}] {row.get('snippet', '')}")
            elif row.get('type') == 'graph_relation':
                context.append(f"{row.get('source')} -[{row.get('relation')}]-> {row.get('target')}")
        from module_user.entity.do.profile_do import KpProfile
        profile = (
            await db.execute(select(KpProfile).where(KpProfile.user_id == user_id_of(current_user)))
        ).scalars().first()
        learner = ''
        if profile is not None:
            learner = f'level={profile.level}; major={profile.major}; goal={profile.goals}'
        messages = [
            {'role': 'system', 'content': 'Answer in clear Chinese using only <retrieved_context>. Say when the context is insufficient.'},
            {'role': 'user', 'content': (
                f'<concept>{concept.name}: {concept.description}</concept>\n'
                f'<learner_profile>{learner}</learner_profile>\n'
                f'<retrieved_context>\n{"\n".join(context)[:7000]}\n</retrieved_context>\n'
                f'Question: {question}'
            )},
        ]
        source = 'offline'
        try:
            answer = str(await AiService.chat(
                db, messages, prompt_code='tutor_chat', concept=concept.name, question=question,
            ) or '').strip()
            if not answer:
                raise RuntimeError('empty provider answer')
            source = 'provider'
        except Exception:
            definition = concept.description or f'{concept.name} 是当前学习对象中的一个知识点。'
            snippets = [row.get('snippet') for row in evidence if row.get('snippet')]
            answer = f'围绕“{concept.name}”：{definition}'
            if snippets:
                fragments = text_fragments(snippets[0], 1)
                if fragments:
                    answer += f'\n\n当前资料提到：{fragments[0]}'
            prerequisites = [
                row['source'] for row in evidence
                if row.get('type') == 'graph_relation' and is_prerequisite_edge(row)
                and row.get('target_id') == concept.concept_id
            ]
            if prerequisites:
                answer += f'\n\n建议先复习：{"、".join(prerequisites)}。'
        evidence_ids = [row['id'] for row in evidence if row.get('id')]
        return {
            'answer': answer,
            'evidence': evidence,
            'evidence_ids': evidence_ids,
            'source': source,
            'concept_id': concept.concept_id,
            'subject_id': concept.subject_id,
            'question': question,
            'session_id': data.get('session_id'),
            'trace_id': f'chat-{uuid.uuid4().hex}',
        }, 200

    @classmethod
    async def list_notes(cls, db: AsyncSession, current_user, *, subject_id=None, concept_id=None, query=''):
        q = select(KpNote)
        if not is_admin(current_user):
            q = q.where(KpNote.user_id == user_id_of(current_user))
        if subject_id not in (None, ''):
            subject = await cls._resolve_subject(db, current_user, subject_id)
            if subject is False:
                return {'code': 'NOT_FOUND', 'message': 'subject_not_found'}, 404
            q = q.where(KpNote.subject_id == (subject.subject_id if subject else None))
        if concept_id not in (None, ''):
            concept = await cls._resolve_concept(db, current_user, concept_id)
            if concept is False:
                return {'code': 'NOT_FOUND', 'message': 'concept_not_found'}, 404
            q = q.where(KpNote.concept_id == (concept.concept_id if concept else None))
        query = str(query or '').strip()
        if query:
            q = q.where((KpNote.title.ilike(f'%{query}%')) | (KpNote.content.ilike(f'%{query}%')))
        notes = (
            await db.execute(q.order_by(KpNote.update_time.desc(), KpNote.note_id.desc()))
        ).scalars().all()
        items = []
        for note in notes:
            items.append(await cls._note_payload(db, note))
        return {'items': items}, 200

    @classmethod
    async def _resolve_subject(cls, db: AsyncSession, current_user, subject_id):
        if subject_id in (None, '', 'null'):
            return None
        subject = await subject_for(db, subject_id)
        if subject is None:
            return False
        if not is_admin(current_user) and subject.user_id != user_id_of(current_user):
            return False
        return subject

    @classmethod
    async def _resolve_concept(cls, db: AsyncSession, current_user, concept_id):
        if concept_id in (None, '', 'null'):
            return None
        try:
            concept_id = int(concept_id)
        except (TypeError, ValueError):
            return False
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
        ).scalars().first()
        if concept is None:
            return False
        subject = await subject_for(db, concept.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return False
        return concept

    @classmethod
    async def _note_payload(cls, db: AsyncSession, note):
        subject = await subject_for(db, note.subject_id) if note.subject_id else None
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == note.concept_id))
        ).scalars().first() if note.concept_id else None
        return {
            'id': note.note_id,
            'title': note.title,
            'content': note.content,
            'subject_id': note.subject_id,
            'subject_name': subject.name if subject else None,
            'concept_id': note.concept_id,
            'concept_name': concept.name if concept else None,
            'created_at': iso_time(note.create_time),
            'updated_at': iso_time(note.update_time),
        }

    @classmethod
    async def create_note(cls, db: AsyncSession, current_user, data: dict):
        title = str(data.get('title', '')).strip() or '未命名笔记'
        if len(title) > 255:
            return {'code': 'VALIDATION_ERROR', 'message': 'title_too_long'}, 400
        if not isinstance(data.get('content', ''), str):
            return {'code': 'VALIDATION_ERROR', 'message': 'content_must_be_string'}, 400
        subject, concept, error = await cls._note_links(db, current_user, data)
        if error:
            return error
        note = KpNote(
            user_id=user_id_of(current_user), title=title, content=data.get('content', ''),
            subject_id=subject.subject_id if subject else None,
            concept_id=concept.concept_id if concept else None,
        )
        db.add(note)
        await db.flush()
        await audit(db, current_user, 'note.create', '/api/v1/notes/', {'id': note.note_id})
        await db.commit()
        return await cls._note_payload(db, note), 201

    @classmethod
    async def update_note(cls, db: AsyncSession, current_user, data: dict):
        note_id = data.get('id', data.get('note_id'))
        if not note_id:
            return {'code': 'VALIDATION_ERROR', 'message': 'note_id_required'}, 400
        if not str(note_id).isdigit():
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        q = select(KpNote).where(KpNote.note_id == int(note_id))
        if not is_admin(current_user):
            q = q.where(KpNote.user_id == user_id_of(current_user))
        note = (await db.execute(q)).scalars().first()
        if note is None:
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        if 'title' in data:
            title = str(data.get('title', '')).strip()
            if not title:
                return {'code': 'VALIDATION_ERROR', 'message': 'title_required'}, 400
            note.title = title
        if 'content' in data:
            if not isinstance(data.get('content'), str):
                return {'code': 'VALIDATION_ERROR', 'message': 'content_must_be_string'}, 400
            note.content = data['content']
        subject, concept, error = await cls._note_links(db, current_user, data, note)
        if error:
            return error
        note.subject_id = subject.subject_id if subject else None
        note.concept_id = concept.concept_id if concept else None
        await audit(db, current_user, 'note.update', '/api/v1/notes/', {'id': note.note_id})
        await db.commit()
        return await cls._note_payload(db, note), 200

    @classmethod
    async def _note_links(cls, db: AsyncSession, current_user, data: dict, current=None):
        subject = None
        concept = None
        if current is not None:
            if current.subject_id:
                subject = await subject_for(db, current.subject_id)
            if current.concept_id:
                concept = (
                    await db.execute(select(KpConcept).where(KpConcept.concept_id == current.concept_id))
                ).scalars().first()
        if 'subject_id' in data:
            resolved = await cls._resolve_subject(db, current_user, data.get('subject_id'))
            if resolved is False:
                return None, None, {'code': 'NOT_FOUND', 'message': 'subject_not_found'}, 404
            subject = resolved
        if 'concept_id' in data:
            resolved = await cls._resolve_concept(db, current_user, data.get('concept_id'))
            if resolved is False:
                return None, None, {'code': 'NOT_FOUND', 'message': 'concept_not_found'}, 404
            concept = resolved
        if concept is not None:
            if subject is None:
                subject = await subject_for(db, concept.subject_id)
            elif subject.subject_id != concept.subject_id:
                return None, None, {'code': 'VALIDATION_ERROR', 'message': 'concept_subject_mismatch'}, 400
        return subject, concept, None
