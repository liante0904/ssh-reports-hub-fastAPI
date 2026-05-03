import os
import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, ForeignKey, Date, DateTime, Float, func, Text, UniqueConstraint
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


class FnGuideReportSummary(Base, TimestampMixin):
    __tablename__ = "tbl_fnguide_report_summaries"

    summary_id = Column(BigInteger, primary_key=True, index=True)
    source_page_url = Column(String, nullable=False, default="")
    report_date = Column(String, index=True, nullable=False, default="")
    company_name = Column(String, index=True, nullable=False)
    company_code = Column(String, index=True, nullable=True)
    report_title = Column(String, nullable=False)
    summary_text = Column(Text, nullable=True)
    opinion = Column(String, nullable=True)
    target_price = Column(String, nullable=True)
    prev_close = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    author = Column(String, nullable=True)
    article_url = Column(String, nullable=True)
    pdf_url = Column(String, nullable=True)
    report_key = Column(String, unique=True, index=True, nullable=False)
    item_rank = Column(Integer, nullable=True)
    sync_status = Column(Integer, default=0)


class SecFirmInfo(Base):
    __tablename__ = "tbm_sec_firm_info"
    sec_firm_order = Column(Integer, primary_key=True)
    sec_firm_name = Column("firm_nm", String, nullable=False)
    is_direct_link = Column("telegram_update_yn", String, default="N")
    description = Column("COMMENT_PDF_URL", String, nullable=True)


class SecBoardInfo(Base):
    __tablename__ = "tbm_sec_firm_board_info"
    sec_firm_order = Column(Integer, primary_key=True)
    article_board_order = Column(Integer, primary_key=True)
    board_nm = Column(String)
    board_cd = Column(String, nullable=True)
    label_nm = Column(String, nullable=True)


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
    parent_id = Column(Integer, nullable=True, index=True)

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


class MarketSentimentIndicator(Base):
    __tablename__ = "tbm_market_sentiment_indicators"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, default="general")
    description = Column(Text, nullable=True)
    value = Column(Float, nullable=False, default=0.0)
    unit = Column(String, nullable=False, default="pt")
    score = Column(Float, nullable=False, default=0.0)
    status = Column(String, nullable=False, default="neutral")
    source = Column(String, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class MarketSentimentSnapshot(Base):
    __tablename__ = "tbm_market_sentiment_snapshots"
    __table_args__ = (
        UniqueConstraint("source", "snapshot_ts", name="uq_market_sentiment_snapshot_source_ts"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False, default="cnn", index=True)
    snapshot_ts = Column(DateTime(timezone=True), nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    rating = Column(String, nullable=False, default="neutral")
    history_json = Column(Text, nullable=False, default="{}")
    indicators_json = Column(Text, nullable=False, default="{}")
    raw_json = Column(Text, nullable=False, default="{}")
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketSentimentDailySnapshot(Base):
    __tablename__ = "tbm_market_sentiment_daily_snapshots"
    __table_args__ = (
        UniqueConstraint("source", "snapshot_date", name="uq_market_sentiment_daily_snapshot_source_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False, default="cnn", index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    snapshot_ts = Column(DateTime(timezone=True), nullable=False)
    score = Column(Float, nullable=False, default=0.0)
    rating = Column(String, nullable=False, default="neutral")
    history_json = Column(Text, nullable=False, default="{}")
    indicators_json = Column(Text, nullable=False, default="{}")
    raw_json = Column(Text, nullable=False, default="{}")
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DartDisclosure(Base):
    __tablename__ = "tbm_dart_disclosures"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, nullable=False, default="dart", index=True)
    published_at = Column(DateTime(timezone=True), nullable=False, index=True)
    company_name = Column(String, nullable=False, index=True)
    company_code = Column(String, nullable=True, index=True)
    disclosure_title = Column(String, nullable=False)
    disclosure_type = Column(String, nullable=False, default="공시")
    insider_name = Column(String, nullable=True)
    insider_role = Column(String, nullable=True)
    transaction_type = Column(String, nullable=False, default="buy")
    shares = Column(Float, nullable=True)
    amount = Column(Float, nullable=True)
    avg_price = Column(Float, nullable=True)
    ownership_after = Column(Float, nullable=True)
    signal_score = Column(Float, nullable=False, default=0.0)
    summary_text = Column(Text, nullable=True)
    dart_url = Column(String, nullable=True)
    telegram_url = Column(String, nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
