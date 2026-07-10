# Backend Development Guide (CI/CD, Refactoring & Security)

> **통합 일자**: 2026-07-01
> **대상 원본 문서**: CI_CD.md, refactoring.md, security.md

---

## [통합 섹션] CI_CD

# CI / CD / Release Flow

이 문서는 백엔드의 로컬 검증과 현재 자동 배포 흐름을 정리합니다.

## 현재 전제

- `.github/workflows/deploy.yml`은 `main` push와 수동 dispatch에서 실행된다.
- CI 테스트가 통과하면 arm64 이미지를 GHCR에 push하고 운영 서버에 blue/green으로 자동 배포한다.
- 따라서 `main` push 전 로컬 검증이 필요하며, 운영 배포를 원하지 않는 변경은 main에 push하지 않는다.

## 가장 효율적인 최소 루틴

1. 로컬에서 `make verify`
- `uv run pytest`
- `uv run python -m compileall app tests`

2. `main` 푸시
- 검증을 통과한 변경만 올린다.
- 혼자 작업할 때는 PR보다 이 루틴이 빠르다.

3. 배포 후 스모크 체크
- `/health`
- 주요 신규 API 1개
- 프론트와 붙는 핵심 응답 1개

## 자동 배포 흐름

1. `uv sync --frozen` 및 `tests/test_api_mocked.py` 실행
2. `ghcr.io/liante0904/ssh-reports-hub-fastapi` arm64 이미지 build/push
3. `deploy_prepare.py`로 서버 checkout을 요청 SHA에 고정하고 `generate_env.py` 실행
4. 비활성 blue/green 컨테이너 기동
5. `external-nginx` 내부 `/health` 확인 후 `target.inc` 전환 및 nginx reload
6. 성공 후 이전 컨테이너 정리; health 실패 시 신규 컨테이너 제거 후 workflow 실패

추가 자동화 후보는 전체 테스트/정적 검사 확대와 배포 후 주요 API smoke test다.

## 이 프로젝트에서 먼저 챙길 것

- 백엔드: `make verify`
- 운영 확인: `/health`, 주요 API 1회 점검
- 프론트와 맞물리는 계약: `docs/`와 라우터의 응답 shape 동기화

## Blue/Green 배포 메모

- 앱 컨테이너는 `ssh-reports-hub-fastapi-blue`, `ssh-reports-hub-fastapi-green` 두 서비스 중 하나만 active target으로 둔다.
- `external-nginx`의 `/etc/nginx/conf.d/target.inc`가 현재 active target을 결정한다.
- GitHub Actions가 `~/secrets/deploy_prepare.py`와 `~/secrets/generate_env.py`를 호출해 서버 checkout과 `.env`를 준비한다. 운영에서 이를 수동 선행 작업으로 반복하지 않는다.
- 신규 color 컨테이너를 먼저 띄우고, `external-nginx` 컨테이너 내부에서 `/health`가 성공할 때만 `target.inc`를 바꾼 뒤 `nginx -s reload` 한다.
- 초기 전환 시 기존 `ssh-reports-hub-fastapi-prod`는 새 color 전환이 성공한 뒤에만 제거한다.

### prod 단일 컨테이너에서 첫 전환

현재 운영 컨테이너가 `ssh-reports-hub-fastapi-prod`뿐이어도 첫 배포는 blue를 대상으로 한다. 이때 트래픽은 다음 순서로 이동한다.

1. `external-nginx`는 아직 `target.inc`의 prod upstream을 바라본다.
2. CI가 `ssh-reports-hub-fastapi-blue`를 새 이미지로 띄운다.
3. `external-nginx` 컨테이너 내부에서 `http://ssh-reports-hub-fastapi-blue:8000/health`를 확인한다.
4. 성공하면 `target.inc`를 blue로 바꾸고 nginx를 reload한다.
5. reload 성공 후에만 기존 `ssh-reports-hub-fastapi-prod`를 stop/rm 한다.

따라서 prod 컨테이너는 전환 성공 전까지 살아 있고, health check 실패 시 새 blue만 제거된다. 이 구조가 작동하려면 `external-nginx` 배포가 먼저 완료되어 `target.inc` include 구조가 적용되어 있어야 한다.

## 메모

- workflow의 실제 테스트는 현재 `tests/test_api_mocked.py`다. 로컬 `make verify`와 범위가 같다고 가정하지 않는다.
- 자동 롤백은 트래픽 전환 전 health 실패에 대해 신규 color를 제거하는 방식이다. 전환 이후 장애는 별도 운영 판단이 필요하다.


---

## [통합 섹션] refactoring

# Refactoring Plan

코드 품질과 유지보수성을 높이기 위한 리팩토링 계획입니다. 난이도가 낮은 순서부터 정렬되어 있습니다.

## 1. 공통 컬럼 Mixin 도입 (완료)
- **대상:** `app/models.py`
- **내용:** `TimestampMixin`을 통해 `created_at`, `updated_at` 중복 제거 완료.

## 2. 전역 설정(Settings) 의존성 주입 최적화 (완료)
- **대상:** `app/dependencies.py`, `app/main.py`
- **내용:** `get_settings_dep`를 통한 의존성 주입 구조 개선 완료.

## 3. Pydantic 스키마 검증 강화 (완료)
- **대상:** `app/schemas.py`
- **내용:** 좌표 범위 및 HEX 색상 코드 검증(`field_validator`) 추가 완료.

