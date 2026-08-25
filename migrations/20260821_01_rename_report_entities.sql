-- The legacy entity table is empty and has no runtime writers/readers, but its
-- tbm_ prefix incorrectly describes a per-report data table. Keep the table
-- available for safe inspection while aligning it with the tbl_ convention.
DO $$
BEGIN
    IF to_regclass('public.tbm_report_entities') IS NOT NULL
       AND to_regclass('public.tbl_sec_reports_entities') IS NULL THEN
        ALTER TABLE public.tbm_report_entities RENAME TO tbl_sec_reports_entities;
    END IF;
END
$$;

DO $$
BEGIN
    IF to_regclass('public.tbm_report_entities_id_seq') IS NOT NULL
       AND to_regclass('public.tbl_sec_reports_entities_id_seq') IS NULL THEN
        ALTER SEQUENCE public.tbm_report_entities_id_seq
            RENAME TO tbl_sec_reports_entities_id_seq;
    END IF;
END
$$;

DO $$
BEGIN
    IF to_regclass('public.tbm_report_entities_pkey') IS NOT NULL
       AND to_regclass('public.tbl_sec_reports_entities_pkey') IS NULL THEN
        ALTER INDEX public.tbm_report_entities_pkey
            RENAME TO tbl_sec_reports_entities_pkey;
    END IF;
END
$$;

DO $$
DECLARE
    old_index text;
    new_index text;
BEGIN
    FOREACH old_index IN ARRAY ARRAY[
        'ix_tbm_report_entities_sector',
        'ix_tbm_report_entities_stock_code',
        'ix_tbm_report_entities_sentiment',
        'ix_tbm_report_entities_keyword',
        'ix_tbm_report_entities_report_id',
        'ix_tbm_report_entities_theme',
        'ix_tbm_report_entities_id'
    ] LOOP
        new_index := replace(old_index, 'tbm_report_entities', 'tbl_sec_reports_entities');
        IF to_regclass('public.' || old_index) IS NOT NULL
           AND to_regclass('public.' || new_index) IS NULL THEN
            EXECUTE format('ALTER INDEX public.%I RENAME TO %I', old_index, new_index);
        END IF;
    END LOOP;
END
$$;

DO $$
BEGIN
    IF to_regclass('public.tbl_sec_reports_entities') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conrelid = 'public.tbl_sec_reports_entities'::regclass
             AND conname = 'tbm_report_entities_report_id_fkey'
       ) THEN
        ALTER TABLE public.tbl_sec_reports_entities
            RENAME CONSTRAINT tbm_report_entities_report_id_fkey
            TO tbl_sec_reports_entities_report_id_fkey;
    END IF;
END
$$;
