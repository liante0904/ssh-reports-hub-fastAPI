import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_reports_db, Base

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


@pytest.mark.anyio
async def test_invalid_telegram_auth_logic(client):
    """인증 로직 검증 (모킹된 환경)"""
    invalid_user = {
        "id": 9999,
        "first_name": "MockUser",
        "auth_date": 12345678,
        "hash": "wrong_hash"
    }
    response = await client.post("/auth/telegram", json=invalid_user)
    assert response.status_code == 401
    assert "Telegram Auth Failed" in response.json()["detail"]
