# 운영 SQL

이 디렉터리는 `tbl_sec_reports` 복구·호환성 조정용 수동 운영 SQL을 보관한다.

- `restore.sql`: 레거시 `key` 컬럼·트리거 의존성을 제거하는 단계
- `restore_complete.sql`: 위 변경을 되돌리고 레거시 호환 구성을 복구하는 단계

일반 배포 변경은 `migrations/`에 기록한다. 이 파일들은 자동 migration이 아니므로 운영 DB에 적용하기 전에 현재 스키마와 백업을 확인한다.