## 4. 에러 핸들링 및 로깅 표준화 (완료)
- **대상:** `app/exceptions.py` (신규), `app/error_handlers.py` (신규), `app/logging_config.py` (신규), `app/routers/`, `app/main.py`, `app/security.py`, `app/dependencies.py`
- **내용:** 커스텀 Exception 클래스(`AppBaseException`, `NotFoundException`, `AuthenticationException`, `PermissionDeniedException`, `ValidationException`, `ServiceUnavailableException`, `ExternalServiceException`, `FileTooLargeException`)를 도입하고 전역 Exception Handler를 등록하여 에러 응답 형식을 통일 완료. RequestID 및 RequestLogging 미들웨어 추가, 구조화 로깅 설정 도입.

## 5. 라이브러리(ssh-library) 모델 통합 (난이도: 상)
- **대상:** `ssh-library`, `app/models.py`
- **내용:** 라이브러리 내부에 SQLAlchemy 모델 정의를 포함시켜 앱과 라이브러리 간의 테이블 명세 중복을 제거합니다.


---

## [통합 섹션] security

# 보안 적용 내역

## 현재 반영된 백엔드 보안

프론트엔드 코드를 변경하지 않고 FastAPI 서버에서 처리 가능한 항목을 우선 반영했습니다.

### JWT 인증

- 기존 `Authorization: Bearer <token>` 방식은 유지했습니다.
- `/auth/telegram` 성공 시 발급되는 JWT에 `sub`, `type`, `iat`, `exp` 클레임을 포함합니다.
- 보호 API는 `OAuth2PasswordBearer`로 Bearer 토큰을 추출하고, 만료되었거나 형식이 잘못된 토큰을 `401`로 거부합니다.
- `JWT_SECRET_KEY`는 최소 32자 이상으로 설정되어야 토큰 발급/검증이 동작합니다. 미설정 또는 약한 값이면 `503`으로 실패합니다.
- `ALLOWED_TELEGRAM_USER_IDS`가 비어 있으면 모든 유효한 Telegram 사용자가 로그인할 수 있습니다. private 서비스로 쓰려면 쉼표로 구분된 사용자 ID 목록을 넣어야 합니다.

### Telegram 인증 검증

- Telegram Login Widget 검증은 `hmac.compare_digest`로 비교합니다.
- `TELEGRAM_BOT_TOKEN`이 비어 있으면 인증을 실패 처리합니다.
- `auth_date`는 `TELEGRAM_AUTH_MAX_AGE_SECONDS` 안에 있는 요청만 허용합니다.

### CORS

- 허용 Origin은 `CORS_ALLOW_ORIGINS` 환경 변수로 관리합니다.
- 기본 허용값은 Netlify 운영 도메인과 로컬 개발 포트입니다.
- 현재 기본 허용값에는 `https://ssh-private-hub.netlify.app`와 `http://localhost:5174`가 포함됩니다.
- 허용 메서드는 `GET`, `POST`, `PUT`, `OPTIONS`로 제한했습니다.
- 허용 헤더는 `Authorization`, `Content-Type`으로 제한했습니다.

### Rate Limiting

- `slowapi`를 적용해 기본 요청 제한을 둡니다.
- 현재는 공통 기본 제한만 적용합니다. `/auth/telegram` 전용 제한은 잠시 빼고 안정화 우선으로 두었습니다.
- 기본값:
  - `RATE_LIMIT_DEFAULT=120/minute`

### 입력 검증

- Pydantic 스키마에 길이, 양수 조건, extra field 금지를 적용했습니다.
- `/reports`의 `limit`은 `1..100`, `offset`은 `0 이상`, `q`는 최대 100자로 제한합니다.
- 키워드는 공백 제거 후 `1..80`자, 동기화 요청은 최대 50개까지 허용합니다.

### 보안 헤더

모든 응답에 다음 헤더를 적용합니다.

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Cache-Control: no-store`
- HTTPS 또는 `X-Forwarded-Proto: https` 요청에는 `Strict-Transport-Security`를 추가합니다.

### 로그 마스킹

- `password`, `secret`, `token`, `jwt_secret_key`, `telegram_bot_token`, `postgres_password` 형태의 값은 로그 필터에서 `***`로 마스킹합니다.

## 환경 변수

```env
JWT_SECRET_KEY=change-this-to-a-random-32-plus-character-secret
ACCESS_TOKEN_EXPIRE_MINUTES=1440
TELEGRAM_BOT_TOKEN=123456:telegram-bot-token
TELEGRAM_AUTH_MAX_AGE_SECONDS=86400
ALLOWED_TELEGRAM_USER_IDS=123456789
CORS_ALLOW_ORIGINS=https://ssh-private-hub.netlify.app,https://ssh-oci.netlify.app,https://ssh-oci.duckdns.org,http://localhost:5174,http://localhost:5173,http://localhost:3000,http://localhost:8888
RATE_LIMIT_DEFAULT=120/minute
```

## 아직 인프라에서 처리해야 할 항목

- Nginx 또는 Traefik으로 Uvicorn 직접 노출 차단
- Let's Encrypt 인증서 적용 및 HTTP to HTTPS 리다이렉트
- 외부 방화벽에서 80/443만 공개하고 DB/SSH는 관리자 IP로 제한
- 운영 로그 수집 시스템에서도 민감정보 마스킹 규칙 적용


---
