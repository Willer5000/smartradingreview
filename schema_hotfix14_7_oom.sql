-- HOTFIX 14.7 — emergency OOM recovery for Render Free (512 MB)
-- Run BEFORE deploying Hotfix 14.7.
-- Deletes only recreatable runtime snapshots. Durable signals/results/learning
-- are intentionally untouched.

BEGIN;

-- Hotfix 14.6 may have persisted a rich 30-combo Futures payload. 14.7 uses
-- compact schema v3 and rebuilds it incrementally, so remove the v2 blob before
-- the new worker starts to avoid downloading/deserializing it during boot.
DELETE FROM runtime_snapshots_v1
WHERE namespace = 'futures'
  AND snapshot_key = 'analysis_cache';

-- Clear already-expired ephemeral rows using the existing bounded cleanup.
SELECT cleanup_ephemeral_v1();

COMMIT;
