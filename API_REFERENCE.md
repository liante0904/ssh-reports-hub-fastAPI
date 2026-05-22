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
| `GET` | `/reports` | 리포트 목록 조회 (Pydantic 직렬화) | None | `test_main.py::test_get_reports_*` (6개), `test_api_mocked.py` |

**Query Params**:

| Param | Type | 설명 |
|-------|------|------|
| `q` | string | 제목 검색 (`article_title` ilike `%q%`) |
| `writer` | string | 작성자 검색 (`writer` ilike `%writer%`) |
| `company` | int | 증권사 필터 (`sec_firm_order`) |
| `board` | int | 게시판 필터 (`article_board_order`) |
| `has_summary` | bool | AI 요약 존재 필터 (`true` 시 gemini_summary IS NOT NULL + not empty) |
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
| `GET` | `/favorites` | 내 즐겨찾기 목록 | Bearer | — |
| `POST` | `/favorites/{report_id}` | 즐겨찾기 추가 | Bearer | — |
| `DELETE` | `/favorites/{report_id}` | 즐겨찾기 제거 | Bearer | — |

## Notes

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/notes` | 내 투자노트 목록 | Bearer | — |
| `POST` | `/notes` | 투자노트 생성 | Bearer | — |
| `PUT` | `/notes/{note_id}` | 투자노트 수정 | Bearer | — |
| `DELETE` | `/notes/{note_id}` | 투자노트 삭제 | Bearer | — |

> `/api/notes` prefix로도 동일한 엔드포인트 제공 (`include_in_schema=False`)

## External API (Public)

> **프론트엔드가 실제 사용하는 메인 엔드포인트 그룹.**  
> Base: `https://ssh-oci.duckdns.org/external/api`  
> ORDS 호환 응답 envelope: `{ items, hasMore, limit, offset, count, links }`

### `/external/api/search` — 통합 검색

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/search` | 다양한 필터로 리포트 통합 검색 | None | `test_main.py::test_external_api_search_*` (5개) |

**Query Params**:

| Param | Type | 설명 |
|-------|------|------|
| `title` | string | 제목 검색 |
| `writer` | string | 작성자 검색 |
| `company` | int | 증권사 필터 (`sec_firm_order`) |
| `board` | int | 게시판 필터 (`article_board_order`) |
| `mkt_tp` | `"global"` \| `"domestic"` | 마켓 타입 필터 |
| `has_summary` | bool | AI 요약 존재 필터 |
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
| `GET` | `/external/api/boards?company={order}` | 특정 증권사 게시판 목록 | None | `test_main.py::test_external_api_boards` (2개) |

### `/external/api/industry` — 산업별 리포트

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/industry` | 사전 정의된 산업분석 게시판 필터로 리포트 조회 | None | `test_main.py::test_external_api_industry` |

**Query Params**: `search`와 동일 (`writer`, `title`, `mkt_tp`, `company`, `board`, `limit`, `offset`)

## Consensus

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/consensus/latest` | 최신 컨센서스 | None | — |
| `GET` | `/consensus/history` | 컨센서스 히스토리 | None | — |
| `GET` | `/consensus/summary` | 컨센서스 요약 | None | — |
| `GET` | `/consensus/sectors` | 섹터별 컨센서스 | None | — |
| `GET` | `/consensus/screener` | 컨센서스 스크리너 | None | — |
| `GET` | `/consensus/top-picks` | 탑픽 종목 | None | — |
| `GET` | `/consensus/revision/1d` | 1일 리비전 데이터 | None | `test_consensus_revision.py` |
| `GET` | `/consensus/revision/1d/summary` | 1일 리비전 요약 | None | `test_consensus_revision.py` |

## Sentiment

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/sentiment` | 마켓 센티먼트 지표 목록 | None | — |
| `GET` | `/sentiment/summary` | 센티먼트 요약 | None | — |

> `/api/sentiment` prefix로도 동일 제공

## CNN Fear & Greed

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/sentiment/cnn/daily` | 일별 CNN Fear & Greed | None | — |
| `GET` | `/sentiment/cnn/history` | CNN F&G 히스토리 | None | — |
| `GET` | `/sentiment/cnn/latest` | 최신 CNN F&G 지수 | None | — |
| `POST` | `/sentiment/cnn/sync` | CNN F&G 동기화 트리거 | None | — |

> `/api/sentiment/cnn` prefix로도 동일 제공

## Disclosure (DART)

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/disclosure` | DART 공시 목록 | None | — |
| `GET` | `/disclosure/summary` | DART 공시 요약 | None | — |

> `/api/disclosure` prefix로도 동일 제공

## Screening

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/screening/files` | 스크리닝 파일 목록 | None | — |
| `GET` | `/screening/files/{filename}` | 스크리닝 파일 다운로드 | None | — |

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
| `test_main.py` | 21 | `/health`, `/reports` (6: pagination, search, writer, has_summary, board, JSON serialization), `/external/api/search` (5: basic, company+board, writer, has_summary, title), `/external/api/companies`, `/external/api/boards` (2), `/external/api/industry`, `/auth/telegram` (3) |
| `test_api_mocked.py` | 3 | `/health`, `/reports` (empty DB), auth 순수 로직 |
| `test_consensus_revision.py` | 6 | `/consensus/revision/1d`, `/consensus/revision/1d/summary` |
| `test_admin_metrics.py` | 4 | `/admin/metrics` |
| **총계** | **34** | |
