from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from ..database import get_reports_db
from ..models import DartDisclosure
from ..schemas import DartDisclosureResponse, DartDisclosureSummaryResponse

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/disclosure", tags=["disclosure"])
api_router = APIRouter(prefix="/api/disclosure", tags=["disclosure"], include_in_schema=False)


MOCK_DART_DISCLOSURES = [
    {
        "source": "dart",
        "published_at": datetime(2026, 5, 2, 9, 12, tzinfo=KST),
        "company_name": "삼성전자",
        "company_code": "005930",
        "disclosure_title": "임원 주식매수선택권 행사 및 소유상황 보고",
        "disclosure_type": "임원변동",
        "insider_name": "김민수",
        "insider_role": "부사장",
        "transaction_type": "buy",
        "shares": 15000.0,
        "amount": 1125000000.0,
        "avg_price": 75000.0,
        "ownership_after": 0.012,
        "signal_score": 92.0,
        "summary_text": "경영진의 자기자본 투입 성격의 매수로 해석되는 강한 신호.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260502000123",
        "telegram_url": None,
        "tags_json": json.dumps(["임원", "매수", "반도체"]),
    },
    {
        "source": "dart",
        "published_at": datetime(2026, 5, 2, 8, 44, tzinfo=KST),
        "company_name": "SK하이닉스",
        "company_code": "000660",
        "disclosure_title": "주식등의 대량보유상황보고서",
        "disclosure_type": "특수관계인",
        "insider_name": "최성훈",
        "insider_role": "임원",
        "transaction_type": "buy",
        "shares": 4200.0,
        "amount": 840000000.0,
        "avg_price": 200000.0,
        "ownership_after": 0.009,
        "signal_score": 88.0,
        "summary_text": "실적 모멘텀 구간에서 임원 매수 공시가 나온 케이스.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260502000114",
        "telegram_url": None,
        "tags_json": json.dumps(["임원", "매수", "반도체", "대량보유"]),
    },
    {
        "source": "dart",
        "published_at": datetime(2026, 5, 1, 17, 31, tzinfo=KST),
        "company_name": "네이버",
        "company_code": "035420",
        "disclosure_title": "임원 소유 주식 매수",
        "disclosure_type": "임원변동",
        "insider_name": "정지훈",
        "insider_role": "대표이사",
        "transaction_type": "buy",
        "shares": 2500.0,
        "amount": 530000000.0,
        "avg_price": 212000.0,
        "ownership_after": 0.021,
        "signal_score": 84.0,
        "summary_text": "대표이사 자사주 매수 성격의 공시.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260501000109",
        "telegram_url": None,
        "tags_json": json.dumps(["대표", "매수", "플랫폼"]),
    },
    {
        "source": "dart",
        "published_at": datetime(2026, 5, 1, 14, 25, tzinfo=KST),
        "company_name": "카카오",
        "company_code": "035720",
        "disclosure_title": "임원 보유 주식 일부 처분",
        "disclosure_type": "임원변동",
        "insider_name": "이서연",
        "insider_role": "전무",
        "transaction_type": "sell",
        "shares": 8200.0,
        "amount": 410000000.0,
        "avg_price": 50000.0,
        "ownership_after": 0.004,
        "signal_score": 52.0,
        "summary_text": "단기 차익실현성 매도로 보이는 공시.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260501000088",
        "telegram_url": None,
        "tags_json": json.dumps(["임원", "매도", "플랫폼"]),
    },
    {
        "source": "dart",
        "published_at": datetime(2026, 5, 1, 9, 56, tzinfo=KST),
        "company_name": "LIG넥스원",
        "company_code": "079550",
        "disclosure_title": "임원 지분 취득",
        "disclosure_type": "특수관계인",
        "insider_name": "박준호",
        "insider_role": "상무",
        "transaction_type": "buy",
        "shares": 3500.0,
        "amount": 273000000.0,
        "avg_price": 78000.0,
        "ownership_after": 0.007,
        "signal_score": 79.0,
        "summary_text": "방산 업종 강세와 함께 나타난 지분 취득 공시.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260501000041",
        "telegram_url": None,
        "tags_json": json.dumps(["임원", "매수", "방산"]),
    },
    {
        "source": "dart",
        "published_at": datetime(2026, 4, 30, 16, 7, tzinfo=KST),
        "company_name": "JYP Ent.",
        "company_code": "035900",
        "disclosure_title": "주요주주 소유주식 변동보고",
        "disclosure_type": "주요주주",
        "insider_name": "박진영",
        "insider_role": "대표 프로듀서",
        "transaction_type": "buy",
        "shares": 12000.0,
        "amount": 1440000000.0,
        "avg_price": 120000.0,
        "ownership_after": 0.053,
        "signal_score": 95.0,
        "summary_text": "창업자/대주주 계열의 매수는 시장 신뢰 신호로 해석 가능.",
        "dart_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260430000235",
        "telegram_url": None,
        "tags_json": json.dumps(["대주주", "매수", "엔터"]),
    },
]


