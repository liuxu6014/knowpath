"""Raw AI gateway endpoints: chat, extract, quiz, and embeddings."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, json_body, json_response
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_ai.service.ai_service import AiService

ai_controller = APIRouterPro(prefix='/api/v1', order_num=10, tags=['AI网关'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


@ai_controller.post('/ai/chat/')
async def ai_chat(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    messages = data.get('messages')
    if not isinstance(messages, list) or not messages:
        return json_response({'error': 'messages_required'}, 400)
    try:
        answer = await AiService.chat(db, messages)
        source = 'provider'
    except Exception:
        answer = '离线模式：已记录你的问题，请结合当前知识点内容继续学习。'
        source = 'offline'
    return json_response({'answer': answer, 'source': source})


@ai_controller.post('/ai/extract/')
async def ai_extract(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    text = str(data.get('text', '') or '').strip()
    if not text:
        return json_response({'error': 'text_required'}, 400)
    result, source = await AiService.extract(db, text)
    return json_response({**result, 'source': source})


@ai_controller.post('/ai/quiz/')
async def ai_quiz(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    if not isinstance(data, dict):
        return json_response({'error': 'invalid_json'}, 400)
    text = str(data.get('text', '') or '').strip()
    if not text:
        return json_response({'error': 'text_required'}, 400)
    try:
        count = int(data.get('count', 5))
    except (TypeError, ValueError):
        return json_response({'error': 'invalid_count'}, 400)
    if count < 1 or count > 20:
        return json_response({'error': 'invalid_count'}, 400)
    questions, source = await AiService.generate_quiz(db, text, count)
    return json_response({'questions': questions, 'source': source})


@ai_controller.post('/ai/embeddings/')
async def ai_embeddings(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    data = await json_body(request)
    texts = data.get('texts') if isinstance(data, dict) else None
    if not isinstance(texts, list) or not texts:
        return json_response({'error': 'texts_required'}, 400)
    vectors, source = await AiService.embeddings(db, [str(value) for value in texts], return_source=True)
    return json_response({'embeddings': vectors, 'source': source})
