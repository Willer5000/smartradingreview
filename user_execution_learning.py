"""RC9.7.14 — aggregated real-execution learning for Futures.

Purpose
-------
Use CLOSED saved Futures trades from all users as a secondary, de-identified
continuity signal for ReviewTrader and as post-trade diagnostics for the UI.

Guardrails
----------
* Never reads/returns ``user_name``.
* One canonical system signal counts once even if several users saved it.
* Manual/modified trades are diagnostic only and never change ReviewTrader.
* N < 8 is OBSERVE_ONLY. A single TP/SL is learned/stored but has zero authority.
* Positive support is capped at +5 points; negative penalty at -8 points.
* It never changes direction, Entry, SL, TP, Safety or leverage. After N>=8 canonical samples, repeated bad Entry behavior can advise better geometry but never becomes a second publication veto.
* Backtest/OOS remains primary authority in ReviewTrader.
* No SQL/schema changes: only existing ``saved_signals`` and ``signals`` fields.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "RC9_7_14_GLOBAL_EXECUTION_LEARNING_V1"
_CACHE_TTL_SECONDS = 2 * 60 * 60
_MAX_ROWS = 700
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"ts": 0.0, "rows": [], "raw_rows": [], "profiles": {}}
_SOURCE_CACHE_LOCK = threading.Lock()
_SOURCE_CACHE: Dict[str, Dict[str, Any]] = {}
_SOURCE_CACHE_TTL_SECONDS = 30 * 60
_SOURCE_CACHE_MAX = 96
_GUARDIAN_POLICY_CACHE_LOCK = threading.Lock()
_GUARDIAN_POLICY_CACHE: Dict[str, Any] = {"ts": 0.0, "profiles": {}}
_GUARDIAN_POLICY_CACHE_TTL_SECONDS = 2 * 60 * 60



def _db():
    try:
        from supabase_client import supabase_db
        if supabase_db and getattr(supabase_db, "enabled", False):
            return supabase_db
    except Exception:
        pass
    return None


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _action(value: Any) -> str:
    text = str(value or "").strip().upper()
    return {"COMPRA_SPOT": "LONG", "VENTA_SPOT": "SHORT"}.get(text, text)


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "-")


def _same_level(a: Any, b: Any) -> bool:
    fa, fb = _float(a), _float(b)
    if fa is None or fb is None:
        return True  # legacy row: absence cannot prove a manual modification
    tol = max(1e-10, abs(fb) * 1e-7)
    return abs(fa - fb) <= tol


def _canonical_system_execution(row: Dict[str, Any]) -> bool:
    """True only when the user's saved trade preserved the system geometry."""
    if not isinstance(row, dict):
        return False
    if not str(row.get("source_signal_id") or "").strip():
        return False
    if not _bool(row.get("system_executable")):
        return False
    if str(row.get("execution_origin") or "").upper() != "SYSTEM_EXECUTABLE":
        return False
    if _action(row.get("action")) not in {"LONG", "SHORT"}:
        return False
    if str(row.get("status") or "").lower() not in {"tp_hit", "sl_hit"}:
        return False
    if not _bool(row.get("entry_touched")):
        return False
    checks = (
        (row.get("entry"), row.get("original_entry")),
        (row.get("stop_loss"), row.get("original_stop_loss")),
        (row.get("take_profit"), row.get("original_take_profit")),
    )
    return all(_same_level(a, b) for a, b in checks)


def _outcome_r(row: Dict[str, Any]) -> Optional[float]:
    """Signed realized R whenever it can be reconstructed.

    Important: ``sl_hit`` describes the exit mechanism, NOT necessarily a loss.
    A Guardian-protected LONG can move SL above Entry and later close by SL with
    positive R; SHORT is analogous. Therefore status is only a last fallback.
    """
    for key in ("actual_close_r", "estimated_net_r", "gross_r"):
        value = _float(row.get(key))
        if value is not None:
            return value

    entry = _float(row.get("original_entry"), _float(row.get("entry")))
    sl = _float(row.get("original_stop_loss"), _float(row.get("stop_loss")))
    close_price = _float(row.get("closed_price"))
    action = _action(row.get("action"))
    if None not in (entry, sl, close_price) and entry and sl and close_price:
        risk = abs(entry - sl)
        if risk > 0:
            if action == "LONG":
                return (close_price - entry) / risk
            if action == "SHORT":
                return (entry - close_price) / risk

    status = str(row.get("status") or "").lower()
    if status == "tp_hit":
        rr = _float(row.get("original_risk_reward"))
        if rr is None:
            tp = _float(row.get("original_take_profit"), _float(row.get("take_profit")))
            if None not in (entry, sl, tp):
                risk = abs(entry - sl)
                reward = abs(tp - entry)
                if risk > 0:
                    rr = reward / risk
        return rr if rr is not None else 1.0
    if status == "sl_hit":
        # Only fallback when no signed close information exists.
        return -1.0

    # Manual/Guardian exits can still be classified from signed PnL when R is
    # unavailable. Keep magnitude conservative; this is diagnostic, not a
    # substitute for a real R calculation.
    for key in ("estimated_net_pnl_pct", "pnl_pct"):
        pnl = _float(row.get(key))
        if pnl is not None:
            if pnl > 0:
                return 0.01
            if pnl < 0:
                return -0.01
            return 0.0
    return None


