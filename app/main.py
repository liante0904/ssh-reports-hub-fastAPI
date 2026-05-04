import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
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
from .models import ReportKeyword, User
from .routers import (
    cnn_sentiment,
    consensus,
    disclosure,
    fnguide_reports,
    notes,
    ords_compat,
    reports,
    sentiment,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=reports_engine)
    Base.metadata.create_all(bind=keywords_engine)
    _ensure_investment_note_layout_columns(keywords_engine)
    sentiment.seed_mock_sentiment_indicators(reports_engine)
    disclosure.seed_mock_disclosures(reports_engine)
    yield


def _ensure_investment_note_layout_columns(engine) -> None:
    inspector = inspect(engine)
    if "investment_notes" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("investment_notes")}
    migrations = {
        "width": "width INTEGER DEFAULT 250",
        "height": "height INTEGER DEFAULT 220",
        "parent_id": "parent_id INTEGER",
    }

    for column_name, column_sql in migrations.items():
        if column_name in existing_columns:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE investment_notes ADD COLUMN {column_sql}"))


configure_sensitive_log_filter()

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

app.add_middleware(SecurityHeadersMiddleware)
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
            raise HTTPException(status_code=503, detail="Telegram bot token is not configured")

        is_valid, reason = verify_telegram_data(user_data.model_dump(), settings)
        if not is_valid:
            logger.warning("Telegram auth rejected for user_id=%s: %s", user_data.id, reason)
            if reason == "Telegram signature mismatch":
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "Telegram Auth Failed: Telegram signature mismatch. "
                        "Check that the frontend VITE_TELEGRAM_BOT_USERNAME matches the bot "
                        "whose token is configured as TELEGRAM_BOT_TOKEN."
                    ),
                )
            raise HTTPException(status_code=401, detail=f"Telegram Auth Failed: {reason}")

    if allowed_ids and user_data.id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Telegram User Not Allowed")

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
    return {"access_token": access_token, "token_type": "bearer", "user": {"id": db_user.id, "status": db_user.status}}


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
        raise HTTPException(status_code=404, detail="Not Found")
    db_keyword.keyword = keyword_in.keyword
    db_keyword.is_active = keyword_in.is_active
    db_keyword.updated_at = int(time.time())
    db.commit()
    db.refresh(db_keyword)
    return db_keyword


app.include_router(reports.router)
app.include_router(fnguide_reports.router)
app.include_router(ords_compat.router)
app.include_router(consensus.router)
app.include_router(notes.router)
app.include_router(notes.api_router)
app.include_router(sentiment.router)
app.include_router(sentiment.api_router)
app.include_router(cnn_sentiment.router)
app.include_router(cnn_sentiment.api_router)
app.include_router(disclosure.router)
app.include_router(disclosure.api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
