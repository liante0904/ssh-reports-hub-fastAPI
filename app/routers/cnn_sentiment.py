from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import MarketSentimentIndicator, MarketSentimentSnapshot
from ..schemas import (
    CNNFearGreedIndicatorResponse,
    CNNFearGreedLatestResponse,
    CNNFearGreedSnapshotResponse,
)
from ..services.cnn_fear_greed import fetch_cnn_fear_greed_snapshot, to_json

router = APIRouter(prefix="/sentiment/cnn", tags=["cnn-sentiment"])
api_router = APIRouter(prefix="/api/sentiment/cnn", tags=["cnn-sentiment"], include_in_schema=False)


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


def _snapshot_to_response(row: MarketSentimentSnapshot) -> CNNFearGreedSnapshotResponse:
    return CNNFearGreedSnapshotResponse(
        id=row.id,
        source=row.source,
        snapshot_ts=row.snapshot_ts,
        score=row.score,
        rating=row.rating,
        history=json.loads(row.history_json or "{}"),
        indicators={
            key: CNNFearGreedIndicatorResponse(**value)
            for key, value in json.loads(row.indicators_json or "{}").items()
        },
        fetched_at=row.fetched_at,
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
