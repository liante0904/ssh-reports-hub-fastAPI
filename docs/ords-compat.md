# ORDS Compatibility Layer

## Why This Exists

The frontend was originally built against Oracle ORDS endpoints backed by `DATA_MAIN_DAILY_SEND`. During the Oracle ATP to PostgreSQL migration, changing the frontend and backend contract at the same time caused report lists, industry reports, company filters, and share lookups to break.

The short-term rule is: keep the old ORDS API contract stable in FastAPI, then clean up backend internals behind that contract.

## Routes

FastAPI currently serves these compatibility routes:

- `GET /ords/admin/data_main_daily_send/industry`
- `GET /ords/admin/data_main_daily_send/industry/`
- `GET /ords/admin/data_main_daily_send/search`
- `GET /ords/admin/data_main_daily_send/search/`

Implementation lives in `app/routers/ords_compat.py`.

As of 2026-04-21, production runs with `DB_BACKEND=postgres`, so these routes read from PostgreSQL `TB_SEC_REPORTS` through the shared `SecReport` model. The same route contract is intentionally preserved from the old Oracle ORDS frontend calls.

## Response Shape

The compatibility routes intentionally return ORDS-style collection JSON:

```json
{
  "items": [],
  "hasMore": false,
  "limit": 100,
  "offset": 0,
  "count": 0,
  "links": []
}
```

The item keys are lowercase to match the ORDS JSON shape, for example `report_id`, `sec_firm_order`, `article_board_order`, `firm_nm`, `article_title`, and `main_ch_send_yn`.

## Industry Filter

The industry route mirrors the legacy SQL predicate:

- fixed `(SEC_FIRM_ORDER, ARTICLE_BOARD_ORDER)` pairs
- `MAIN_CH_SEND_YN = 'Y'`
- optional `last_report_id`, mapped to `report_id < last_report_id`
- sorted by `report_id DESC`

The fixed board mapping is stored as `INDUSTRY_REPORT_BOARD_FILTERS`.

## Search Filter

The search route accepts legacy frontend parameters:

- `report_id`
- `writer`
- `title`
- `mkt_tp=global|domestic`
- `company`
- `limit`
- `offset`

Oracle `CONTAINS(...) > 0` is approximated with SQLAlchemy `ilike` for PostgreSQL compatibility. If relevance ranking becomes important, replace this with PostgreSQL full-text search behind the same API contract.

## Known Gaps

- `send_user` and `download_status_yn` are returned as `null` because the current SQLAlchemy model does not expose those columns.
- The compatibility `links` array is minimal. The frontend should use `items`/`hasMore`/pagination fields, not rely on all ORDS metadata links.
- The newer `/reports` endpoint still exists and should be evolved separately after the frontend migration.

## Removal Criteria

Do not remove this layer until:

1. Frontend calls have moved away from the ORDS paths.
2. Share links no longer depend on `search/?report_id=...`.
3. Industry/company/report list views are verified against the replacement API.
4. Tests covering the new frontend contract replace `tests/test_ords_compat.py`.
