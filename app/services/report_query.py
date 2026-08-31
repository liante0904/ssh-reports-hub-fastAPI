"""Side-effect-free query construction for the external report API."""

from typing import Optional


BASE_SELECT_SQL = """
    SELECT * FROM v_reports_api r
"""


def build_report_list_query(
    q=None, writer=None, company=None, board=None, has_summary=None,
    tag=None, sector=None, stock=None, limit=50, offset=0, is_postgres=True,
) -> tuple[str, list]:
    placeholder = "%s" if is_postgres else "?"
    source = "v_reports_api" if is_postgres else "tbl_sec_reports"
    like_op = "ILIKE" if is_postgres else "LIKE"
    clauses = []
    params = []
    for value, column in ((q, "article_title"), (writer, "writer")):
        if value:
            clauses.append(f"r.{column} {like_op} {placeholder}")
            params.append(f"%{value}%")
    if company is not None:
        clauses.append(f"r.firm_id = {placeholder}")
        params.append(company)
    if board is not None:
        clauses.append(f"r.board_id = {placeholder}")
        params.append(board)
    if has_summary:
        clauses.append("r.gemini_summary IS NOT NULL AND r.gemini_summary NOT IN ('',' ')")
    if tag:
        clauses.append(f"r.tags {like_op} {placeholder}")
        params.append(f'%"{tag}"%')
    if sector:
        clauses.append(f"r.sector {like_op} {placeholder}")
        params.append(f"%{sector}%")
    if stock:
        clauses.append(f"r.stock_names {like_op} {placeholder}")
        params.append(f'%"{stock}"%')
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        f"SELECT * FROM {source} r {where} "
        f"ORDER BY r.report_date DESC, r.report_id DESC "
        f"LIMIT {placeholder} OFFSET {placeholder}"
    )
    return sql, params + [limit, offset]


def base_select_sql(db) -> str:
    return BASE_SELECT_SQL if db.get_bind().dialect.name == "postgresql" else "SELECT * FROM tbl_sec_reports r"


def build_where_clauses(
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
    like_op = "ILIKE" if is_postgres else "LIKE"
    clauses = []
    params = []
    if writer:
        clauses.append(f"r.writer {like_op} %s")
        params.append(f"%{writer}%")
    if title:
        normalized_title = " ".join(title.lower().split())
        if "해외주식" in normalized_title and (
            "탑픽" in normalized_title or "top pick" in normalized_title
        ):
            clauses.append(f"(r.article_title {like_op} %s OR r.article_title {like_op} %s)")
            params.extend(["%해외주식%탑픽%", "%해외주식%Top Pick%"])
        else:
            clauses.append(f"r.article_title {like_op} %s")
            params.append(f"%{title}%")
    if mkt_tp == "global":
        clauses.append("r.mkt_tp != 'KR'")
    elif mkt_tp == "domestic":
        clauses.append("r.mkt_tp = 'KR'")
    if company is not None:
        clauses.append("r.firm_id = %s")
        params.append(company)
    if board is not None:
        clauses.append("r.board_id = %s")
        params.append(board)
    if tag:
        clauses.append(f"r.tags {like_op} %s")
        params.append(f'%"{tag}"%')
    if sector:
        clauses.append(f"r.sector {like_op} %s")
        params.append(f"%{sector}%")
    if stock:
        clauses.append(f"r.stock_names {like_op} %s")
        params.append(f'%"{stock}"%')
    return clauses, params


def build_outlook_clauses(outlook_year: Optional[int], is_postgres: bool = True) -> tuple[list[str], list]:
    like_op = "ILIKE" if is_postgres else "LIKE"
    clauses = [f"r.article_title {like_op} %s"]
    params = ["%전망%"]
    if is_postgres:
        clauses.extend([
            "r.article_title ~* '하반기|상반기|연간|[0-9]{4}년|[0-9]H[0-9]{2}|전망포럼|"
            "(경제|금융시장|주식시장|시장)[[:space:]]*전망|(업종|산업)[[:space:]]*전망'",
            "r.article_title !~* '\\([0-9]{5,6}'",
            "r.article_title !~* '\\[[0-9]{5,6}/'",
            "r.article_title !~* '\\[[^\\]]+/(매수|매도|중립|시장수익률|Buy|Hold|Sell|Neutral|Outperform|Underperform|Not[[:space:]]*Rated|Trading[[:space:]]*Buy)'",
            "r.article_title !~* '목표주가'",
        ])
    if outlook_year:
        clauses.append(f"r.article_title {like_op} %s")
        params.append(f"%{outlook_year}년%")
    return clauses, params


def paginate_query(query_or_sql, limit: int, offset: int, db=None, params: list = None, execute_raw_query=None) -> tuple[list, bool]:
    if not isinstance(query_or_sql, str):
        rows = query_or_sql.offset(offset).limit(limit + 1).all()
        return rows[:limit], len(rows) > limit
    sql = f"{query_or_sql} LIMIT %s OFFSET %s"
    extended_params = list(params or []) + [limit + 1, offset]
    results = execute_raw_query(db, sql, extended_params)
    return results[:limit], len(results) > limit
