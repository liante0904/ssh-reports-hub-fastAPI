import time
from sqlalchemy import Column, Integer, String, Boolean, BigInteger, LargeBinary, ForeignKey, Date, DateTime, Float, Numeric, func, Text, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from .database import Base

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# DB 설정에 따라 테이블 이름 결정
# 2026-06-11: 옛 컬럼 드랍 시 v_sec_reports_full 뷰로 전환 예정.
#   뷰는 SELECT 전용이므로 ORM write(report.fnguide_summary_id=...)는
#   raw SQL로 마이그레이션하거나, tbl_sec_reports에 직접 쓰도록 유지.
#   참조: ~/workspace/external.reports-hub/docs/DB_MIGRATION_STATUS.md
MAIN_TABLE_NAME = "tbl_sec_reports"
# MAIN_TABLE_NAME = "v_sec_reports_full"  # ← 옛 컬럼 드랍 후 활성화

class User(Base):
    __tablename__ = "tbl_sec_reports_telegram_users"
    id = Column(BigInteger, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, default="pending")  # 관리자 승인 전까지 pending
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
    
    # ── 프리미엄 5대 속성 컬럼 내재화 ──────────────────
    target_price = Column(Numeric, nullable=True)  # 목표주가
    rating = Column(String, nullable=True)         # 투자의견 (BUY, HOLD 등)
    revision_type = Column(String, nullable=True)  # 목표가 변동 성격 (UPGRADE, DOWNGRADE 등)
    report_type = Column(String, nullable=True)    # 리포트 분류 (COMPANY, INDUSTRY 등)
    stock_tickers = Column(String, default="[]")   # 6자리 표준 종목코드 JSON 배열
    # ──────────────────────────────────────────────────
    
    # FnGuide 요약 리포트 매칭 ID
    fnguide_summary_id = Column(BigInteger, ForeignKey("tbl_fnguide_report_summaries.summary_id", ondelete="SET NULL"), nullable=True)
    
    # 발송 이력과의 관계
    sent_histories = relationship("ReportSentHistory", back_populates="report")

    # PDF 아카이브와의 관계 (1:1, report_id 기준)
    pdf_archive = relationship("PdfArchive", uselist=False, back_populates="report", foreign_keys="PdfArchive.report_id")

    # FnGuide 요약 리포트와의 관계 (N:1, fnguide_summary_id 기준)
    fnguide_summary = relationship("FnGuideReportSummary", foreign_keys=[fnguide_summary_id], back_populates="sec_reports")


class FnGuideReportSummary(Base, TimestampMixin):
    """FnGuide에서 수집한 종목별 요약 리포트 엔터티"""
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

    # SecReport 들과의 관계 (1:N 역방향 관계)
    sec_reports = relationship("SecReport", foreign_keys="[SecReport.fnguide_summary_id]", back_populates="fnguide_summary")


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
    description = Column("comment_pdf_url", String, nullable=True)  # 2026-06-11: 소문자로 마이그레이션 완료


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


class ReportNotification(Base, TimestampMixin):
    __tablename__ = "tbl_sec_reports_notifications"
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(BigInteger, ForeignKey(f"tbl_sec_reports.report_id", ondelete="CASCADE"), nullable=False)
    article_title = Column(String, nullable=False)
    firm_nm = Column(String, nullable=True)
    summary_model = Column(String, nullable=True)  # deepseek or gemini
    message = Column(Text, nullable=False)

