from pathlib import Path
from types import SimpleNamespace

import app.main as main_module
import scripts.apply_migrations as migration_module


ROOT = Path(__file__).resolve().parents[1]


class ReadOnlyEngine:
    dialect = SimpleNamespace(name="postgresql")

    def begin(self):
        raise AssertionError("startup view validation must not open a DDL transaction")


class ViewInspector:
    def get_view_names(self):
        return ["v_reports", "v_reports_api"]


def test_repeated_startup_view_validation_is_read_only(monkeypatch):
    engine = ReadOnlyEngine()
    monkeypatch.setattr(main_module, "inspect", lambda candidate: ViewInspector())

    main_module._validate_required_views(engine)
    main_module._validate_required_views(engine)


def test_view_column_changes_live_in_versioned_drop_create_migration():
    startup_source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    migration_source = (
        ROOT / "migrations/20260710_01_recreate_report_views.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE OR REPLACE VIEW" not in startup_source
    assert "DROP VIEW IF EXISTS v_reports_api" in migration_source
    assert "DROP VIEW IF EXISTS v_reports" in migration_source
    assert "CREATE VIEW v_reports_api" in migration_source
    assert "CREATE OR REPLACE VIEW" not in migration_source


class MigrationCursor:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, sql):
        self.engine.migration_executions.append(sql)


class MigrationConnection:
    def __init__(self, engine):
        self.engine = engine
        self.connection = SimpleNamespace(
            driver_connection=SimpleNamespace(cursor=lambda: MigrationCursor(engine))
        )

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SELECT version"):
            return [(version,) for version in self.engine.completed]
        if sql.startswith("INSERT INTO app_schema_migrations"):
            self.engine.completed.add(params["version"])
        return []


class MigrationEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.completed = set()
        self.migration_executions = []

    def begin(self):
        return MigrationTransaction(self)


class MigrationTransaction:
    def __init__(self, engine):
        self.connection = MigrationConnection(engine)

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return None


def test_migration_runner_applies_each_version_once(tmp_path, monkeypatch):
    migration = tmp_path / "001.sql"
    migration.write_text("DROP VIEW old_view;", encoding="utf-8")
    monkeypatch.setattr(migration_module, "MIGRATIONS_DIR", tmp_path)
    engine = MigrationEngine()

    assert migration_module.apply_pending_migrations(engine) == ["001.sql"]
    assert migration_module.apply_pending_migrations(engine) == []
    assert engine.migration_executions == ["DROP VIEW old_view;"]
