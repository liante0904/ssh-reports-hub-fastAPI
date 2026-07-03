from typing import Annotated, Optional
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from ..cache import cache_response
from ..database import get_reports_db
from ..models import MAIN_TABLE_NAME
from ..schemas import FnGuideReportDateResponse, FnGuideReportSummaryResponse

logger = logging.getLogger("app.fnguide")

router = APIRouter(prefix="/pub/api/fnguide", tags=["fnguide-reports"])


def _build_report_filter_sql(
    q: Optional[str],
    provider: Optional[str],
    author: Optional[str],
    report_date: Optional[str],
) -> tuple[str, dict]:
    """
    FnGuide 요약 리포트 테이블에 필터링 조건을 일관되게 적용합니다.
    Raw SQL 전환 대상 API에서 WHERE 절을 명시적으로 남겨 SQL 디버깅을 쉽게 합니다.
    """
    where_clauses = []
    params = {}
    if q:
        params["q"] = f"%{q.lower()}%"
        where_clauses.append(
            """
            (
                lower(coalesce(company_name, '')) LIKE :q
                OR lower(coalesce(report_title, '')) LIKE :q
                OR lower(coalesce(summary_text, '')) LIKE :q
                OR lower(coalesce(provider, '')) LIKE :q
                OR lower(coalesce(author, '')) LIKE :q
            )
            """
        )
    if provider:
        params["provider"] = f"%{provider.lower()}%"
        where_clauses.append("lower(coalesce(provider, '')) LIKE :provider")
    if author:
        params["author"] = f"%{author.lower()}%"
        where_clauses.append("lower(coalesce(author, '')) LIKE :author")
    if report_date:
        params["report_date"] = report_date
        where_clauses.append("report_date = :report_date")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return where_sql, params


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


@router.get("/report-summaries", response_model=list[FnGuideReportSummaryResponse], summary="FnGuide 리포트 요약 목록 조회")
@router.get("/report-summaries/", response_model=list[FnGuideReportSummaryResponse], include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (insert 시 internal webhook으로 무효화)
async def get_report_summaries(
    request: Request,
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    provider: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    author: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    report_date: Annotated[Optional[str], Query(min_length=1, max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    FnGuide 리포트 요약 정보를 페이지네이션하여 조회합니다.
    """
    where_sql, params = _build_report_filter_sql(q, provider, author, report_date)
    rows = db.execute(
        text(
            f"""
            SELECT
                summary_id,
                source_page_url,
                report_date,
                company_name,
                company_code,
                report_title,
                summary_text,
                opinion,
                target_price,
                prev_close,
                provider,
                author,
                article_url,
                pdf_url,
                report_key,
                item_rank,
                sync_status,
                created_at,
                updated_at
            FROM tbl_fnguide_report_summaries
            {where_sql}
            ORDER BY report_date DESC, summary_id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": limit, "offset": offset},
    ).all()

    summaries = [_row_to_dict(row) for row in rows]
    if not summaries:
        return []

    summary_ids = [row["summary_id"] for row in summaries]
    sec_report_rows = db.execute(
        text(
            f"""
            SELECT
                report_id,
                coalesce(firm_nm, '') AS firm_nm,
                coalesce(article_title, '') AS article_title,
                pdf_url,
                download_url,
                telegram_url,
                fnguide_summary_id
            FROM {MAIN_TABLE_NAME}
            WHERE fnguide_summary_id IN :summary_ids
            ORDER BY report_id DESC
            """
        ).bindparams(bindparam("summary_ids", expanding=True)),
        {"summary_ids": summary_ids},
    ).all()

    reports_by_summary_id = {summary_id: [] for summary_id in summary_ids}
    for row in sec_report_rows:
        report = _row_to_dict(row)
        summary_id = report.pop("fnguide_summary_id")
        reports_by_summary_id.setdefault(summary_id, []).append(report)

    for summary in summaries:
        summary["sec_reports"] = reports_by_summary_id.get(summary["summary_id"], [])

    return summaries


@router.get("/report-dates", response_model=list[FnGuideReportDateResponse], summary="FnGuide 리포트 날짜별 개수 집계")
@router.get("/report-dates/", response_model=list[FnGuideReportDateResponse], include_in_schema=False)
async def get_report_dates(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    provider: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    author: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    db: Session = Depends(get_reports_db),
):
    """
    FnGuide 요약 리포트가 존재하는 날짜들과 일자별 리포트 개수를 집계하여 내림차순 반환합니다.
    """
    where_sql, params = _build_report_filter_sql(q, provider, author, None)
    date_filter_sql = (
        f"{where_sql} AND report_date != ''"
        if where_sql
        else "WHERE report_date != ''"
    )
    rows = db.execute(
        text(
            f"""
            SELECT
                report_date,
                COUNT(summary_id) AS report_count
            FROM tbl_fnguide_report_summaries
            {date_filter_sql}
            GROUP BY report_date
            ORDER BY report_date DESC
            """
        ),
        params,
    ).all()
    return [
        FnGuideReportDateResponse(report_date=row.report_date, report_count=row.report_count)
        for row in rows
    ]
