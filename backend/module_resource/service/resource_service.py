"""Resource ingestion, chunking, and processing-task service."""
import hashlib
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api import is_admin
from core.domain import audit, iso_time
from module_resource.entity.do.resource_do import KpChunk, KpProcessingTask, KpResource
from module_subject.entity.do.subject_do import KpSubject

SUPPORTED_SUFFIXES = {'.md', '.markdown', '.txt', '.pdf', '.docx'}
ALLOWED_MIMES = {
    '.md': {'text/markdown', 'text/plain', 'application/octet-stream'},
    '.markdown': {'text/markdown', 'text/plain', 'application/octet-stream'},
    '.txt': {'text/plain', 'application/octet-stream'},
    '.pdf': {'application/pdf', 'application/octet-stream'},
    '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/zip', 'application/octet-stream'},
}


def _extract_file(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded file; best-effort for pdf/docx."""
    suffix = Path(filename).suffix.lower()
    if suffix in {'.md', '.markdown', '.txt'}:
        return data.decode('utf-8', errors='replace')
    if suffix == '.pdf':
        try:
            import pdfplumber
        except Exception:
            raise ValueError('PDF parsing requires the pdfplumber package.')
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or '')
        return '\n\n'.join(text_parts)
    if suffix == '.docx':
        try:
            import docx
        except Exception:
            raise ValueError('DOCX parsing requires the python-docx package.')
        import io
        document = docx.Document(io.BytesIO(data))
        return '\n'.join(paragraph.text for paragraph in document.paragraphs)
    raise ValueError(f'Unsupported file type: {suffix or "unknown"}')


def resource_payload(resource, task=None, subject=None):
    """Return the wire shape used by both list and detail endpoints."""
    task_progress = (100 if task and task.status == 'succeeded' else task.progress) if task else None
    return {
        'id': resource.resource_id,
        'title': resource.title,
        'content': resource.content,
        'subject_id': resource.subject_id,
        'subject_name': subject.name if subject else None,
        'user_id': resource.user_id,
        'sha256': resource.sha256,
        'file_name': resource.file,
        'file_size': len(resource.content.encode('utf-8')) if resource.content else None,
        'chunks': 0,
        'task': (
            {
                'id': task.task_id,
                'status': task.status,
                'progress': task_progress,
                'attempts': task.attempts,
                'error': task.error,
            }
            if task else None
        ),
    }


class ResourceService:
    """异步学习资料服务层。"""

    @classmethod
    async def _subject_for(cls, db: AsyncSession, subject_id):
        if subject_id in (None, '', 'null'):
            return None
        try:
            subject_id = int(subject_id)
        except (TypeError, ValueError):
            return False
        return (
            await db.execute(select(KpSubject).where(KpSubject.subject_id == subject_id))
        ).scalars().first()

    @classmethod
    async def accessible(cls, db: AsyncSession, current_user, resource) -> bool:
        if resource is None or current_user is None or current_user.user is None:
            return False
        if is_admin(current_user):
            return True
        user_id = current_user.user.user_id
        if resource.user_id == user_id:
            return True
        if resource.subject_id:
            subject = await cls._subject_for(db, resource.subject_id)
            if subject and subject.user_id == user_id:
                return True
        return False

    @classmethod
    async def list_resources(cls, db: AsyncSession, current_user):
        user_id = current_user.user.user_id
        query = select(KpResource)
        if not is_admin(current_user):
            owned_subjects = select(KpSubject.subject_id).where(KpSubject.user_id == user_id)
            query = query.where(
                (KpResource.user_id == user_id) | (KpResource.subject_id.in_(owned_subjects))
            )
        resources = (await db.execute(query.order_by(KpResource.create_time.desc(), KpResource.resource_id.desc()))).scalars().all()
        items = []
        for resource in resources:
            task = await cls._latest_task(db, resource.resource_id)
            subject = await cls._subject_for(db, resource.subject_id) if resource.subject_id else None
            payload = resource_payload(resource, task, subject)
            payload['chunks'] = (
                await db.execute(
                    select(func.count()).select_from(KpChunk).where(KpChunk.resource_id == resource.resource_id)
                )
            ).scalar() or 0
            items.append(payload)
        return items

    @classmethod
    async def _latest_task(cls, db: AsyncSession, resource_id: int) -> KpProcessingTask | None:
        return (
            await db.execute(
                select(KpProcessingTask)
                .where(KpProcessingTask.resource_id == resource_id)
                .order_by(KpProcessingTask.create_time.desc(), KpProcessingTask.task_id.desc())
            )
        ).scalars().first()

    @classmethod
    async def create_resource(
        cls, db: AsyncSession, current_user, *, title, subject, content, sha256, file=None
    ):
        resource = KpResource(
            title=title,
            content=content,
            subject_id=subject.subject_id if subject else None,
            user_id=current_user.user.user_id,
            sha256=sha256,
            file=file,
        )
        db.add(resource)
        await db.flush()
        task = KpProcessingTask(resource_id=resource.resource_id)
        db.add(task)
        await db.flush()
        await cls.process_resource(db, resource, task)
        return resource, task

    @classmethod
    async def process_resource(cls, db: AsyncSession, resource, task):
        """Port of Django's synchronous ``_process_resource``."""
        task.status = 'running'
        task.progress = max(1, min(99, task.progress or 0))
        task.attempts = (task.attempts or 0) + 1
        await db.flush()
        try:
            text = resource.content or ''
            task.progress = 45
            await db.flush()
            resource.content = text
            await db.execute(delete(KpChunk).where(KpChunk.resource_id == resource.resource_id))
            size = 1200
            current_heading = ''
            line_cursor = 0
            for i, start in enumerate(range(0, len(text), size)):
                content = text[start:start + size]
                if not content:
                    continue
                lines = content.splitlines()
                heading = current_heading
                for line in lines:
                    if line.lstrip().startswith('#'):
                        current_heading = line.strip().lstrip('#').strip()
                        if not heading:
                            heading = current_heading
                db.add(
                    KpChunk(
                        resource_id=resource.resource_id,
                        index=i,
                        content=content,
                        metadata_json={
                            'chars': len(content),
                            'start_char': start,
                            'end_char': start + len(content),
                            'line_start': line_cursor + 1,
                            'line_end': line_cursor + content.count('\n') + 1,
                            'heading': heading,
                        },
                    )
                )
                line_cursor += content.count('\n')
            task.status = 'succeeded'
            task.progress = 100
            task.error = ''
            await db.flush()
        except Exception as exc:
            task.status = 'failed'
            task.error = str(exc)
            await db.flush()

    @classmethod
    async def create_from_json(cls, db: AsyncSession, current_user, data: dict):
        title = str(data.get('title', '')).strip()
        if not title:
            return {'code': 'VALIDATION_ERROR', 'message': 'title_required'}, 400
        subject = await cls._subject_for(db, data.get('subject_id'))
        if subject is False:
            return {'code': 'NOT_FOUND', 'message': 'subject_not_found'}, 404
        if subject is None:
            return {'code': 'VALIDATION_ERROR', 'message': 'subject_id_required'}, 400
        if subject.archived:
            return {'code': 'SUBJECT_ARCHIVED', 'message': 'subject_archived'}, 409
        if not is_admin(current_user) and subject.user_id != current_user.user.user_id:
            return {'code': 'NOT_FOUND', 'message': 'subject_not_found'}, 404
        content = data.get('content', '')
        if not isinstance(content, str):
            return {'code': 'VALIDATION_ERROR', 'message': 'content_must_be_string'}, 400
        sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest()
        dup = await cls._duplicate(db, subject.subject_id, sha256)
        if dup:
            return {'code': 'DUPLICATE_RESOURCE', 'message': 'resource_already_exists', 'resource_id': dup}, 409
        resource, task = await cls.create_resource(db, current_user, title=title, subject=subject, content=content, sha256=sha256)
        await audit(db, current_user, 'resource.create', '/api/v1/resources/', {'id': resource.resource_id})
        await db.commit()
        return await cls._create_payload(db, resource, task), 201

    @classmethod
    async def create_from_upload(cls, db: AsyncSession, current_user, *, title, subject, content, filename):
        sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest()
        dup = await cls._duplicate(db, subject.subject_id, sha256)
        if dup:
            return {'code': 'DUPLICATE_RESOURCE', 'message': 'resource_already_exists', 'resource_id': dup}, 409
        resource, task = await cls.create_resource(
            db, current_user, title=title, subject=subject, content=content, sha256=sha256, file=filename
        )
        await audit(db, current_user, 'resource.create', '/api/v1/resources/', {'id': resource.resource_id})
        await db.commit()
        return await cls._create_payload(db, resource, task), 201

    @classmethod
    async def _duplicate(cls, db: AsyncSession, subject_id, sha256) -> int | None:
        existing = (
            await db.execute(
                select(KpResource.resource_id)
                .where(KpResource.subject_id == subject_id, KpResource.sha256 == sha256)
                .order_by(KpResource.resource_id)
            )
        ).scalars().first()
        return existing

    @classmethod
    async def _create_payload(cls, db: AsyncSession, resource, task):
        chunk_count = (
            await db.execute(
                select(func.count()).select_from(KpChunk).where(KpChunk.resource_id == resource.resource_id)
            )
        ).scalar() or 0
        return {
            'resource_id': resource.resource_id,
            'parse_status': task.status,
            'chunks': chunk_count,
            'task': {
                'id': task.task_id,
                'status': task.status,
                'progress': (100 if task.status == 'succeeded' else task.progress),
                'attempts': task.attempts,
                'error': task.error,
            },
        }

    @classmethod
    async def detail(cls, db: AsyncSession, current_user, resource_id: int):
        resource = (
            await db.execute(select(KpResource).where(KpResource.resource_id == resource_id))
        ).scalars().first()
        if resource is None:
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        if not await cls.accessible(db, current_user, resource):
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        task = await cls._latest_task(db, resource_id)
        subject = await cls._subject_for(db, resource.subject_id) if resource.subject_id else None
        payload = resource_payload(resource, task, subject)
        payload['chunks'] = (
            await db.execute(
                select(func.count()).select_from(KpChunk).where(KpChunk.resource_id == resource_id)
            )
        ).scalar() or 0
        return payload, 200

    @classmethod
    async def parse(cls, db: AsyncSession, current_user, resource_id: int):
        resource = (
            await db.execute(select(KpResource).where(KpResource.resource_id == resource_id))
        ).scalars().first()
        if resource is None:
            return {'code': 'NOT_FOUND'}, 404
        if not await cls.accessible(db, current_user, resource):
            return {'code': 'NOT_FOUND'}, 404
        task = await cls._latest_task(db, resource_id)
        if task is None:
            task = KpProcessingTask(resource_id=resource_id)
            db.add(task)
            await db.flush()
        await cls.process_resource(db, resource, task)
        await db.commit()
        return await cls._parse_payload(db, resource, task), 200

    @classmethod
    async def _parse_payload(cls, db: AsyncSession, resource, task):
        chunk_count = (
            await db.execute(
                select(func.count()).select_from(KpChunk).where(KpChunk.resource_id == resource.resource_id)
            )
        ).scalar() or 0
        return {
            'resource_id': resource.resource_id,
            'parse_status': task.status,
            'chunks': chunk_count,
            'task': {
                'id': task.task_id,
                'status': task.status,
                'progress': (100 if task.status == 'succeeded' else task.progress),
                'attempts': task.attempts,
                'error': task.error,
            },
        }

    @classmethod
    async def chunks(cls, db: AsyncSession, current_user, resource_id: int):
        resource = (
            await db.execute(select(KpResource).where(KpResource.resource_id == resource_id))
        ).scalars().first()
        if resource is None:
            return {'code': 'NOT_FOUND'}, 404
        if not await cls.accessible(db, current_user, resource):
            return {'code': 'NOT_FOUND'}, 404
        chunks = (
            await db.execute(
                select(KpChunk).where(KpChunk.resource_id == resource_id).order_by(KpChunk.seq_no)
            )
        ).scalars().all()
        return {
            'items': [
                {'id': c.chunk_id, 'seq_no': c.seq_no, 'content': c.content, 'metadata': c.metadata_json}
                for c in chunks
            ]
        }, 200

    @classmethod
    async def list_tasks(cls, db: AsyncSession, current_user):
        tasks = (
            await db.execute(
                select(KpProcessingTask).order_by(KpProcessingTask.update_time.desc(), KpProcessingTask.task_id.desc())
            )
        ).scalars().all()
        items = []
        for t in tasks:
            resource = (
                await db.execute(select(KpResource).where(KpResource.resource_id == t.resource_id))
            ).scalars().first()
            if resource is None:
                continue
            if not is_admin(current_user):
                if resource.user_id != current_user.user.user_id:
                    subject = await cls._subject_for(db, resource.subject_id) if resource.subject_id else None
                    if not (subject and subject.user_id == current_user.user.user_id):
                        continue
            chunk_count = (
                await db.execute(
                    select(func.count()).select_from(KpChunk).where(KpChunk.resource_id == resource.resource_id)
                )
            ).scalar() or 0
            progress = (100 if t.status == 'succeeded' else t.progress)
            items.append({
                'id': t.task_id,
                'kind': 'resource',
                'name': f'解析 {resource.title}',
                'status': t.status,
                'progress': progress,
                'result': {
                    'resource_id': t.resource_id,
                    'attempts': t.attempts,
                    'error': t.error,
                    'chunks': chunk_count,
                    'progress': progress,
                },
                'updated_at': iso_time(t.update_time),
            })
        return items

    @classmethod
    async def task_detail(cls, db: AsyncSession, current_user, task_id: int):
        task = (
            await db.execute(select(KpProcessingTask).where(KpProcessingTask.task_id == task_id))
        ).scalars().first()
        if task is None:
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        resource = (
            await db.execute(select(KpResource).where(KpResource.resource_id == task.resource_id))
        ).scalars().first()
        if resource is None or not await cls.accessible(db, current_user, resource):
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        return {
            'id': task.task_id,
            'resource_id': task.resource_id,
            'status': task.status,
            'progress': (100 if task.status == 'succeeded' else task.progress),
            'attempts': task.attempts,
            'error': task.error,
        }, 200

    @classmethod
    async def task_retry(cls, db: AsyncSession, current_user, task_id: int):
        task = (
            await db.execute(select(KpProcessingTask).where(KpProcessingTask.task_id == task_id))
        ).scalars().first()
        if task is None:
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        resource = (
            await db.execute(select(KpResource).where(KpResource.resource_id == task.resource_id))
        ).scalars().first()
        if resource is None or not await cls.accessible(db, current_user, resource):
            return {'code': 'NOT_FOUND', 'message': 'not_found'}, 404
        if task.status != 'failed':
            return {'code': 'VALIDATION_ERROR', 'message': 'task_not_failed', 'status': task.status}, 409
        await cls.process_resource(db, resource, task)
        await db.commit()
        return {
            'id': task.task_id,
            'status': task.status,
            'progress': (100 if task.status == 'succeeded' else task.progress),
            'attempts': task.attempts,
            'error': task.error,
        }, 200
