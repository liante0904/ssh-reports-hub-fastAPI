"""
태그 Enrichment 시스템 테스트

검증 대상:
1. _parse_json_field - 타입별 정규화
2. TagExtractionManager - 실제 제목에서 태그 추출
3. API /search - tag/sector/stock 파라미터
4. API 응답 - tags/stock_names/sector 필드 포함
"""

import json
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_reports_db, get_keywords_db
from app.dependencies import get_settings_dep
from app.settings import Settings
from app.models import SecReport, SecFirmInfo, SecBoardInfo

# ── 테스트 DB 설정 ──────────────────────────────────────────────────
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


async def override_get_reports_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


async def override_get_keywords_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
async def client():
    app.dependency_overrides[get_reports_db] = override_get_reports_db
    app.dependency_overrides[get_keywords_db] = override_get_keywords_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _seed_data(db):
    """검색 테스트용 샘플 데이터"""
    db.add_all([
        SecFirmInfo(sec_firm_order=0, sec_firm_name="LS증권", is_direct_link="N", description=""),
        SecFirmInfo(sec_firm_order=4, sec_firm_name="KB증권", is_direct_link="N", description=""),
    ])
    db.add_all([
        SecBoardInfo(sec_firm_order=0, article_board_order=0, board_nm="종목", board_cd="stock", label_nm="종목"),
        SecBoardInfo(sec_firm_order=4, article_board_order=0, board_nm="산업", board_cd="industry", label_nm="산업"),
    ])
    db.add_all([
        SecReport(
            report_id=1, sec_firm_order=0, article_board_order=0,
            firm_nm="LS증권", article_title="삼성전자 (005930) - 1Q25 Review: 메모리 반등 시작",
            writer="홍길동", key="key1", reg_dt="20250501", save_time="2025-05-01T10:00:00",
            telegram_sent=True, tags='["반도체", "실적 리뷰"]', stock_names='["삼성전자"]', sector="반도체",
        ),
        SecReport(
            report_id=2, sec_firm_order=4, article_board_order=0,
            firm_nm="KB증권", article_title="[2H26 산업 전망] 바이오; 트리거의 시작",
            writer="김철수", key="key2", reg_dt="20250502", save_time="2025-05-02T10:00:00",
            telegram_sent=True, tags='["바이오", "산업 분석"]', stock_names="[]", sector="바이오/헬스케어",
        ),
        SecReport(
            report_id=3, sec_firm_order=0, article_board_order=0,
            firm_nm="LS증권", article_title="Daily Brief - 시장 동향",
            writer="이영희", key="key3", reg_dt="20250503", save_time="2025-05-03T10:00:00",
            telegram_sent=False, tags="[]", stock_names="[]", sector="",
        ),
    ])
    db.commit()


# ═══════════════════════════════════════════════════════════════════
# 1. _parse_json_field 유닛 테스트
# ═══════════════════════════════════════════════════════════════════

class TestParseJsonField:
    """external_api._parse_json_field 타입별 처리 검증"""

    def _get_func(self):
        from app.routers.external_api import _parse_json_field
        return _parse_json_field

    def test_none_returns_empty_list(self):
        f = self._get_func()
        assert f(None) == []

    def test_empty_string_returns_empty_list(self):
        f = self._get_func()
        assert f("") == []

    def test_list_returns_as_is(self):
        f = self._get_func()
        assert f(["반도체", "AI"]) == ["반도체", "AI"]

    def test_empty_list_returns_empty(self):
        f = self._get_func()
        assert f([]) == []

    def test_json_string_parsed(self):
        f = self._get_func()
        assert f('["반도체", "AI"]') == ["반도체", "AI"]

    def test_empty_json_array_parsed(self):
        f = self._get_func()
        assert f("[]") == []

    def test_invalid_json_returns_empty(self):
        f = self._get_func()
        assert f("{invalid}") == []

    def test_non_list_json_returns_empty(self):
        f = self._get_func()
        assert f('{"key": "value"}') == []

    def test_number_returns_empty(self):
        f = self._get_func()
        assert f(123) == []


# ═══════════════════════════════════════════════════════════════════
# 2. TagExtractionManager 추출 정확도 테스트
# ═══════════════════════════════════════════════════════════════════

