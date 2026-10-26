"""Diagnostic assessment, mastery profile, and mistake review service."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin, user_id_of
from core.domain import active_concepts, record_learning_event, subject_for
from core.graph.resolver import latest_usable_graph
from core.helpers import bool_value, safe_float
from module_assessment.entity.do.assessment_do import (
    KpAssessment,
    KpAssessmentAttempt,
    KpMasteryHistory,
    KpMasteryRecord,
)
from module_assessment.service.mastery_service import MasteryService, _mastery_value, public_questions
from module_knowledge.entity.do.concept_do import KpConcept
from module_quiz.entity.do.quiz_do import KpQuiz
from module_subject.entity.do.subject_do import KpSubject


class AssessmentService:
    """异步测评服务层。"""

    @classmethod
    async def _subject_for(cls, db: AsyncSession, current_user, subject_id: int):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return None
        return subject

    @classmethod
    async def start(cls, db: AsyncSession, current_user, subject_id: int, options: dict):
        subject = await cls._subject_for(db, current_user, subject_id)
        if subject is None:
            return {'code': 'NOT_FOUND'}, 404
        try:
            question_count = int(options.get('question_count', 20))
        except (TypeError, ValueError):
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_question_count'}, 400
        if not 1 <= question_count <= 50:
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_question_count'}, 400
        _, graph_nodes, _ = await latest_usable_graph(db, subject_id)
        concepts = await active_concepts(db, subject_id, graph_nodes)
        active_ids = {str(concept.concept_id) for concept in concepts}
        existing = (
            await db.execute(
                select(KpAssessment)
                .outerjoin(KpQuiz, KpQuiz.assessment_id == KpAssessment.assessment_id)
                .where(KpAssessment.subject_id == subject_id, KpQuiz.quiz_id.is_(None))
                .order_by(KpAssessment.create_time.desc(), KpAssessment.assessment_id.desc())
            )
        ).scalars().first()
        candidate_concepts = concepts[:question_count]
        target_ids = {str(concept.concept_id) for concept in candidate_concepts}
        bound_ids = {
            str(question.get('concept_id'))
            for question in (existing.questions or [])
            if isinstance(question, dict) and question.get('concept_id') is not None
        } if existing is not None else set()
        legacy_generated = bool(
            existing is not None
            and existing.title == 'Initial assessment'
            and isinstance(existing.questions, list)
            and existing.questions
            and any(
                isinstance(question, dict)
                and question.get('concept_id') is not None
                and (not isinstance(question.get('options'), list) or len(question.get('options') or []) < 2)
                for question in existing.questions
            )
        )
        refresh = (
            existing is None
            or not (existing.questions if existing is not None else [])
            or bound_ids != target_ids
            or legacy_generated
        )
        if refresh:
            names = []
            seen_names = set()
            for item in concepts:
                name = str(item.name or '').strip()
                key = name.casefold()
                if name and key not in seen_names:
                    seen_names.add(key)
                    names.append(name)
            questions = []
            for concept in candidate_concepts:
                answer = str(concept.name or '').strip()
                description = str(concept.description or answer).strip()
                prompt = description[:240]
                distractors = [name for name in names if name.casefold() != answer.casefold()][:3]
                if not distractors:
                    distractors = ['其他概念']
                choices = [answer, *distractors]
                offset = concept.concept_id % len(choices)
                choices = choices[offset:] + choices[:offset]
                questions.append({
                    'id': f'c{concept.concept_id}',
                    'type': 'single',
                    'concept_id': concept.concept_id,
                    'question': f'以下哪一项最符合“{prompt}”所描述的知识概念？',
                    'options': choices,
                    'answer': answer,
                    'explanation': f'该描述对应概念“{answer}”。',
                })
            if not questions:
                return {'code': 'NO_QUESTIONS', 'message': 'Create concepts or add an assessment first.'}, 409
            existing = KpAssessment(subject_id=subject_id, title='起点测评', questions=questions)
            db.add(existing)
            await db.flush()
        questions = public_questions([
            question for question in (existing.questions or [])
            if not isinstance(question, dict)
            or question.get('concept_id') is None
            or str(question.get('concept_id')) in active_ids
        ])
        if not questions:
            return {'code': 'NO_QUESTIONS', 'message': 'Create concepts with descriptions or add an assessment first.'}, 409
        await record_learning_event(
            db, user_id_of(current_user), 'assessment_start',
            subject_id=subject_id,
            metadata={'assessment_id': existing.assessment_id, 'question_count': len(questions)},
        )
        await db.commit()
        return {
            'id': existing.assessment_id,
            'assessment_id': existing.assessment_id,
            'subject_id': subject_id,
            'title': existing.title,
            'status': 'running',
            'question_count': len(questions),
            'questions': questions,
        }, 201

    @classmethod
    async def list_assessments(cls, db: AsyncSession, current_user, subject_id=None, kind=None):
        query = select(KpAssessment)
        if not is_admin(current_user):
            owned_subjects = select(KpSubject.subject_id).where(KpSubject.user_id == user_id_of(current_user))
            query = query.where(KpAssessment.subject_id.in_(owned_subjects))
        if subject_id is not None:
            query = query.where(KpAssessment.subject_id == subject_id)
        if kind in {'diagnostic', 'assessment'}:
            query = query.outerjoin(KpQuiz, KpQuiz.assessment_id == KpAssessment.assessment_id).where(KpQuiz.quiz_id.is_(None))
        assessments = (
            await db.execute(query.order_by(KpAssessment.create_time.desc(), KpAssessment.assessment_id.desc()))
        ).scalars().all()
        items = []
        for assessment in assessments:
            is_quiz = (
                await db.execute(select(KpQuiz.quiz_id).where(KpQuiz.assessment_id == assessment.assessment_id).limit(1))
            ).scalars().first() is not None
            items.append({
                'id': assessment.assessment_id,
                'title': assessment.title,
                'subject_id': assessment.subject_id,
                'question_count': len(assessment.questions) if isinstance(assessment.questions, list) else 0,
                'kind': 'quiz' if is_quiz else 'assessment',
            })
        return {'items': items}, 200

    @classmethod
    async def create_assessment(cls, db: AsyncSession, current_user, data: dict):
        subject = await subject_for(db, data.get('subject_id'))
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'error': 'not_found'}, 404
        questions = data.get('questions')
        if not isinstance(questions, list) or not questions or len(questions) > 100 or any(
            not isinstance(q, dict) or q.get('answer', q.get('correct_answer')) is None for q in questions
        ):
            return {'error': 'valid_questions_required'}, 400
        if len({str(q.get('id', i)) for i, q in enumerate(questions)}) != len(questions):
            return {'error': 'duplicate_question_id'}, 400
        assessment = KpAssessment(title=str(data.get('title', 'Assessment'))[:255], subject_id=subject.subject_id, questions=questions)
        db.add(assessment)
        await db.commit()
        return {'id': assessment.assessment_id, 'title': assessment.title, 'questions': public_questions(assessment.questions)}, 201

    @classmethod
    async def detail(cls, db: AsyncSession, current_user, assessment_id: int):
        assessment = (
            await db.execute(select(KpAssessment).where(KpAssessment.assessment_id == assessment_id))
        ).scalars().first()
        if assessment is None:
            return {'code': 'NOT_FOUND'}, 404
        subject = await subject_for(db, assessment.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        return {
            'id': assessment.assessment_id,
            'title': assessment.title,
            'subject_id': assessment.subject_id,
            'questions': public_questions(assessment.questions),
        }, 200

    @classmethod
    async def attempt_history(cls, db: AsyncSession, current_user, assessment_id: int):
        assessment = (
            await db.execute(select(KpAssessment).where(KpAssessment.assessment_id == assessment_id))
        ).scalars().first()
        if assessment is None:
            return {'error': 'not_found'}, 404
        attempts = (
            await db.execute(
                select(KpAssessmentAttempt)
                .where(KpAssessmentAttempt.assessment_id == assessment_id, KpAssessmentAttempt.user_id == user_id_of(current_user))
                .order_by(KpAssessmentAttempt.create_time.desc(), KpAssessmentAttempt.attempt_id.desc())
            )
        ).scalars().all()
        return {
            'items': [
                {'id': x.attempt_id, 'score': x.score, 'answers': x.answers, 'created_at': x.create_time.isoformat()}
                for x in attempts
            ]
        }, 200

    @classmethod
    async def mastery_profile(cls, db: AsyncSession, current_user, subject_id: int):
        subject = await cls._subject_for(db, current_user, subject_id)
        if subject is None:
            return {'code': 'NOT_FOUND'}, 404
        values = await MasteryService.mastery_values(db, user_id_of(current_user), subject_id)
        concepts = await active_concepts(db, subject_id)
        items = []
        for concept in concepts:
            score = round(max(0.0, min(100.0, _mastery_value(values, concept.concept_id))), 2)
            items.append({
                'concept_id': concept.concept_id,
                'name': concept.name,
                'description': concept.description,
                'mastery': score,
                'mastery_percent': score,
                'status': 'mastered' if score >= 80 else 'learning' if score > 0 else 'unknown',
            })
        records = (
            await db.execute(
                select(KpMasteryRecord)
                .join(KpConcept, KpConcept.concept_id == KpMasteryRecord.concept_id)
                .where(KpMasteryRecord.user_id == user_id_of(current_user), KpConcept.subject_id == subject_id)
            )
        ).scalars().all()
        record_map = {row.concept_id: row for row in records}
        for item in items:
            row = record_map.get(item['concept_id'])
            if row:
                item.update({
                    'confidence': float(row.confidence or 0),
                    'evidence_count': row.evidence_count,
                    'status': row.status,
                    'updated_at': row.last_evidence_at.isoformat() if row.last_evidence_at else None,
                })
        return {'subject_id': subject_id, 'items': items}, 200

    @classmethod
    async def mastery_history(cls, db: AsyncSession, current_user, subject_id: int, limit: int = 100):
        subject = await cls._subject_for(db, current_user, subject_id)
        if subject is None:
            return {'code': 'NOT_FOUND'}, 404
        limit = max(1, min(200, limit))
        rows = (
            await db.execute(
                select(KpMasteryHistory, KpMasteryRecord, KpConcept)
                .join(KpMasteryRecord, KpMasteryRecord.record_id == KpMasteryHistory.mastery_record_id)
                .join(KpConcept, KpConcept.concept_id == KpMasteryRecord.concept_id)
                .where(KpMasteryRecord.user_id == user_id_of(current_user), KpConcept.subject_id == subject_id)
                .order_by(KpMasteryHistory.create_time.desc(), KpMasteryHistory.history_id.desc())
                .limit(limit)
            )
        ).all()
        items = [{
            'id': history.history_id,
            'concept_id': record.concept_id,
            'concept': concept.name,
            'before': float(history.before_value),
            'after': float(history.after_value),
            'delta': float(history.delta),
            'reason': history.reason,
            'evidence_type': history.evidence_type,
            'evidence_id': history.evidence_id,
            'calculation_detail': history.calculation_detail,
            'created_at': history.create_time.isoformat(),
        } for history, record, concept in rows]
        return {'subject_id': subject_id, 'items': items, 'count': len(items)}, 200

    @classmethod
    async def mistakes(cls, db: AsyncSession, current_user):
        rows = []
        seen = set()
        attempts = (
            await db.execute(
                select(KpAssessmentAttempt, KpAssessment)
                .join(KpAssessment, KpAssessment.assessment_id == KpAssessmentAttempt.assessment_id)
                .where(KpAssessmentAttempt.user_id == user_id_of(current_user))
                .order_by(KpAssessmentAttempt.create_time.desc(), KpAssessmentAttempt.attempt_id.desc())
            )
        ).all()
        for attempt, assessment in attempts:
            questions = {str(q.get('id', i)): q for i, q in enumerate(assessment.questions or []) if isinstance(q, dict)}
            answer_payload = attempt.answers if isinstance(attempt.answers, dict) else {}
            for item in answer_payload.get('items', []):
                if not isinstance(item, dict):
                    continue
                key = (assessment.assessment_id, str(item.get('question_id')))
                if key in seen:
                    continue
                seen.add(key)
                if not item.get('correct'):
                    q = questions.get(key[1], {})
                    rows.append({
                        'id': attempt.attempt_id,
                        'assessment_id': assessment.assessment_id,
                        'subject_id': assessment.subject_id,
                        'assessment': assessment.title,
                        'question_id': key[1],
                        'question': q.get('question', q.get('text', '')),
                        'answer': item.get('answer'),
                        'expected_answer': q.get('answer', q.get('correct_answer')),
                        'explanation': q.get('explanation', ''),
                        'attempt_id': attempt.attempt_id,
                        'created_at': attempt.create_time.isoformat(),
                    })
        return {'items': rows, 'count': len(rows)}, 200

    @classmethod
    async def wrong_retry(cls, db: AsyncSession, current_user, attempt_id: int):
        attempt = (
            await db.execute(
                select(KpAssessmentAttempt, KpAssessment)
                .join(KpAssessment, KpAssessment.assessment_id == KpAssessmentAttempt.assessment_id)
                .where(KpAssessmentAttempt.attempt_id == attempt_id, KpAssessmentAttempt.user_id == user_id_of(current_user))
            )
        ).first()
        if attempt is None:
            return {'code': 'NOT_FOUND'}, 404
        attempt_row, assessment = attempt
        return {
            'id': assessment.assessment_id,
            'assessment_id': assessment.assessment_id,
            'title': assessment.title,
            'questions': public_questions(assessment.questions),
        }, 200
