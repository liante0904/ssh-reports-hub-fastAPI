# Gemini Notes

Read `AGENTS.md` first. Keep `app/main.py` as the app assembly layer and place report API work in `app/routers/`.

The ORDS-compatible routes are intentional migration shims. Preserve their URL paths, query parameters, and `items` response shape until the frontend no longer depends on them.
