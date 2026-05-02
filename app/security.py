import hashlib
import hmac
import logging
import re
import time
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from .settings import Settings

SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(jwt_secret_key|telegram_bot_token|postgres_password|password|secret|token)=([^,\s]+)"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(str(record.msg))
        if record.args:
            record.args = tuple(mask_sensitive(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def mask_sensitive(value: str) -> str:
    return SENSITIVE_VALUE_RE.sub(r"\1=***", value)


def configure_sensitive_log_filter() -> None:
    sensitive_filter = SensitiveDataFilter()
    for logger_name in ("uvicorn.access", "uvicorn.error", "app"):
        logging.getLogger(logger_name).addFilter(sensitive_filter)


def require_jwt_secret(settings: Settings) -> None:
    if not settings.jwt_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret is not configured",
        )


def create_access_token(subject: int, settings: Settings) -> str:
    require_jwt_secret(settings)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(subject),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict:
    require_jwt_secret(settings)
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def verify_telegram_data(data: dict, settings: Settings) -> tuple[bool, str]:
    bot_token = settings.clean_telegram_bot_token
    if not bot_token:
        return False, "TELEGRAM_BOT_TOKEN is not configured"

    check_hash = data.get("hash")
    if not check_hash:
        return False, "Missing Telegram hash"

    auth_date = data.get("auth_date", 0)
    if time.time() - auth_date > settings.telegram_auth_max_age_seconds:
        return False, "Telegram auth data is expired"

    data_list = [f"{key}={value}" for key, value in sorted(data.items()) if key != "hash" and value is not None]
    data_check_string = "\n".join(data_list)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, check_hash):
        return False, "Telegram signature mismatch"
    return True, ""
