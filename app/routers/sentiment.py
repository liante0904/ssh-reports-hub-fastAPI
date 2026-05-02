from __future__ import annotations

from datetime import datetime
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from ..database import get_reports_db
from ..models import MarketSentimentIndicator
from ..schemas import MarketSentimentIndicatorResponse, MarketSentimentSummaryResponse

router = APIRouter(prefix="/sentiment", tags=["sentiment"])
api_router = APIRouter(prefix="/api/sentiment", tags=["sentiment"], include_in_schema=False)

MOCK_SENTIMENT_INDICATORS = [
    {
        "key": "fear_greed_index",
        "title": "Fear & Greed Index",
        "category": "overheat",
        "description": "종합 시장 탐욕 지수입니다.",
        "value": 81.0,
        "unit": "pt",
        "score": 81.0,
        "status": "greed",
        "source": "mock",
        "sort_order": 1,
    },
    {
        "key": "vix_percentile",
        "title": "VIX Percentile",
        "category": "volatility",
        "description": "최근 변동성의 상대적 위치입니다.",
        "value": 74.0,
        "unit": "pt",
        "score": 74.0,
        "status": "elevated",
        "source": "mock",
        "sort_order": 2,
    },
    {
        "key": "breadth_ratio",
        "title": "상승/하락 종목 비율",
        "category": "breadth",
        "description": "시장의 확산 강도를 보여줍니다.",
        "value": 63.0,
        "unit": "%",
        "score": 63.0,
        "status": "neutral",
        "source": "mock",
        "sort_order": 3,
    },
    {
        "key": "funding_heat",
        "title": "펀딩비 과열도",
        "category": "leverage",
        "description": "선물 레버리지 쏠림을 반영합니다.",
        "value": 88.0,
        "unit": "pt",
        "score": 88.0,
        "status": "overheated",
        "source": "mock",
        "sort_order": 4,
    },
    {
        "key": "extreme_ratio",
        "title": "52주 극단값 비중",
        "category": "trend",
        "description": "신고가/신저가 쏠림을 나타냅니다.",
        "value": 70.0,
        "unit": "%",
        "score": 70.0,
        "status": "hot",
        "source": "mock",
        "sort_order": 5,
    },
]


def seed_mock_sentiment_indicators(engine) -> None:
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_factory() as db:
        if db.query(func.count(MarketSentimentIndicator.id)).scalar() or 0:
            return

        db.add_all(MarketSentimentIndicator(**item) for item in MOCK_SENTIMENT_INDICATORS)
        db.commit()


def _fetch_indicators(db: Session, source: Optional[str] = None):
    query = db.query(MarketSentimentIndicator)
    if source:
        query = query.filter(MarketSentimentIndicator.source == source)
    else:
        has_cnn_rows = db.query(MarketSentimentIndicator.id).filter(MarketSentimentIndicator.source == "cnn").first()
        if has_cnn_rows:
            query = query.filter(MarketSentimentIndicator.source == "cnn")

    return query.order_by(MarketSentimentIndicator.sort_order.asc(), MarketSentimentIndicator.id.asc()).all()


def _summary_payload(rows):
    if not rows:
        return {
            "composite_score": 0.0,
            "status_label": "데이터 없음",
            "overheat_count": 0,
            "neutral_count": 0,
            "fear_count": 0,
            "latest_update": datetime.now(),
        }

    scores = [float(row.score or 0.0) for row in rows]
    composite_score = round(mean(scores), 1)
    overheat_count = sum(1 for score in scores if score >= 70)
    neutral_count = sum(1 for score in scores if 40 <= score < 70)
    fear_count = sum(1 for score in scores if score < 40)
    latest_update = max(row.updated_at for row in rows if row.updated_at is not None)

    if composite_score >= 80:
        status_label = "강한 과열"
    elif composite_score >= 65:
        status_label = "과열 주의"
    elif composite_score >= 35:
        status_label = "중립"
    else:
        status_label = "공포"

    return {
        "composite_score": composite_score,
        "status_label": status_label,
        "overheat_count": overheat_count,
        "neutral_count": neutral_count,
        "fear_count": fear_count,
        "latest_update": latest_update,
    }


@router.get("", response_model=list[MarketSentimentIndicatorResponse])
@router.get("/", response_model=list[MarketSentimentIndicatorResponse])
async def get_sentiment_indicators(db: Session = Depends(get_reports_db)):
    return _fetch_indicators(db)


@api_router.get("", response_model=list[MarketSentimentIndicatorResponse])
@api_router.get("/", response_model=list[MarketSentimentIndicatorResponse])
async def get_sentiment_indicators_api(db: Session = Depends(get_reports_db)):
    return _fetch_indicators(db)


@router.get("/summary", response_model=MarketSentimentSummaryResponse)
@router.get("/summary/", response_model=MarketSentimentSummaryResponse)
async def get_sentiment_summary(db: Session = Depends(get_reports_db)):
    rows = _fetch_indicators(db)
    return _summary_payload(rows)


@api_router.get("/summary", response_model=MarketSentimentSummaryResponse)
@api_router.get("/summary/", response_model=MarketSentimentSummaryResponse)
async def get_sentiment_summary_api(db: Session = Depends(get_reports_db)):
    rows = _fetch_indicators(db)
    return _summary_payload(rows)
