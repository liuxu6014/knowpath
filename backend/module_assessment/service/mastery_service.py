"""Assessment scoring and mastery evidence logic.

Port of the Django ``apps/assessment/services.py`` module: answer grading,
EMA mastery updates, and prerequisite-aware learning-path node construction.
"""
import re

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.graph.planner import topological_order
from core.graph.resolver import latest_usable_graph, restrict_concepts_to_graph
from core.graph.validator import is_prerequisite_edge, validate_dag
from module_assessment.entity.do.assessment_do import (
    KpAssessment,
    KpAssessmentAttempt,
    KpMasteryHistory,
    KpMasteryRecord,
)
from module_knowledge.entity.do.concept_do import KpConcept
from module_learning.entity.do.learning_path_do import KpLearningPath
from module_quiz.entity.do.quiz_do import KpQuiz
from utils.time_util import TimezoneUtil

MASTERED_THRESHOLD = 80.0


def public_questions(questions):
    """Strip answers/explanations so the browser only sees selectable questions."""
    return [
        {k: v for k, v in q.items() if k not in ('answer', 'correct_answer', 'explanation', 'rubric')}
        for q in (questions or [])
        if isinstance(q, dict)
    ]


def correct_answer(question, answer):
    """Grade one answer against a question's expected answer(s)."""
    if not isinstance(question, dict):
        return False
    if answer is None or isinstance(answer, (dict, list, bool)) or not str(answer).strip():
        return False
    expected = question.get('answer', question.get('correct_answer'))
    if expected is None:
        return False
    expected = expected if isinstance(expected, list) else [expected]
    options = question.get('options') or []
    if not isinstance(options, list):
        options = []

    def normalize(value):
        value = str(value).strip()
        if options and value not in options:
            if value.isdigit() and int(value) < len(options):
                value = str(options[int(value)])
            elif len(value) == 1 and 'A' <= value.upper() < chr(65 + len(options)):
                value = str(options[ord(value.upper()) - 65])
        return value.casefold()

    return normalize(answer) in {normalize(value) for value in expected}


def _mastery_status(value):
    """Return the documented status for a normalized 0..1 mastery value."""
    if value < 0.30:
        return 'unknown'
    if value < 0.60:
        return 'weak'
    if value < 0.80:
        return 'learning'
    return 'mastered'


def _mastery_value(values, concept_id):
    """Read mastery while tolerating legacy string keys."""
    value = (values or {}).get(concept_id, (values or {}).get(str(concept_id), 0))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _completed_value(value):
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'done', 'completed'}
    return bool(value)


def _previous_path_nodes(previous_nodes):
    """Index previous path metadata by concept id, including legacy ids."""
    indexed = {}
    for raw in previous_nodes or []:
        if not isinstance(raw, dict):
            continue
        concept_id = raw.get('concept_id')
        if concept_id is None:
            node_id = str(raw.get('id', '')).strip()
            if node_id.startswith('concept-'):
                concept_id = node_id[len('concept-'):]
        if concept_id is not None and str(concept_id).strip():
            indexed[str(concept_id).strip()] = raw
    return indexed


