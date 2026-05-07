"""
관리자 전용 API 엔드포인트
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
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
