"""
커스텀 예외 클래스 계층

에러 핸들링 표준화를 위한 도메인별 예외 클래스.
전역 예외 핸들러(app/error_handlers.py)가 이 예외들을 일관된 JSON 응답으로 변환합니다.

사용 예:
    raise NotFoundException("Report not found")
    raise AuthenticationException("Invalid or expired token")
    raise ValidationException("Invalid filename format")
"""

from typing import Optional


class AppBaseException(Exception):
    """애플리케이션 기본 예외 — 모든 커스텀 예외의 부모."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        detail: str = "Internal Server Error",
        *,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.headers = headers


class NotFoundException(AppBaseException):
    """리소스를 찾을 수 없을 때 (404)."""

    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, detail: str = "Resource not found", **kwargs) -> None:
        super().__init__(detail, **kwargs)


class AuthenticationException(AppBaseException):
    """인증 실패 (401)."""

    status_code = 401
    error_code = "AUTHENTICATION_FAILED"

    def __init__(self, detail: str = "Authentication failed", **kwargs) -> None:
        headers = kwargs.pop("headers", None) or {"WWW-Authenticate": "Bearer"}
        super().__init__(detail, headers=headers, **kwargs)


class PermissionDeniedException(AppBaseException):
    """권한 부족 (403)."""

    status_code = 403
    error_code = "PERMISSION_DENIED"

    def __init__(self, detail: str = "Permission denied", **kwargs) -> None:
        super().__init__(detail, **kwargs)


class ValidationException(AppBaseException):
    """입력값 검증 실패 (400)."""

    status_code = 400
    error_code = "VALIDATION_FAILED"

    def __init__(self, detail: str = "Validation failed", **kwargs) -> None:
        super().__init__(detail, **kwargs)


class ServiceUnavailableException(AppBaseException):
    """서비스 이용 불가 (503)."""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"

    def __init__(self, detail: str = "Service unavailable", **kwargs) -> None:
        super().__init__(detail, **kwargs)


class ExternalServiceException(AppBaseException):
    """외부 서비스 연동 실패 (502)."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_FAILED"

    def __init__(self, detail: str = "External service failed", **kwargs) -> None:
        super().__init__(detail, **kwargs)


class FileTooLargeException(AppBaseException):
    """파일 크기 초과 (413)."""

    status_code = 413
    error_code = "FILE_TOO_LARGE"

    def __init__(self, detail: str = "File too large", **kwargs) -> None:
        super().__init__(detail, **kwargs)
