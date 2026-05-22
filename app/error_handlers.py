"""
전역 예외 핸들러

모든 커스텀 예외(AppBaseException 계열)와 표준 HTTPException을
일관된 JSON 응답 형식으로 변환합니다.

응답 형식: { "detail": str, "error_code": str, "request_id": str }
"""

import logging
import uuid
from contextvars import ContextVar

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import AppBaseException

logger = logging.getLogger("app.error_handlers")

# 요청별 request_id 전파용 ContextVar
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def _extract_request_id(request: Request) -> str:
    """요청에서 request_id를 추출하거나 생성."""
    rid = request_id_ctx.get()
    if rid:
        return rid
    # 헤더에서 클라이언트가 보낸 request-id 재사용 시도
    rid = request.headers.get("x-request-id", "")
    if rid:
        return rid
    return str(uuid.uuid4())


def _error_response(
    status_code: int,
    detail: str,
    *,
    error_code: str = "UNKNOWN",
    request_id: str = "",
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content = {
        "detail": detail,
        "error_code": error_code,
        "request_id": request_id,
    }
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=headers,
    )


async def app_base_exception_handler(request: Request, exc: AppBaseException) -> JSONResponse:
    """커스텀 예외 → 일관된 JSON 에러 응답."""
    request_id = _extract_request_id(request)
    logger.warning(
        "AppException status=%d code=%s detail=%s request_id=%s path=%s",
        exc.status_code,
        exc.error_code,
        exc.detail,
        request_id,
        request.url.path,
    )
    return _error_response(
        status_code=exc.status_code,
        detail=exc.detail,
        error_code=exc.error_code,
        request_id=request_id,
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """표준 HTTPException (FastAPI/Starlette) → JSON 에러 응답."""
    request_id = _extract_request_id(request)
    logger.warning(
        "HTTPException status=%d detail=%s request_id=%s path=%s",
        exc.status_code,
        exc.detail,
        request_id,
        request.url.path,
    )
    return _error_response(
        status_code=exc.status_code,
        detail=str(exc.detail),
        error_code="HTTP_ERROR",
        request_id=request_id,
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """미처리 예외 → 500 에러 응답 (catch-all)."""
    request_id = _extract_request_id(request)
    logger.exception(
        "Unhandled exception type=%s detail=%s request_id=%s path=%s",
        type(exc).__name__,
        str(exc),
        request_id,
        request.url.path,
    )
    return _error_response(
        status_code=500,
        detail="Internal Server Error",
        error_code="INTERNAL_ERROR",
        request_id=request_id,
    )


def register_exception_handlers(app) -> None:
    """FastAPI 앱에 전역 예외 핸들러를 등록합니다."""
    app.add_exception_handler(AppBaseException, app_base_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    logger.info("Global exception handlers registered")
