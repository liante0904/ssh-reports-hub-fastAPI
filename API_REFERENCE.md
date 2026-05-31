# API Reference — ssh-reports-hub-fastAPI

> 각 섹션 우측에 대응 테스트 파일을 명시. 테스트와 엔드포인트는 1:1 매치.
> 프론트엔드가 실제 호출하는 External API 엔드포인트는 [External API](#external-api-public) 섹션 참고.

## Health

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/health` | 서버 상태 확인 | None | `test_main.py::test_health_check`, `test_api_mocked.py::test_health_check_mocked` |

## Auth

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `POST` | `/auth/telegram` | Telegram OAuth 로그인 → JWT 발급 | Telegram hash | `test_main.py::test_auth_telegram_*` (3개) |
| `POST` | `/api/auth/telegram` | (alias) | Telegram hash | `test_main.py` |

## Reports

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/reports` | 리포트 목록 조회 (Pydantic 직렬화) | None | `test_main.py::test_get_reports_*`, `test_enricher.py` |

**Query Params**:

| Param | Type | 설명 |
|-------|------|------|
| `q` | string | 제목 검색 (`article_title` ilike `%q%`) |
| `writer` | string | 작성자 검색 (`writer` ilike `%writer%`) |
| `company` | int | 증권사 필터 (`sec_firm_order`) |
| `board` | int | 게시판 필터 (`article_board_order`) |
| `has_summary` | bool | AI 요약 존재 필터 |
| `tag` | string | Enricher 태그 필터 (예: "반도체", "AI") |
| `sector` | string | Enricher 섹터 필터 (예: "자동차") |
| `stock` | string | Enricher 종목명 필터 (예: "삼성전자") |
| `limit` | int (1-100) | 페이지 크기 (기본값 50) |
| `offset` | int (>=0) | 페이지 오프셋 (기본값 0) |

**Response**: `list[SecReportResponse]` — Pydantic JSON 직렬화된 배열.

> ⚠️ 2026-05-21 장애 원인: `PdfArchiveResponse.pdf_hash: Optional[bytes]` 필드가 PostgreSQL `BYTEA` → `memoryview` 변환 시 Pydantic JSON 직렬화를 깨뜨렸음. 해당 필드 제거 완료.

## Keywords

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/keywords` | 내 키워드 목록 조회 | Bearer | — |
| `POST` | `/keywords` | 키워드 추가 | Bearer | — |
| `POST` | `/keywords/sync` | 키워드 일괄 동기화 (전체 덮어쓰기) | Bearer | — |
| `PUT` | `/keywords/{keyword_id}` | 키워드 수정 | Bearer | — |

## Favorites

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/favorites` | 내 즐겨찾기 목록 | Bearer | `test_main.py::test_favorites_*` |
| `POST` | `/favorites/{report_id}` | 즐겨찾기 추가 | Bearer | `test_main.py` |
| `DELETE` | `/favorites/{report_id}` | 즐겨찾기 제거 | Bearer | `test_main.py` |

## External API (Public)

> **프론트엔드가 실제 사용하는 메인 엔드포인트 그룹.**  
> Base: `https://ssh-oci.duckdns.org/external/api`  
> ORDS 호환 응답 envelope: `{ items, hasMore, limit, offset, count, links }`

### `/external/api/search` — 통합 검색

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/search` | 다양한 필터로 리포트 통합 검색 | None | `test_main.py::test_external_api_search_*`, `test_enricher.py` |

**Query Params**:

| Param | Type | 설명 |
|-------|------|------|
| `title` | string | 제목 검색 |
| `writer` | string | 작성자 검색 |
| `company` | int | 증권사 필터 (`sec_firm_order`) |
| `board` | int | 게시판 필터 (`article_board_order`) |
| `mkt_tp` | `"global"` \| `"domestic"` | 마켓 타입 필터 |
| `has_summary` | bool | AI 요약 존재 필터 |
| `tag` | string | Enricher 태그 필터 |
| `sector` | string | Enricher 섹터 필터 |
| `stock` | string | Enricher 종목명 필터 |
| `outlook` | bool | 시장 전망 리포트만 보기 (전망포럼, 연간전망 등) |
| `outlook_year` | int | 특정 연도 전망 필터 (예: 2026) |
| `report_id` | int | 단일 리포트 조회 (공유 링크용) |
| `limit` | int (1-100) | 페이지 크기 (기본값 100) |
| `offset` | int (>=0) | 페이지 오프셋 (기본값 0) |

### `/external/api/companies` — 증권사 목록

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/companies` | 리포트 존재하는 증권사 목록 + 리포트 수 | None | `test_main.py::test_external_api_companies` |

### `/external/api/boards` — 게시판 목록

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/boards?company={order}` | 특정 증권사 게시판 목록 | None | `test_main.py::test_external_api_boards` |

### `/external/api/industry` — 산업별 리포트

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/industry` | 사전 정의된 산업분석 게시판 필터로 리포트 조회 | None | `test_main.py::test_external_api_industry` |

**Query Params**: `search`와 동일 (`writer`, `title`, `mkt_tp`, `company`, `board`, `limit`, `offset`)

## Admin

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/admin/metrics` | 서버 메트릭 (CPU, Memory, Disk) | Bearer (admin) | `test_admin_metrics.py` |
| `GET` | `/admin/logs` | 로그 목록 | Bearer (admin) | — |
| `GET` | `/admin/logs/view` | 로그 뷰어 | Bearer (admin) | — |

---

## 테스트 매핑

| 테스트 파일 | 테스트 수 | 커버리지 |
|-------------|-----------|----------|
| `test_main.py` | 28 | `/health`, `/reports`, `/external/api/search`, `/external/api/companies`, `/external/api/boards`, `/external/api/industry`, `/auth/telegram`, `/favorites` |
| `test_api_mocked.py` | 3 | `/health`, `/reports` (empty DB), auth 순수 로직 |
| `test_admin_metrics.py` | 4 | `/admin/metrics` |
| `test_enricher.py` | 12 | 태그 추출 로직, `/external/api/search` 태그/섹터/종목 필터 |
| **총계** | **47** | |
