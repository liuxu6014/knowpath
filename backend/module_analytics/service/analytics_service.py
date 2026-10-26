"""Learning analytics: events, dashboard, subject reports, and summary."""
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin, user_id_of
from core.domain import iso_time, normalize_duration, record_learning_event, subject_for
from core.graph.resolver import latest_usable_graph, restrict_concepts_to_graph
from core.helpers import bool_value, graph_key, path_node_concept_id
from module_analytics.entity.do.learning_report_do import KpLearningEvent, KpLearningReport
from module_assessment.entity.do.assessment_do import KpAssessment, KpAssessmentAttempt
from module_assessment.service.mastery_service import MasteryService
from module_knowledge.entity.do.concept_do import KpConcept
from module_learning.entity.do.learning_path_do import KpLearningPath
from module_learning.service.learning_service import LearningService
from module_quiz.entity.do.quiz_do import KpQuiz
from module_subject.entity.do.subject_do import KpSubject
from utils.time_util import TimezoneUtil


def _graph_value_keys(value):
    if isinstance(value, dict):
        values = (value.get('id'), value.get('concept_id'), value.get('conceptId'),
                  value.get('name'), value.get('title'), value.get('label'))
    else:
        values = (value,)
    keys = set()
    for item in values:
        if item is None or isinstance(item, (dict, list, tuple, set)):
            continue
        key = str(item).strip().casefold()
        if not key:
            continue
        keys.add(key)
        if key.startswith('concept-'):
            keys.add(key[8:])
        else:
            keys.add('concept-' + key)
        collapsed = ' '.join(key.split())
        if collapsed:
            keys.add(collapsed)
            keys.add('-'.join(collapsed.split()))
    return keys


def _bare_identity(value):
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ''
    key = str(value).strip().casefold()
    return key[8:] if key.startswith('concept-') else key


def _looks_like_explicit_id(value):
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return False
    key = str(value).strip().casefold()
    return bool(key) and (key.isdigit() or key.startswith('concept-'))


async def _graph_scope(db: AsyncSession, subject_id: int):
    _, graph_nodes, _ = await latest_usable_graph(db, subject_id)
    if not graph_nodes:
        return None
    keys = set()
    graph_names = set()
    explicit_ids = set()
    for node in graph_nodes:
        keys.update(_graph_value_keys(node))
        if isinstance(node, dict):
            names = [node.get(field) for field in ('name', 'title', 'label')]
            for name in names:
                if name is not None:
                    graph_names.update(_graph_value_keys(name))
            raw_id = node.get('id')
            concept_id = node.get('concept_id', node.get('conceptId'))
            display_keys = {
                str(value).strip().casefold()
                for value in names
                if value is not None and str(value).strip()
            }
            if concept_id is not None and str(concept_id).strip():
                explicit_ids.add(_bare_identity(concept_id))
            elif (
                raw_id is not None and str(raw_id).strip()
                and (_looks_like_explicit_id(raw_id) or str(raw_id).strip().casefold() not in display_keys)
            ):
                explicit_ids.add(_bare_identity(raw_id))
    concepts = (
        await db.execute(select(KpConcept).where(KpConcept.subject_id == subject_id))
    ).scalars().all()
    active_concepts = restrict_concepts_to_graph(concepts, graph_nodes)
    active_ids = {_bare_identity(concept.concept_id) for concept in active_concepts}
    active_names = set().union(
        *(_graph_value_keys(concept.name) for concept in active_concepts)
    ) if active_concepts else graph_names
    return {
        'keys': keys,
        'ids': {value for value in active_ids | explicit_ids if value},
        'names': active_names,
        'node_count': len(graph_nodes),
    }


def _scope_value_matches(value, scope, *, id_field=False):
    if scope is None:
        return True
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return False
    if id_field and _looks_like_explicit_id(value):
        return _bare_identity(value) in scope['ids']
    value_keys = _graph_value_keys(value)
    if value_keys.intersection(scope['names']):
        return True
    return not scope['names'] and bool(value_keys.intersection(scope['keys']))