def invalidate_global_execution_cache() -> None:
    """Called after a saved trade closes; reload compact execution/Guardian evidence."""
    with _CACHE_LOCK:
        _CACHE["ts"] = 0.0
        _CACHE["rows"] = []
        _CACHE["raw_rows"] = []
        _CACHE["profiles"] = {}
    with _GUARDIAN_POLICY_CACHE_LOCK:
        _GUARDIAN_POLICY_CACHE["ts"] = 0.0
        _GUARDIAN_POLICY_CACHE["profiles"] = {}


def _fetch_closed_rows() -> List[Dict[str, Any]]:
    db = _db()
    if db is None or (hasattr(db, "read_circuit_open") and db.read_circuit_open()):
        return []

    # Cross-user learning is aggregate/de-identified; identity is not selected.
    fields = (
        "id,source_signal_id,symbol,timeframe,action,status,entry_touched,"
        "entry,stop_loss,take_profit,original_entry,original_stop_loss,"
        "original_take_profit,original_risk_reward,execution_origin,"
        "system_executable,risk_class,candle_timestamp,close_reason,closed_at,"
        "actual_close_r,estimated_net_r,gross_r,mfe_r,mae_r,"
        "candles_to_mfe,candles_to_mae,estimated_net_pnl_pct,pnl_pct,closed_price"
    )
    fallback = (
        "id,source_signal_id,symbol,timeframe,action,status,entry_touched,"
        "entry,stop_loss,take_profit,original_entry,original_stop_loss,"
        "original_take_profit,original_risk_reward,execution_origin,"
        "system_executable,risk_class,candle_timestamp,closed_at,pnl_pct,closed_price"
    )
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

    def run(select_fields: str):
        q = (
            db.client.table("saved_signals")
            .select(select_fields)
            .in_("status", ["tp_hit", "sl_hit", "closed_manual"])
            .gte("closed_at", cutoff)
            .order("closed_at", desc=True)
            .limit(_MAX_ROWS)
        )
        return db._with_retry(lambda: q.execute())

    try:
        response = run(fields)
    except Exception:
        try:
            response = run(fallback)
        except Exception:
            return []
    return list(response.data or []) if response else []


