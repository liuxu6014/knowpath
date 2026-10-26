"""Quiz generation and submission service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin, user_id_of
from core.domain import subject_for
from module_ai.service.ai_service import AiService
from module_assessment.entity.do.assessment_do import KpAssessment
from module_assessment.service.mastery_service import public_questions
from module_knowledge.entity.do.concept_do import KpConcept
from module_quiz.entity.do.quiz_do import KpQuiz
from module_subject.entity.do.subject_do import KpSubject


def _normalize_generated_quiz_questions(raw_questions, concept, count):
    """Return answerable, non-leaking questions for the browser quiz UI."""
    if not isinstance(raw_questions, list):
        return None
    normalized = []
    for index, raw in enumerate(raw_questions[:count]):
        if not isinstance(raw, dict):
            return None
        answer = raw.get('answer', raw.get('correct_answer'))
        if answer is None or isinstance(answer, (dict, list, tuple, set, bool)):
            return None
        answer = str(answer).strip()
        stem = str(raw.get('question', raw.get('stem', raw.get('text', ''))) or '').strip()
        if not answer or not stem:
            return None
        options = raw.get('options')
        if not isinstance(options, list):
            options = []
        clean_options = []
        seen = set()
        for option in options:
            if option is None or isinstance(option, (dict, list, tuple, set, bool)):
                continue
            value = str(option).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                clean_options.append(value)
        if answer.casefold() not in seen:
            clean_options.append(answer)
            seen.add(answer.casefold())
        if len(clean_options) < 2:
            distractor = '其他选项'
            if distractor.casefold() in seen:
                distractor = '暂不确定'
            clean_options.append(distractor)
        if len(clean_options) > 6:
            clean_options = clean_options[:6]
            if answer.casefold() not in {item.casefold() for item in clean_options}:
                clean_options[-1] = answer
        item = {
            'id': str(index),
            'type': str(raw.get('type') or 'single').strip() or 'single',
            'concept_id': concept.concept_id,
            'question': stem,
            'options': clean_options,
            'answer': answer,
        }
        if isinstance(raw.get('explanation'), str) and raw['explanation'].strip():
            item['explanation'] = raw['explanation'].strip()[:2000]
        normalized.append(item)
    return normalized or None


class QuizService:
    """异步练习测验服务层。"""

    @classmethod
    async def generate(cls, db: AsyncSession, current_user, concept_id: int, options: dict):
        concept = (
            await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
        ).scalars().first()
        if concept is None:
            return {'code': 'NOT_FOUND'}, 404
        subject = await subject_for(db, concept.subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        try:
            count = int(options.get('count', 5))
        except (TypeError, ValueError):
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_count'}, 400
        if not 1 <= count <= 20:
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_count'}, 400
        questions, source = await AiService.generate_quiz(db, concept.description or concept.name, count)
        questions = _normalize_generated_quiz_questions(questions, concept, count)
        if not questions:
            return {'code': 'INVALID_GENERATED_QUESTIONS'}, 502
        assessment = KpAssessment(subject_id=concept.subject_id, title=concept.name + ' practice', questions=questions)
        db.add(assessment)
        await db.flush()
        quiz = KpQuiz(subject_id=concept.subject_id, title=assessment.title, questions=questions, assessment_id=assessment.assessment_id)
        db.add(quiz)
        await db.commit()
        return {'id': quiz.quiz_id, 'assessment_id': assessment.assessment_id, 'questions': public_questions(questions), 'source': source}, 201

    @classmethod
    async def list_quizzes(cls, db: AsyncSession, current_user):
        query = select(KpQuiz)
        if not is_admin(current_user):
            owned_subjects = select(KpSubject.subject_id).where(KpSubject.user_id == user_id_of(current_user))
            query = query.where(KpQuiz.subject_id.in_(owned_subjects))
        quizzes = (
            await db.execute(query.order_by(KpQuiz.create_time.desc(), KpQuiz.quiz_id.desc()).limit(100))
        ).scalars().all()
        return {
            'items': [
                {'id': q.quiz_id, 'title': q.title, 'subject_id': q.subject_id,
                 'question_count': len(q.questions or []), 'created_at': q.create_time.isoformat()}
                for q in quizzes
            ]
        }, 200

    @classmethod
    async def create_quiz(cls, db: AsyncSession, current_user, data: dict):
        questions = data.get('questions', [])
        if not isinstance(questions, list) or not questions:
            return {'error': 'questions_required'}, 400
        subject_id = data.get('subject_id')
        subject = await subject_for(db, subject_id) if subject_id else None
        if subject is not None and not is_admin(current_user) and subject.user_id != user_id_of(current_user):
            return {'error': 'not_found'}, 404
        quiz = KpQuiz(
            title=str(data.get('title', '练习题'))[:255],
            subject_id=subject.subject_id if subject else None,
            questions=questions,
        )
        db.add(quiz)
        await db.commit()
        return {'id': quiz.quiz_id, 'title': quiz.title, 'subject_id': quiz.subject_id, 'questions': quiz.questions}, 201

    @classmethod
    async def get_quiz(cls, db: AsyncSession, quiz_id: int):
        quiz = (
            await db.execute(select(KpQuiz).where(KpQuiz.quiz_id == quiz_id))
        ).scalars().first()
        return quiz
