-- HOTFIX 14.6 — persistent, bounded runtime state for Render Free (512 MB)
-- Run once in Supabase SQL Editor before deploying the Python changes.

CREATE TABLE IF NOT EXISTS runtime_snapshots_v1 (
    namespace TEXT NOT NULL,
    snapshot_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '6 hours'),
    PRIMARY KEY (namespace, snapshot_key)
);
CREATE INDEX IF NOT EXISTS idx_runtime_snapshots_expiry_v1
    ON runtime_snapshots_v1(expires_at);

CREATE TABLE IF NOT EXISTS macro_context_events_v1 (
    event_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title_es TEXT NOT NULL,
    source TEXT,
    url TEXT,
    category TEXT,
    risk_level TEXT,
    risk_score INTEGER DEFAULT 0,
    futures_posture TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    relevant_until TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_macro_context_relevant_until_v1
    ON macro_context_events_v1(relevant_until);
CREATE INDEX IF NOT EXISTS idx_macro_context_occurred_at_v1
    ON macro_context_events_v1(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_macro_context_risk_v1
    ON macro_context_events_v1(risk_level, occurred_at DESC);

-- Ephemeral rows only. Durable signals/results/learning are NEVER removed here.
CREATE OR REPLACE FUNCTION cleanup_ephemeral_v1()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM runtime_snapshots_v1 WHERE expires_at < NOW();
    DELETE FROM runtime_snapshots_v1
    WHERE (namespace, snapshot_key) IN (
        SELECT namespace, snapshot_key
        FROM runtime_snapshots_v1
        ORDER BY updated_at DESC
        OFFSET 60
    );
    DELETE FROM macro_context_events_v1 WHERE relevant_until < NOW();
    DELETE FROM macro_context_events_v1
    WHERE event_key IN (
        SELECT event_key
        FROM macro_context_events_v1
        ORDER BY updated_at DESC
        OFFSET 250
    );
END;
$$;
