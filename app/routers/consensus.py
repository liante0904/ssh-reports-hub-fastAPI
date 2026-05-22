from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_reports_db
from ..models import ConsensusHistory
from ..schemas import (
    ConsensusResponse,
    ConsensusHistoryResponse,
    ConsensusSummaryResponse,
    ConsensusSectorResponse,
    Consensus1DRevisionResponse,
    Consensus1DRevisionSummaryResponse,
    RevisionMetricItem,
)

router = APIRouter(prefix="/consensus", tags=["Consensus"])


@router.get("/summary", response_model=ConsensusSummaryResponse)
@router.get("/summary/", response_model=ConsensusSummaryResponse)
async def get_consensus_summary(db: Session = Depends(get_reports_db)):
    """
    오늘(가장 최근 날짜)의 상향/하향 리비전 건수 요약을 조회합니다.
    """
    latest_date = db.query(func.max(ConsensusHistory.date)).scalar()
    if not latest_date:
        return {"total": 0, "up_count": 0, "down_count": 0, "latest_date": datetime.now()}

    total = db.query(ConsensusHistory).filter(ConsensusHistory.date == latest_date).count()
    up_count = db.query(ConsensusHistory).filter(
        ConsensusHistory.date == latest_date, 
        or_(ConsensusHistory.rev_1m > 0, ConsensusHistory.rev_3m > 0)
    ).count()
    down_count = db.query(ConsensusHistory).filter(
        ConsensusHistory.date == latest_date, 
        or_(ConsensusHistory.rev_1m < 0, ConsensusHistory.rev_3m < 0)
    ).count()

    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "latest_date": latest_date
    }


