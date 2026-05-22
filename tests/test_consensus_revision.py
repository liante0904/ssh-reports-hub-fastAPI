"""1D Revision API 테스트"""
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db, get_keywords_db
from app.dependencies import get_settings_dep
from app.main import app
from app.models import ConsensusHistory
from app.settings import Settings

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
async def client():
    app.dependency_overrides[get_reports_db] = override_get_db
    app.dependency_overrides[get_keywords_db] = override_get_db
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        app_env="prod",
        jwt_secret_key="x" * 32,
        telegram_bot_token="dummy-token",
        allow_auth_bypass=False,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_consensus(revision_db):
    """이틀치 컨센서스 데이터를 심는다."""
    today = datetime(2025, 6, 20)
    yesterday = datetime(2025, 6, 19)

    stocks = [
        # code, name, sector, operating_profit(today/yesterday), net_income, sales, eps
        ("005930", "삼성전자", "전기전자", 6_500_000_000_000, 6_200_000_000_000, 5_000_000_000_000, 4_800_000_000_000, 80_000_000_000_000, 78_000_000_000_000, 4_500, 4_300),
        ("000660", "SK하이닉스", "전기전자", 3_200_000_000_000, 3_500_000_000_000, 2_800_000_000_000, 3_000_000_000_000, 30_000_000_000_000, 31_000_000_000_000, 8_000, 8_500),
        ("035720", "카카오", "서비스", 500_000_000_000, 500_000_000_000, 300_000_000_000, 300_000_000_000, 5_000_000_000_000, 5_000_000_000_000, 1_200, 1_200),
    ]

    for code, name, sector, op_t, op_y, ni_t, ni_y, sales_t, sales_y, eps_t, eps_y in stocks:
        for date, op_val, ni_val, sales_val, eps_val in [
            (yesterday, op_y, ni_y, sales_y, eps_y),
            (today, op_t, ni_t, sales_t, eps_t),
        ]:
            revision_db.add(ConsensusHistory(
                code=code,
                date=date,
                target_period="2026E",
                name=name,
                sector=sector,
                current_price=75000 if code == "005930" else 200000,
                operating_profit=op_val,
                net_income=ni_val,
                sales=sales_val,
                eps=eps_val,
                rev_1m=3.5 if code == "005930" else (-2.1 if code == "000660" else 0.0),
                rev_3m=8.2,
            ))
    revision_db.commit()


@pytest.mark.anyio
async def test_1d_revision_returns_revision_data(client):
    db = TestingSessionLocal()
    _seed_consensus(db)

    response = await client.get("/consensus/revision/1d")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # 삼성전자: 영업이익 상향 (6500 vs 6200) → up
    samsung = next(r for r in data if r["code"] == "005930")
    assert samsung["operating_profit"]["direction"] == "up"
    assert samsung["operating_profit"]["today"] == 6_500_000_000_000
    assert samsung["operating_profit"]["yesterday"] == 6_200_000_000_000
    assert samsung["operating_profit"]["change_pct"] == pytest.approx(4.84, rel=0.01)

    # SK하이닉스: 영업이익 하향 (3200 vs 3500) → down
    sk = next(r for r in data if r["code"] == "000660")
    assert sk["operating_profit"]["direction"] == "down"
    assert sk["operating_profit"]["change_pct"] == pytest.approx(-8.57, rel=0.01)

    # 카카오: 변화 없음 → flat
    kakao = next(r for r in data if r["code"] == "035720")
    assert kakao["operating_profit"]["direction"] == "flat"
    assert kakao["operating_profit"]["change_pct"] == 0.0

    db.close()


@pytest.mark.anyio
async def test_1d_revision_direction_filter(client):
    db = TestingSessionLocal()
    _seed_consensus(db)

    # up only
    resp = await client.get("/consensus/revision/1d?direction=up")
    assert resp.status_code == 200
    data = resp.json()
    codes = [r["code"] for r in data]
    assert "005930" in codes
    assert "000660" not in codes  # down
    assert "035720" not in codes  # flat

    # down only
    resp = await client.get("/consensus/revision/1d?direction=down")
    data = resp.json()
    codes = [r["code"] for r in data]
    assert "000660" in codes

    db.close()


@pytest.mark.anyio
async def test_1d_revision_code_filter(client):
    db = TestingSessionLocal()
    _seed_consensus(db)

    resp = await client.get("/consensus/revision/1d?code=005930")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["code"] == "005930"

    db.close()


@pytest.mark.anyio
async def test_1d_revision_summary(client):
    db = TestingSessionLocal()
    _seed_consensus(db)

    resp = await client.get("/consensus/revision/1d/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_stocks"] == 3
    assert data["up_count"] == 1    # 삼성전자
    assert data["down_count"] == 1   # SK하이닉스
    assert data["flat_count"] == 1   # 카카오
    assert data["avg_op_revision"] is not None
    assert data["avg_ni_revision"] is not None
    assert "latest_date" in data
    assert "previous_date" in data

    db.close()


@pytest.mark.anyio
async def test_1d_revision_sort_by_eps(client):
    db = TestingSessionLocal()
    _seed_consensus(db)

    resp = await client.get("/consensus/revision/1d?sort_by=eps")
    assert resp.status_code == 200
    data = resp.json()
    # EPS 변화율 절댓값 큰 순: SK(-5.88%) > 삼성(+4.65%) > 카카오(0%)
    assert data[0]["code"] == "000660"   # EPS: 8000→8500, -5.88%
    assert data[1]["code"] == "005930"   # EPS: 4500→4300, +4.65%
    assert data[2]["code"] == "035720"   # EPS: flat

    db.close()


@pytest.mark.anyio
async def test_1d_revision_empty_db(client):
    resp = await client.get("/consensus/revision/1d")
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get("/consensus/revision/1d/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_stocks"] == 0
