# API Reference — ssh-reports-hub-fastAPI

> 각 섹션 우측에 대응 테스트 파일을 명시. 테스트와 엔드포인트는 1:1 매치.

## Auth

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `POST` | `/auth/telegram` | Telegram OAuth 로그인 → JWT 발급 | Telegram hash | `test_main.py` |
| `POST` | `/api/auth/telegram` | (alias) | Telegram hash | `test_main.py` |

## Health

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/health` | 서버 상태 확인 | None | `test_main.py`, `test_api_mocked.py` |

## Reports

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/reports` | 리포트 목록 조회 (pagination, q=검색어, company, board 필터) | None | `test_main.py`, `test_api_mocked.py` |

**Query Params**: `limit`, `offset`, `q`, `company`, `board`

## Keywords

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/keywords` | 내 키워드 목록 조회 | Bearer | `test_main.py` (indirect) |
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

ORDS 호환 응답 envelope: `{ items, hasMore, limit, offset, count, links }`

| Method | Endpoint | 설명 | 인증 | 테스트 |
|--------|----------|------|------|--------|
| `GET` | `/external/api/companies` | 증권사 목록 (리포트 존재 기준) | None | — |
| `GET` | `/external/api/boards` | 특정 증권사 게시판 목록 (`?company=`) | None | — |
| `GET` | `/external/api/industry` | 산업별 리포트 (main_ch_send_yn=Y) | None | `test_ords_external_api_parity.py` |
| `GET` | `/external/api/search` | 통합 검색 | None | `test_ords_external_api_parity.py` |

**Industry/Search params**: ORDS Compat 과 동일.

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

| 테스트 파일 | 커버리지 |
|-------------|----------|
| `test_main.py` | `/health`, `/reports`, `/external/api/...`, `/auth/telegram` |
| `test_api_mocked.py` | `/health`, `/reports`, auth 순수 로직 |
| `test_consensus_revision.py` | `/consensus/revision/1d`, `/consensus/revision/1d/summary` |
| `test_admin_metrics.py` | `/admin/metrics` |
