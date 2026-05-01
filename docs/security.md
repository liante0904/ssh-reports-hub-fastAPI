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
- `/auth/telegram`은 별도 제한값 `RATE_LIMIT_AUTH`를 적용합니다.
- 기본값:
  - `RATE_LIMIT_DEFAULT=120/minute`
  - `RATE_LIMIT_AUTH=10/minute`

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
RATE_LIMIT_AUTH=10/minute
```

## 아직 인프라에서 처리해야 할 항목

- Nginx 또는 Traefik으로 Uvicorn 직접 노출 차단
- Let's Encrypt 인증서 적용 및 HTTP to HTTPS 리다이렉트
- 외부 방화벽에서 80/443만 공개하고 DB/SSH는 관리자 IP로 제한
- 운영 로그 수집 시스템에서도 민감정보 마스킹 규칙 적용
