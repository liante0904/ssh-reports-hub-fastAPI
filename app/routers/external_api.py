import asyncio
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Annotated, Optional
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import and_, or_, func, text
from sqlalchemy.orm import Session, joinedload

from ..cache import cache_response, invalidate_prefix
from ..database import get_reports_db
from ..models import SecReport, SecFirmInfo, SecBoardInfo
from ..schemas import ArchiveBundleRequest, CompanyResponse, BoardResponse, SecReportResponse
from ..services import archive_files as _archive_files
from ..services import report_query as _report_query

# External API 라우터 — 프론트엔드가 직접 호출하는 공개 API
router = APIRouter(prefix="/external/api", tags=["external-api"])


def _archive_remote_path(storage_key: str) -> str:
    return _archive_files.archive_remote_path(storage_key)


def _download_archive_file(storage_key: str, file_name: str) -> Path:
    return _archive_files.download_archive_file(storage_key, file_name)


def _remove_download_temp_file(path: Path) -> None:
    _archive_files.remove_download_temp_file(path)


def _bundle_file_name(file_name: str, report_id: int) -> str:
    return _archive_files.bundle_file_name(file_name, report_id)


def _remove_bundle_temp_file(path: Path) -> None:
    _archive_files.remove_bundle_temp_file(path)


@router.post("/reports/archive-bundle", summary="아카이브 PDF 묶음 다운로드")
async def download_archive_bundle(
    payload: ArchiveBundleRequest = Body(...),
    db: Session = Depends(get_reports_db),
):
    """Create a ZIP from Drive-backed PDFs without calling broker URLs.

    Files that are not archived are listed in manifest.json for a later,
    explicitly rate-limited fallback flow. Drive downloads are intentionally
    sequential to avoid burst traffic against the configured remote.
    """
    report_ids = sorted(set(payload.report_ids))
    rows = _execute_raw_psycopg2_query(
        db,
        """
        SELECT r.report_id, r.article_title, r.firm_nm,
               p.archive_status, p.storage_key, p.storage_backend, p.file_name
        FROM tbl_sec_reports r
        LEFT JOIN tbl_sec_reports_pdf_archive p ON p.report_id = r.report_id
        WHERE r.report_id = ANY(%s)
        ORDER BY r.report_id
        """,
        [report_ids],
    )
    row_by_id = {int(row["report_id"]): row for row in rows}
    missing = [
        {"report_id": report_id, "reason": "not_archived"}
        for report_id in report_ids
        if report_id not in row_by_id
        or row_by_id[report_id].get("archive_status") != "ARCHIVED"
        or not row_by_id[report_id].get("storage_key")
        or (row_by_id[report_id].get("storage_backend") and row_by_id[report_id].get("storage_backend") != "googledrive")
    ]

    temp_dir = Path(tempfile.mkdtemp(prefix="ssh-report-bundle-"))
    zip_path = temp_dir / "reports.zip"
    included = []
    used_names = set()

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for report_id in report_ids:
                row = row_by_id.get(report_id)
                if not row or any(item["report_id"] == report_id for item in missing):
                    continue
                try:
                    local_file = await asyncio.to_thread(
                        _download_archive_file,
                        row["storage_key"],
                        row.get("file_name") or f"report-{report_id}.pdf",
                    )
                    name = _bundle_file_name(row.get("file_name"), report_id)
                    stem, suffix = Path(name).stem, Path(name).suffix
                    candidate = name
                    counter = 2
                    while candidate in used_names:
                        candidate = f"{stem}-{counter}{suffix}"
                        counter += 1
                    used_names.add(candidate)
                    bundle.write(local_file, arcname=candidate)
                    included.append({"report_id": report_id, "file_name": candidate})
                    _remove_download_temp_file(local_file)
                except Exception as exc:
                    missing.append({"report_id": report_id, "reason": "archive_unavailable"})
                    # The bundle should still deliver successfully archived files.
                    _ = exc

            bundle.writestr("manifest.json", json.dumps({
                "requested_report_ids": report_ids,
                "included": included,
                "missing": missing,
            }, ensure_ascii=False, indent=2))
    except Exception:
        _remove_bundle_temp_file(zip_path)
        raise

    if not included:
        _remove_bundle_temp_file(zip_path)
        raise HTTPException(status_code=404, detail={"message": "No archived PDFs available", "missing": missing})

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="ssh-reports-archive.zip",
        background=BackgroundTask(_remove_bundle_temp_file, zip_path),
    )


