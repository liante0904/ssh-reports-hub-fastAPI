from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import MarketSentimentDailySnapshot, MarketSentimentIndicator, MarketSentimentSnapshot
from ..schemas import (
    CNNFearGreedIndicatorResponse,
    CNNFearGreedDailySnapshotResponse,
    CNNFearGreedLatestResponse,
    CNNFearGreedSnapshotResponse,
)
from ..services.cnn_fear_greed import fetch_cnn_fear_greed_snapshot, to_json

KST = timezone(timedelta(hours=9))

router = APIRouter(prefix="/sentiment/cnn", tags=["cnn-sentiment"])
api_router = APIRouter(prefix="/api/sentiment/cnn", tags=["cnn-sentiment"], include_in_schema=False)


def _to_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _to_snapshot_date(value: datetime):
    return _to_kst(value).date()


def _upsert_live_indicator_rows(db: Session, snapshot: dict) -> None:
    for key, item in snapshot["indicators"].items():
        row = db.query(MarketSentimentIndicator).filter(MarketSentimentIndicator.key == key).first()
        if not row:
            row = MarketSentimentIndicator(
                key=key,
                title=item["title"],
                category="cnn",
                description=f"CNN Fear & Greed: {item['title']}",
                value=item["score"],
                unit="pt",
                score=item["score"],
                status=item["rating"],
                source="cnn",
                sort_order=len(snapshot["indicators"]),
            )
            db.add(row)
            continue

        row.title = item["title"]
        row.category = "cnn"
        row.description = f"CNN Fear & Greed: {item['title']}"
        row.value = item["score"]
        row.unit = "pt"
        row.score = item["score"]
        row.status = item["rating"]
        row.source = "cnn"


