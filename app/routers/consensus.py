from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_reports_db
from ..models import ConsensusHistory
from ..schemas import ConsensusResponse, ConsensusHistoryResponse, ConsensusSummaryResponse, ConsensusSectorResponse

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
