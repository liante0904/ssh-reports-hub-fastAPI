import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db
from app.main import app
from app.models import SecReport


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
            SecReport(
                report_id=300,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260421",
                article_title="디스플레이 패널가",
                main_ch_send_yn="Y",
                writer="김선우",
                mkt_tp="KR",
                save_time="21-APR-26",
            ),
            SecReport(
                report_id=200,
                sec_firm_order=4,
                article_board_order=0,
                firm_nm="KB증권",
                reg_dt="20260420",
                article_title="Global Insights",
                main_ch_send_yn="Y",
                writer="김일혁",
                mkt_tp="US",
                save_time="20-APR-26",
            ),
            SecReport(
                report_id=100,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260419",
                article_title="미발송 산업",
                main_ch_send_yn="N",
                writer="김선우",
                mkt_tp="KR",
                save_time="19-APR-26",
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
async def test_ords_industry_uses_existing_filter_and_response_shape(client):
    response = await client.get("/ords/admin/data_main_daily_send/industry")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["hasMore"] is False
    assert data["items"][0]["report_id"] == 300
    assert data["items"][0]["sec_firm_order"] == 20
    assert data["items"][0]["article_board_order"] == 1
    assert data["items"][0]["main_ch_send_yn"] == "Y"


@pytest.mark.anyio
async def test_ords_industry_accepts_legacy_search_filters(client):
    response = await client.get(
        "/ords/admin/data_main_daily_send/industry",
        params={"writer": "김선우", "title": "디스플레이", "mkt_tp": "domestic", "company": 20},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 300


@pytest.mark.anyio
async def test_ords_industry_filters_out_non_matching_writer(client):
    response = await client.get(
        "/ords/admin/data_main_daily_send/industry",
        params={"writer": "없는작성자"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.anyio
async def test_ords_search_filters_like_legacy_endpoint(client):
    response = await client.get(
        "/ords/admin/data_main_daily_send/search/",
        params={"title": "Global", "mkt_tp": "global", "company": 4},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 200
    assert data["items"][0]["mkt_tp"] == "US"


@pytest.mark.anyio
async def test_ords_search_report_id_share_filter(client):
    response = await client.get(
        "/ords/admin/data_main_daily_send/search/",
        params={"report_id": 300},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["article_title"] == "디스플레이 패널가"
