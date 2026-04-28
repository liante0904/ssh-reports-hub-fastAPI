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
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .database import Base, get_keywords_db, keywords_engine, reports_engine
from .models import ReportKeyword, User
from .routers import ords_compat, pub_api, reports
from .schemas import KeywordCreate, KeywordResponse, KeywordSyncRequest, TelegramUser
from .security import (
    SecurityHeadersMiddleware,
    configure_sensitive_log_filter,
    create_access_token,
    decode_access_token,
    verify_telegram_data,
)
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=reports_engine)
    Base.metadata.create_all(bind=keywords_engine)
    yield


settings = get_settings()
configure_sensitive_log_filter()

app = FastAPI(
    title="SSH Reports Hub API",
    description="Telegram 인증 기반 리서치 리포트 조회 및 키워드 알림 API",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/telegram")


async def get_user_from_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_keywords_db)):
    payload = decode_access_token(token, settings)
    user_id = payload["sub"]
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User Not Found")
    return user


@app.post("/auth/telegram")
@limiter.limit(settings.rate_limit_auth)
async def auth_telegram(request: Request, user_data: TelegramUser, db: Session = Depends(get_keywords_db)):
    if not verify_telegram_data(user_data.model_dump(), settings):
        raise HTTPException(status_code=401, detail="Telegram Auth Failed")

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
        if not kw_text:
            continue
        db_keyword = db.query(ReportKeyword).filter(
            ReportKeyword.user_id == current_user.id,
            ReportKeyword.keyword == kw_text,
        ).first()
        if db_keyword:
            db_keyword.is_active = True
        else:
            db_keyword = ReportKeyword(user_id=current_user.id, keyword=kw_text, is_active=True)
            db.add(db_keyword)
    db.commit()
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()


@app.put("/keywords/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(
    keyword_id: int,
    keyword_in: KeywordCreate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db),
):
    db_keyword = db.query(ReportKeyword).filter(
        ReportKeyword.id == keyword_id,
        ReportKeyword.user_id == current_user.id,
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
app.include_router(pub_api.router)
app.include_router(ords_compat.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
