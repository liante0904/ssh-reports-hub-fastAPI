from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


CNN_INDICATOR_TITLES = {
    "market_momentum_sp500": "Market Momentum",
    "stock_price_strength": "Stock Price Strength",
    "stock_price_breadth": "Stock Price Breadth",
    "put_call_options": "Put/Call Options",
    "market_volatility_vix": "Market Volatility",
    "safe_haven_demand": "Safe Haven Demand",
    "junk_bond_demand": "Junk Bond Demand",
}


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fetch_cnn_fear_greed_snapshot() -> dict[str, Any]:
    import fear_greed

    payload = fear_greed.get()
    timestamp = _parse_timestamp(payload["timestamp"])
    indicators = payload.get("indicators", {})

    normalized_indicators: dict[str, dict[str, Any]] = {}
    for key, data in indicators.items():
        normalized_indicators[key] = {
            "key": key,
            "title": CNN_INDICATOR_TITLES.get(key, key),
            "score": float(data.get("score", 0.0)),
            "rating": str(data.get("rating", "neutral")),
        }

    return {
        "score": float(payload.get("score", 0.0)),
        "rating": str(payload.get("rating", "neutral")),
        "timestamp": timestamp,
        "history": payload.get("history", {}),
        "indicators": normalized_indicators,
        "raw": payload,
    }


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
