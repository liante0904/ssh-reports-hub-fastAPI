-- Report source-key readability and redundant-index cleanup.
-- Manual operational SQL: run as admin, outside an application migration
-- transaction. Existing view columns are preserved; the new alias is appended.

CREATE OR REPLACE VIEW public.v_sec_reports_full AS
SELECT
    r.report_id,
    r.firm_id,
    r.board_id,
    r.firm_nm,
    r.article_title,
    NULL::text AS article_url,
    r.report_unique_key,
    r.report_date,
    r.save_at,
    r.telegram_sent,
    r.telegram_url,
    r.writer,
    r.mkt_tp,
    r.pdf_url AS download_url,
    r.pdf_url,
    r.download_status_yn,
    r.pdf_sync_status,
    r.pdf_hash,
    r.sync_status,
    r.retry_count,
    r.archive_path,
    r.report_unique_key AS report_source_key
FROM public.tbl_sec_reports AS r;

CREATE OR REPLACE VIEW public.v_sec_reports_canonical AS
SELECT
    r.report_id,
    r.firm_id,
    r.board_id,
    r.firm_nm,
    r.article_title,
    NULL::text AS article_url,
    r.download_status_yn,
    r.pdf_url AS download_url,
    r.writer,
    r.telegram_url,
    r.mkt_tp,
    r.gemini_summary,
    r.summary_time,
    r.summary_model,
    r.archive_path,
    r.retry_count,
    r.sync_status,
    r.pdf_url,
    r.pdf_sync_status,
    r.pdf_hash,
    r.tags,
    r.stock_names,
    r.sector,
    r.fnguide_summary_id,
    r.target_price,
    r.rating,
    r.revision_type,
    r.report_type,
    r.stock_tickers,
    r.report_date,
    r.telegram_sent,
    r.report_unique_key,
    r.save_at,
    r.article_text,
    r.gdrive_pdf_url,
    r.save_at AS scraped_at,
    r.firm_nm AS firm_name,
    r.mkt_tp AS market_type,
    r.report_unique_key AS report_source_key
FROM public.tbl_sec_reports AS r;

-- These are duplicate standalone indexes on report_unique_key. Keep the
-- descriptive unique index idx_report_unique_uid as the conflict arbiter.
DROP INDEX CONCURRENTLY IF EXISTS public.tb_sec_reports_uid_key;
DROP INDEX CONCURRENTLY IF EXISTS public.idx_report_unique_key;
