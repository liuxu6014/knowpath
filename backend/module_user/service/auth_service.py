"""KnowPath auth service: sys_user + JWT in place of Django session/CSRF.

Port of the Django ``register`` / ``auth_login`` / ``auth_logout`` / ``me``
views.  The wire contract (plain JSON, real status codes) is preserved; the
only change is that login/register now also return a JWT ``token`` and the
frontend authenticates with ``Authorization: Bearer`` instead of a cookie.
"""
import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import RedisInitKeyConfig
from config.env import AppConfig, JwtConfig
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from module_user.entity.do.profile_do import KpProfile
from utils.pwd_util import PwdUtil
from utils.time_util import TimezoneUtil

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value))


class AuthService:
    """异步用户认证与个人资料服务层。"""

    @classmethod
    async def issue_token(cls, request, user: SysUser) -> str:
        """Create and store a JWT access token for ``user`` (RuoYi pattern)."""
        session_id = str(uuid.uuid4())
        access_token = await LoginService.create_access_token(
            data={
                'user_id': str(user.user_id),
                'user_name': user.user_name,
                'dept_name': None,
                'session_id': session_id,
                'login_info': None,
            },
            expires_delta=timedelta(minutes=JwtConfig.jwt_expire_minutes),
        )
        if AppConfig.app_same_time_login:
            key = f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}'
        else:
            key = f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{user.user_id}'
        await request.app.state.redis.set(
            key, access_token, ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes)
        )
        return access_token

    @classmethod
    async def register(cls, request, db: AsyncSession, data: dict):
        """Port of the Django ``register`` view (returns ``{id, username, token}``)."""
        raw_username = data.get('username', '')
        raw_password = data.get('password', '')
        if not isinstance(raw_username, str) or not isinstance(raw_password, str):
            return {'error': 'username_and_password_required'}, 400
        username = raw_username.strip()
        password = raw_password
        if not username or not password:
            return {'error': 'username_and_password_required'}, 400
        if len(username) > 30:
            # RuoYi's ``sys_user.user_name`` is String(30), tighter than Django's 150.
            return {'error': 'username_too_long'}, 400
        if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            return {'error': 'password_weak', 'message': '密码至少 8 位，并同时包含字母和数字'}, 400
        if 'email' in data and data.get('email') is not None and not isinstance(data.get('email'), str):
            return {'error': 'email_must_be_string'}, 400
        email = str(data.get('email') or '').strip().lower()
        if email:
            if not _is_valid_email(email):
                return {'error': 'email_invalid'}, 400
            exists = (await db.execute(select(SysUser.user_id).where(SysUser.email == email))).scalars().first()
            if exists is not None:
                return {'error': 'email_exists'}, 409
        exists = (await db.execute(select(SysUser.user_id).where(SysUser.user_name == username))).scalars().first()
        if exists is not None:
            return {'error': 'username_exists'}, 409

        user = SysUser(
            user_name=username,
            nick_name=username,
            email=email or None,
            password=PwdUtil.get_password_hash(password),
            status='0',
            del_flag='0',
            pwd_update_date=TimezoneUtil.utc_now(),
        )
        db.add(user)
        await db.flush()
        db.add(KpProfile(user_id=user.user_id))
        await db.commit()
        token = await cls.issue_token(request, user)
        return {'id': user.user_id, 'username': user.user_name, 'token': token}, 201

    @classmethod
    async def login(cls, request, db: AsyncSession, data: dict):
        """Port of the Django ``auth_login`` view."""
        raw_username = data.get('username', '')
        raw_password = data.get('password', '')
        if not isinstance(raw_username, str) or not isinstance(raw_password, str):
            return {'error': 'invalid_credentials'}, 401
        username = raw_username.strip()
        password = raw_password
        if not username or len(username) > 30:
            return {'error': 'invalid_credentials'}, 401
        user = (
            await db.execute(
                select(SysUser).where(SysUser.user_name == username, SysUser.status == '0', SysUser.del_flag == '0')
            )
        ).scalars().first()
        if user is None or not user.password or not PwdUtil.verify_password(password, user.password):
            return {'error': 'invalid_credentials'}, 401
        token = await cls.issue_token(request, user)
        return {'id': user.user_id, 'username': user.user_name, 'token': token}, 200

    @classmethod
    async def profile(cls, db: AsyncSession, user_id: int) -> KpProfile:
        """Get-or-create the KnowPath profile row for a user."""
        profile = (
            await db.execute(select(KpProfile).where(KpProfile.user_id == user_id))
        ).scalars().first()
        if profile is None:
            profile = KpProfile(user_id=user_id)
            db.add(profile)
            await db.flush()
        return profile

    @classmethod
    def me_payload(cls, current_user: CurrentUserModel, profile: KpProfile, *, authenticated: bool) -> dict:
        """Build the Django ``/me/`` response shape."""
        if not authenticated or current_user is None or current_user.user is None:
            return {'authenticated': False, 'csrf_token': None, 'user': None}
        user = current_user.user
        return {
            'authenticated': True,
            'csrf_token': None,
            'user': {
                'id': user.user_id,
                'username': user.user_name,
                'email': user.email,
                'is_staff': bool(user.admin),
                'profile': {
                    'avatar': profile.avatar,
                    'major': profile.major,
                    'level': profile.level,
                    'goals': profile.goals,
                    'preferences': profile.preferences or {},
                },
            },
        }

    @classmethod
    async def me_patch(cls, db: AsyncSession, current_user: CurrentUserModel, data: dict):
        """Port of the Django ``me`` PATCH branch."""
        user = current_user.user
        profile = await cls.profile(db, user.user_id)
        if 'email' in data:
            raw_email = data.get('email')
            if not isinstance(raw_email, str):
                return {'error': 'email_must_be_string'}, 400
            email = raw_email.strip().lower()
            if email:
                if not _is_valid_email(email):
                    return {'error': 'email_invalid'}, 400
                exists = (
                    await db.execute(
                        select(SysUser.user_id).where(SysUser.email == email, SysUser.user_id != user.user_id)
                    )
                ).scalars().first()
                if exists is not None:
                    return {'error': 'email_exists'}, 409
            user.email = email or None
        for field in ('avatar', 'major', 'level', 'goals'):
            if field in data:
                setattr(profile, field, str(data[field])[:10000])
        if 'preferences' in data and not isinstance(data['preferences'], dict):
            return {'error': 'preferences_must_be_object'}, 400
        if isinstance(data.get('preferences'), dict):
            profile.preferences = data['preferences']
        await db.commit()
        return None