def _sent_report_filter():
    return SecReport.telegram_sent == True


@router.get("/reports/{report_id}/archive-download", summary="아카이브 PDF 다운로드")
async def download_archived_pdf(report_id: int, db: Session = Depends(get_reports_db)):
    """Download an archived PDF without exposing the Drive key or credentials."""
    # PdfArchive ORM still carries retired legacy columns. Query only the live
    # archive contract so a download request cannot fail on those stale fields.
    rows = _execute_raw_psycopg2_query(
        db,
        """
        SELECT archive_status, storage_key, storage_backend, file_name
        FROM tbl_sec_reports_pdf_archive
        WHERE report_id = %s
        """,
        [report_id],
    )
    archive = rows[0] if rows else None
    if not archive or archive["archive_status"] != "ARCHIVED" or not archive["storage_key"]:
        raise HTTPException(status_code=404, detail="Archived PDF not found")
    if archive["storage_backend"] and archive["storage_backend"] != "googledrive":
        raise HTTPException(status_code=404, detail="Archived PDF not found")

    try:
        local_file = await asyncio.to_thread(
            _download_archive_file,
            archive["storage_key"],
            archive["file_name"] or f"report-{report_id}.pdf",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Archived PDF not found")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Archive download timed out")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return FileResponse(
        local_file,
        media_type="application/pdf",
        filename=Path(archive["file_name"] or f"report-{report_id}.pdf").name,
        background=BackgroundTask(_remove_download_temp_file, local_file),
    )

def _execute_raw_psycopg2_query(db: Session, sql_str: str, params: list = None) -> list:
    if params is None:
        params = []
    
    dialect_name = db.get_bind().dialect.name
    if dialect_name != "postgresql":
        sql_str = sql_str.replace("%s", "?")
        
    conn = db.get_bind().raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_str, params)
        colnames = [desc[0] for desc in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(colnames, row)))
        return rows
    finally:
        conn.close()


@router.get("/companies", response_model=list[CompanyResponse], summary="증권사 정보 목록 조회 (리포트 존재 기준)")
@cache_response(ttl=1800, prefix="api")  # 30분 캐시 (증권사 목록은 거의 변하지 않음)
async def get_companies(request: Request, db: Session = Depends(get_reports_db)):
    """
    tbm_sec_firm_info와 tbl_sec_reports를 JOIN하여
    실제로 리포트가 존재하는 증권사 목록과 리포트 개수를 반환합니다.
    """
    sql = """
        SELECT
            f.firm_id AS firm_id,
            f.firm_nm,
            f.telegram_update_yn AS is_direct_link,
            f.comment_pdf_url AS description,
            COUNT(r.report_id) AS report_count
        FROM tbm_sec_firm_info f
        JOIN tbl_sec_reports r ON f.firm_id = r.firm_id
        WHERE r.telegram_sent = TRUE
        GROUP BY
            f.firm_id,
            f.firm_nm,
            f.telegram_update_yn,
            f.comment_pdf_url
        ORDER BY f.firm_id ASC
    """
    results = _execute_raw_psycopg2_query(db, sql)

    return [
        CompanyResponse(
            firm_id=row["firm_id"],
            name=row["firm_nm"],
            is_direct=(row["is_direct_link"] == 'Y'),
            note=row["description"],
            report_count=row["report_count"]
        ) for row in results
    ]

@router.get("/boards", response_model=list[BoardResponse], summary="특정 증권사의 게시판 목록 조회")
@cache_response(ttl=600, prefix="api")  # 10분 캐시 (게시판 목록은 자주 변하지 않음)
async def get_boards(
    company: Annotated[int, Query(ge=0)],
    request: Request,
    db: Session = Depends(get_reports_db)
):
    """
    TBM_SEC_FIRM_BOARD_INFO와 SecReport를 JOIN하여 
    리포트가 존재하는 게시판 목록을 반환합니다.
    """
    sql = """
        SELECT
            b.firm_id AS firm_id,
            b.board_id AS board_id,
            b.board_nm,
            b.label_nm,
            COUNT(r.report_id) AS report_count
        FROM tbm_sec_firm_board_info b
        LEFT OUTER JOIN tbl_sec_reports r ON
            b.firm_id = r.firm_id AND
            b.board_id = r.board_id AND
            r.telegram_sent = TRUE
        WHERE b.firm_id = %s
        GROUP BY
            b.firm_id,
            b.board_id,
            b.board_nm,
            b.label_nm
        ORDER BY b.board_id ASC
    """
    results = _execute_raw_psycopg2_query(db, sql, [company])

    return [
        BoardResponse(
            firm_id=row["firm_id"],
            board_id=row["board_id"],
            board_nm=row["board_nm"],
            label_nm=row["label_nm"],
            report_count=row["report_count"]
        ) for row in results
    ]

