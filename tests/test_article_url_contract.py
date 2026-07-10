from pathlib import Path

from app.models import SecReport
from app.routers.external_api import _view_row_to_api_item


ROOT = Path(__file__).resolve().parents[1]


def test_sec_report_does_not_map_dropped_article_url_column():
    assert "article_url" not in SecReport.__table__.columns
    assert SecReport().source_url is None


def test_api_item_keeps_nullable_source_url_compatibility():
    assert _view_row_to_api_item({})["source_url"] is None


def test_runtime_report_queries_do_not_reference_dropped_article_url_column():
    runtime_files = (
        ROOT / "app/main.py",
        ROOT / "app/routers/favorites.py",
        ROOT / "app/routers/reports.py",
    )

    for path in runtime_files:
        source = path.read_text(encoding="utf-8")
        assert "r.article_url" not in source, path
        assert "article_url         AS source_url" not in source, path
