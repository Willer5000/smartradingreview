-- Q6-D: additive job ledger. Run ONCE before deploying the Q6 package.
-- Does not modify existing authentication, users, policies or trading tables.
CREATE TABLE IF NOT EXISTS public.q6_job_runs (
    job_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'DONE', 'FAILED')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- This new server-only table is private from creation. Existing Q6-C is deferred.
ALTER TABLE public.q6_job_runs ENABLE ROW LEVEL SECURITY;
