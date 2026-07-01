import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_settings_dep
from app.settings import Settings

from app.models import SecReport, SecFirmInfo, SecBoardInfo

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

    # 샘플 데이터 추가 (SecFirmInfo, SecBoardInfo 포함)
    db = TestingSessionLocal()
    db.add_all(
        [
            SecFirmInfo(
                sec_firm_order=0,
                sec_firm_name="LS증권",
                is_direct_link="N",
                description="test",
            ),
            SecFirmInfo(
                sec_firm_order=4,
                sec_firm_name="KB증권",
                is_direct_link="N",
                description="test",
            ),
            SecFirmInfo(
                sec_firm_order=20,
                sec_firm_name="메리츠증권",
                is_direct_link="Y",
                description="test",
            ),
            SecBoardInfo(
                sec_firm_order=4,
                article_board_order=0,
                board_nm="기업분석",
                label_nm="기업분석",
            ),
            SecBoardInfo(
                sec_firm_order=20,
                article_board_order=1,
                board_nm="산업분석",
                label_nm="산업분석",
            ),
            SecReport(
                report_id=1,
                sec_firm_order=0,
                article_board_order=0,
                firm_nm="LS증권",
                article_title="반도체 산업 전망",
                reg_dt="20260428",
                telegram_sent=True,
                key="test-key-1",
                writer="홍길동",
                gemini_summary="AI 요약: 반도체 긍정적 전망",
                mkt_tp="KR",
            ),
            SecReport(
                report_id=3,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260421",
                article_title="반도체 업황 점검",
                telegram_sent=True,
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
                telegram_sent=True,
                writer="김일혁",
                mkt_tp="US",
                save_time="20-APR-26",
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
    # JWT 토큰 검증에 일관된 시크릿 사용
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        app_env="prod",
        jwt_secret_key="test-jwt-secret-for-fav-tests" * 2,
        telegram_bot_token="dummy-token",
        allowed_telegram_user_ids="123456",
        allow_auth_bypass=False,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_health_check(client):
    """서버 상태 확인 엔드포인트 테스트"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ──────────────────────────────────────────────
# /reports (Pydantic 직렬화)
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_reports_pagination(client):
    """리포트 목록 조회 및 페이지네이션 테스트"""
    response = await client.get("/external/api/reports?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5

    if len(data) > 0:
        report = data[0]
        assert "report_id" in report
        assert "firm_nm" in report
        assert "article_title" in report


@pytest.mark.anyio
async def test_get_reports_search(client):
    """리포트 검색 (q=) 기능 테스트"""
    response = await client.get("/external/api/reports?q=반도체&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "반도체" in data[0]["article_title"]


@pytest.mark.anyio
async def test_get_reports_writer_filter(client):
    """리포트 작성자(writer=) 필터 테스트"""
    response = await client.get("/external/api/reports?writer=김선우&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert all("김선우" in r["writer"] for r in data)


@pytest.mark.anyio
async def test_get_reports_has_summary_filter(client):
    """리포트 AI 요약(has_summary=true) 필터 테스트"""
    response = await client.get("/external/api/reports?has_summary=true&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for r in data:
        assert r.get("gemini_summary") is not None
        assert r["gemini_summary"] not in ("", " ")


@pytest.mark.anyio
async def test_get_reports_board_filter(client):
    """증권사+게시판 필터 조합 테스트"""
    response = await client.get("/external/api/reports?company=20&board=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["report_id"] == 3


@pytest.mark.anyio
async def test_get_reports_json_serialization_full_set(client):
    """Pydantic JSON 직렬화 회귀 테스트 (memoryview/bytes 필드 검증)"""
    response = await client.get("/external/api/reports?limit=100")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # 모든 필드가 JSON 직렬화에 성공해야 함 (PydanticSerializationError 없음)
    for report in data:
        assert isinstance(report.get("report_id"), int)
        assert isinstance(report.get("firm_nm"), (str, type(None)))
        assert isinstance(report.get("article_title"), (str, type(None)))


# ──────────────────────────────────────────────
# /external/api/search (프론트엔드 메인 엔드포인트)
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_external_api_search_basic(client):
    """통합 검색 기본 응답 envelope 검증"""
    response = await client.get("/external/api/search?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "hasMore" in data
    assert "count" in data
    assert "limit" in data
    assert "offset" in data
    assert "links" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["hasMore"], bool)
    assert isinstance(data["count"], int)


@pytest.mark.anyio
async def test_external_api_search_company_board_filter(client):
    """검색 + 증권사 + 게시판 필터 조합"""
    response = await client.get("/external/api/search?company=20&board=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 3


@pytest.mark.anyio
async def test_external_api_search_writer_filter(client):
    """검색 + 작성자 필터"""
    response = await client.get("/external/api/search?writer=김일혁&limit=5")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert "김일혁" in item["writer"]


@pytest.mark.anyio
async def test_external_api_search_has_summary_filter(client):
    """검색 + AI 요약 있는 것만 필터"""
    response = await client.get("/external/api/search?has_summary=true&limit=5")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item.get("gemini_summary") is not None
        assert item["gemini_summary"] not in ("", " ")


@pytest.mark.anyio
async def test_external_api_search_title_filter(client):
    """검색 + 제목(title=) 필터"""
    response = await client.get("/external/api/search?title=Global&limit=5")
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert "Global" in item["article_title"]


# ──────────────────────────────────────────────
# /external/api/companies
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_external_api_companies(client):
    """증권사 목록 조회 (리포트 존재 기준)"""
    response = await client.get("/external/api/companies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    company = data[0]
    assert "name" in company
    assert "is_direct" in company
    assert "report_count" in company
    assert company["report_count"] >= 0


# ──────────────────────────────────────────────
# /external/api/boards
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_external_api_boards(client):
    """특정 증권사 게시판 목록 조회"""
    response = await client.get("/external/api/boards?company=20")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    board = data[0]
    assert "board_nm" in board
    assert "report_count" in board


@pytest.mark.anyio
async def test_external_api_boards_empty_company(client):
    """게시판 목록: 리포트 없는 증권사는 빈 배열"""
    response = await client.get("/external/api/boards?company=999")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


# ──────────────────────────────────────────────
# /external/api/industry
# ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_external_api_industry(client):
    """산업별 리포트 조회"""
    response = await client.get("/external/api/industry?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "hasMore" in data
    assert isinstance(data["items"], list)


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# /favorites (즐겨찾기)
# ──────────────────────────────────────────────

async def _get_auth_headers(client):
    """즐겨찾기 테스트용 인증 토큰 발급 (client fixture가 이미 설정 오버라이드 함)"""
    resp = await client.post(
        "/auth/telegram",
        json={
            "id": 123456,
            "first_name": "TestFav",
            "auth_date": 1600000000,
            "hash": "bypass",
        },
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_favorites_empty(client):
    """즐겨찾기 없는 상태에서 빈 목록 반환"""
    headers = await _get_auth_headers(client)
    resp = await client.get("/favorites", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


@pytest.mark.anyio
async def test_favorites_add_and_list(client):
    """즐겨찾기 추가 후 목록 조회"""
    headers = await _get_auth_headers(client)

    resp = await client.post("/favorites/1", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "added"

    resp = await client.get("/favorites", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["items"][0]["report_id"] == 1


@pytest.mark.anyio
async def test_favorites_duplicate(client):
    """중복 즐겨찾기 추가 시 already_exists 반환"""
    headers = await _get_auth_headers(client)

    await client.post("/favorites/2", headers=headers)
    resp = await client.post("/favorites/2", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_exists"


@pytest.mark.anyio
async def test_favorites_remove(client):
    """즐겨찾기 제거 후 목록에서 사라짐"""
    headers = await _get_auth_headers(client)

    await client.post("/favorites/3", headers=headers)
    resp = await client.delete("/favorites/3", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"

    resp = await client.get("/favorites", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.anyio
async def test_favorites_remove_not_found(client):
    """존재하지 않는 즐겨찾기 제거 시 not_found"""
    headers = await _get_auth_headers(client)

    resp = await client.delete("/favorites/999", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_found"


@pytest.mark.anyio
async def test_favorites_unauthorized(client):
    """인증 없이 즐겨찾기 접근 시 403"""
    resp = await client.get("/favorites")
    assert resp.status_code in {401, 403}


@pytest.mark.anyio
async def test_favorites_response_structure(client):
    """즐겨찾기 응답에 필수 키 존재 확인"""
    headers = await _get_auth_headers(client)

    await client.post("/favorites/1", headers=headers)
    resp = await client.get("/favorites", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    assert "report_id" in item
    assert "firm_nm" in item
    assert "article_title" in item
    assert "favorite_created_at" in item
    assert "pdf_archive" in item

