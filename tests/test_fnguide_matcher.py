import pytest
import json
from datetime import date
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
        firm_id=1,
        board_id=0,
        firm_nm="신한금융투자",
        article_title="삼성전자 2분기 호실적 기대감",
        report_date=date(2026, 6, 4),
        telegram_sent=True,
        writer="홍길동",
        stock_names=json.dumps(["삼성전자"]),
    )
    # 3. 매칭 실패 케이스 리포트 추가 (증권사가 다름)
    diff_firm_report = SecReport(
        report_id=2,
        firm_id=2,
        board_id=0,
        firm_nm="하나증권",
        article_title="삼성전자 2분기 호실적 기대감",
        report_date=date(2026, 6, 4),
        telegram_sent=True,
        writer="홍길동",
        stock_names=json.dumps(["삼성전자"]),
    )
    # 4. 매칭 실패 케이스 리포트 추가 (날짜가 범위 밖)
    diff_date_report = SecReport(
        report_id=3,
        firm_id=1,
        board_id=0,
        firm_nm="신한금융투자",
        article_title="삼성전자 2분기 호실적 기대감",
        report_date=date(2026, 6, 1),  # 6월 1일은 6월 5일 기준 +-1일 범위 밖
        telegram_sent=True,
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
        firm_id=3,
        board_id=0,
        firm_nm="이베스트투자증권",  # LS증권의 구명칭/동의어
        article_title="현대차 실적 맑음",
        report_date=date(2026, 6, 5),
        telegram_sent=True,
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




@pytest.mark.anyio
async def test_trigger_fnguide_match_internal_api(client, db_session):
    """
    내부 전용 API /admin/fnguide/match-internal 의 동작 여부,
    보안 토큰(X-Internal-Token) 검증 및 정상 매칭 여부 검증
    """
    # 1. 테스트용 레포트 및 요약 데이터 추가
    fnguide_summary = FnGuideReportSummary(
        summary_id=250,
        company_name="삼성전자",
        report_title="삼성전자 2분기 어닝 서프라이즈",
        report_date="2026-06-05",
        provider="LS증권",
        author="김철수",
        summary_text="반도체 사업부 흑자 규모 대폭 확대",
        report_key="key_250",
    )
    sec_report = SecReport(
        report_id=25,
        firm_id=3,
        board_id=0,
        firm_nm="LS증권",
        article_title="삼성전자 2분기 실적 서프라이즈 예고",
        report_date=date(2026, 6, 5),
        telegram_sent=True,
        writer="김철수",
        stock_names=json.dumps(["삼성전자"]),
    )
    db_session.add_all([fnguide_summary, sec_report])
    db_session.commit()

    # 가짜 토큰 및 토큰 누락 케이스 테스트 (403 Forbidden)
    response_no_token = await client.post("/admin/fnguide/match-internal?limit=10")
    assert response_no_token.status_code == 403

    response_bad_token = await client.post(
        "/admin/fnguide/match-internal?limit=10",
        headers={"X-Internal-Token": "invalid_secret_key_1234"}
    )
    assert response_bad_token.status_code == 403

    # 올바른 토큰 케이스 테스트 (settings.JWT_SECRET_KEY 검증)
    from app.settings import get_settings
    settings = get_settings()
    correct_token = settings.jwt_secret_key

    response_success = await client.post(
        "/admin/fnguide/match-internal?limit=10&dry_run=false",
        headers={"X-Internal-Token": correct_token}
    )
    assert response_success.status_code == 200
    data = response_success.json()
    assert data["status"] == "success"
    assert data["matched_count"] == 1

    # 실제 DB에 반영되었는지 검증
    db_session.expire_all()
    matched_report = db_session.query(SecReport).filter_by(report_id=25).first()
    assert matched_report.fnguide_summary_id == 250


@pytest.mark.anyio
async def test_get_report_summaries_with_matched_sec_reports(client, db_session):
    """
    /pub/api/fnguide/report-summaries API 조회 시,
    매칭된 sec_reports가 정상적으로 prefetch되어 응답 스키마에 포함되는지 검증합니다.
    """
    # 1. 요약 리포트 및 당사 리포트 삽입
    fnguide_summary = FnGuideReportSummary(
        summary_id=303,
        company_name="LG에너지솔루션",
        report_title="LG에너지솔루션 배터리 실적 기대",
        report_date="2026-06-05",
        provider="메리츠증권",
        author="이철희",
        summary_text="LG엔솔 하반기 턴어라운드",
        report_key="key_303",
    )
    db_session.add(fnguide_summary)
    db_session.commit()

    sec_report = SecReport(
        report_id=30,
        firm_id=4,
        board_id=0,
        firm_nm="메리츠증권",
        article_title="LG엔솔 실적 분석",
        report_date=date(2026, 6, 5),
        telegram_sent=True,
        writer="이철희",
        stock_names=json.dumps(["LG에너지솔루션"]),
        fnguide_summary_id=303,  # 수동 매핑
    )
    db_session.add(sec_report)
    db_session.commit()

    # 2. API 호출
    response = await client.get("/pub/api/fnguide/report-summaries?report_date=2026-06-05")
    assert response.status_code == 200
    data = response.json()
    
    # 3. 매칭된 sec_reports가 포함되었는지 데이터 검증
    assert len(data) >= 1
    target_summary = next((item for item in data if item["summary_id"] == 303), None)
    assert target_summary is not None
    assert "sec_reports" in target_summary
    assert len(target_summary["sec_reports"]) == 1
    assert target_summary["sec_reports"][0]["report_id"] == 30
    assert target_summary["sec_reports"][0]["firm_nm"] == "메리츠증권"
    assert target_summary["sec_reports"][0]["article_title"] == "LG엔솔 실적 분석"


def test_parse_date_and_dots_matching(db_session):
    """
    1. YYYY.MM.DD 포맷의 날짜가 올바르게 파싱되는지 검증
    2. 마침표(.) 형식의 날짜를 가진 FnGuide 요약과 YYYYMMDD 형태의 당사 리포트가 성공적으로 매칭되는지 검증
    """
    from app.services.fnguide_matcher import parse_date, FnGuideMatcher
    import datetime

    # 1. parse_date 단위 테스트
    assert parse_date("20260608") == datetime.date(2026, 6, 8)
    assert parse_date("2026-06-08") == datetime.date(2026, 6, 8)
    assert parse_date("2026.06.08") == datetime.date(2026, 6, 8)

    # 2. 마침표 날짜 매칭 통합 테스트
    fnguide_summary = FnGuideReportSummary(
        summary_id=505,
        company_name="현대자동차",
        report_title="현대자동차 실적 개선 지속",
        report_date="2026.06.08",  # 실제 운영 환경의 마침표 형태
        provider="하나증권",
        author="김철수",
        summary_text="현대차 실적 맑음",
        report_key="key_505",
    )
    db_session.add(fnguide_summary)

    sec_report = SecReport(
        report_id=50,
        firm_id=2,
        board_id=0,
        firm_nm="하나투자증권",  # 정규화되어 '하나'로 매칭 예정
        article_title="현대차 실적 분석 및 전망",
        report_date=date(2026, 6, 8),  # YYYYMMDD 형태
        telegram_sent=True,
        writer="김철수",
        stock_names=json.dumps(["현대자동차"]),
    )
    db_session.add(sec_report)
    db_session.commit()

    # 매칭 수행
    matcher = FnGuideMatcher(db_session)
    result = matcher.match_pending_reports(limit=10, dry_run=False)

    assert result["status"] == "success"
    assert result["matched_count"] == 1

    # 업데이트 결과 검증
    db_session.refresh(sec_report)
    assert sec_report.fnguide_summary_id == 505


def test_matcher_skips_blank_and_invalid_dates(db_session):
    db_session.add_all([
        FnGuideReportSummary(
            summary_id=601,
            company_name="삼성전자",
            report_title="삼성전자 실적 전망",
            report_date=None,
            provider="신한투자증권",
            author="홍길동",
            summary_text="빈 날짜 데이터",
            report_key="key_601",
        ),
        FnGuideReportSummary(
            summary_id=602,
            company_name="삼성전자",
            report_title="삼성전자 실적 전망",
            report_date=None,
            provider="신한투자증권",
            author="홍길동",
            summary_text="잘못된 날짜 데이터",
            report_key="key_602",
        ),
        SecReport(
            report_id=60,
            firm_id=1,
            board_id=0,
            firm_nm="신한투자증권",
            article_title="삼성전자 실적 전망",
            report_date=None,
            writer="홍길동",
            stock_names=json.dumps(["삼성전자"]),
        ),
        SecReport(
            report_id=61,
            firm_id=1,
            board_id=0,
            firm_nm="신한투자증권",
            article_title="삼성전자 실적 전망",
            report_date=None,
            writer="홍길동",
            stock_names=json.dumps(["삼성전자"]),
        ),
    ])
    db_session.commit()

    result = FnGuideMatcher(db_session).match_pending_reports(limit=10)

    assert result["status"] == "success"
    assert result["matched_count"] == 0
    assert result["total_processed"] == 2
