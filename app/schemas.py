import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator

class PdfArchiveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    pdf_url: Optional[str] = None
    download_url: Optional[str] = None
    telegram_url: Optional[str] = None
    key: Optional[str] = None
    archive_status: Optional[str] = None
    file_name: Optional[str] = None
    download_status_yn: Optional[str] = None
    sync_status: Optional[int] = None
    retry_count: Optional[int] = None
    firm_nm: Optional[str] = None
    title: Optional[str] = None
    reg_dt: Optional[str] = None
    pdf_sync_status: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    author: Optional[str] = None
    has_text: Optional[bool] = None
    is_encrypted: Optional[bool] = None
    storage_backend: Optional[str] = None
    storage_key: Optional[str] = None
    last_accessed_at: Optional[datetime] = None


class FnGuideMatchedReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    report_id: int
    firm_nm: str
    article_title: str
    pdf_url: Optional[str] = None
    download_url: Optional[str] = None
    telegram_url: Optional[str] = None


class FnGuideReportSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_id: int
    source_page_url: str
    report_date: str
    company_name: str
    company_code: Optional[str] = None
    report_title: str
    summary_text: Optional[str] = None
    opinion: Optional[str] = None
    target_price: Optional[str] = None
    prev_close: Optional[str] = None
    provider: Optional[str] = None
    author: Optional[str] = None
    article_url: Optional[str] = None
    pdf_url: Optional[str] = None
    report_key: str
    item_rank: Optional[int] = None
    sync_status: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    sec_reports: Optional[list[FnGuideMatchedReportResponse]] = []


class FnGuideReportDateResponse(BaseModel):
    report_date: str
    report_count: int


class SecReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    firm_nm: Optional[str] = None
    is_direct: Optional[bool] = None
    reg_dt: Optional[str] = None
    article_title: Optional[str] = None
    telegram_url: Optional[str] = None
    pdf_url: Optional[str] = None
    writer: Optional[str] = None
    gemini_summary: Optional[str] = None
    tags: Optional[list[str]] = None
    stock_names: Optional[list[str]] = None
    sector: Optional[str] = None
    
    # ── 프리미엄 5대 속성 스키마 선언 ──────────────────
    target_price: Optional[float] = None          # 목표주가
    rating: Optional[str] = None                  # 투자의견 (BUY, HOLD 등)
    revision_type: Optional[str] = None           # 목표가 변동 성격 (UPGRADE, DOWNGRADE 등)
    report_type: Optional[str] = None             # 리포트 분류 (COMPANY, INDUSTRY 등)
    stock_tickers: Optional[list[str]] = None     # 6자리 표준 종목코드 리스트
    # ──────────────────────────────────────────────────
    
    pdf_archive: Optional[PdfArchiveResponse] = None
    fnguide_summary: Optional[FnGuideReportSummaryResponse] = None

    @field_validator("tags", "stock_names", "stock_tickers", mode="before")
    @classmethod
    def parse_json_array(cls, v):
        """DB에서 문자열로 저장된 JSON 배열을 list로 변환"""
        if v is None:
            return None
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []


class CompanyResponse(BaseModel):
    name: str
    is_direct: bool
    note: Optional[str] = None
    report_count: int

class BoardResponse(BaseModel):
    sec_firm_order: int
    article_board_order: int
    board_nm: str
    label_nm: Optional[str] = None
    report_count: int = 0

class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class KeywordBase(BaseModel):
    keyword: str
    is_active: bool = True

class KeywordCreate(KeywordBase):
    pass

class KeywordResponse(KeywordBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

class KeywordSyncRequest(BaseModel):
    keywords: List[str]
