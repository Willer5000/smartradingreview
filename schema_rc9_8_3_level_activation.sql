-- ============================================================================
-- RC9.8.3 — CAUSAL ENTRY / SL / TP ACTIVATION
-- Ejecutar UNA VEZ en Supabase antes del deploy de RC9.8.3.
-- Idempotente.
-- ============================================================================

ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS entry_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stop_loss_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS take_profit_updated_at TIMESTAMPTZ;

-- Backfill conservador para señales ABIERTAS que ya habían sido modificadas
-- antes de RC9.8.3. No toca señales cerradas ni reescribe historial.
UPDATE public.saved_signals
SET entry_updated_at = COALESCE(entry_updated_at, updated_at)
WHERE status IN ('active', 'entry_touched')
  AND original_entry IS NOT NULL
  AND entry IS DISTINCT FROM original_entry;

UPDATE public.saved_signals
SET stop_loss_updated_at = COALESCE(stop_loss_updated_at, updated_at)
WHERE status IN ('active', 'entry_touched')
  AND original_stop_loss IS NOT NULL
  AND stop_loss IS DISTINCT FROM original_stop_loss;

UPDATE public.saved_signals
SET take_profit_updated_at = COALESCE(take_profit_updated_at, updated_at)
WHERE status IN ('active', 'entry_touched')
  AND original_take_profit IS NOT NULL
  AND take_profit IS DISTINCT FROM original_take_profit;

COMMENT ON COLUMN public.saved_signals.entry_updated_at IS
'RC9.8.3: timestamp desde el que el Entry actual es causalmente válido.';
COMMENT ON COLUMN public.saved_signals.stop_loss_updated_at IS
'RC9.8.3: timestamp desde el que el Stop Loss actual es causalmente válido.';
COMMENT ON COLUMN public.saved_signals.take_profit_updated_at IS
'RC9.8.3: timestamp desde el que el Take Profit actual es causalmente válido.';