class TestTagExtraction:
    """규칙 기반 태그 추출 정확도"""

    @pytest.mark.anyio
    async def test_extract_stock_with_code(self):
        """종목명(코드) 패턴 추출"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("삼성전자(005930) : 실적 전망 상향", "LS증권")
        assert "삼성전자" in result["stock_names"]

    @pytest.mark.anyio
    async def test_extract_sector_semiconductor(self):
        """반도체 산업 분류"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("[2H26 산업 전망] 반도체; No 'Memory', No 'AI'", "신한증권")
        assert result["sector"] == "반도체"

    @pytest.mark.anyio
    async def test_extract_tags_ai(self):
        """AI 태그 추출"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("AI 반도체 시대, HBM 수요 폭발", "KB증권")
        assert "AI" in result["tags"]
        assert "반도체" in result["tags"]

    @pytest.mark.anyio
    async def test_extract_action_target_up(self):
        """목표주가 상향 액션 추출"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("삼성SDI - 목표주가 800,000원으로 상향", "메리츠증권")
        assert "목표주가 상향" in result["tags"]

    @pytest.mark.anyio
    async def test_no_tags_daily_brief(self):
        """일일 브리프는 태그 적게 추출"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("IBKS Morning Brief_230414", "IBK투자증권")
        # morning brief는 일반적으로 종목/산업 태그가 없음
        assert len(result["stock_names"]) == 0  # 종목 없음

    @pytest.mark.anyio
    async def test_result_structure(self):
        """응답 구조 완전성"""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scrapers', 'ssh-reports-scraper'))
        from enricher.tag_extractor import TagExtractionManager
        extractor = TagExtractionManager()
        result = await extractor.extract_tags("테스트 제목", "테스트증권")
        assert "tags" in result
        assert "stock_names" in result
        assert "sector" in result
        assert "action_type" in result
        assert "status" in result
        assert result["model"] == "rule-based"


# ═══════════════════════════════════════════════════════════════════
# 3. API /search 엔드포인트 테스트
# ═══════════════════════════════════════════════════════════════════

class TestSearchAPI:
    """태그/섹터/종목 검색 API"""

    @pytest.mark.anyio
    async def test_search_by_tag(self, client):
        """태그로 검색"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?tag=반도체")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["items"][0]["report_id"] == 1

    @pytest.mark.anyio
    async def test_search_by_sector(self, client):
        """섹터로 검색"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?sector=바이오")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["items"][0]["report_id"] == 2

    @pytest.mark.anyio
    async def test_search_by_stock(self, client):
        """종목명으로 검색"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?stock=삼성전자")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["items"][0]["report_id"] == 1

    @pytest.mark.anyio
    async def test_search_combined(self, client):
        """복합 필터 검색"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?tag=반도체&sector=반도체")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    @pytest.mark.anyio
    async def test_response_includes_tags_field(self, client):
        """응답에 tags/stock_names/sector 필드 존재"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        item = data["items"][0]
        assert "tags" in item
        assert "stock_names" in item
        assert "sector" in item
        assert isinstance(item["tags"], list)
        assert isinstance(item["stock_names"], list)

    @pytest.mark.anyio
    async def test_search_no_tag_param_returns_all(self, client):
        """태그 파라미터 없으면 전체 반환"""
        db = TestingSessionLocal()
        _seed_data(db)
        db.close()

        resp = await client.get("/external/api/search?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3  # 전체 3건


# ═══════════════════════════════════════════════════════════════════
# 4. _ensure_tags_columns 테스트
# ═══════════════════════════════════════════════════════════════════

class TestEnsureTagsColumns:
    """컬럼 자동 생성 로직"""

    def test_idempotent_on_existing_columns(self):
        """컬럼이 이미 있으면 중복 생성 안 함"""
        import os
        os.environ["DB_BACKEND"] = "sqlite"
        from app.main import _ensure_tags_columns

        # SQLite in-memory DB에는 Base.metadata.create_all로 이미 컬럼 생성됨
        # 추가 호출해도 에러 없어야 함
        _ensure_tags_columns(engine)  # Should not raise

    def test_handles_missing_table(self):
        """테이블이 없으면 조용히 리턴"""
        import os
        os.environ["DB_BACKEND"] = "sqlite"
        from app.main import _ensure_tags_columns
        from sqlalchemy import create_engine as ce
        from sqlalchemy.pool import StaticPool as SP

        empty_engine = ce("sqlite://", connect_args={"check_same_thread": False}, poolclass=SP)
        _ensure_tags_columns(empty_engine)  # Should not raise
        empty_engine.dispose()
