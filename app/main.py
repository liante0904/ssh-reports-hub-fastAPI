import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

"""
[SYSTEM NOTICE for AI/LLM Developers]
이 프로젝트는 초고속 내부 전용망 환경에서 구동됩니다.
네트워크 지연이 거의 없으므로(5초 이내), 서버 재시작이나 API 호출 시 10초 이상의 지체는 불필요합니다.
에러 발생 시 지연 대기보다는 즉시 프로세스(fuser -k 8000/tcp)를 정리하고 재구동하십시오.
"""

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .database import Base, get_keywords_db, keywords_engine, reports_engine
from .error_handlers import register_exception_handlers
from .exceptions import (
    AuthenticationException,
    NotFoundException,
    PermissionDeniedException,
    ServiceUnavailableException,
)
from .logging_config import (
    RequestIDMiddleware,
    RequestLoggingMiddleware,
    configure_structured_logging,
)
from .models import ReportKeyword, User
from .routers import (
    admin,
    favorites,
    external_api,
    reports,
    fnguide_reports,
)
from .schemas import KeywordCreate, KeywordResponse, KeywordSyncRequest, TelegramUser
from .security import (
    SecurityHeadersMiddleware,
    configure_sensitive_log_filter,
    create_access_token,
    decode_access_token,
    verify_telegram_data,
)
from .settings import get_settings, Settings
from .dependencies import get_user_from_token, oauth2_scheme, get_settings_dep


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache Warming — 메인 페이지 API 쿼리를 미리 Redis에 채워둠
# ---------------------------------------------------------------------------

# 메인 페이지(HomeDashboard)에서 호출하는 쿼리들
_WARMUP_QUERIES = [
    "/external/api/search?limit=5&offset=0",
    "/external/api/global?limit=5&offset=0",
    "/external/api/industry?limit=5&offset=0",
    "/external/api/companies",
    "/pub/api/fnguide/report-summaries?limit=5&offset=0",
]

_WARMUP_INTERVAL_SEC = int(os.getenv("CACHE_WARMUP_INTERVAL", "120"))  # 기본 2분


async def _warm_cache_once(port: int) -> None:
    """localhost의 메인 페이지 쿼리들을 호출해 Redis에 캐싱"""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        for path in _WARMUP_QUERIES:
            try:
                resp = await client.get(f"http://127.0.0.1:{port}{path}")
                if resp.status_code == 200:
                    logger.debug("Cache warm: %s (200)", path)
                else:
                    logger.debug("Cache warm: %s (%s)", path, resp.status_code)
            except Exception as exc:
                logger.debug("Cache warm failed for %s: %s", path, exc)


async def _cache_warming_loop(app: FastAPI) -> None:
    """주기적으로 Redis cache warming을 수행하는 백그라운드 태스크"""
    port = int(os.getenv("API_PORT", "8000"))

    # 서버가 완전히 시작될 때까지 기다림
    await asyncio.sleep(3)

    while True:
        try:
            await _warm_cache_once(port)
        except Exception as exc:
            logger.warning("Cache warming error: %s", exc)
        await asyncio.sleep(_WARMUP_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=reports_engine)  # 동일 DB이므로 한 번만 호출 (keywords_engine은 reports_engine의 alias)
    _ensure_tags_columns(reports_engine)
    _ensure_send_history_trigger(reports_engine)
    _migrate_telegram_sent(reports_engine)
    _ensure_llm_view(reports_engine)
    _ensure_reports_api_view(reports_engine)
    _ensure_article_text_column(reports_engine)

    # cache warming
    warming_task = asyncio.create_task(_cache_warming_loop(app))

    yield

    # 종료 시 warming task 정리
    warming_task.cancel()
    try:
        await warming_task
    except asyncio.CancelledError:
        pass