def seed_mock_disclosures(engine) -> None:
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_factory() as db:
        if db.query(func.count(DartDisclosure.id)).scalar() or 0:
            return

        db.add_all(DartDisclosure(**item) for item in MOCK_DART_DISCLOSURES)
        db.commit()


def _to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST)


def _parse_tags(tags_json: str) -> list[str]:
    try:
        data = json.loads(tags_json or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _disclosure_to_response(row: DartDisclosure) -> DartDisclosureResponse:
    return DartDisclosureResponse(
        id=row.id,
        source=row.source,
        published_at=_to_kst(row.published_at),
        company_name=row.company_name,
        company_code=row.company_code,
        disclosure_title=row.disclosure_title,
        disclosure_type=row.disclosure_type,
        insider_name=row.insider_name,
        insider_role=row.insider_role,
        transaction_type=row.transaction_type,
        shares=row.shares,
        amount=row.amount,
        avg_price=row.avg_price,
        ownership_after=row.ownership_after,
        signal_score=row.signal_score,
        summary_text=row.summary_text,
        dart_url=row.dart_url,
        telegram_url=row.telegram_url,
        tags=_parse_tags(row.tags_json),
        fetched_at=_to_kst(row.fetched_at),
    )


def _summary_payload(rows: list[DartDisclosure]) -> DartDisclosureSummaryResponse:
    buy_count = sum(1 for row in rows if row.transaction_type == "buy")
    sell_count = sum(1 for row in rows if row.transaction_type == "sell")
    insider_buy_count = sum(
        1 for row in rows
        if row.transaction_type == "buy" and (row.insider_role or "").lower() not in {"", "unknown"}
    )
    executive_buy_count = sum(
        1 for row in rows
        if row.transaction_type == "buy" and any(token in (row.insider_role or "") for token in ["임원", "대표", "사장", "부사장", "전무", "상무", "CEO", "CFO"])
    )
    net_buy_amount = round(
        sum((row.amount or 0.0) if row.transaction_type == "buy" else -(row.amount or 0.0) for row in rows),
        0,
    )
    latest_update = max((_to_kst(row.published_at) for row in rows), default=datetime.now(KST))

    return DartDisclosureSummaryResponse(
        total_count=len(rows),
        buy_count=buy_count,
        sell_count=sell_count,
        insider_buy_count=insider_buy_count,
        executive_buy_count=executive_buy_count,
        net_buy_amount=net_buy_amount,
        latest_update=latest_update,
    )


@router.get("", response_model=list[DartDisclosureResponse])
@router.get("/", response_model=list[DartDisclosureResponse])
async def get_disclosures(
    limit: int = Query(default=30, ge=1, le=200),
    transaction_type: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default="dart"),
    db: Session = Depends(get_reports_db),
):
    query = db.query(DartDisclosure).order_by(DartDisclosure.signal_score.desc(), DartDisclosure.published_at.desc())
    if source:
        query = query.filter(DartDisclosure.source == source)
    if transaction_type:
        query = query.filter(DartDisclosure.transaction_type == transaction_type)
    rows = query.limit(limit).all()
    return [_disclosure_to_response(row) for row in rows]


@router.get("/summary", response_model=DartDisclosureSummaryResponse)
@router.get("/summary/", response_model=DartDisclosureSummaryResponse)
async def get_disclosure_summary(
    source: Optional[str] = Query(default="dart"),
    db: Session = Depends(get_reports_db),
):
    query = db.query(DartDisclosure)
    if source:
        query = query.filter(DartDisclosure.source == source)
    rows = query.order_by(DartDisclosure.signal_score.desc(), DartDisclosure.published_at.desc()).all()
    return _summary_payload(rows)


@api_router.get("", response_model=list[DartDisclosureResponse])
@api_router.get("/", response_model=list[DartDisclosureResponse])
async def get_disclosures_api(
    limit: int = Query(default=30, ge=1, le=200),
    transaction_type: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default="dart"),
    db: Session = Depends(get_reports_db),
):
    return await get_disclosures(limit=limit, transaction_type=transaction_type, source=source, db=db)


@api_router.get("/summary", response_model=DartDisclosureSummaryResponse)
@api_router.get("/summary/", response_model=DartDisclosureSummaryResponse)
async def get_disclosure_summary_api(
    source: Optional[str] = Query(default="dart"),
    db: Session = Depends(get_reports_db),
):
    return await get_disclosure_summary(source=source, db=db)
