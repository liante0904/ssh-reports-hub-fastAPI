from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

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

class CompanyResponse(BaseModel):
    name: str
    is_direct: bool
    note: Optional[str] = None
    report_count: int

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
