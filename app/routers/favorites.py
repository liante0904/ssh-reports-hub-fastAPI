"""
즐겨찾기 API (서버사이드)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from ..database import get_keywords_db, get_reports_db
from ..dependencies import get_user_from_token
from ..models import ReportFavorite, User

logger = logging.getLogger("app.favorites")
router = APIRouter(prefix="/favorites", tags=["favorites"])


def _format_datetime_value(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).replace(" ", "T", 1)


@router.get("")
@router.get("/")
async def get_favorites(
    current_user: User = Depends(get_user_from_token),
    reports_db: Session = Depends(get_reports_db),
):
    """내 즐겨찾기 목록을 조회합니다. tbl_sec_reports와 JOIN하여 유효한 리포트만 반환합니다."""
    placeholder = "%s" if reports_db.get_bind().dialect.name == "postgresql" else "?"
    sql = f"""
        SELECT r.report_id, r.firm_id, r.board_id, r.firm_nm, r.article_title,
               NULL AS source_url, r.telegram_sent, r.pdf_url AS pdf_file_url, r.telegram_url,
               r.writer, r.report_date, r.save_at, r.report_unique_key, r.mkt_tp,
               r.gemini_summary, r.summary_time, r.summary_model,
               p.page_count AS pdf_page_count, p.file_name AS pdf_file_name,
               p.has_text AS pdf_has_text, p.is_encrypted AS pdf_is_encrypted,
               p.author AS pdf_author,
               r.save_at AS scraped_at,
               f.created_at AS favorite_created_at
        FROM tbl_sec_reports_favorites f
        JOIN tbl_sec_reports r ON f.report_id = r.report_id
        LEFT JOIN tbl_sec_reports_pdf_archive p ON r.report_id = p.report_id
        WHERE f.user_id = {placeholder}
        ORDER BY f.created_at DESC
    """
    conn = reports_db.get_bind().raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, [current_user.id])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    items = []
    for r in rows:
        items.append({
            "report_id": r["report_id"],
            "firm_id": r["firm_id"],
            "board_id": r["board_id"],
            "firm_nm": r["firm_nm"],
            "article_title": r["article_title"],
            "source_url": r["source_url"],
            "telegram_sent": r["telegram_sent"],
            "pdf_file_url": r["pdf_file_url"],
            "telegram_url": r["telegram_url"],
            "writer": r["writer"],
            "report_date": r["report_date"],
            "scraped_at": _format_datetime_value(r["scraped_at"]),
            "report_unique_key": r["report_unique_key"],
            "mkt_tp": r["mkt_tp"],
            "gemini_summary": r["gemini_summary"],
            "summary_time": r["summary_time"],
            "summary_model": r["summary_model"],
            "favorite_created_at": _format_datetime_value(r["favorite_created_at"]),
            "pdf_archive": {"page_count": r["pdf_page_count"], "file_name": r["pdf_file_name"], "has_text": r["pdf_has_text"], "is_encrypted": r["pdf_is_encrypted"], "author": r["pdf_author"]} if r["pdf_page_count"] is not None else None,
        })

    return {"items": items, "count": len(items), "total_favorites": len(rows)}


@router.post("/{report_id}")
async def add_favorite(
    report_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    """리포트를 즐겨찾기에 추가합니다."""
    exists = (
        db.query(ReportFavorite)
        .filter(
            ReportFavorite.user_id == current_user.id,
            ReportFavorite.report_id == report_id,
        )
        .first()
    )
    if exists:
        return {"status": "already_exists", "report_id": report_id}

    fav = ReportFavorite(user_id=current_user.id, report_id=report_id)
    db.add(fav)
    db.commit()
    return {"status": "added", "report_id": report_id}


@router.delete("/{report_id}")
async def remove_favorite(
    report_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    """즐겨찾기를 제거합니다."""
    deleted = (
        db.query(ReportFavorite)
        .filter(
            ReportFavorite.user_id == current_user.id,
            ReportFavorite.report_id == report_id,
        )
        .delete()
    )
    db.commit()
    if deleted == 0:
        return {"status": "not_found", "report_id": report_id}
    return {"status": "removed", "report_id": report_id}
