"""Learning analytics endpoints: events, dashboard, and subject reports."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from core.api import KnowPathUserDependency, error_response, json_body, json_response, user_id_of
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_analytics.service.analytics_service import AnalyticsService, learning_summary, report_dates

analytics_controller = APIRouterPro(prefix='/api/v1', order_num=8, tags=['学习分析'])


def _auth(current_user: CurrentUserModel | None):
    if current_user is None or current_user.user is None:
        return error_response('AUTH_REQUIRED', 401, 'authentication required')
    return None


async def _learning_events(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    if request.method == 'POST':
        data = await json_body(request)
        if not isinstance(data, dict):
            return error_response('VALIDATION_ERROR', 400, 'invalid_json')
        payload, status = await AnalyticsService.create_event(db, current_user, data)
        return json_response(payload, status)
    params = request.query_params
    subject_id = params.get('subject_id', params.get('subject_uuid'))
    concept_id = params.get('concept_id', params.get('concept_uuid'))
    event_type = str(params.get('event_type') or params.get('event') or params.get('type') or '').strip().lower()
    try:
        dates = report_dates(params)
    except ValueError as exc:
        return error_response('VALIDATION_ERROR', 400, str(exc))
    try:
        limit = max(1, min(200, int(params.get('limit', 100))))
    except (TypeError, ValueError):
        return error_response('VALIDATION_ERROR', 400, 'invalid_limit')
    payload, status = await AnalyticsService.list_events(
        db, current_user, subject_id=subject_id, concept_id=concept_id,
        event_type=event_type, dates=dates, limit=limit,
    )
    return json_response(payload, status)


for _path in ('/learning-events/', '/events/', '/analytics/events/', '/learning/events/'):
    analytics_controller.add_api_route(_path, _learning_events, methods=['GET', 'POST'])


@analytics_controller.get('/dashboard/')
async def dashboard(
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    try:
        dates = report_dates(request.query_params)
    except ValueError as exc:
        return error_response('VALIDATION_ERROR', 400, str(exc))
    payload = await learning_summary(db, user_id_of(current_user), dates=dates)
    return json_response(payload)


@analytics_controller.get('/subjects/{subject_id}/analytics/')
async def subject_analytics(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    try:
        dates = report_dates(request.query_params)
    except ValueError as exc:
        return error_response('VALIDATION_ERROR', 400, str(exc))
    payload, status = await AnalyticsService.subject_analytics(db, current_user, subject_id, dates)
    return json_response(payload, status)


@analytics_controller.get('/subjects/{subject_id}/report/')
async def subject_report(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    version = request.query_params.get('version')
    payload, status = await AnalyticsService.subject_report(db, current_user, subject_id, version)
    return json_response(payload, status)


@analytics_controller.post('/subjects/{subject_id}/report/generate/')
async def generate_report(
    subject_id: int,
    request: Request,
    current_user: Annotated[CurrentUserModel | None, KnowPathUserDependency()],
    db: Annotated[AsyncSession, DBSessionDependency()],
) -> JSONResponse:
    if error := _auth(current_user):
        return error
    try:
        dates = report_dates(request.query_params)
    except ValueError as exc:
        return error_response('VALIDATION_ERROR', 400, str(exc))
    payload, status = await AnalyticsService.generate_report(db, current_user, subject_id, dates)
    return json_response(payload, status)