def build_learning_path_nodes(concepts, edges, values, previous_nodes=None,
                              mastered_threshold=MASTERED_THRESHOLD):
    """Build a complete prerequisite-aware path and retain progress history."""
    concepts = list(concepts or [])
    if not concepts:
        return [], 'active'

    concept_ids = [concept.concept_id for concept in concepts]
    mastery = {concept_id: _mastery_value(values, concept_id) for concept_id in concept_ids}
    by_key = {}
    for concept in concepts:
        for key in (
            str(concept.concept_id),
            f'concept-{concept.concept_id}',
            str(concept.name),
            str(concept.name).replace(' ', '-'),
        ):
            by_key.setdefault(str(key).strip().casefold(), concept.concept_id)
    resolved_edges = []
    seen_edges = set()
    for edge in edges or []:
        if isinstance(edge, dict):
            if not is_prerequisite_edge(edge):
                continue
            source = edge.get('from', edge.get('source'))
            target = edge.get('to', edge.get('target'))
        else:
            try:
                source, target = edge
            except (TypeError, ValueError):
                continue
        source_id = by_key.get(str(source).strip().casefold())
        target_id = by_key.get(str(target).strip().casefold())
        if source_id is None or target_id is None or source_id == target_id:
            continue
        pair = (source_id, target_id)
        if pair not in seen_edges:
            seen_edges.add(pair)
            resolved_edges.append(pair)
    order = topological_order(concept_ids, resolved_edges, mastery)
    previous = _previous_path_nodes(previous_nodes)
    by_id = {concept.concept_id: concept for concept in concepts}

    prerequisites = {concept_id: [] for concept_id in concept_ids}
    dependents = {concept_id: [] for concept_id in concept_ids}
    for source_id, target_id in resolved_edges:
        prerequisites[target_id].append(source_id)
        dependents[source_id].append(target_id)

    nodes = []
    for concept_id in order:
        concept = by_id[concept_id]
        prior = previous.get(str(concept_id), {})
        completed = _completed_value(prior.get('completed')) or mastery[concept_id] >= float(mastered_threshold)
        node = {
            'id': f'concept-{concept_id}',
            'concept_id': concept_id,
            'title': concept.name,
            'name': concept.name,
            'description': concept.description,
            'mastery': mastery[concept_id],
            'mastery_percent': mastery[concept_id],
            'completed': completed,
            'order_no': len(nodes) + 1,
            'prerequisite_concept_ids': list(prerequisites.get(concept_id, [])),
            'dependent_concept_ids': list(dependents.get(concept_id, [])),
        }
        for key, value in prior.items():
            if key not in {'id', 'concept_id', 'title', 'mastery', 'completed'}:
                node.setdefault(key, value)
        nodes.append(node)

    completed_ids = {node['concept_id'] for node in nodes if node['completed']}
    current_id = next(
        (node['concept_id'] for node in nodes
         if not node['completed'] and all(prereq in completed_ids for prereq in prerequisites.get(node['concept_id'], []))),
        None,
    )
    for node in nodes:
        concept_id = node['concept_id']
        if node['completed']:
            node['state'] = 'completed'
            node['status'] = 'completed'
            node['reason_codes'] = ['MASTERED' if node['mastery'] >= float(mastered_threshold) else 'COMPLETED_PREVIOUSLY']
        elif concept_id == current_id:
            node['state'] = 'current'
            node['status'] = 'current'
            reasons = ['PREREQUISITES_SATISFIED']
            if node['mastery'] < float(mastered_threshold):
                reasons.append('CURRENT_WEAKNESS')
            node['reason_codes'] = reasons
        elif all(prereq in completed_ids for prereq in prerequisites.get(concept_id, [])):
            node['state'] = 'pending'
            node['status'] = 'pending'
            node['reason_codes'] = ['PREREQUISITES_SATISFIED']
        else:
            node['state'] = 'blocked'
            node['status'] = 'blocked'
            node['reason_codes'] = ['PREREQUISITES_INCOMPLETE']

    status = 'completed' if nodes and all(node['completed'] for node in nodes) else 'active'
    return nodes, status


