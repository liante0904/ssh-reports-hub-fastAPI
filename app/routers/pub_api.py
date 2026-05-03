from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import SecReport, SecFirmInfo, SecBoardInfo
from ..schemas import CompanyResponse, BoardResponse

# 새로운 주소 체계를 위한 라우터 (레거시 ords_compat부와 로직 동일)
router = APIRouter(prefix="/pub/api", tags=["public-api"])

@router.get("/companies", response_model=list[CompanyResponse], summary="증권사 정보 목록 조회 (리포트 존재 기준)")
async def get_companies(db: Session = Depends(get_reports_db)):
    """
    tbm_sec_firm_info와 tbl_sec_reports를 JOIN하여
    실제로 리포트가 존재하는 증권사 목록과 리포트 개수를 반환합니다.
    """
    query = db.query(
        SecFirmInfo.sec_firm_name,
        SecFirmInfo.is_direct_link,
        SecFirmInfo.description,
        func.count(SecReport.report_id).label("report_count")
    ).join(
        SecReport, SecFirmInfo.sec_firm_order == SecReport.sec_firm_order
    ).filter(
        SecReport.main_ch_send_yn == 'Y'
    ).group_by(
        SecFirmInfo.sec_firm_order,
        SecFirmInfo.sec_firm_name,
        SecFirmInfo.is_direct_link,
        SecFirmInfo.description
    ).order_by(SecFirmInfo.sec_firm_order.asc())
    
    results = query.all()
    
    return [
        CompanyResponse(
            name=row.sec_firm_name,
            is_direct=(row.is_direct_link == 'Y'),
            note=row.description,
            report_count=row.report_count
        ) for row in results
    ]

@router.get("/boards", response_model=list[BoardResponse], summary="특정 증권사의 게시판 목록 조회")
async def get_boards(
    company: Annotated[int, Query(ge=0)],
    db: Session = Depends(get_reports_db)
):
    """
    TBM_SEC_FIRM_BOARD_INFO와 SecReport를 JOIN하여 
    리포트가 존재하는 게시판 목록을 반환합니다.
    """
    query = db.query(
        SecBoardInfo.sec_firm_order,
        SecBoardInfo.article_board_order,
        SecBoardInfo.board_nm,
        SecBoardInfo.label_nm,
        func.count(SecReport.report_id).label("report_count")
    ).outerjoin(
        SecReport, and_(
            SecBoardInfo.sec_firm_order == SecReport.sec_firm_order,
            SecBoardInfo.article_board_order == SecReport.article_board_order,
            SecReport.main_ch_send_yn == 'Y'
        )
    ).filter(
        SecBoardInfo.sec_firm_order == company
    ).group_by(
        SecBoardInfo.sec_firm_order,
        SecBoardInfo.article_board_order,
        SecBoardInfo.board_nm,
        SecBoardInfo.label_nm
    ).order_by(SecBoardInfo.article_board_order.asc())

    results = query.all()

    return [
        BoardResponse(
            sec_firm_order=row.sec_firm_order,
            article_board_order=row.article_board_order,
            board_nm=row.board_nm,
            label_nm=row.label_nm,
            report_count=row.report_count
        ) for row in results
    ]

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


def _report_to_ords_item(report: SecReport, is_direct: bool = None) -> dict:
    return {
        "report_id": report.report_id,
        "sec_firm_order": report.sec_firm_order,
        "article_board_order": report.article_board_order,
        "firm_nm": report.firm_nm,
        "is_direct": is_direct,
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
    items: list,
    limit: int,
    offset: int,
    has_more: bool,
) -> dict:
    processed_items = []
    for item in items:
        if isinstance(item, tuple):
            report, is_direct_link = item
            processed_items.append(_report_to_ords_item(report, is_direct_link == 'Y'))
        else:
            processed_items.append(_report_to_ords_item(item))

    return {
        "items": processed_items,
        "hasMore": has_more,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "links": [
            {"rel": "self", "href": str(request.url)},
            {"rel": "first", "href": str(request.url.include_query_params(offset=0))},
        ],
    }


def _paginate_ords_query(query, limit: int, offset: int) -> tuple[list, bool]:
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


@router.get("/industry", summary="산업별 리포트 조회 (Public API)")
@router.get("/industry/", include_in_schema=False)
async def get_industry_reports(
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
    """
    산업별 필터가 적용된 리포트 목록을 조회합니다. (구 ORDS industry 경로 마이그레이션용)
    """
    board_filters = [
        and_(
            SecReport.sec_firm_order == firm_order,
            SecReport.article_board_order.in_(board_orders),
        )
        for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS
    ]
    query = db.query(SecReport, SecFirmInfo.is_direct_link).outerjoin(
        SecFirmInfo, SecReport.sec_firm_order == SecFirmInfo.sec_firm_order
    ).filter(
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


@router.get("/search", summary="리포트 통합 검색 (Public API)")
@router.get("/search/", include_in_schema=False)
async def search_reports(
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
    """
    다양한 필터를 사용하여 리포트를 검색합니다. (구 ORDS search 경로 마이그레이션용)
    """
    query = db.query(SecReport, SecFirmInfo.is_direct_link).outerjoin(
        SecFirmInfo, SecReport.sec_firm_order == SecFirmInfo.sec_firm_order
    )
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
