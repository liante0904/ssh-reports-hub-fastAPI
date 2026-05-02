import os
import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, ForeignKey, DateTime, Float, func, Text
from sqlalchemy.orm import relationship
from .database import Base

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# DB 설정에 따라 테이블 이름 결정
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
MAIN_TABLE_NAME = "tbl_sec_reports" if DB_BACKEND == "postgres" else "data_main_daily_send"

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
    notes = relationship("InvestmentNote", back_populates="owner", cascade="all, delete-orphan")

class ReportKeyword(Base, TimestampMixin):
    __tablename__ = "tbm_sec_reports_alert_keywords"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbm_sec_reports_telegram_users.id"))
    keyword = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    owner = relationship("User", back_populates="keywords")

class SecReport(Base):
    __tablename__ = MAIN_TABLE_NAME
    report_id = Column(BigInteger, primary_key=True, index=True)
    sec_firm_order = Column(Integer)
    article_board_order = Column(Integer)
    firm_nm = Column(String)
    article_title = Column(String)
    article_url = Column(String)
    main_ch_send_yn = Column(String)
    download_status_yn = Column(String, default="")
    download_url = Column(String)
    save_time = Column(String)
    reg_dt = Column(String, default="")
    writer = Column(String, default="")
    key = Column(String, unique=True)
    telegram_url = Column(String, default="")
    mkt_tp = Column(String, default="KR")
    gemini_summary = Column(String, nullable=True)
    summary_time = Column(String, nullable=True)
    summary_model = Column(String, nullable=True)
    archive_path = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    sync_status = Column(Integer, default=0)
    pdf_url = Column(String, default="")
    pdf_sync_status = Column(Integer, default=0)
    
    # 발송 이력과의 관계
    sent_histories = relationship("ReportSentHistory", back_populates="report")

class SecFirmInfo(Base):
    __tablename__ = "tbm_sec_firm_info"
    sec_firm_order = Column(Integer, primary_key=True)
    sec_firm_name = Column("firm_nm", String, nullable=False)
    is_direct_link = Column("telegram_update_yn", String, default="N")
    description = Column("COMMENT_PDF_URL", String, nullable=True)

class InvestmentNote(Base, TimestampMixin):
    __tablename__ = "investment_notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbm_sec_reports_telegram_users.id"), nullable=False)
    content = Column(Text, default="")
    color_bg = Column(String(20))
    color_border = Column(String(20))
    x_pos = Column(Integer, default=100)
    y_pos = Column(Integer, default=100)
    width = Column(Integer, default=250)
    height = Column(Integer, default=220)
    z_index = Column(Integer, default=10)

    owner = relationship("User", back_populates="notes")

class ReportSentHistory(Base):
    __tablename__ = "tbl_report_send_history"
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(BigInteger, ForeignKey(f"{MAIN_TABLE_NAME}.report_id"))
    user_id = Column(BigInteger)
    keyword = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    
    report = relationship("SecReport", back_populates="sent_histories")


class ConsensusHistory(Base):
    __tablename__ = "tbm_consensus_history"

    code = Column(String, primary_key=True)
    date = Column(DateTime, primary_key=True)
    target_period = Column(String, primary_key=True)

    name = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    current_price = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    per = Column(Float, nullable=True)
    pbr = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    operating_profit = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    sales = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)
    rev_1m = Column(Float, nullable=True)
    rev_3m = Column(Float, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
