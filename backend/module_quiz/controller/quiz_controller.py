"""Quiz endpoints (generate, list/create, submit)."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, is_admin, json_body, json_response, user_id_of
from core.domain import subject_for
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_assessment.entity.do.assessment_do import KpAssessment
from module_assessment.service.mastery_service import MasteryService
from module_quiz.entity.do.quiz_do import KpQuiz
from module_quiz.service.quiz_service import QuizService

quiz_controller = APIRouterPro(prefix='/api/v1', order_num=7, tags=['练习测验'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


@quiz_controller.post('/concepts/{concept_id}/quiz/generate/')
async def quiz_generate(
    concept_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request) or {}
    payload, status = await QuizService.generate(db, current_user, concept_id, data)
    return json_response(payload, status)


@quiz_controller.get('/quizzes/')
async def quizzes(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await QuizService.list_quizzes(db, current_user)
    return json_response(payload, status)


@quiz_controller.post('/quizzes/')
async def quiz_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    payload, status = await QuizService.create_quiz(db, current_user, data)
    return json_response(payload, status)


@quiz_controller.post('/quizzes/{quiz_id}/submit/')
async def quiz_submit(
    quiz_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    quiz = await QuizService.get_quiz(db, quiz_id)
    if quiz is None:
        return json_response({'code': 'NOT_FOUND'}, 404)
    subject = await subject_for(db, quiz.subject_id)
    if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
        return json_response({'code': 'NOT_FOUND'}, 404)
    assessment_id = quiz.assessment_id
    if assessment_id is None:
        assessment = KpAssessment(subject_id=quiz.subject_id, title=quiz.title, questions=quiz.questions)
        db.add(assessment)
        await db.flush()
        quiz.assessment_id = assessment.assessment_id
        assessment_id = assessment.assessment_id
        await db.flush()
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    assessment = (
        await db.execute(select(KpAssessment).where(KpAssessment.assessment_id == assessment_id))
    ).scalars().first()
    try:
        result = await MasteryService.submit(db, assessment, user_id_of(current_user), data.get('answers'))
    except ValueError as exc:
        return json_response({'error': str(exc)}, 400)
    return json_response(result, 201)
