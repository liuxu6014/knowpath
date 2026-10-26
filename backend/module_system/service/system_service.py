"""Admin system endpoints: users, audit/AI logs, model configs, prompts."""
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain import audit, iso_time
from core.helpers import bool_value
from module_admin.entity.do.user_do import SysUser
from module_system.entity.do.system_do import KpAuditLog, KpModelConfig, KpPromptTemplate


def _valid_base_url(value):
    """Accept an empty URL or a valid http(s) URL with a host."""
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def _model_config_payload(item):
    return {
        'id': item.config_id,
        'name': item.name,
        'provider': item.provider,
        'base_url': item.base_url,
        'model': item.model,
        'enabled': bool(item.enabled),
        'created_at': iso_time(item.create_time),
    }


def _prompt_payload(item):
    return {
        'id': item.template_id,
        'code': item.code,
        'version': item.version,
        'template': item.template,
        'enabled': bool(item.enabled),
        'created_at': iso_time(item.create_time),
    }


class SystemService:
    """异步系统管理服务层。"""

    @classmethod
    async def admin_users(cls, db: AsyncSession):
        users = (
            await db.execute(
                select(SysUser)
                .where(SysUser.del_flag != '2')
                .order_by(SysUser.user_id)
            )
        ).scalars().all()
        return {
            'items': [
                {
                    'id': user.user_id,
                    'username': user.user_name,
                    'email': user.email,
                    'is_staff': user.user_id == 1,
                    'is_active': user.status == '0',
                }
                for user in users
            ]
        }, 200

    @classmethod
    async def admin_logs(cls, db: AsyncSession):
        logs = (
            await db.execute(
                select(KpAuditLog).order_by(KpAuditLog.log_id.desc()).limit(200)
            )
        ).scalars().all()
        return {
            'items': [
                {
                    'id': row.log_id,
                    'action': row.action,
                    'path': row.path,
                    'user_id': row.user_id,
                    'detail': row.detail,
                    'created_at': iso_time(row.create_time),
                }
                for row in logs
            ]
        }, 200

    @classmethod
    async def model_configs(cls, db: AsyncSession):
        rows = (
            await db.execute(
                select(KpModelConfig).order_by(KpModelConfig.name, KpModelConfig.config_id)
            )
        ).scalars().all()
        return {'items': [_model_config_payload(item) for item in rows]}, 200

    @classmethod
    async def model_config_create(cls, db: AsyncSession, current_user, data: dict):
        name = str(data.get('name', '')).strip()
        if not name:
            return {'code': 'VALIDATION_ERROR', 'message': 'name_required'}, 400
        base_url = str(data.get('base_url', '') or '').strip()
        if not _valid_base_url(base_url):
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_base_url'}, 400
        item = KpModelConfig(
            name=name[:120],
            provider=str(data.get('provider', 'openai-compatible') or '')[:80],
            base_url=base_url,
            model=str(data.get('model', '') or '')[:120],
            enabled=bool_value(data.get('enabled', True), default=True),
        )
        db.add(item)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            return {'code': 'DUPLICATE_RESOURCE', 'error': 'model_name_exists', 'message': 'model_name_exists'}, 409
        await audit(db, current_user, 'model_config.create', '/admin/model-configs/', {'id': item.config_id, 'name': item.name})
        await db.commit()
        payload = _model_config_payload(item)
        return {'item': payload, **payload}, 201

    @classmethod
    async def model_config_detail(cls, db: AsyncSession, config_id: int):
        item = (
            await db.execute(select(KpModelConfig).where(KpModelConfig.config_id == config_id))
        ).scalars().first()
        if item is None:
            return {'code': 'NOT_FOUND', 'error': 'NOT_FOUND'}, 404
        return _model_config_payload(item), 200

    @classmethod
    async def model_config_update(cls, db: AsyncSession, current_user, config_id: int, data: dict):
        item = (
            await db.execute(select(KpModelConfig).where(KpModelConfig.config_id == config_id))
        ).scalars().first()
        if item is None:
            return {'code': 'NOT_FOUND', 'error': 'NOT_FOUND'}, 404
        updates = {}
        if 'name' in data:
            name = str(data.get('name') or '').strip()
            if not name:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_required'}, 400
            if len(name) > 120:
                return {'code': 'VALIDATION_ERROR', 'message': 'name_too_long'}, 400
            updates['name'] = name
        if 'provider' in data:
            updates['provider'] = str(data.get('provider') or '').strip()[:80]
        if 'base_url' in data:
            base_url = str(data.get('base_url') or '').strip()
            if not _valid_base_url(base_url):
                return {'code': 'VALIDATION_ERROR', 'message': 'invalid_base_url'}, 400
            updates['base_url'] = base_url
        if 'model' in data:
            updates['model'] = str(data.get('model') or '').strip()[:120]
        if 'enabled' in data:
            updates['enabled'] = bool_value(data.get('enabled'), default=item.enabled)
        for field, value in updates.items():
            setattr(item, field, value)
        if updates:
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                return {'code': 'DUPLICATE_RESOURCE', 'error': 'model_name_exists', 'message': 'model_name_exists'}, 409
            await audit(db, current_user, 'model_config.update', f'/admin/model-configs/{config_id}/', {'id': config_id, 'fields': sorted(updates)})
        await db.commit()
        return _model_config_payload(item), 200

    @classmethod
    async def prompts(cls, db: AsyncSession):
        rows = (
            await db.execute(
                select(KpPromptTemplate).order_by(
                    KpPromptTemplate.code,
                    KpPromptTemplate.version.desc(),
                    KpPromptTemplate.template_id,
                )
            )
        ).scalars().all()
        return {'items': [_prompt_payload(item) for item in rows]}, 200

    @classmethod
    async def prompt_create(cls, db: AsyncSession, current_user, data: dict):
        code = str(data.get('code', '')).strip()
        template = str(data.get('template', ''))
        if not code:
            return {'code': 'VALIDATION_ERROR', 'message': 'code_required'}, 400
        if not template.strip():
            return {'code': 'VALIDATION_ERROR', 'message': 'template_required'}, 400
        try:
            version = int(data.get('version', 1))
        except (TypeError, ValueError):
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_version'}, 400
        if version < 1:
            return {'code': 'VALIDATION_ERROR', 'message': 'invalid_version'}, 400
        enabled = bool_value(data.get('enabled', True), default=True)
        if enabled:
            await db.execute(
                update(KpPromptTemplate)
                .where(KpPromptTemplate.code == code[:120], KpPromptTemplate.enabled.is_(True))
                .values(enabled=False)
            )
        item = KpPromptTemplate(code=code[:120], version=version, template=template, enabled=enabled)
        db.add(item)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            return {'code': 'DUPLICATE_RESOURCE', 'error': 'prompt_version_exists', 'message': 'prompt_version_exists'}, 409
        await audit(db, current_user, 'prompt_template.create', '/admin/prompts/', {'id': item.template_id, 'code': item.code, 'version': item.version})
        await db.commit()
        payload = _prompt_payload(item)
        return {'item': payload, **payload}, 201

    @classmethod
    async def prompt_detail(cls, db: AsyncSession, template_id: int):
        item = (
            await db.execute(select(KpPromptTemplate).where(KpPromptTemplate.template_id == template_id))
        ).scalars().first()
        if item is None:
            return {'code': 'NOT_FOUND', 'error': 'NOT_FOUND'}, 404
        return _prompt_payload(item), 200

    @classmethod
    async def prompt_update(cls, db: AsyncSession, current_user, template_id: int, data: dict):
        item = (
            await db.execute(select(KpPromptTemplate).where(KpPromptTemplate.template_id == template_id))
        ).scalars().first()
        if item is None:
            return {'code': 'NOT_FOUND', 'error': 'NOT_FOUND'}, 404
        updates = {}
        if 'code' in data:
            code = str(data.get('code') or '').strip()
            if not code:
                return {'code': 'VALIDATION_ERROR', 'message': 'code_required'}, 400
            if len(code) > 120:
                return {'code': 'VALIDATION_ERROR', 'message': 'code_too_long'}, 400
            updates['code'] = code
        if 'version' in data:
            try:
                version = int(data.get('version'))
            except (TypeError, ValueError):
                return {'code': 'VALIDATION_ERROR', 'message': 'invalid_version'}, 400
            if version < 1:
                return {'code': 'VALIDATION_ERROR', 'message': 'invalid_version'}, 400
            updates['version'] = version
        if 'template' in data:
            template = str(data.get('template') or '')
            if not template.strip():
                return {'code': 'VALIDATION_ERROR', 'message': 'template_required'}, 400
            updates['template'] = template
        if 'enabled' in data:
            updates['enabled'] = bool_value(data.get('enabled'), default=item.enabled)
        for field, value in updates.items():
            setattr(item, field, value)
        if updates:
            target_code = updates.get('code', item.code)
            if updates.get('enabled', item.enabled):
                await db.execute(
                    update(KpPromptTemplate)
                    .where(KpPromptTemplate.code == target_code, KpPromptTemplate.enabled.is_(True), KpPromptTemplate.template_id != template_id)
                    .values(enabled=False)
                )
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                return {'code': 'DUPLICATE_RESOURCE', 'error': 'prompt_version_exists', 'message': 'prompt_version_exists'}, 409
            await audit(db, current_user, 'prompt_template.update', f'/admin/prompts/{template_id}/', {'id': template_id, 'fields': sorted(updates)})
        await db.commit()
        return _prompt_payload(item), 200
