-- ============================================================================
-- COMMIT 1 — OPERATIONAL FIXES
-- Saved Futures: Telegram EXPIRED_NO_ENTRY
-- ============================================================================
--
-- Ejecutar UNA VEZ en Supabase SQL Editor ANTES del deploy del Commit 1.
--
-- 1) Añade la marca persistente para que EXPIRED se notifique una sola vez.
-- 2) Marca como ya informadas las expiraciones históricas armadas para evitar
--    una lluvia de mensajes al desplegar esta funcionalidad por primera vez.
-- 3) Las expiraciones futuras quedan NULL hasta que Telegram se envíe.
-- ============================================================================

ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS telegram_expired_notified_at TIMESTAMPTZ;

UPDATE public.saved_signals
SET telegram_expired_notified_at = COALESCE(
    telegram_expired_notified_at,
    NOW()
)
WHERE status = 'expired'
  AND close_reason = 'expired_no_entry'
  AND telegram_lifecycle_armed_at IS NOT NULL
  AND telegram_expired_notified_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_saved_signals_telegram_expired
ON public.saved_signals (
    status,
    telegram_expired_notified_at
)
WHERE telegram_lifecycle_armed_at IS NOT NULL;
