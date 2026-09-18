-- RC9.7.3 — saved_signals contract completion for fresh Supabase
-- Safe/idempotent. Does not delete or overwrite trading data.

ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS user_name TEXT,
    ADD COLUMN IF NOT EXISTS execution_origin TEXT NOT NULL DEFAULT 'SYSTEM_EXECUTABLE',
    ADD COLUMN IF NOT EXISTS risk_class TEXT NOT NULL DEFAULT 'PREMIUM',
    ADD COLUMN IF NOT EXISTS system_executable BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS engine_publication_status TEXT,
    ADD COLUMN IF NOT EXISTS execution_safety_at_save NUMERIC,
    ADD COLUMN IF NOT EXISTS execution_safety_minimum_at_save NUMERIC,
    ADD COLUMN IF NOT EXISTS original_risk_reward NUMERIC,
    ADD COLUMN IF NOT EXISTS source_signal_id TEXT,
    ADD COLUMN IF NOT EXISTS source_context TEXT,
    ADD COLUMN IF NOT EXISTS manual_override_ack BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS original_rejection_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_saved_signals_user_status_created
ON public.saved_signals(user_name, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_saved_signals_source_signal_id
ON public.saved_signals(source_signal_id)
WHERE source_signal_id IS NOT NULL;

-- Ask PostgREST to refresh its schema cache immediately.
NOTIFY pgrst, 'reload schema';

-- Verification: must return missing_columns = 0 and found_columns = 12.
WITH required(column_name) AS (
    VALUES
      ('user_name'),
      ('execution_origin'),
      ('risk_class'),
      ('system_executable'),
      ('engine_publication_status'),
      ('execution_safety_at_save'),
      ('execution_safety_minimum_at_save'),
      ('original_risk_reward'),
      ('source_signal_id'),
      ('source_context'),
      ('manual_override_ack'),
      ('original_rejection_reason')
), present AS (
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='saved_signals'
)
SELECT
    count(*) FILTER (WHERE p.column_name IS NOT NULL) AS found_columns,
    count(*) FILTER (WHERE p.column_name IS NULL) AS missing_columns,
    coalesce(jsonb_agg(r.column_name) FILTER (WHERE p.column_name IS NULL), '[]'::jsonb) AS missing
FROM required r
LEFT JOIN present p USING(column_name);