INDUSTRY_REPORT_BOARD_FILTERS = (
    (0, (2,)),                     # LS증권 산업분석
    (1, (0,)),                     # 신한증권 산업분석
    (3, (6, 15)),                  # 하나증권 산업분석 + 글로벌 산업분석
    (5, (1,)),                     # 삼성증권 산업분석
    (6, (1,)),                     # 상상인증권 산업리포트
    (10, (1,)),                    # 키움증권 산업분석
    (14, (8, 9, 10, 11, 12, 13)),  # 다올투자증권 산업분석
    (18, (1,)),                    # IM증권 산업분석(국내)
    (19, (0,)),                    # DB증권 기업/산업분석(국내) - 종목코드 필터 필요
    (20, (1,)),                    # 메리츠증권 산업분석
    (22, (1,)),                    # 한양증권 산업 및 이슈 분석
    (23, (1,)),                    # BNK투자증권 산업분석
    (24, (1,)),                    # 교보증권 산업분석
    (25, (2,)),                    # IBK투자증권 산업분석
    (26, (6, 8)),                  # SK증권 산업분석
    (27, (1,)),                    # 유안타증권 산업분석
    (28, (0,)),                    # 흥국증권 산업/기업분석
)



def _base_select_sql(db: Session) -> str:
    return _report_query.base_select_sql(db)

_VIEW_TO_API_KEY_MAP = {
    "firm_id": "firm_id", "board_id": "board_id",
    "firm_nm": "firm_nm", "mkt_tp": "mkt_tp",
    "report_date": "report_date",
    "article_title": "article_title", "telegram_url": "telegram_url",
    "pdf_file_url": "pdf_file_url", "writer": "writer", "gemini_summary": "gemini_summary",
    "tags": "tags", "stock_names": "stock_names", "sector": "sector",
    "target_price": "target_price", "rating": "rating",
    "revision_type": "revision_type", "report_type": "report_type",
    "stock_tickers": "stock_tickers",
    "save_at": "save_at", "report_unique_key": "report_unique_key",
    "source_url": "source_url",
    "summary_time": "summary_time", "summary_model": "summary_model",
    "telegram_sent": "telegram_sent", "report_id": "report_id",
}

def _view_row_to_api_item(row) -> dict:
    """v_reports_api 뷰 row → API 응답 dict. 컬럼 추가 시 _VIEW_TO_API_KEY_MAP 만 수정."""
    # Collection routes normalize rows before handing them to
    # _collection_response(), which calls this helper once more. Preserve the
    # already-built nested archive payload on that second pass.
    if isinstance(row, dict) and "report_id" in row and "pdf_archive" in row:
        return row
    m = row._mapping if hasattr(row, "_mapping") else row
    item = {api_key: m.get(view_col) for view_col, api_key in _VIEW_TO_API_KEY_MAP.items()}
    item["is_direct"] = (str(m.get("is_direct", "")) == "Y") or None
    item["send_user"] = None
    # scraped_at: view가 이미 계산해서 제공
    item["scraped_at"] = m.get("scraped_at")
    if item["scraped_at"] is None:
        item["scraped_at"] = m.get("save_at")
    if isinstance(item["scraped_at"], datetime):
        item["scraped_at"] = item["scraped_at"].isoformat()
    elif isinstance(item["scraped_at"], str):
        item["scraped_at"] = item["scraped_at"].replace(" ", "T", 1)
    for json_field in ("tags", "stock_names", "stock_tickers"):
        item[json_field] = _parse_json_field(item.get(json_field))
    # nested objects
    item["pdf_archive"] = {k[4:]: m.get(k) for k in (
        "pdf_report_id","pdf_file_path","pdf_file_size","pdf_page_count",
        "pdf_archive_status","pdf_file_name","pdf_has_text","pdf_is_encrypted",
        "pdf_storage_backend","pdf_storage_key","pdf_author",
        "pdf_created_at","pdf_updated_at","pdf_last_accessed_at"
    )} if m.get("pdf_report_id") is not None else None
    item["fnguide_summary"] = {k[3:]: m.get(k) for k in (
        "fs_summary_id","fs_source_page_url","fs_report_date","fs_company_name",
        "fs_company_code","fs_report_title","fs_summary_text","fs_opinion",
        "fs_target_price","fs_prev_close","fs_provider","fs_author",
        "fs_article_url","fs_pdf_url","fs_report_key","fs_item_rank",
        "fs_sync_status","fs_created_at","fs_updated_at"
    )} if m.get("fs_summary_id") is not None else None
    # float cast
    if item.get("target_price") is not None:
        try: item["target_price"] = float(item["target_price"])
        except (ValueError, TypeError): pass
    return item

