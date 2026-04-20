import hashlib
import hmac
import time
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from fastapi.security import HTTPBearer

from .database import engine, Base, get_db
from .models import User, ReportKeyword, SecReport
from .schemas import TelegramUser, KeywordResponse, KeywordSyncRequest, KeywordCreate, SecReportResponse

# 초기 설정
Base.metadata.create_all(bind=engine)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
ALGORITHM = "HS256"

app = FastAPI(title="SSH Reports Hub API")

origins = ["https://ssh-oci.netlify.app", "http://localhost:5173", "http://localhost:3000", "http://localhost:8888"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

auth_scheme = HTTPBearer()

async def get_user_from_token(token: str = Depends(auth_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None: raise HTTPException(status_code=401, detail="Invalid Token")
    except JWTError: raise HTTPException(status_code=401, detail="Token Expired")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None: raise HTTPException(status_code=401, detail="User Not Found")
    return user

# --- 엔드포인트 ---

@app.post("/auth/telegram")
async def auth_telegram(user_data: TelegramUser, db: Session = Depends(get_db)):
    def verify_telegram_data(data: dict) -> bool:
        check_hash = data.get("hash")
        data_list = [f"{k}={v}" for k, v in sorted(data.items()) if k != "hash" and v is not None]
        data_check_string = "\n".join(data_list)
        secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
        hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return (hmac_hash == check_hash) and (time.time() - data.get("auth_date", 0) < 86400)

    if not verify_telegram_data(user_data.model_dump()):
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
    access_token = jwt.encode({"sub": str(db_user.id)}, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer", "user": {"id": db_user.id, "status": db_user.status}}

@app.get("/keywords", response_model=List[KeywordResponse])
async def get_my_keywords(current_user: User = Depends(get_user_from_token), db: Session = Depends(get_db)):
    return db.query(ReportKeyword).filter(ReportKeyword.user_id == current_user.id, ReportKeyword.is_active == True).all()

@app.post("/keywords/sync", response_model=List[KeywordResponse])
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

@app.get("/reports", response_model=List[SecReportResponse])
async def get_reports(
    q: Optional[str] = None, 
    limit: int = 50, 
    offset: int = 0, 
    db: Session = Depends(get_db)
):
    query = db.query(SecReport)
    if q:
        query = query.filter(SecReport.ARTICLE_TITLE.ilike(f"%{q}%"))
    return query.order_by(SecReport.REG_DT.desc(), SecReport.report_id.desc()).offset(offset).limit(limit).all()

@app.get("/health")
async def health_check(): return {"status": "ok"}