def _question_in_scope(question, scope):
    if scope is None or not isinstance(question, dict):
        return True
    for field in ('concept_id', 'conceptId'):
        if field in question and question.get(field) is not None and str(question.get(field)).strip():
            return _scope_value_matches(question.get(field), scope, id_field=True)
    for field in ('concept', 'concept_name', 'conceptName'):
        if field in question and question.get(field) is not None and str(question.get(field)).strip():
            return _scope_value_matches(question.get(field), scope, id_field=False)
    return True


def _path_node_in_scope(node, scope):
    if scope is None or not isinstance(node, dict):
        return True
    for field in ('concept_id', 'conceptId'):
        if field in node and node.get(field) is not None and str(node.get(field)).strip():
            return _scope_value_matches(node.get(field), scope, id_field=True)
    raw_id = node.get('id')
    if raw_id is not None and str(raw_id).strip() and _looks_like_explicit_id(raw_id):
        return _bare_identity(raw_id) in scope['ids']
    display = node.get('name', node.get('title', node.get('label', raw_id)))
    return _scope_value_matches(display, scope, id_field=False)


def _correct_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {'1', 'true', 'yes', 'correct', 'right'}:
            return True
        if normalized in {'0', 'false', 'no', 'incorrect', 'wrong'}:
            return False
    return None


def report_dates(params) -> tuple[date | None, date | None]:
    """Parse and validate the ``start_date``/``end_date`` query parameters."""
    result = []
    for key in ('start_date', 'end_date'):
        raw = params.get(key)
        if not raw:
            result.append(None)
            continue
        try:
            value = date.fromisoformat(raw)
        except (ValueError, TypeError):
            value = None
        if value is None or value.isoformat() != raw:
            raise ValueError(f'{key} must be YYYY-MM-DD')
        result.append(value)
    start, end = result
    if start and end and start > end:
        raise ValueError('start_date must not be after end_date')
    if end and end.year == 9999:
        raise ValueError('end_date is out of range')
    return start, end


def _event_payload(event):
    return {
        'id': event.event_id,
        'event_type': event.event_type,
        'subject_id': event.subject_id,
        'concept_id': event.concept_id,
        'concept_uuid': event.concept_id,
        'duration_sec': event.duration_sec,
        'metadata': event.metadata_json or {},
        'metadata_json': event.metadata_json or {},
        'trace_id': event.trace_id,
        'created_at': iso_time(event.create_time),
    }


