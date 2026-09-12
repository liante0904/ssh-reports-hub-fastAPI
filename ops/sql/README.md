# 운영 SQL

이 디렉터리는 `tbl_sec_reports` 복구·호환성 조정용 수동 운영 SQL을 보관한다.

- `restore.sql`: 레거시 `key` 컬럼·트리거 의존성을 제거하는 단계
- `restore_complete.sql`: 위 변경을 되돌리고 레거시 호환 구성을 복구하는 단계
- `20260913_report_source_key_and_index_cleanup.sql`: 기존 live view의 컬럼을 유지한 채
  `report_source_key` alias를 추가하고, `tbl_sec_reports.report_unique_key`의 중복
  standalone 인덱스 2개를 `DROP INDEX CONCURRENTLY`로 정리한 실행 기록

`report_source_key`는 물리 컬럼이 아니라 `report_unique_key`의 read-only view alias다.
의미는 수집 원천 식별키 및 중복 삽입 판별용 기준키다. `idx_report_unique_uid`만
UNIQUE 인덱스로 유지한다.

일반 배포 변경은 `migrations/`에 기록한다. 이 파일들은 자동 migration이 아니므로 운영 DB에 적용하기 전에 현재 스키마와 백업을 확인한다.
