"""
FCF (Free Cash Flow) 스크리닝 API.

제공 엔드포인트:
- GET /api/screening/fcf          : 전체 FCF 스크리닝 목록 (페이징)
- GET /api/screening/fcf/{code}   : 단일 종목 FCF 상세
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_keywords_db

logger = logging.getLogger("app.fcf_screening")

router = APIRouter(prefix="/screening/fcf", tags=["FCF Screening"])
api_router = APIRouter(prefix="/api/screening/fcf", tags=["FCF Screening"], include_in_schema=False)


# ── Response schemas ──

class FcfScreeningItem(BaseModel):
    stock_code: str
    stock_name: str
    market: Optional[str] = None
    sector: Optional[str] = None
    mktcap_date: Optional[date] = None
    market_cap: Optional[float] = None
    current_price: Optional[float] = None
    corp_name: Optional[str] = None
    report_year: Optional[int] = None
    report_code: Optional[str] = None
    report_type: Optional[str] = None
    operating_cash_flow: Optional[float] = None
    capex_tangible: Optional[float] = None
    capex_intangible: Optional[float] = None
    capex: Optional[float] = None
    fcf: Optional[float] = None
    p_fcf: Optional[float] = None
    fcf_yield: Optional[float] = None
    total_debt: Optional[float] = None
    cash_equivalents: Optional[float] = None
    ev: Optional[float] = None
    ev_fcf: Optional[float] = None

    class Config:
        from_attributes = True


class FcfScreeningListResponse(BaseModel):
    items: list[FcfScreeningItem]
    total: int
    limit: int
    offset: int


# ── Helpers ──

SECTOR_BLACKLIST = [
    '은행', '증권', '보험', '금융업', '기타금융',
    '부동산', '저축은행', '카드', '창업투자', '선물', '신탁',
]

SORT_COLUMNS = {
    'fcf_yield': 'fcf_yield DESC NULLS LAST',
    'p_fcf': 'p_fcf ASC NULLS LAST',
    'market_cap': 'market_cap DESC NULLS LAST',
    'fcf': 'fcf DESC NULLS LAST',
    'stock_code': 'stock_code ASC',
}


def _build_fcf_query(
    stock_code: Optional[str] = None,
    sector: Optional[str] = None,
    market: Optional[str] = None,
    min_fcf_yield: Optional[float] = None,
    max_p_fcf: Optional[float] = None,
    sort_by: str = 'fcf_yield',
    limit: int = 50,
    offset: int = 0,
):
    """mv_fcf_screening 기반 동적 쿼리 빌더."""
    where_clauses = []
    params: dict = {}

    if stock_code:
        where_clauses.append("stock_code = :stock_code")
        params["stock_code"] = stock_code
    if sector:
        where_clauses.append("sector = :sector")
        params["sector"] = sector
    if market:
        where_clauses.append("market = :market")
        params["market"] = market
    if min_fcf_yield is not None:
        where_clauses.append("fcf_yield >= :min_fcf_yield")
        params["min_fcf_yield"] = min_fcf_yield
    if max_p_fcf is not None:
        where_clauses.append("p_fcf <= :max_p_fcf AND p_fcf IS NOT NULL")
        params["max_p_fcf"] = max_p_fcf

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    order_sql = SORT_COLUMNS.get(sort_by, 'fcf_yield DESC NULLS LAST')

    return where_sql, order_sql, params


# ── Endpoints ──

@router.get("")
@router.get("/")
@api_router.get("")
@api_router.get("/")
async def list_fcf_screening(
    stock_code: Optional[str] = Query(None, description="종목코드 필터"),
    sector: Optional[str] = Query(None, description="섹터 필터"),
    market: Optional[str] = Query(None, description="시장 필터 (KOSPI/KOSDAQ)"),
    min_fcf_yield: Optional[float] = Query(None, description="최소 FCF Yield (%)"),
    max_p_fcf: Optional[float] = Query(None, description="최대 P/FCF"),
    sort_by: str = Query("fcf_yield", description="정렬 기준 (fcf_yield, p_fcf, market_cap, fcf)"),
    limit: int = Query(50, ge=1, le=500, description="페이지 크기"),
    offset: int = Query(0, ge=0, description="오프셋"),
    db: Session = Depends(get_keywords_db),
):
    """FCF 스크리닝 목록을 반환합니다. mv_fcf_screening 뷰를 사용."""
    where_sql, order_sql, params = _build_fcf_query(
        stock_code=stock_code, sector=sector, market=market,
        min_fcf_yield=min_fcf_yield, max_p_fcf=max_p_fcf,
        sort_by=sort_by, limit=limit, offset=offset,
    )

    # Total count
    count_sql = f"SELECT COUNT(*) FROM mv_fcf_screening WHERE {where_sql}"
    total_row = db.execute(text(count_sql), params).fetchone()
    total = total_row[0] if total_row else 0

    # Data query
    data_sql = f"""
        SELECT stock_code, stock_name, market, sector, mktcap_date, market_cap,
               current_price, corp_name, report_year, report_code, report_type,
               operating_cash_flow, capex_tangible, capex_intangible, capex, fcf,
               p_fcf, fcf_yield, total_debt, cash_equivalents, ev, ev_fcf
        FROM mv_fcf_screening
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    rows = db.execute(text(data_sql), params).fetchall()

    items = [
        FcfScreeningItem(
            stock_code=r[0], stock_name=r[1], market=r[2], sector=r[3],
            mktcap_date=r[4], market_cap=float(r[5]) if r[5] else None,
            current_price=float(r[6]) if r[6] else None, corp_name=r[7],
            report_year=r[8], report_code=r[9], report_type=r[10],
            operating_cash_flow=float(r[11]) if r[11] else None,
            capex_tangible=float(r[12]) if r[12] else None,
            capex_intangible=float(r[13]) if r[13] else None,
            capex=float(r[14]) if r[14] else None,
            fcf=float(r[15]) if r[15] else None,
            p_fcf=float(r[16]) if r[16] else None,
            fcf_yield=float(r[17]) if r[17] else None,
            total_debt=float(r[18]) if r[18] else None,
            cash_equivalents=float(r[19]) if r[19] else None,
            ev=float(r[20]) if r[20] else None,
            ev_fcf=float(r[21]) if r[21] else None,
        )
        for r in rows
    ]

    return FcfScreeningListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{stock_code}")
