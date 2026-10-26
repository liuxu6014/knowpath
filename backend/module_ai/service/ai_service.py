"""Small OpenAI-compatible gateway with database-selectable runtime settings.

Port of the Django ``apps/ai_gateway/provider.py`` module to the async
SQLAlchemy service layer.  ``KpModelConfig`` and ``KpPromptTemplate`` are
optional at runtime: a fresh database still uses environment defaults until
an admin enables a configuration.  The blocking HTTP call is run on a worker
thread so the async event loop is never blocked.
"""
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.request

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge import deduplicate, extract_knowledge
from module_system.entity.do.system_do import KpAuditLog, KpModelConfig, KpPromptTemplate

log = logging.getLogger('knowpath.ai')


def _env_float(name, default):
    try:
        value = float(os.getenv(name, default))
        return value if math.isfinite(value) and value > 0 else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _env_int(name, default):
    try:
        return max(0, int(os.getenv(name, default)))
    except (TypeError, ValueError, OverflowError):
        return int(default)


# Keep these names for existing callers/tests while resolving database values
# per request instead of freezing the environment at import time.
BASE_URL = os.getenv('AI_BASE_URL', os.getenv('OPENAI_BASE_URL', '')).rstrip('/')
API_KEY = os.getenv('AI_API_KEY', os.getenv('OPENAI_API_KEY', ''))
CHAT_MODEL = os.getenv('AI_CHAT_MODEL', os.getenv('OPENAI_MODEL', 'gpt-4o-mini'))
EMBED_MODEL = os.getenv('AI_EMBED_MODEL', 'text-embedding-3-small')
TIMEOUT = _env_float('AI_TIMEOUT', 20)
RETRIES = _env_int('AI_RETRIES', 2)