class MasteryService:
    """异步掌握度与测评打分服务层。"""

    @classmethod
    async def mastery_values(cls, db: AsyncSession, user_id: int, subject_id: int) -> dict:
        """Answer history is the authoritative mastery source for a subject."""
        values: dict = {}
        rows = (
            await db.execute(
                select(KpAssessmentAttempt, KpAssessment)
                .join(KpAssessment, KpAssessment.assessment_id == KpAssessmentAttempt.assessment_id)
                .where(
                    KpAssessmentAttempt.user_id == user_id,
                    KpAssessment.subject_id == subject_id,
                )
                .order_by(KpAssessmentAttempt.create_time, KpAssessmentAttempt.attempt_id)
            )
        ).all()
        for attempt, assessment in rows:
            questions = {
                str(q.get('id', i)): q
                for i, q in enumerate(assessment.questions or [])
                if isinstance(q, dict)
            }
            answers = attempt.answers if isinstance(attempt.answers, dict) else {}
            for item in answers.get('items', []):
                if not isinstance(item, dict):
                    continue
                cid = questions.get(str(item.get('question_id')), {}).get('concept_id')
                if cid is not None:
                    correct = item.get('correct')
                    if isinstance(correct, str):
                        correct = correct.strip().lower() in {'1', 'true', 'yes', 'correct'}
                    values[cid] = round(values.get(cid, values.get(str(cid), 0)) * .7 + (100 if correct else 0) * .3, 4)
        return values

    @classmethod
    async def submit(cls, db: AsyncSession, assessment: KpAssessment, user_id: int, answers) -> dict:
        """Grade a full answer set, persist mastery evidence, refresh the path."""
        questions = assessment.questions
        if not isinstance(questions, list) or not questions or any(not isinstance(q, dict) for q in questions):
            raise ValueError('answers_required')
        if isinstance(answers, list):
            normalized = {}
            for item in answers:
                if not isinstance(item, dict):
                    raise ValueError('complete_answers_required')
                question_id = item.get('question_id', item.get('id'))
                if question_id is None or 'answer' not in item:
                    raise ValueError('complete_answers_required')
                key = str(question_id)
                if key in normalized:
                    raise ValueError('duplicate_answer_id')
                normalized[key] = item.get('answer')
            answers = normalized
        if not isinstance(answers, dict):
            raise ValueError('answers_required')
        keys = {str(q.get('id', i)) for i, q in enumerate(questions)}
        if set(answers) != keys or any(
            isinstance(v, (dict, list, bool)) or v is None or not str(v).strip()
            for v in answers.values()
        ):
            raise ValueError('complete_answers_required')

        prior_values = await cls.mastery_values(db, user_id, assessment.subject_id)
        details = []
        for i, q in enumerate(questions):
            key = str(q.get('id', i))
            details.append({
                'question_id': key,
                'answer': answers[key],
                'correct': correct_answer(q, answers[key]),
                'expected_answer': q.get('answer', q.get('correct_answer')),
                'explanation': q.get('explanation', ''),
            })
        score = round(100 * sum(x['correct'] for x in details) / len(details), 2)
        attempt = KpAssessmentAttempt(
            assessment_id=assessment.assessment_id,
            user_id=user_id,
            answers={'items': details},
            score=score,
        )
        db.add(attempt)
        await db.flush()
        await cls._persist_mastery_evidence(db, assessment, user_id, attempt, details, prior_values)
        await cls._refresh_learning_path(db, user_id, assessment.subject_id)
        await db.commit()
        return {
            'id': attempt.attempt_id,
            'assessment_id': assessment.assessment_id,
            'score': score,
            'correct': sum(x['correct'] for x in details),
            'total': len(details),
            'details': details,
        }

    @classmethod
    async def _persist_mastery_evidence(
        cls, db: AsyncSession, assessment: KpAssessment, user_id: int, attempt: KpAssessmentAttempt,
        details: list, prior_values: dict | None = None,
    ) -> None:
        """Persist one current snapshot and one immutable history row per answer."""
        is_quiz = (
            await db.execute(
                select(KpQuiz.quiz_id).where(KpQuiz.assessment_id == assessment.assessment_id).limit(1)
            )
        ).scalars().first() is not None
        reason = 'quiz' if is_quiz else 'diagnostic'
        running = dict(prior_values or {})
        now = TimezoneUtil.utc_now()
        questions = {
            str(q.get('id', i)): q
            for i, q in enumerate(assessment.questions or [])
            if isinstance(q, dict)
        }
        for item in details:
            question = questions.get(str(item.get('question_id')), {})
            concept_id = question.get('concept_id')
            if concept_id is None:
                continue
            try:
                concept_id = int(concept_id)
            except (TypeError, ValueError):
                continue
            before_percent = _mastery_value(running, concept_id)
            after_percent = round(before_percent * .7 + (100 if item.get('correct') else 0) * .3, 4)
            running[concept_id] = after_percent
            before = round(max(0.0, min(1.0, before_percent / 100)), 4)
            after = round(max(0.0, min(1.0, after_percent / 100)), 4)
            record = (
                await db.execute(
                    select(KpMasteryRecord).where(
                        KpMasteryRecord.user_id == user_id,
                        KpMasteryRecord.concept_id == concept_id,
                    )
                )
            ).scalars().first()
            if record is None:
                record = KpMasteryRecord(
                    user_id=user_id,
                    concept_id=concept_id,
                    mastery=before,
                    confidence=0,
                    status=_mastery_status(before),
                )
                db.add(record)
                await db.flush()
            if record.evidence_count:
                before = float(record.mastery)
                after = round(max(0.0, min(1.0, before * .7 + (0.3 if item.get('correct') else 0))), 4)
            record.mastery = after
            record.evidence_count = (record.evidence_count or 0) + 1
            record.confidence = min(1, record.evidence_count / 5)
            record.status = _mastery_status(after)
            record.last_evidence_at = now
            record.update_time = now
            db.add(KpMasteryHistory(
                mastery_record_id=record.record_id,
                before_value=before,
                after_value=after,
                delta=round(after - before, 4),
                reason=reason,
                evidence_type='assessment_attempt',
                evidence_id=attempt.attempt_id,
                calculation_detail={
                    'algorithm': 'ema_v1',
                    'alpha': 0.3,
                    'correct': bool(item.get('correct')),
                    'score': attempt.score,
                    'question_id': str(item.get('question_id')),
                },
            ))

    @classmethod
    async def _supersede_learning_paths(cls, db: AsyncSession, user_id: int, subject_id: int) -> None:
        """Keep one current path while retaining old versions for history."""
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
    async def _refresh_learning_path(cls, db: AsyncSession, user_id: int, subject_id: int) -> KpLearningPath | None:
        """Create a user-scoped path ordered by weakest mastery after an attempt."""
        values = await cls.mastery_values(db, user_id, subject_id)
        concepts = (
            await db.execute(
                select(KpConcept).where(KpConcept.subject_id == subject_id).order_by(KpConcept.concept_id)
            )
        ).scalars().all()
        _, graph_nodes, snapshot_edges = await latest_usable_graph(db, subject_id)
        concepts = restrict_concepts_to_graph(concepts, graph_nodes)
        if not concepts:
            return None
        previous = (
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
        by_key = {}
        for concept in concepts:
            for key in (
                str(concept.concept_id),
                f'concept-{concept.concept_id}',
                str(concept.name),
                re.sub(r'\s+', '-', str(concept.name)),
            ):
                by_key.setdefault(str(key).strip().lower(), concept.concept_id)
        edges = []
        for edge in snapshot_edges:
            if not isinstance(edge, dict) or not is_prerequisite_edge(edge):
                continue
            a = by_key.get(str(edge.get('from', edge.get('source', ''))).strip().lower())
            b = by_key.get(str(edge.get('to', edge.get('target', ''))).strip().lower())
            if a and b and a != b:
                edges.append((a, b))
        concept_ids = [c.concept_id for c in concepts]
        if not validate_dag(concept_ids, edges):
            edges = []
        nodes, status = build_learning_path_nodes(
            concepts,
            edges,
            values,
            previous.nodes if previous else None,
        )
        await cls._supersede_learning_paths(db, user_id, subject_id)
        path = KpLearningPath(
            user_id=user_id,
            subject_id=subject_id,
            title='我的个性化学习路径',
            nodes=nodes,
            status=status,
        )
        db.add(path)
        await db.flush()
        return path
