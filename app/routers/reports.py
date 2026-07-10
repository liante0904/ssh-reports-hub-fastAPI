from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session, joinedload
from ..dependencies import get_user_from_token

from ..database import get_reports_db
from ..models import SecReport, User
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
    is_pg = db.get_bind().dialect.name == "postgresql"
    _from = "v_reports_api" if is_pg else "tbl_sec_reports"
    placeholder = "%s" if is_pg else "?"
    like_op = "ILIKE" if is_pg else "LIKE"
    if q:
        clauses.append(f"r.article_title {like_op} {placeholder}"); params.append(f"%{q}%")
    if writer:
        clauses.append(f"r.writer {like_op} {placeholder}"); params.append(f"%{writer}%")
    if company is not None:
        clauses.append(f"r.firm_id = {placeholder}"); params.append(company)
    if board is not None:
        clauses.append(f"r.board_id = {placeholder}"); params.append(board)
    if has_summary:
        clauses.append("r.gemini_summary IS NOT NULL AND r.gemini_summary NOT IN ('',' ')")
    if tag:
        clauses.append(f"r.tags {like_op} {placeholder}"); params.append(f'%"{tag}"%')
    if sector:
        clauses.append(f"r.sector {like_op} {placeholder}"); params.append(f"%{sector}%")
    if stock:
        clauses.append(f"r.stock_names {like_op} {placeholder}"); params.append(f'%"{stock}"%')

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM {_from} r {where} ORDER BY r.report_date DESC, r.report_id DESC LIMIT {placeholder} OFFSET {placeholder}"
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
    user: User = Depends(get_user_from_token),
):
    """AI 요약 완료 알림. tbl_sec_reports_notifications + tbl_sec_reports JOIN. (로그인 필수)"""
    try:
        conn = db.get_bind().raw_connection()
        cur = conn.cursor()
        is_pg = db.get_bind().dialect.name == "postgresql"
        r_tbl = "tbl_sec_reports"
        n_tbl = "tbl_sec_reports_notifications"
        ph = "%s" if is_pg else "?"
        cur.execute(f"SELECT n.id, n.report_id, n.article_title, n.firm_nm, n.summary_model,"
                    f" n.message, n.created_at, r.pdf_url AS pdf_file_url, r.telegram_url, NULL AS source_url, r.firm_id"
                    f" FROM {n_tbl} n LEFT JOIN {r_tbl} r ON n.report_id = r.report_id"
                    f" ORDER BY n.created_at DESC LIMIT {ph}", [limit])
        rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        conn.close()
        return [ReportNotificationResponse(
            id=r["id"], report_id=r["report_id"], article_title=r["article_title"],
            firm_nm=r["firm_nm"], firm_id=r["firm_id"], summary_model=r["summary_model"],
            message=r["message"], pdf_file_url=r["pdf_file_url"], telegram_url=r["telegram_url"],
            source_url=r["source_url"], created_at=r["created_at"],
        ) for r in rows]
    except Exception:
        import logging
        logging.getLogger(__name__).error("Failed to fetch notifications", exc_info=True)
        return []


@router.get("/reports/send-history", response_model=list[ReportSentHistoryResponse], summary="리포트 알림 내역 조회 (텔레그램 발송 + AI 요약 완료)")
async def get_send_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(get_reports_db),
):
    """통합 알림 내역 (텔레그램 키워드 + AI 요약)."""
    try:
        conn = db.get_bind().raw_connection()
        cur = conn.cursor()
        is_pg = db.get_bind().dialect.name == "postgresql"
        ph = "%s" if is_pg else "?"
        ph = "%s" if is_pg else "?"
        cur.execute(f"SELECT h.id, h.report_id, h.user_id, h.keyword, h.sent_at,"
                    f" r.article_title, r.firm_nm"
                    f" FROM tbl_report_send_history h LEFT JOIN tbl_sec_reports r ON h.report_id = r.report_id"
                    f" ORDER BY h.sent_at DESC LIMIT {ph}", [limit])
        rows = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        conn.close()
        return [ReportSentHistoryResponse(**r) for r in rows]
    except Exception:
        import logging
        logging.getLogger(__name__).error("Failed to fetch send history", exc_info=True)
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
