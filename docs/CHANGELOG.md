# Changelog

## 2026-04-30

### Added

- 투자 메모(`investment_notes`) CRUD API 기능을 추가했습니다.
- `ssh-library` 공통 라이브러리에 `InvestmentNoteManager`를 추가하여 외부 연동을 지원합니다.
- 순환 참조 해결을 위해 `app/dependencies.py`를 신설하고 인증 로직을 분리했습니다.
- 향후 코드 품질 개선을 위한 `docs/refactoring.md` 계획서를 작성했습니다.

### Changed

- `app/models.py`와 `app/schemas.py`에 투자 메모 관련 모델 및 스키마를 추가했습니다.
- `app/main.py`에 `InvestmentNote` 라우터를 등록했습니다.

### Verification

- `PYTHONPATH=. pytest` (7 passed)
- `ssh-library` 기존 테스트 통과 확인 (3 passed)
- 수동 컴파일 확인 (`python3 -m py_compile`)

## 2026-04-21

### Added

- Oracle ORDS 호환 라우트 `/ords/admin/data_main_daily_send/industry`와 `/ords/admin/data_main_daily_send/search/`를 추가했습니다.
- ORDS 호환 레이어의 목적, 응답 형태, 필터 조건, 제거 기준을 `docs/ords-compat.md`에 문서화했습니다.
- Codex/Gemini/Claude 작업용 ignore 파일과 에이전트 지침 문서를 추가했습니다.
- ORDS 호환 라우트의 응답 형태와 필터 동작 회귀 테스트를 추가했습니다.

### Changed

- `/reports` 라우트를 `app/routers/reports.py`로 분리했습니다.
- ORDS 호환 라우트를 `app/routers/ords_compat.py`로 분리해 `main.py`가 앱 조립 중심으로 남도록 정리했습니다.
- 운영 컨테이너의 `DB_BACKEND`를 `postgres`로 전환해 리포트 조회가 `TB_SEC_REPORTS`를 사용하도록 변경했습니다.
- Mock DB 테스트가 실제 `/reports` 의존성인 `get_reports_db`를 override하도록 수정했습니다.

### Verification

- `POSTGRES_HOST=127.0.0.1 uv run pytest`
- 컨테이너 내부 확인:
  - `DB_BACKEND=postgres`
  - `MAIN_TABLE_NAME=TB_SEC_REPORTS`
  - reports DB URL prefix: `postgresql`
- `/health`, `/reports?limit=1`, `/ords/admin/data_main_daily_send/search/?limit=1`, `/ords/admin/data_main_daily_send/industry?limit=3`

## 2026-04-20

### Added

- `pydantic-settings` 기반 애플리케이션 보안 설정을 추가했습니다.
- JWT 발급 토큰에 `exp`, `iat`, `type` 클레임을 추가했습니다.
- `OAuth2PasswordBearer` 기반 Bearer 토큰 검증을 적용했습니다.
- `slowapi` Rate Limiting을 추가했습니다.
- CORS 허용 Origin/헤더/메서드를 설정값 기반으로 제한했습니다.
- 응답 보안 헤더 미들웨어를 추가했습니다.
- 민감정보 로그 마스킹 필터를 추가했습니다.
- Telegram 인증 검증에서 `hmac.compare_digest`를 사용하도록 변경했습니다.
- Pydantic 요청 스키마와 `/reports` 쿼리 파라미터에 엄격한 길이/범위 검증을 추가했습니다.
- 보안 적용 내역 문서와 체인지로그를 추가했습니다.

### Changed

- `/auth/telegram` 응답 형식은 유지하면서 토큰 만료 정책을 서버 설정으로 관리하도록 변경했습니다.
- CORS의 `allow_methods`, `allow_headers`, `expose_headers`를 와일드카드에서 명시 목록으로 변경했습니다.
- `/reports/` 요청이 `/reports`로 307 리다이렉트되지 않도록 `redirect_slashes=False`와 trailing slash 라우트를 추가했습니다.
- 프록시 환경에서 HTTPS 스킴을 FastAPI가 인식하도록 `ProxyHeadersMiddleware`를 추가했습니다.

### Verification

- Mock DB 기반 API 테스트에 보안 헤더, 입력 검증, 인증 필요 여부, 유효 JWT 접근 테스트를 추가했습니다.
- `/reports/`가 리다이렉트 없이 바로 `200`을 반환하는 회귀 테스트를 추가했습니다.