@router.get("/history", response_model=list[ConsensusHistoryResponse])
@router.get("/history/", response_model=list[ConsensusHistoryResponse])
async def get_consensus_history(
    code: Annotated[str, Query(min_length=1, max_length=32)],
    target_period: Annotated[Optional[str], Query(min_length=1, max_length=16)] = None,
    db: Session = Depends(get_reports_db),
):
    """
    특정 종목의 과거 컨센서스 변화 이력을 조회합니다. (차트용)
    """
    query = db.query(ConsensusHistory).filter(ConsensusHistory.code == code)
    
    if target_period:
        query = query.filter(ConsensusHistory.target_period == target_period)
    else:
        # target_period가 없을 경우 가장 최근 레코드의 target_period를 기준으로 조회
        latest_period_sq = (
            select(ConsensusHistory.target_period)
            .filter(ConsensusHistory.code == code)
            .order_by(ConsensusHistory.date.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = query.filter(ConsensusHistory.target_period == latest_period_sq)

    return query.order_by(ConsensusHistory.date.asc()).all()


@router.get("/latest", response_model=list[ConsensusResponse])
@router.get("/latest/", response_model=list[ConsensusResponse])
async def get_latest_revision(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    code: Annotated[Optional[str], Query(min_length=1, max_length=32)] = None,
    db: Session = Depends(get_reports_db),
):
    latest_date_sq = select(func.max(ConsensusHistory.date)).scalar_subquery()
    previous_date_sq = select(func.max(ConsensusHistory.date)).where(ConsensusHistory.date < latest_date_sq).scalar_subquery()

    latest = aliased(ConsensusHistory)
    previous = aliased(ConsensusHistory)

    operating_profit_revision = case(
        (
            or_(previous.operating_profit.is_(None), previous.operating_profit == 0),
            0.0,
        ),
        else_=func.round(
            ((latest.operating_profit - previous.operating_profit) / func.abs(previous.operating_profit)) * 100,
            2,
        ),
    )
    net_income_revision = case(
        (
            or_(previous.net_income.is_(None), previous.net_income == 0),
            0.0,
        ),
        else_=func.round(
            ((latest.net_income - previous.net_income) / func.abs(previous.net_income)) * 100,
            2,
        ),
    )
    sales_revision = case(
        (
            or_(previous.sales.is_(None), previous.sales == 0),
            0.0,
        ),
        else_=func.round(((latest.sales - previous.sales) / func.abs(previous.sales)) * 100, 2),
    )
    eps_revision = case(
        (
            or_(previous.eps.is_(None), previous.eps == 0),
            0.0,
        ),
        else_=func.round(((latest.eps - previous.eps) / func.abs(previous.eps)) * 100, 2),
    )

    query = (
        db.query(
            latest.code.label("code"),
            latest.name.label("name"),
            latest.date.label("date"),
            latest.target_period.label("target_period"),
            latest.sector.label("sector"),
            latest.current_price.label("current_price"),
            latest.market_cap.label("market_cap"),
            latest.per.label("per"),
            latest.pbr.label("pbr"),
            latest.roe.label("roe"),
            latest.dividend_yield.label("dividend_yield"),
            latest.operating_profit.label("operating_profit"),
            previous.operating_profit.label("operating_profit_prev"),
            operating_profit_revision.label("operating_profit_revision"),
            latest.net_income.label("net_income"),
            previous.net_income.label("net_income_prev"),
            net_income_revision.label("net_income_revision"),
            latest.sales.label("sales"),
            previous.sales.label("sales_prev"),
            sales_revision.label("sales_revision"),
            latest.eps.label("eps"),
            previous.eps.label("eps_prev"),
            eps_revision.label("eps_revision"),
            latest.rev_1m.label("rev_1m"),
            latest.rev_3m.label("rev_3m"),
            latest.updated_at.label("updated_at"),
        )
        .select_from(latest)
        .outerjoin(
            previous,
            and_(
                latest.code == previous.code,
                latest.target_period == previous.target_period,
                previous.date == previous_date_sq,
            ),
        )
        .filter(latest.date == latest_date_sq)
    )

    if code:
        query = query.filter(latest.code == code)

    rows = (
        query.order_by(
            func.abs(func.coalesce(latest.rev_1m, operating_profit_revision, 0)).desc(),
            latest.operating_profit.desc().nullslast(),
            latest.code.asc(),
            latest.target_period.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return rows


@router.get("/top-picks", response_model=list[ConsensusHistoryResponse])
@router.get("/top-picks/", response_model=list[ConsensusHistoryResponse])
async def get_top_picks(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_reports_db),
):
    """
    이익 상향(rev_1m > 0) + 우량 지표 종목을 추출합니다.
    """
    latest_date_sq = select(func.max(ConsensusHistory.date)).scalar_subquery()
    
    query = (
        db.query(ConsensusHistory)
        .filter(
            ConsensusHistory.date == latest_date_sq,
            ConsensusHistory.rev_1m > 0,
            ConsensusHistory.per > 0
        )
        .order_by(ConsensusHistory.rev_1m.desc(), ConsensusHistory.roe.desc())
        .limit(limit)
    )
    return query.all()


@router.get("/sectors", response_model=list[ConsensusSectorResponse])
@router.get("/sectors/", response_model=list[ConsensusSectorResponse])
async def get_sector_analysis(db: Session = Depends(get_reports_db)):
    """
    섹터별 평균 리비전 현황을 분석합니다.
    """
    latest_date_sq = select(func.max(ConsensusHistory.date)).scalar_subquery()
    
    query = (
        db.query(
            ConsensusHistory.sector.label("sector"),
            func.count(ConsensusHistory.code).label("stock_count"),
            func.round(func.avg(ConsensusHistory.rev_1m), 2).label("avg_rev_1m"),
            func.round(func.avg(ConsensusHistory.rev_3m), 2).label("avg_rev_3m")
        )
        .filter(
            ConsensusHistory.date == latest_date_sq,
            ConsensusHistory.sector.isnot(None),
            ConsensusHistory.sector != ""
        )
        .group_by(ConsensusHistory.sector)
        .order_by(func.avg(ConsensusHistory.rev_1m).desc())
    )
    
    results = query.all()
    return [{"sector": r.sector, "stock_count": r.stock_count, "avg_rev_1m": r.avg_rev_1m, "avg_rev_3m": r.avg_rev_3m} for r in results]


@router.get("/screener", response_model=list[ConsensusHistoryResponse])
@router.get("/screener/", response_model=list[ConsensusHistoryResponse])
async def get_screener(
    min_rev_1m: float = 0.0,
    max_per: float = 20.0,
    min_roe: float = 5.0,
    sector: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_reports_db),
):
    """
    사용자 정의 조건으로 종목을 검색합니다.
    """
    latest_date_sq = select(func.max(ConsensusHistory.date)).scalar_subquery()
    
    query = db.query(ConsensusHistory).filter(
        ConsensusHistory.date == latest_date_sq,
        ConsensusHistory.rev_1m >= min_rev_1m,
        ConsensusHistory.per <= max_per,
        ConsensusHistory.roe >= min_roe
    )
    
    if sector:
        query = query.filter(ConsensusHistory.sector == sector)
        
    return query.order_by(ConsensusHistory.rev_1m.desc()).limit(limit).all()


# ── 1D Revision helpers ──────────────────────────────────────────────

def _calc_revision(today_val, yesterday_val) -> dict:
    """두 값의 변화율과 방향을 계산한다."""
    if today_val is None or yesterday_val is None or yesterday_val == 0:
        return {"today": today_val, "yesterday": yesterday_val, "change_pct": 0.0, "direction": "flat"}

    change_pct = round(((today_val - yesterday_val) / abs(yesterday_val)) * 100, 2)
    if change_pct > 0:
        direction = "up"
    elif change_pct < 0:
        direction = "down"
    else:
        direction = "flat"

    return {"today": today_val, "yesterday": yesterday_val, "change_pct": change_pct, "direction": direction}


def _build_revision_rows(db: Session):
    """오늘 vs 이전일자 self-join 결과를 row dict 리스트로 반환."""
    latest_date_sq = select(func.max(ConsensusHistory.date)).scalar_subquery()
    previous_date_sq = select(func.max(ConsensusHistory.date)).where(ConsensusHistory.date < latest_date_sq).scalar_subquery()

    latest = aliased(ConsensusHistory)
    previous = aliased(ConsensusHistory)

    query = (
        db.query(
            latest.code,
            latest.name,
            latest.date,
            latest.target_period,
            latest.sector,
            latest.current_price,
            latest.operating_profit,
            previous.operating_profit,
            latest.net_income,
            previous.net_income,
            latest.sales,
            previous.sales,
            latest.eps,
            previous.eps,
            latest.rev_1m,
            latest.rev_3m,
            latest.updated_at,
        )
        .select_from(latest)
        .outerjoin(
            previous,
            and_(
                latest.code == previous.code,
                latest.target_period == previous.target_period,
                previous.date == previous_date_sq,
            ),
        )
        .filter(latest.date == latest_date_sq)
    )

    rows = query.all()
    return rows


# ── 1D Revision endpoints ───────────────────────────────────────────

@router.get("/revision/1d", response_model=list[Consensus1DRevisionResponse])
@router.get("/revision/1d/", response_model=list[Consensus1DRevisionResponse])
async def get_1d_revision(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    code: Annotated[Optional[str], Query(min_length=1, max_length=32)] = None,
    sector: Annotated[Optional[str], Query(min_length=1, max_length=64)] = None,
    target_period: Annotated[Optional[str], Query(min_length=1, max_length=16)] = None,
    sort_by: Annotated[str, Query(pattern="^(op|ni|sales|eps|rev_1m|rev_3m)$")] = "op",
    direction: Annotated[Optional[str], Query(pattern="^(up|down|all)$")] = "all",
    db: Session = Depends(get_reports_db),
):
    """
    **1D 리비전**: 오늘 들어온 컨센서스 데이터와 이전일자를 비교해 변화율을 조회한다.

    - `sort_by`: 정렬 기준 (op / ni / sales / eps / rev_1m / rev_3m)
    - `direction`: 변화 방향 필터 (up / down / all)
    - `code`, `sector`, `target_period`: 선택적 필터
    """
    rows = _build_revision_rows(db)

    results = []
    for r in rows:
        op = _calc_revision(r[6], r[7])   # operating_profit
        ni = _calc_revision(r[8], r[9])   # net_income
        sl = _calc_revision(r[10], r[11])  # sales
        ep = _calc_revision(r[12], r[13])  # eps

        # 방향 필터: 지정된 지표의 direction 으로 판단
        sort_metric_map = {
            "op": op["direction"],
            "ni": ni["direction"],
            "sales": sl["direction"],
            "eps": ep["direction"],
        }
        item_direction = sort_metric_map.get(sort_by, op["direction"])

        if direction and direction != "all" and item_direction != direction:
            continue
        if code and r[0] != code:
            continue
        if sector and r[4] != sector:
            continue
        if target_period and r[3] != target_period:
            continue

        results.append({
            "code": r[0],
            "name": r[1],
            "date": r[2],
            "target_period": r[3],
            "sector": r[4],
            "current_price": r[5],
            "operating_profit": RevisionMetricItem(**op),
            "net_income": RevisionMetricItem(**ni),
            "sales": RevisionMetricItem(**sl),
            "eps": RevisionMetricItem(**ep),
            "rev_1m": r[14],
            "rev_3m": r[15],
            "updated_at": r[16],
        })

    # 정렬: 지정된 지표의 change_pct 절댓값 기준 내림차순
    sort_key_map = {
        "op": lambda x: abs(x["operating_profit"].change_pct or 0),
        "ni": lambda x: abs(x["net_income"].change_pct or 0),
        "sales": lambda x: abs(x["sales"].change_pct or 0),
        "eps": lambda x: abs(x["eps"].change_pct or 0),
        "rev_1m": lambda x: abs(x["rev_1m"] or 0),
        "rev_3m": lambda x: abs(x["rev_3m"] or 0),
    }
    key_fn = sort_key_map.get(sort_by, sort_key_map["op"])
    results.sort(key=key_fn, reverse=True)

    return results[offset : offset + limit]


@router.get("/revision/1d/summary", response_model=Consensus1DRevisionSummaryResponse)
@router.get("/revision/1d/summary/", response_model=Consensus1DRevisionSummaryResponse)
async def get_1d_revision_summary(db: Session = Depends(get_reports_db)):
    """
    **1D 리비전 요약**: 당일 전체 변화 건수 및 평균 변화율을 집계한다.
    """
    rows = _build_revision_rows(db)

    if not rows:
        return {
            "latest_date": datetime.now(),
            "previous_date": None,
            "total_stocks": 0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "avg_op_revision": None,
            "avg_ni_revision": None,
            "avg_sales_revision": None,
            "avg_eps_revision": None,
        }

    op_changes, ni_changes, sales_changes, eps_changes = [], [], [], []
    up = down = flat = 0

    for r in rows:
        op = _calc_revision(r[6], r[7])
        ni = _calc_revision(r[8], r[9])

        op_changes.append(op["change_pct"])
        ni_changes.append(ni["change_pct"])
        sales_changes.append(_calc_revision(r[10], r[11])["change_pct"])
        eps_changes.append(_calc_revision(r[12], r[13])["change_pct"])

        # 영업이익 변화 기준 up/down/flat 판정
        if op["direction"] == "up":
            up += 1
        elif op["direction"] == "down":
            down += 1
        else:
            flat += 1

    def _avg(vals):
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "latest_date": rows[0][2],
        "previous_date": None,  # 추후 개별 쿼리로 채울 수도 있음
        "total_stocks": len(rows),
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "avg_op_revision": _avg(op_changes),
        "avg_ni_revision": _avg(ni_changes),
        "avg_sales_revision": _avg(sales_changes),
        "avg_eps_revision": _avg(eps_changes),
    }