class AnalyticsService:
    """异步学习分析服务层。"""

    @classmethod
    async def list_events(cls, db: AsyncSession, current_user, *, subject_id=None, concept_id=None, event_type=None, dates=(None, None), limit=100):
        user_id = user_id_of(current_user)
        query = select(KpLearningEvent).where(KpLearningEvent.user_id == user_id)
        if subject_id not in (None, ''):
            subject = await subject_for(db, subject_id)
            if subject is None:
                return {'code': 'NOT_FOUND'}, 404
            query = query.where(KpLearningEvent.subject_id == int(subject_id))
        if concept_id not in (None, ''):
            try:
                concept_id = int(concept_id)
            except (TypeError, ValueError):
                return {'code': 'NOT_FOUND'}, 404
            concept = (
                await db.execute(select(KpConcept).where(KpConcept.concept_id == concept_id))
            ).scalars().first()
            if concept is None:
                return {'code': 'NOT_FOUND'}, 404
            query = query.where(KpLearningEvent.concept_id == concept_id)
        if event_type:
            query = query.where(KpLearningEvent.event_type == event_type)
        start, end = dates
        bounds = TimezoneUtil.local_date_strings_to_utc(
            start.isoformat() if start else None,
            end.isoformat() if end else None,
        )
        if bounds:
            if bounds[0]:
                query = query.where(KpLearningEvent.create_time >= bounds[0])
            if bounds[1]:
                query = query.where(KpLearningEvent.create_time < bounds[1])
        limit = max(1, min(200, limit))
        events = (
            await db.execute(
                query.order_by(KpLearningEvent.create_time.desc(), KpLearningEvent.event_id.desc()).limit(limit)
            )
        ).scalars().all()
        aggregate_seconds = sum(event.duration_sec or 0 for event in events)
        total_count = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
        return {
            'items': [_event_payload(e) for e in events],
            'count': len(events),
            'total_count': total_count,
            'study_seconds': aggregate_seconds,
            'study_minutes': round(aggregate_seconds / 60, 2),
            'duration_sec': aggregate_seconds,
        }, 200

    @classmethod
    async def create_event(cls, db: AsyncSession, current_user, data: dict):
        user_id = user_id_of(current_user)
        event_type = str(data.get('event_type') or data.get('event') or data.get('type') or '').strip()
        if not event_type:
            return {'code': 'VALIDATION_ERROR', 'message': 'event_type_required'}, 400
        subject_id = data.get('subject_id', data.get('subject_uuid'))
        subject = None
        if subject_id not in (None, ''):
            subject = await subject_for(db, subject_id)
            if subject is None:
                return {'code': 'NOT_FOUND'}, 404
        concept_id = data.get('concept_id', data.get('concept_uuid'))
        concept = None
        if concept_id not in (None, ''):
            try:
                concept = (
                    await db.execute(select(KpConcept).where(KpConcept.concept_id == int(concept_id)))
                ).scalars().first()
            except (TypeError, ValueError):
                concept = None
            if concept is None:
                return {'code': 'NOT_FOUND'}, 404
            if subject is not None and concept.subject_id != subject.subject_id:
                return {'code': 'VALIDATION_ERROR', 'message': 'concept_subject_mismatch'}, 400
            subject = subject or (await subject_for(db, concept.subject_id))
        try:
            duration_sec = normalize_duration(data.get('duration_sec', data.get('duration', 0)))
        except ValueError as exc:
            return {'code': 'VALIDATION_ERROR', 'message': str(exc)}, 400
        metadata = data.get('metadata', data.get('metadata_json', {}))
        if not isinstance(metadata, dict):
            metadata = {}
        event = KpLearningEvent(
            user_id=user_id,
            event_type=event_type.lower(),
            subject_id=subject.subject_id if subject else None,
            concept_id=concept.concept_id if concept else None,
            duration_sec=duration_sec,
            metadata_json=metadata,
            trace_id=str(data.get('trace_id') or '').strip()[:64] or None,
        )
        db.add(event)
        await db.commit()
        return _event_payload(event), 201

    @classmethod
    async def subject_analytics(cls, db: AsyncSession, current_user, subject_id: int, dates):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        return await learning_summary(db, user_id_of(current_user), subject_id, dates), 200

    @classmethod
    async def subject_report(cls, db: AsyncSession, current_user, subject_id: int, version=None):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        query = select(KpLearningReport).where(
            KpLearningReport.subject_id == subject_id,
            KpLearningReport.user_id == user_id_of(current_user),
        )
        if version is not None:
            if not str(version).isdecimal() or len(str(version)) > 9 or int(version) < 1:
                return {'code': 'VALIDATION_ERROR', 'message': 'version must be a positive integer'}, 400
            query = query.where(KpLearningReport.version == int(version))
        report = (await db.execute(query.order_by(KpLearningReport.report_id.desc()))).scalars().first()
        if report is None:
            return {'code': 'NOT_FOUND', 'message': 'No saved report'}, 404
        return {
            'id': report.report_id,
            'subject_id': report.subject_id,
            'version': report.version,
            'created_at': iso_time(report.create_time),
            'data': report.snapshot,
        }, 200

    @classmethod
    async def generate_report(cls, db: AsyncSession, current_user, subject_id: int, dates):
        subject = await subject_for(db, subject_id)
        if subject is None or not (is_admin(current_user) or subject.user_id == user_id_of(current_user)):
            return {'code': 'NOT_FOUND'}, 404
        latest = (
            await db.execute(
                select(KpLearningReport)
                .where(KpLearningReport.user_id == user_id_of(current_user), KpLearningReport.subject_id == subject_id)
                .order_by(KpLearningReport.report_id.desc())
            )
        ).scalars().first()
        report = KpLearningReport(
            user_id=user_id_of(current_user),
            subject_id=subject_id,
            version=(latest.version + 1) if latest else 1,
            snapshot=await learning_summary(db, user_id_of(current_user), subject_id, dates),
        )
        db.add(report)
        await db.commit()
        return {
            'id': report.report_id,
            'subject_id': report.subject_id,
            'version': report.version,
            'created_at': iso_time(report.create_time),
            'data': report.snapshot,
        }, 201


