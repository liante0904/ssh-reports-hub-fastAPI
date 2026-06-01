"""
Redis 캐시 유틸리티

API 응답을 Redis에 캐싱하여 PostgreSQL 쿼리 부하를 줄이고 응답 속도를 개선합니다.

사용법:
    from .cache import cache_response

    @router.get("/search")
    @cache_response(ttl=30)   # 30초 TTL
    async def search_reports(...):
        ...

캐시 키 전략:
    - request.url (query string 포함)을 키로 사용
    - 서로 다른 사용자/파라미터 조합이 자연스럽게 분리됨
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Optional

import redis.asyncio as aioredis
from fastapi import Request

from .settings import get_settings

logger = logging.getLogger("app.cache")

# ---------------------------------------------------------------------------
# Redis 연결 풀 (전역 싱글톤)
# ---------------------------------------------------------------------------

_redis_pool: Optional[aioredis.Redis] = None
_pool_lock = asyncio.Lock()


async def get_redis() -> Optional[aioredis.Redis]:
    """Redis 연결 풀을 반환합니다. 연결 실패 시 None."""
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.ping()
            return _redis_pool
        except Exception:
            _redis_pool = None  # 연결이 끊겼으면 재연결

    settings = get_settings()
    if not settings.redis_configured:
        return None

    async with _pool_lock:
        if _redis_pool is not None:
            return _redis_pool
        try:
            _redis_pool = aioredis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                socket_timeout=settings.redis_socket_timeout,
                socket_connect_timeout=settings.redis_connect_timeout,
                decode_responses=False,  # 바이너리로 저장 (JSON 직렬화)
            )
            await _redis_pool.ping()
            logger.info("Redis connected: %s", settings.redis_url)
            return _redis_pool
        except Exception as exc:
            logger.warning("Redis unavailable (caching disabled): %s", exc)
            return None


def _cache_key_from_request(request: Request, prefix: str = "api") -> str:
    """요청 URL을 기반으로 Redis 키 생성"""
    raw = str(request.url)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _to_json_safe(obj):
    """Pydantic 모델과 SQLAlchemy 객체를 JSON-safe 타입으로 재귀 변환"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        # Pydantic v2 모델
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        # Pydantic v1 모델
        return obj.dict()
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_json_safe(item) for item in obj]
    # SQLAlchemy row 등 그 외는 str 변환
    return str(obj)


def _serialize(obj) -> bytes:
    return json.dumps(_to_json_safe(obj), ensure_ascii=False).encode("utf-8")


def _deserialize(data: bytes):
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------------------
# 데코레이터: cache_response
# ---------------------------------------------------------------------------


def cache_response(
    ttl: int = 30,
    prefix: str = "api",
    enabled: bool = True,
):
    """
    FastAPI 엔드포인트 응답을 Redis에 캐싱하는 데코레이터.

    Args:
        ttl: 캐시 수명 (초), 기본 30초
        prefix: Redis 키 접두사
        enabled: False면 캐싱 비활성화 (테스트/디버깅용)
    """
    def decorator(func: Callable):
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not enabled:
                return await func(*args, **kwargs)

            # request 객체 찾기
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                # keyword arguments 에서 찾기
                request = kwargs.get("request")

            if request is None:
                return await func(*args, **kwargs)

            redis_conn = await get_redis()
            if redis_conn is None:
                return await func(*args, **kwargs)

            cache_key = _cache_key_from_request(request, prefix)

            # 캐시 읽기 시도
            try:
                cached = await redis_conn.get(cache_key)
                if cached is not None:
                    logger.debug("Cache HIT: %s", cache_key)
                    return _deserialize(cached)
            except Exception as exc:
                logger.debug("Cache read error (fallback to origin): %s", exc)

            # origin 호출
            result = await func(*args, **kwargs)

            # 응답 캐싱 (백그라운드 - 실패해도 무시)
            try:
                await redis_conn.setex(
                    cache_key,
                    ttl,
                    _serialize(result),
                )
                logger.debug("Cache SET: %s (ttl=%ds)", cache_key, ttl)
            except Exception as exc:
                logger.debug("Cache write error: %s", exc)

            return result

        # FastAPI 의존성 주입을 위해 원본 함수 시그니처 보존
        wrapper.__signature__ = sig
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 캐시 무효화 유틸리티
# ---------------------------------------------------------------------------


async def invalidate_prefix(prefix: str = "api") -> int:
    """
    특정 prefix로 시작하는 모든 캐시 키를 삭제합니다.
    새 리포트가 스크래핑되었을 때 호출합니다.

    Returns:
        삭제된 키 개수
    """
    redis_conn = await get_redis()
    if redis_conn is None:
        return 0

    count = 0
    cursor = 0
    pattern = f"{prefix}:*"
    while True:
        cursor, keys = await redis_conn.scan(cursor, match=pattern, count=100)
        if keys:
            count += await redis_conn.delete(*keys)
        if cursor == 0:
            break
    logger.info("Cache invalidated: prefix=%s, deleted=%d keys", prefix, count)
    return count
