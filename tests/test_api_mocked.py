import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_reports_db, get_keywords_db, Base
from app.models import FnGuideReportSummary
from app.dependencies import get_settings_dep
from app.security import verify_telegram_data
from app.settings import Settings

# 테스트용 SQLite 메모리 DB 설정
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


@pytest.mark.anyio
async def test_health_check_mocked(client):
    """DB 없이도 동작하는 헬스 체크 테스트"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_get_reports_empty_db(client):
    """빈 DB에서의 리포트 조회 테스트"""
    response = await client.get("/reports?limit=5")
    assert response.status_code == 200
    assert response.json() == []


def test_invalid_telegram_auth_logic():
    """인증 로직 검증은 라우트 대신 순수 함수로 빠르게 확인한다."""
    invalid_user = {
        "id": 9999,
        "first_name": "MockUser",
        "auth_date": 12345678,
        "hash": "wrong_hash"
    }
    settings = Settings(
        app_env="prod",
        jwt_secret_key="x" * 32,
        telegram_bot_token="dummy-token",
        allow_auth_bypass=False,
    )
    is_valid, reason = verify_telegram_data(invalid_user, settings)
    assert is_valid is False
    assert reason in {"Telegram auth data is expired", "Telegram signature mismatch"}


def seed_fnguide_reports(rows):
    db = TestingSessionLocal()
    try:
        for row in rows:
            db.add(FnGuideReportSummary(**row))
        db.commit()
    finally:
        db.close()


@pytest.mark.anyio
async def test_fnguide_report_summaries_support_report_date_filter(client):
    seed_fnguide_reports([
        {
            "summary_id": 1,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-02",
            "company_name": "Alpha",
            "company_code": "000001",
            "report_title": "Alpha update",
            "summary_text": "Alpha summary",
            "opinion": "Buy",
            "target_price": "100,000",
            "prev_close": "90,000",
            "provider": "FnGuide",
            "author": "Alice",
            "article_url": "https://example.com/a",
            "pdf_url": "",
            "report_key": "fnguide:1",
            "item_rank": 1,
            "sync_status": 1,
        },
        {
            "summary_id": 2,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-02",
            "company_name": "Beta",
            "company_code": "000002",
            "report_title": "Beta update",
            "summary_text": "Beta summary",
            "opinion": "Hold",
            "target_price": "20,000",
            "prev_close": "18,000",
            "provider": "FnGuide",
            "author": "Bob",
            "article_url": "https://example.com/b",
            "pdf_url": "",
            "report_key": "fnguide:2",
            "item_rank": 2,
            "sync_status": 1,
        },
        {
            "summary_id": 3,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-01",
            "company_name": "Gamma",
            "company_code": "000003",
            "report_title": "Gamma update",
            "summary_text": "Gamma summary",
            "opinion": "Sell",
            "target_price": "5,000",
            "prev_close": "6,000",
            "provider": "Other",
            "author": "Carol",
            "article_url": "https://example.com/c",
            "pdf_url": "",
            "report_key": "fnguide:3",
            "item_rank": 3,
            "sync_status": 1,
        },
    ])

    response = await client.get("/pub/api/fnguide/report-summaries?report_date=2026-05-02&limit=100")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {item["report_date"] for item in payload} == {"2026-05-02"}
    assert [item["summary_id"] for item in payload] == [2, 1]


@pytest.mark.anyio
async def test_fnguide_report_dates_group_by_day(client):
    seed_fnguide_reports([
        {
            "summary_id": 11,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-02",
            "company_name": "Alpha",
            "company_code": "000001",
            "report_title": "Alpha update",
            "summary_text": "Alpha summary",
            "provider": "FnGuide",
            "author": "Alice",
            "article_url": "https://example.com/a",
            "pdf_url": "",
            "report_key": "fnguide:11",
            "sync_status": 1,
        },
        {
            "summary_id": 12,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-02",
            "company_name": "Beta",
            "company_code": "000002",
            "report_title": "Beta update",
            "summary_text": "Beta summary",
            "provider": "FnGuide",
            "author": "Bob",
            "article_url": "https://example.com/b",
            "pdf_url": "",
            "report_key": "fnguide:12",
            "sync_status": 1,
        },
        {
            "summary_id": 13,
            "source_page_url": "https://example.com/list",
            "report_date": "2026-05-01",
            "company_name": "Gamma",
            "company_code": "000003",
            "report_title": "Gamma update",
            "summary_text": "Gamma summary",
            "provider": "Other",
            "author": "Carol",
            "article_url": "https://example.com/c",
            "pdf_url": "",
            "report_key": "fnguide:13",
            "sync_status": 1,
        },
    ])

    response = await client.get("/pub/api/fnguide/report-dates")
    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {"report_date": "2026-05-02", "report_count": 2},
        {"report_date": "2026-05-01", "report_count": 1},
    ]
