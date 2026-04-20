import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.fixture
async def client():
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
        assert "FIRM_NM" in report
        assert "ARTICLE_TITLE" in report


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
        assert "반도체" in data[0]["ARTICLE_TITLE"]


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
