"""KnowPath auth endpoints: register/login/logout/me/refresh.

Port of the Django ``auth/register/``, ``auth/login/``, ``auth/logout/``,
``me/`` and ``auth/refresh/`` views onto the RuoYi-FastAPI async stack.  The
wire contract (plain JSON, real HTTP status codes, trailing slashes) is kept
so the existing Vue frontend works unchanged; the only difference is that
login/register also return a JWT ``token`` and the client authenticates with
``Authorization: Bearer`` instead of a session cookie.
"""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from config.env import AppConfig
from core.api import KnowPathUserDependency, json_body, json_response, plain_error
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from module_user.service.auth_service import AuthService
from utils.jwt_util import JwtUtil

auth_controller = APIRouterPro(prefix='/api/v1', order_num=2, tags=['用户认证'])


@auth_controller.post('/auth/register/')
async def register(request: Request, db: Annotated[AsyncSession, DBSessionDependency()]) -> JSONResponse:
    data = await json_body(request)
    if not isinstance(data, dict):
        return plain_error('invalid_json', 400)
    payload, status = await AuthService.register(request, db, data)
    return json_response(payload, status)


@auth_controller.post('/auth/login/')
async def login(request: Request, db: Annotated[AsyncSession, DBSessionDependency()]) -> JSONResponse:
    data = await json_body(request)
    if not isinstance(data, dict):
        return plain_error('invalid_json', 400)
    payload, status = await AuthService.login(request, db, data)
    return json_response(payload, status)


@auth_controller.post('/auth/logout/')
async def logout(request: Request) -> JSONResponse:
    authorization = request.headers.get('Authorization', '')
    if authorization.startswith('Bearer '):
        token = authorization[7:]
        try:
            payload = JwtUtil.decode(token, options={'verify_exp': False})
            token_id = payload.get('session_id') if AppConfig.app_same_time_login else payload.get('user_id')
            if token_id is not None:
                await LoginService.logout_services(request, str(token_id))
        except Exception:
            pass
    return json_response({'ok': True})


@auth_controller.get('/me/')
async def me_get(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'authenticated': False, 'csrf_token': None, 'user': None})
    profile = await AuthService.profile(db, current_user.user.user_id)
    return json_response(AuthService.me_payload(current_user, profile, authenticated=True))


@auth_controller.patch('/me/')
async def me_patch(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'authenticated': False, 'csrf_token': None, 'user': None})
    data = await json_body(request)
    if not isinstance(data, dict):
        return plain_error('invalid_json', 400)
    result = await AuthService.me_patch(db, current_user, data)
    if result is not None:
        error, status = result
        return plain_error(error, status)
    profile = await AuthService.profile(db, current_user.user.user_id)
    return json_response(AuthService.me_payload(current_user, profile, authenticated=True))


@auth_controller.post('/auth/refresh/')
async def auth_refresh(
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
) -> JSONResponse:
    if current_user is None or current_user.user is None:
        return json_response({'code': 'AUTH_REQUIRED'}, 401)
    return json_response({'code': 0, 'data': {'authenticated': True, 'csrf_token': None}})
