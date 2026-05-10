"""
즐겨찾기 API (서버사이드)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..database import get_keywords_db, get_reports_db
from ..dependencies import get_user_from_token
from ..models import ReportFavorite, SecReport, User

logger = logging.getLogger("app.favorites")
router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("")
@router.get("/")
async def get_favorites(
    current_user: User = Depends(get_user_from_token),
    keywords_db: Session = Depends(get_keywords_db),
    reports_db: Session = Depends(get_reports_db),
):
    """내 즐겨찾기 목록을 조회합니다. tbl_sec_reports와 JOIN하여 유효한 리포트만 반환합니다."""
    # 1. 사용자의 즐겨찾기 report_id 목록 조회 (즐겨찾기 추가 시간 내림차순)
    favs = (
        keywords_db.query(ReportFavorite)
        .filter(ReportFavorite.user_id == current_user.id)
        .order_by(ReportFavorite.created_at.desc())
        .all()
    )

    if not favs:
        return {"items": [], "count": 0, "total_favorites": 0}

    # 2. tbl_sec_reports에서 실제 존재하는 리포트만 조회
    fav_report_ids = [f.report_id for f in favs]
    existing_reports = (
        reports_db.query(SecReport)
        .options(joinedload(SecReport.pdf_archive))
        .filter(SecReport.report_id.in_(fav_report_ids))
        .all()
    )

    # 3. 리포트 ID → 리포트 객체 매핑
    report_map = {r.report_id: r for r in existing_reports}

    # 4. 즐겨찾기 추가 시간 순서를 유지하면서 리포트 데이터 구성
    items = []
    for fav in favs:
        report = report_map.get(fav.report_id)
        if report is None:
            continue  # tbl_sec_reports에 존재하지 않는 report_id는 제외

        archive = report.pdf_archive
        pdf_archive_data = None
        if archive:
            pdf_archive_data = {
                "file_path": archive.file_path,
                "file_size": archive.file_size,
                "page_count": archive.page_count,
                "archive_status": archive.archive_status,
                "file_name": archive.file_name,
                "has_text": archive.has_text,
                "is_encrypted": archive.is_encrypted,
                "storage_backend": archive.storage_backend,
                "storage_key": archive.storage_key,
                "author": archive.author,
                "created_at": archive.created_at.isoformat() if archive.created_at else None,
                "updated_at": archive.updated_at.isoformat() if archive.updated_at else None,
                "last_accessed_at": archive.last_accessed_at.isoformat() if archive.last_accessed_at else None,
            }

        items.append({
            "report_id": report.report_id,
            "sec_firm_order": report.sec_firm_order,
            "article_board_order": report.article_board_order,
            "firm_nm": report.firm_nm,
            "article_title": report.article_title,
            "article_url": report.article_url,
            "main_ch_send_yn": report.main_ch_send_yn,
            "download_url": report.download_url,
            "pdf_url": report.pdf_url,
            "telegram_url": report.telegram_url,
            "writer": report.writer,
            "reg_dt": report.reg_dt,
            "save_time": report.save_time,
            "key": report.key,
            "mkt_tp": report.mkt_tp,
            "gemini_summary": report.gemini_summary,
            "summary_time": report.summary_time,
            "summary_model": report.summary_model,
            "favorite_created_at": fav.created_at.isoformat() if fav.created_at else None,
            "pdf_archive": pdf_archive_data,
        })

    return {
        "items": items,
        "count": len(items),
        "total_favorites": len(favs),
    }


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