def _collection_response(
    request: Request,
    items: list,
    limit: int,
    offset: int,
    has_more: bool,
) -> dict:
    processed_items = [_view_row_to_api_item(r) for r in items]

    return {
        "items": processed_items,
        "hasMore": has_more,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "links": [
            {"rel": "self", "href": str(request.url)},
            {"rel": "first", "href": str(request.url.include_query_params(offset=0))},
        ],
    }


def _build_where_clauses(
    writer: Optional[str],
    title: Optional[str],
    mkt_tp: Optional[str],
    company: Optional[int],
    board: Optional[int] = None,
    tag: Optional[str] = None,
    sector: Optional[str] = None,
    stock: Optional[str] = None,
    is_postgres: bool = True,
) -> tuple[list[str], list]:
    return _report_query.build_where_clauses(
        writer, title, mkt_tp, company, board, tag, sector, stock, is_postgres
    )


def _build_outlook_clauses(
    outlook_year: Optional[int],
    is_postgres: bool = True,
) -> tuple[list[str], list]:
    return _report_query.build_outlook_clauses(outlook_year, is_postgres)


def _paginate_query(query_or_sql, limit: int, offset: int, db: Session = None, params: list = None) -> tuple[list, bool]:
    return _report_query.paginate_query(
        query_or_sql, limit, offset, db, params, _execute_raw_psycopg2_query
    )


