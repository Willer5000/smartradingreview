-- ============================================================================
-- COMMIT 36R
-- AI ADVISOR / ASISTENTE PERSONAL / AI LEARNING SHADOW
-- ============================================================================
--
-- La IA:
-- - aconseja;
-- - critica;
-- - genera hipótesis;
-- - se evalúa contra resultados.
--
-- NO:
-- - cambia Safety;
-- - cambia Publication Gate;
-- - cambia votos;
-- - cambia pesos;
-- - cambia Entry / SL / TP;
-- - cambia leverage;
-- - ejecuta operaciones.
-- ============================================================================


-- ============================================================================
-- 36R.1 — USO / CUOTAS PERSISTENTES
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.ai_usage_events (

    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    user_name TEXT NOT NULL,

    usage_type TEXT NOT NULL,
    -- MANUAL / AUTO / LEARNING

    context_type TEXT,

    market TEXT,

    provider TEXT,

    model TEXT,

    status TEXT,

    input_tokens INTEGER DEFAULT 0,

    output_tokens INTEGER DEFAULT 0,

    total_tokens INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS
    idx_ai_usage_user_created

ON public.ai_usage_events (
    user_name,
    created_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_ai_usage_type_created

ON public.ai_usage_events (
    usage_type,
    created_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_ai_usage_created

ON public.ai_usage_events (
    created_at DESC
);


-- ============================================================================
-- 36R.2–36R.7 — OBSERVACIONES IA
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.ai_advisor_observations (

    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    user_name TEXT NOT NULL,

    usage_type TEXT NOT NULL,

    context_type TEXT NOT NULL,

    event_type TEXT,

    market TEXT NOT NULL,

    symbol TEXT,

    timeframe TEXT,

    -- Puede vincularse con una operación personal Saved Futures.
    related_saved_signal_id UUID
        REFERENCES public.saved_signals(id)
        ON DELETE SET NULL,

    -- ID de señal/análisis del sistema cuando existe.
    -- Es TEXT para no asumir que pertenece a saved_signals.
    source_signal_id TEXT,

    -- Evita gastar llamadas si el contexto no cambió.
    input_fingerprint TEXT NOT NULL,

    provider TEXT,

    model TEXT,

    system_action TEXT,

    ai_verdict TEXT,

    ai_confidence INTEGER,

    -- Respuesta completa estructurada.
    response_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Snapshot compacto que vio la IA.
    context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,

    assistant_question TEXT,

    -- ================================================================
    -- AUTORIDAD
    -- ================================================================

    authority TEXT NOT NULL DEFAULT 'ADVISORY_ONLY',

    affect_decision BOOLEAN NOT NULL DEFAULT FALSE,

    affect_safety BOOLEAN NOT NULL DEFAULT FALSE,

    affect_levels BOOLEAN NOT NULL DEFAULT FALSE,

    affect_leverage BOOLEAN NOT NULL DEFAULT FALSE,

    affect_weights BOOLEAN NOT NULL DEFAULT FALSE,

    -- ================================================================
    -- 36R.7 — RESULTADO
    -- ================================================================

    outcome_status TEXT NOT NULL DEFAULT 'NOT_LINKED',

    outcome_r NUMERIC(12, 6),

    outcome_pnl_usdt NUMERIC(20, 8),

    outcome_win BOOLEAN,

    outcome_source TEXT,

    settled_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- La misma pregunta/contexto no vuelve a llamar la IA.

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_ai_advisor_fingerprint

ON public.ai_advisor_observations (
    user_name,
    context_type,
    input_fingerprint
);


CREATE INDEX IF NOT EXISTS
    idx_ai_advisor_user_created

ON public.ai_advisor_observations (
    user_name,
    created_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_ai_advisor_market_created

ON public.ai_advisor_observations (
    market,
    created_at DESC
);


CREATE INDEX IF NOT EXISTS
    idx_ai_advisor_outcome_pending

ON public.ai_advisor_observations (
    outcome_status
)

WHERE
    outcome_status = 'PENDING';


CREATE INDEX IF NOT EXISTS
    idx_ai_advisor_verdict

ON public.ai_advisor_observations (
    ai_verdict,
    outcome_status
);
