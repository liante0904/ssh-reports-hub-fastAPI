from datetime import datetime
import re
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class FnGuideReportDateResponse(BaseModel):
    report_date: str
    report_count: int

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

class ConsensusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    date: datetime
    target_period: str
    sector: Optional[str] = None
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    operating_profit: Optional[float] = None
    operating_profit_prev: Optional[float] = None
    operating_profit_revision: Optional[float] = None
    net_income: Optional[float] = None
    net_income_prev: Optional[float] = None
    net_income_revision: Optional[float] = None
    sales: Optional[float] = None
    sales_prev: Optional[float] = None
    sales_revision: Optional[float] = None
    eps: Optional[float] = None
    eps_prev: Optional[float] = None
    eps_revision: Optional[float] = None
    rev_1m: Optional[float] = None
    rev_3m: Optional[float] = None
    updated_at: datetime

class ConsensusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime
    rev_1m: Optional[float] = None
    rev_3m: Optional[float] = None
    current_price: Optional[float] = None
    operating_profit: Optional[float] = None
    net_income: Optional[float] = None
    sales: Optional[float] = None
    eps: Optional[float] = None

class ConsensusSectorResponse(BaseModel):
    sector: str
    stock_count: int
    avg_rev_1m: float
    avg_rev_3m: float

class ConsensusSummaryResponse(BaseModel):
    total: int
    up_count: int
    down_count: int
    latest_date: datetime

class InvestmentNoteBase(BaseModel):
    content: Optional[str] = ""
    color_bg: Optional[str] = None
    color_border: Optional[str] = None
    x_pos: int = 100
    y_pos: int = 100
    width: int = 250
    height: int = 220
    z_index: int = 10
    parent_id: Optional[int] = None

    @field_validator("x_pos", "y_pos")
    @classmethod
    def check_coordinates(cls, v: int) -> int:
        if not (0 <= v <= 5000):
            raise ValueError("Coordinates must be between 0 and 5000")
        return v

    @field_validator("width", "height")
    @classmethod
    def check_size(cls, v: int) -> int:
        if not (120 <= v <= 800):
            raise ValueError("Size must be between 120 and 800")
        return v

    @field_validator("color_bg", "color_border")
    @classmethod
    def check_color_hex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", v):
            raise ValueError("Color must be a valid HEX code (e.g., #FFFFFF or #FFF)")
        return v

class InvestmentNoteCreate(InvestmentNoteBase):
    pass

class InvestmentNoteUpdate(BaseModel):
    content: Optional[str] = None
    color_bg: Optional[str] = None
    color_border: Optional[str] = None
    x_pos: Optional[int] = None
    y_pos: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    z_index: Optional[int] = None
    parent_id: Optional[int] = None

class InvestmentNoteResponse(InvestmentNoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class MarketSentimentIndicatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    title: str
    category: str
    description: Optional[str] = None
    value: float
    unit: str
    score: float
    status: str
    source: Optional[str] = None
    sort_order: int
    updated_at: datetime


class MarketSentimentSummaryResponse(BaseModel):
    composite_score: float
    status_label: str
    overheat_count: int
    neutral_count: int
    fear_count: int
    latest_update: datetime


class CNNFearGreedIndicatorResponse(BaseModel):
    key: str
    score: float
    rating: str
    title: Optional[str] = None


class CNNFearGreedLatestResponse(BaseModel):
    score: float
    rating: str
    timestamp: datetime
    history: dict
    indicators: dict[str, CNNFearGreedIndicatorResponse]


class CNNFearGreedSnapshotResponse(BaseModel):
    id: int
    source: str
    snapshot_ts: datetime
    score: float
    rating: str
    history: dict
    indicators: dict[str, CNNFearGreedIndicatorResponse]
    fetched_at: datetime


class CNNFearGreedDailySnapshotResponse(BaseModel):
    id: int
    source: str
    snapshot_date: str
    snapshot_ts: datetime
    score: float
    rating: str
    history: dict
    indicators: dict[str, CNNFearGreedIndicatorResponse]
    fetched_at: datetime


class DartDisclosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    published_at: datetime
    company_name: str
    company_code: Optional[str] = None
    disclosure_title: str
    disclosure_type: str
    insider_name: Optional[str] = None
    insider_role: Optional[str] = None
    transaction_type: str
    shares: Optional[float] = None
    amount: Optional[float] = None
    avg_price: Optional[float] = None
    ownership_after: Optional[float] = None
    signal_score: float
    summary_text: Optional[str] = None
    dart_url: Optional[str] = None
    telegram_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    fetched_at: datetime


class DartDisclosureSummaryResponse(BaseModel):
    total_count: int
    buy_count: int
    sell_count: int
    insider_buy_count: int
    executive_buy_count: int
    net_buy_amount: float
    latest_update: datetime
