import pytest

from app.routers import external_api
from app.routers.external_api import _archive_remote_path, _view_row_to_api_item


def test_archive_remote_path_uses_configured_gdrive_root(monkeypatch):
    monkeypatch.setenv("PDF_ARCHIVE_RCLONE_REMOTE", "gdrive:archive/pdf")

    assert _archive_remote_path("2026-08/DB증권/report_1.pdf") == (
        "gdrive:archive/pdf/2026-08/DB증권/report_1.pdf"
    )


@pytest.mark.parametrize("storage_key", ["", "/etc/passwd", "2026-08/../../secret.pdf"])
def test_archive_remote_path_rejects_unsafe_keys(storage_key):
    with pytest.raises(ValueError):
        _archive_remote_path(storage_key)


@pytest.mark.anyio
async def test_archive_download_returns_pdf_without_exposing_storage_key(tmp_path, monkeypatch):
    local_pdf = tmp_path / "archived.pdf"
    local_pdf.write_bytes(b"%PDF-1.7\\n")
    archive = {
        "archive_status": "ARCHIVED",
        "storage_key": "2026-08/DB증권/report_1.pdf",
        "storage_backend": "googledrive",
        "file_name": "DB report.pdf",
    }
    db = object()
    monkeypatch.setattr(external_api, "_execute_raw_psycopg2_query", lambda *args: [archive])
    monkeypatch.setattr(external_api, "_download_archive_file", lambda *args: local_pdf)

    response = await external_api.download_archived_pdf(1, db)

    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert "DB%20report.pdf" in response.headers["content-disposition"]
    assert "storage_key" not in response.headers["content-disposition"]


def test_normalized_archive_payload_survives_collection_response_second_pass():
    raw_row = {
        "report_id": 1,
        "pdf_report_id": 1,
        "pdf_archive_status": "ARCHIVED",
        "pdf_storage_key": "2026-08/DB증권/report_1.pdf",
        "pdf_storage_backend": "googledrive",
    }

    normalized = _view_row_to_api_item(raw_row)

    assert normalized["pdf_archive"]["archive_status"] == "ARCHIVED"
    assert _view_row_to_api_item(normalized)["pdf_archive"]["storage_key"] == "2026-08/DB증권/report_1.pdf"
