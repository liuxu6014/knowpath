"""Shared helpers for the KnowPath ``/api/v1`` surface.

The KnowPath Vue frontend talks to Django with plain JSON bodies, real HTTP
status codes and ``/api/v1/`` paths.  The backend migration keeps that wire
contract exactly while moving the implementation onto the RuoYi-FastAPI async
stack (SQLAlchemy 2.0 async, ``sys_user`` + JWT auth).

Only two things change at the trust boundary:

* session/CSRF cookies become a JWT Bearer token issued against ``sys_user``;
* ``is_staff`` is derived from RuoYi's ``user_id == 1`` admin convention.
"""
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Request, params
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from exceptions.exception import AuthException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService


def _json_default(obj):
    """JSON ``default`` hook so ORM scalar types never leak into payloads.

    MySQL returns ``DECIMAL`` for ``SUM``/``Numeric`` columns even when the
    source column is ``Integer``, and async SQLAlchemy hands those back as
    ``decimal.Decimal``.  Starlette's ``JSONResponse`` does not pass a
    ``default`` hook, so a stray ``Decimal`` aborts rendering with a 500.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


class JsonResponse(JSONResponse):
    """``JSONResponse`` that serializes ``Decimal``/date values transparently."""

    def render(self, content):
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(',', ':'),
            default=_json_default,
        ).encode('utf-8')


def error_response(code, status, message=None, **extra):
    """Return the stable ``{code, error, message}`` error envelope."""
    payload = {'code': code, 'error': code}
    if message:
        payload['message'] = message
    payload.update(extra)
    return JsonResponse(payload, status_code=status)


def plain_error(error, status, **extra):
    """Return the legacy ``{error, ...}`` shape used by the auth endpoints."""
    return JsonResponse({'error': error, **extra}, status_code=status)


def json_response(payload, status=200):
    """Return a plain JSON body with an explicit HTTP status code."""
    return JsonResponse(payload, status_code=status)


async def json_body(request: Request):
    """Parse a JSON object body, returning ``None`` for non-object bodies."""
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def knowpath_current_user(
    request: Request,
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> CurrentUserModel | None:
    """Resolve the JWT-authenticated user, or ``None`` for anonymous requests."""
    authorization = request.headers.get('Authorization', '')
    if not authorization:
        return None
    try:
        return await LoginService.get_current_user(request, authorization, db)
    except AuthException:
        return None


def KnowPathUserDependency() -> params.Depends:  # noqa: N802
    """Dependency that yields ``CurrentUserModel | None``."""
    return Depends(knowpath_current_user)


def is_admin(current_user: CurrentUserModel | None) -> bool:
    """Map Django's ``is_staff`` onto RuoYi's ``user_id == 1`` convention."""
    return bool(current_user and current_user.user and current_user.user.admin)


def user_id_of(current_user: CurrentUserModel | None) -> int | None:
    """Return the numeric user id for a resolved current user."""
    if current_user and current_user.user:
        return current_user.user.user_id
    return None
