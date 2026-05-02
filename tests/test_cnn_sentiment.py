import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.models import MarketSentimentSnapshot
from app.routers import cnn_sentiment


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
async def client(monkeypatch):
    Base.metadata.create_all(bind=engine)

    async def override_get_reports_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_reports_db] = override_get_reports_db
    app.dependency_overrides[get_keywords_db] = override_get_reports_db

    monkeypatch.setattr(
        cnn_sentiment,
        "fetch_cnn_fear_greed_snapshot",
        lambda: {
            "score": 64.2,
            "rating": "neutral",
            "timestamp": __import__("datetime").datetime.fromisoformat("2026-05-01T12:00:00+00:00"),
            "history": {"1w": 60.0, "1m": 58.0, "3m": 55.0, "6m": 53.0, "1y": 50.0},
            "indicators": {
                "market_momentum_sp500": {"key": "market_momentum_sp500", "title": "Market Momentum", "score": 70.0, "rating": "greed"},
                "stock_price_strength": {"key": "stock_price_strength", "title": "Stock Price Strength", "score": 66.0, "rating": "greed"},
                "stock_price_breadth": {"key": "stock_price_breadth", "title": "Stock Price Breadth", "score": 61.0, "rating": "neutral"},
                "put_call_options": {"key": "put_call_options", "title": "Put/Call Options", "score": 48.0, "rating": "neutral"},
                "market_volatility_vix": {"key": "market_volatility_vix", "title": "Market Volatility", "score": 52.0, "rating": "neutral"},
                "safe_haven_demand": {"key": "safe_haven_demand", "title": "Safe Haven Demand", "score": 44.0, "rating": "neutral"},
                "junk_bond_demand": {"key": "junk_bond_demand", "title": "Junk Bond Demand", "score": 58.0, "rating": "neutral"},
            },
            "raw": {
                "score": 64.2,
                "rating": "neutral",
                "timestamp": "2026-05-01T12:00:00+00:00",
                "history": {"1w": 60.0},
                "indicators": {},
            },
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_cnn_latest(client):
    response = await client.get("/sentiment/cnn/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 64.2
    assert data["rating"] == "neutral"
    assert "market_momentum_sp500" in data["indicators"]


@pytest.mark.anyio
async def test_cnn_sync_and_history(client):
    sync_response = await client.post("/sentiment/cnn/sync")
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    assert sync_data["source"] == "cnn"

    history_response = await client.get("/sentiment/cnn/history?limit=5")
    assert history_response.status_code == 200
    history_data = history_response.json()
    assert len(history_data) == 1
    assert history_data[0]["score"] == 64.2

    db = TestingSessionLocal()
    try:
        snapshots = db.query(MarketSentimentSnapshot).all()
        assert len(snapshots) == 1
    finally:
        db.close()
