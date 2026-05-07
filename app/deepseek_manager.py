"""
DeepSeek 요약 관리자 (PDF 텍스트 추출 + Text-only API)

PDF URL을 받아 → PDF 다운로드 → 텍스트 추출(PyMuPDF) → DeepSeek API(text) → 요약 반환
dry_run=True이면 추출된 텍스트 정보와 실행 방법만 반환 (실제 API 호출 안 함)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.deepseek")

DEFAULT_PROMPT = """당신은 금융 전문가입니다. 아래 증권사 레포트 내용을 분석하여 다음 형식으로 요약해 주세요:

1. 핵심 요약 (3줄 이내)
2. 주요 포인트 (불렛 포인트)
3. 투자의견 및 목표주가 (있는 경우)

한국어로 답변해 주세요."""


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    model: str = "deepseek-chat"  # or "deepseek-reasoner"
    api_base: str = "https://api.deepseek.com/v1"
    max_tokens: int = 4096
    temperature: float = 0.1
    dry_run: bool = True  # True면 텍스트 추출까지만 하고 API 호출 안 함


class DeepSeekManager:
    def __init__(self, config: Optional[DeepSeekConfig] = None):
        if config is None:
            config = DeepSeekConfig(
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            )
        elif not config.api_key:
            # config가 전달됐지만 api_key가 비어있으면 환경변수에서 채움
            config.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.config = config

    # ── PDF 텍스트 추출 ──────────────────────────────────────────

    async def _download_pdf(self, pdf_url: str) -> bytes:
        """aiohttp로 PDF를 다운로드하여 bytes로 반환합니다."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(pdf_url, timeout=60, allow_redirects=True) as resp:
                resp.raise_for_status()
                return await resp.read()

    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """PyMuPDF(fitz)로 PDF 바이트에서 텍스트를 추출합니다."""
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text: list[str] = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text")
            pages_text.append(text)
        doc.close()
        return "\n\n".join(pages_text)

    def _truncate_text(self, text: str, max_chars: int = 80000) -> str:
        """토큰 제한을 고려하여 텍스트를 자릅니다."""
        if len(text) <= max_chars:
            return text
        logger.warning(
            f"[DeepSeek] Text too long ({len(text)} chars), truncating to {max_chars}"
        )
        return text[:max_chars] + "\n\n[--- 이후 내용은 토큰 제한으로 생략됨 ---]"

    # ── curl/python 실행 명령어 구성 ──────────────────────────────

    def build_cli_command(
        self,
        pdf_url: str,
        report_id: int | None = None,
        article_title: str = "",
        extracted_text: str = "",
    ) -> str:
        """
        dry_run용 CLI 실행 가이드를 반환합니다.
        DeepSeek API 호출 + PostgreSQL DB 저장까지 포함된 완전한 스크립트입니다.
        """
        title_safe = article_title.replace("'", "\\'")
        db_update = ""
        if report_id:
            db_update = f'''
    # ── 4) PostgreSQL DB 저장 ──
    import psycopg2
    from datetime import datetime

    conn = psycopg2.connect(
        host="main-postgres",
        port=5432,
        user="ssh_reports_hub",
        password="dlrtmrja!",
        dbname="ssh_reports_hub",
    )
    cur = conn.cursor()
    cur.execute(
        """UPDATE tbl_sec_reports
           SET gemini_summary = %s,
               summary_time = %s,
               summary_model = %s
           WHERE report_id = %s""",
        (result.get("summary", ""), datetime.utcnow().isoformat(), result.get("model", ""), {report_id}),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ DB 업데이트 완료 (report_id={report_id})")'''

        lines = [
            'docker exec -i ssh-reports-hub-fastapi-prod python3 -c """',
            "import asyncio, json, os",
            "os.environ['DEEPSEEK_API_KEY'] = 'YOUR_API_KEY_HERE'",
            "from app.deepseek_manager import DeepSeekConfig, DeepSeekManager",
            "config = DeepSeekConfig(dry_run=False)",
            "manager = DeepSeekManager(config)",
            f"result = asyncio.run(manager.summarize(",
            f"    pdf_url='{pdf_url}',",
            f"    article_title='{title_safe}',",
            f"))",
            "print(json.dumps(result, ensure_ascii=False, indent=2))",
            f"{db_update}",
            '"""',
        ]
        if extracted_text:
            preview = extracted_text[:300].replace("'", "\\'").replace("\n", "\\n")
            lines += [
                "",
                f"# 텍스트 추출 완료 (총 {len(extracted_text)} 자)",
            ]
        return "\n".join(lines)

    # ── 핵심: PDF → 텍스트 추출 → DeepSeek API 호출 ────────────

    async def summarize(
        self, pdf_url: str, article_title: str, prompt: Optional[str] = None, report_id: Optional[int] = None
    ) -> dict:
        """
        PDF URL을 받아 → 다운로드 → 텍스트 추출 → DeepSeek 요청 → 결과 반환

        dry_run=True이면 텍스트 추출까지만 하고 CLI 실행 가이드 반환.
        dry_run=False이면 실제 DeepSeek API 호출까지 수행.
        """
        prompt = prompt or DEFAULT_PROMPT
        context = f"[{article_title}]" if article_title else ""

        # ── 1) PDF 다운로드 ──────────────────────────────────────
        logger.info(f"[DeepSeek] Downloading PDF: {article_title or pdf_url}")
        try:
            pdf_bytes = await self._download_pdf(pdf_url)
            logger.info(f"[DeepSeek] Downloaded {len(pdf_bytes)} bytes")
        except Exception as e:
            logger.error(f"[DeepSeek] PDF download failed: {e}")
            return {
                "status": "error",
                "error": f"PDF 다운로드 실패: {e}",
                "summary": None,
                "model": self.config.model,
            }

        # ── 2) PDF에서 텍스트 추출 ───────────────────────────────
        try:
            extracted_text = self._extract_text_from_pdf(pdf_bytes)
            logger.info(
                f"[DeepSeek] Extracted {len(extracted_text)} chars from PDF"
            )
        except Exception as e:
            logger.error(f"[DeepSeek] Text extraction failed: {e}")
            return {
                "status": "error",
                "error": f"PDF 텍스트 추출 실패: {e}",
                "summary": None,
                "model": self.config.model,
            }

        # ── 3) 텍스트 길이 제한 ──────────────────────────────────
        truncated_text = self._truncate_text(extracted_text)

        # ── 4) 최종 프롬프트 구성 ────────────────────────────────
        full_prompt = (
            f"{context}\n\n아래는 보고서 본문입니다:\n\n{truncated_text}\n\n---\n\n{prompt}"
        )

        # ── 5) Dry-run: 실제 호출 없이 정보만 반환 ──────────────
        if self.config.dry_run:
            cli_guide = self.build_cli_command(
                pdf_url,
                report_id=report_id,
                article_title=article_title,
                extracted_text=extracted_text,
            )
            logger.info("[DeepSeek] DRY RUN - no API call made")
            return {
                "status": "dry_run",
                "message": (
                    "PDF 텍스트 추출 완료. 아래 CLI 명령어로 실제 DeepSeek API를 호출하세요.\n"
                    "dry_run=False로 설정하면 자동 실행됩니다."
                ),
                "summary": None,
                "model": self.config.model,
                "pdf_stats": {
                    "bytes": len(pdf_bytes),
                    "text_chars": len(extracted_text),
                    "text_chars_truncated": len(truncated_text),
                },
                "cli_command": cli_guide,
            }

        # ── 6) 실제 DeepSeek API 호출 ────────────────────────────
        logger.info(f"[DeepSeek] Calling API: {article_title}")
        try:
            import aiohttp

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            }

            payload = {
                "model": self.config.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a financial analyst. Always respond in Korean.",
                    },
                    {
                        "role": "user",
                        "content": full_prompt,
                    },
                ],
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[DeepSeek] API error {resp.status}: {error_text}"
                        )
                        return {
                            "status": "error",
                            "error": f"API returned {resp.status}: {error_text[:200]}",
                            "summary": None,
                            "model": self.config.model,
                        }

                    result = await resp.json()
                    summary = (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    # DeepSeek API 응답에서 실제 사용된 모델명을 추출
                    actual_model = result.get("model", self.config.model)
                    logger.info(
                        f"[DeepSeek] Summary generated ({len(summary)} chars) model={actual_model}"
                    )
                    return {
                        "status": "success",
                        "summary": summary,
                        "model": actual_model,
                        "pdf_stats": {
                            "bytes": len(pdf_bytes),
                            "text_chars": len(extracted_text),
                        },
                    }

        except Exception as e:
            logger.error(f"[DeepSeek] Exception: {e}")
            return {
                "status": "error",
                "error": str(e),
                "summary": None,
                "model": self.config.model,
            }
