# Changelog

## 2026-05-26

### Refactored

- 테이블명 체계 정리: `tbm_` → `tbl_`로 변경 (favorites, telegram_users, alert_keywords 등).
- 비핵심 라우터 이관: `consensus`, `sentiment`, `cnn_sentiment`, `disclosure`, `screening`, `notes` 라우터를 `internal.private-hub` 프로젝트로 이관하여 본 프로젝트를 리포트 중심으로 슬림화했습니다.
- `app/main.py`, `app/models.py`, `app/schemas.py`에서 불필요한 코드 및 스키마 제거.

### Fixed

- Favorites API 테스트 7건을 추가하고 안정성을 확인했습니다.

## 2026-05-24

### Added

- **Enricher 기능 추가**: 앱 시작 시 `tags`, `stock_names`, `sector` 컬럼 자동 생성 (Lifespan Migration).
- **통합 검색 필터 고도화**: `/external/api/search` 및 `/reports`에 `tag`, `sector`, `stock` 필터 추가.
- **시장 전망 필터 추가**: `/external/api/search`에 `outlook` (Boolean) 및 `outlook_year` 필터 추가. 정규표현식을 통해 개별 종목 분석은 제외하고 순수 시장 전망 리포트만 추출합니다.
- **산업분석 필터 강화**: PostgreSQL 정규표현식을 활용하여 산업분석 게시판 내 개별 종목 리포트(종목코드 포함 제목)를 필터링하는 기능을 추가했습니다.

### Fixed

- JSONB 컬럼이 이미 리스트로 역직렬화된 경우 발생하는 `TypeError` 수정.
- DB 컬럼이 없는 상태에서도 쿼리가 안전하게 동작하도록 `deferred()` 및 `try/except` 적용.
- 권한 오류로 인한 시작 시 크래시 방지를 위해 `seed_mock` 호출부를 `try/except`로 래핑.

## 2026-05-14

### Changed

- **ORDS 호환 라우트 제거**: 프론트엔드의 `/external/api` 이관이 완료됨에 따라 `/ords/*` 경로를 제거했습니다.
- **API_REFERENCE.md 도입**: 테스트 파일과 1:1 매칭되는 API 문서를 도입하여 문서와 구현의 정합성을 높였습니다.

## 2026-05-05

### Added

- **Admin 기능 강화**: 서버 메트릭(CPU, RAM, Disk) 조회 API(`/admin/metrics`) 및 실시간 로그 브라우저(`/admin/logs`, `/admin/logs/view`) 추가.
- **Screening API**: 일별 엑셀 파일 조회 및 데이터소스 추상이 적용된 스크리닝 라우터 추가.
- **DeepSeek Summary**: PDF 텍스트 추출(PyMuPDF) 및 DeepSeek 모델 기반 요약 관리 기능 추가.

## 2026-05-02

### Added

- 백엔드 최소 검증 진입점 `make verify`를 추가했습니다.
- 백엔드 문서 인덱스 `docs/README.md`를 추가했습니다.
- CI/CD 및 릴리즈 흐름 문서 `docs/CI_CD.md`를 추가했습니다.
- DART 공시 분석 보드 백엔드 기능을 추가했습니다. (`/pub/api/disclosure`)
- CNN Fear & Greed 지수 직접 수집 및 일일 히스토리 관리 기능을 추가했습니다. (`/pub/api/cnn-sentiment`)
- 종목별 컨센서스(Earnings Revision) 및 목표주가 추이 인사이트 엔드포인트를 추가했습니다. (`/pub/api/consensus`)
- 투자 메모(`investment_notes`)에 부모-자식 계층 구조(Hierarchy) 기능을 추가했습니다.
- 투자 메모 편집 시 리사이징 가능한 필드 구조를 적용했습니다.
- 센티멘트 분석 API 및 테스트용 Mock 데이터를 추가했습니다.
- FnGuide 리포트 요약 조회용 전용 테이블 `tbl_fnguide_report_summaries`를 추가했습니다.
- `/pub/api/fnguide/report-summaries` 조회 라우터를 추가했습니다.

### Changed

- README에 빠른 시작과 문서 진입점을 추가했습니다.
- 현재 운영 방식에 맞춰 배포 전 검증 우선순위를 문서화했습니다.
- `auth/telegram` 테스트의 장시간 대기를 없애기 위해 라우트 통합 테스트를 함수 검증으로 정리했습니다.
- CNN 수집은 외부 HTTP 라이브러리 대신 표준 라이브러리 기반으로 단순화했습니다.
- `make verify`는 `/tmp` 캐시를 사용하도록 조정했습니다.
- 센티멘트 데이터의 타임스탬프를 KST 및 UTC 기준으로 정규화하여 일관성을 확보했습니다.
- 텔레그램 인증 로직을 강화하고, 특정 환경에서 제어된 인증 우회 기능을 추가했습니다.
- FnGuide 요약 데이터는 `tbl_sec_reports`와 분리된 별도 엔터티로 관리하도록 정리했습니다.

### Fixed

- GitHub Actions 배포 워크플로우(`deploy.yml`)의 컨테이너 경로 및 검사 로직 오류를 수정했습니다.
- 투자 메모 라우팅 및 인증 처리의 보안 취약점을 보완했습니다.

### Verification

- FastAPI 문법 검사 및 로컬 빌드 확인
- 신규 API 엔드포인트(`disclosure`, `cnn-sentiment`, `consensus`, `sentiment`) 유닛 테스트 작성 및 통과
- FnGuide 워커 동작 및 데이터 정합성 확인

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
