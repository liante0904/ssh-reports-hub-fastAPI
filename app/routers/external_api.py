import json
import os
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from ..cache import cache_response, invalidate_prefix
from ..database import get_reports_db
from ..models import SecReport, SecFirmInfo, SecBoardInfo, PdfArchive
from ..schemas import CompanyResponse, BoardResponse

# External API 라우터 — 프론트엔드가 직접 호출하는 공개 API
router = APIRouter(prefix="/external/api", tags=["external-api"])

@router.get("/companies", response_model=list[CompanyResponse], summary="증권사 정보 목록 조회 (리포트 존재 기준)")
@cache_response(ttl=1800, prefix="api")  # 30분 캐시 (증권사 목록은 거의 변하지 않음)
async def get_companies(request: Request, db: Session = Depends(get_reports_db)):
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
        SecReport.is_sent == True
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
@cache_response(ttl=600, prefix="api")  # 10분 캐시 (게시판 목록은 자주 변하지 않음)
async def get_boards(
    company: Annotated[int, Query(ge=0)],
    request: Request,
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
            SecReport.is_sent == True
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


def _parse_json_field(value):
    """JSONB/list/str 어떤 타입으로 오든 list로 정규화"""
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _report_to_api_item(report: SecReport, is_direct: bool = None) -> dict:
    archive = report.pdf_archive
    tags = _parse_json_field(report.tags)
    stock_names = _parse_json_field(report.stock_names)
    sector = report.sector or ''
    item = {
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
        "tags": tags,
        "stock_names": stock_names,
        "sector": sector,
    }
    # PDF 아카이브 컬럼 추가
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

    # FnGuide 요약 정보 추가 (LEFT JOIN 결과물)
    fnguide = report.fnguide_summary
    if fnguide:
        item["fnguide_summary"] = {
            "summary_id": fnguide.summary_id,
            "report_title": fnguide.report_title,
            "report_date": fnguide.report_date,
            "company_name": fnguide.company_name,
            "company_code": fnguide.company_code,
            "summary_text": fnguide.summary_text,
            "opinion": fnguide.opinion,
            "target_price": fnguide.target_price,
            "prev_close": fnguide.prev_close,
            "provider": fnguide.provider,
            "author": fnguide.author,
            "pdf_url": fnguide.pdf_url,
        }
    else:
        item["fnguide_summary"] = None

    return item


def _collection_response(
    request: Request,
    items: list,
    limit: int,
    offset: int,
    has_more: bool,
) -> dict:
    processed_items = []
    for item in items:
        try:
            report, is_direct_link = item
        except (TypeError, ValueError):
            processed_items.append(_report_to_api_item(item))
        else:
            processed_items.append(_report_to_api_item(report, is_direct_link == 'Y'))

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


def _paginate_query(query, limit: int, offset: int) -> tuple[list, bool]:
    rows = query.offset(offset).limit(limit + 1).all()
    return rows[:limit], len(rows) > limit


def _apply_search_filters(
    query,
    writer: Optional[str],
    title: Optional[str],
    mkt_tp: Optional[str],
    company: Optional[int],
    board: Optional[int] = None,
    tag: Optional[str] = None,
    sector: Optional[str] = None,
    stock: Optional[str] = None,
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
    if tag:
        query = query.filter(SecReport.tags.ilike(f'%"{tag}"%'))
    if sector:
        query = query.filter(SecReport.sector.ilike(f"%{sector}%"))
    if stock:
        query = query.filter(SecReport.stock_names.ilike(f'%"{stock}"%'))
    return query


@router.get("/industry", summary="산업별 리포트 조회 (Public API)")
@router.get("/industry/", include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (insert 시 internal webhook으로 무효화)
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
    산업별 필터가 적용된 리포트 목록을 조회합니다.
    """
    board_filters = []
    for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS:
        f = and_(
            SecReport.sec_firm_order == firm_order,
            SecReport.article_board_order.in_(board_orders),
        )
        if firm_order == 19:
            # DB증권: 종목코드(숫자 5~6자리)가 포함된 제목은 기업분석이므로 제외
            if db.get_bind().dialect.name == "postgresql":
                f = and_(f, SecReport.article_title.op("!~")(r"\([0-9]{5,6}\)"))
        board_filters.append(f)

    query = db.query(SecReport, SecFirmInfo.is_direct_link).outerjoin(
        SecFirmInfo, SecReport.sec_firm_order == SecFirmInfo.sec_firm_order
    ).filter(
        or_(*board_filters),
        SecReport.is_sent == True,
    )
    # PostgreSQL 전용: 개별 종목코드 제외 (산업분석 게시판에 올라온 기업분석 필터링)
    if db.get_bind().dialect.name == "postgresql":
        query = query.filter(
            SecReport.article_title.op("!~*")(r"\(\d{5,6}"),        # 한국 종목코드 (071050)
            SecReport.article_title.op("!~*")(r"\[\d{5,6}/"),        # [071050/...] 형식
            SecReport.article_title.op("!~*")(r"\([A-Z]{1,5}\.[A-Z]{2}\)"),  # 해외티커 (NVDA.US)
            SecReport.article_title.op("!~*")(r"\(\d+\.K[QS]\)"),       # 국내티커 (005930.KS, 123456.KQ)
            SecReport.article_title.op("!~*")(
                r"\[[^\]]+/(매수|매도|중립|시장수익률|Buy|Hold|Sell|Neutral|Outperform|Underperform|Not\s*Rated|Trading\s*Buy)"
            ),
            SecReport.article_title.op("!~*")(r"목표주가"),
        )
    if last_report_id is not None:
        query = query.filter(SecReport.report_id < last_report_id)
    query = _apply_search_filters(query, writer, title, mkt_tp, company, board)

    # PdfArchive와 outerjoin하여 page_count 기반 필터링
    query = query.outerjoin(PdfArchive, SecReport.report_id == PdfArchive.report_id)
    query = query.filter(
        or_(
            PdfArchive.report_id == None,      # 아카이브 없음 → 통과
            PdfArchive.page_count == None,      # 페이지 정보 없음 → 통과
            PdfArchive.page_count >= 10,        # 10페이지 이상만 통과
        )
    )

    query = query.options(joinedload(SecReport.pdf_archive), joinedload(SecReport.fnguide_summary))

    rows, has_more = _paginate_query(
        query.order_by(SecReport.report_id.desc()),
        limit,
        offset,
    )
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/global", summary="글로벌 리포트 조회 (Public API)")
@router.get("/global/", include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (insert 시 internal webhook으로 무효화)
async def get_global_reports(
    request: Request,
    report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    글로벌(해외주식/글로벌 시장) 관련 리포트 목록을 독립적으로 조회합니다.
    국내 종목코드나 국내 시장 관련 키워드가 제목에 포함된 리포트는 제외됩니다.
    """
    query = db.query(SecReport, SecFirmInfo.is_direct_link).outerjoin(
        SecFirmInfo, SecReport.sec_firm_order == SecFirmInfo.sec_firm_order
    ).filter(
        SecReport.is_sent == True,
        SecReport.mkt_tp != "KR",
    )

    # PostgreSQL 전용: 국내 종목(네오팜 등) 및 국내 퀀트 전략 리포트 필터링 제외
    if db.get_bind().dialect.name == "postgresql":
        query = query.filter(
            # 국내 종목코드 및 티커 형식 (예: 092730.KQ, 005930.KS, 6자리 숫자 종목코드) 제외
            SecReport.article_title.op("!~*")(r"\(\d{5,6}\.K[QS]\)"),
            SecReport.article_title.op("!~*")(r"\b\d{5,6}\b"),
            # 국내 시장 및 퀀트 전략 관련 키워드(코스피, 코스닥, KOSPI, KOSDAQ, 퀀트, Quant, MP) 제외
            SecReport.article_title.op("!~*")(r"코스피|코스닥|KOSPI|KOSDAQ|퀀트|Quant|MP"),
        )

    if report_id is not None:
        query = query.filter(SecReport.report_id == report_id)

    query = _apply_search_filters(query, writer, title, "global", company, board)
    query = query.options(joinedload(SecReport.pdf_archive), joinedload(SecReport.fnguide_summary))

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

    rows, has_more = _paginate_query(query, limit, offset)
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/search", summary="리포트 통합 검색 (Public API)")
@router.get("/search/", include_in_schema=False)
@cache_response(ttl=120, prefix="api")  # 2분 캐시 (insert 시 internal webhook으로 무효화)
async def search_reports(
    request: Request,
    report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    has_summary: Annotated[Optional[bool], Query()] = None,
    tag: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    sector: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    stock: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    outlook: Annotated[Optional[bool], Query()] = None,
    outlook_year: Annotated[Optional[int], Query(ge=2000, le=2099)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    다양한 필터를 사용하여 리포트를 검색합니다.
    tag, sector, stock 파라미터로 enricher 태그 기반 필터링이 가능합니다.

    outlook=true 시 제목에 '전망'이 포함된 시장 전망 리포트만 필터링합니다.
    (2026년 하반기 전망, 연간 전망 등)
    """
    query = db.query(SecReport, SecFirmInfo.is_direct_link).outerjoin(
        SecFirmInfo, SecReport.sec_firm_order == SecFirmInfo.sec_firm_order
    )
    if report_id is not None:
        query = query.filter(SecReport.report_id == report_id)
    query = _apply_search_filters(query, writer, title, mkt_tp, company, board, tag, sector, stock)
    query = query.options(joinedload(SecReport.pdf_archive), joinedload(SecReport.fnguide_summary))

    # AI 요약이 있는 리포트만 필터링
    if has_summary:
        query = query.filter(
            SecReport.gemini_summary.isnot(None),
            SecReport.gemini_summary != "",
            SecReport.gemini_summary != " ",
        )

    # 시장 전망 리포트 필터링
    # 포함: 하반기/상반기/연간/전망포럼 등 시장 맥락 + '전망'
    # 제외: 개별 종목코드(숫자5~6자리), 목표주가 언급
    if outlook:
        query = query.filter(
            # 기본: 제목에 "전망" 포함
            SecReport.article_title.ilike("%전망%"),
            # 시장 맥락 키워드 필수 (하반기, 상반기, 연간, 전망포럼, N년, 2H26 등)
            SecReport.article_title.op("~*")(
                r"하반기|상반기|연간|\d{4}년|\dH\d{2}|전망포럼"
                r"|(?:경제|금융시장|주식시장|시장)\s*전망"
                r"|(?:업종|산업)\s*전망"
            ),
            # 개별 종목코드 제외: (071050), (030200.KS/매수) 등
            SecReport.article_title.op("!~*")(r"\(\d{5,6}"),
            SecReport.article_title.op("!~*")(r"\[\d{5,6}/"),
            # 개별 종목 투자의견 제외: [회사명/매수], [회사명/Buy] 등
            SecReport.article_title.op("!~*")(
                r"\[[^\]]+/(매수|매도|중립|시장수익률|Buy|Hold|Sell|Neutral|Outperform|Underperform|Not\s*Rated|Trading\s*Buy)"
            ),
            # 목표주가 언급 제외
            SecReport.article_title.op("!~*")(r"목표주가"),
        )
        # 연도별 세분 필터 (outlook_year=2026 → 제목에 "2026년" 포함)
        if outlook_year:
            query = query.filter(
                SecReport.article_title.ilike(f"%{outlook_year}년%"),
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

    rows, has_more = _paginate_query(query, limit, offset)
    return _collection_response(request, rows, limit, offset, has_more)


# ---------------------------------------------------------------------------
# Internal 캐시 무효화 Webhook — 스크래퍼가 새 데이터 insert 후 호출
# ---------------------------------------------------------------------------

INTERNAL_CACHE_TOKEN = os.getenv("INTERNAL_CACHE_TOKEN", "")


def _verify_internal_token(x_internal_token: Annotated[Optional[str], Header()] = None) -> None:
    """Internal webhook 호출자를 shared secret으로 인증한다."""
    if not INTERNAL_CACHE_TOKEN:
        raise HTTPException(status_code=501, detail="Internal cache invalidation is not configured")
    if not x_internal_token or x_internal_token != INTERNAL_CACHE_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/internal/cache/invalidate", summary="[Internal] Redis 캐시 무효화")
async def invalidate_cache(
    x_internal_token: Annotated[Optional[str], Header()] = None,
    prefix: Annotated[str, Query(description="무효화할 캐시 키 prefix (기본값: api)")] = "api",
):
    """
    스크래퍼가 새 리포트를 PostgreSQL에 insert 한 후 호출하는 internal webhook.
    지정된 prefix의 Redis 캐시를 모두 삭제하여 다음 API 호출이 최신 데이터를 반환하도록 한다.

    사용 예 (GitHub Actions / cron):
        curl -X POST https://ssh-oci.duckdns.org/external/api/internal/cache/invalidate \\
          -H "X-Internal-Token: $INTERNAL_CACHE_TOKEN"
    """
    _verify_internal_token(x_internal_token)
    deleted = await invalidate_prefix(prefix)
    return {"status": "ok", "deleted_keys": deleted}
