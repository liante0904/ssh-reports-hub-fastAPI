import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db, Base

# 테스트용 SQLite 메모리 DB 설정
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 테스트 전 테이블 생성
Base.metadata.create_all(bind=engine)

# DB 의존성 주입을 테스트용 DB로 교체
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_health_check_mocked():
    """DB 없이도 동작하는 헬스 체크 테스트"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_reports_empty_db():
    """빈 DB에서의 리포트 조회 테스트"""
    response = client.get("/reports?limit=5")
    assert response.status_code == 200
    assert response.json() == []

def test_invalid_telegram_auth_logic():
    """인증 로직 검증 (모킹된 환경)"""
    invalid_user = {
        "id": 9999,
        "first_name": "MockUser",
        "auth_date": 12345678,
        "hash": "wrong_hash"
    }
    response = client.post("/auth/telegram", json=invalid_user)
    assert response.status_code == 401
    assert "Telegram Auth Failed" in response.json()["detail"]
