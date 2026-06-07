#!/usr/bin/env python
"""
FnGuide 요약 리포트 매칭 처리 CLI 배치 스크립트
"""

import os
import sys
import argparse
import logging

# app 패키지를 찾기 위해 부모 디렉토리를 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("match_fnguide_reports")

from app.database import ReportsSessionLocal, reports_engine
from app.main import _ensure_tags_columns, Base
from app.services.fnguide_matcher import FnGuideMatcher

def main():
    parser = argparse.ArgumentParser(description="FnGuide 요약 리포트 매칭 배치 처리 스크립트")
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="처리할 미매칭 리포트 수 (기본값: 200)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 DB에 반영하지 않고 매칭 후보군 결과만 로깅합니다."
    )
    
    args = parser.parse_args()
    
    logger.info("FnGuide Matching Batch Process Started.")
    logger.info(f"Parameters - Limit: {args.limit}, Dry-Run: {args.dry_run}")

    db_backend = os.getenv("DB_BACKEND", "").lower()
    
    if db_backend == "sqlite":
        # SQLite 인메모리 개발/테스트 환경 보장
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        
        logger.info("Using SQLite in-memory database for execution.")
        sqlite_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        
        # 스키마 전체 빌드 및 누락 컬럼 자동 추가
        Base.metadata.create_all(bind=sqlite_engine)
        _ensure_tags_columns(sqlite_engine)
        logger.info("SQLite Database schema build and migration completed.")
        
        SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=sqlite_engine)
        db = SessionClass()
    else:
        # PostgreSQL 운영/개발 환경 설정
        try:
            Base.metadata.create_all(bind=reports_engine)
            _ensure_tags_columns(reports_engine)
            logger.info("PostgreSQL Database schema verification and migration completed.")
        except Exception as e:
            logger.warning(f"Database schema verification warning: {e}")
        
        db = ReportsSessionLocal()

    try:
        matcher = FnGuideMatcher(db)
        result = matcher.match_pending_reports(limit=args.limit, dry_run=args.dry_run)
        
        if result["status"] == "success":
            logger.info(f"Batch completed successfully. {result['matched_count']}/{result['total_processed']} matched.")
            if result["matched_count"] > 0:
                logger.info("Detailed updates:")
                for update in result["updates"]:
                    logger.info(
                        f"  [Report {update['report_id']}] {update['sec_firm']} | "
                        f"{update['sec_title']} -> FnGuide Summary {update['fnguide_summary_id']} "
                        f"({update['fnguide_stock']} - {update['fnguide_title']}, score: {update['score']})"
                    )
        else:
            logger.error(f"Batch processing failed: {result.get('message')}")
            sys.exit(1)
            
    except Exception as e:
        logger.exception(f"Unexpected error occurred during FnGuide matching: {e}")
        sys.exit(1)
    finally:
        db.close()
        logger.info("FnGuide Matching Batch Process Finished.")

if __name__ == "__main__":
    main()
