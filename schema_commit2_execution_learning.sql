-- ============================================================================
-- COMMIT 2 — EXECUTION LEARNING V2
-- Diagnóstico retrospectivo de Entry / SL / TP + Strategy Attribution V2
-- ============================================================================
--
-- Seguro e idempotente:
-- - no borra filas;
-- - no reescribe outcomes;
-- - no cambia Entry / SL / TP / leverage / Safety;
-- - las señales históricas quedan con {} hasta que exista evidencia nueva.
-- ============================================================================

ALTER TABLE IF EXISTS public.signal_results
    ADD COLUMN IF NOT EXISTS execution_forensics JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_signal_results_forensics_diagnosis
ON public.signal_results ((execution_forensics->>'diagnosis'));

CREATE INDEX IF NOT EXISTS idx_signal_results_forensics_version
ON public.signal_results ((execution_forensics->>'version'));

SELECT
    'signal_results.execution_forensics' AS component,
    COUNT(*) FILTER (
        WHERE execution_forensics IS NOT NULL
          AND execution_forensics <> '{}'::jsonb
    ) AS rows_with_forensics,
    COUNT(*) AS total_rows
FROM public.signal_results;
