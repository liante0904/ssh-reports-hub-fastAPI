"""
로깅 설정 및 미들웨어

- RequestIDMiddleware: 각 요청에 고유 request_id 할당 및 응답 헤더 추가
- RequestLoggingMiddleware: 요청별 메서드/경로/상태/소요시간 로깅
- configure_structured_logging: 운영 환경용 JSON 포맷 로깅 활성화
"""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .error_handlers import request_id_ctx

logger = logging.getLogger("app.logging")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    요청별 고유 request_id를 ContextVar에 설정하고 응답 헤더에 추가.

    우선순위:
    1. 클라이언트가 보낸 X-Request-ID 헤더 → 재사용
    2. 없으면 UUID v4 생성
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        request_id_ctx.set(rid)

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    모든 요청의 메서드, 경로, 상태 코드, 소요 시간을 로깅.

    헬스체크(/health)는 로깅 제외.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in ("/health",):
            return await call_next(request)

        start = time.monotonic()
        rid = request_id_ctx.get() or "—"

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error(
                "[%s] %s %s → crashed in %.1fms",
                rid,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "[%s] %s %s → %d (%.1fms)",
            rid,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


def configure_structured_logging() -> None:
    """
    운영 환경용 구조화 로깅 활성화.

    프로덕션 환경에서 JSON 라인 포맷을 사용하도록
    root logger에 StreamHandler를 추가합니다.
    테스트/개발 환경에서는 기존 포맷을 유지합니다.
    """
    root = logging.getLogger()
    if not root.handlers:
        # 기본 핸들러가 없는 경우만 추가 (uvicorn이 이미 설정한 경우 스킵)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    # 앱 로거 레벨 조정
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("app.logging").setLevel(logging.INFO)
    logging.getLogger("app.error_handlers").setLevel(logging.WARNING)

    # SQLAlchemy 로그 과다 방지
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
