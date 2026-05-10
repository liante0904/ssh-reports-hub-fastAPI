import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_reports_db, get_keywords_db, Base
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
