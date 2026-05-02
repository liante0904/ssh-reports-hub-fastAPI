from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CNN_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://edition.cnn.com/",
    "Accept": "application/json",
}

KST = timezone(timedelta(hours=9))


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
    return dt.astimezone(KST)


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers=CNN_HEADERS)
    try:
        with urlopen(request, timeout=10) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"CNN request failed with status {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"CNN request failed: {exc.reason}") from exc

    return json.loads(payload)


def fetch_cnn_fear_greed_snapshot() -> dict[str, Any]:
    payload = _fetch_json(CNN_API_URL)
    fear_greed = payload["fear_and_greed"]
    historical_points = payload["fear_and_greed_historical"]["data"]
    timestamp = _parse_timestamp(fear_greed["timestamp"])
    indicators = {
        key: payload.get(key, {})
        for key in (
            "market_momentum_sp500",
            "stock_price_strength",
            "stock_price_breadth",
            "put_call_options",
            "market_volatility_vix",
            "safe_haven_demand",
            "junk_bond_demand",
        )
        if key in payload
    }

    normalized_indicators: dict[str, dict[str, Any]] = {}
    for key, data in indicators.items():
        normalized_indicators[key] = {
            "key": key,
            "title": CNN_INDICATOR_TITLES.get(key, key),
            "score": float(data.get("score", 0.0)),
            "rating": str(data.get("rating", "neutral")),
        }

    def _closest_history_score(days_ago: int) -> float | None:
        target = datetime.now(timezone.utc).timestamp() * 1000 - (days_ago * 24 * 60 * 60 * 1000)
        closest = min(historical_points, key=lambda item: abs(float(item["x"]) - target), default=None)
        return round(float(closest["y"]), 2) if closest else None

    return {
        "score": float(fear_greed.get("score", 0.0)),
        "rating": str(fear_greed.get("rating", "neutral")),
        "timestamp": timestamp,
        "history": {
            "1w": round(float(fear_greed.get("previous_1_week", 0.0)), 2),
            "1m": round(float(fear_greed.get("previous_1_month", 0.0)), 2),
            "3m": _closest_history_score(90),
            "6m": _closest_history_score(180),
            "1y": round(float(fear_greed.get("previous_1_year", 0.0)), 2),
        },
        "indicators": normalized_indicators,
        "raw": payload,
    }


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
