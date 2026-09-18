-- RC9.7.9 · conservar la vigencia técnica original al guardar una señal confirmada o vigente
-- Ejecutar UNA sola vez en Supabase SQL Editor antes del deploy Main.
ALTER TABLE public.saved_signals
    ADD COLUMN IF NOT EXISTS source_valid_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_saved_signals_source_valid_until
    ON public.saved_signals(source_valid_until)
    WHERE status = 'active';
