-- 1. 뷰 일시 제거
DROP VIEW IF EXISTS v_reports CASCADE;
DROP VIEW IF EXISTS v_sec_reports_full CASCADE;
DROP VIEW IF EXISTS v_sec_reports_canonical CASCADE;

-- 2. key 컬럼 추가 및 데이터 복원
ALTER TABLE tbl_sec_reports ADD COLUMN IF NOT EXISTS key text;
UPDATE tbl_sec_reports SET key = report_unique_key WHERE key IS NULL OR key = '';

-- 3. 제약 조건 및 인덱스 복구
ALTER TABLE tbl_sec_reports DROP CONSTRAINT IF EXISTS tbl_sec_reports_key_unique;
ALTER TABLE tbl_sec_reports ADD CONSTRAINT tbl_sec_reports_key_unique UNIQUE (key);
DROP INDEX IF EXISTS idx_tb_sec_reports_key;
CREATE INDEX IF NOT EXISTS idx_tb_sec_reports_key ON tbl_sec_reports (key);

-- 4. 함수 및 트리거 복구
CREATE OR REPLACE FUNCTION public.normalize_report_legacy_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.report_unique_key IS NULL OR btrim(NEW.report_unique_key) = '' THEN
        NEW.report_unique_key := NULLIF(NEW.key, '');
    END IF;
    IF NEW.reg_dt IS NULL OR NEW.reg_dt !~ '^[0-9]{8}$' THEN
        IF NEW.report_date IS NOT NULL THEN
            NEW.reg_dt := to_char(NEW.report_date, 'YYYYMMDD');
        ELSIF NEW.save_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
            NEW.reg_dt := replace(left(NEW.save_time, 10), '-', '');
        ELSE
            NEW.reg_dt := to_char(current_timestamp AT TIME ZONE 'Asia/Seoul', 'YYYYMMDD');
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_normalize_report_legacy_fields ON public.tbl_sec_reports;
CREATE TRIGGER trg_normalize_report_legacy_fields
BEFORE INSERT OR UPDATE OF key, report_unique_key, reg_dt, report_date, save_time
ON public.tbl_sec_reports
FOR EACH ROW
EXECUTE FUNCTION normalize_report_legacy_fields();

-- 5. 하위 호환 뷰 원상 복구 (r.key 직접 참조)
CREATE OR REPLACE VIEW public.v_sec_reports_full AS
SELECT
    r.report_id, r.sec_firm_order, r.article_board_order, r.firm_nm,
    r.article_title, r.article_url, r.key, r.report_unique_key,
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
    COALESCE(NULLIF(r.report_unique_key, ''), NULLIF(r.key, '')) AS report_key,
    COALESCE(
        r.save_at,
        CASE
            WHEN left(r.save_time, 10) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN (left(r.save_time, 10) || ' 00:00:00+09')::timestamptz
            ELSE NULL
        END
    ) AS scraped_at,
    COALESCE(r.telegram_sent, false) AS notification_sent,
    CASE
        WHEN COALESCE(NULLIF(r.report_unique_key, ''), NULLIF(r.key, '')) IS NULL
        THEN 'missing'
        WHEN NULLIF(r.report_unique_key, '') IS NULL
        THEN 'legacy_key'
        WHEN NULLIF(r.key, '') IS NULL
        THEN 'report_unique_key'
        WHEN r.report_unique_key = r.key
        THEN 'aligned'
        ELSE 'mismatch'
    END AS report_key_status
FROM public.tbl_sec_reports r;
