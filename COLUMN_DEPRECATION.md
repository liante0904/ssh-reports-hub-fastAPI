# Column Deprecation Checklist — tbl_sec_reports

> 원본: `docs/DB_MIGRATION_STATUS.md`  
> 대상: backend / frontend / scraper 모든 팀

---

## 드랍 예정 컬럼 (5개)

| # | 옛 컬럼 | → 새 컬럼 | 코드 클린업 | DB 드랍 |
|---|---|---|---|---|
| 1 | `save_time` (VARCHAR) | `save_at` (TIMESTAMPTZ) | ✅ 7/3 완료 | ⏳ 대기 |
| 2 | `reg_dt` (VARCHAR) | `report_date` (DATE) | ✅ 7/3 완료 | ⏳ 대기 |
| 3 | `main_ch_send_yn` | `telegram_sent` (BOOLEAN) | ✅ 완료 | ⏳ 대기 |
| 4 | `key` (VARCHAR) | `report_unique_key` (UNIQUE) | ✅ 7/1 완료 | ⏳ 대기 |
| 5 | `article_url` | — (제거) | ✅ 6/15 완료 | ⏳ 대기 |

---

## 팀별 완료 조건

### Backend (FastAPI)
- [x] `models.py`에서 deprecated 컬럼 제거 또는 deprecation 주석 표기
- [x] 모든 `ORDER BY` / `WHERE` 절에서 `reg_dt` → `report_date` 전환
- [x] `save_time` fallback 코드 전면 제거
- [ ] `main.py` 뷰 `v_reports_api`, `v_llm_reports`에서 COALESCE 구문 정상 동작 확인 (운영 배포 후)

### Scraper (29 modules)
- [ ] `save_time` → `save_at` 으로 INSERT 컬럼 변경 (모든 모듈)
- [ ] `reg_dt` → `report_date` 로 INSERT 컬럼 변경 (모든 모듈)
- [ ] `key` → `report_unique_key` 로 INSERT 컬럼 변경 (완료되지 않았다면)

### Frontend (React)
- [ ] API 응답에서 `save_time` 필드 사용 중인지 확인 → `scraped_at` 사용
- [ ] API 응답에서 `reg_dt` 필드 정상 표시 확인 (뷰에서 하위호환 유지 중)

---

## 드랍 SQL (사용자 승인 후 실행)

```sql
ALTER TABLE tbl_sec_reports DROP COLUMN save_time;
ALTER TABLE tbl_sec_reports DROP COLUMN reg_dt;
ALTER TABLE tbl_sec_reports DROP COLUMN main_ch_send_yn;
ALTER TABLE tbl_sec_reports DROP COLUMN key;
ALTER TABLE tbl_sec_reports DROP COLUMN article_url;
```

---

## 컬럼 매핑 빠른 참조

| 용도 | 옛 컬럼 | 새 컬럼 | 타입 | 비고 |
|---|---|---|---|---|
| 저장 시각 | `save_time` | `save_at` | TIMESTAMPTZ | 뷰에서 `scraped_at`으로 노출 |
| 발행일 | `reg_dt` | `report_date` | DATE | 뷰에서 `reg_dt`는 COALESCE로 하위호환 |
| 발송 여부 | `main_ch_send_yn` | `telegram_sent` | BOOLEAN | |
| 리포트 식별자 | `key` | `report_unique_key` | TEXT UNIQUE | |
| 원문 URL | `article_url` | — | — | `download_url`/`pdf_url`로 대체 |
