"""
관리자 메트릭 API 테스트
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_user_from_token, get_settings_dep
from app.models import SecReport, User
from app.settings import Settings

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

    # 샘플 데이터: User (admin), Reports
    db = TestingSessionLocal()
    db.add(User(
        id=999,
        first_name="Admin",
        username="admin_test",
        is_admin=True,
    ))
    db.add_all([
        SecReport(
            report_id=100,
            firm_nm="테스트증권",
            article_title="시장 전망 리포트",
            reg_dt="20260428",
            main_ch_send_yn="Y",
            key="test-key-100",
            save_time="2026-04-28T10:00:00",
        ),
        SecReport(
            report_id=101,
            firm_nm="KB증권",
            article_title="글로벌 마켓 인사이트",
            reg_dt="20260428",
            main_ch_send_yn="Y",
            key="test-key-101",
            save_time="2026-04-28T09:30:00",
        ),
    ])
    db.commit()
    db.close()

    # 의존성 오버라이드: 관리자 유저 반환
    async def override_get_user():
        db = TestingSessionLocal()
        user = db.query(User).filter(User.id == 999).first()
        db.close()
        return user

    async def override_get_db():
        test_db = TestingSessionLocal()
        try:
            yield test_db
        finally:
            test_db.close()

    app.dependency_overrides[get_user_from_token] = override_get_user
    app.dependency_overrides[get_reports_db] = override_get_db
    app.dependency_overrides[get_keywords_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.anyio
async def test_admin_metrics_structure(client):
    """/admin/metrics 엔드포인트 응답 구조 검증"""
    response = await client.get("/admin/metrics")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    # --- 최상위 필드 ---
    assert "timestamp" in data
    assert "overall" in data
    assert data["overall"] in {"online", "degraded", "offline"}

    # --- system ---
    assert "system" in data
    assert "hostname" in data["system"]
    assert "uptime_days" in data["system"]
    assert isinstance(data["system"]["uptime_days"], (int, float))
    assert data["system"]["uptime_days"] >= 0

    # --- cpu ---
    assert "cpu" in data
    cpu = data["cpu"]
    assert "percent" in cpu
    assert 0 <= cpu["percent"] <= 100
    assert "cores" in cpu
    assert cpu["cores"] >= 1
    # frequency_mhz는 환경에 따라 None일 수 있음
    assert cpu.get("frequency_mhz") is None or cpu["frequency_mhz"] > 0

    # --- memory ---
    assert "memory" in data
    mem = data["memory"]
    assert "total_gb" in mem
    assert mem["total_gb"] > 0
    assert "used_gb" in mem
    assert mem["used_gb"] > 0
    assert "percent" in mem
    assert 0 < mem["percent"] <= 100

    # --- disk ---
    assert "disk" in data
    disk = data["disk"]
    assert "total_gb" in disk
    assert disk["total_gb"] > 0
    assert "percent" in disk
    assert 0 <= disk["percent"] <= 100

    # --- database ---
    assert "database" in data
    db = data["database"]
    assert db["status"] in {"online", "offline", "degraded"}
    # SQLite 메모리 DB이므로 online이어야 함
    assert db["status"] == "online", f"DB status should be online, got: {db['status']}"
    assert "latency_ms" in db
    assert db["latency_ms"] is None or db["latency_ms"] > 0

    # --- reports ---
    assert "reports" in data
    rpt = data["reports"]
    assert "total" in rpt
    assert rpt["total"] >= 2  # 샘플 데이터 2건
    assert "today_inserts" in rpt
    assert "by_firm_today" in rpt

    # --- last_activity ---
    assert "last_activity" in data
    la = data["last_activity"]
    assert "last_save_time" in la
    assert "last_title" in la
    assert la["last_title"] == "시장 전망 리포트"
    assert "last_firm" in la


@pytest.mark.anyio
async def test_admin_metrics_unauthorized(client):
    """인증 없이 접근 시 403 반환 확인"""
    # 의존성 초기화 (auth 제거)
    app.dependency_overrides.pop(get_user_from_token, None)

    response = await client.get("/admin/metrics")
    # 토큰이 없으므로 401 또는 403
    assert response.status_code in {401, 403}

    # 원래 오버라이드 복원
    app.dependency_overrides[get_user_from_token] = \
        lambda: TestingSessionLocal().query(User).filter(User.id == 999).first()


@pytest.mark.anyio
async def test_admin_metrics_cpu_range(client):
    """CPU 퍼센트가 유효 범위 내에 있는지 확인"""
    response = await client.get("/admin/metrics")
    assert response.status_code == 200
    data = response.json()
    cpu_percent = data["cpu"]["percent"]
    assert isinstance(cpu_percent, (int, float))
    assert 0 <= cpu_percent <= 100, f"CPU percent out of range: {cpu_percent}"


@pytest.mark.anyio
async def test_admin_metrics_memory_and_disk_range(client):
    """메모리와 디스크 사용률이 유효 범위 내에 있는지 확인"""
    response = await client.get("/admin/metrics")
    assert response.status_code == 200
    data = response.json()
    assert 0 < data["memory"]["percent"] <= 100
    assert 0 <= data["disk"]["percent"] <= 100
