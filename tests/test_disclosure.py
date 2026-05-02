import pytest
from datetime import datetime, timezone, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_keywords_db, get_reports_db
from app.main import app
from app.models import DartDisclosure

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
KST = timezone(timedelta(hours=9))


@pytest.fixture
async def client():
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all(
        [
            DartDisclosure(
                source="dart",
                published_at=datetime(2026, 5, 2, 9, 12, tzinfo=KST),
                company_name="삼성전자",
                company_code="005930",
                disclosure_title="임원 주식매수선택권 행사 및 소유상황 보고",
                disclosure_type="임원변동",
                insider_name="김민수",
                insider_role="부사장",
                transaction_type="buy",
                shares=15000.0,
                amount=1125000000.0,
                avg_price=75000.0,
                ownership_after=0.012,
                signal_score=92.0,
                summary_text="경영진의 자기자본 투입 성격의 매수로 해석되는 강한 신호.",
                dart_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260502000123",
                tags_json='["임원", "매수", "반도체"]',
            ),
            DartDisclosure(
                source="dart",
                published_at=datetime(2026, 5, 1, 14, 25, tzinfo=KST),
                company_name="카카오",
                company_code="035720",
                disclosure_title="임원 보유 주식 일부 처분",
                disclosure_type="임원변동",
                insider_name="이서연",
                insider_role="전무",
                transaction_type="sell",
                shares=8200.0,
                amount=410000000.0,
                avg_price=50000.0,
                ownership_after=0.004,
                signal_score=52.0,
                summary_text="단기 차익실현성 매도로 보이는 공시.",
                dart_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260501000088",
                tags_json='["임원", "매도", "플랫폼"]',
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
async def test_disclosure_summary(client):
    response = await client.get("/disclosure/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert data["buy_count"] == 1
    assert data["sell_count"] == 1
    assert data["executive_buy_count"] == 1
    assert data["net_buy_amount"] == 715000000.0


@pytest.mark.anyio
async def test_disclosure_filter(client):
    response = await client.get("/disclosure?transaction_type=buy")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["transaction_type"] == "buy"
    assert data[0]["company_name"] == "삼성전자"
