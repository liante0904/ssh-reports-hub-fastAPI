"""
관리자 전용 API 엔드포인트
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import get_keywords_db, get_reports_db
from ..deepseek_manager import DeepSeekConfig, DeepSeekManager
from ..dependencies import get_user_from_token
from ..models import SecReport, User

logger = logging.getLogger("app.admin")
router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_user_from_token)) -> User:
    """관리자 권한을 확인하는 의존성"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/reports/{report_id}/summarize-command")
async def get_summarize_command(
    report_id: int,
    current_user: User = Depends(require_admin),
    reports_db: Session = Depends(get_reports_db),
):
    """
    [Dry-Run] 리포트 요약을 위한 DeepSeek CLI 실행 가이드를 반환합니다.

    PDF를 다운로드하여 텍스트를 추출한 후, 실행 가능한 CLI 명령어를 반환합니다.
    실제 DeepSeek API 호출은 하지 않습니다.
    """
    # 리포트 조회
    report = (
        reports_db.query(SecReport)
        .filter(SecReport.report_id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 요약 대상 PDF URL 결정
    pdf_url = report.pdf_url or report.telegram_url or report.download_url or ""
    if not pdf_url:
        raise HTTPException(status_code=400, detail="No PDF URL available for this report")

    # DeepSeek 매니저 (dry-run 모드)
    config = DeepSeekConfig(dry_run=True)
    manager = DeepSeekManager(config)

    result = await manager.summarize(
        pdf_url=pdf_url,
        article_title=report.article_title or "",
        report_id=report_id,
    )

    return {
        "report_id": report_id,
        "title": report.article_title,
        "pdf_url": pdf_url,
        "dry_run": True,
        "cli_command": result.get("cli_command", ""),
        "message": "PDF 텍스트 추출 완료. 위 CLI 명령어를 검토 후 실행하세요. DEEPSEEK_API_KEY 환경변수를 확인하세요.",
    }


@router.post("/reports/{report_id}/summarize")
async def trigger_summarize(
    report_id: int,
    current_user: User = Depends(require_admin),
    reports_db: Session = Depends(get_reports_db),
    keywords_db: Session = Depends(get_keywords_db),
):
    """
    리포트 AI 요약을 실행하고 DB를 업데이트합니다.

    - dry_run=False로 설정되어야 실제 DeepSeek API 호출이 이루어집니다.
    - 현재는 dry_run=True이며, curl 명령어를 반환합니다.
    """
    from ..database import keywords_engine, reports_engine
    from sqlalchemy import text

    # 리포트 조회 (reports_db = reports_engine)
    report = (
        reports_db.query(SecReport)
        .filter(SecReport.report_id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 이미 요약이 있는지 확인
    if report.gemini_summary and report.gemini_summary.strip():
        return {
            "report_id": report_id,
            "status": "skipped",
            "message": "이미 요약이 존재합니다.",
            "existing_summary": report.gemini_summary[:100] + "...",
        }

    # PDF URL 결정
    pdf_url = report.pdf_url or report.telegram_url or report.download_url or ""
    if not pdf_url:
        raise HTTPException(status_code=400, detail="No PDF URL available for this report")

    # DeepSeek 요약 실행 (dry_run=False → PDF 다운로드 → 텍스트 추출 → DeepSeek API → DB 저장)
    config = DeepSeekConfig(dry_run=False)
    manager = DeepSeekManager(config)

    result = await manager.summarize(
        pdf_url=pdf_url,
        article_title=report.article_title or "",
        report_id=report_id,
    )

    # --- 실제 실행 완료 → DB 저장 ---
    if result["status"] == "success" and result.get("summary"):
        summary = result["summary"]
        model_name = result["model"]

        # DB 업데이트 (reports_db 사용)
        from datetime import datetime

        stmt = text(
            """
            UPDATE tbl_sec_reports
            SET gemini_summary = :summary,
                summary_time = :summary_time,
                summary_model = :model
            WHERE report_id = :report_id
            """
        )
        reports_db.execute(
            stmt,
            {
                "summary": summary,
                "summary_time": datetime.utcnow().isoformat(),
                "model": model_name,
                "report_id": report_id,
            },
        )
        reports_db.commit()

        return {
            "report_id": report_id,
            "status": "success",
            "summary": summary,
            "summary_model": model_name,
        }

    return {
        "report_id": report_id,
        "status": "error",
        "error": result.get("error", "Unknown error"),
    }


@router.get("/metrics")
async def get_system_metrics(
    current_user: User = Depends(require_admin),
    reports_db: Session = Depends(get_reports_db),
    keywords_db: Session = Depends(get_keywords_db),
):
    """
    시스템 메트릭 (CPU, RAM, Disk, DB 상태, 레포트 통계)을 반환합니다.
    관리자만 접근 가능합니다.
    """
    # --- CPU ---
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()
    cpu_freq_mhz = round(cpu_freq.current, 1) if cpu_freq else None

    # --- Memory ---
    mem = psutil.virtual_memory()
    mem_total_gb = round(mem.total / (1024 ** 3), 2)
    mem_used_gb = round(mem.used / (1024 ** 3), 2)
    mem_percent = mem.percent

    # --- Disk (메인 데이터 경로) ---
    disk_path = os.getenv("DISK_CHECK_PATH", "/")
    try:
        disk = psutil.disk_usage(disk_path)
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_used_gb = round(disk.used / (1024 ** 3), 1)
        disk_percent = disk.percent
    except Exception:
        disk_total_gb = 0
        disk_used_gb = 0
        disk_percent = 0

    # --- System uptime ---
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime_days = round((datetime.now() - boot_time).total_seconds() / 86400, 1)

    # --- DB health check ---
    db_ok = False
    db_latency_ms = None
    try:
        t0 = time.time()
        keywords_db.execute(text("SELECT 1"))
        t1 = time.time()
        db_ok = True
        db_latency_ms = round((t1 - t0) * 1000, 1)
    except Exception as e:
        logger.warning("DB health check failed: %s", e)

    # --- Report statistics ---
    total_reports = 0
    today_reports = 0
    reports_by_firm = []
    last_report_time = None
    last_report_title = None
    last_report_firm = None

    try:
        total_reports = reports_db.query(func.count(SecReport.report_id)).scalar() or 0

        today_str = datetime.now().strftime("%Y%m%d")
        today_reports = (
            reports_db.query(func.count(SecReport.report_id))
            .filter(SecReport.reg_dt == today_str)
            .scalar()
            or 0
        )

        # 증권사별 오늘 건수 (최대 10개)
        if DB_BACKEND := os.getenv("DB_BACKEND", "sqlite").lower() == "postgres":
            rows = (
                reports_db.query(SecReport.firm_nm, func.count(SecReport.report_id))
                .filter(SecReport.reg_dt == today_str)
                .group_by(SecReport.firm_nm)
                .order_by(func.count(SecReport.report_id).desc())
                .limit(10)
                .all()
            )
            reports_by_firm = [{"firm": row[0], "count": row[1]} for row in rows]

        # 최근 레포트
        latest = (
            reports_db.query(SecReport)
            .order_by(SecReport.save_time.desc())
            .first()
        )
        if latest:
            last_report_time = latest.save_time
            last_report_title = latest.article_title
            last_report_firm = latest.firm_nm

    except Exception as e:
        logger.warning("Report stats query failed: %s", e)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": "online" if db_ok else "degraded",
        "system": {
            "hostname": os.uname().nodename,
            "uptime_days": uptime_days,
            "python_version": os.getenv("PYTHON_VERSION", __import__("sys").version),
        },
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_count,
            "frequency_mhz": cpu_freq_mhz,
        },
        "memory": {
            "total_gb": mem_total_gb,
            "used_gb": mem_used_gb,
            "percent": mem_percent,
        },
        "disk": {
            "total_gb": disk_total_gb,
            "used_gb": disk_used_gb,
            "percent": disk_percent,
        },
        "database": {
            "status": "online" if db_ok else "offline",
            "latency_ms": db_latency_ms,
        },
        "reports": {
            "total": total_reports,
            "today_inserts": today_reports,
            "by_firm_today": reports_by_firm,
        },
        "last_activity": {
            "last_save_time": last_report_time,
            "last_title": last_report_title,
            "last_firm": last_report_firm,
        },
    }
