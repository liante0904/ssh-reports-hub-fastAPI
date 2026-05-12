# Agent Notes

> **[IMPORTANT] 인프라 및 속도 가이드**
> - 이 환경은 **초고속 내부 전용망**입니다. 모든 네트워크 응답은 5초 이내여야 합니다.
> - 작업 시 10초 이상 지체하지 마십시오. 서버 이슈 시 즉시 프로세스를 죽이고 다시 띄우는 것이 가장 빠릅니다.

This is a small FastAPI service for Telegram-authenticated research report lookup and keyword alerts.

## Current Structure

- `app/main.py` should stay focused on app assembly, middleware, auth, and keyword endpoints.
- `app/routers/reports.py` owns the newer `/reports` API.
- `app/routers/ords_compat.py` owns temporary ORDS-compatible endpoints used to keep the existing frontend working during the Oracle ATP to PostgreSQL migration.
- `app/models.py` maps report tables. `MAIN_TABLE_NAME` changes with `DB_BACKEND`.
- `app/database.py` owns separate report and keyword DB sessions.

## Migration Rule

Do not remove or rename the ORDS-compatible routes until the frontend has been migrated away from the old Oracle ORDS contract:

- `/ords/admin/data_main_daily_send/industry`
- `/ords/admin/data_main_daily_send/search/`

Those routes intentionally return ORDS-style collection JSON with `items`, `hasMore`, `limit`, `offset`, `count`, and `links`.

## Testing

Run:

```bash
uv run pytest
```

When adding report API behavior, add focused tests under `tests/`. Prefer dependency overrides for `get_reports_db` or `get_keywords_db` instead of touching real services.

## Safety

- Do not commit `.env`, local DB files, logs, or virtualenv contents.
- Avoid broad rewrites in `main.py`; add routers/modules instead.
- Preserve backwards compatibility first, then refactor internals behind the stable route contract.
