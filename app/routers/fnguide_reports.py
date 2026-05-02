from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import FnGuideReportSummary
from ..schemas import FnGuideReportSummaryResponse

router = APIRouter(prefix="/pub/api/fnguide", tags=["fnguide-reports"])


@router.get("/report-summaries", response_model=list[FnGuideReportSummaryResponse], summary="FnGuide 리포트 요약 목록")
@router.get("/report-summaries/", response_model=list[FnGuideReportSummaryResponse], include_in_schema=False)
async def get_report_summaries(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    provider: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    author: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(FnGuideReportSummary)
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

    return (
        query.order_by(FnGuideReportSummary.summary_id.asc(), FnGuideReportSummary.report_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
