"""Knowledge graph, relations, snapshots, notes, lesson, and chat endpoints."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, is_admin, json_body, json_response
from core.helpers import bool_value
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_knowledge.service.knowledge_service import KnowledgeService

knowledge_controller = APIRouterPro(prefix='/api/v1', order_num=5, tags=['知识图谱'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


def _admin(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    if not is_admin(current_user):
        return error_response('PERMISSION_DENIED', 403, 'admin permission required')
    return None


@knowledge_controller.post('/subjects/{subject_id}/knowledge/build/')
async def knowledge_build(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await KnowledgeService.build(db, current_user, subject_id)
    return json_response(payload, status)


@knowledge_controller.get('/subjects/{subject_id}/knowledge/graph/')
async def knowledge_graph(
    subject_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await KnowledgeService.graph(db, current_user, subject_id)
    return json_response(payload, status)


@knowledge_controller.post('/knowledge/validate/')
async def knowledge_validate(
    request: Request,
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    data = await json_body(request)
    payload, status = await KnowledgeService.validate(data)
    return json_response(payload, status)


@knowledge_controller.get('/knowledge/profile/')
async def knowledge_profile(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await KnowledgeService.profile(db, current_user)
    return json_response(payload, status)


@knowledge_controller.patch('/knowledge/concepts/{concept_id}/')
async def knowledge_concept_update(
    concept_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await KnowledgeService.concept_update(db, current_user, concept_id, data)
    return json_response(payload, status)


@knowledge_controller.post('/knowledge/relations/')
async def knowledge_relation_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await KnowledgeService.relation_create(db, current_user, data)
    return json_response(payload, status)


@knowledge_controller.patch('/knowledge/relations/{relation_id}/')
@knowledge_controller.delete('/knowledge/relations/{relation_id}/')
async def knowledge_relation_update(
    relation_id: str,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    deleting = request.method == 'DELETE'
    data: dict = {}
    if request.method == 'PATCH':
        data = await json_body(request)
        if not isinstance(data, dict):
            return error_response('VALIDATION_ERROR', 400, 'invalid_json')
        deleting = data.get('action') in {'delete', 'remove'} or bool_value(data.get('deleted'), default=False)
    payload, status = await KnowledgeService.relation_update(db, current_user, relation_id, data, deleting=deleting)
    return json_response(payload, status)


async def _snapshots_get(current_user, db):
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    items = await KnowledgeService.list_snapshots(db, current_user)
    return json_response({'items': items})


async def _snapshots_post(request, current_user, db):
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    payload, status = await KnowledgeService.create_snapshot(db, current_user, data)
    return json_response(payload, status)


@knowledge_controller.get('/graph/snapshots/')
@knowledge_controller.get('/knowledge/snapshots/')
async def graph_snapshots_get(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    return await _snapshots_get(current_user, db)


@knowledge_controller.post('/graph/snapshots/')
@knowledge_controller.post('/knowledge/snapshots/')
async def graph_snapshots_post(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    return await _snapshots_post(request, current_user, db)


@knowledge_controller.post('/graph/snapshots/{snapshot_id}/sync/')
@knowledge_controller.post('/knowledge/snapshots/{snapshot_id}/sync/')
async def graph_snapshot_sync(
    snapshot_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'error': 'authentication_required'}, 401)
    payload, status = await KnowledgeService.sync_snapshot(db, current_user, snapshot_id)
    return json_response(payload, status)


@knowledge_controller.get('/concepts/{concept_id}/lesson/')
@knowledge_controller.post('/concepts/{concept_id}/lesson/')
async def lesson(
    concept_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    duration_sec = 0
    metadata = {}
    if request.method == 'POST':
        data = await json_body(request)
        if data is None or not isinstance(data, dict):
            return error_response('VALIDATION_ERROR', 400, 'invalid_json')
        requested_subject = data.get('subject_id')
        concept = await KnowledgeService._resolve_concept(db, current_user, concept_id)
        if concept is False or concept is None:
            return error_response('NOT_FOUND', 404)
        if requested_subject not in (None, '', str(concept.subject_id), concept.subject_id):
            return error_response('NOT_FOUND', 404)
        duration_sec = data.get('duration_sec', data.get('duration', 0))
        metadata = data.get('metadata', {})
    else:
        duration_sec = request.query_params.get('duration_sec', 0)
    payload, status = await KnowledgeService.lesson(db, current_user, concept_id, duration_sec=duration_sec, metadata=metadata)
    return json_response(payload, status)


@knowledge_controller.post('/concepts/{concept_id}/chat/')
async def chat(
    concept_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await KnowledgeService.chat(db, current_user, concept_id, data)
    return json_response(payload, status)


@knowledge_controller.get('/notes/')
async def notes_list(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    payload, status = await KnowledgeService.list_notes(
        db, current_user,
        subject_id=request.query_params.get('subject_id'),
        concept_id=request.query_params.get('concept_id'),
        query=request.query_params.get('q', ''),
    )
    return json_response(payload, status)


@knowledge_controller.post('/notes/')
@knowledge_controller.patch('/notes/')
async def notes_write(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    if request.method == 'PATCH':
        payload, status = await KnowledgeService.update_note(db, current_user, data)
    else:
        payload, status = await KnowledgeService.create_note(db, current_user, data)
    return json_response(payload, status)
