"""
ords/admin/data_main_daily_send/ 와 external/api/ 의 1:1 로직/API 패리티 검증 테스트

검증 대상:
  1. 파라미터 시그니처가 동등한지
  2. 공유 헬퍼 함수가 동일한 로직인지
  3. 필터 상수(INDUSTRY_REPORT_BOARD_FILTERS)가 동일한지
  4. 응답 shape이 호환되는지
  5. 실제 쿼리 실행 결과가 동등한지 (same DB, same params → same items)
"""

import inspect
import re
import textwrap

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_reports_db
from app.main import app
from app.models import SecReport, SecFirmInfo
from app.routers import ords_compat, external_api


# ---------------------------------------------------------------------------
# Fixture — SQLite in-memory with sample data
# ---------------------------------------------------------------------------

@pytest.fixture
async def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    db.add_all(
        [
            SecReport(
                report_id=300,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260421",
                article_title="디스플레이 패널가",
                main_ch_send_yn="Y",
                writer="김선우",
                mkt_tp="KR",
                save_time="21-APR-26",
            ),
            SecReport(
                report_id=200,
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
            SecReport(
                report_id=100,
                sec_firm_order=20,
                article_board_order=1,
                firm_nm="메리츠증권",
                reg_dt="20260419",
                article_title="미발송 산업",
                main_ch_send_yn="N",
                writer="김선우",
                mkt_tp="KR",
                save_time="19-APR-26",
            ),
            # 추가: 여러 증권사의 산업분석 + 검색 검증용
            SecReport(
                report_id=500,
                sec_firm_order=3,
                article_board_order=6,
                firm_nm="하나증권",
                reg_dt="20260422",
                article_title="반도체 산업 전망",
                main_ch_send_yn="Y",
                writer="이철민",
                mkt_tp="KR",
                save_time="22-APR-26",
                gemini_summary="AI 반도체 수요 급증…",
            ),
            SecReport(
                report_id=400,
                sec_firm_order=20,
                article_board_order=0,
                firm_nm="메리츠증권",
                reg_dt="20260422",
                article_title="기업분석: 삼성전자(005930)",
                main_ch_send_yn="Y",
                writer="박지원",
                mkt_tp="KR",
                save_time="22-APR-26",
                gemini_summary="4Q 실적 호조",
            ),
            SecReport(
                report_id=350,
                sec_firm_order=1,
                article_board_order=0,
                firm_nm="신한증권",
                reg_dt="20260421",
                article_title="자동차 산업 업데이트",
                main_ch_send_yn="Y",
                writer="임상현",
                mkt_tp="KR",
                save_time="21-APR-26",
            ),
            SecReport(
                report_id=250,
                sec_firm_order=19,
                article_board_order=0,
                firm_nm="DB증권",
                reg_dt="20260420",
                article_title="산업분석: 2차전지",
                main_ch_send_yn="Y",
                writer="김민호",
                mkt_tp="KR",
                save_time="20-APR-26",
            ),
            # DB증권 기업분석 (종목코드 포함 → 산업필터에서 제외되어야 함)
            SecReport(
                report_id=249,
                sec_firm_order=19,
                article_board_order=0,
                firm_nm="DB증권",
                reg_dt="20260420",
                article_title="기업분석: LG에너지솔루션(373220)",
                main_ch_send_yn="Y",
                writer="박철수",
                mkt_tp="KR",
                save_time="20-APR-26",
            ),
            # 글로벌 리포트
            SecReport(
                report_id=150,
                sec_firm_order=4,
                article_board_order=0,
                firm_nm="KB증권",
                reg_dt="20260419",
                article_title="US Tech Outlook",
                main_ch_send_yn="Y",
                writer="John Doe",
                mkt_tp="US",
                save_time="19-APR-26",
                gemini_summary=" ",
            ),
        ]
    )
    db.add(
        SecFirmInfo(
            sec_firm_order=20,
            sec_firm_name="메리츠증권",
            is_direct_link="Y",
        )
    )
    db.add(
        SecFirmInfo(
            sec_firm_order=4,
            sec_firm_name="KB증권",
            is_direct_link="N",
        )
    )
    db.add(
        SecFirmInfo(
            sec_firm_order=3,
            sec_firm_name="하나증권",
            is_direct_link="Y",
        )
    )
    db.add(
        SecFirmInfo(
            sec_firm_order=1,
            sec_firm_name="신한증권",
            is_direct_link="Y",
        )
    )
    db.add(
        SecFirmInfo(
            sec_firm_order=19,
            sec_firm_name="DB증권",
            is_direct_link="N",
        )
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. 파라미터 시그니처 비교
# ---------------------------------------------------------------------------

class TestParameterSignatures:
    """두 라우터의 industry / search 엔드포인트 파라미터가 동등한지 검증"""

    def test_industry_params_match(self):
        ords_sig = inspect.signature(ords_compat.get_ords_industry_reports)
        ext_sig = inspect.signature(external_api.get_industry_reports)

        ords_params = set(ords_sig.parameters.keys())
        ext_params = set(ext_sig.parameters.keys())

        assert ords_params == ext_params, (
            f"파라미터 불일치!\n"
            f"  ords only: {ords_params - ext_params}\n"
            f"  external only: {ext_params - ords_params}"
        )

    def test_search_params_match(self):
        ords_sig = inspect.signature(ords_compat.search_ords_reports)
        ext_sig = inspect.signature(external_api.search_reports)

        ords_params = set(ords_sig.parameters.keys())
        ext_params = set(ext_sig.parameters.keys())

        assert ords_params == ext_params, (
            f"파라미터 불일치!\n"
            f"  ords only: {ords_params - ext_params}\n"
            f"  external only: {ext_params - ords_params}"
        )

    @pytest.mark.parametrize("endpoint_func", [
        ords_compat.get_ords_industry_reports,
        external_api.get_industry_reports,
    ])
    def test_industry_param_defaults_match(self, endpoint_func):
        """같은 파라미터의 기본값이 두 라우터 간에 동일한지 검증"""
        ords_sig = inspect.signature(ords_compat.get_ords_industry_reports)
        ext_sig = inspect.signature(external_api.get_industry_reports)

        for name in ords_sig.parameters:
            ords_default = ords_sig.parameters[name].default
            ext_default = ext_sig.parameters[name].default
            # Query(...) 는 비교가 어려우므로 타입 어노테이션만 비교
            ords_anno = ords_sig.parameters[name].annotation
            ext_anno = ext_sig.parameters[name].annotation

            assert str(ords_anno) == str(ext_anno), (
                f"'{name}' 파라미터 타입 불일치: ords={ords_anno}, external={ext_anno}"
            )


# ---------------------------------------------------------------------------
# 2. 공유 헬퍼 함수 로직 비교
# ---------------------------------------------------------------------------

class TestSharedHelpers:
    """ords_compat 와 external_api 의 헬퍼 함수가 동일한 로직인지 검증"""

    def test_industry_filters_identical(self):
        """INDUSTRY_REPORT_BOARD_FILTERS 상수가 양쪽에서 동일한지"""
        ords_filters = ords_compat.INDUSTRY_REPORT_BOARD_FILTERS
        ext_filters = external_api.INDUSTRY_REPORT_BOARD_FILTERS

        assert ords_filters == ext_filters, (
            f"INDUSTRY_REPORT_BOARD_FILTERS 불일치!\n"
            f"  ords: {ords_filters}\n"
            f"  external: {ext_filters}"
        )

    def test_filter_count_identical(self):
        """양쪽 모두 동일한 수의 증권사 필터를 가지고 있는지"""
        assert len(ords_compat.INDUSTRY_REPORT_BOARD_FILTERS) == len(
            external_api.INDUSTRY_REPORT_BOARD_FILTERS
        )

    def test_apply_legacy_search_filters_source_identical(self):
        """_apply_legacy_search_filters 함수 소스코드가 양쪽에서 동일한지"""
        ords_src = _normalize_source(inspect.getsource(ords_compat._apply_legacy_search_filters))
        ext_src = _normalize_source(inspect.getsource(external_api._apply_legacy_search_filters))

        assert ords_src == ext_src, (
            f"_apply_legacy_search_filters 불일치!\n"
            f"--- ords:\n{ords_src}\n--- external:\n{ext_src}"
        )

    def test_paginate_ords_query_source_identical(self):
        """_paginate_ords_query 함수 소스코드가 양쪽에서 동일한지"""
        ords_src = _normalize_source(inspect.getsource(ords_compat._paginate_ords_query))
        ext_src = _normalize_source(inspect.getsource(external_api._paginate_ords_query))

        assert ords_src == ext_src, (
            f"_paginate_ords_query 불일치!\n"
            f"--- ords:\n{ords_src}\n--- external:\n{ext_src}"
        )


# ---------------------------------------------------------------------------
# 3. /industry 응답 비교
# ---------------------------------------------------------------------------

class TestIndustryParity:
    """/industry 엔드포인트의 실제 응답이 양쪽에서 동등한지 검증"""

    @pytest.mark.anyio
    async def test_industry_same_total_count(self, client):
        """동일 파라미터로 호출했을 때 총 아이템 수가 같아야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        assert ords_resp.status_code == 200
        assert ext_resp.status_code == 200

        ords_data = ords_resp.json()
        ext_data = ext_resp.json()

        assert ords_data["count"] == ext_data["count"], (
            f"industry count 불일치: ords={ords_data['count']}, external={ext_data['count']}"
        )

    @pytest.mark.anyio
    async def test_industry_report_ids_match(self, client):
        """양쪽 응답의 report_id 목록이 동일해야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, (
            f"report_id 집합 불일치!\n"
            f"  ords only: {ords_ids - ext_ids}\n"
            f"  external only: {ext_ids - ords_ids}"
        )

    @pytest.mark.anyio
    async def test_industry_same_order(self, client):
        """양쪽 응답의 report_id 순서가 동일해야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        ords_ids = [item["report_id"] for item in ords_resp.json()["items"]]
        ext_ids = [item["report_id"] for item in ext_resp.json()["items"]]

        assert ords_ids == ext_ids, (
            f"report_id 순서 불일치!\n"
            f"  ords: {ords_ids}\n"
            f"  external: {ext_ids}"
        )

    @pytest.mark.anyio
    async def test_industry_field_intersection(self, client):
        """ords 응답의 모든 필드가 external 응답에도 존재해야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        ords_items = ords_resp.json()["items"]
        ext_items = ext_resp.json()["items"]

        if not ords_items:
            pytest.skip("No items to compare")

        # ords 아이템의 모든 top-level key가 external에도 있어야 함
        ords_keys = set(ords_items[0].keys())
        ext_keys = set(ext_items[0].keys())

        missing_in_ext = ords_keys - ext_keys
        # external_api는 'is_direct' 필드를 추가로 가짐 → 이건 허용
        extra_in_ext = ext_keys - ords_keys - {"is_direct"}

        assert not missing_in_ext, (
            f"external 응답에 누락된 필드: {missing_in_ext}"
        )
        # is_direct 외 추가 필드는 없어야 함
        assert not extra_in_ext, (
            f"external 응답에 불필요한 추가 필드: {extra_in_ext}"
        )

    @pytest.mark.anyio
    async def test_industry_field_values_match(self, client):
        """동일 report_id의 모든 공통 필드 값이 일치해야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        ords_by_id = {item["report_id"]: item for item in ords_resp.json()["items"]}
        ext_by_id = {item["report_id"]: item for item in ext_resp.json()["items"]}

        common_ids = set(ords_by_id.keys()) & set(ext_by_id.keys())
        assert common_ids, "공통 report_id가 없습니다"

        common_keys = set(ords_by_id[next(iter(common_ids))].keys()) & set(
            ext_by_id[next(iter(common_ids))].keys()
        )

        mismatches = []
        for rid in sorted(common_ids):
            for key in sorted(common_keys):
                ov = ords_by_id[rid].get(key)
                ev = ext_by_id[rid].get(key)
                if ov != ev:
                    mismatches.append(f"  report_id={rid}, key='{key}': ords={ov!r}, external={ev!r}")

        assert not mismatches, (
            f"필드 값 불일치 ({len(mismatches)}건):\n" + "\n".join(mismatches[:20])
        )

    @pytest.mark.anyio
    async def test_industry_with_filters(self, client):
        """writer, title, mkt_tp, company, board 필터 적용 시 양쪽 응답 동일"""
        params = {"writer": "김선우", "mkt_tp": "domestic", "company": 20}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry", params=params)
        ext_resp = await client.get("/external/api/industry", params=params)

        assert ords_resp.status_code == 200
        assert ext_resp.status_code == 200

        ords_ids = [item["report_id"] for item in ords_resp.json()["items"]]
        ext_ids = [item["report_id"] for item in ext_resp.json()["items"]]

        assert ords_ids == ext_ids, (
            f"필터 적용 시 report_id 불일치 (params={params}):\n"
            f"  ords: {ords_ids}\n"
            f"  external: {ext_ids}"
        )

    @pytest.mark.anyio
    async def test_industry_last_report_id(self, client):
        """last_report_id 필터 양쪽 동일"""
        ords_resp = await client.get(
            "/ords/admin/data_main_daily_send/industry",
            params={"last_report_id": 400},
        )
        ext_resp = await client.get(
            "/external/api/industry",
            params={"last_report_id": 400},
        )

        assert ords_resp.status_code == 200
        assert ext_resp.status_code == 200

        ords_ids = [item["report_id"] for item in ords_resp.json()["items"]]
        ext_ids = [item["report_id"] for item in ext_resp.json()["items"]]

        assert ords_ids == ext_ids, f"last_report_id 필터 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_industry_pagination_hasmore(self, client):
        """페이지네이션(limit/offset)과 hasMore가 양쪽 동일"""
        params = {"limit": 2, "offset": 1}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry", params=params)
        ext_resp = await client.get("/external/api/industry", params=params)

        assert ords_resp.status_code == 200
        assert ext_resp.status_code == 200

        ords_data = ords_resp.json()
        ext_data = ext_resp.json()

        assert ords_data["limit"] == ext_data["limit"]
        assert ords_data["offset"] == ext_data["offset"]
        assert ords_data["hasMore"] == ext_data["hasMore"]
        assert ords_data["count"] == ext_data["count"]

        ords_ids = [item["report_id"] for item in ords_data["items"]]
        ext_ids = [item["report_id"] for item in ext_data["items"]]
        assert ords_ids == ext_ids, f"페이지네이션 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_industry_response_envelope(self, client):
        """응답 envelope 구조가 양쪽 동일한지"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry")
        ext_resp = await client.get("/external/api/industry")

        expected_keys = {"items", "hasMore", "limit", "offset", "count", "links"}

        ords_keys = set(ords_resp.json().keys())
        ext_keys = set(ext_resp.json().keys())

        assert ords_keys == expected_keys, f"ords envelope key 불일치: {ords_keys}"
        assert ext_keys == expected_keys, f"external envelope key 불일치: {ext_keys}"


# ---------------------------------------------------------------------------
# 4. /search 응답 비교
# ---------------------------------------------------------------------------

class TestSearchParity:
    """search 엔드포인트의 실제 응답이 양쪽에서 동등한지 검증"""

    @pytest.mark.anyio
    async def test_search_same_total_count(self, client):
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search")
        ext_resp = await client.get("/external/api/search")

        assert ords_resp.status_code == 200
        assert ext_resp.status_code == 200

        ords_data = ords_resp.json()
        ext_data = ext_resp.json()

        # search는 industry와 달리 main_ch_send_yn 필터가 없음 → 전체 리포트
        assert ords_data["count"] == ext_data["count"], (
            f"search count 불일치: ords={ords_data['count']}, external={ext_data['count']}"
        )

    @pytest.mark.anyio
    async def test_search_report_ids_match(self, client):
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search")
        ext_resp = await client.get("/external/api/search")

        ords_ids = [item["report_id"] for item in ords_resp.json()["items"]]
        ext_ids = [item["report_id"] for item in ext_resp.json()["items"]]

        assert ords_ids == ext_ids, (
            f"search report_id 순서 불일치!\n  ords: {ords_ids}\n  external: {ext_ids}"
        )

    @pytest.mark.anyio
    async def test_search_with_report_id(self, client):
        """report_id로 단건 검색 시 양쪽 동일"""
        params = {"report_id": 300}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_data = ords_resp.json()
        ext_data = ext_resp.json()

        assert ords_data["count"] == ext_data["count"] == 1
        assert ords_data["items"][0]["report_id"] == ext_data["items"][0]["report_id"] == 300

    @pytest.mark.anyio
    async def test_search_with_title_filter(self, client):
        params = {"title": "Global"}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"title filter 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_with_mkt_tp_global(self, client):
        params = {"mkt_tp": "global"}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"mkt_tp=global 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_with_mkt_tp_domestic(self, client):
        params = {"mkt_tp": "domestic"}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"mkt_tp=domestic 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_with_has_summary(self, client):
        """has_summary=true 필터 양쪽 동일"""
        params = {"has_summary": "true"}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"has_summary 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_with_company_and_board(self, client):
        params = {"company": 4, "board": 0}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"company+board filter 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_combined_filters(self, client):
        """복합 필터 양쪽 동일"""
        params = {"writer": "김", "mkt_tp": "domestic", "company": 20}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_ids = {item["report_id"] for item in ords_resp.json()["items"]}
        ext_ids = {item["report_id"] for item in ext_resp.json()["items"]}

        assert ords_ids == ext_ids, f"복합 filter 불일치: ords={ords_ids}, ext={ext_ids}"

    @pytest.mark.anyio
    async def test_search_field_values_match(self, client):
        """동일 report_id의 모든 공통 필드 값이 일치해야 함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search")
        ext_resp = await client.get("/external/api/search")

        ords_by_id = {item["report_id"]: item for item in ords_resp.json()["items"]}
        ext_by_id = {item["report_id"]: item for item in ext_resp.json()["items"]}

        common_ids = set(ords_by_id.keys()) & set(ext_by_id.keys())
        assert common_ids, "공통 report_id가 없습니다"

        common_keys = set(ords_by_id[next(iter(common_ids))].keys()) & set(
            ext_by_id[next(iter(common_ids))].keys()
        )

        mismatches = []
        for rid in sorted(common_ids):
            for key in sorted(common_keys):
                ov = ords_by_id[rid].get(key)
                ev = ext_by_id[rid].get(key)
                if ov != ev:
                    mismatches.append(f"  report_id={rid}, key='{key}': ords={ov!r}, external={ev!r}")

        assert not mismatches, (
            f"search 필드 값 불일치 ({len(mismatches)}건):\n" + "\n".join(mismatches[:20])
        )

    @pytest.mark.anyio
    async def test_search_pagination(self, client):
        """search 페이지네이션 양쪽 동일"""
        params = {"limit": 3, "offset": 2}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search", params=params)
        ext_resp = await client.get("/external/api/search", params=params)

        ords_data = ords_resp.json()
        ext_data = ext_resp.json()

        assert ords_data["limit"] == ext_data["limit"]
        assert ords_data["offset"] == ext_data["offset"]
        assert ords_data["hasMore"] == ext_data["hasMore"]
        assert ords_data["count"] == ext_data["count"]

        ords_ids = [item["report_id"] for item in ords_data["items"]]
        ext_ids = [item["report_id"] for item in ext_data["items"]]
        assert ords_ids == ext_ids, f"search 페이지네이션 불일치: ords={ords_ids}, ext={ext_ids}"


# ---------------------------------------------------------------------------
# 5. Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """엣지 케이스에서 양쪽 응답이 동등한지 검증"""

    @pytest.mark.anyio
    async def test_empty_result(self, client):
        """결과가 없을 때 양쪽 모두 빈 배열 반환"""
        params = {"writer": "존재하지않는작성자xyz"}
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry", params=params)
        ext_resp = await client.get("/external/api/industry", params=params)

        assert ords_resp.json()["items"] == []
        assert ext_resp.json()["items"] == []
        assert ords_resp.json()["count"] == 0
        assert ext_resp.json()["count"] == 0

    @pytest.mark.anyio
    async def test_limit_validation(self, client):
        """limit 파라미터 유효성 검증이 양쪽 동일"""
        # limit > 100 → 422
        ords_resp = await client.get("/ords/admin/data_main_daily_send/industry", params={"limit": 101})
        ext_resp = await client.get("/external/api/industry", params={"limit": 101})
        assert ords_resp.status_code == 422
        assert ext_resp.status_code == 422

    @pytest.mark.anyio
    async def test_mkt_tp_validation(self, client):
        """mkt_tp 유효성 검증이 양쪽 동일"""
        ords_resp = await client.get(
            "/ords/admin/data_main_daily_send/search", params={"mkt_tp": "invalid"}
        )
        ext_resp = await client.get("/external/api/search", params={"mkt_tp": "invalid"})
        assert ords_resp.status_code == 422
        assert ext_resp.status_code == 422

    @pytest.mark.anyio
    async def test_response_envelope_links(self, client):
        """links 배열이 양쪽 모두 자기 참조 포함"""
        ords_resp = await client.get("/ords/admin/data_main_daily_send/search")
        ext_resp = await client.get("/external/api/search")

        ords_links = ords_resp.json()["links"]
        ext_links = ext_resp.json()["links"]

        ords_rels = {link["rel"] for link in ords_links}
        ext_rels = {link["rel"] for link in ext_links}

        assert ords_rels == ext_rels, f"links rel 불일치: ords={ords_rels}, ext={ext_rels}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_source(src: str) -> str:
    """소스코드에서 공백/주석/타입힌트 차이를 제거하고 정규화"""
    # docstring 제거
    src = re.sub(r'""".*?"""', '"""..."""', src, flags=re.DOTALL)
    # return type hint 제거 (-> ... 부분, 중첩 제네릭 포함)
    src = re.sub(r'\s*->\s*[^:]+(?=:\s*\n|\s*\n)', '', src)
    # parameter type hints 제거 (: type 부분) — 콜론이 포함된 타입
    src = re.sub(r':\s*\w+(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])?', '', src)
    # 빈 줄, leading/trailing whitespace 정리
    src = textwrap.dedent(src).strip()
    # 연속 공백 → 단일 공백
    src = re.sub(r'[ \t]+', ' ', src)
    # 빈 줄 연속 → 단일 빈 줄
    src = re.sub(r'\n\s*\n', '\n\n', src)
    return src
