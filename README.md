# SSH Reports Hub FastAPI Backend

증권사 리포트 수집 및 배포 플랫폼의 고성능 API 서비스 백엔드 엔진입니다.

## 🚀 주요 기능 및 변경사항 (2026-07-01 업데이트)

### 1. 성능 최적화: ORM → Raw SQL 전면 전환
- API 응답 속도 및 동시 처리량 향상을 위해 기존 SQLAlchemy ORM 방식의 목록 조회 및 다중 JOIN 쿼리를 **psycopg2 기반의 동적 Raw SQL 실행 방식**으로 전면 마이그레이션 완료하였습니다.
- PostgreSQL의 `%s` 바인딩을 활용하여 SQL Injection을 방지하였으며, 로컬 인메모리 SQLite 환경(테스트 샌드박스)의 `?` 바인딩과도 완벽한 호환을 제공합니다.

### 2. API 구조 변경
- **Reports Router Prefix**: 기존 `/reports` 였던 prefix가 `/external/api` 로 통일 변경되어 통합 및 관리가 용이해졌습니다.
- **최근 리포트 전용 엔드포인트 `/recent`**: 무겁고 복합 필터가 들어가는 통합 `/search` API 대신, 성능 최적화된 `/recent` 엔드포인트를 신설하여 프론트엔드 홈 대시보드 로딩 속도를 향상시켰습니다.
- **`key` 필드 Deprecation**: 기존 `key` 컬럼 데이터의 쓰기 및 가공이 전면 중단됨에 따라, Pydantic Schema 수준에서 `Field(deprecated=True)` 처리하고 canonical 식별자인 `report_unique_key` 로 완전히 이행하였습니다.

## 🛠️ 개발 및 테스트 실행

### 로컬 테스트 실행 (SQLite 샌드박스)
운영 데이터베이스를 안전하게 보호하기 위해 로컬 테스트 기동 시에는 반드시 SQLite 인메모리 드라이버를 백엔드로 사용합니다.

```bash
DB_BACKEND=sqlite uv run pytest tests/ -v
```

### 환경 설정
로컬 개발 환경에서는 `secrets.json`에 `POSTGRES_USER=oci2_readonly`를 설정하여 운영 DB를 조회(Read-only) 형태로만 안전하게 연동해 개발합니다.
