import os
import sys
import sysconfig
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

# ssh-library 공통 DB credential 로드.
# __init__.py가 scraper/analytics까지 import하므로 database.py만 직접 로드한다.
import importlib.util
_LIB_DATABASE = None
_candidate_roots = [
    sysconfig.get_paths().get("purelib"),
    "/opt/venv/lib/python3.12/site-packages",
    "/opt/ssh-library",
    os.path.expanduser("~/workspace/lib/ssh_library"),
    os.path.expanduser("~/workspace/lib/ssh-library"),
]
for _root in _candidate_roots:
    if not _root:
        continue
    _candidate = os.path.join(_root, "ssh_library", "database.py")
    if os.path.isfile(_candidate):
        _LIB_DATABASE = _candidate
        break

if _LIB_DATABASE:
    _spec = importlib.util.spec_from_file_location(
        "ssh_library.database",
        _LIB_DATABASE,
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

POSTGRES_ENGINE_KWARGS = {
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "10")),
}

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

reports_engine = create_engine(REPORTS_DATABASE_URL, connect_args=reports_connect_args, **POSTGRES_ENGINE_KWARGS)
ReportsSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=reports_engine)


# --- 2. 키워드/유저용 DB 설정 (reports_engine과 동일 DB → 풀 공유) ---
# 동일 DB에 대해 별도 engine/pool을 생성하면 connection slot을 불필요하게 소모하므로
# keywords_engine / KeywordsSessionLocal 은 reports_engine / ReportsSessionLocal 을 재사용합니다.
keywords_engine = reports_engine
KeywordsSessionLocal = ReportsSessionLocal


class Base(DeclarativeBase):
    pass

# --- 의존성 주입 함수들 ---

def get_db():
    """기본 db 유지 (하위 호환성용)"""
    db = ReportsSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_reports_db():
    """리포트 전용 DB 세션"""
    db = ReportsSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_keywords_db():
    """키워드/유저 전용 PostgreSQL 세션"""
    db = KeywordsSessionLocal()
    try:
        yield db
    finally:
        db.close()
