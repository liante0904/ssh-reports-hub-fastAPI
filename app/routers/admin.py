"""
관리자 전용 API 엔드포인트
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import get_keywords_db, get_reports_db
from ..deepseek_manager import DeepSeekConfig, DeepSeekManager
from ..dependencies import get_settings_dep, get_user_from_token
from ..models import SecReport, User
from ..settings import Settings

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


# ──────────────────────────────────────────────
#  로그 브라우저 (/admin/logs, /admin/logs/view)
# ──────────────────────────────────────────────

_LOG_DESCRIPTIONS: dict[str, str] = {
    "fix_ls_db": "LS DB Fix 로그",
    "fix_dbfi_urls": "DB Fi URL Fix 로그",
    "scheduler": "스케줄러 실행 로그",
    "scraper_background": "스크래퍼 백그라운드 로그",
    "output": "스크래퍼 출력 로그",
    "ls_fix_background": "LS Fix 백그라운드 로그",
}


def _resolve_log_path(sub_path: str | None, log_dir: Path) -> Path:
    """로그 디렉토리 내 경로를 안전하게 resolve (path traversal 방지)."""
    if sub_path:
        requested = (log_dir / sub_path).resolve()
        if not str(requested).startswith(str(log_dir) + "/") and str(requested) != str(log_dir):
            raise HTTPException(status_code=403, detail="Access denied: path traversal detected")
        return requested
    return log_dir


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def _format_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def _get_description(name: str) -> str | None:
    for pattern, desc in _LOG_DESCRIPTIONS.items():
        if pattern in name:
            return desc
    return None


def _is_archived(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in (".gz", ".zip", ".bz2", ".tar", ".xz"))


@router.get("/logs")
async def list_log_files(
    path: str | None = Query(None, description="서브 디렉토리 경로"),
    current_user: User = Depends(require_admin),
    settings: Settings = Depends(get_settings_dep),
):
    target_dir = _resolve_log_path(path, Path(settings.admin_log_dir))

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Directory not found")
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    log_dir = Path(settings.admin_log_dir).resolve()
    entries: list[dict] = []
    try:
        for child in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                entries.append({
                    "type": "directory",
                    "name": child.name,
                    "full_path": str(child.relative_to(log_dir)),
                    "description": "디렉토리",
                    "modified": _format_mtime(child.stat().st_mtime),
                })
            elif child.is_file():
                stat = child.stat()
                entries.append({
                    "type": "file",
                    "name": child.name,
                    "full_path": str(child.relative_to(log_dir)),
                    "size": _format_size(stat.st_size),
                    "modified": _format_mtime(stat.st_mtime),
                    "description": _get_description(child.name),
                    "archived": _is_archived(child.name),
                })
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to list directory: {e}")

    current_path = str(target_dir.relative_to(log_dir)) if target_dir != log_dir else None
    return {"entries": entries, "current_path": current_path}


@router.get("/logs/view")
async def view_log_file(
    file: str = Query(..., description="읽을 로그 파일 경로 (admin_log_dir 기준 상대 경로)"),
    lines: int = Query(500, ge=10, le=10000, description="읽을 줄 수"),
    tail: bool = Query(True, description="tail 모드 (끝에서부터 읽기)"),
    current_user: User = Depends(require_admin),
    settings: Settings = Depends(get_settings_dep),
):
    target_file = _resolve_log_path(file, Path(settings.admin_log_dir))

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    MAX_FILE_SIZE = 100 * 1024 * 1024
    file_size = target_file.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large ({_format_size(file_size)}). Maximum allowed: 100 MB")

    try:
        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            if tail:
                all_lines = f.readlines()
                content_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            else:
                content_lines = []
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    content_lines.append(line)

        content = "".join(content_lines)
        return {
            "file": file,
            "content": content,
            "lines_returned": len(content_lines),
            "tail": tail,
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a readable text file")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")
