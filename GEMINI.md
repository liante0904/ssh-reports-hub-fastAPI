# Gemini Notes

Read `AGENTS.md` first. Keep `app/main.py` as the app assembly layer and place report API work in `app/routers/`.

The ORDS-compatible routes were removed on 2026-05-14 as the frontend has fully migrated to `/external/api`.
Preserve the `/external/api` response shape (ORDS-compatible envelope: `items`, `hasMore`, etc.) to maintain frontend compatibility.
