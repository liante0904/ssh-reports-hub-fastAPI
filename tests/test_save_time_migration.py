import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_user_from_token
from app.models import SecReport, User, ReportFavorite

# 테스트용 SQLite 메모리 DB
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
async def client():
    Base.metadata.create_all(bind=engine)

    # 테스트 동안 단일 세션을 유지하여 SQLite 격리 수준 문제를 해결함
    db = TestingSessionLocal()
    
    # 어드민 유저 생성
    db.add(User(
        id=999,
        first_name="Admin",
        username="admin_test",
        is_admin=True,
    ))
    
    # 1. save_at이 없고 save_time만 있는 예전 데이터 (명시적으로 report_id 부여 및 필수 필드 매핑)
    r1 = SecReport(
        report_id=1,
        firm_nm="A증권",
        article_title="예전 리포트",
        reg_dt="20260420",
        key="key-1",
        report_unique_key="key-1",
        save_time="2026-04-20 10:00:00",
        save_at=None,
        sec_firm_order=1,
        telegram_sent=True,
    )
    db.add(r1)
    
    # 2. save_at이 생성된 마이그레이션 완료 데이터 (명시적으로 report_id 부여 및 필수 필드 매핑)
    r2 = SecReport(
        report_id=2,
        firm_nm="B증권",
        article_title="신규 리포트",
        reg_dt="20260421",
        key="key-2",
        report_unique_key="key-2",
        save_time="2026-04-21 11:00:00",
        save_at=datetime(2026, 4, 21, 11, 0, 0, tzinfo=timezone.utc),
        sec_firm_order=2,
        telegram_sent=True,
    )
    db.add(r2)
    db.commit()

    # 즐겨찾기(ReportFavorite) 데이터 추가 시 생성된 ID 사용
    db.add(ReportFavorite(
        user_id=999,
        report_id=1,
    ))
    db.add(ReportFavorite(
        user_id=999,
        report_id=2,
    ))
    db.commit()

    # 의존성 오버라이드
    async def override_get_user():
        user = db.query(User).filter(User.id == 999).first()
        return user

    async def override_get_db():
        try:
            yield db
        finally:
            pass  # 피처 수명 주기가 끝날 때까지 닫지 않음

    app.dependency_overrides[get_user_from_token] = override_get_user
    app.dependency_overrides[get_reports_db] = override_get_db
    app.dependency_overrides[get_keywords_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    db.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_external_api_scraped_at_fallback(client):
    """External API의 scraped_at 필드 검증 및 save_time 키 제거 검증"""
    response = await client.get("/external/api/search")
    assert response.status_code == 200
    data = response.json()
    
    items = data["items"]
    # 2개의 리포트가 정상 리턴되었는지 확인
    assert len(items) >= 2
    
    # key 순서에 관계없이 맵 구성
    report_map = {item["key"]: item for item in items}
    
    # save_at이 없는 A증권 리포트
    item1 = report_map.get("key-1")
    assert item1 is not None
    assert "save_time" not in item1
    # save_time 값이 scraped_at으로 폴백되었는지 확인
    assert item1["scraped_at"] == "2026-04-20 10:00:00"
    
    # save_at이 있는 B증권 리포트
    item2 = report_map.get("key-2")
    assert item2 is not None
    assert "save_time" not in item2
    # save_at의 ISO 포맷 값이 들어갔는지 확인
    assert "2026-04-21T11:00:00" in item2["scraped_at"]


@pytest.mark.anyio
async def test_admin_metrics_last_save_time(client):
    """Admin metrics API에서 last_save_time이 save_at을 사용해 올바른 값을 반환하는지 검증"""
    response = await client.get("/admin/metrics")
    assert response.status_code == 200
    data = response.json()
    
    # 최신 리포트는 report_id=2 (save_at=2026-04-21T11:00:00+00:00)
    # 따라서 last_save_time 필드가 이 값을 가지고 와야 함
    last_save_time = data["last_activity"]["last_save_time"]
    assert "2026-04-21T11:00:00" in last_save_time


@pytest.mark.anyio
async def test_admin_firm_health_save_at(client):
    """Admin firm-health API에서 last_save가 save_at을 사용해 날짜만 반환하는지 검증"""
    response = await client.get("/admin/firm-health")
    assert response.status_code == 200
    data = response.json()
    
    firms = data["firms"]
    assert len(firms) >= 2
    
    # B증권 (sec_firm_order=2)의 last_save 검증 (DateTime.isoformat() -> "2026-04-21")
    firm_b = next((f for f in firms if f["sec_firm_order"] == 2), None)
    assert firm_b is not None
    assert firm_b["last_save"] == "2026-04-21"
    
    # A증권 (sec_firm_order=1)의 last_save 검증 (save_at이 None이므로 None 반환)
    firm_a = next((f for f in firms if f["sec_firm_order"] == 1), None)
    assert firm_a is not None
    assert firm_a["last_save"] is None


@pytest.mark.anyio
async def test_favorites_api_scraped_at(client):
    """Favorites API 응답에서 save_time 대신 scraped_at 필드가 적용되었는지 검증"""
    response = await client.get("/favorites")
    assert response.status_code == 200
    data = response.json()
    
    items = data["items"]
    assert len(items) >= 2
    
    # report_id=2 에 대응되는 favorite 아이템 검증
    fav2 = next((x for x in items if x["key"] == "key-2"), None)
    assert fav2 is not None
    assert "save_time" not in fav2
    assert "2026-04-21T11:00:00" in fav2["scraped_at"]
    
    # report_id=1 에 대응되는 favorite 아이템 검증 (save_time 폴백)
    fav1 = next((x for x in items if x["key"] == "key-1"), None)
    assert fav1 is not None
    assert "save_time" not in fav1
    assert fav1["scraped_at"] == "2026-04-20 10:00:00"
