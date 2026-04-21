from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_reports_db
from ..models import SecReport
from ..schemas import SecReportResponse

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=list[SecReportResponse])
@router.get("/reports/", response_model=list[SecReportResponse])
async def get_reports(
    q: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    query = db.query(SecReport)
    if q:
        query = query.filter(SecReport.ARTICLE_TITLE.ilike(f"%{q}%"))
    if writer:
        query = query.filter(SecReport.WRITER.ilike(f"%{writer}%"))
    return query.order_by(SecReport.REG_DT.desc(), SecReport.report_id.desc()).offset(offset).limit(limit).all()