@router.get("/{stock_code}/")
@api_router.get("/{stock_code}")
@api_router.get("/{stock_code}/")
async def get_fcf_detail(
    stock_code: str,
    db: Session = Depends(get_keywords_db),
):
    """단일 종목의 FCF 상세 데이터를 반환합니다. 모든 보고기간 포함."""
    rows = db.execute(
        text("""
            SELECT stock_code, stock_name, market, sector, mktcap_date, market_cap,
                   current_price, corp_name, report_year, report_code, report_type,
                   operating_cash_flow, capex_tangible, capex_intangible, capex, fcf,
                   p_fcf, fcf_yield, total_debt, cash_equivalents, ev, ev_fcf
            FROM mv_fcf_screening
            WHERE stock_code = :stock_code
            ORDER BY report_year DESC, report_code DESC
        """),
        {"stock_code": stock_code},
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"FCF data not found for stock_code={stock_code}")

    return [
        FcfScreeningItem(
            stock_code=r[0], stock_name=r[1], market=r[2], sector=r[3],
            mktcap_date=r[4], market_cap=float(r[5]) if r[5] else None,
            current_price=float(r[6]) if r[6] else None, corp_name=r[7],
            report_year=r[8], report_code=r[9], report_type=r[10],
            operating_cash_flow=float(r[11]) if r[11] else None,
            capex_tangible=float(r[12]) if r[12] else None,
            capex_intangible=float(r[13]) if r[13] else None,
            capex=float(r[14]) if r[14] else None,
            fcf=float(r[15]) if r[15] else None,
            p_fcf=float(r[16]) if r[16] else None,
            fcf_yield=float(r[17]) if r[17] else None,
            total_debt=float(r[18]) if r[18] else None,
            cash_equivalents=float(r[19]) if r[19] else None,
            ev=float(r[20]) if r[20] else None,
            ev_fcf=float(r[21]) if r[21] else None,
        )
        for r in rows
    ]


@router.get("/sectors/list")
@router.get("/sectors/list/")
@api_router.get("/sectors/list")
@api_router.get("/sectors/list/")
async def list_sectors(
    db: Session = Depends(get_keywords_db),
):
    """FCF 스크리닝이 가능한 섹터 목록을 반환합니다 (금융업 제외)."""
    rows = db.execute(
        text("SELECT DISTINCT sector FROM mv_fcf_screening WHERE sector IS NOT NULL ORDER BY sector")
    ).fetchall()
    return [r[0] for r in rows]
