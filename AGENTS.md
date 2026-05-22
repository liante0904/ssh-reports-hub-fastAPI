# Agent Notes — ssh-reports-hub-fastAPI

## 서버 정보

| 호스트명 | IP | 역할 | SSH 별칭 |
|---|---|---|---|
| 배포 서버 (Production) | `132.145.91.78` | 실질 소스 실행 및 배포 서버 | `ssh oci` |
| 테스트 서버 (Development) | `64.110.82.78` | 개발 및 테스트 서버 (현재) | `ssh oci2` |

> **[IMPORTANT] 인프라 및 속도 가이드**
> - 이 환경은 **초고속 내부 전용망**입니다. 모든 네트워크 응답은 5초 이내여야 합니다.
> - 작업 시 10초 이상 지체하지 마십시오. 서버 이슈 시 즉시 프로세스를 죽이고 다시 띄우는 것이 가장 빠릅니다.

This is a FastAPI service for Telegram-authenticated research report lookup and keyword alerts.  
**PostgreSQL backend only.** Oracle ATP / ORDS migration completed (2026-04-21).

## Current Structure

- `app/main.py` — app assembly, middleware, auth, keyword CRUD.
- `app/routers/reports.py` — `/reports` API (Pydantic serialized).
- `app/routers/external_api.py` — `/external/api/*` (search, companies, boards, industry). **프론트엔드가 직접 사용하는 메인 API.**
- `app/models.py` — SQLAlchemy models. `MAIN_TABLE_NAME` = `tbl_sec_reports` (PostgreSQL).
- `app/database.py` — report & keyword DB sessions.
- `app/schemas.py` — Pydantic response/request schemas.

## Critical Rules

### 1. External API 보호
`/external/api/search`, `/external/api/companies`, `/external/api/boards`, `/external/api/industry` 는 프론트엔드(Netlify)가 직접 호출하는 엔드포인트다. **절대 응답 형식을 변경하거나 제거하지 말 것.**

응답 envelope: `{ items, hasMore, limit, offset, count, links }`

### 2. Pydantic Serialization Safety
`/reports` 엔드포인트는 `response_model=list[SecReportResponse]`로 Pydantic 직렬화를 사용한다. **스키마에 `bytes` 타입 필드를 추가하지 말 것.** PostgreSQL `BYTEA` 컬럼은 `memoryview`로 반환되어 Pydantic JSON 직렬화를 깨뜨린다.

> **2026-05-21 장애**: `PdfArchiveResponse.pdf_hash: Optional[bytes]` 필드가 원인. 제거 완료.

### 3. nginx DNS Caching
`external-nginx`는 Docker DNS를 한 번만 resolve하고 캐싱한다. **백엔드 컨테이너 재시작 후에는 반드시 `external-nginx`도 재시작할 것.**

```bash
ssh oci "docker restart ssh-reports-hub-fastapi-prod && docker restart external-nginx"
```

> **2026-05-21 장애**: 백엔드 컨테이너 IP 변경 시 external-nginx가 옛 IP로 프록시 시도 → 502. nginx 재시작으로 해결.

### 4. 테스트 커버리지
External API 엔드포인트 추가/변경 시 `tests/test_main.py`에 반드시 테스트 추가. 프론트엔드 연동 테스트는 `test/integration/api.test.js`.

## Testing

```bash
# Backend
uv run pytest                          # 32 tests

# Frontend (from apps/frontend/ssh-reports-hub)
node test/integration/api.test.js      # Production integration
node test/verify-api-coverage.js       # API doc coverage check
```

## Safety

- Do not commit `.env`, local DB files, logs, or virtualenv contents.
- Avoid broad rewrites in `main.py`; add routers/modules instead.
- `app/schemas.py` 필드 추가 시 `bytes` 타입 사용 금지.
- Production endpoint 변경은 프론트엔드 팀과 사전 협의.
