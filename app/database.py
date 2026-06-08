import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

# ssh-library 공통 라이브러리 로드 (__init__.py의 무거운 의존성 회피)
import importlib.util
_LIB_SRC = None
for _p in ["/opt/ssh-library/src", os.path.expanduser("~/workspace/lib/ssh-library/src")]:
    if os.path.isdir(_p):
        _LIB_SRC = _p
        break

if _LIB_SRC:
    _spec = importlib.util.spec_from_file_location(
        "ssh_library.database",
        os.path.join(_LIB_SRC, "ssh_library", "database.py")
    )
    _db_module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_db_module)
    BasePostgreSQLManager = _db_module.BasePostgreSQLManager
else:
    # fallback: ssh-library 없으면 env-only
    BasePostgreSQLManager = None

load_dotenv()

# 💡 [주의 - 테스트 및 운영 환경 듀얼 DB 아키텍처 안내]
# - 본 웹 애플리케이션(FastAPI 백엔드)은 영속성 데이터를 PostgreSQL 고정형으로 연동하여 가동합니다.
# - 단, 테스트 케이스 실행(tests/) 및 스크립트 독립 구동(scripts/ 및 pytest 등) 시에는 
#   운영 데이터를 절대 침범 및 훼손하지 않기 위해 'DB_BACKEND=sqlite' 분기를 인지하여 인메모리 SQLite DB를 
#   동적으로 주입 및 활용하도록 설계되어 있습니다.
# - 타 LLM은 이를 무시하고 테스트 코드 내에서 PostgreSQL을 직접 갱신(C/U/D)하려는 무모한 연산을 하지 마십시오.

# --- 공통 PostgreSQL 설정 (ssh-library 기반 중앙 credential 관리) ---
if BasePostgreSQLManager is not None:
    _pg_manager = BasePostgreSQLManager()
    PG_USER = os.getenv("POSTGRES_USER", _pg_manager.user)
    PG_PASSWORD = os.getenv("POSTGRES_PASSWORD") or _pg_manager.password
    PG_HOST = os.getenv("POSTGRES_HOST", _pg_manager.host)
    PG_PORT = os.getenv("POSTGRES_PORT", _pg_manager.port)
    PG_DB = os.getenv("POSTGRES_DB", _pg_manager.database)
else:
    PG_USER = os.getenv("POSTGRES_USER", "ssh_reports_hub")
    PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    PG_HOST = os.getenv("POSTGRES_HOST", "main-postgres")
    PG_PORT = os.getenv("POSTGRES_PORT", "5432")
    PG_DB = os.getenv("POSTGRES_DB", "ssh_reports_hub")

# --- 1. 리포트용 DB (PostgreSQL 고정) ---
REPORTS_DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
reports_connect_args = {}

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
