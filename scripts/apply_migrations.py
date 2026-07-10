#!/usr/bin/env python3
"""Apply pending versioned SQL migrations to the reports database."""

from pathlib import Path
import sys

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import reports_engine


MIGRATIONS_DIR = ROOT / "migrations"


def apply_pending_migrations(engine=reports_engine) -> list[str]:
    if engine.dialect.name != "postgresql":
        return []

    applied = []
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        completed = {
            row[0]
            for row in conn.execute(text("SELECT version FROM app_schema_migrations"))
        }
        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_path.name
            if version in completed:
                continue
            conn.connection.driver_connection.cursor().execute(
                migration_path.read_text(encoding="utf-8")
            )
            conn.execute(
                text("INSERT INTO app_schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )
            applied.append(version)
    return applied


if __name__ == "__main__":
    for version in apply_pending_migrations():
        print(f"Applied migration: {version}")