@router.get("/industry", summary="산업별 리포트 조회 (Public API)")
@router.get("/industry/", include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (insert 시 internal webhook으로 무효화)
async def get_industry_reports(
    request: Request,
    last_report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    산업별 필터가 적용된 리포트 목록을 조회합니다.
    """
    is_postgres = (db.get_bind().dialect.name == "postgresql")
    
    params = []
    board_clauses = []
    for firm_order, board_orders in INDUSTRY_REPORT_BOARD_FILTERS:
        placeholders = ", ".join(["%s"] * len(board_orders))
        if firm_order == 19 and is_postgres:
            c = f"(r.firm_id = %s AND r.board_id IN ({placeholders}) AND r.article_title !~ '\\([0-9]{{5,6}}\\)')"
        else:
            c = f"(r.firm_id = %s AND r.board_id IN ({placeholders}))"
        board_clauses.append(c)
        params.append(firm_order)
        params.extend(board_orders)
    
    clauses = ["(" + ") OR (".join(board_clauses) + ")"]
    clauses.append("r.telegram_sent = TRUE")
    
    if is_postgres:
        clauses.append("r.article_title !~* '\\(\\d{5,6}'")
        clauses.append("r.article_title !~* '\\[\\d{5,6}/'")
        clauses.append("r.article_title !~* '\\([A-Z]{1,5}\\.[A-Z]{2}\\)'")
        clauses.append("r.article_title !~* '\\(\\d+\\.K[QS]\\)'")
        clauses.append("r.article_title !~* '\\[[^\\]]+/(매수|매도|중립|시장수익률|Buy|Hold|Sell|Neutral|Outperform|Underperform|Not\\s*Rated|Trading\\s*Buy)'")
        clauses.append("r.article_title !~* '목표주가'")

    if is_postgres:
        clauses.append("(r.pdf_report_id IS NULL OR r.pdf_page_count IS NULL OR r.pdf_page_count >= 10)")
    
    if last_report_id is not None:
        clauses.append("r.report_id < %s")
        params.append(last_report_id)
        
    search_clauses, search_params = _build_where_clauses(
        writer, title, mkt_tp, company, board, is_postgres=is_postgres
    )
    clauses.extend(search_clauses)
    params.extend(search_params)
    
    where_str = ""
    if clauses:
        where_str = "WHERE " + " AND ".join(clauses)
        
    order_by = "ORDER BY r.report_id DESC"
    sql_base = f"{_base_select_sql(db)} {where_str} {order_by}"
    
    rows, has_more = _paginate_query(sql_base, limit, offset, db=db, params=params)
    rows = [_view_row_to_api_item(r) for r in rows]
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/global", summary="글로벌 리포트 조회 (Public API)")
@router.get("/global/", include_in_schema=False)
@cache_response(ttl=300, prefix="api")  # 5분 캐시 (insert 시 internal webhook으로 무효화)
async def get_global_reports(
    request: Request,
    report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    글로벌(해외주식/글로벌 시장) 관련 리포트 목록을 독립적으로 조회합니다.
    국내 종목코드나 국내 시장 관련 키워드가 제목에 포함된 리포트는 제외됩니다.
    """
    is_postgres = (db.get_bind().dialect.name == "postgresql")
    
    clauses = ["r.telegram_sent = TRUE", "r.mkt_tp != 'KR'"]
    params = []
    
    if is_postgres:
        clauses.append("r.article_title !~* '\\(\\d{5,6}\\.K[QS]\\)'")
        clauses.append("r.article_title !~* '\\([^)]+\\.K[QS][^)]*\\)'")   # (214150.KQ/매수) 등 변형
        clauses.append("r.article_title !~* '\\b\\d{5,6}\\b'")
        clauses.append("r.article_title !~* '코스피|코스닥|KOSPI|KOSDAQ|퀀트|Quant|MP'")
        
    if report_id is not None:
        clauses.append("r.report_id = %s")
        params.append(report_id)
        
    search_clauses, search_params = _build_where_clauses(
        writer, title, "global", company, board, is_postgres=is_postgres
    )
    clauses.extend(search_clauses)
    params.extend(search_params)
    
    if report_id is not None:
        order_by = "ORDER BY r.report_id DESC"
    else:
        if is_postgres:
            order_by = "ORDER BY r.report_date DESC, r.save_at DESC NULLS LAST, r.report_id DESC, r.firm_id, r.board_id"
        else:
            order_by = "ORDER BY r.report_date DESC, CASE WHEN r.save_at IS NULL THEN 1 ELSE 0 END, r.save_at DESC, r.report_id DESC, r.firm_id, r.board_id"
            
    where_str = ""
    if clauses:
        where_str = "WHERE " + " AND ".join(clauses)
        
    sql_base = f"{_base_select_sql(db)} {where_str} {order_by}"
    
    rows, has_more = _paginate_query(sql_base, limit, offset, db=db, params=params)
    rows = [_view_row_to_api_item(r) for r in rows]
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/outlook", summary="전망 리포트 조회 (Public API)")
@router.get("/outlook/", include_in_schema=False)
@cache_response(ttl=300, prefix="api")
async def get_outlook_reports(
    request: Request,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    outlook_year: Annotated[Optional[int], Query(ge=2000, le=2099)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    전망 페이지 전용 리포트 목록을 조회합니다.
    /outlook 프론트엔드 페이지 전용 — search API와 정규식 필터를 분리합니다.
    """
    is_postgres = (db.get_bind().dialect.name == "postgresql")

    clauses, params = _build_outlook_clauses(outlook_year, is_postgres=is_postgres)
    search_clauses, search_params = _build_where_clauses(
        writer, title, mkt_tp, company, board, is_postgres=is_postgres
    )
    clauses.extend(search_clauses)
    params.extend(search_params)

    if is_postgres:
        order_by = "ORDER BY r.report_date DESC, r.save_at DESC NULLS LAST, r.report_id DESC, r.firm_id, r.board_id"
    else:
        order_by = "ORDER BY r.report_date DESC, CASE WHEN r.save_at IS NULL THEN 1 ELSE 0 END, r.save_at DESC, r.report_id DESC, r.firm_id, r.board_id"

    where_str = "WHERE " + " AND ".join(clauses)
    sql_base = f"{_base_select_sql(db)} {where_str} {order_by}"

    rows, has_more = _paginate_query(sql_base, limit, offset, db=db, params=params)
    rows = [_view_row_to_api_item(r) for r in rows]
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/search", summary="리포트 통합 검색 (Public API)")
@router.get("/search/", include_in_schema=False)
@cache_response(ttl=120, prefix="api")  # 2분 캐시 (insert 시 internal webhook으로 무효화)
async def search_reports(
    request: Request,
    report_id: Annotated[Optional[int], Query(ge=1)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    mkt_tp: Annotated[Optional[str], Query(pattern="^(global|domestic)$")] = None,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    has_summary: Annotated[Optional[bool], Query()] = None,
    tag: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    sector: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    stock: Annotated[Optional[str], Query(min_length=1, max_length=50)] = None,
    outlook: Annotated[Optional[bool], Query()] = None,
    outlook_year: Annotated[Optional[int], Query(ge=2000, le=2099)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    다양한 필터를 사용하여 리포트를 검색합니다.
    tag, sector, stock 파라미터로 enricher 태그 기반 필터링이 가능합니다.
    """
    is_postgres = (db.get_bind().dialect.name == "postgresql")
    
    clauses = []
    params = []
    
    if report_id is not None:
        clauses.append("r.report_id = %s")
        params.append(report_id)
        
    search_clauses, search_params = _build_where_clauses(
        writer, title, mkt_tp, company, board, tag, sector, stock, is_postgres=is_postgres
    )
    clauses.extend(search_clauses)
    params.extend(search_params)
    
    if has_summary:
        clauses.append("(r.gemini_summary IS NOT NULL AND r.gemini_summary != '' AND r.gemini_summary != ' ')")
        
    if outlook:
        outlook_clauses, outlook_params = _build_outlook_clauses(
            outlook_year, is_postgres=is_postgres
        )
        clauses.extend(outlook_clauses)
        params.extend(outlook_params)
            
    if report_id is not None:
        order_by = "ORDER BY r.report_id DESC"
    else:
        if is_postgres:
            order_by = "ORDER BY r.report_date DESC, r.save_at DESC NULLS LAST, r.report_id DESC, r.firm_id, r.board_id"
        else:
            order_by = "ORDER BY r.report_date DESC, CASE WHEN r.save_at IS NULL THEN 1 ELSE 0 END, r.save_at DESC, r.report_id DESC, r.firm_id, r.board_id"
            
    where_str = ""
    if clauses:
        where_str = "WHERE " + " AND ".join(clauses)
        
    sql_base = f"{_base_select_sql(db)} {where_str} {order_by}"
    
    rows, has_more = _paginate_query(sql_base, limit, offset, db=db, params=params)
    rows = [_view_row_to_api_item(r) for r in rows]
    return _collection_response(request, rows, limit, offset, has_more)


@router.get("/recent", summary="최근 리포트 조회 (Public API)")
@router.get("/recent/", include_in_schema=False)
@cache_response(ttl=120, prefix="api")
async def get_recent_reports(
    request: Request,
    company: Annotated[Optional[int], Query(ge=0)] = None,
    board: Annotated[Optional[int], Query(ge=0)] = None,
    writer: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    title: Annotated[Optional[str], Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_reports_db),
):
    """
    최근 발송된 리포트를 report_date(리포트 발행일) 기준 내림차순, 동일 발행일 내 save_at(스크래핑 시각) 내림차순으로 조회합니다.
    /recent 프론트엔드 페이지 전용 — search API 부하 분산.
    """
    is_postgres = (db.get_bind().dialect.name == "postgresql")
    order_by = "ORDER BY r.report_date DESC, r.save_at DESC NULLS LAST, r.report_id DESC" if is_postgres else \
               "ORDER BY r.report_date DESC, CASE WHEN r.save_at IS NULL THEN 1 ELSE 0 END, r.save_at DESC, r.report_id DESC"

    clauses = ["r.telegram_sent = TRUE"]
    params = []
    if company is not None:
        clauses.append("r.firm_id = %s"); params.append(company)
    if board is not None:
        clauses.append("r.board_id = %s"); params.append(board)
    if writer:
        clauses.append("r.writer ILIKE %s"); params.append(f"%{writer}%")
    if title:
        clauses.append("r.article_title ILIKE %s"); params.append(f"%{title}%")

    where = "WHERE " + " AND ".join(clauses)
    sql_base = f"{_base_select_sql(db)} {where} {order_by}"
    rows, has_more = _paginate_query(sql_base, limit, offset, db=db, params=params)
    rows = [_view_row_to_api_item(r) for r in rows]
    return _collection_response(request, rows, limit, offset, has_more)


def _parse_json_field(v) -> list:
    import json
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []

# ---------------------------------------------------------------------------
# Internal 캐시 무효화 Webhook — 스크래퍼가 새 데이터 insert 후 호출
# ---------------------------------------------------------------------------

INTERNAL_CACHE_TOKEN = os.getenv("INTERNAL_CACHE_TOKEN", "")


def _verify_internal_token(x_internal_token: Annotated[Optional[str], Header()] = None) -> None:
    """Internal webhook 호출자를 shared secret으로 인증한다."""
    if not INTERNAL_CACHE_TOKEN:
        raise HTTPException(status_code=501, detail="Internal cache invalidation is not configured")
    if not x_internal_token or x_internal_token != INTERNAL_CACHE_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/internal/cache/invalidate", summary="[Internal] Redis 캐시 무효화")
async def invalidate_cache(
    x_internal_token: Annotated[Optional[str], Header()] = None,
    prefix: Annotated[str, Query(description="무효화할 캐시 키 prefix (기본값: api)")] = "api",
):
    """
    스크래퍼가 새 리포트를 PostgreSQL에 insert 한 후 호출하는 internal webhook.
    지정된 prefix의 Redis 캐시를 모두 삭제하여 다음 API 호출이 최신 데이터를 반환하도록 한다.

    사용 예 (GitHub Actions / cron):
        curl -X POST https://ssh-oci.duckdns.org/external/api/internal/cache/invalidate \\
          -H "X-Internal-Token: $INTERNAL_CACHE_TOKEN"
    """
    _verify_internal_token(x_internal_token)
    deleted = await invalidate_prefix(prefix)
    return {"status": "ok", "deleted_keys": deleted}


@router.get("/internal/ls-existing-keys", summary="[Internal] LS증권 기존 key + writer 목록 조회")
async def get_ls_existing_keys(
    x_internal_token: Annotated[Optional[str], Header()] = None,
):
    """
    GA LS scraper v2가 기존 DB key 목록을 조회하여 중복 스크래핑을 방지.
    writer(사원명) 정보도 함께 반환 → detail 페이지 없이도 msg URL 재구성 가능.

    사용 예 (GA workflow):
        curl -H "X-Internal-Token: $INTERNAL_CACHE_TOKEN" \\
             https://ssh-oci.duckdns.org/external/api/internal/ls-existing-keys \\
             > ls_existing_keys.json
    """
    _verify_internal_token(x_internal_token)

    import psycopg2
    from urllib.parse import urlparse

    db_host = os.getenv("POSTGRES_HOST_REPORTS", "main-postgres")
    db_port = os.getenv("POSTGRES_PORT_REPORTS", "5432")
    db_user = os.getenv("POSTGRES_USER_REPORTS", "ssh_reports_hub")
    db_password = os.getenv("POSTGRES_PASSWORD_REPORTS", "")
    db_name = os.getenv("POSTGRES_DB_REPORTS", "ssh_reports_hub")

    conn = psycopg2.connect(
        host=db_host, port=db_port, user=db_user,
        password=db_password, dbname=db_name,
    )
    try:
        with conn.cursor() as cur:
            # LS증권(firm_id=0)의 모든 key + writer 조회
            cur.execute("""
                SELECT key, writer, article_title
                FROM tbl_sec_reports
                WHERE firm_id = 0 AND key IS NOT NULL AND key != ''
                ORDER BY key
            """)
            rows = cur.fetchall()

            keys = []
            key_writer_map = {}
            for row in rows:
                k = row[0]
                w = row[1] or ""
                keys.append(k)
                if w and k not in key_writer_map:
                    key_writer_map[k] = w

        return {
            "status": "ok",
            "count": len(keys),
            "keys": keys,
            "key_writer_map": key_writer_map,
        }
    finally:
        conn.close()


# Keep router-level names stable while response normalization lives in a pure service.
from ..services.report_response import (
    view_row_to_api_item as _view_row_to_api_item,
    collection_response as _collection_response,
    parse_json_field as _parse_json_field,
)
