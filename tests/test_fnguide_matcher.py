import pytest
import json
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_settings_dep, get_user_from_token
from app.settings import Settings
from app.models import SecReport, FnGuideReportSummary, User
from app.services.fnguide_matcher import FnGuideMatcher

# 테스트용 SQLite 메모리 DB 설정
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def client(db_session):
    # 의존성 오버라이드
    def override_get_reports_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_keywords_db():
        try:
            yield db_session
        finally:
            pass

    # 테스트 관리자 유저
    def override_get_user_from_token():
        return User(
            id=1,
            username="admin",
            is_admin=True,
            status="active"
        )

    app.dependency_overrides[get_reports_db] = override_get_reports_db
    app.dependency_overrides[get_keywords_db] = override_get_keywords_db
    app.dependency_overrides[get_user_from_token] = override_get_user_from_token

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def test_fnguide_matcher_logic(db_session):
    """
    FnGuideMatcher의 매칭 로직 핵심 비즈니스 규칙 테스트:
    1. 날짜 +-1일 범위 매칭
    2. 증권사명 표준화 매칭 (예: 신한투자증권 vs 신한금융투자)
    3. 작성자 교집합 검증
    4. 제목 유사도 및 종목명 가산점
    """
    # 1. 테스트용 FnGuide 요약 데이터 삽입
    fnguide_summary = FnGuideReportSummary(
        summary_id=101,
        company_name="삼성전자",
        report_title="삼성전자 2분기 어닝 서프라이즈 전망",
        report_date="2026-06-05",
        provider="신한투자증권",
        author="홍길동, 이순신",
        summary_text="삼성전자 반도체 부문 실적 개선 기대",
        report_key="key_101",
    )
    db_session.add(fnguide_summary)

    # 2. 매칭 성공 케이스 리포트 추가 (+-1일 이내인 6월 4일자, 신한금융투자, 홍길동 작성)
    matched_report = SecReport(
        report_id=1,
        sec_firm_order=1,
        article_board_order=0,
        firm_nm="신한금융투자",
        article_title="삼성전자 2분기 호실적 기대감",
        reg_dt="20260604",
        main_ch_send_yn="Y",
        writer="홍길동",
        stock_names=json.dumps(["삼성전자"]),
    )
    # 3. 매칭 실패 케이스 리포트 추가 (증권사가 다름)
    diff_firm_report = SecReport(
        report_id=2,
        sec_firm_order=2,
        article_board_order=0,
        firm_nm="하나증권",
        article_title="삼성전자 2분기 호실적 기대감",
        reg_dt="20260604",
        main_ch_send_yn="Y",
        writer="홍길동",
        stock_names=json.dumps(["삼성전자"]),
    )
    # 4. 매칭 실패 케이스 리포트 추가 (날짜가 범위 밖)
    diff_date_report = SecReport(
        report_id=3,
        sec_firm_order=1,
        article_board_order=0,
        firm_nm="신한금융투자",
        article_title="삼성전자 2분기 호실적 기대감",
        reg_dt="20260601",  # 6월 1일은 6월 5일 기준 +-1일 범위 밖
        main_ch_send_yn="Y",
        writer="홍길동",
        stock_names=json.dumps(["삼성전자"]),
    )

    db_session.add_all([matched_report, diff_firm_report, diff_date_report])
    db_session.commit()

    # Matcher 실행
    matcher = FnGuideMatcher(db_session)
    result = matcher.match_pending_reports(limit=10, dry_run=False)

    assert result["status"] == "success"
    # 총 3개 리포트 중 1개만 매칭되어야 함
    assert result["matched_count"] == 1
    
    # DB 조회하여 실제 업데이트 반영 상태 검증
    updated_report = db_session.query(SecReport).filter_by(report_id=1).first()
    assert updated_report.fnguide_summary_id == 101

    not_updated_firm = db_session.query(SecReport).filter_by(report_id=2).first()
    assert not_updated_firm.fnguide_summary_id is None

    not_updated_date = db_session.query(SecReport).filter_by(report_id=3).first()
    assert not_updated_date.fnguide_summary_id is None


@pytest.mark.anyio
async def test_trigger_fnguide_match_api(client, db_session):
    """
    관리자 API /admin/fnguide/match 동작 여부 및 응답 결과 검증
    """
    # 임시 FnGuide 요약 리포트와 당사 리포트 삽입
    fnguide_summary = FnGuideReportSummary(
        summary_id=202,
        company_name="현대차",
        report_title="현대차 신차 효과 및 실적 개선",
        report_date="2026-06-05",
        provider="LS증권",
        author="김철수",
        summary_text="현대차 호실적 전망",
        report_key="key_202",
    )
    sec_report = SecReport(
        report_id=10,
        sec_firm_order=3,
        article_board_order=0,
        firm_nm="이베스트투자증권",  # LS증권의 구명칭/동의어
        article_title="현대차 실적 맑음",
        reg_dt="20260605",
        main_ch_send_yn="Y",
        writer="김철수",
        stock_names=json.dumps(["현대차"]),
    )
    db_session.add_all([fnguide_summary, sec_report])
    db_session.commit()

    # API 호출 (Dry Run = True)
    response = await client.post("/admin/fnguide/match?limit=10&dry_run=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Dry-Run" in data["message"]
    assert data["matched_count"] == 1
    
    # Dry Run 이었으므로 DB에 반영되면 안 됨
    db_session.expire_all()
    report_after_dry_run = db_session.query(SecReport).filter_by(report_id=10).first()
    assert report_after_dry_run.fnguide_summary_id is None

    # API 호출 (Dry Run = False)
    response = await client.post("/admin/fnguide/match?limit=10&dry_run=false")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Dry-Run" not in data["message"]
    assert data["matched_count"] == 1

    # 실제 DB에 반영되었는지 확인
    report_after_real = db_session.query(SecReport).filter_by(report_id=10).first()
    assert report_after_real.fnguide_summary_id == 202
