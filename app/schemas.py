from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class SecReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    FIRM_NM: Optional[str] = None
    REG_DT: Optional[str] = None
    ARTICLE_TITLE: Optional[str] = None
    ATTACH_URL: Optional[str] = None
    TELEGRAM_URL: Optional[str] = None
    PDF_URL: Optional[str] = None
    WRITER: Optional[str] = None
    GEMINI_SUMMARY: Optional[str] = None

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
    created_at: int
    updated_at: int

class KeywordSyncRequest(BaseModel):
    keywords: List[str]
