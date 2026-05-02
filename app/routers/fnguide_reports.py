from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import FnGuideReportSummary
from ..schemas import FnGuideReportDateResponse, FnGuideReportSummaryResponse

router = APIRouter(prefix="/pub/api/fnguide", tags=["fnguide-reports"])


def _apply_report_filters(
    query,
    q: Optional[str],
    provider: Optional[str],
    author: Optional[str],
    report_date: Optional[str],
):
    if q:
        query = query.filter(
            or_(
                FnGuideReportSummary.company_name.ilike(f"%{q}%"),
                FnGuideReportSummary.report_title.ilike(f"%{q}%"),
                FnGuideReportSummary.summary_text.ilike(f"%{q}%"),
                FnGuideReportSummary.provider.ilike(f"%{q}%"),
                FnGuideReportSummary.author.ilike(f"%{q}%"),
            )
        )
    if provider:
        query = query.filter(FnGuideReportSummary.provider.ilike(f"%{provider}%"))
    if author:
        query = query.filter(FnGuideReportSummary.author.ilike(f"%{author}%"))
    if report_date:
        query = query.filter(FnGuideReportSummary.report_date == report_date)
    return query


@router.get("/report-summaries", response_model=list[FnGuideReportSummaryResponse], summary="FnGuide 리포트 요약 목록")
@router.get("/report-summaries/", response_model=list[FnGuideReportSummaryResponse], include_in_schema=False)
async def get_report_summaries(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    provider: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    author: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    report_date: Annotated[Optional[str], Query(min_length=1, max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = _apply_report_filters(db.query(FnGuideReportSummary), q, provider, author, report_date)
    return (
        query.order_by(
            FnGuideReportSummary.report_date.desc(),
            FnGuideReportSummary.summary_id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/report-dates", response_model=list[FnGuideReportDateResponse], summary="FnGuide 리포트 날짜별 개수")
@router.get("/report-dates/", response_model=list[FnGuideReportDateResponse], include_in_schema=False)
async def get_report_dates(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    provider: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    author: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    db: Session = Depends(get_reports_db),
):
    query = _apply_report_filters(db.query(FnGuideReportSummary), q, provider, author, None)
    rows = (
        query.with_entities(
            FnGuideReportSummary.report_date,
            func.count(FnGuideReportSummary.summary_id).label("report_count"),
        )
        .filter(FnGuideReportSummary.report_date != "")
        .group_by(FnGuideReportSummary.report_date)
        .order_by(FnGuideReportSummary.report_date.desc())
        .all()
    )
    return [
        FnGuideReportDateResponse(report_date=row.report_date, report_count=row.report_count)
        for row in rows
    ]
