from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, or_, not_
from sqlalchemy.orm import Session, joinedload

from ..database import get_reports_db
from ..models import SecReport

router = APIRouter(prefix="/ords/admin/data_main_daily_send", tags=["ords-compat"])

"""
[산업분석 필터 관리 가이드]
INDUSTRY_REPORT_BOARD_FILTERS는 산업분석 리포트만 추출하기 위한 증권사별 보드 매핑입니다.
- 하나증권(3): 1(경제) 제외, 6(산업), 15(글로벌산업) 적용 (2026.05.12 수정)
- DB증권(19): 기업/산업 합본 보드이므로 제목에서 종목코드 패턴 (숫자 5~6자리) 제외 필터 필수 적용
- 신규 추가: SK(26), 유안타(27), 흥국(28) (2026.05.12)
"""
INDUSTRY_REPORT_BOARD_FILTERS = (
    (0, (2,)),                     # LS증권 산업분석
    (1, (0,)),                     # 신한증권 산업분석
    (3, (6, 15)),                  # 하나증권 산업분석 + 글로벌 산업분석
    (5, (1,)),                     # 삼성증권 산업분석
    (6, (1,)),                     # 상상인증권 산업리포트
    (10, (1,)),                    # 키움증권 산업분석
    (14, (8, 9, 10, 11, 12, 13)),  # 다올투자증권 산업분석
    (18, (1,)),                    # IM증권 산업분석(국내)
    (19, (0,)),                    # DB증권 기업/산업분석(국내) - 종목코드 필터 필요
    (20, (1,)),                    # 메리츠증권 산업분석
    (22, (1,)),                    # 한양증권 산업 및 이슈 분석
    (23, (1,)),                    # BNK투자증권 산업분석
    (24, (1,)),                    # 교보증권 산업분석
    (25, (2,)),                    # IBK투자증권 산업분석
    (26, (6, 8)),                  # SK증권 산업분석
    (27, (1,)),                    # 유안타증권 산업분석
    (28, (0,)),                    # 흥국증권 산업/기업분석
)


def _report_to_ords_item(report: SecReport) -> dict:
    archive = report.pdf_archive
    item = {
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
    if archive:
        item["pdf_archive"] = {
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
    else:
        item["pdf_archive"] = None
    return item


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
    board_filters = []
    for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS:
        f = and_(
            SecReport.sec_firm_order == firm_order,
            SecReport.article_board_order.in_(board_orders),
        )
        if firm_order == 19:
            # DB증권: 종목코드(숫자 5~6자리)가 포함된 제목은 기업분석이므로 제외 (산업분석만 포함)
            # !~ 연산자는 PostgreSQL 전용이므로 dialect를 체크하여 적용
            if db.get_bind().dialect.name == "postgresql":
                f = and_(f, SecReport.article_title.op("!~")(r"\([0-9]{5,6}\)"))
        board_filters.append(f)

    query = db.query(SecReport).filter(
        or_(*board_filters),
        SecReport.main_ch_send_yn == "Y",
    )
    if last_report_id is not None:
        query = query.filter(SecReport.report_id < last_report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company, board)
    query = query.options(joinedload(SecReport.pdf_archive))

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
    has_summary: Annotated[Optional[bool], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(SecReport)
    if report_id is not None:
        query = query.filter(SecReport.report_id == report_id)
    query = _apply_legacy_search_filters(query, writer, title, mkt_tp, company, board)
    query = query.options(joinedload(SecReport.pdf_archive))

    # AI 요약이 있는 리포트만 필터링
    if has_summary:
        query = query.filter(
            SecReport.gemini_summary.isnot(None),
            SecReport.gemini_summary != "",
            SecReport.gemini_summary != " ",
        )

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
