import os
import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, LargeBinary, ForeignKey, Date, DateTime, Float, func, Text, UniqueConstraint, Index
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
    is_admin = Column(Boolean, default=False)
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    keywords = relationship("ReportKeyword", back_populates="owner")
    notes = relationship("InvestmentNote", back_populates="owner", cascade="all, delete-orphan")
    favorites = relationship("ReportFavorite", back_populates="owner", cascade="all, delete-orphan")


class ReportFavorite(Base):
    __tablename__ = "tbm_sec_reports_favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbm_sec_reports_telegram_users.id", ondelete="CASCADE"), nullable=False)
    report_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User", back_populates="favorites")
    __table_args__ = (
        UniqueConstraint("user_id", "report_id", name="uq_user_report_favorite"),
        Index("idx_favorites_user_id", "user_id"),
        Index("idx_favorites_report_id", "report_id"),
    )

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

    # PDF 아카이브와의 관계 (1:1, report_id 기준)
    pdf_archive = relationship("PdfArchive", uselist=False, back_populates="report", foreign_keys="PdfArchive.report_id")


class PdfArchive(Base):
    """PDF 아카이버 - 리포트 PDF 파일의 메타데이터 및 스토리지 정보"""
    __tablename__ = "tbl_sec_reports_pdf_archive"

    report_id = Column(BigInteger, ForeignKey(f"{MAIN_TABLE_NAME}.report_id"), primary_key=True)
    file_path = Column(Text, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    page_count = Column(Integer, nullable=True)
    pdf_url = Column(Text, nullable=True)
    download_url = Column(Text, nullable=True)
    telegram_url = Column(Text, nullable=True)
    key = Column(Text, nullable=True)
    archive_status = Column(Text, nullable=True)
    file_name = Column(Text, nullable=True)
    download_status_yn = Column(Text, nullable=True)
    sync_status = Column(Integer, nullable=True, default=0)
    retry_count = Column(Integer, nullable=True, default=0)
    firm_nm = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    reg_dt = Column(Text, nullable=True)
    pdf_sync_status = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    pdf_hash = Column(LargeBinary, nullable=True)
    author = Column(Text, nullable=True)
    has_text = Column(Boolean, nullable=True)
    is_encrypted = Column(Boolean, nullable=True)
    storage_backend = Column(Text, nullable=True)
    storage_key = Column(Text, nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    # 리포트와의 관계
    report = relationship("SecReport", back_populates="pdf_archive", foreign_keys=[report_id])


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
