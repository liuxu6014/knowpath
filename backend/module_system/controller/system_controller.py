"""Admin system endpoints: users, logs, model configs, and prompts."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, is_admin, json_body, json_response
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_system.service.system_service import SystemService

system_controller = APIRouterPro(prefix='/api/v1', order_num=9, tags=['系统管理'])


def _admin(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    if not is_admin(current_user):
        return error_response('PERMISSION_DENIED', 403, 'admin permission required')
    return None


@system_controller.get('/admin/users/')
async def admin_users(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.admin_users(db)
    return json_response(payload, status)


@system_controller.get('/admin/ai-logs/')
async def admin_logs(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.admin_logs(db)
    return json_response(payload, status)


@system_controller.get('/admin/model-configs/')
async def model_configs(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.model_configs(db)
    return json_response(payload, status)


@system_controller.post('/admin/model-configs/')
async def model_config_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SystemService.model_config_create(db, current_user, data)
    return json_response(payload, status)


@system_controller.get('/admin/model-configs/{config_id}/')
async def model_config_detail(
    config_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.model_config_detail(db, config_id)
    return json_response(payload, status)


@system_controller.patch('/admin/model-configs/{config_id}/')
async def model_config_update(
    config_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SystemService.model_config_update(db, current_user, config_id, data)
    return json_response(payload, status)


@system_controller.get('/admin/prompts/')
async def prompts(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.prompts(db)
    return json_response(payload, status)


@system_controller.post('/admin/prompts/')
async def prompt_create(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SystemService.prompt_create(db, current_user, data)
    return json_response(payload, status)


@system_controller.get('/admin/prompts/{template_id}/')
async def prompt_detail(
    template_id: int,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    payload, status = await SystemService.prompt_detail(db, template_id)
    return json_response(payload, status)


@system_controller.patch('/admin/prompts/{template_id}/')
async def prompt_update(
    template_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _admin(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return error_response('VALIDATION_ERROR', 400, 'invalid_json')
    payload, status = await SystemService.prompt_update(db, current_user, template_id, data)
    return json_response(payload, status)
