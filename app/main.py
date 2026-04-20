import time
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.extension import _rate_limit_exceeded_handler
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .database import engine, Base, get_db
from .models import User, ReportKeyword, SecReport, ReportSentHistory
from .schemas import TelegramUser, KeywordResponse, KeywordSyncRequest, KeywordCreate, SecReportResponse
from .security import (
    SecurityHeadersMiddleware,
    configure_sensitive_log_filter,
    create_access_token,
    decode_access_token,
    verify_telegram_data,
)
from .settings import get_settings

# 데이터베이스 테이블 초기화 (애플리케이션 시작 시점에만 실행)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 테이블 생성
    Base.metadata.create_all(bind=engine)
    yield
    # 앱 종료 시 필요한 정리 작업이 있다면 여기서 수행

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

# Middleware order matters: CORS is registered last so it wraps redirect/error responses.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=[],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/telegram")

async def get_user_from_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_access_token(token, settings)
    user_id = payload["sub"]
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User Not Found")
    return user

# --- 엔드포인트 ---

@app.post("/auth/telegram")
@limiter.limit(settings.rate_limit_auth)
async def auth_telegram(request: Request, user_data: TelegramUser, db: Session = Depends(get_db)):
    if not verify_telegram_data(user_data.model_dump(), settings):
        raise HTTPException(status_code=401, detail="Telegram Auth Failed")
    
    db_user = db.query(User).filter(User.id == user_data.id).first()
    if not db_user:
        db_user = User(id=user_data.id, first_name=user_data.first_name, last_name=user_data.last_name, 
                       username=user_data.username, photo_url=user_data.photo_url)
        db.add(db_user)
    else:
        db_user.first_name, db_user.last_name, db_user.username, db_user.photo_url = \
            user_data.first_name, user_data.last_name, user_data.username, user_data.photo_url
    
    db.commit()
    db.refresh(db_user)
    access_token = create_access_token(db_user.id, settings)
    return {"access_token": access_token, "token_type": "bearer", "user": {"id": db_user.id, "status": db_user.status}}

@app.get("/keywords", response_model=list[KeywordResponse])
async def get_my_keywords(current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)):
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()

@app.post("/keywords/sync", response_model=list[KeywordResponse])
async def sync_keywords(request: KeywordSyncRequest, current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)):
    db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id).update({"is_active": False})
    for kw_text in request.keywords:
        kw_text = kw_text.strip()
        if not kw_text: continue
        db_keyword = db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.keyword == kw_text).first()
        if db_keyword: db_keyword.is_active = True
        else:
            db_keyword = ReportKeyword(user_id=current_user.id, keyword=kw_text, is_active=True)
            db.add(db_keyword)
    db.commit()
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()

@app.put("/keywords/{keyword_id}", response_model=KeywordResponse)
async def update_keyword(keyword_id: int, keyword_in: KeywordCreate, current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)):
    db_keyword = db.query(ReportKeyword).filter(ReportKeyword.id == keyword_id, ReportKeyword.user_id == current_user.id).first()
    if not db_keyword: raise HTTPException(status_code=404, detail="Not Found")
    db_keyword.keyword, db_keyword.is_active, db_keyword.updated_at = keyword_in.keyword, keyword_in.is_active, int(time.time())
    db.commit()
    db.refresh(db_keyword)
    return db_keyword

@app.get("/reports", response_model=list[SecReportResponse])
@app.get("/reports/", response_model=list[SecReportResponse])
async def get_reports(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db)
):
    query = db.query(SecReport)
    if q:
        query = query.filter(SecReport.ARTICLE_TITLE.ilike(f"%{q}%"))
    if writer:
        query = query.filter(SecReport.WRITER.ilike(f"%{writer}%"))
    return query.order_by(SecReport.REG_DT.desc(), SecReport.report_id.desc()).offset(offset).limit(limit).all()

@app.get("/health")
async def health_check(): return {"status": "ok"}
