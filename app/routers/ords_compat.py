from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import SecReport

router = APIRouter(prefix="/ords/admin/data_main_daily_send", tags=["ords-compat"])

INDUSTRY_REPORT_BOARD_FILTERS = (
    (0, (2,)),
    (1, (0,)),
    (3, (1,)),
    (5, (1,)),
    (6, (1,)),
    (10, (1,)),
    (12, (2,)),
    (14, (8, 9, 10, 11, 12, 13)),
    (18, (1,)),
    (20, (1,)),
    (22, (1,)),
    (23, (1,)),
    (24, (1,)),
    (25, (2,)),
)


def _report_to_ords_item(report: SecReport) -> dict:
    return {
        "report_id": report.report_id,
        "sec_firm_order": report.SEC_FIRM_ORDER,
        "article_board_order": report.ARTICLE_BOARD_ORDER,
        "firm_nm": report.FIRM_NM,
        "send_user": None,
        "main_ch_send_yn": report.MAIN_CH_SEND_YN,
        "download_status_yn": None,
        "save_time": report.SAVE_TIME,
        "reg_dt": report.REG_DT,
        "writer": report.WRITER,
        "key": report.KEY,
        "mkt_tp": report.MKT_TP,
        "article_title": report.ARTICLE_TITLE,
        "telegram_url": report.TELEGRAM_URL,
        "article_url": report.ARTICLE_URL,
        "download_url": report.DOWNLOAD_URL,
        "pdf_url": report.PDF_URL,
        "gemini_summary": report.GEMINI_SUMMARY,
        "summary_time": report.SUMMARY_TIME,
        "summary_model": report.SUMMARY_MODEL,
    }


def _ords_collection_response(
    request: Request,
    reports: list[SecReport],
    limit: int,
    offset: int,
    has_more: bool,
) -> dict:
    return {
        "items": [_report_to_ords_item(report) for report in reports],
        "hasMore": has_more,
        "limit": limit,
        "offset": offset,
        "count": len(reports),
        "links": [
            {"rel": "self", "href": str(request.url)},
            {"rel": "first", "href": str(request.url.include_query_params(offset=0))},
        ],
    }


def _paginate_ords_query(query, limit: int, offset: int) -> tuple[list[SecReport], bool]:
    rows = query.offset(offset).limit(limit + 1).all()
    return rows[:limit], len(rows) > limit


def _apply_legacy_search_filters(
    query,
    writer: Optional[str],
    title: Optional[str],
    mkt_tp: Optional[str],
    company: Optional[int],
):
    if writer:
        query = query.filter(SecReport.WRITER.ilike(f"%{writer}%"))
    if title:
        query = query.filter(SecReport.ARTICLE_TITLE.ilike(f"%{title}%"))
    if mkt_tp == "global":
        query = query.filter(SecReport.MKT_TP != "KR")
    elif mkt_tp == "domestic":
        query = query.filter(SecReport.MKT_TP == "KR")
    if company is not None:
        query = query.filter(SecReport.SEC_FIRM_ORDER == company)
    return query


@router.get("/industry")
@router.get("/industry/")
async def get_ords_industry_reports(
    request: Request,
    last_report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    board_filters = [
        and_(
            SecReport.SEC_FIRM_ORDER == firm_order,
            SecReport.ARTICLE_BOARD_ORDER.in_(board_orders),
        )
        for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS
    ]
    query = db.query(SecReport).filter(
        or_(*board_filters),
        SecReport.MAIN_CH_SEND_YN == "Y",
    )
    if last_report_id is not None:
        query = query.filter(SecReport.report_id < last_report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company)

    rows, has_more = _paginate_ords_query(
        query.order_by(SecReport.report_id.desc()),
        limit,
        offset,
    )
    return _ords_collection_response(request, rows, limit, offset, has_more)


@router.get("/search")
@router.get("/search/")
async def search_ords_reports(
    request: Request,
    report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(SecReport)
    if report_id is not None:
        query = query.filter(SecReport.report_id == report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company)

    if report_id is not None:
        query = query.order_by(SecReport.report_id.desc())
    else:
        query = query.order_by(
            SecReport.REG_DT.desc(),
            SecReport.SAVE_TIME.desc(),
            SecReport.report_id.desc(),
            SecReport.SEC_FIRM_ORDER,
            SecReport.ARTICLE_BOARD_ORDER,
        )

    rows, has_more = _paginate_ords_query(query, limit, offset)
    return _ords_collection_response(request, rows, limit, offset, has_more)
