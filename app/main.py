import hashlib
import hmac
import time
import os
from typing import Optional, List, Any
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError
from sqlalchemy import create_engine, Column, Integer, String, Boolean, BigInteger, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from dotenv import load_dotenv

# 설정 로드
load_dotenv()
_raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_TOKEN = _raw_token.strip().strip('"').strip("'")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

# PostgreSQL 설정
PG_USER = os.getenv("POSTGRES_USER", "ssh_reports_hub")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password123")
PG_HOST = os.getenv("POSTGRES_HOST", "main-postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "ssh_reports_hub")

DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 모델 정의 (생략/유지) ---
class User(Base):
    __tablename__ = "TELEGRAM_USERS"
    id = Column(BigInteger, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    status = Column(String, default="active")
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    keywords = relationship("ReportKeyword", back_populates="owner")

class ReportKeyword(Base):
    __tablename__ = "REPORT_ALERT_KEYWORDS"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("TELEGRAM_USERS.id"))
    keyword = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(BigInteger, default=lambda: int(time.time()))
    updated_at = Column(BigInteger, default=lambda: int(time.time()), onupdate=lambda: int(time.time()))
    owner = relationship("User", back_populates="keywords")

Base.metadata.create_all(bind=engine)

# --- Pydantic 스키마 (더 유연하게 수정) ---
class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class KeywordBase(BaseModel):
    keyword: str
    is_active: bool = True

class KeywordCreate(KeywordBase):
    pass

class KeywordResponse(KeywordBase):
    id: int
    user_id: int
    created_at: int
    updated_at: int
    class Config:
        from_attributes = True

class KeywordSyncRequest(BaseModel):
    keywords: List[str]

app = FastAPI(title="Telegram Auth & Keyword Hub")

origins = ["https://ssh-oci.netlify.app", "http://localhost:5173", "http://localhost:3000", "http://localhost:8888"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

from fastapi.security import HTTPBearer
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
    print(f"DEBUG: Received user_data: {user_data.dict()}") # 수신 데이터 출력
    
    def verify_telegram_data(data: dict) -> bool:
        check_hash = data.get("hash")
        # 텔레그램 공식 가이드: hash를 제외하고 키순 정렬
        data_list = [f"{k}={v}" for k, v in sorted(data.items()) if k != "hash" and v is not None]
        data_check_string = "\n".join(data_list)
        
        # 비밀키: 봇 토큰의 SHA256 해시
        secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
        hmac_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        print(f"DEBUG: Calculated hash={hmac_hash}, received={check_hash}")
        
        is_valid = (hmac_hash == check_hash)
        is_not_expired = (time.time() - data.get("auth_date", 0) < 86400)
        
        if not is_valid: print(f"ERROR: Hash mismatch! Check string was:\n{data_check_string}")
        return is_valid and is_not_expired

    if not verify_telegram_data(user_data.dict()):
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

# 나머지 엔드포인트 (Keywords 관련) 생략/유지
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

@app.get("/health")
async def health_check(): return {"status": "ok"}
