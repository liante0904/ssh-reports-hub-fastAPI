# Backend Working Guide

This repository owns the FastAPI report API and its read/query contracts.
It does not own collection scheduling or broker HTML/PDF parsing; route those
tasks to `../scrapers/ssh-reports-scraper`.

## Read order

1. `README.md`
2. the affected router/service under `app/`
3. matching tests under `tests/`

## Verification

```bash
git status --short --branch
DB_BACKEND=sqlite uv run pytest tests/ -v
```

Use canonical report identifiers and fields (`report_unique_key`, `report_date`,
`save_at`). Treat production PostgreSQL as read-only unless the user explicitly
authorizes a write or DDL change.
