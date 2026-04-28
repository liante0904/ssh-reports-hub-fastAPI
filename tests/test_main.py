import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import get_reports_db, Base
from app.models import SecReport

# 테스트용 SQLite 메모리 DB 설정
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
async def client():
    # 테이블 생성
    Base.metadata.create_all(bind=engine)
    
    # 샘플 데이터 추가
    db = TestingSessionLocal()
    db.add(SecReport(
        report_id=1,
        firm_nm="테스트증권",
        article_title="반도체 산업 전망",
        reg_dt="20260428",
        main_ch_send_yn="Y",
        key="test-key-1"
    ))
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
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_health_check(client):
    """서버 상태 확인 엔드포인트 테스트"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_get_reports_pagination(client):
    """리포트 목록 조회 및 페이지네이션 테스트"""
    # 5개만 가져오기
    response = await client.get("/reports?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5
    
    # 첫 번째 데이터에 필수 필드가 있는지 확인
    if len(data) > 0:
        report = data[0]
        assert "report_id" in report
        assert "firm_nm" in report
        assert "article_title" in report


@pytest.mark.anyio
async def test_search_reports(client):
    """리포트 검색 기능 테스트"""
    # '반도체' 키워드로 검색 (데이터가 있을 것으로 예상되는 키워드)
    response = await client.get("/reports?q=반도체&limit=1")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # 만약 결과가 있다면 제목에 '반도체'가 포함되어야 함 (대소문자 무시 검색 확인)
    if len(data) > 0:
        assert "반도체" in data[0]["article_title"]


@pytest.mark.anyio
async def test_auth_telegram_invalid(client):
    """유효하지 않은 텔레그램 인증 데이터 요청 테스트"""
    invalid_user = {
        "id": 123456,
        "first_name": "Test",
        "auth_date": 1600000000,
        "hash": "invalid_hash"
    }
    response = await client.post("/auth/telegram", json=invalid_user)
    # 인증 실패(401)가 정상적으로 발생하는지 확인
    assert response.status_code == 401
    assert response.json()["detail"] == "Telegram Auth Failed"
