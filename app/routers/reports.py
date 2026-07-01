from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session, joinedload
from ..dependencies import get_user_from_token

from ..database import get_reports_db
from ..models import SecReport
from ..schemas import SecReportResponse, ReportNotificationResponse, ReportSentHistoryResponse

router = APIRouter(prefix="/external/api", tags=["reports"])


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
    clauses, params = [], []
    if q:
        clauses.append("r.article_title ILIKE %s"); params.append(f"%{q}%")
    if writer:
        clauses.append("r.writer ILIKE %s"); params.append(f"%{writer}%")
    if company is not None:
        clauses.append("r.firm_id = %s"); params.append(company)
    if board is not None:
        clauses.append("r.board_id = %s"); params.append(board)
    if has_summary:
        clauses.append("r.gemini_summary IS NOT NULL AND r.gemini_summary NOT IN ('',' ')")
    if tag:
        clauses.append("r.tags ILIKE %s"); params.append(f'%"{tag}"%')
    if sector:
        clauses.append("r.sector ILIKE %s"); params.append(f"%{sector}%")
    if stock:
        clauses.append("r.stock_names ILIKE %s"); params.append(f'%"{stock}"%')

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM v_reports_api r {where} ORDER BY r.reg_dt DESC, r.report_id DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    from ..routers.external_api import _view_row_to_api_item
    conn = db.get_bind().raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    finally:
        conn.close()
    return [_view_row_to_api_item(r) for r in rows]


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


@router.get("/reports/notifications", response_model=list[ReportNotificationResponse], summary="AI 요약 완료 알림 목록 조회")
async def get_summary_notifications(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_reports_db),
):
    """
    tbl_sec_reports_notifications 기반 AI 요약 완료 알림.
    필요한 모든 종류의 인앱 알림을 이 테이블에 push 하면 종버튼에 표시됩니다.
    """
    from ..models import ReportNotification, SecReport
    try:
        rows = (
            db.query(
                ReportNotification,
                SecReport.pdf_url,
                SecReport.telegram_url,
                SecReport.article_url,
                SecReport.firm_id,
            )
            .outerjoin(SecReport, ReportNotification.report_id == SecReport.report_id)
            .order_by(ReportNotification.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            ReportNotificationResponse(
                id=n.id,
                report_id=n.report_id,
                article_title=n.article_title,
                firm_nm=n.firm_nm,
                sec_firm_order=firm_id,
                summary_model=n.summary_model,
                message=n.message,
                pdf_url=pdf_url,
                telegram_url=telegram_url,
                article_url=article_url,
                created_at=n.created_at,
            )
            for n, pdf_url, telegram_url, article_url, firm_id in rows
        ]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch notifications: {str(e)}")
        return []


@router.get("/reports/send-history", response_model=list[ReportSentHistoryResponse], summary="리포트 알림 내역 조회 (텔레그램 발송 + AI 요약 완료)")
async def get_send_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_reports_db),
):
    """
    tbl_report_send_history 기반 통합 알림 내역.
    텔레그램 키워드 알림 발송 내역과 AI 요약 완료 알림을 최근순으로 조회합니다.
    """
    from ..models import ReportSentHistory
    try:
        rows = (
            db.query(
                ReportSentHistory.id,
                ReportSentHistory.report_id,
                ReportSentHistory.user_id,
                ReportSentHistory.keyword,
                ReportSentHistory.sent_at,
                SecReport.article_title,
                SecReport.firm_nm,
            )
            .outerjoin(SecReport, ReportSentHistory.report_id == SecReport.report_id)
            .order_by(ReportSentHistory.sent_at.desc())
            .limit(limit)
            .all()
        )
        return [
            ReportSentHistoryResponse(
                id=row.id,
                report_id=row.report_id,
                user_id=row.user_id,
                keyword=row.keyword,
                sent_at=row.sent_at,
                article_title=row.article_title,
                firm_nm=row.firm_nm,
            )
            for row in rows
        ]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to fetch send history: {str(e)}")
        return []


from .admin import require_admin, User
from fastapi import Depends
from pydantic import BaseModel, Field
from ..exceptions import ServiceUnavailableException

class LLMSettingUpdate(BaseModel):
    visibility: str = Field(..., pattern="^(admin|telegram)$", description="노출 범위 ('admin' 또는 'telegram')")

@router.get("/admin/llm-setting", summary="LLM 요약 노출 설정 조회 (Admin)")
async def get_llm_setting_admin(
    current_user: User = Depends(require_admin),
):
    visibility = load_llm_visibility()
    return {"visibility": visibility}

@router.post("/admin/llm-setting", summary="LLM 요약 노출 설정 변경 (Admin)")
async def update_llm_setting_admin(
    payload: LLMSettingUpdate,
    current_user: User = Depends(require_admin),
):
    import json
    try:
        data = {"visibility": payload.visibility}
        with open(SETTING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise ServiceUnavailableException(f"Failed to save setting: {e}")
    return {"status": "success", "visibility": payload.visibility}


# ── Notification Read Status (localStorage → DB) ──

from ..models import NotificationRead, User


@router.get("/reports/notifications/read-status", summary="알림 읽음 상태 조회")
async def get_notification_reads(
    user: User = Depends(get_user_from_token),
    db: Session = Depends(get_reports_db),
):
    rows = db.query(NotificationRead.notification_key).filter(
        NotificationRead.user_id == user.id
    ).all()
    return [r[0] for r in rows]


@router.post("/reports/notifications/mark-read", summary="알림 읽음 처리")
async def mark_notification_read(
    notification_key: str = Body(..., embed=True),
    user: User = Depends(get_user_from_token),
    db: Session = Depends(get_reports_db),
):
    exists = db.query(NotificationRead).filter(
        NotificationRead.user_id == user.id,
        NotificationRead.notification_key == notification_key,
    ).first()
    if not exists:
        db.add(NotificationRead(user_id=user.id, notification_key=notification_key))
        db.commit()
    return {"status": "ok"}


@router.post("/reports/notifications/mark-all-read", summary="전체 읽음 처리")
async def mark_all_notifications_read(
    keys: list = Body(..., embed=True),
    user: User = Depends(get_user_from_token),
    db: Session = Depends(get_reports_db),
):
    str_keys = [str(k) for k in keys]
    for key in str_keys:
        exists = db.query(NotificationRead).filter(
            NotificationRead.user_id == user.id,
            NotificationRead.notification_key == key,
        ).first()
        if not exists:
            db.add(NotificationRead(user_id=user.id, notification_key=key))
    db.commit()
    return {"status": "ok", "count": len(str_keys)}
