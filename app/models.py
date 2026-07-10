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
    """
    증권사 리포트 마스터. 283,933 rows. SSoT: docs/schema.sql.

    Component ownership (이 클래스의 컬럼을 누가 쓰는지):
      [Scraper]       INSERT  report_id, report_unique_key, firm_id, board_id,
                              firm_nm, article_title, writer,
                              report_date, save_at, mkt_tp, telegram_url, pdf_url
      [Enricher]      UPDATE  tags, stock_names, stock_tickers, sector,
                              gemini_summary, summary_time, summary_model,
                              target_price, rating, revision_type, report_type
      [FnGuide]       UPDATE  fnguide_summary_id
      [Scheduler]     UPDATE  telegram_sent
      [PDF-Archiver]  UPDATE  download_status_yn, pdf_sync_status, pdf_hash,
                              archive_path, retry_count, sync_status

    jsonb-as-String columns (DB는 jsonb, ORM은 String — parse before use):
      tags, stock_names, stock_tickers

    Data density (non-NULL ratio):
      Scraper core: 100% | Enricher tags: 1.2% | AI summary: 0.13% | Premium: 2.5%
    """
    __tablename__ = MAIN_TABLE_NAME

    # -- [Scraper] INSERT columns --
    report_id = Column(BigInteger, primary_key=True, index=True)
    firm_id = Column(Integer)
    board_id = Column(Integer)
    firm_nm = Column(String)
    article_title = Column(String)
    writer = Column(String, default="")
    report_date = Column(Date, nullable=True)
    save_at = Column(DateTime(timezone=True))
    mkt_tp = Column(String, default="KR")
    telegram_url = Column(String, default="")
    pdf_file_url = Column("pdf_url", String, default="")  # DB: pdf_url, API: pdf_file_url
    report_unique_key = Column(String, unique=True)

    @property
    def source_url(self):
        """Legacy API attribute; article_url is no longer a physical report column."""
        return None

    # -- [Scheduler] UPDATE --
    telegram_sent = Column(Boolean, default=False)

    # -- [Enricher-Tags] UPDATE --
    tags = Column(String, default="[]")            # jsonb array
    stock_names = Column(String, default="[]")     # jsonb array
    stock_tickers = Column(String, default="[]")   # jsonb array
    sector = Column(String, default="")

    # -- [Enricher-AI] UPDATE --
    gemini_summary = Column(String, nullable=True)
    summary_time = Column(String, nullable=True)
    summary_model = Column(String, nullable=True)

    # -- [Enricher-Premium] UPDATE --
    target_price = Column(Numeric, nullable=True)      # 목표주가
    rating = Column(String, nullable=True)             # BUY/HOLD/SELL
    revision_type = Column(String, nullable=True)      # UPGRADE/DOWNGRADE
    report_type = Column(String, nullable=True)        # COMPANY/INDUSTRY/MACRO

    # -- [FnGuide] UPDATE --
    fnguide_summary_id = Column(BigInteger, ForeignKey("tbl_fnguide_report_summaries.summary_id", ondelete="SET NULL"), nullable=True)

    # -- [PDF-Archiver] UPDATE --
    download_status_yn = Column(String, default="")
    pdf_sync_status = Column(Integer, default=0)
    archive_path = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    sync_status = Column(Integer, default=0)

    # -- [Other] --
    article_text = Column(Text, nullable=True)     # 증권사 view page 본문 텍스트

    # Relationships
    sent_histories = relationship("ReportSentHistory", back_populates="report")
    pdf_archive = relationship("PdfArchive", uselist=False, back_populates="report", foreign_keys="PdfArchive.report_id")
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
    telegram_url = Column(Text, nullable=True)
    key = Column(Text, nullable=True)
    archive_status = Column(Text, nullable=True)
    file_name = Column(Text, nullable=True)
    download_status_yn = Column(Text, nullable=True)
    sync_status = Column(Integer, nullable=True, default=0)
    retry_count = Column(Integer, nullable=True, default=0)
    firm_nm = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    report_date = Column(Text, nullable=True)
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
    firm_id = Column(Integer, primary_key=True)
    sec_firm_name = Column("firm_nm", String, nullable=False)
    is_direct_link = Column("telegram_update_yn", String, default="N")
    description = Column("comment_pdf_url", String, nullable=True)  # 2026-06-11: 소문자로 마이그레이션 완료


class SecBoardInfo(Base):
    __tablename__ = "tbm_sec_firm_board_info"
    firm_id = Column(Integer, primary_key=True)
    board_id = Column(Integer, primary_key=True)
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


class NotificationRead(Base, TimestampMixin):
    """종버튼 알림 읽음 상태 (localStorage → DB 마이그레이션)"""
    __tablename__ = "tbl_notification_reads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    notification_key = Column(String, nullable=False)  # telegram:12345 or summary:12345
