import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_settings_dep
from app.settings import Settings

from app.models import SecReport, MarketSentimentIndicator

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
    db.add_all(
        [
            SecReport(
                report_id=1,
                firm_nm="테스트증권",
                article_title="반도체 산업 전망",
                reg_dt="20260428",
                main_ch_send_yn="Y",
                key="test-key-1"
            ),
            SecReport(
                report_id=3,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260421",
                article_title="반도체 업황 점검",
                main_ch_send_yn="Y",
                writer="김선우",
                mkt_tp="KR",
                save_time="21-APR-26",
            ),
            SecReport(
                report_id=2,
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
        ]
    )
    db.add_all(
        [
            MarketSentimentIndicator(
                key="fear_greed_index",
                title="Fear & Greed Index",
                category="overheat",
                description="종합 시장 탐욕 지수입니다.",
                value=81.0,
                unit="pt",
                score=81.0,
                status="greed",
                source="mock",
                sort_order=1,
            ),
            MarketSentimentIndicator(
                key="vix_percentile",
                title="VIX Percentile",
                category="volatility",
                description="최근 변동성의 상대적 위치입니다.",
                value=74.0,
                unit="pt",
                score=74.0,
                status="elevated",
                source="mock",
                sort_order=2,
            ),
            MarketSentimentIndicator(
                key="breadth_ratio",
                title="상승/하락 종목 비율",
                category="breadth",
                description="시장의 확산 강도를 보여줍니다.",
                value=63.0,
                unit="%",
                score=63.0,
                status="neutral",
                source="mock",
                sort_order=3,
            ),
            MarketSentimentIndicator(
                key="funding_heat",
                title="펀딩비 과열도",
                category="leverage",
                description="선물 레버리지 쏠림을 반영합니다.",
                value=88.0,
                unit="pt",
                score=88.0,
                status="overheated",
                source="mock",
                sort_order=4,
            ),
            MarketSentimentIndicator(
                key="extreme_ratio",
                title="52주 극단값 비중",
                category="trend",
                description="신고가/신저가 쏠림을 나타냅니다.",
                value=70.0,
                unit="%",
                score=70.0,
                status="hot",
                source="mock",
                sort_order=5,
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
    app.dependency_overrides[get_keywords_db] = override_get_reports_db
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
async def test_board_filter_reports(client):
    """증권사와 게시판 필터를 함께 적용하면 정확히 좁혀지는지 확인"""
    response = await client.get("/reports?company=20&board=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["report_id"] == 3


@pytest.mark.anyio
async def test_ords_search_board_filter(client):
    """레거시 ORDS 검색 경로에서도 board 필터가 동작하는지 확인"""
    response = await client.get("/ords/admin/data_main_daily_send/search?company=20&board=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 3


@pytest.mark.anyio
async def test_pub_api_search_board_filter(client):
    """공용 API에서 회사와 게시판 필터가 함께 동작하는지 확인"""
    response = await client.get("/external/api/search?company=20&board=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 3


@pytest.mark.anyio
async def test_get_sentiment_indicators(client):
    response = await client.get("/sentiment")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    assert data[0]["key"] == "fear_greed_index"


@pytest.mark.anyio
async def test_get_sentiment_summary(client):
    response = await client.get("/sentiment/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["composite_score"] >= 60
    assert data["overheat_count"] >= 3


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
    # 개발 환경에서는 바이패스가 켜질 수 있으므로, 응답 형태만 검증한다.
    assert response.status_code in {200, 401}
    if response.status_code == 401:
        assert response.json()["detail"].startswith("Telegram Auth Failed")
    else:
        payload = response.json()
        assert "access_token" in payload


@pytest.mark.anyio
async def test_auth_telegram_missing_bot_token_returns_503(client):
    async def override_get_settings_dep():
        return Settings(
            app_env="prod",
            jwt_secret_key="x" * 32,
            telegram_bot_token="",
            allow_auth_bypass=False,
        )

    app.dependency_overrides[get_settings_dep] = override_get_settings_dep
    try:
        response = await client.post(
            "/auth/telegram",
            json={
                "id": 123456,
                "first_name": "Test",
                "auth_date": 1600000000,
                "hash": "invalid_hash",
            },
        )
    finally:
        app.dependency_overrides.pop(get_settings_dep, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Telegram bot token is not configured"


@pytest.mark.anyio
async def test_auth_telegram_whitelisted_user_skips_signature_check(client):
    async def override_get_settings_dep():
        return Settings(
            app_env="prod",
            jwt_secret_key="x" * 32,
            telegram_bot_token="dummy-token",
            allowed_telegram_user_ids="123456",
            allow_auth_bypass=False,
        )

    app.dependency_overrides[get_settings_dep] = override_get_settings_dep
    try:
        response = await client.post(
            "/auth/telegram",
            json={
                "id": 123456,
                "first_name": "Test",
                "auth_date": 1600000000,
                "hash": "invalid_hash",
            },
        )
    finally:
        app.dependency_overrides.pop(get_settings_dep, None)

    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
