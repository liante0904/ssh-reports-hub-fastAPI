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
        "sec_firm_order": report.sec_firm_order,
        "article_board_order": report.article_board_order,
        "firm_nm": report.firm_nm,
        "send_user": None,
        "main_ch_send_yn": report.main_ch_send_yn,
        "download_status_yn": None,
        "save_time": report.save_time,
        "reg_dt": report.reg_dt,
        "writer": report.writer,
        "key": report.key,
        "mkt_tp": report.mkt_tp,
        "article_title": report.article_title,
        "telegram_url": report.telegram_url,
        "article_url": report.article_url,
        "download_url": report.download_url,
        "pdf_url": report.pdf_url,
        "gemini_summary": report.gemini_summary,
        "summary_time": report.summary_time,
        "summary_model": report.summary_model,
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
    board: Optional[int] = None,
):
    if writer:
        query = query.filter(SecReport.writer.ilike(f"%{writer}%"))
    if title:
        query = query.filter(SecReport.article_title.ilike(f"%{title}%"))
    if mkt_tp == "global":
        query = query.filter(SecReport.mkt_tp != "KR")
    elif mkt_tp == "domestic":
        query = query.filter(SecReport.mkt_tp == "KR")
    if company is not None:
        query = query.filter(SecReport.sec_firm_order == company)
    if board is not None:
        query = query.filter(SecReport.article_board_order == board)
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
    board: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    board_filters = [
        and_(
            SecReport.sec_firm_order == firm_order,
            SecReport.article_board_order.in_(board_orders),
        )
        for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS
    ]
    query = db.query(SecReport).filter(
        or_(*board_filters),
        SecReport.main_ch_send_yn == "Y",
    )
    if last_report_id is not None:
        query = query.filter(SecReport.report_id < last_report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company, board)

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
    board: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(SecReport)
    if report_id is not None:
        query = query.filter(SecReport.report_id == report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company, board)

    if report_id is not None:
        query = query.order_by(SecReport.report_id.desc())
    else:
        query = query.order_by(
            SecReport.reg_dt.desc(),
            SecReport.save_time.desc(),
            SecReport.report_id.desc(),
            SecReport.sec_firm_order,
            SecReport.article_board_order,
        )

    rows, has_more = _paginate_ords_query(query, limit, offset)
    return _ords_collection_response(request, rows, limit, offset, has_more)
