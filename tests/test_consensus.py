from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db
from app.main import app
from app.models import ConsensusHistory


@pytest.fixture
async def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all(
        [
            ConsensusHistory(
                code="0001",
                name="Alpha",
                date=datetime(2026, 4, 28, 9, 0, 0),
                target_period="2026/12",
                operating_profit=100.0,
                net_income=80.0,
                sales=300.0,
                eps=1.5,
                updated_at=datetime(2026, 4, 28, 9, 5, 0),
            ),
            ConsensusHistory(
                code="0001",
                name="Alpha",
                date=datetime(2026, 4, 29, 9, 0, 0),
                target_period="2026/12",
                operating_profit=150.0,
                net_income=90.0,
                sales=330.0,
                eps=1.8,
                updated_at=datetime(2026, 4, 29, 9, 5, 0),
            ),
            ConsensusHistory(
                code="0002",
                name="Beta",
                date=datetime(2026, 4, 28, 9, 0, 0),
                target_period="2026/12",
                operating_profit=200.0,
                net_income=150.0,
                sales=500.0,
                eps=2.2,
                updated_at=datetime(2026, 4, 28, 9, 5, 0),
            ),
            ConsensusHistory(
                code="0002",
                name="Beta",
                date=datetime(2026, 4, 29, 9, 0, 0),
                target_period="2026/12",
                operating_profit=160.0,
                net_income=120.0,
                sales=520.0,
                eps=2.0,
                updated_at=datetime(2026, 4, 29, 9, 5, 0),
            ),
            ConsensusHistory(
                code="0003",
                name="Gamma",
                date=datetime(2026, 4, 29, 9, 0, 0),
                target_period="2026/12",
                operating_profit=70.0,
                net_income=60.0,
                sales=180.0,
                eps=0.9,
                updated_at=datetime(2026, 4, 29, 9, 5, 0),
            ),
        ]
    )
    db.commit()
    db.close()

    async def override_get_reports_db():
        test_db = TestingSessionLocal()
        try:
            yield test_db
        finally:
            test_db.close()

    app.dependency_overrides[get_reports_db] = override_get_reports_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_consensus_latest_returns_latest_date_rows_sorted_by_revision(client):
    response = await client.get("/consensus/latest")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["code"] == "0001"
    assert data[0]["operating_profit_revision"] == 50.0
    assert data[0]["net_income_revision"] == 12.5
    assert data[1]["code"] == "0002"
    assert data[1]["operating_profit_revision"] == -20.0
    assert data[2]["code"] == "0003"
    assert data[2]["operating_profit_revision"] == 0.0


@pytest.mark.anyio
async def test_consensus_latest_supports_code_filter(client):
    response = await client.get("/consensus/latest", params={"code": "0002"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["code"] == "0002"
    assert data[0]["sales_revision"] == 4.0


@pytest.mark.anyio
async def test_consensus_history_returns_time_series_for_code(client):
    response = await client.get("/consensus/history", params={"code": "0001"})

    assert response.status_code == 200
    data = response.json()
    # 4/28, 4/29 두 개의 데이터가 날짜 오름차순으로 와야 함
    assert len(data) == 2
    assert "2026-04-28" in data[0]["date"]
    assert "2026-04-29" in data[1]["date"]
    assert data[0]["operating_profit"] == 100.0
    assert data[1]["operating_profit"] == 150.0


@pytest.mark.anyio
async def test_consensus_history_requires_code(client):
    response = await client.get("/consensus/history")
    assert response.status_code == 422  # Validation Error
