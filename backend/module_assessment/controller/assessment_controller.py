"""Assessment, mastery, and mistake endpoints."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, is_admin, json_body, json_response, user_id_of
from core.domain import normalize_duration, record_learning_event, subject_for
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_assessment.entity.do.assessment_do import KpAssessment
from module_assessment.service.assessment_service import AssessmentService
from module_assessment.service.mastery_service import MasteryService
from module_knowledge.entity.do.concept_do import KpConcept
from module_quiz.entity.do.quiz_do import KpQuiz

from sqlalchemy import select

assessment_controller = APIRouterPro(prefix='/api/v1', order_num=6, tags=['测评与掌握度'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


@assessment_controller.post('/subjects/{subject_id}/assessments/start/')
async def assessment_start(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request) or {}
    payload, status = await AssessmentService.start(db, current_user, subject_id, data)
    return json_response(payload, status)


@assessment_controller.get('/assessments/')
async def assessments(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    subject_id = request.query_params.get('subject_id')
    if subject_id:
        try:
            subject_id = int(subject_id)
        except (TypeError, ValueError):
            return error_response('VALIDATION_ERROR', 400, 'invalid_subject_id')
    else:
        subject_id = None
    kind = request.query_params.get('kind')
    payload, status = await AssessmentService.list_assessments(db, current_user, subject_id, kind)
    return json_response(payload, status)


@assessment_controller.post('/assessments/')
async def assessment_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    payload, status = await AssessmentService.create_assessment(db, current_user, data)
    return json_response(payload, status)


@assessment_controller.get('/assessments/{assessment_id}/')
async def assess_detail(
    assessment_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await AssessmentService.detail(db, current_user, assessment_id)
    return json_response(payload, status)


@assessment_controller.get('/assessments/{assessment_id}/submit/')
async def assessment_attempt_history(
    assessment_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await AssessmentService.attempt_history(db, current_user, assessment_id)
    return json_response(payload, status)


@assessment_controller.post('/assessments/{assessment_id}/submit/')
async def assessment_attempt(
    assessment_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    assessment = (
        await db.execute(select(KpAssessment).where(KpAssessment.assessment_id == assessment_id))
    ).scalars().first()
    if assessment is None:
        return json_response({'error': 'not_found'}, 404)
    subject = await subject_for(db, assessment.subject_id)
    if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
        return json_response({'error': 'not_found'}, 404)
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    try:
        duration_sec = normalize_duration(data.get('duration_sec', data.get('duration', 0)))
    except ValueError as exc:
        return json_response({'error': str(exc), 'code': 'VALIDATION_ERROR'}, 400)
    try:
        result = await MasteryService.submit(db, assessment, user_id_of(current_user), data.get('answers'))
    except ValueError as exc:
        return json_response({'error': str(exc)}, 400)
    concept = None
    for question in assessment.questions or []:
        if not isinstance(question, dict) or question.get('concept_id') is None:
            continue
        concept = (
            await db.execute(
                select(KpConcept).where(
                    KpConcept.concept_id == question.get('concept_id'),
                    KpConcept.subject_id == assessment.subject_id,
                )
            )
        ).scalars().first()
        if concept is not None:
            break
    is_quiz = (
        await db.execute(select(KpQuiz.quiz_id).where(KpQuiz.assessment_id == assessment_id).limit(1))
    ).scalars().first() is not None
    await record_learning_event(
        db, user_id_of(current_user),
        'quiz_submit' if is_quiz else 'assessment_submit',
        subject_id=assessment.subject_id,
        concept_id=concept.concept_id if concept else None,
        duration_sec=duration_sec,
        metadata={
            'assessment_id': assessment_id,
            'attempt_id': result.get('id'),
            'score': result.get('score'),
            'correct': result.get('correct'),
            'total': result.get('total'),
        },
    )
    await db.commit()
    return json_response(result, 201)


@assessment_controller.get('/subjects/{subject_id}/mastery/')
async def mastery_profile(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await AssessmentService.mastery_profile(db, current_user, subject_id)
    return json_response(payload, status)


@assessment_controller.get('/subjects/{subject_id}/mastery/history/')
async def mastery_history(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    try:
        limit = max(1, min(200, int(request.query_params.get('limit', 100))))
    except (TypeError, ValueError):
        return error_response('VALIDATION_ERROR', 400, 'invalid_limit')
    payload, status = await AssessmentService.mastery_history(db, current_user, subject_id, limit)
    return json_response(payload, status)


@assessment_controller.get('/wrong-questions/')
async def mistakes(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await AssessmentService.mistakes(db, current_user)
    return json_response(payload, status)


@assessment_controller.post('/wrong-questions/{attempt_id}/retry/')
async def wrong_retry(
    attempt_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await AssessmentService.wrong_retry(db, current_user, attempt_id)
    return json_response(payload, status)
