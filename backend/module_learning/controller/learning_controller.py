"""Learning-path endpoints (paths, path_generate, path_current, next_node, path_progress)."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import (
    KnowPathUserDependency,
    error_response,
    json_body,
    json_response,
    user_id_of,
)
from core.domain import can_access_subject, subject_for
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_learning.service.learning_service import LearningService, path_payload

learning_controller = APIRouterPro(prefix='/api/v1', order_num=10, tags=['学习路径'])


async def _subject_check(
    db: AsyncSession,
    current_user: CurrentUserModel | None,
    subject_id,
):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    subject = await subject_for(db, subject_id)
    if subject is None or not can_access_subject(current_user, subject):
        return error_response('NOT_FOUND', 404)
    return subject


@learning_controller.get('/paths/')
async def paths(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    items = await LearningService.list_paths(db, current_user.user.user_id)
    return json_response({'items': items})


@learning_controller.post('/paths/')
async def paths_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    payload, status = await LearningService.create(db, current_user.user.user_id, data)
    return json_response(payload, status)


@learning_controller.post('/subjects/{subject_id}/paths/generate/')
async def path_generate(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    subject = await _subject_check(db, current_user, subject_id)
    if isinstance(subject, JSONResponse):
        return subject
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await LearningService.generate(db, current_user.user.user_id, subject_id, data)
    return json_response(payload, status)


@learning_controller.get('/subjects/{subject_id}/paths/current/')
async def path_current(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    subject = await _subject_check(db, current_user, subject_id)
    if isinstance(subject, JSONResponse):
        return subject
    path = await LearningService.latest_path(db, current_user.user.user_id, subject_id)
    path = await LearningService.refresh_stale_path(db, path, subject_id, current_user.user.user_id)
    return json_response({'path': path_payload(path) if path else None})


@learning_controller.get('/subjects/{subject_id}/next/')
async def next_node(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    subject = await _subject_check(db, current_user, subject_id)
    if isinstance(subject, JSONResponse):
        return subject
    payload = await LearningService.next_node(db, current_user.user.user_id, subject_id)
    payload, status = payload
    return json_response(payload, status)


@learning_controller.post('/paths/{path_id}/progress/')
async def path_progress(
    path_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    result = await LearningService.progress(db, current_user.user.user_id, path_id, data)
    payload, status = result
    return json_response(payload, status)