async def learning_summary(db: AsyncSession, user_id: int, subject_id=None, dates=(None, None)):
    """Port of Django's ``apps/analytics/services.learning_summary``."""
    attempts_query = select(KpAssessmentAttempt, KpAssessment).join(
        KpAssessment, KpAssessment.assessment_id == KpAssessmentAttempt.assessment_id
    ).where(KpAssessmentAttempt.user_id == user_id)
    events_query = select(KpLearningEvent).where(KpLearningEvent.user_id == user_id)
    if subject_id is not None:
        attempts_query = attempts_query.where(KpAssessment.subject_id == subject_id)
        concept_subquery = select(KpConcept.concept_id).where(KpConcept.subject_id == subject_id)
        events_query = events_query.where(
            or_(
                KpLearningEvent.subject_id == subject_id,
                KpLearningEvent.concept_id.in_(concept_subquery),
            )
        )
    start, end = dates
    bounds = TimezoneUtil.local_date_strings_to_utc(
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )
    if bounds:
        if bounds[0]:
            attempts_query = attempts_query.where(KpAssessmentAttempt.create_time >= bounds[0])
            events_query = events_query.where(KpLearningEvent.create_time >= bounds[0])
        if bounds[1]:
            attempts_query = attempts_query.where(KpAssessmentAttempt.create_time < bounds[1])
            events_query = events_query.where(KpLearningEvent.create_time < bounds[1])
    attempts_rows = (
        await db.execute(
            attempts_query.order_by(KpAssessmentAttempt.create_time, KpAssessmentAttempt.attempt_id)
        )
    ).all()
    attempts = [attempt for attempt, _ in attempts_rows]
    assessments = {a.assessment_id: a for _, a in attempts_rows}
    assessment_ids = [attempt.assessment_id for attempt in attempts]
    quiz_assessment_ids = set()
    if assessment_ids:
        quiz_assessment_ids = set(
            (
                await db.execute(
                    select(KpQuiz.assessment_id).where(KpQuiz.assessment_id.in_(assessment_ids))
                )
            ).scalars().all()
        )

    scope_cache = {}

    async def scope_for(subject_id_value):
        if subject_id_value not in scope_cache:
            scope_cache[subject_id_value] = await _graph_scope(db, subject_id_value)
        return scope_cache[subject_id_value]

    subject_rows_by_id, days, weak = {}, {}, {}
    events = (
        await db.execute(events_query.order_by(KpLearningEvent.create_time, KpLearningEvent.event_id))
    ).scalars().all()
    study_seconds = sum(event.duration_sec or 0 for event in events)
    for event in events:
        day = TimezoneUtil.to_business_time(event.create_time).date().isoformat()
        daily = days.setdefault(day, {
            'date': day, 'attempts': 0, 'diagnostic_attempts': 0, 'practice_attempts': 0,
            'answers': 0, 'correct': 0, 'diagnostic_answers': 0, 'diagnostic_correct': 0,
            'practice_answers': 0, 'practice_correct': 0, 'study_seconds': 0, 'study_minutes': 0,
            'duration_sec': 0, 'event_count': 0,
        })
        daily['study_seconds'] = daily.get('study_seconds', 0) + (event.duration_sec or 0)
        daily['study_minutes'] = round(daily['study_seconds'] / 60, 2)
        daily['duration_sec'] = daily['study_seconds']
        daily['event_count'] = daily.get('event_count', 0) + 1
    scores, diagnostic_scores, practice_scores = [], [], []
    total = correct = 0
    included_attempts = []

    for attempt in attempts:
        assessment = assessments[attempt.assessment_id]
        scope = await scope_for(assessment.subject_id)
        question_list = assessment.questions if isinstance(assessment.questions, list) else []
        questions = {
            str(question.get('id', index)): question
            for index, question in enumerate(question_list)
            if isinstance(question, dict)
        }
        raw_answers = attempt.answers.get('items', []) if isinstance(attempt.answers, dict) else []
        if not isinstance(raw_answers, list):
            raw_answers = []
        filtered_answers = []
        dropped_mapped_answers = 0
        for answer in raw_answers:
            if not isinstance(answer, dict):
                continue
            question_id = str(answer.get('question_id', answer.get('id', '')))
            question = questions.get(question_id)
            if scope is not None and question is not None and not _question_in_scope(question, scope):
                dropped_mapped_answers += 1
                continue
            filtered_answers.append((answer, question or {}))
        if scope is not None and raw_answers and dropped_mapped_answers and not filtered_answers:
            continue
        is_practice = attempt.assessment_id in quiz_assessment_ids
        kind = 'practice' if is_practice else 'diagnostic'
        answer_correctness = [_correct_value(answer.get('correct')) for answer, _ in filtered_answers]
        usable_correctness = [value for value in answer_correctness if value is not None]
        score = attempt.score
        if filtered_answers and len(usable_correctness) == len(filtered_answers):
            score = round(100 * sum(usable_correctness) / len(usable_correctness), 2)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        included_attempts.append((attempt, filtered_answers, kind, score))
        scores.append(score)
        (practice_scores if is_practice else diagnostic_scores).append(score)
        subject_row = subject_rows_by_id.setdefault(assessment.subject_id, {
            'subject_id': assessment.subject_id,
            'subject': None,
            'scores': [], 'diagnostic_scores': [], 'practice_scores': [],
        })
        subject_row['scores'].append(score)
        subject_row[f'{kind}_scores'].append(score)
        day = TimezoneUtil.to_business_time(attempt.create_time).date().isoformat()
        daily = days.setdefault(day, {
            'date': day, 'attempts': 0, 'diagnostic_attempts': 0, 'practice_attempts': 0,
            'answers': 0, 'correct': 0, 'diagnostic_answers': 0, 'diagnostic_correct': 0,
            'practice_answers': 0, 'practice_correct': 0, 'study_seconds': 0, 'study_minutes': 0,
            'duration_sec': 0, 'event_count': 0,
        })
        daily['attempts'] += 1
        daily[f'{kind}_attempts'] += 1
        for answer, question in filtered_answers:
            total += 1
            daily['answers'] += 1
            daily[f'{kind}_answers'] += 1
            is_correct = _correct_value(answer.get('correct')) is True
            if is_correct:
                correct += 1
                daily['correct'] += 1
                daily[f'{kind}_correct'] += 1
                continue
            question_id = str(answer.get('question_id', answer.get('id', '')))
            concept_id = question.get('concept_id', question.get('conceptId'))
            if isinstance(concept_id, (dict, list, tuple, set)):
                concept_id = None
            key = (
                ('concept', str(concept_id))
                if concept_id is not None
                else ('question', assessment.assessment_id, question_id)
            )
            row = weak.setdefault(key, {
                'concept_id': concept_id,
                'subject_id': assessment.subject_id,
                'mistakes': 0,
                'evidence': [],
            })
            row['mistakes'] += 1
            row['evidence'].append({
                'attempt_id': attempt.attempt_id,
                'assessment_id': assessment.assessment_id,
                'question_id': question_id,
            })

    diagnostic_total = sum(len(answers) for _, answers, kind, _ in included_attempts if kind == 'diagnostic')
    practice_total = sum(len(answers) for _, answers, kind, _ in included_attempts if kind == 'practice')
    diagnostic_correct = sum(
        1 for _, answers, kind, _ in included_attempts if kind == 'diagnostic'
        for answer, _ in answers if _correct_value(answer.get('correct')) is True
    )
    practice_correct = sum(
        1 for _, answers, kind, _ in included_attempts if kind == 'practice'
        for answer, _ in answers if _correct_value(answer.get('correct')) is True
    )

    concept_ids = {
        str(row['concept_id']).strip()
        for row in weak.values()
        if row.get('concept_id') is not None and not isinstance(row.get('concept_id'), (dict, list, tuple, set))
    }
    concept_lookup = {}
    if concept_ids:
        numeric_ids = []
        for value in concept_ids:
            value = str(value).strip()
            if value.casefold().startswith('concept-'):
                value = value[8:]
            try:
                numeric_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if numeric_ids:
            concept_query = select(KpConcept).where(KpConcept.concept_id.in_(numeric_ids))
            if subject_id is not None:
                concept_query = concept_query.where(KpConcept.subject_id == subject_id)
            concept_lookup = {
                str(item.concept_id): item
                for item in (await db.execute(concept_query)).scalars().all()
            }

    for row in weak.values():
        concept_id = row.get('concept_id')
        if concept_id is None:
            row.update({'kind': 'question', 'name': '未关联概念的题目'})
            continue
        lookup_key = str(concept_id).strip()
        if lookup_key.casefold().startswith('concept-'):
            lookup_key = lookup_key[8:]
        concept = concept_lookup.get(lookup_key)
        row.update({
            'kind': 'concept',
            'name': concept.name if concept is not None else f'概念 #{concept_id}',
            'subject_id': concept.subject_id if concept is not None else row.get('subject_id'),
        })

    subject_rows = []
    for row in subject_rows_by_id.values():
        values = row.pop('scores')
        diagnostic_values = row.pop('diagnostic_scores')
        practice_values = row.pop('practice_scores')
        subject = await subject_for(db, row['subject_id'])
        row['subject'] = subject.name if subject else None
        row.update({
            'attempts': len(values),
            'average_score': round(sum(values) / len(values), 2) if values else 0,
            'diagnostic_attempts': len(diagnostic_values),
            'practice_attempts': len(practice_values),
            'diagnostic_average_score': round(sum(diagnostic_values) / len(diagnostic_values), 2) if diagnostic_values else 0,
            'practice_average_score': round(sum(practice_values) / len(practice_values), 2) if practice_values else 0,
        })
        subject_rows.append(row)

    weak_points = sorted(weak.values(), key=lambda row: -row['mistakes'])
    mastery_score = None
    mastery_by_subject = []
    path_progress = None
    if subject_id is not None:
        values = await MasteryService.mastery_values(db, user_id, subject_id)
        active_scope = await scope_for(subject_id)
        if active_scope is not None:
            values = {
                key: value for key, value in values.items()
                if _scope_value_matches(key, active_scope, id_field=True)
            }
        mastery_score = round(sum(values.values()) / len(values), 2) if values else None
        path = await LearningService.latest_path(db, user_id, subject_id)
        nodes = [node for node in (path.nodes if path else []) if isinstance(node, dict)]
        if active_scope is not None:
            nodes = [node for node in nodes if _path_node_in_scope(node, active_scope)]
        expected_nodes = active_scope.get('node_count') if active_scope is not None else len(nodes)
        path_progress = round(
            sum(_correct_value(node.get('completed')) is True for node in nodes) / expected_nodes,
            4,
        ) if nodes and expected_nodes else None
        mastery_by_subject = [{'subject_id': subject_id, 'mastery_score': mastery_score}]
    else:
        subjects = (
            await db.execute(select(KpSubject).where(KpSubject.user_id == user_id))
        ).scalars().all()
        for subject_obj in subjects:
            values = await MasteryService.mastery_values(db, user_id, subject_obj.subject_id)
            _, graph_nodes, _ = await latest_usable_graph(db, subject_obj.subject_id)
            if graph_nodes:
                active_scope = await scope_for(subject_obj.subject_id)
                values = {
                    key: value for key, value in values.items()
                    if _scope_value_matches(key, active_scope, id_field=True)
                }
            score = round(sum(values.values()) / len(values), 2) if values else None
            mastery_by_subject.append({'subject_id': subject_obj.subject_id, 'mastery_score': score})
        known_scores = [row['mastery_score'] for row in mastery_by_subject if row['mastery_score'] is not None]
        mastery_score = round(sum(known_scores) / len(known_scores), 2) if known_scores else None

    diagnostic_attempt_count = len(diagnostic_scores)
    practice_attempt_count = len(practice_scores)
    return {
        'subject_id': subject_id,
        'start_date': start.isoformat() if start else None,
        'end_date': end.isoformat() if end else None,
        'total_attempts': len(included_attempts),
        'average_score': round(sum(scores) / len(scores), 2) if scores else 0,
        'answer_count': total,
        'correct_count': correct,
        'mistakes_count': total - correct,
        'accuracy': round(correct / total, 4) if total else None,
        'diagnostic_attempts': diagnostic_attempt_count,
        'practice_attempts': practice_attempt_count,
        'diagnostic_average_score': round(sum(diagnostic_scores) / diagnostic_attempt_count, 2) if diagnostic_attempt_count else 0,
        'practice_average_score': round(sum(practice_scores) / practice_attempt_count, 2) if practice_attempt_count else 0,
        'diagnostic_answer_count': diagnostic_total,
        'diagnostic_correct_count': diagnostic_correct,
        'diagnostic_accuracy': round(diagnostic_correct / diagnostic_total, 4) if diagnostic_total else None,
        'practice_answer_count': practice_total,
        'practice_correct_count': practice_correct,
        'practice_accuracy': round(practice_correct / practice_total, 4) if practice_total else None,
        'mastery_score': mastery_score,
        'mastery_by_subject': mastery_by_subject,
        'path_progress': path_progress,
        'subjects': subject_rows,
        'study_seconds': study_seconds,
        'study_minutes': round(study_seconds / 60, 2),
        'duration_sec': study_seconds,
        'duration_minutes': round(study_seconds / 60, 2),
        'event_count': len(events),
        'study_event_count': sum(1 for event in events if (event.duration_sec or 0) > 0),
        'trend': [days[key] for key in sorted(days)],
        'weak_points': weak_points,
        'summary': (
            f'完成 {len(included_attempts)} 次学习记录，其中能力测评 {diagnostic_attempt_count} 次、'
            f'练习 {practice_attempt_count} 次，记录 {total} 道答题，其中 {correct} 道正确。'
        ),
        'suggestions': ([{
            'text': '复习这个重点，再完成一次练习。',
            'evidence': row['evidence'],
            'kind': row.get('kind'),
            'name': row.get('name'),
            'concept_id': row.get('concept_id'),
            'mistakes': row.get('mistakes', 0),
        } for row in weak_points] or [{
            'text': '继续完成下一次测评，积累学习证据。',
            'evidence': [],
        }]),
    }
