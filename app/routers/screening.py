"""
소외주 발굴 (Value Screening) API

tbl_daily_stock_screening + tbl_fnguide_consensus + tbl_fnguide_report_summaries
3-way JOIN으로 저PER·저PBR·고성장 종목을 필터링합니다.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..cache import cache_response
from ..database import get_reports_db
from ..schemas import ScreeningItemResponse

router = APIRouter(prefix="/external/api", tags=["screening"])

SCREENING_QUERY = """
WITH latest_screen AS (
    SELECT * FROM tbl_daily_stock_screening
    WHERE collected_date = (SELECT MAX(collected_date) FROM tbl_daily_stock_screening)
),
latest_cons AS (
    SELECT DISTINCT ON (code) *
    FROM tbl_fnguide_consensus
    WHERE date = (SELECT MAX(date) FROM tbl_fnguide_consensus)
      AND target_period = '2026.12(E)'
    ORDER BY code, date DESC
),
fn_summaries AS (
    SELECT
        company_name,
        COUNT(*) AS report_cnt,
        STRING_AGG(DISTINCT LEFT(summary_text, 120), ' | '
                   ORDER BY report_date DESC) AS sample_summaries,
        STRING_AGG(DISTINCT opinion, ', '
                   ORDER BY opinion) FILTER (WHERE opinion IS NOT NULL AND opinion != '') AS opinions,
        MAX(report_date) AS latest_report_date
    FROM tbl_fnguide_report_summaries
    WHERE summary_text IS NOT NULL AND summary_text != ''
    GROUP BY company_name
)
SELECT
    s.stock_code,
    s.stock_name,
    s.market,
    s.sector,
    s.current_price,
    s.change_rate,
    s.per,
    s.fwd_per,
    s.pbr,
    s.roe,
    s.market_cap,
    s.return_1m,
    s.return_3m,
    s.return_1y,
    ROUND(c.rev_op_1y::numeric, 1) AS op_growth_1y,
    ROUND(c.rev_np_1y::numeric, 1) AS np_growth_1y,
    ROUND(c.rev_op_3m::numeric, 1) AS op_growth_3m,
    ROUND(c.avg_target_price::numeric, 0) AS avg_target_price,
    ROUND(
        (c.avg_target_price::numeric - s.current_price::numeric)
        / NULLIF(s.current_price::numeric, 0) * 100,
        1
    ) AS target_upside_pct,
    c.est_inst_cnt,
    c.avg_recommendation,
    COALESCE(f.report_cnt, 0) AS fn_report_cnt,
    f.sample_summaries,
    f.opinions,
    f.latest_report_date
FROM latest_screen s
JOIN latest_cons c ON s.stock_code = c.code
LEFT JOIN fn_summaries f ON s.stock_name = f.company_name
WHERE s.per > 0
  AND s.per < :max_per
  AND s.pbr > 0
  AND s.pbr < :max_pbr
  AND c.rev_op_1y IS NOT NULL
  AND c.rev_op_1y > :min_growth
ORDER BY c.rev_op_1y DESC
LIMIT :limit OFFSET :offset
"""


@router.get("/screening", response_model=list[ScreeningItemResponse], summary="소외주 발굴 — 저PER·저PBR·고성장 종목 필터")
@router.get("/screening/", response_model=list[ScreeningItemResponse], include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (장중에는 자주 바뀌지 않음)
async def get_screening(
    request: Request,
    max_per: Annotated[float, Query(ge=1, le=100)] = 10.0,
    max_pbr: Annotated[float, Query(ge=0.1, le=10)] = 1.0,
    min_growth: Annotated[float, Query(ge=-100, le=500)] = 0.0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    저PER·저PBR·고성장 종목을 필터링합니다.

    - **max_per**: 최대 PER (기본 10)
    - **max_pbr**: 최대 PBR (기본 1.0)
    - **min_growth**: 최소 영업이익 1년 변화율 % (기본 0, 즉 성장주만)
    - **limit**: 반환 개수 (기본 50)
    - **offset**: 페이징 오프셋

    응답에는 FnGuide 요약본 sample_summaries 와 opinions 정보가 포함됩니다.
    """
    params = {
        "max_per": max_per,
        "max_pbr": max_pbr,
        "min_growth": min_growth,
        "limit": limit,
        "offset": offset,
    }
    rows = db.execute(text(SCREENING_QUERY), params).mappings().all()
    return [dict(row) for row in rows]
