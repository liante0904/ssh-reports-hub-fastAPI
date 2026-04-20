import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# --- 공통 PostgreSQL 설정 ---
PG_USER = os.getenv("POSTGRES_USER", "ssh_reports_hub")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
PG_HOST = os.getenv("POSTGRES_HOST", "main-postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "ssh_reports_hub")

# --- 1. 리포트용 DB 설정 (DB_BACKEND에 따라 결정) ---
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

if DB_BACKEND == "postgres":
    REPORTS_DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    reports_connect_args = {}
else:
    # SQLite 설정
    SQLITE_PATH = os.getenv("SQLITE_DB_PATH", "/data/telegram.db")
    REPORTS_DATABASE_URL = f"sqlite:///{SQLITE_PATH}"
    reports_connect_args = {"check_same_thread": False}

reports_engine = create_engine(REPORTS_DATABASE_URL, connect_args=reports_connect_args)
ReportsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=reports_engine)


# --- 2. 키워드/유저용 DB 설정 (무조건 PostgreSQL 고정) ---
KEYWORDS_DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

keywords_engine = create_engine(KEYWORDS_DATABASE_URL)
KeywordsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=keywords_engine)


class Base(DeclarativeBase):
    pass

# --- 의존성 주입 함수들 ---

async def get_db():
    """기본 db 유지 (하위 호환성용)"""
    db = ReportsSessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_reports_db():
    """리포트 전용 DB 세션"""
    db = ReportsSessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_keywords_db():
    """키워드/유저 전용 PostgreSQL 세션"""
    db = KeywordsSessionLocal()
    try:
        yield db
    finally:
        db.close()