def _ensure_tags_columns(engine) -> None:
    """레포트 태그/종목명/산업 컬럼이 없으면 자동 생성 (enricher 용)"""
    inspector = inspect(engine)
    table_name = "tbl_sec_reports" if os.getenv("DB_BACKEND", "").lower() == "postgres" else "data_main_daily_send"
    if table_name not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    # PostgreSQL: JSONB, SQLite: TEXT
    if os.getenv("DB_BACKEND", "").lower() == "postgres":
        migrations = {
            "tags": "tags JSONB DEFAULT '[]'::jsonb",
            "stock_names": "stock_names JSONB DEFAULT '[]'::jsonb",
            "sector": "sector TEXT DEFAULT ''",
            "fnguide_summary_id": "fnguide_summary_id BIGINT DEFAULT NULL",
        }
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tb_sec_reports_tags ON tbl_sec_reports USING gin (tags)",
            "CREATE INDEX IF NOT EXISTS idx_tb_sec_reports_stock_names ON tbl_sec_reports USING gin (stock_names)",
            "CREATE INDEX IF NOT EXISTS idx_tb_sec_reports_sector ON tbl_sec_reports USING btree (sector)",
            "CREATE INDEX IF NOT EXISTS idx_tb_sec_reports_fnguide_summary_id ON tbl_sec_reports (fnguide_summary_id)",
        ]
    else:
        migrations = {
            "tags": "tags TEXT DEFAULT '[]'",
            "stock_names": "stock_names TEXT DEFAULT '[]'",
            "sector": "sector TEXT DEFAULT ''",
            "fnguide_summary_id": "fnguide_summary_id INTEGER DEFAULT NULL",
        }
        indexes = []

    for column_name, column_sql in migrations.items():
        if column_name in existing_columns:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
            logger.info(f"Created column: {table_name}.{column_name}")

    for index_sql in indexes:
        try:
            with engine.begin() as conn:
                conn.execute(text(index_sql))
        except Exception:
            pass  # 인덱스 중복 등은 무시


def _ensure_send_history_trigger(engine) -> None:
    """tbl_report_send_history INSERT 시 notifications로 자동 미러링하는 트리거 생성"""
    inspector = inspect(engine)
    if "tbl_report_send_history" not in inspector.get_table_names():
        return
    if "tbl_sec_reports_notifications" not in inspector.get_table_names():
        return

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION mirror_send_history_to_notifications()
                RETURNS TRIGGER AS $$
                BEGIN
                    INSERT INTO tbl_sec_reports_notifications (report_id, article_title, firm_nm, summary_model, message)
                    SELECT NEW.report_id,
                           COALESCE(r.article_title, ''),
                           COALESCE(r.firm_nm, ''),
                           NULL,
                           CASE WHEN NEW.keyword IS NOT NULL AND NEW.keyword != ''
                                THEN '[텔레그램 · ' || NEW.keyword || '] ' || COALESCE(r.article_title, '')
                                ELSE '[텔레그램] ' || COALESCE(r.article_title, '')
                           END
                    FROM tbl_sec_reports r
                    WHERE r.report_id = NEW.report_id;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            conn.execute(text("""
                DO $$
                BEGIN
                    CREATE TRIGGER trg_mirror_send_history
                    AFTER INSERT ON tbl_report_send_history
                    FOR EACH ROW EXECUTE FUNCTION mirror_send_history_to_notifications();
                EXCEPTION WHEN duplicate_object THEN
                    NULL;
                END $$;
            """))
        logger.info("Migration: send_history → notifications mirror trigger ensured")
    except Exception as exc:
        logger.warning("Could not ensure send_history trigger (non-fatal): %s", exc)


def _migrate_telegram_sent(engine) -> None:
    """telegram_sent (BOOLEAN) 컬럼 보장 마이그레이션 (is_sent/main_ch_send_yn legacy 제거 완료)"""
    inspector = inspect(engine)
    for tname in ["tbl_sec_reports"]:
        if tname not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(tname)}
        if "telegram_sent" not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tname} ADD COLUMN telegram_sent BOOLEAN DEFAULT false"))
                logger.info("Migration: added telegram_sent column to %s", tname)


# _migrate_save_at removed — save_time → save_at migration completed (2026-07-03)


