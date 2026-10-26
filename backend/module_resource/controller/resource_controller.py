"""Resource endpoints (list/create/detail/parse/chunks, tasks, subject resources)."""
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, is_admin, json_body, json_response
from core.domain import can_access_subject, subject_for
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_resource.service.resource_service import (
    ResourceService,
    _extract_file,
)

resource_controller = APIRouterPro(prefix='/api/v1', order_num=4, tags=['学习资料'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


async def _create_from_request(db: AsyncSession, current_user, request: Request):
    content_type = request.headers.get('content-type', '')
    if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
        form = await request.form()
        title = str(form.get('title', '') or '').strip()
        subject_id = form.get('subject_id')
        file = form.get('file')
        content = form.get('content')
        if file is not None:
            filename = getattr(file, 'filename', None) or 'upload'
            data = await file.read()
            try:
                extracted = _extract_file(filename, data)
            except ValueError as exc:
                return error_response('VALIDATION_ERROR', 400, str(exc))
            if not title:
                title = Path(filename).stem
            subject = await ResourceService._subject_for(db, subject_id)
            if subject is False:
                return error_response('NOT_FOUND', 404, 'subject_not_found')
            if subject is None:
                return error_response('VALIDATION_ERROR', 400, 'subject_id_required')
            if subject.archived:
                return error_response('SUBJECT_ARCHIVED', 409, 'subject_archived')
            if not is_admin(current_user) and subject.user_id != current_user.user.user_id:
                return error_response('NOT_FOUND', 404, 'subject_not_found')
            payload, status = await ResourceService.create_from_upload(
                db, current_user, title=title, subject=subject, content=extracted, filename=filename
            )
            return json_response(payload, status)
        data = {'title': title, 'subject_id': subject_id, 'content': content}
    else:
        data = await json_body(request)
        if not isinstance(data, dict):
            return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await ResourceService.create_from_json(db, current_user, data)
    return json_response(payload, status)


@resource_controller.get('/resources/')
async def resources(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    items = await ResourceService.list_resources(db, current_user)
    return json_response({'items': items})


@resource_controller.post('/resources/')
async def resource_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    return await _create_from_request(db, current_user, request)


@resource_controller.get('/resources/{resource_id}/')
async def resource_detail(
    resource_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await ResourceService.detail(db, current_user, resource_id)
    return json_response(payload, status)


@resource_controller.post('/resources/{resource_id}/parse/')
async def resource_parse(
    resource_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await ResourceService.parse(db, current_user, resource_id)
    return json_response(payload, status)


@resource_controller.get('/resources/{resource_id}/chunks/')
async def resource_chunks(
    resource_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await ResourceService.chunks(db, current_user, resource_id)
    return json_response(payload, status)


@resource_controller.get('/tasks/')
async def tasks(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    items = await ResourceService.list_tasks(db, current_user)
    return json_response({'items': items})


@resource_controller.get('/tasks/{task_id}/')
async def task_detail(
    task_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await ResourceService.task_detail(db, current_user, task_id)
    return json_response(payload, status)


@resource_controller.post('/tasks/{task_id}/retry/')
async def task_retry(
    task_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await ResourceService.task_retry(db, current_user, task_id)
    return json_response(payload, status)


@resource_controller.get('/subjects/{subject_id}/resources/')
async def subject_resources(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    subject = await subject_for(db, subject_id)
    if subject is None or not can_access_subject(current_user, subject):
        return error_response('NOT_FOUND', 404)
    items = await ResourceService.list_resources(db, current_user)
    items = [item for item in items if item.get('subject_id') == int(subject_id)]
    return json_response({'items': items})


@resource_controller.post('/subjects/{subject_id}/resources/')
async def subject_resource_create(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    subject = await subject_for(db, subject_id)
    if subject is None or not can_access_subject(current_user, subject):
        return error_response('NOT_FOUND', 404)
    return await _create_from_request(db, current_user, request)
