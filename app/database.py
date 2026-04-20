import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# DB 백엔드 설정 (default: sqlite)
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").lower()

if DB_BACKEND == "postgres":
    PG_USER = os.getenv("POSTGRES_USER", "ssh_reports_hub")
    PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password123")
    PG_HOST = os.getenv("POSTGRES_HOST", "main-postgres")
    PG_PORT = os.getenv("POSTGRES_PORT", "5432")
    PG_DB = os.getenv("POSTGRES_DB", "ssh_reports_hub")
    DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
else:
    # SQLite 설정 (도커 내부 경로 기준)
    SQLITE_PATH = os.getenv("SQLITE_DB_PATH", "/data/telegram.db")
    DATABASE_URL = f"sqlite:///{SQLITE_PATH}"

# SQLite의 경우 체크 옵션 추가 (check_same_thread=False)
connect_args = {"check_same_thread": False} if DB_BACKEND == "sqlite" else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