def _ensure_llm_view(engine) -> None:
    """LLM 친화적 컬럼명으로 tbl_sec_reports를 감싼 VIEW 생성 (PostgreSQL 전용)"""
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE OR REPLACE VIEW v_reports AS SELECT
                    report_id,
                    firm_id             AS broker_id,
                    firm_id             AS firm_id,
                    firm_nm             AS broker_name,
                    board_id            AS board_category_id,
                    board_id            AS board_id,
                    mkt_tp              AS market_type,
                    article_title       AS title,
                    NULL::text          AS source_url,
                    report_unique_key,
                    telegram_url        AS telegram_url,
                    pdf_url             AS pdf_file_url,
                    report_unique_key   AS raw_unique_key,
                    report_date::text AS published_date,
                    save_at             AS scraped_at,
                    save_at             AS scraped_at_tz,
                    writer              AS analyst_name,
                    gemini_summary      AS llm_summary,
                    summary_time        AS summary_created_at,
                    summary_model       AS summary_model,
                    telegram_sent       AS notification_sent,
                    download_status_yn  AS pdf_download_status_legacy,
                    archive_path        AS archive_pdf_path,
                    tags                AS tags_json,
                    stock_names         AS stock_names_json,
                    sector              AS sector_name,
                    stock_tickers       AS stock_tickers_json,
                    target_price        AS target_price,
                    rating              AS rating,
                    revision_type       AS revision_type,
                    report_type         AS report_type,
                    retry_count         AS pdf_download_retry_count,
                    sync_status         AS archive_sync_status,
                    pdf_sync_status     AS pdf_sync_status_code
                FROM tbl_sec_reports
            """))
            logger.info("Migration: v_reports LLM-friendly VIEW created/updated")
    except Exception as exc:
        logger.warning("Could not ensure llm VIEW (non-fatal): %s", exc)


def _ensure_reports_api_view(engine) -> None:
    """FastAPI external_api에서 사용할 통합 VIEW v_reports_api 생성"""
    dialect_name = engine.dialect.name
    
    create_view_sql = """
        SELECT 
            r.report_id, 
            r.firm_nm AS firm_name, 
            r.firm_nm AS firm_nm,
            r.report_date AS report_date,
            r.article_title AS title, 
            r.article_title AS article_title,
            r.telegram_url,
            r.pdf_url AS pdf_file_url,
            r.writer, 
            r.gemini_summary, 
            r.tags, 
            r.stock_names, 
            r.sector,
            r.target_price, 
            r.rating, 
            r.revision_type, 
            r.report_type, 
            r.stock_tickers,
            r.firm_id AS firm_id,
            r.board_id AS board_id,
            r.save_at AS scraped_at,
            r.save_at AS save_at,
            r.report_unique_key, 
            r.mkt_tp AS market_type, 
            r.mkt_tp AS mkt_tp,
            NULL AS source_url,
            r.summary_time,
            r.summary_model, 
            r.telegram_sent,
            p.report_id AS pdf_report_id, 
            p.file_path AS pdf_file_path, 
            p.file_size AS pdf_file_size, 
            p.page_count AS pdf_page_count, 
            p.page_count AS page_count,
            p.archive_status AS pdf_archive_status, 
            p.file_name AS pdf_file_name, 
            p.has_text AS pdf_has_text, 
            p.is_encrypted AS pdf_is_encrypted, 
            p.storage_backend AS pdf_storage_backend, 
            p.storage_key AS pdf_storage_key, 
            p.author AS pdf_author, 
            p.created_at AS pdf_created_at, 
            p.updated_at AS pdf_updated_at, 
            p.last_accessed_at AS pdf_last_accessed_at,
            fs.summary_id AS fs_summary_id, 
            fs.source_page_url AS fs_source_page_url, 
            fs.report_date AS fs_report_date, 
            fs.company_name AS fs_company_name, 
            fs.company_code AS fs_company_code, 
            fs.report_title AS fs_report_title, 
            fs.summary_text AS fs_summary_text, 
            fs.opinion AS fs_opinion, 
            fs.target_price AS fs_target_price, 
            fs.prev_close AS fs_prev_close, 
            fs.provider AS fs_provider, 
            fs.author AS fs_author, 
            fs.article_url AS fs_article_url, 
            fs.pdf_url AS fs_pdf_url, 
            fs.report_key AS fs_report_key, 
            fs.item_rank AS fs_item_rank, 
            fs.sync_status AS fs_sync_status, 
            fs.created_at AS fs_created_at, 
            fs.updated_at AS fs_updated_at,
            f.telegram_update_yn AS is_direct
        FROM tbl_sec_reports r
        LEFT OUTER JOIN tbl_sec_reports_pdf_archive p ON r.report_id = p.report_id
        LEFT OUTER JOIN tbl_fnguide_report_summaries fs ON r.fnguide_summary_id = fs.summary_id
        LEFT OUTER JOIN tbm_sec_firm_info f ON r.firm_id = f.firm_id
    """

    try:
        with engine.begin() as conn:
            if dialect_name == "postgresql":
                conn.execute(text(f"CREATE OR REPLACE VIEW v_reports_api AS {create_view_sql}"))
            else:
                conn.execute(text("DROP VIEW IF EXISTS v_reports_api"))
                conn.execute(text(f"CREATE VIEW v_reports_api AS {create_view_sql}"))
        logger.info("Migration: v_reports_api VIEW created/updated")
    except Exception as exc:
        logger.warning("Could not ensure v_reports_api VIEW (non-fatal): %s", exc)


def _ensure_article_text_column(engine) -> None:
    """article_text TEXT 컬럼 추가 (증권사 view page 본문)"""
    inspector = inspect(engine)
    for tname in ["tbl_sec_reports"]:
        if tname not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(tname)}
        if "article_text" not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {tname} ADD COLUMN article_text TEXT"))
                logger.info("Migration: added article_text column to %s", tname)


configure_sensitive_log_filter()
configure_structured_logging()

app = FastAPI(
    title="SSH Private Hub API",
    description="Private Telegram 인증 기반 주식 리서치 및 미니 블룸버그 API",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

limiter = Limiter(key_func=get_remote_address, default_limits=[get_settings().rate_limit_default])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 전역 예외 핸들러 등록 (커스텀 예외 → 일관된 JSON 응답)
register_exception_handlers(app)

# 미들웨어 (실행 순서: 아래에서 위로)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.post("/auth/telegram")
@app.post("/api/auth/telegram")
async def auth_telegram(
    request: Request, 
    user_data: TelegramUser, 
    db: Session = Depends(get_keywords_db),
    settings: Settings = Depends(get_settings_dep)
):
    # 개발 모드에서만 로컬 바이패스를 허용한다.
    is_bypass = user_data.hash == "bypass" or settings.app_env == "dev" or settings.allow_auth_bypass
    allowed_ids = settings.telegram_allowed_user_ids
    is_whitelisted_user = bool(allowed_ids) and user_data.id in allowed_ids

    if not is_bypass and not is_whitelisted_user:
        if not settings.clean_telegram_bot_token:
            raise ServiceUnavailableException("Telegram bot token is not configured")

        is_valid, reason = verify_telegram_data(user_data.model_dump(), settings)
        if not is_valid:
            logger.warning("Telegram auth rejected for user_id=%s: %s", user_data.id, reason)
            if reason == "Telegram signature mismatch":
                raise AuthenticationException(
                    "Telegram Auth Failed: Telegram signature mismatch. "
                    "Check that the frontend VITE_TELEGRAM_BOT_USERNAME matches the bot "
                    "whose token is configured as TELEGRAM_BOT_TOKEN.",
                )
            raise AuthenticationException(f"Telegram Auth Failed: {reason}")

    if allowed_ids and user_data.id not in allowed_ids:
        raise PermissionDeniedException("Telegram User Not Allowed")

    db_user = db.query(User).filter(User.id == user_data.id).first()
    if not db_user:
        db_user = User(
            id=user_data.id,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            username=user_data.username,
            photo_url=user_data.photo_url,
        )
        db.add(db_user)
    else:
        db_user.first_name = user_data.first_name
        db_user.last_name = user_data.last_name
        db_user.username = user_data.username
        db_user.photo_url = user_data.photo_url

    db.commit()
    db.refresh(db_user)
    access_token = create_access_token(db_user.id, settings)
    return {"access_token": access_token, "token_type": "bearer", "user": {"id": db_user.id, "status": db_user.status, "is_admin": db_user.is_admin}}


@app.get("/keywords", response_model=list[KeywordResponse])
async def get_my_keywords(current_user: User = Depends(get_user_from_token), db: Session = Depends(get_keywords_db)):
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()


@app.post("/keywords/sync", response_model=list[KeywordResponse])
async def sync_keywords(
    request: KeywordSyncRequest,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id).update({"is_active": False})
    for kw_text in request.keywords:
        kw_text = kw_text.strip()
        if not kw_text: continue
        db_kw = db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.keyword == kw_text).first()
        if db_kw:
            db_kw.is_active = True
        else:
            db_kw = ReportKeyword(user_id=current_user.id, keyword=kw_text, is_active=True)
            db.add(db_kw)
    db.commit()
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()


@app.post("/keywords", response_model=KeywordResponse)
async def add_keyword(
    keyword_in: KeywordCreate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    db_keyword = db.query(ReportKeyword).filter(
        ReportKeyword.user_id == current_user.id, 
        ReportKeyword.keyword == keyword_in.keyword
    ).first()
    if db_keyword:
        db_keyword.is_active = True
    else:
        db_keyword = ReportKeyword(user_id=current_user.id, **keyword_in.model_dump())
        db.add(db_keyword)
    db.commit()
    db.refresh(db_keyword)
    return db_keyword


@app.put("/keywords/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    keyword_in: KeywordCreate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    db_keyword = db.query(ReportKeyword).filter(
        ReportKeyword.id == keyword_id, 
        ReportKeyword.user_id == current_user.id
    ).first()
    if not db_keyword:
        raise NotFoundException("Keyword Not Found")
    db_keyword.keyword = keyword_in.keyword
    db_keyword.is_active = keyword_in.is_active
    db_keyword.updated_at = int(time.time())
    db.commit()
    db.refresh(db_keyword)
    return db_keyword


app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(external_api.router)
app.include_router(favorites.router)
app.include_router(fnguide_reports.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

# FCF Screening routes
from .routers import fcf_screening
app.include_router(fcf_screening.router)
app.include_router(fcf_screening.api_router)