class AiService:
    """AI 网关服务层（chat/extract/quiz/embeddings）。"""

    @classmethod
    async def _audit(cls, db: AsyncSession | None, path: str, status: str, source: str, started: float, **extra) -> None:
        """Persist a small, secret-free invocation record."""
        if db is None:
            return
        detail = {
            'status': status,
            'source': source,
            'duration_ms': round((time.monotonic() - started) * 1000, 2),
        }
        detail.update({key: value for key, value in extra.items() if value is not None})
        try:
            db.add(KpAuditLog(action='ai.call', path=path, detail=detail))
            await db.flush()
        except Exception:
            # AI use must remain available if logging storage is temporarily down.
            pass

    @classmethod
    async def _enabled_model_config(cls, db: AsyncSession | None):
        """Return the newest enabled config, or ``None`` outside DB time."""
        if db is None:
            return None
        try:
            return (
                (
                    await db.execute(
                        select(KpModelConfig)
                        .where(KpModelConfig.enabled.is_(True))
                        .order_by(KpModelConfig.create_time.desc(), KpModelConfig.config_id.desc())
                    )
                )
                .scalars()
                .first()
            )
        except Exception:
            return None

    @classmethod
    async def _runtime_config(cls, db: AsyncSession | None, kind: str = 'chat', model=None) -> dict:
        """Resolve database config first and environment defaults second."""
        config = await cls._enabled_model_config(db)
        provider = str(getattr(config, 'provider', '') or 'openai-compatible').strip().lower()
        base_url = str(getattr(config, 'base_url', '') or '').strip().rstrip('/') or BASE_URL
        default_model = EMBED_MODEL if kind == 'embedding' else CHAT_MODEL
        selected_model = (
            str(model or '').strip()
            or str(getattr(config, 'model', '') or '').strip()
            or default_model
        )
        return {
            'provider': provider,
            'base_url': base_url,
            'api_key': API_KEY,
            'model': selected_model,
            'timeout': TIMEOUT,
            'retries': RETRIES,
            'config_id': getattr(config, 'config_id', None),
        }

    @classmethod
    async def _active_prompt(cls, db: AsyncSession | None, code: str, default: str = '', **values) -> tuple[str, int | None]:
        """Load the highest enabled prompt version and render ``{{name}}`` vars."""
        template = None
        if db is not None:
            try:
                template = (
                    (
                        await db.execute(
                            select(KpPromptTemplate)
                            .where(KpPromptTemplate.code == str(code), KpPromptTemplate.enabled.is_(True))
                            .where(KpPromptTemplate.template != '')
                            .order_by(KpPromptTemplate.version.desc(), KpPromptTemplate.template_id.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
            except Exception:
                template = None
        text = str(getattr(template, 'template', '') or default)
        if values:
            text = re.sub(
                r'\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}',
                lambda match: str(values.get(match.group(1), match.group(0))),
                text,
            )
        return text, getattr(template, 'version', None)

    @classmethod
    async def _messages_with_prompt(cls, db: AsyncSession | None, messages, prompt_code=None, **values):
        copied = [dict(item) for item in (messages or []) if isinstance(item, dict)]
        if not prompt_code:
            return copied, None
        current_system = next(
            (item.get('content') for item in copied if item.get('role') == 'system'),
            '',
        )
        prompt, version = await cls._active_prompt(db, prompt_code, current_system, **values)
        if not prompt:
            return copied, version
        for item in copied:
            if item.get('role') == 'system':
                item['content'] = prompt
                break
        else:
            copied.insert(0, {'role': 'system', 'content': prompt})
        return copied, version

    @classmethod
    def _http_request_sync(cls, path: str, payload: dict, config: dict):
        """Blocking HTTP request, executed on a worker thread."""
        base_url = str(config.get('base_url') or '').rstrip('/')
        api_key = str(config.get('api_key') or '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = 'Bearer ' + api_key
        request = urllib.request.Request(
            base_url + path,
            json.dumps(payload).encode('utf-8'),
            headers,
        )
        last = None
        retries = max(0, int(config.get('retries', RETRIES)))
        timeout = float(config.get('timeout', TIMEOUT))
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read())
            except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                last = exc
                if attempt < retries:
                    time.sleep(0.25 * (2**attempt))
        raise RuntimeError(str(last))

    @classmethod
    async def _request(cls, db: AsyncSession | None, path: str, payload: dict, *, config=None, audit_detail=None) -> dict:
        started = time.monotonic()
        config = config or await cls._runtime_config(db)
        base_url = str(config.get('base_url') or '').rstrip('/')
        api_key = str(config.get('api_key') or '')
        provider = str(config.get('provider') or 'openai-compatible').lower()
        # Local Ollama/OpenAI-compatible servers commonly do not require a key.
        local = provider in {'ollama', 'local', 'mock'} or base_url.startswith(
            ('http://localhost', 'http://127.0.0.1', 'http://[::1]')
        )
        if not base_url or (not api_key and not local) or provider == 'mock':
            await cls._audit(db, path, 'offline', 'offline', started, **(audit_detail or {}))
            raise RuntimeError('AI provider is not configured')
        try:
            result = await asyncio.to_thread(cls._http_request_sync, path, payload, config)
        except Exception as exc:
            await cls._audit(db, path, 'error', 'provider', started, **(audit_detail or {}))
            raise RuntimeError(str(exc)) from exc
        await cls._audit(db, path, 'ok', 'provider', started, **(audit_detail or {}))
        return result

    @classmethod
    async def chat(cls, db: AsyncSession | None, messages, **kwargs) -> str:
        prompt_code = kwargs.pop('prompt_code', 'tutor_chat')
        rendered, prompt_version = await cls._messages_with_prompt(
            db,
            messages,
            prompt_code,
            **{
                key: value
                for key, value in kwargs.items()
                if key not in {'model', 'temperature'}
            },
        )
        config = await cls._runtime_config(db, 'chat', kwargs.get('model'))
        payload = {
            'model': config['model'],
            'messages': rendered,
            'temperature': kwargs.get('temperature', 0),
        }
        result = await cls._request(
            db,
            '/chat/completions',
            payload,
            config=config,
            audit_detail={
                'model': config['model'],
                'provider': config['provider'],
                'config_id': config.get('config_id'),
                'prompt_code': prompt_code,
                'prompt_version': prompt_version,
            },
        )
        return result['choices'][0]['message']['content']

    @classmethod
    async def embeddings(cls, db: AsyncSession | None, texts, *, return_source=False, **kwargs):
        values = list(texts)
        config = await cls._runtime_config(db, 'embedding', kwargs.get('model'))
        try:
            result = await cls._request(
                db,
                '/embeddings',
                {'model': config['model'], 'input': values},
                config=config,
                audit_detail={
                    'model': config['model'],
                    'provider': config['provider'],
                    'config_id': config.get('config_id'),
                },
            )
            data = result.get('data', [])
            output = [item['embedding'] for item in data]
            # A successful HTTP response with missing/partial vectors is not a
            # usable provider result; use the same deterministic fallback and
            # report its source accurately.
            if len(output) != len(values) or any(
                not isinstance(vector, list) or not vector for vector in output
            ):
                raise ValueError('embedding response is incomplete')
            return (output, 'provider') if return_source else output
        except Exception:
            # Fixed hash vectors; use provider embeddings when semantic recall matters.
            output = []
            for value in values:
                vector = [
                    (
                        int.from_bytes(
                            hashlib.sha256(f'{index}:{value}'.encode()).digest()[:4],
                            'big',
                        )
                        / 2**32
                    )
                    * 2
                    - 1
                    for index in range(32)
                ]
                norm = math.sqrt(sum(item * item for item in vector)) or 1
                output.append([round(item / norm, 6) for item in vector])
            return (output, 'offline') if return_source else output

    @classmethod
    async def extract(cls, db: AsyncSession | None, text: str):
        text = str(text)
        try:
            raw = await cls.chat(
                db,
                [
                    {'role': 'system', 'content': 'Return JSON with nodes and edges only.'},
                    {'role': 'user', 'content': text},
                ],
                prompt_code='extract_concepts',
                text=text,
            )
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError('invalid extraction result')
            if not isinstance(obj.get('nodes'), list) or not isinstance(obj.get('edges'), list):
                raise ValueError('extraction result must contain nodes and edges arrays')
            obj['nodes'] = deduplicate(obj.get('nodes', []))
            return obj, 'provider'
        except Exception:
            return extract_knowledge(text), 'offline'

    @classmethod
    async def generate_quiz(cls, db: AsyncSession | None, text: str, count: int = 5):
        count = int(count)
        try:
            raw = await cls.chat(
                db,
                [
                    {
                        'role': 'system',
                        'content': f'Return JSON array of {count} quiz objects with question, options, answer.',
                    },
                    {'role': 'user', 'content': str(text)},
                ],
                prompt_code='generate_practice',
                text=str(text),
                count=count,
            )
            questions = json.loads(raw)
            if not isinstance(questions, list):
                raise ValueError('invalid quiz result')
            return questions, 'provider'
        except Exception:
            terms = deduplicate(extract_knowledge(str(text))['nodes'])
            return (
                [
                    {
                        'id': index,
                        'question': f'以下概念是什么：{term["name"]}？',
                        'options': [term['name'], '其他'],
                        'answer': term['name'],
                    }
                    for index, term in enumerate(terms[:count])
                ],
                'offline',
            )