def _dedupe_canonical(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One system signal = one sample, regardless of how many users saved it."""
    selected: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        if not _canonical_system_execution(row):
            continue
        sid = str(row.get("source_signal_id") or "").strip()
        if not sid:
            continue
        # TP/SL is preferred over manual close because it reflects original geometry.
        current = selected.get(sid)
        if current is None:
            selected[sid] = row
            continue
        cur_status = str(current.get("status") or "").lower()
        new_status = str(row.get("status") or "").lower()
        if cur_status == "closed_manual" and new_status in {"tp_hit", "sl_hit"}:
            selected[sid] = row
    return list(selected.values())


def _profile(rows: Iterable[Dict[str, Any]], symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    sym, tf, act = _symbol(symbol), str(timeframe or ""), _action(action)
    cell = [r for r in rows if _symbol(r.get("symbol")) == sym and str(r.get("timeframe") or "") == tf and _action(r.get("action")) == act]
    r_values = [v for v in (_outcome_r(r) for r in cell) if v is not None]
    # Economic sign wins. Exit mechanism (TP/SL/manual/Guardian) is kept as
    # a separate diagnostic dimension. A protected SL above Entry is a win.
    wins = sum(1 for r in cell if (_outcome_r(r) is not None and _outcome_r(r) > 0))
    losses = sum(1 for r in cell if (_outcome_r(r) is not None and _outcome_r(r) < 0))
    n = len(r_values)
    expectancy = (sum(r_values) / n) if n else 0.0
    win_rate = (wins / max(1, wins + losses)) * 100.0

    fast_sl = 0
    weak_progress_sl = 0
    weak_rr = 0
    mfe_vals: List[float] = []
    mae_vals: List[float] = []
    for row in cell:
        status = str(row.get("status") or "").lower()
        mfe = _float(row.get("mfe_r"))
        mae = _float(row.get("mae_r"))
        cmae = _float(row.get("candles_to_mae"))
        rr = _float(row.get("original_risk_reward"))
        if mfe is not None:
            mfe_vals.append(mfe)
        if mae is not None:
            mae_vals.append(mae)
        if rr is not None and rr < 1.2:
            weak_rr += 1
        actual_r = _outcome_r(row)
        # A protected stop can close with positive R. Only economically negative
        # outcomes count as fast/weak SL evidence against Entry quality.
        if status == "sl_hit" and actual_r is not None and actual_r < 0:
            if mfe is not None and mfe < 0.25:
                weak_progress_sl += 1
            if cmae is not None and cmae <= 2 and (mfe is None or mfe < 0.25):
                fast_sl += 1

    authority = "OBSERVE_ONLY"
    adjustment = 0.0
    reason = "Muestra insuficiente; se registra pero no modifica decisiones."
    if n >= 8:
        authority = "BOUNDED_CONTINUITY"
        penalty = 0.0
        support = 0.0
        if expectancy < 0:
            penalty += min(5.0, 2.0 + abs(expectancy) * 3.0)
        if win_rate < 40.0:
            penalty += 1.5
        if n and (fast_sl / n) >= 0.30:
            penalty += 1.5
        penalty = min(8.0, penalty)
        if n >= 12 and expectancy >= 0.15 and win_rate >= 52.0:
            support = min(5.0, 2.0 + expectancy * 3.0 + max(0.0, win_rate - 52.0) / 15.0)
        adjustment = max(-8.0, min(5.0, support - penalty))
        reason = (
            "Continuidad real agregada positiva y acotada."
            if adjustment > 0
            else "Continuidad real agregada deteriorada; aplica penalización acotada."
            if adjustment < 0
            else "Evidencia real mixta; sin ajuste."
        )

    return {
        "version": VERSION,
        "market": "futures",
        "symbol": sym,
        "timeframe": tf,
        "action": act,
        "sample_size": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "expectancy_r": round(expectancy, 4),
        "avg_mfe_r": round(sum(mfe_vals) / len(mfe_vals), 4) if mfe_vals else None,
        "avg_mae_r": round(sum(mae_vals) / len(mae_vals), 4) if mae_vals else None,
        "fast_sl_rate": round(fast_sl / n, 4) if n else 0.0,
        "weak_progress_sl_rate": round(weak_progress_sl / n, 4) if n else 0.0,
        "weak_rr_rate": round(weak_rr / max(1, len(cell)), 4) if cell else 0.0,
        "authority": authority,
        "score_adjustment": round(adjustment, 2),
        "reason": reason,
        "deidentified_all_users": True,
        "deduped_by_source_signal": True,
        "changes_geometry": False,
    }


def _ensure_cache() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[Tuple[str, str, str], Dict[str, Any]]]:
    now = time.monotonic()
    with _CACHE_LOCK:
        if (now - float(_CACHE.get("ts") or 0.0)) < _CACHE_TTL_SECONDS:
            return (
                list(_CACHE.get("rows") or []),
                list(_CACHE.get("raw_rows") or []),
                dict(_CACHE.get("profiles") or {}),
            )
    raw_rows = _fetch_closed_rows()
    rows = _dedupe_canonical(raw_rows)
    profiles: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    keys = {(_symbol(r.get("symbol")), str(r.get("timeframe") or ""), _action(r.get("action"))) for r in raw_rows}
    for key in keys:
        profiles[key] = _profile(rows, *key)
    with _CACHE_LOCK:
        _CACHE["ts"] = now
        _CACHE["rows"] = list(rows)
        _CACHE["raw_rows"] = list(raw_rows)
        _CACHE["profiles"] = dict(profiles)
    return rows, raw_rows, profiles


def get_global_execution_profile(symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    rows, raw_rows, profiles = _ensure_cache()
    key = (_symbol(symbol), str(timeframe or ""), _action(action))
    profile = dict(profiles.get(key) or _profile(rows, *key))

    observed = [
        r for r in raw_rows
        if _symbol(r.get('symbol')) == key[0]
        and str(r.get('timeframe') or '') == key[1]
        and _action(r.get('action')) == key[2]
        and _bool(r.get('entry_touched'))
    ]
    manual = [r for r in observed if str(r.get('execution_origin') or '').upper() != 'SYSTEM_EXECUTABLE']
    fast_adverse = 0
    for r in observed:
        actual = _outcome_r(r)
        if actual is None or actual >= 0:
            continue
        mfe = _float(r.get('mfe_r'))
        cmae = _float(r.get('candles_to_mae'))
        if cmae is not None and cmae <= 2 and (mfe is None or mfe < 0.25):
            fast_adverse += 1

    # Actual managed execution (including Guardian) is a separate track from
    # the unchanged original-plan canonical sample. One source signal still
    # counts once even when several users followed it.
    managed_groups: Dict[str, List[float]] = {}
    for r in observed:
        if str(r.get('execution_origin') or '').upper() != 'SYSTEM_EXECUTABLE':
            continue
        sid = str(r.get('source_signal_id') or '').strip()
        value = _outcome_r(r)
        if not sid or value is None:
            continue
        managed_groups.setdefault(sid, []).append(value)
    managed_values = [sum(values) / len(values) for values in managed_groups.values() if values]
    managed_wins = sum(1 for value in managed_values if value > 0)
    managed_losses = sum(1 for value in managed_values if value < 0)

    profile.update({
        'observed_trade_count_all_users': len(observed),
        'manual_diagnostic_count': len(manual),
        'all_user_fast_adverse_rate': round(fast_adverse / len(observed), 4) if observed else 0.0,
        'manual_trades_affect_authority': False,
        'managed_system_sample_size': len(managed_values),
        'managed_system_wins': managed_wins,
        'managed_system_losses': managed_losses,
        'managed_system_win_rate': round(
            managed_wins / max(1, managed_wins + managed_losses) * 100.0, 2
        ) if managed_values else 0.0,
        'managed_system_expectancy_r': round(
            sum(managed_values) / len(managed_values), 4
        ) if managed_values else None,
        'managed_track_includes_guardian': True,
        'managed_track_affects_direction': False,
    })
    return profile


def adjust_review_score(existing_score: float, symbol: str, timeframe: str, action: str) -> Tuple[float, Dict[str, Any]]:
    """Compatibility helper: execution outcomes never rewrite directional score.

    RC9.7.14 deliberately learns bad/good execution at the Entry/publication layer.
    A poor Entry must not be reinterpreted as evidence that the LONG/SHORT thesis
    itself was wrong.  Keep the helper for callers from older builds, but make it
    an explicit no-op.
    """
    score = float(existing_score or 0.0)
    return score, get_global_execution_profile(symbol, timeframe, action)


def get_guardian_trade_review(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Read Guardian events for one saved trade without exposing identity.

    EXIT/PROTECT events already carry a counterfactual ``delta_r`` after the
    original HOLD path is reconstructed by ``saved_signals``. Positive delta_r
    means Guardian improved R versus holding the original plan; negative means
    it cut/managed the trade worse than HOLD. This is the correct evidence for
    learning whether Guardian itself was right or wrong.
    """
    signal = signal or {}
    saved_id = str(signal.get("id") or "").strip()
    if not saved_id:
        return {"available": False, "events": [], "evaluated": 0}
    db = _db()
    if db is None:
        return {"available": False, "events": [], "evaluated": 0}
    fields = (
        "event_action,event_bucket,observed_at,observed_price,observed_r,"
        "deterioration_score,progress_r,suggested_stop_loss,"
        "suggested_take_profit,counterfactual_status,counterfactual_r,"
        "delta_r,would_help,actual_close_r,actual_close_reason,evaluation_note"
    )
    try:
        response = db._with_retry(lambda: (
            db.client.table("guardian_learning_events")
            .select(fields)
            .eq("signal_id", saved_id)
            .order("observed_at", desc=False)
            .limit(30)
            .execute()
        ))
        rows = list(response.data or []) if response else []
    except Exception:
        rows = []

    compact = []
    deltas = []
    for row in rows:
        status = str(row.get("counterfactual_status") or "").upper()
        delta = _float(row.get("delta_r"))
        if status.startswith("EVALUATED") and delta is not None:
            deltas.append(delta)
        compact.append({
            "action": str(row.get("event_action") or "").upper(),
            "observed_at": row.get("observed_at"),
            "observed_r": _float(row.get("observed_r")),
            "deterioration_score": _float(row.get("deterioration_score")),
            "progress_r": _float(row.get("progress_r")),
            "suggested_stop_loss": _float(row.get("suggested_stop_loss")),
            "suggested_take_profit": _float(row.get("suggested_take_profit")),
            "counterfactual_status": status,
            "counterfactual_r": _float(row.get("counterfactual_r")),
            "delta_r": delta,
            "would_help": row.get("would_help"),
            "actual_close_r": _float(row.get("actual_close_r")),
            "actual_close_reason": row.get("actual_close_reason"),
            "note": row.get("evaluation_note"),
        })
    helpful = sum(1 for d in deltas if d > 0)
    harmful = sum(1 for d in deltas if d < 0)
    return {
        "available": bool(rows),
        "events": compact,
        "evaluated": len(deltas),
        "helpful": helpful,
        "harmful": harmful,
        "avg_delta_r": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "learning_interpretation": (
            "HELPFUL" if deltas and sum(deltas) > 0
            else "HARMFUL" if deltas and sum(deltas) < 0
            else "PENDING_OR_NEUTRAL"
        ),
        "identity_exposed": False,
    }


def get_saved_trade_forensics(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Decompose one closed trade into economic, Entry and Guardian evidence.

    One trade remains ONE market sample. Component labels are multiple views of
    the same sample and are never counted as independent N.
    """
    signal = signal or {}
    status = str(signal.get("status") or "").lower()
    mfe = _float(signal.get("mfe_r"))
    mae = _float(signal.get("mae_r"))
    cmae = _float(signal.get("candles_to_mae"))
    rr = _float(signal.get("original_risk_reward"))
    actual_r = _outcome_r(signal)
    guardian = get_guardian_trade_review(signal)
    reasons: List[str] = []
    tags: List[str] = []

    economic_outcome = (
        "WIN" if actual_r is not None and actual_r > 0
        else "LOSS" if actual_r is not None and actual_r < 0
        else "BREAKEVEN" if actual_r is not None
        else "UNKNOWN"
    )

    if rr is not None and rr < 1.0:
        tags.append("WEAK_RR_GEOMETRY")
        reasons.append(f"La geometría original ofrecía R/R {rr:.2f}, menor a 1:1.")
    elif rr is not None and rr < 1.2:
        tags.append("MARGINAL_RR_GEOMETRY")
        reasons.append(f"La geometría original tenía R/R ajustado ({rr:.2f}).")

    # Economic result first. A stop can be a profitable protected stop.
    if actual_r is not None and actual_r > 0:
        tags.append("POSITIVE_ECONOMIC_OUTCOME")
        if status == "sl_hit":
            tags.append("PROTECTED_STOP_WIN")
            reasons.append(
                "La salida fue por Stop Loss, pero el stop protegido cerró por encima de break-even: económicamente es un trade positivo."
            )
        elif status == "closed_manual":
            reasons.append("El cierre gestionado terminó con R positivo; se registra como resultado económico favorable.")
        elif status == "tp_hit":
            tags.append("ENTRY_DEFENDED_TO_TARGET")
            reasons.append("El plan alcanzó TP con resultado económico positivo.")

    if actual_r is not None and actual_r < 0:
        if mfe is not None and mfe < 0.25:
            tags.append("ENTRY_TIMING_SUSPECTED")
            reasons.append(
                "Tras tocar Entry, el precio avanzó menos de 0.25R a favor antes del resultado negativo; el timing/Entry merece revisión."
            )
        if cmae is not None and cmae <= 2 and (mfe is None or mfe < 0.25):
            tags.append("FAST_ADVERSE_MOVE")
            reasons.append("El movimiento adverso apareció en las primeras dos velas tras Entry.")
        if mfe is not None and mfe >= 0.75:
            tags.append("MANAGEMENT_OR_STOP_REVIEW")
            reasons.append(
                "La operación desarrolló avance relevante antes de terminar negativa; revisar Guardian/SL/gestión además del Entry."
            )

    guardian_eval = str(guardian.get("learning_interpretation") or "")
    if guardian_eval == "HELPFUL":
        tags.append("GUARDIAN_HELPFUL")
        reasons.append(
            f"El contrafactual del Guardian mejoró el resultado frente a HOLD en promedio {float(guardian.get('avg_delta_r') or 0):+.2f}R."
        )
    elif guardian_eval == "HARMFUL":
        tags.append("GUARDIAN_HARMFUL")
        reasons.append(
            f"El contrafactual indica que Guardian empeoró el resultado frente a HOLD en promedio {float(guardian.get('avg_delta_r') or 0):+.2f}R; sus umbrales deben aprender de este patrón si se repite."
        )

    if not reasons:
        reasons.append(
            "Todavía no hay evidencia suficiente para atribuir el resultado a Entry, SL, TP, estrategia o Guardian con certeza."
        )

    component_assessment = {
        "economic_result": {
            "outcome": economic_outcome,
            "actual_r": round(actual_r, 4) if actual_r is not None else None,
        },
        "entry": {
            "state": (
                "REVIEW" if "ENTRY_TIMING_SUSPECTED" in tags or "FAST_ADVERSE_MOVE" in tags
                else "SUPPORTED" if "ENTRY_DEFENDED_TO_TARGET" in tags
                else "UNRESOLVED"
            ),
            "mfe_r": mfe,
            "mae_r": mae,
        },
        "geometry": {
            "state": (
                "WEAK" if "WEAK_RR_GEOMETRY" in tags
                else "MARGINAL" if "MARGINAL_RR_GEOMETRY" in tags
                else "UNFLAGGED"
            ),
            "original_rr": rr,
        },
        "guardian": {
            "state": guardian_eval or "PENDING_OR_NEUTRAL",
            "evaluated_events": int(guardian.get("evaluated") or 0),
            "avg_delta_r": guardian.get("avg_delta_r"),
        },
        "strategy": {
            "state": "ONE_SHARED_SAMPLE",
            "note": "La estrategia se audita con el outcome canónico de la señal; este trade no se multiplica como muestras independientes por componente.",
        },
        "direction": {
            "state": "SEPARATE_FROM_ENTRY",
            "note": "Un Entry malo no se interpreta automáticamente como dirección LONG/SHORT equivocada.",
        },
    }

    return {
        "version": VERSION,
        "status": status,
        "economic_outcome": economic_outcome,
        "actual_r": round(actual_r, 4) if actual_r is not None else None,
        "mfe_r": mfe,
        "mae_r": mae,
        "diagnostic_tags": tags,
        "reasons": reasons,
        "entry_issue_suspected": "ENTRY_TIMING_SUSPECTED" in tags,
        "guardian_review": guardian,
        "component_assessment": component_assessment,
        "diagnostic_only": True,
        "single_trade_changes_policy": False,
        "one_trade_equals_one_market_sample": True,
    }


def _ts_iso(value: Any) -> str:
    try:
        text = str(value or "").strip()
        if not text:
            return ""
        # Avoid pandas dependency in this lightweight module.
        return text.replace("Z", "+00:00")
    except Exception:
        return ""


def _ts_key(value: Any) -> Optional[int]:
    text = _ts_iso(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace(' ', 'T'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp())
    except Exception:
        return None


def _source_cache_get(key: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _SOURCE_CACHE_LOCK:
        item = _SOURCE_CACHE.get(key)
        if not item or now - float(item.get("ts") or 0.0) > _SOURCE_CACHE_TTL_SECONDS:
            _SOURCE_CACHE.pop(key, None)
            return None
        return dict(item.get("value") or {})


def _source_cache_put(key: str, value: Dict[str, Any]) -> None:
    with _SOURCE_CACHE_LOCK:
        _SOURCE_CACHE[key] = {"ts": time.monotonic(), "value": dict(value or {})}
        if len(_SOURCE_CACHE) > _SOURCE_CACHE_MAX:
            oldest = sorted(_SOURCE_CACHE.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0.0))[:len(_SOURCE_CACHE)-_SOURCE_CACHE_MAX]
            for old_key, _ in oldest:
                _SOURCE_CACHE.pop(old_key, None)


def get_source_signal_configuration(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Return compact original strategy/motives from canonical ReviewTrader signal."""
    signal = signal or {}
    sym = _symbol(signal.get("symbol"))
    tf = str(signal.get("timeframe") or "")
    act = _action(signal.get("action"))
    candle = _ts_iso(signal.get("candle_timestamp"))
    cache_key = f"{sym}|{tf}|{act}|{candle}"
    cached = _source_cache_get(cache_key)
    if cached is not None:
        return cached

    db = _db()
    if db is None or not sym or not tf or act not in {"LONG", "SHORT"}:
        return {}

    fields = "confidence,entry_price,stop_loss,take_profit,leverage,risk_reward,candle_timestamp,context,indicators_snapshot"
    row = None
    try:
        def _op():
            q = (
                db.client.table("signals")
                .select(fields)
                .eq("symbol", sym)
                .eq("timeframe", tf)
                .eq("system_type", "futures")
                .eq("action_normalized", act)
            )
            if candle:
                q = q.eq("candle_timestamp", candle)
            return q.order("candle_timestamp", desc=True).limit(1).execute()
        response = db._with_retry(_op)
        if response and response.data:
            row = response.data[0]
    except Exception:
        row = None

    # Timestamp formatting can differ across legacy rows. An exact SELECT can
    # return zero rows without raising, so the bounded fallback is also needed
    # after a clean empty response. Never substitute a different candle when
    # the saved signal already carries a source candle timestamp.
    if row is None:
        try:
            response = db._with_retry(lambda: (
                db.client.table("signals").select(fields)
                .eq("symbol", sym).eq("timeframe", tf).eq("system_type", "futures")
                .eq("action_normalized", act).order("candle_timestamp", desc=True).limit(6).execute()
            ))
            candidates = list(response.data or []) if response else []
            wanted_ts = _ts_key(candle)
            if wanted_ts is not None:
                row = next(
                    (candidate for candidate in candidates if _ts_key(candidate.get('candle_timestamp')) == wanted_ts),
                    None,
                )
            elif candidates:
                row = candidates[0]
        except Exception:
            row = None

    if not isinstance(row, dict):
        result = {"available": False, "reason": "SOURCE_SIGNAL_NOT_FOUND"}
        _source_cache_put(cache_key, result)
        return result

    context = row.get("context") or {}
    learning = context.get("learning") or {} if isinstance(context, dict) else {}
    op = learning.get("operational_source_v1") or {} if isinstance(learning, dict) else {}
    attrib = learning.get("strategy_attribution_v2") or {} if isinstance(learning, dict) else {}
    execution = context.get("execution") or {} if isinstance(context, dict) else {}
    market_regime = context.get("market_regime") or {} if isinstance(context, dict) else {}
    items = list(attrib.get("items") or []) if isinstance(attrib, dict) else []
    support = [i for i in items if isinstance(i, dict) and str(i.get("relation_to_final") or "") == "SUPPORT"][:8]
    oppose = [i for i in items if isinstance(i, dict) and str(i.get("relation_to_final") or "") == "OPPOSE"][:5]
    indicators = row.get("indicators_snapshot") or {}

    reasons: List[str] = []
    family = str(op.get("default_family") or "").strip()
    strategy_id = str(op.get("default_strategy_id") or "").strip()
    if strategy_id or family:
        reasons.append(f"Playbook seleccionado: {strategy_id or family}.")
    mtf = str(op.get("mtf_alignment") or "").strip()
    if mtf:
        reasons.append(f"Alineación multitemporal: {mtf}.")
    thesis_quality = _float(op.get("thesis_quality"))
    if thesis_quality is not None:
        reasons.append(f"Calidad de tesis al confirmar: {thesis_quality:.1f}.")
    for item in support[:3]:
        strategy = str(item.get("strategy") or "").strip()
        trader = str(item.get("trader") or "").strip()
        if strategy:
            reasons.append(f"{trader or 'Especialista'} apoyó con {strategy}.")

    result = {
        "available": True,
        "source_candle_timestamp": row.get("candle_timestamp"),
        "confidence": row.get("confidence"),
        "strategy": {
            "id": strategy_id or None,
            "family": family or None,
            "archetype_id": op.get("default_archetype_id"),
            "specialization_key": op.get("default_specialization_key"),
            "source": op.get("candidate_source"),
            "quality": op.get("default_quality"),
            "research_state": op.get("research_state"),
        },
        "thesis": {
            "direction": op.get("thesis_direction"),
            "quality": op.get("thesis_quality"),
            "families": list(op.get("thesis_families") or [])[:8],
            "mtf_alignment": op.get("mtf_alignment"),
            "mtf_complete": op.get("mtf_complete"),
        },
        "market_regime": {
            "regime": market_regime.get("regime"),
            "confidence": market_regime.get("confidence"),
        },
        "execution": {
            "entry_score": execution.get("entry_score"),
            "entry_smc_raw_score": execution.get("entry_smc_raw_score"),
            "entry_reachability_score": execution.get("entry_reachability_score"),
            "entry_defensibility_score": execution.get("entry_defensibility_score"),
            "entry_distance_atr": execution.get("entry_distance_atr"),
            "entry_distance_pct": execution.get("entry_distance_pct"),
            "entry_source": execution.get("entry_source"),
            "entry_timing_mode": execution.get("entry_timing_mode"),
            "entry_independent_confluence_families": execution.get("entry_independent_confluence_families"),
            "sl_source": execution.get("sl_source"),
            "tp_source": execution.get("tp_source"),
            "execution_safety": execution.get("execution_safety"),
            "sl_reliability": execution.get("sl_reliability"),
            "tp_quality_score": execution.get("tp_quality_score"),
            "risk_reward": row.get("risk_reward"),
        },
        "supporting_strategies": support,
        "opposing_strategies": oppose,
        "key_indicators": {k: indicators.get(k) for k in ("rsi", "adx", "plus_di", "minus_di", "atr_pct", "macd_hist", "volume_ratio") if isinstance(indicators, dict) and k in indicators},
        "motives": reasons[:8],
        "read_only": True,
    }
    _source_cache_put(cache_key, result)
    return result


def _build_guardian_policy_profiles() -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """Aggregate Guardian counterfactuals across users, deduped by source signal.

    No user identity is selected. One market signal contributes at most one
    delta per Guardian action, even if several users followed it.
    """
    now = time.monotonic()
    with _GUARDIAN_POLICY_CACHE_LOCK:
        if now - float(_GUARDIAN_POLICY_CACHE.get("ts") or 0.0) < _GUARDIAN_POLICY_CACHE_TTL_SECONDS:
            return dict(_GUARDIAN_POLICY_CACHE.get("profiles") or {})

    _rows, raw_rows, _profiles = _ensure_cache()
    saved_to_source = {
        str(r.get("id") or ""): str(r.get("source_signal_id") or "")
        for r in raw_rows
        if str(r.get("id") or "") and str(r.get("source_signal_id") or "")
    }
    db = _db()
    if db is None or not saved_to_source:
        return {}
    fields = (
        "signal_id,symbol,timeframe,direction,event_action,"
        "counterfactual_status,delta_r,observed_at"
    )
    try:
        response = db._with_retry(lambda: (
            db.client.table("guardian_learning_events")
            .select(fields)
            .order("observed_at", desc=True)
            .limit(700)
            .execute()
        ))
        events = list(response.data or []) if response else []
    except Exception:
        events = []

    # One delta per source signal + action. Multiple users/buckets do not turn
    # one market event into independent evidence. If several evaluated events
    # exist, average them inside that market sample first.
    per_source: Dict[Tuple[str, str], List[float]] = {}
    context_for_source: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {}
    for event in events:
        status = str(event.get("counterfactual_status") or "").upper()
        delta = _float(event.get("delta_r"))
        if not status.startswith("EVALUATED") or delta is None:
            continue
        saved_id = str(event.get("signal_id") or "")
        source_id = saved_to_source.get(saved_id)
        if not source_id:
            continue
        action = str(event.get("event_action") or "").upper()
        if action not in {"EXIT", "PROTECT"}:
            continue
        source_key = (source_id, action)
        per_source.setdefault(source_key, []).append(delta)
        context_for_source[source_key] = (
            _symbol(event.get("symbol")),
            str(event.get("timeframe") or ""),
            _action(event.get("direction")),
            action,
        )

    grouped: Dict[Tuple[str, str, str, str], List[float]] = {}
    for source_key, deltas in per_source.items():
        if not deltas:
            continue
        context = context_for_source.get(source_key)
        if not context:
            continue
        grouped.setdefault(context, []).append(sum(deltas) / len(deltas))

    profiles: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for key, deltas in grouped.items():
        n = len(deltas)
        avg = sum(deltas) / n if n else 0.0
        helpful = sum(1 for d in deltas if d > 0)
        harmful = sum(1 for d in deltas if d < 0)
        profiles[key] = {
            "sample_size": n,
            "avg_delta_r": round(avg, 4),
            "helpful_rate": round(helpful / n, 4) if n else 0.0,
            "harmful_rate": round(harmful / n, 4) if n else 0.0,
            "authority": "BOUNDED_CALIBRATION" if n >= 8 else "OBSERVE_ONLY",
            "deduped_by_source_signal": True,
            "deidentified_all_users": True,
        }

    with _GUARDIAN_POLICY_CACHE_LOCK:
        _GUARDIAN_POLICY_CACHE["ts"] = now
        _GUARDIAN_POLICY_CACHE["profiles"] = dict(profiles)
    return profiles


def get_guardian_policy_adjustment(symbol: str, timeframe: str, action: str) -> Dict[str, Any]:
    """Bounded all-user calibration for Guardian EXIT and PROTECT behavior.

    Each source signal remains one market sample even when several users follow
    it.  EXIT and PROTECT are evaluated against the counterfactual original
    HOLD path.  Positive delta-R means Guardian improved the outcome; negative
    delta-R means the unmanaged original plan would have done better.

    N<8 is OBSERVE_ONLY.  Production changes are deliberately small and never
    rewrite Entry/SL/TP or directional thesis.
    """
    profiles = _build_guardian_policy_profiles()
    base_key = (_symbol(symbol), str(timeframe or ""), _action(action))

    exit_profile = dict(profiles.get(base_key + ("EXIT",)) or {})
    protect_profile = dict(profiles.get(base_key + ("PROTECT",)) or {})

    n = int(exit_profile.get("sample_size") or 0)
    avg = float(exit_profile.get("avg_delta_r") or 0.0)
    helpful = float(exit_profile.get("helpful_rate") or 0.0)
    harmful = float(exit_profile.get("harmful_rate") or 0.0)
    exit_delta = 0.0
    reason = "OBSERVE_ONLY: Guardian necesita >=8 outcomes EXIT contrafactuales comparables."
    if n >= 8:
        if avg <= -0.10 and harmful >= 0.60:
            # Guardian exits too early/wrong too often -> demand more deterioration.
            exit_delta = min(6.0, 2.0 + abs(avg) * 4.0)
            reason = "Guardian históricamente cortó HOLDs mejores; se exige más deterioro antes de EXIT."
        elif avg >= 0.10 and helpful >= 0.60:
            # Guardian consistently saves R -> allow slightly earlier defense.
            exit_delta = -min(4.0, 1.0 + avg * 3.0)
            reason = "Guardian históricamente preservó R; se permite protección algo más temprana."
        else:
            reason = "Evidencia EXIT del Guardian mixta; sin ajuste de umbral."

    pn = int(protect_profile.get("sample_size") or 0)
    pavg = float(protect_profile.get("avg_delta_r") or 0.0)
    phelpful = float(protect_profile.get("helpful_rate") or 0.0)
    pharmful = float(protect_profile.get("harmful_rate") or 0.0)
    protect_policy = "OBSERVE_ONLY"
    protect_reason = "OBSERVE_ONLY: Guardian necesita >=8 PROTECT contrafactuales comparables."
    # Repeated harmful protection usually means the stop was tightened too soon
    # and a later recovery would have outperformed it.  We do not invent a new
    # SL; we merely require more deterioration before accepting a low-urgency
    # PROTECT recommendation.
    if pn >= 8:
        if pavg <= -0.10 and pharmful >= 0.60:
            protect_policy = "REQUIRE_MORE_CONFIRMATION"
            protect_reason = (
                "PROTECT ha cortado recuperaciones mejores de forma repetida; "
                "las protecciones de baja urgencia deben esperar más confirmación."
            )
        elif pavg >= 0.10 and phelpful >= 0.60:
            protect_policy = "SUPPORTED"
            protect_reason = "PROTECT preservó R de forma repetida; se mantiene su conducta actual."
        else:
            protect_policy = "MIXED_NO_CHANGE"
            protect_reason = "Evidencia PROTECT mixta; sin cambio."

    return {
        "version": "RC9_7_14_GUARDIAN_COUNTERFACTUAL_CALIBRATION_V2",
        "sample_size": n,
        "exit_threshold_delta": round(exit_delta, 2),
        "reduce_threshold_delta": round(exit_delta * 0.5, 2),
        "reason": reason,
        "profile": exit_profile,
        "protect_sample_size": pn,
        "protect_policy": protect_policy,
        "protect_reason": protect_reason,
        "protect_profile": protect_profile,
        "changes_entry_sl_tp": False,
        "one_source_signal_one_sample": True,
    }


def get_trade_learning_bundle(signal: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "configuration": get_source_signal_configuration(signal),
        "forensics": get_saved_trade_forensics(signal),
        "global_profile": get_global_execution_profile(
            signal.get("symbol"), signal.get("timeframe"), signal.get("action")
        ),
        "guardian_global_profile": get_guardian_policy_adjustment(
            signal.get("symbol"), signal.get("timeframe"), signal.get("action")
        ),
    }


def get_execution_publication_review(
    symbol: str, timeframe: str, action: str, levels: Dict[str, Any],
) -> Dict[str, Any]:
    """RC9.8: execution learning advises geometry; it never vetoes publication."""
    levels = levels or {}
    profile = get_global_execution_profile(symbol, timeframe, action)
    review = {
        "version": "RC9_8_EXECUTION_GEOMETRY_ADVISORY_V1",
        "authority": profile.get("authority"),
        "sample_size": int(profile.get("sample_size") or 0),
        "block_publication": False,
        "publication_veto_disabled": True,
        "geometry_advice": "KEEP_CURRENT_GEOMETRY",
        "reason": "",
        "profile": profile,
        "changes_levels": False,
        "changes_direction": False,
    }
    if profile.get("authority") != "BOUNDED_CONTINUITY":
        review["reason"] = "OBSERVE_ONLY: muestra insuficiente; sin autoridad sobre geometría."
        return review
    exp_r = float(profile.get("expectancy_r") or 0.0)
    fast_sl = float(profile.get("fast_sl_rate") or 0.0)
    weak_progress = float(profile.get("weak_progress_sl_rate") or 0.0)
    repeated = exp_r < 0.0 and (fast_sl >= 0.30 or weak_progress >= 0.40)
    if repeated:
        defensibility = _float(levels.get("entry_defensibility_score"))
        reachability = _float(levels.get("entry_reachability_score"))
        weak = (defensibility is not None and defensibility < 65.0) or (reachability is not None and reachability < 55.0)
        if weak or (defensibility is None and reachability is None):
            review["geometry_advice"] = "PREFER_BETTER_PROTECTED_ENTRY_GEOMETRY"
        review["reason"] = (
            f"Evidencia ejecución N={review['sample_size']}, Exp={exp_r:.2f}R, "
            f"fast-SL={fast_sl*100:.0f}%, low-progress-SL={weak_progress*100:.0f}%. "
            "Ajusta preferencia geométrica; no bloquea publicación."
        )
    else:
        review["reason"] = "Sin patrón repetido de Entry adverso; conservar geometría actual."
    return review
