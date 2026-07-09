"""
관리자 리포트 AI 요약 다중 엔진 API 정밀 테스트
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, date
import os
import uuid

from app.database import Base, get_reports_db, get_keywords_db
from app.main import app
from app.dependencies import get_user_from_token
from app.models import SecReport, User
from app.settings import Settings
import ssh_library.antigravity_manager as _ag_mgr
import ssh_library.deepseek_manager as _ds_mgr



# 전역 SQLite 테스트 DB 설정
local_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=local_engine)


@pytest.fixture
async def admin_client():
    # 완벽한 테스트 격리를 보장하기 위해 각 비동기 테스트 실행 시마다 고유한 SQLite 물리 파일을 개별 생성합니다.
    db_filename = f"test_summarize_{uuid.uuid4().hex}.db"
    db_url = f"sqlite:///{db_filename}"
    
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal.configure(bind=engine)
    
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()

    # 관리자 유저 추가
    db.add(User(
        id=999,
        first_name="Admin",
        username="admin_test",
        is_admin=True,
    ))
    # 일반 유저 추가
    db.add(User(
        id=888,
        first_name="General",
        username="general_test",
        is_admin=False,
    ))
    
    # 샘플 리포트 추가
    db.add_all([
        SecReport(
            report_id=200,
            firm_nm="테스트증권",
            article_title="반도체 전망 리포트",
            report_date=date(2026, 6, 7),
            telegram_sent=True,
            key="test-key-200",
            pdf_file_url="https://test.com/report200.pdf",
            gemini_summary=None,
        ),
        SecReport(
            report_id=201,
            firm_nm="KB증권",
            article_title="이미 요약된 리포트",
            report_date=date(2026, 6, 7),
            telegram_sent=True,
            key="test-key-201",
            pdf_url="https://test.com/report201.pdf",
            gemini_summary="기존에 존재하는 훌륭한 요약 내용입니다.",
        ),
        SecReport(
            report_id=202,
            firm_nm="대신증권",
            article_title="PDF 링크 없는 리포트",
            report_date=date(2026, 6, 7),
            telegram_sent=True,
            key="test-key-202",
            pdf_file_url=None,
            telegram_url=None,
            gemini_summary=None,
        ),
    ])
    db.commit()
    db.close()

    # 의존성 오버라이드: 디폴트 관리자 유저 반환
    async def override_get_admin_user():
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

    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_user_from_token] = override_get_admin_user
    fastapi_app.dependency_overrides[get_reports_db] = override_get_db
    fastapi_app.dependency_overrides[get_keywords_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    
    # 임시 물리 SQLite 파일 제거
    if os.path.exists(db_filename):
        try:
            os.remove(db_filename)
        except Exception:
            pass


@pytest.mark.anyio
@patch("ssh_library.deepseek_manager.DeepSeekManager.summarize", new_callable=AsyncMock)
async def test_trigger_summarize_deepseek_success(mock_summarize, admin_client):
    """DeepSeek 엔진을 사용하여 요약을 정상 수행 및 DB 반영 검증"""
    mock_summarize.return_value = {
        "status": "success",
        "summary": "DeepSeek가 요약한 반도체 성장 가도 전망",
        "model": "deepseek-chat",
    }

    response = await admin_client.post("/admin/reports/200/summarize?engine=deepseek")
    assert response.status_code == 200, response.text
    
    data = response.json()
    assert data["report_id"] == 200
    assert data["status"] == "success"
    assert data["summary"] == "DeepSeek가 요약한 반도체 성장 가도 전망"
    assert data["summary_model"] == "deepseek-chat"

    # DB에 정상 업데이트되었는지 직접 조회 확인
    db = TestingSessionLocal()
    report = db.query(SecReport).filter(SecReport.report_id == 200).first()
    assert report.gemini_summary == "DeepSeek가 요약한 반도체 성장 가도 전망"
    assert report.summary_model == "deepseek-chat"
    assert report.summary_time is not None
    db.close()


@pytest.mark.anyio
@patch("ssh_library.antigravity_manager.AntigravityManager.summarize", new_callable=AsyncMock)
async def test_trigger_summarize_antigravity_success(mock_summarize, admin_client):
    """Antigravity (Gemini) 엔진을 사용하여 요약을 정상 수행 및 DB 반영 검증"""
    mock_summarize.return_value = {
        "status": "success",
        "summary": "Antigravity가 요약한 초전도 반도체 상승 포탈 시나리오",
        "model": "gemini-2.5-flash",
    }

    response = await admin_client.post("/admin/reports/200/summarize?engine=ag")
    assert response.status_code == 200, response.text
    
    data = response.json()
    assert data["report_id"] == 200
    assert data["status"] == "success"
    assert data["summary"] == "Antigravity가 요약한 초전도 반도체 상승 포탈 시나리오"
    assert data["summary_model"] == "gemini-2.5-flash"

    # DB에 정상 업데이트되었는지 직접 조회 확인
    db = TestingSessionLocal()
    report = db.query(SecReport).filter(SecReport.report_id == 200).first()
    assert report.gemini_summary == "Antigravity가 요약한 초전도 반도체 상승 포탈 시나리오"
    assert report.summary_model == "gemini-2.5-flash"
    db.close()


@pytest.mark.anyio
async def test_trigger_summarize_already_exists(admin_client):
    """이미 요약이 존재하는 리포트 요청 시, 스킵되고 기존 요약 반환 확인"""
    response = await admin_client.post("/admin/reports/201/summarize?engine=ag")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "skipped"
    assert "이미 요약이 존재합니다." in data["message"]
    assert "기존에 존재하는" in data["existing_summary"]


@pytest.mark.anyio
async def test_trigger_summarize_no_pdf_url(admin_client):
    """PDF URL이 부재한 리포트 요약 트리거 시 Validation Error 반환 검증"""
    response = await admin_client.post("/admin/reports/202/summarize?engine=ag")
    # ValidationException은 app에서 400 또는 422 에러로 변환되어야 함
    assert response.status_code in {400, 422}
    assert "PDF" in response.text or "URL" in response.text


@pytest.mark.anyio
async def test_trigger_summarize_unauthorized(admin_client):
    """관리자 권한이 아닌 일반 유저가 요청 시 Permission Denied(403) 통제 검증"""
    # 의존성을 일반 유저 반환으로 오버라이딩 변경
    async def override_get_general_user():
        db = TestingSessionLocal()
        user = db.query(User).filter(User.id == 888).first()
        db.close()
        return user

    app.dependency_overrides[get_user_from_token] = override_get_general_user

    response = await admin_client.post("/admin/reports/200/summarize?engine=ag")
    assert response.status_code in {401, 403}
