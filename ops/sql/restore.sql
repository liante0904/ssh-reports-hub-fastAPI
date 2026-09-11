-- 1. 뷰 일시 제거
DROP VIEW IF EXISTS v_reports CASCADE;
DROP VIEW IF EXISTS v_sec_reports_full CASCADE;
DROP VIEW IF EXISTS v_sec_reports_canonical CASCADE;

-- 2. 레거시 트리거 및 함수 제거
DROP TRIGGER IF EXISTS trg_normalize_report_legacy_fields ON tbl_sec_reports;
DROP FUNCTION IF EXISTS normalize_report_legacy_fields();

-- 3. 물리 컬럼 key 제거
ALTER TABLE tbl_sec_reports DROP COLUMN IF EXISTS key;

-- 4. 뷰 재작성 (key 컬럼 의존성 완전히 제거)
CREATE OR REPLACE VIEW public.v_sec_reports_full AS
SELECT
    r.report_id, r.sec_firm_order, r.article_board_order, r.firm_nm,
    r.article_title, r.article_url, 
    r.report_unique_key,
    r.reg_dt, r.report_date,
    r.save_time, r.saved_at,
    r.telegram_sent,
    r.telegram_url, r.writer, r.mkt_tp,
    r.download_url, r.pdf_url,
    r.download_status_yn, r.pdf_sync_status, r.pdf_hash,
    r.sync_status, r.retry_count, r.archive_path,
    COALESCE(t.tags, '[]'::jsonb) AS tags,
    COALESCE(t.stock_names, '[]'::jsonb) AS stock_names,
    COALESCE(t.stock_tickers, '[]'::jsonb) AS stock_tickers,
    COALESCE(t.sector, '') AS sector,
    s.gemini_summary, s.summary_time, s.summary_model,
    p.target_price, p.rating, p.revision_type, p.report_type,
    p.fnguide_summary_id
FROM tbl_sec_reports r
LEFT JOIN tbl_report_enricher_tags t ON r.report_id = t.report_id
LEFT JOIN tbl_report_ai_summaries s ON r.report_id = s.report_id
LEFT JOIN tbl_report_price_targets p ON r.report_id = p.report_id;

CREATE OR REPLACE VIEW public.v_sec_reports_canonical AS
SELECT
    r.*,
    r.report_unique_key AS report_key,
    COALESCE(
        r.save_at,
        CASE
            WHEN left(r.save_time, 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN (left(r.save_time, 10) || ' 00:00:00+09')::timestamptz
            ELSE NULL
        END
    ) AS scraped_at,
    COALESCE(r.telegram_sent, false) AS notification_sent,
    'report_unique_key'::text AS report_key_status
FROM public.tbl_sec_reports r;