def _store_snapshot(db: Session, snapshot: dict) -> MarketSentimentSnapshot:
    existing = db.query(MarketSentimentSnapshot).filter(
        MarketSentimentSnapshot.source == "cnn",
        MarketSentimentSnapshot.snapshot_ts == snapshot["timestamp"],
    ).first()

    history_json = to_json(snapshot["history"])
    indicators_json = to_json(snapshot["indicators"])
    raw_json = to_json(snapshot["raw"])

    if existing:
        existing.score = snapshot["score"]
        existing.rating = snapshot["rating"]
        existing.history_json = history_json
        existing.indicators_json = indicators_json
        existing.raw_json = raw_json
        db.commit()
        db.refresh(existing)
        return existing

    record = MarketSentimentSnapshot(
        source="cnn",
        snapshot_ts=snapshot["timestamp"],
        score=snapshot["score"],
        rating=snapshot["rating"],
        history_json=history_json,
        indicators_json=indicators_json,
        raw_json=raw_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _store_daily_snapshot(db: Session, snapshot: dict) -> MarketSentimentDailySnapshot:
    snapshot_date = _to_snapshot_date(snapshot["timestamp"])
    existing = db.query(MarketSentimentDailySnapshot).filter(
        MarketSentimentDailySnapshot.source == "cnn",
        MarketSentimentDailySnapshot.snapshot_date == snapshot_date,
    ).first()

    history_json = to_json(snapshot["history"])
    indicators_json = to_json(snapshot["indicators"])
    raw_json = to_json(snapshot["raw"])

    if existing:
        existing.snapshot_ts = snapshot["timestamp"]
        existing.score = snapshot["score"]
        existing.rating = snapshot["rating"]
        existing.history_json = history_json
        existing.indicators_json = indicators_json
        existing.raw_json = raw_json
        db.commit()
        db.refresh(existing)
        return existing

    record = MarketSentimentDailySnapshot(
        source="cnn",
        snapshot_date=snapshot_date,
        snapshot_ts=snapshot["timestamp"],
        score=snapshot["score"],
        rating=snapshot["rating"],
        history_json=history_json,
        indicators_json=indicators_json,
        raw_json=raw_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _snapshot_to_response(row: MarketSentimentSnapshot) -> CNNFearGreedSnapshotResponse:
    snapshot_ts = _to_kst(row.snapshot_ts)
    fetched_at = _to_kst(row.fetched_at)

    return CNNFearGreedSnapshotResponse(
        id=row.id,
        source=row.source,
        snapshot_ts=snapshot_ts,
        score=row.score,
        rating=row.rating,
        history=json.loads(row.history_json or "{}"),
        indicators={
            key: CNNFearGreedIndicatorResponse(**value)
            for key, value in json.loads(row.indicators_json or "{}").items()
        },
        fetched_at=fetched_at,
    )


def _daily_snapshot_to_response(row: MarketSentimentDailySnapshot) -> CNNFearGreedDailySnapshotResponse:
    snapshot_ts = _to_kst(row.snapshot_ts)
    fetched_at = _to_kst(row.fetched_at)

    return CNNFearGreedDailySnapshotResponse(
        id=row.id,
        source=row.source,
        snapshot_date=row.snapshot_date.isoformat(),
        snapshot_ts=snapshot_ts,
        score=row.score,
        rating=row.rating,
        history=json.loads(row.history_json or "{}"),
        indicators={
            key: CNNFearGreedIndicatorResponse(**value)
            for key, value in json.loads(row.indicators_json or "{}").items()
        },
        fetched_at=fetched_at,
    )


@router.get("/latest", response_model=CNNFearGreedLatestResponse)
@router.get("/latest/", response_model=CNNFearGreedLatestResponse)
async def get_latest_cnn_fear_greed():
    try:
        snapshot = fetch_cnn_fear_greed_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch CNN Fear & Greed data: {exc}") from exc

    return CNNFearGreedLatestResponse(
        score=snapshot["score"],
        rating=snapshot["rating"],
        timestamp=snapshot["timestamp"],
        history=snapshot["history"],
        indicators={
            key: CNNFearGreedIndicatorResponse(**value)
            for key, value in snapshot["indicators"].items()
        },
    )


@router.post("/sync", response_model=CNNFearGreedSnapshotResponse)
@router.post("/sync/", response_model=CNNFearGreedSnapshotResponse)
async def sync_cnn_fear_greed(db: Session = Depends(get_reports_db)):
    try:
        snapshot = fetch_cnn_fear_greed_snapshot()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch CNN Fear & Greed data: {exc}") from exc

    _upsert_live_indicator_rows(db, snapshot)
    row = _store_snapshot(db, snapshot)
    _store_daily_snapshot(db, snapshot)
    return _snapshot_to_response(row)


@router.get("/history", response_model=list[CNNFearGreedSnapshotResponse])
@router.get("/history/", response_model=list[CNNFearGreedSnapshotResponse])
async def get_cnn_fear_greed_history(
    limit: int = Query(default=30, ge=1, le=200),
    source: Optional[str] = Query(default="cnn"),
    db: Session = Depends(get_reports_db),
):
    query = db.query(MarketSentimentSnapshot).order_by(MarketSentimentSnapshot.snapshot_ts.desc())
    if source:
        query = query.filter(MarketSentimentSnapshot.source == source)
    rows = query.limit(limit).all()
    return [_snapshot_to_response(row) for row in rows]


@router.get("/daily", response_model=list[CNNFearGreedDailySnapshotResponse])
@router.get("/daily/", response_model=list[CNNFearGreedDailySnapshotResponse])
async def get_cnn_fear_greed_daily_history(
    limit: int = Query(default=30, ge=1, le=365),
    source: Optional[str] = Query(default="cnn"),
    db: Session = Depends(get_reports_db),
):
    query = db.query(MarketSentimentDailySnapshot).order_by(MarketSentimentDailySnapshot.snapshot_date.desc())
    if source:
        query = query.filter(MarketSentimentDailySnapshot.source == source)
    rows = query.limit(limit).all()

    if not rows and source:
        snapshot_rows = (
            db.query(MarketSentimentSnapshot)
            .filter(MarketSentimentSnapshot.source == source)
            .order_by(MarketSentimentSnapshot.snapshot_ts.asc())
            .all()
        )
        if snapshot_rows:
            deduped: dict[str, MarketSentimentSnapshot] = {}
            for row in snapshot_rows:
                deduped[_to_snapshot_date(row.snapshot_ts).isoformat()] = row
            for row in deduped.values():
                _store_daily_snapshot(
                    db,
                    {
                        "timestamp": _to_kst(row.snapshot_ts),
                        "score": row.score,
                        "rating": row.rating,
                        "history": json.loads(row.history_json or "{}"),
                        "indicators": json.loads(row.indicators_json or "{}"),
                        "raw": json.loads(row.raw_json or "{}"),
                    },
                )
            rows = query.limit(limit).all()

    return [_daily_snapshot_to_response(row) for row in rows]


@api_router.get("/latest", response_model=CNNFearGreedLatestResponse)
@api_router.get("/latest/", response_model=CNNFearGreedLatestResponse)
async def get_latest_cnn_fear_greed_api():
    return await get_latest_cnn_fear_greed()


@api_router.post("/sync", response_model=CNNFearGreedSnapshotResponse)
@api_router.post("/sync/", response_model=CNNFearGreedSnapshotResponse)
async def sync_cnn_fear_greed_api(db: Session = Depends(get_reports_db)):
    return await sync_cnn_fear_greed(db)


@api_router.get("/history", response_model=list[CNNFearGreedSnapshotResponse])
@api_router.get("/history/", response_model=list[CNNFearGreedSnapshotResponse])
async def get_cnn_fear_greed_history_api(
    limit: int = Query(default=30, ge=1, le=200),
    source: Optional[str] = Query(default="cnn"),
    db: Session = Depends(get_reports_db),
):
    return await get_cnn_fear_greed_history(limit=limit, source=source, db=db)


@api_router.get("/daily", response_model=list[CNNFearGreedDailySnapshotResponse])
@api_router.get("/daily/", response_model=list[CNNFearGreedDailySnapshotResponse])
async def get_cnn_fear_greed_daily_history_api(
    limit: int = Query(default=30, ge=1, le=365),
    source: Optional[str] = Query(default="cnn"),
    db: Session = Depends(get_reports_db),
):
    return await get_cnn_fear_greed_daily_history(limit=limit, source=source, db=db)
