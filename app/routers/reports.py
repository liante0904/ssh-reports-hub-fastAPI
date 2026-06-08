from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_reports_db
from ..models import SecReport
from ..schemas import SecReportResponse, ReportNotificationResponse

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=list[SecReportResponse])
@router.get("/reports/", response_model=list[SecReportResponse])
async def get_reports(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    has_summary: Annotated[Optional[bool], Query()] = None,
    tag: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    sector: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    stock: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(SecReport)
    if q:
        query = query.filter(SecReport.article_title.ilike(f"%{q}%"))
    if writer:
        query = query.filter(SecReport.writer.ilike(f"%{writer}%"))
    if company is not None:
        query = query.filter(SecReport.sec_firm_order == company)
    if board is not None:
        query = query.filter(SecReport.article_board_order == board)
    if has_summary:
        query = query.filter(
            SecReport.gemini_summary.isnot(None),
            SecReport.gemini_summary != "",
            SecReport.gemini_summary != " ",
        )
    if tag:
        query = query.filter(SecReport.tags.ilike(f'%"{tag}"%'))
    if sector:
        query = query.filter(SecReport.sector.ilike(f"%{sector}%"))
    if stock:
        query = query.filter(SecReport.stock_names.ilike(f'%"{stock}"%'))
    return query.options(
        joinedload(SecReport.pdf_archive),
        joinedload(SecReport.fnguide_summary)
    ).order_by(
        SecReport.reg_dt.desc(), SecReport.report_id.desc()
    ).offset(offset).limit(limit).all()


import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SETTING_FILE = BASE_DIR / "llm_setting.json"

def load_llm_visibility() -> str:
    """
    LLM 요약 노출 설정 로드 ('admin' 또는 'telegram')
    기존 주석 보존: 파일이 존재하지 않는 경우 기본값 'admin' 반환
    """
    try:
        if SETTING_FILE.exists():
            with open(SETTING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("visibility", "admin")
    except Exception:
        pass
    return "admin"

@router.get("/reports/llm-setting", summary="LLM 요약 노출 범위 설정 조회 (Public)")
async def get_llm_setting():
    """
    프론트엔드 및 일반 사용자에게 LLM 요약 노출 설정을 제공합니다.
    """
    visibility = load_llm_visibility()
    return {"visibility": visibility}


@router.get("/reports/notifications", response_model=list[ReportNotificationResponse], summary="최신 AI 요약 완료 알림 목록 조회")
async def get_summary_notifications(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_reports_db),
):
    """
    최신 AI 요약 완료 알림 목록을 최근순으로 조회합니다.
    """
    from ..models import ReportNotification
    try:
        notifications = (
            db.query(ReportNotification)
            .order_by(ReportNotification.created_at.desc())
            .limit(limit)
            .all()
        )
        return notifications
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch notifications: {str(e)}")
        return []


