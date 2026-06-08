# -*- coding:utf-8 -*-
import json
import pytest
from pydantic import ValidationError
from app.models import SecReport
from app.schemas import SecReportResponse

def test_secreport_model_has_premium_attributes():
    """
    SQLAlchemy SecReport 모델 클래스 정의에 신규 프리미엄 컬럼 5가지가
    올바르게 선언되었는지 검증합니다.
    """
    assert hasattr(SecReport, "target_price"), "SecReport 모델에 target_price 컬럼이 정의되지 않았습니다."
    assert hasattr(SecReport, "rating"), "SecReport 모델에 rating 컬럼이 정의되지 않았습니다."
    assert hasattr(SecReport, "revision_type"), "SecReport 모델에 revision_type 컬럼이 정의되지 않았습니다."
    assert hasattr(SecReport, "report_type"), "SecReport 모델에 report_type 컬럼이 정의되지 않았습니다."
    assert hasattr(SecReport, "stock_tickers"), "SecReport 모델에 stock_tickers 컬럼이 정의되지 않았습니다."

def test_secreportresponse_schema_serialization():
    """
    Pydantic SecReportResponse 스키마에 프리미엄 5대 속성 필드가 제대로 반영되었으며,
    SQLAlchemy 가상 객체(또는 딕셔너리)를 직렬화(Serialization)할 때 
    정상적으로 바인딩 및 변환되는지 테스트합니다.
    """
    # mock SQLAlchemy model instance
    mock_report = SecReport(
        report_id=123,
        firm_nm="LS증권",
        article_title="반도체 업황 개선 리포트",
        tags='["IT", "상향"]',
        stock_names='["삼성전자"]',
        sector="반도체",
        target_price=98000.0,
        rating="BUY",
        revision_type="UPGRADE",
        report_type="COMPANY",
        stock_tickers='["005930"]'
    )

    # from_attributes=True를 통하여 SQLAlchemy 모델에서 Pydantic 스키마로 로드
    response = SecReportResponse.model_validate(mock_report)

    # 필드 확인
    assert response.report_id == 123
    assert response.firm_nm == "LS증권"
    assert response.article_title == "반도체 업황 개선 리포트"
    assert response.tags == ["IT", "상향"]
    assert response.stock_names == ["삼성전자"]
    assert response.sector == "반도체"
    assert response.target_price == 98000.0
    assert response.rating == "BUY"
    assert response.revision_type == "UPGRADE"
    assert response.report_type == "COMPANY"
    assert response.stock_tickers == ["005930"] # JSON string이 list로 성공적으로 변환되었는지 검증

def test_secreportresponse_schema_nullable_handling():
    """
    프리미엄 속성들이 Null(None) 또는 누락된 상황에서도 
    Pydantic 스키마 검증이 실패하지 않고 하위 호환성 있게 기본값으로 채워지는지 확인합니다.
    """
    mock_legacy_report = SecReport(
        report_id=456,
        firm_nm="신한투자증권",
        article_title="레거시 리포트",
        tags=None,
        stock_names=None,
        sector=None,
        target_price=None,
        rating=None,
        revision_type=None,
        report_type=None,
        stock_tickers=None
    )

    response = SecReportResponse.model_validate(mock_legacy_report)

    assert response.report_id == 456
    assert response.target_price is None
    assert response.rating is None
    assert response.revision_type is None
    assert response.report_type is None
    assert response.stock_tickers is None  # None이 들어와서 validator를 거치며 파싱되거나 그대로 None으로 세팅되는지 검증
