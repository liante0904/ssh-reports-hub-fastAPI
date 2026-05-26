import os
import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, LargeBinary, ForeignKey, Date, DateTime, Float, Numeric, func, Text, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from .database import Base

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# DB 설정에 따라 테이블 이름 결정
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()
MAIN_TABLE_NAME = "tbl_sec_reports" if DB_BACKEND == "postgres" else "data_main_daily_send"

class User(Base):
    __tablename__ = "tbl_sec_reports_telegram_users"
    id = Column(BigInteger, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, default="active")
    is_admin = Column(Boolean, default=False)
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    keywords = relationship("ReportKeyword", back_populates="owner")
    favorites = relationship("ReportFavorite", back_populates="owner", cascade="all, delete-orphan")


class ReportFavorite(Base):
    __tablename__ = "tbl_sec_reports_favorites"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbl_sec_reports_telegram_users.id", ondelete="CASCADE"), nullable=False)
    report_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User", back_populates="favorites")
    __table_args__ = (
        UniqueConstraint("user_id", "report_id", name="uq_user_report_favorite"),
        Index("idx_favorites_user_id", "user_id"),
        Index("idx_favorites_report_id", "report_id"),
    )

class ReportKeyword(Base, TimestampMixin):
    __tablename__ = "tbl_sec_reports_alert_keywords"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("tbl_sec_reports_telegram_users.id"))
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
    tags = Column(String, default="[]")         # JSON array of tags
    stock_names = Column(String, default="[]")  # JSON array of stock names
    sector = Column(String, default="")         # industry sector
    
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


class ReportSentHistory(Base):
    __tablename__ = "tbl_report_send_history"
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(BigInteger, ForeignKey(f"{MAIN_TABLE_NAME}.report_id"))
    user_id = Column(BigInteger)
    keyword = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    
    report = relationship("SecReport", back_populates="sent_histories")
