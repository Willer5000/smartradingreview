# Release Notes — Commit 19.2.3

- Fixes late 1D Telegram confirmations being announced as “new”.
- Fixes weekly close calendar: Monday 00:00 UTC boundary (Sunday evening Argentina/Bolivia).
- Keeps legitimate delayed 4h confirmations within a bounded 60-minute grace.
- Adds Spot per-timeframe close watermarks in existing Supabase runtime snapshot.
- Reduces ordinary 4h Spot work from all 4 strategic TFs to only the TFs that truly closed.
- Futures/Multi Premium Telegram inherits the same fresh-close contract.
- No trading thresholds changed. No SQL. No new provider/thread/worker.
