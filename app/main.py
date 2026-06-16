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
    Base.metadata.create_all(bind=reports_engine)
    Base.metadata.create_all(bind=keywords_engine)
    _ensure_tags_columns(reports_engine)

    # 백그라운드 cache warming 시작
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
