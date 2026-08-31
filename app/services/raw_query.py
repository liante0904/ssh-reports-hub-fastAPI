"""Small DB adapter for raw, read-only query results."""


def execute_raw_query(db, sql_str: str, params: list | None = None) -> list:
    params = [] if params is None else params
    if db.get_bind().dialect.name != "postgresql":
        sql_str = sql_str.replace("%s", "?")
    conn = db.get_bind().raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_str, params)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()
