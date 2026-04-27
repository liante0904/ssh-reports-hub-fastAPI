import os
import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .database import Base

# DB 설정에 따라 테이블 이름 결정
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
MAIN_TABLE_NAME = "TB_SEC_REPORTS" if DB_BACKEND == "postgres" else "data_main_daily_send"

class User(Base):
    __tablename__ = "tbm_sec_reports_telegram_users"
    id = Column(BigInteger, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, default="active")
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    keywords = relationship("ReportKeyword", back_populates="owner")

class ReportKeyword(Base):
    __tablename__ = "tbm_sec_reports_alert_keywords"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbm_sec_reports_telegram_users.id"))
    keyword = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="keywords")

class SecReport(Base):
    __tablename__ = MAIN_TABLE_NAME
    report_id = Column(BigInteger, primary_key=True, index=True)
    sec_firm_order = Column(Integer)
    article_board_order = Column(Integer)
    FIRM_NM = Column(String)
    REG_DT = Column(String)
    ARTICLE_TITLE = Column(String)
    ARTICLE_URL = Column(String)
    MAIN_CH_SEND_YN = Column(String)
    DOWNLOAD_URL = Column(String)
    TELEGRAM_URL = Column(String)
    PDF_URL = Column(String)
    WRITER = Column(String)
    MKT_TP = Column(String)
    KEY = Column(String, unique=True)
    SAVE_TIME = Column(String)
    GEMINI_SUMMARY = Column(String, nullable=True)
    SUMMARY_TIME = Column(String, nullable=True)
    SUMMARY_MODEL = Column(String, nullable=True)
    
    # 발송 이력과의 관계
    sent_histories = relationship("ReportSentHistory", back_populates="report")

class ReportSentHistory(Base):
    __tablename__ = "tbl_report_send_history"
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(BigInteger, ForeignKey(f"{MAIN_TABLE_NAME}.report_id"))
    user_id = Column(BigInteger)
    keyword = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    
    report = relationship("SecReport", back_populates="sent_histories")
