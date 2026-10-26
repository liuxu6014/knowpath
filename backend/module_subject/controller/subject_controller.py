"""Subject endpoints (list, create, detail, update, archive)."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, json_body, json_response
from core.helpers import bool_value
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_subject.service.subject_service import SubjectService

subject_controller = APIRouterPro(prefix='/api/v1', order_num=3, tags=['学科管理'])


def _auth(current_user: CurrentUserModel | None):
    return None if (current_user and current_user.user) else error_response('AUTH_REQUIRED', 401, 'authentication required')


@subject_controller.get('/subjects/')
async def subjects(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    include_archived = bool_value(request.query_params.get('include_archived')) or request.query_params.get('archived') in {'1', 'true'}
    items = await SubjectService.list_subjects(db, current_user, include_archived)
    return json_response({'items': items})


@subject_controller.post('/subjects/')
async def subject_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SubjectService.create(db, current_user.user.user_id, data)
    return json_response(payload, status)


@subject_controller.get('/subjects/{subject_id}/')
async def subject_detail(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await SubjectService.detail(db, current_user, subject_id)
    return json_response(payload, status)


@subject_controller.patch('/subjects/{subject_id}/')
async def subject_update(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SubjectService.update(db, current_user, subject_id, data)
    return json_response(payload, status)


@subject_controller.delete('/subjects/{subject_id}/')
async def subject_delete(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await SubjectService.archive(db, current_user, subject_id)
    return json_response(payload, status)
