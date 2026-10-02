from pathlib import Path
from datetime import datetime, timezone
import importlib.util

ROOT=Path(__file__).resolve().parent
app=(ROOT/'app.py').read_text(encoding='utf-8')
proc=(ROOT/'Procfile').read_text(encoding='utf-8')
render=(ROOT/'render.yaml').read_text(encoding='utf-8')
runtime=(ROOT/'commit19_1_runtime.py').read_text(encoding='utf-8')
mod_path=ROOT/'candle_close_authority_19_2_3.py'
spec=importlib.util.spec_from_file_location('cca', mod_path)
cca=importlib.util.module_from_spec(spec); spec.loader.exec_module(cca)

checks=[]
def ck(name, cond):
    ok=bool(cond); checks.append((name,ok)); print(('PASS ' if ok else 'FAIL ')+name)

# Calendar authority — the production bug was weekly epoch anchoring + broad freshness.
weekly_open=datetime(2026,9,21,0,0,tzinfo=timezone.utc)  # Monday
weekly_close=cca.canonical_close_from_open_utc('1W', weekly_open)
ck('weekly_close_is_next_monday_utc', weekly_close.isoformat()=='2026-09-28T00:00:00+00:00')
ck('weekly_midweek_timestamp_anchors_to_monday', cca.canonical_start_utc('1W','2026-09-30T12:00:00Z').isoformat()=='2026-09-28T00:00:00+00:00')
ck('daily_anchor_is_midnight_utc', cca.canonical_start_utc('1D','2026-10-02T04:36:00Z').isoformat()=='2026-10-02T00:00:00+00:00')
ck('4h_anchor_is_utc_grid', cca.canonical_start_utc('4h','2026-10-02T04:36:00Z').isoformat()=='2026-10-02T04:00:00+00:00')

sig_daily={'source_candle_timestamp':'2026-10-01T00:00:00Z'}
sig_4h={'source_candle_timestamp':'2026-10-02T00:00:00Z'}
sig_week={'source_candle_timestamp':'2026-09-28T00:00:00Z'}
ck('daily_4h36_late_is_not_new', not cca.confirmed_recent_enough(sig_daily,'1D',now='2026-10-02T04:36:00Z'))
ck('4h_36m_late_remains_allowed', cca.confirmed_recent_enough(sig_4h,'4h',now='2026-10-02T04:36:00Z'))
ck('weekly_midweek_is_not_new', not cca.confirmed_recent_enough(sig_week,'1W',now='2026-10-02T04:36:00Z'))
ck('weekly_minutes_after_close_is_allowed', cca.confirmed_recent_enough({'source_candle_timestamp':'2026-09-21T00:00:00Z'},'1W',now='2026-09-28T00:35:00Z'))

# Per-timeframe watermarks: a 4h close must not re-run daily/weekly.
watermarks={
    '4h':'2026-10-02T00:00:00+00:00',
    '12h':'2026-10-02T00:00:00+00:00',
    '1D':'2026-10-02T00:00:00+00:00',
    '1W':'2026-09-28T00:00:00+00:00',
}
due=cca.due_spot_timeframes(watermarks, now='2026-10-02T04:10:00Z')
ck('at_0410_only_4h_is_due', set(due)=={'4h'})
weekly_due=cca.due_spot_timeframes({**watermarks,'4h':'2026-10-05T00:00:00+00:00','12h':'2026-10-05T00:00:00+00:00','1D':'2026-10-05T00:00:00+00:00'}, now='2026-10-05T00:10:00Z')
ck('monday_close_makes_weekly_due', '1W' in weekly_due)

# App integration: one authority for Spot/Futures/Multi confirmed delivery.
ck('app_uses_shared_signal_close_authority', 'from candle_close_authority_19_2_3 import signal_close_utc' in app)
ck('app_uses_shared_fresh_close_gate', 'from candle_close_authority_19_2_3 import confirmed_recent_enough' in app)
ck('weekly_entry_dedup_uses_calendar_authority', 'from candle_close_authority_19_2_3 import canonical_start_utc' in app)
ck('stale_confirmed_is_logged_not_sent', '[CONFIRMED CLOSE AUTH]' in app and 'fuera de la ventana post-cierre' in app)
ck('spot_has_per_tf_close_watermarks', '_SPOT_CONFIRMED_WATERMARK_ATTR' in app and 'closed_candle_watermarks' in app)
ck('spot_compute_uses_only_due_timeframes', "due_close_by_tf = _spot_due_confirmed_timeframes" in app and "if tf in due_close_by_tf" in app)
ck('spot_preserves_non_due_confirmed_snapshots', 'Preserve the latest confirmed snapshot for TFs whose candle has NOT just' in app)
ck('spot_partial_failure_does_not_advance_watermark', 'incompleto' in app and 'se reintentará' in app)
ck('spot_watermarks_persist_to_supabase_snapshot', "'closed_candle_watermarks': watermarks" in app)
ck('spot_watermarks_restore_after_worker_recycle', "payload.get('closed_candle_watermarks')" in app)

# Quality/frequency policy: this release fixes timing, it does not manufacture Premium.
ck('entry65_unchanged', 'entry_q<65.0' in runtime)
ck('sl60_unchanged', 'sl_rel<60.0' in runtime)
ck('tp60_unchanged', 'tp_q<60.0' in runtime)
ck('no_quality_threshold_change_in_close_module', all(x not in mod_path.read_text(encoding='utf-8') for x in ['execution_safety','entry_quality_score','sl_reliability','tp_quality_score']))

# Render/free-resource contract remains unchanged.
ck('one_worker_two_threads', '--workers 1 --threads 2' in proc and '--workers 1 --threads 2' in render)
ck('new_entrypoint_19_2_3', 'commit19_2_3_main_entrypoint:app' in proc and 'commit19_2_3_main_entrypoint:app' in render)
ck('memory_guards_unchanged', '_MEMORY_HARD_LIMIT_MB = min(_MEMORY_HARD_LIMIT_MB, 300.0)' in app and '_MEMORY_JOB_START_LIMIT_MB = min(_MEMORY_JOB_START_LIMIT_MB, 200.0)' in app)
ck('no_new_network_in_close_authority', all(x not in mod_path.read_text(encoding='utf-8').lower() for x in ['requests.', 'urllib', 'http://', 'https://']))
ck('no_new_threads_in_close_authority', 'threading' not in mod_path.read_text(encoding='utf-8'))

passed=sum(ok for _,ok in checks); total=len(checks)
print(f'\nSUMMARY {passed}/{total} PASS')
failed=[name for name,ok in checks if not ok]
if failed:
    print('FAILED',failed)
    raise SystemExit(1)
