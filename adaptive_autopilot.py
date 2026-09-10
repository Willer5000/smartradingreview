"""Commit 4 — ReviewTrader Adaptive Autopilot (governed).

This module converts accumulated evidence into versioned, reversible policies.
It is deliberately conservative:

- insufficient evidence => STATIC/OBSERVE (no production change)
- negative robust evidence => PROTECT (may only reduce risk / tighten quality)
- positive robust evidence => ACTIVE profile with bounded optimization
- strategy promotion requires historical validation AND live evidence
- no AI text can promote a strategy or change risk by itself
- every transition is persisted for audit and rollback

The module never edits Python source at runtime.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
import hashlib
import json
import math
import threading
import time

AUTOPILOT_VERSION = "C9_REVIEWTRADER_AUTOPILOT_V2"
EXECUTION_PROFILE_VERSION = "C9_ADAPTIVE_EXECUTION_PROFILE_V2"
STRATEGY_GOVERNANCE_VERSION = "C8_STRATEGY_GOVERNANCE_V2"

# Evidence gates. These are not trading thresholds; they govern whether learning
# is allowed to change production behavior.
MIN_PROFILE_SAMPLE = 25
MIN_GROWTH_SAMPLE = 50
MIN_STRONG_GROWTH_SAMPLE = 100
MIN_RESEARCH_VALIDATION_N = 25
MIN_LIVE_STRATEGY_N = 25
MIN_RESEARCH_EXPECTANCY_R = 0.10
MIN_RESEARCH_PF = 1.15
MIN_LIVE_EXPECTANCY_R = 0.10
MIN_LIVE_PF = 1.15

# Growth is intentionally bounded even after robust evidence. Hard SL/ATR/
# publication constraints in futures_system remain authoritative.
MAX_LEVERAGE_TARGET_FACTOR = 1.20
MIN_LEVERAGE_CAP_FACTOR = 0.75

DEFAULT_Q2_WEIGHTS = {
    "sl": 0.40,
    "tp": 0.30,
    "rr": 0.30,
}

_RESEARCH_TO_REGISTRY = {
    "Q7_RSI_PROFILE_REPLAY": "Q7_RSI_PROFILE_V1",
    "Q7_RSI_PROFILE_V1": "Q7_RSI_PROFILE_V1",
    "Q7_ROLLING_VWAP_REVERSION_V1": "Q7_ROLLING_VWAP_REVERSION_V1",
    "Q7_BREAKOUT_RETEST_V1": "Q7_BREAKOUT_RETEST_V1",
}

AUTO_RESEARCH_UNIVERSE = [
    (symbol, timeframe)
    for symbol in ("BTC-USDT", "ETH-USDT", "SOL-USDT", "XRP-USDT", "ADA-USDT")
    for timeframe in ("5m", "15m", "30m", "1h", "2h", "4h")
]

_cache_lock = threading.Lock()
_profile_cache: Dict[Tuple[str, str, str, str], Tuple[float, Dict[str, Any]]] = {}
_profile_cache_ttl = 180.0


def _governance_status(db=None) -> Dict[str, Any]:
    """Commit 8: read the persisted fail-closed promotion gate."""
    try:
        from promotion_governance import get_promotion_governance_status
        return get_promotion_governance_status(db)
    except Exception as exc:
        return {
            "quality_optimization_allowed": False,
            "strategy_veto_authority_allowed": False,
            "risk_growth_allowed": False,
            "block_reasons": [f"GOVERNANCE_UNAVAILABLE:{type(exc).__name__}"],
        }


def _positive_authority_enabled(db=None) -> bool:
    """Compatibility alias: positive quality authority is evidence-driven."""
    return bool(_governance_status(db).get("quality_optimization_allowed", False))


def _strategy_veto_authority_enabled(db=None) -> bool:
    return bool(_governance_status(db).get("strategy_veto_authority_allowed", False))


def _risk_growth_enabled(db=None) -> bool:
    # Deliberately false in Commit 8; Commit 9 owns leverage scaling.
    return bool(_governance_status(db).get("risk_growth_allowed", False))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
    return bool(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_weights(weights: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    raw = dict(DEFAULT_Q2_WEIGHTS)
    if isinstance(weights, dict):
        for key in raw:
            if key in weights:
                raw[key] = max(0.0, _safe_float(weights.get(key), raw[key]))
    total = sum(raw.values())
    if total <= 0:
        return dict(DEFAULT_Q2_WEIGHTS)
    return {key: round(value / total, 6) for key, value in raw.items()}


def default_execution_profile(
    symbol: str = "*",
    timeframe: str = "*",
    market_regime: str = "*",
) -> Dict[str, Any]:
    return {
        "version": EXECUTION_PROFILE_VERSION,
        "system_type": "futures",
        "symbol": str(symbol or "*"),
        "timeframe": str(timeframe or "*"),
        "market_regime": str(market_regime or "*"),
        "state": "OBSERVE",
        "production_authority": False,
        "config": {
            # Entry: never moves the level. This is a learned quality gate over
            # the already-computed structural Q1 Entry.
            "entry_min_defensibility": 0.0,
            # Q2: only changes ranking between already-valid structural SL/TP
            # candidates; it cannot invent a level.
            "q2_weights": dict(DEFAULT_Q2_WEIGHTS),
            "q2_min_pair_improvement": 4.0,
            # Leverage: target factor changes only the chosen leverage inside
            # the existing SL/ATR/security/timeframe hard ceilings.
            "leverage_target_factor": 1.0,
            "leverage_cap_factor": 1.0,
            "allow_leverage_growth": False,
            # Commit 9: growth, when globally governed, is selected from a
            # bounded loss budget and structural SL geometry. Timeframe then
            # becomes a soft reference instead of an arbitrary hard ceiling.
            "leverage_policy_mode": "STATIC_MINIMUM",
            "target_loss_budget_pct_margin": 5.0,
            # No learned rule may lower the static safety floor.
            "minimum_safety_delta": 0.0,
        },
        "evidence": {
            "resolved": 0,
            "tp": 0,
            "sl": 0,
            "expectancy_r": None,
            "profit_factor": None,
            "model_complete_net_coverage_pct": 0.0,
            "model_complete_net_expectancy_r": None,
            "model_complete_net_profit_factor": None,
            "avg_mfe_r": None,
            "avg_mae_r": None,
            "stop_without_progress_ratio": None,
            "stop_tight_suspect_ratio": None,
            "reason": "INSUFFICIENT_EVIDENCE",
        },
        "updated_at": None,
    }


def _verified_futures_signal(signal: Dict[str, Any]) -> bool:
    if str(signal.get("system_type") or "").lower() != "futures":
        return False
    context = signal.get("context") or {}
    if not isinstance(context, dict):
        return False
    learning = context.get("learning") or {}
    if not isinstance(learning, dict):
        return False
    return bool(
        learning.get("cohort") == "FUTURES_PERPETUAL_REAL_CLOSED_V1"
        and learning.get("market_data_source") == "KUCOIN_FUTURES_PERPETUAL_REST"
        and not _as_bool(learning.get("market_data_is_synthetic", True))
        and _as_bool(learning.get("source_candle_closed", False))
        and _as_bool(learning.get("statistically_eligible", False))
        and str(learning.get("evaluation_role") or "").upper() == "EXECUTABLE_SIGNAL"
    )


def calculate_execution_metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    resolved: List[Dict[str, Any]] = []
    for row in rows or []:
        status = str(row.get("status") or "").lower()
        if status in {"tp_hit", "sl_hit"}:
            resolved.append(row)

    n = len(resolved)
    tp = sum(1 for row in resolved if str(row.get("status") or "").lower() == "tp_hit")
    sl = n - tp
    rs: List[float] = []
    net_rs: List[float] = []
    mfe_values: List[float] = []
    mae_values: List[float] = []
    stopped_without_progress = 0
    tight_suspects = 0

    for row in resolved:
        status = str(row.get("status") or "").lower()
        planned_rr = max(0.0, _safe_float(row.get("risk_reward"), 0.0))
        rs.append(planned_rr if status == "tp_hit" else -1.0)

        result = row.get("result") or {}
        if isinstance(result, dict):
            mfe_values.append(max(0.0, _safe_float(result.get("mfe_r"), 0.0)))
            mae_values.append(max(0.0, _safe_float(result.get("mae_r"), 0.0)))
            if bool(result.get("economics_cost_components_complete", False)):
                net_value = result.get("modeled_net_r")
                if net_value is not None:
                    net_rs.append(_safe_float(net_value, 0.0))
            elif result.get("net_pnl_pct") is not None:
                # Future actual-fill integrations are stronger evidence. Convert
                # only when Entry/SL geometry is present in the signal row.
                entry = _safe_float(row.get("entry_price"), 0.0)
                stop = _safe_float(row.get("stop_loss"), 0.0)
                actual_pct = _safe_float(result.get("net_pnl_pct"), 0.0)
                risk_pct = abs(entry - stop) / entry * 100.0 if entry > 0 else 0.0
                if risk_pct > 0:
                    net_rs.append(actual_pct / risk_pct)
            forensic = result.get("execution_forensics") or {}
            if isinstance(forensic, dict):
                if str(forensic.get("diagnosis") or "") == "STOPPED_WITHOUT_PROGRESS":
                    stopped_without_progress += 1
                if _as_bool(forensic.get("stop_was_possibly_tight", False)):
                    tight_suspects += 1

    def _pf(values: List[float]):
        gains = sum(max(0.0, value) for value in values)
        losses = abs(sum(min(0.0, value) for value in values))
        if losses > 0:
            return gains / losses
        return None if gains == 0 else 99.0

    expectancy = (sum(rs) / n) if n else None
    pf = _pf(rs)
    net_expectancy = (sum(net_rs) / len(net_rs)) if net_rs else None
    net_pf = _pf(net_rs)

    return {
        "resolved": n,
        "tp": tp,
        "sl": sl,
        "win_rate_pct": round(tp / n * 100.0, 2) if n else None,
        "expectancy_r": round(expectancy, 4) if expectancy is not None else None,
        "profit_factor": round(pf, 3) if pf is not None else None,
        "model_complete_net_rows": len(net_rs),
        "model_complete_net_coverage_pct": round(len(net_rs) / n * 100.0, 2) if n else 0.0,
        "model_complete_net_expectancy_r": round(net_expectancy, 4) if net_expectancy is not None else None,
        "model_complete_net_profit_factor": round(net_pf, 3) if net_pf is not None else None,
        "avg_mfe_r": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else None,
        "avg_mae_r": round(sum(mae_values) / len(mae_values), 4) if mae_values else None,
        "stop_without_progress_ratio": round(stopped_without_progress / sl, 4) if sl else 0.0,
        "stop_tight_suspect_ratio": round(tight_suspects / sl, 4) if sl else 0.0,
    }


def derive_execution_profile(
    metrics: Dict[str, Any],
    *,
    symbol: str = "*",
    timeframe: str = "*",
    market_regime: str = "*",
) -> Dict[str, Any]:
    """Pure governance logic; safe to unit test without Supabase."""
    profile = default_execution_profile(symbol, timeframe, market_regime)
    metrics = metrics or {}
    evidence = dict(profile["evidence"])
    evidence.update({key: metrics.get(key) for key in evidence if key in metrics})

    n = _safe_int(metrics.get("resolved"), 0)
    expectancy = metrics.get("expectancy_r")
    pf = metrics.get("profit_factor")
    expectancy_value = _safe_float(expectancy, 0.0) if expectancy is not None else None
    pf_value = _safe_float(pf, 0.0) if pf is not None else None
    stop_direct = _safe_float(metrics.get("stop_without_progress_ratio"), 0.0)
    tight_ratio = _safe_float(metrics.get("stop_tight_suspect_ratio"), 0.0)
    avg_mae = metrics.get("avg_mae_r")
    avg_mae_value = _safe_float(avg_mae, 99.0) if avg_mae is not None else 99.0
    net_coverage = _safe_float(metrics.get("model_complete_net_coverage_pct"), 0.0)
    net_expectancy = metrics.get("model_complete_net_expectancy_r")
    net_pf = metrics.get("model_complete_net_profit_factor")
    net_expectancy_value = _safe_float(net_expectancy, 0.0) if net_expectancy is not None else None
    net_pf_value = _safe_float(net_pf, 0.0) if net_pf is not None else None

    config = dict(profile["config"])
    config["q2_weights"] = dict(DEFAULT_Q2_WEIGHTS)

    if n < MIN_PROFILE_SAMPLE:
        evidence["reason"] = f"INSUFFICIENT_EVIDENCE_{n}_OF_{MIN_PROFILE_SAMPLE}"
        profile["evidence"] = evidence
        return profile

    # ------------------------------------------------------------------
    # PROTECT: robust negative evidence can reduce risk automatically.
    # ------------------------------------------------------------------
    if expectancy_value is not None and (
        expectancy_value <= -0.10
        or (pf_value is not None and pf_value < 0.90)
    ):
        profile["state"] = "PROTECT"
        profile["production_authority"] = True
        evidence["reason"] = "ROBUST_NEGATIVE_EXECUTION_EVIDENCE"
        config["leverage_cap_factor"] = 0.85 if expectancy_value <= -0.25 else 0.90
        config["leverage_target_factor"] = 1.0
        config["allow_leverage_growth"] = False
        config["leverage_policy_mode"] = "STATIC_MINIMUM"
        config["target_loss_budget_pct_margin"] = 5.0
        config["minimum_safety_delta"] = 0.0  # 7E.3 already handles Safety protection.

        if stop_direct >= 0.40:
            # Reachable but not defended: demand stronger Q1 structural evidence.
            config["entry_min_defensibility"] = 62.0
        elif stop_direct >= 0.25:
            config["entry_min_defensibility"] = 57.0

        if tight_ratio >= 0.25:
            # Favor SL quality among structural candidates; do not widen a stop
            # by a percentage and do not invent levels.
            config["q2_weights"] = _normalized_weights({"sl": 0.50, "tp": 0.25, "rr": 0.25})
            config["q2_min_pair_improvement"] = 2.5
        elif stop_direct >= 0.40:
            config["q2_weights"] = _normalized_weights({"sl": 0.38, "tp": 0.30, "rr": 0.32})

        profile["config"] = config
        profile["evidence"] = evidence
        return profile

    # ------------------------------------------------------------------
    # ACTIVE: only robust positive edge may optimize upward.
    # ------------------------------------------------------------------
    net_profile_ready = bool(
        net_coverage >= 95.0
        and net_expectancy_value is not None
        and net_expectancy_value >= 0.05
        and net_pf_value is not None
        and net_pf_value >= 1.10
    )
    gross_profile_ready = bool(
        expectancy_value is not None
        and pf_value is not None
        and expectancy_value >= 0.10
        and pf_value >= 1.15
    )
    if gross_profile_ready and (net_profile_ready or net_coverage <= 0.0):
        profile["state"] = "ACTIVE"
        profile["production_authority"] = True
        evidence["reason"] = "ROBUST_POSITIVE_EXECUTION_EVIDENCE"

        if tight_ratio >= 0.25:
            config["q2_weights"] = _normalized_weights({"sl": 0.48, "tp": 0.27, "rr": 0.25})
            config["q2_min_pair_improvement"] = 2.5

        # Growth needs stronger evidence than configuration selection.
        candidate_growth_ready = bool(
            n >= MIN_GROWTH_SAMPLE
            and avg_mae_value <= 0.80
            and (
                (
                    net_coverage >= 95.0
                    and net_expectancy_value is not None and net_expectancy_value >= 0.15
                    and net_pf_value is not None and net_pf_value >= 1.25
                )
                or (
                    net_coverage <= 0.0
                    and expectancy_value is not None and expectancy_value >= 0.15
                    and pf_value is not None and pf_value >= 1.20
                )
            )
        )
        if candidate_growth_ready:
            config["allow_leverage_growth"] = True
            config["leverage_target_factor"] = 1.10  # compatibility diagnostic
            config["leverage_policy_mode"] = "RISK_BUDGET_V3"
            config["target_loss_budget_pct_margin"] = 5.0

        strong_candidate_ready = bool(
            n >= MIN_STRONG_GROWTH_SAMPLE
            and avg_mae_value <= 0.65
            and (
                (
                    net_coverage >= 95.0
                    and net_expectancy_value is not None and net_expectancy_value >= 0.25
                    and net_pf_value is not None and net_pf_value >= 1.40
                )
                or (
                    net_coverage <= 0.0
                    and expectancy_value is not None and expectancy_value >= 0.25
                    and pf_value is not None and pf_value >= 1.40
                )
            )
        )
        if strong_candidate_ready:
            config["leverage_target_factor"] = MAX_LEVERAGE_TARGET_FACTOR
            config["target_loss_budget_pct_margin"] = 6.0

        profile["config"] = config
        profile["evidence"] = evidence
        return profile

    evidence["reason"] = "ENOUGH_SAMPLE_BUT_NO_ACTIONABLE_EDGE"
    profile["evidence"] = evidence
    return profile


def _profile_specificity(row: Dict[str, Any], symbol: str, timeframe: str, regime: str) -> int:
    score = 0
    for key, expected in (("symbol", symbol), ("timeframe", timeframe), ("market_regime", regime)):
        value = str(row.get(key) or "*")
        if value == expected:
            score += 2
        elif value == "*":
            score += 0
        else:
            return -999
    return score


def get_execution_profile(
    symbol: str,
    timeframe: str,
    market_regime: str = "*",
    system_type: str = "futures",
    db=None,
) -> Dict[str, Any]:
    """Read the most specific persisted profile; fail-open to OBSERVE."""
    if str(system_type or "").lower() != "futures":
        return default_execution_profile(symbol, timeframe, market_regime)

    key = ("futures", str(symbol), str(timeframe), str(market_regime or "*"))
    now = time.monotonic()
    with _cache_lock:
        cached = _profile_cache.get(key)
        if cached and now - cached[0] < _profile_cache_ttl:
            return json.loads(json.dumps(cached[1]))

    if db is None:
        try:
            from supabase_client import supabase_db as db
        except Exception:
            db = None

    fallback = default_execution_profile(symbol, timeframe, market_regime)
    if db is None or not getattr(db, "enabled", False):
        return fallback

    try:
        response = (
            db.client.table("adaptive_execution_profiles")
            .select("*")
            .eq("system_type", "futures")
            .in_("symbol", [str(symbol), "*"])
            .in_("timeframe", [str(timeframe), "*"])
            .in_("market_regime", [str(market_regime or "*"), "*"])
            .limit(20)
            .execute()
        )
        rows = response.data or []
        rows = sorted(rows, key=lambda row: _profile_specificity(row, str(symbol), str(timeframe), str(market_regime or "*")), reverse=True)
        if rows and _profile_specificity(rows[0], str(symbol), str(timeframe), str(market_regime or "*")) >= 0:
            row = rows[0]
            profile = {
                "version": str(row.get("version") or EXECUTION_PROFILE_VERSION),
                "system_type": "futures",
                "symbol": row.get("symbol") or "*",
                "timeframe": row.get("timeframe") or "*",
                "market_regime": row.get("market_regime") or "*",
                "state": str(row.get("state") or "OBSERVE"),
                "production_authority": str(row.get("state") or "OBSERVE") in {"PROTECT", "ACTIVE"},
                "config": row.get("config") or {},
                "evidence": row.get("evidence") or {},
                "updated_at": row.get("updated_at"),
            }
        else:
            profile = fallback
    except Exception:
        profile = fallback

    # Commit 8: ACTIVE quality profiles obtain authority only from the persisted
    # evidence gate. PROTECT remains allowed because it can only reduce risk.
    governance = _governance_status(db)
    profile_evidence = dict(profile.get('evidence') or {})
    profile_net_coverage = _safe_float(
        profile_evidence.get('model_complete_net_coverage_pct'), 0.0
    )
    profile_net_exp = profile_evidence.get('model_complete_net_expectancy_r')
    profile_net_ready = bool(
        profile_net_coverage >= 95.0
        and profile_net_exp is not None
        and _safe_float(profile_net_exp, -99.0) >= 0.05
    )

    if str(profile.get('state') or '').upper() == 'ACTIVE':
        profile['production_authority'] = bool(
            governance.get('quality_optimization_allowed', False)
            and profile_net_ready
        )
        profile_evidence['promotion_governance'] = {
            'quality_optimization_allowed': bool(governance.get('quality_optimization_allowed', False)),
            'risk_growth_allowed': bool(governance.get('risk_growth_allowed', False)),
            'profile_net_evidence_ready': profile_net_ready,
            'block_reasons': list(governance.get('block_reasons') or []),
            'risk_block_reasons': list(governance.get('risk_block_reasons') or []),
        }
        profile['evidence'] = profile_evidence

    # Commit 9: even when the GLOBAL risk gate opens, the selected profile must
    # itself have complete positive net evidence. This prevents a globally good
    # cohort from granting leverage growth to an unvalidated symbol/timeframe.
    if not (_risk_growth_enabled(db) and profile_net_ready):
        config = dict(profile.get('config') or {})
        config['allow_leverage_growth'] = False
        config['leverage_target_factor'] = min(1.0, _safe_float(config.get('leverage_target_factor'), 1.0))
        config['leverage_policy_mode'] = 'STATIC_MINIMUM'
        config['target_loss_budget_pct_margin'] = 5.0
        profile['config'] = config

    with _cache_lock:
        _profile_cache[key] = (now, profile)
    return json.loads(json.dumps(profile))


def invalidate_profile_cache() -> None:
    with _cache_lock:
        _profile_cache.clear()


def _upsert_profile(db, profile: Dict[str, Any]) -> bool:
    if not getattr(db, "enabled", False):
        return False
    payload = {
        "system_type": "futures",
        "symbol": profile.get("symbol") or "*",
        "timeframe": profile.get("timeframe") or "*",
        "market_regime": profile.get("market_regime") or "*",
        "state": profile.get("state") or "OBSERVE",
        "config": profile.get("config") or {},
        "evidence": profile.get("evidence") or {},
        "version": EXECUTION_PROFILE_VERSION,
        "updated_at": _now_iso(),
    }
    try:
        existing_response = (
            db.client.table("adaptive_execution_profiles")
            .select("*")
            .eq("system_type", payload["system_type"])
            .eq("symbol", payload["symbol"])
            .eq("timeframe", payload["timeframe"])
            .eq("market_regime", payload["market_regime"])
            .limit(1)
            .execute()
        )
        existing = existing_response.data[0] if existing_response.data else None
        changed = bool(
            existing is None
            or str(existing.get("state") or "OBSERVE") != payload["state"]
            or (existing.get("config") or {}) != payload["config"]
        )

        if existing is not None and changed:
            try:
                db.client.table("adaptive_execution_profile_history").insert({
                    "system_type": existing.get("system_type") or "futures",
                    "symbol": existing.get("symbol") or "*",
                    "timeframe": existing.get("timeframe") or "*",
                    "market_regime": existing.get("market_regime") or "*",
                    "state": existing.get("state") or "OBSERVE",
                    "config": existing.get("config") or {},
                    "evidence": existing.get("evidence") or {},
                    "version": existing.get("version") or EXECUTION_PROFILE_VERSION,
                }).execute()
            except Exception:
                pass

        db.client.table("adaptive_execution_profiles").upsert(
            payload,
            on_conflict="system_type,symbol,timeframe,market_regime",
        ).execute()

        if changed:
            component = f"EXECUTION_PROFILE:{payload['symbol']}:{payload['timeframe']}:{payload['market_regime']}"
            _record_event(
                db,
                "EXECUTION_PROFILE",
                component,
                str(existing.get("state") or "NONE") if existing else "NONE",
                payload["state"],
                str((payload.get("evidence") or {}).get("reason") or "PROFILE_REFRESH"),
                {
                    "previous_config": (existing.get("config") or {}) if existing else {},
                    "new_config": payload["config"],
                    "evidence": payload["evidence"],
                },
            )
        invalidate_profile_cache()
        return True
    except Exception:
        return False


def _record_event(db, event_type: str, component: str, old_state: str, new_state: str, reason: str, evidence: Dict[str, Any]) -> None:
    if not getattr(db, "enabled", False):
        return
    try:
        db.client.table("adaptive_autopilot_events").insert({
            "event_type": str(event_type),
            "component": str(component),
            "old_state": str(old_state or ""),
            "new_state": str(new_state or ""),
            "reason": str(reason or "")[:500],
            "evidence": evidence or {},
            "version": AUTOPILOT_VERSION,
        }).execute()
    except Exception:
        pass


def _fetch_execution_rows(db, limit: int = 400) -> List[Dict[str, Any]]:
    if not getattr(db, "enabled", False):
        return []
    try:
        signals_response = (
            db.client.table("signals")
            .select("id,symbol,timeframe,system_type,status,context,risk_reward,entry_price,stop_loss,created_at")
            .eq("system_type", "futures")
            .in_("status", ["tp_hit", "sl_hit", "expired"])
            .order("created_at", desc=True)
            .limit(max(50, min(int(limit), 800)))
            .execute()
        )
        signals = [row for row in (signals_response.data or []) if _verified_futures_signal(row)]
        if not signals:
            return []
        by_id = {str(row.get("id")): row for row in signals if row.get("id")}
        ids = list(by_id)
        for start in range(0, len(ids), 100):
            batch = ids[start:start + 100]
            response = (
                db.client.table("signal_results")
                .select("signal_id,status,pnl_pct,mfe_r,mae_r,execution_forensics,economics_status,economics_cost_components_complete,modeled_net_r,net_pnl_pct,created_at")
                .in_("signal_id", batch)
                .execute()
            )
            for result in response.data or []:
                signal = by_id.get(str(result.get("signal_id")))
                if signal is not None:
                    signal["result"] = result
        return [row for row in signals if isinstance(row.get("result"), dict)]
    except Exception:
        return []


def _group_execution_rows(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or "*")
        timeframe = str(row.get("timeframe") or "*")
        groups[(symbol, timeframe)].append(row)
        groups[("*", timeframe)].append(row)
        groups[(symbol, "*")].append(row)
        groups[("*", "*")].append(row)
    return groups


def _research_fingerprint(result: Dict[str, Any]) -> str:
    core = {
        "version": result.get("version"),
        "symbol": result.get("symbol"),
        "timeframe": result.get("timeframe"),
        "data_start": result.get("data_start"),
        "data_end": result.get("data_end"),
        "observations": result.get("observations"),
        "resolved": result.get("resolved"),
        "split": result.get("split"),
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]


def persist_research_run(db, result: Dict[str, Any], user_id: Optional[str] = None) -> bool:
    if not getattr(db, "enabled", False) or not isinstance(result, dict):
        return False
    fingerprint = _research_fingerprint(result)
    payload = {
        "user_id": user_id,
        "symbol": str(result.get("symbol") or ""),
        "timeframe": str(result.get("timeframe") or ""),
        "cohort": "HISTORICAL_RESEARCH",
        "engine_version": str(result.get("version") or "UNKNOWN"),
        "result": result,
        "data_fingerprint": fingerprint,
    }
    try:
        # Same candle window must not count twice merely because the endpoint was
        # pressed twice.
        existing = (
            db.client.table("strategy_research_runs")
            .select("id")
            .eq("data_fingerprint", fingerprint)
            .limit(1)
            .execute()
        )
        if existing.data:
            return True
        db.client.table("strategy_research_runs").insert(payload).execute()
        return True
    except Exception:
        return False


def _research_evidence(db, limit: int = 120) -> Dict[str, Dict[str, Any]]:
    evidence: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "unique_runs": 0,
        "validation_n": 0,
        "positive_runs": 0,
        "expectancy_weighted_sum": 0.0,
        "pf_values": [],
    })
    if not getattr(db, "enabled", False):
        return {}
    try:
        response = (
            db.client.table("strategy_research_runs")
            .select("result,data_fingerprint,created_at")
            .eq("cohort", "HISTORICAL_RESEARCH")
            .order("created_at", desc=True)
            .limit(max(20, min(int(limit), 300)))
            .execute()
        )
    except Exception:
        return {}

    seen = set()
    for row in response.data or []:
        fingerprint = str(row.get("data_fingerprint") or "")
        if fingerprint and fingerprint in seen:
            continue
        if fingerprint:
            seen.add(fingerprint)
        result = row.get("result") or {}
        if not isinstance(result, dict):
            continue
        strategies = result.get("strategies") or {}
        split = result.get("split") or {}
        validation = split.get("validation_30") or {}
        if not isinstance(strategies, dict) or not isinstance(validation, dict):
            continue
        val_n = _safe_int(validation.get("n"), 0)
        val_exp = _safe_float(validation.get("expectancy_r"), 0.0)
        val_pf = validation.get("profit_factor")
        val_pf_num = _safe_float(val_pf, 0.0) if val_pf is not None else None
        for research_name in strategies:
            key = _RESEARCH_TO_REGISTRY.get(str(research_name))
            if not key:
                continue
            item = evidence[key]
            item["unique_runs"] += 1
            item["validation_n"] += val_n
            item["expectancy_weighted_sum"] += val_exp * val_n
            if val_pf_num is not None:
                item["pf_values"].append(val_pf_num)
            if val_n >= MIN_RESEARCH_VALIDATION_N and val_exp >= MIN_RESEARCH_EXPECTANCY_R and (val_pf_num is None or val_pf_num >= MIN_RESEARCH_PF):
                item["positive_runs"] += 1

    output: Dict[str, Dict[str, Any]] = {}
    for key, item in evidence.items():
        n = item["validation_n"]
        output[key] = {
            "unique_runs": item["unique_runs"],
            "validation_n": n,
            "validation_expectancy_r": round(item["expectancy_weighted_sum"] / n, 4) if n else None,
            "validation_pf_mean": round(sum(item["pf_values"]) / len(item["pf_values"]), 3) if item["pf_values"] else None,
            "positive_runs": item["positive_runs"],
        }
    return output


def _edge_family_evidence(db, limit_runs: int = 12) -> Dict[str, Dict[str, Any]]:
    """Return only edge hypotheses that can be enforced exactly at runtime.

    Commit 7 may discover useful combinations containing arbitrary context. An
    arbitrary text hypothesis must never become production code implicitly. For
    Commit 8 we promote only predicates that map losslessly to an existing lab
    strategy observation plus optional action/timeframe/regime constraints.

    This is especially important for Q7 RSI: FAST|ALIGNED evidence must not
    accidentally authorize BALANCED|CONFLICT merely because both observations
    share the broad ``Q7_RSI_PROFILE_V1`` strategy name.
    """
    if not getattr(db, "enabled", False):
        return {}
    try:
        response = (
            db.client.table("edge_discovery_runs")
            .select("summary,created_at")
            .order("created_at", desc=True)
            .limit(max(1, min(int(limit_runs), 30)))
            .execute()
        )
    except Exception:
        return {}

    state_to_trendline = {
        "TRENDLINE_SUPPORT_BOUNCE": "TRENDLINE_SUPPORT_REACTION_V1",
        "TRENDLINE_RESISTANCE_REJECTION": "TRENDLINE_RESISTANCE_REACTION_V1",
        "TRENDLINE_BREAK_RETEST_LONG": "TRENDLINE_BREAK_RETEST_LONG_V1",
        "TRENDLINE_BREAK_RETEST_SHORT": "TRENDLINE_BREAK_RETEST_SHORT_V1",
        "FALSE_BREAK_RECLAIM_LONG": "TRENDLINE_SUPPORT_REACTION_V1",
        "FALSE_BREAK_RECLAIM_SHORT": "TRENDLINE_RESISTANCE_REACTION_V1",
    }

    def parse_enforceable_predicate(factors):
        strategy_key = None
        rule: Dict[str, Any] = {}
        for raw in factors or []:
            factor = str(raw or "")
            if factor.startswith("RSI_PROFILE:"):
                if strategy_key and strategy_key != "Q7_RSI_PROFILE_V1":
                    return None
                strategy_key = "Q7_RSI_PROFILE_V1"
                value = factor.split(":", 1)[1].upper()
                parts = value.split("|", 1)
                if len(parts) != 2 or not all(parts):
                    return None
                rule["profile"] = parts[0]
                rule["alignment_with_system"] = parts[1]
            elif factor.startswith("VWAP:"):
                if strategy_key and strategy_key != "Q7_ROLLING_VWAP_REVERSION_V1":
                    return None
                strategy_key = "Q7_ROLLING_VWAP_REVERSION_V1"
                state = factor.split(":", 1)[1].upper()
                if not state:
                    return None
                rule["state"] = state
                if state.endswith("_LONG"):
                    rule["direction"] = "LONG"
                elif state.endswith("_SHORT"):
                    rule["direction"] = "SHORT"
            elif factor.startswith("RETEST:"):
                if strategy_key and strategy_key != "Q7_BREAKOUT_RETEST_V1":
                    return None
                strategy_key = "Q7_BREAKOUT_RETEST_V1"
                state = factor.split(":", 1)[1].upper()
                if not state:
                    return None
                rule["state"] = state
                if "LONG" in state:
                    rule["direction"] = "LONG"
                elif "SHORT" in state:
                    rule["direction"] = "SHORT"
            elif factor.startswith("TRENDLINE_STATE:"):
                state = factor.split(":", 1)[1].upper()
                key = state_to_trendline.get(state)
                if not key or (strategy_key and strategy_key != key):
                    return None
                strategy_key = key
                rule["state"] = state
                if "LONG" in state or state == "TRENDLINE_SUPPORT_BOUNCE":
                    rule["direction"] = "LONG"
                elif "SHORT" in state or state == "TRENDLINE_RESISTANCE_REJECTION":
                    rule["direction"] = "SHORT"
            elif factor.startswith("ACTION:"):
                value = factor.split(":", 1)[1].upper()
                if value not in {"LONG", "SHORT"}:
                    return None
                rule["action"] = value
            elif factor.startswith("TF:"):
                value = factor.split(":", 1)[1].upper()
                if not value:
                    return None
                rule["timeframe"] = value
            elif factor.startswith("REGIME:"):
                value = factor.split(":", 1)[1].upper()
                if not value:
                    return None
                rule["market_regime"] = value
            else:
                # Entry/TP/Safety/Cautious/microstructure/etc. are useful for
                # research, but Commit 8 has no exact runtime predicate for them.
                # They remain research-only rather than being approximated.
                return None

        if not strategy_key or not rule:
            return None
        signature = json.dumps(rule, sort_keys=True, separators=(",", ":"))
        return strategy_key, rule, signature

    candidates: Dict[Tuple[str, str], Dict[str, Any]] = {}
    seen_snapshot = set()
    for run_idx, row in enumerate(response.data or []):
        summary = row.get("summary") or {}
        futures = summary.get("futures_shadow") or {} if isinstance(summary, dict) else {}
        hypotheses = list(futures.get("priority") or [])
        for hyp in hypotheses:
            if not isinstance(hyp, dict) or str(hyp.get("state") or "") != "RESEARCH_PRIORITY":
                continue
            parsed = parse_enforceable_predicate(hyp.get("factors") or [])
            if not parsed:
                continue
            key, observation_filter, signature = parsed
            validation = hyp.get("validation") or {}
            total = hyp.get("total") or {}
            vn = _safe_int(validation.get("resolved"), 0)
            vexp = validation.get("expectancy_r")
            vpf = validation.get("profit_factor")
            total_n = _safe_int(total.get("resolved"), 0)
            total_exp = total.get("expectancy_r")
            total_pf = total.get("profit_factor")
            positive = bool(
                total_n >= 25
                and vn >= 10
                and vexp is not None and _safe_float(vexp) >= 0.10
                and total_exp is not None and _safe_float(total_exp) >= 0.05
                and (vpf is None or _safe_float(vpf) >= 1.10)
                and (total_pf is None or _safe_float(total_pf) >= 1.10)
            )
            if not positive:
                continue

            candidate_key = (key, signature)
            item = candidates.setdefault(candidate_key, {
                "positive_snapshots": 0,
                "latest_validation_n": 0,
                "latest_validation_expectancy_r": None,
                "latest_validation_profit_factor": None,
                "latest_total_n": 0,
                "latest_total_expectancy_r": None,
                "latest_total_profit_factor": None,
                "latest_label": None,
                "latest_at": None,
                "observation_filter": observation_filter,
                "filter_signature": signature,
            })
            marker = (run_idx, key, signature)
            if marker not in seen_snapshot:
                seen_snapshot.add(marker)
                item["positive_snapshots"] += 1
            if item["latest_at"] is None:
                item.update({
                    "latest_validation_n": vn,
                    "latest_validation_expectancy_r": _safe_float(vexp),
                    "latest_validation_profit_factor": _safe_float(vpf, None) if vpf is not None else None,
                    "latest_total_n": total_n,
                    "latest_total_expectancy_r": _safe_float(total_exp, None),
                    "latest_total_profit_factor": _safe_float(total_pf, None) if total_pf is not None else None,
                    "latest_label": hyp.get("label"),
                    "latest_at": row.get("created_at"),
                })

    # Only one predicate can own the broad registry key at a time. Choose the
    # predicate with the strongest repeated time-separated evidence; ties use
    # validation sample and expectancy. Once CHALLENGER/CANARY, transition code
    # pins the predicate in config so later cycles cannot silently swap subtype.
    out: Dict[str, Dict[str, Any]] = {}
    for (key, _signature), item in candidates.items():
        score = (
            _safe_int(item.get("positive_snapshots"), 0),
            _safe_int(item.get("latest_validation_n"), 0),
            _safe_float(item.get("latest_validation_expectancy_r"), -999.0),
        )
        current = out.get(key)
        if current is None or score > current.get("_score", (-1, -1, -999.0)):
            out[key] = {**item, "_score": score}
    for item in out.values():
        item.pop("_score", None)
    return out

def _bounded_q7_live_evidence(db, limit: int = 600) -> Dict[str, Dict[str, Any]]:
    """Compact live Q7 evidence used only for governance, never official KPIs."""
    if not getattr(db, "enabled", False):
        return {}
    try:
        response = (
            db.client.table("signals")
            .select("id,symbol,timeframe,system_type,status,action_normalized,risk_reward,context,created_at")
            .eq("system_type", "futures")
            .in_("status", ["tp_hit", "sl_hit", "expired"])
            .order("created_at", desc=True)
            .limit(max(100, min(int(limit), 900)))
            .execute()
        )
    except Exception:
        return {}

    agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"n": 0, "tp": 0, "sl": 0, "r_sum": 0.0, "gross_win": 0.0, "gross_loss": 0.0})
    for signal in response.data or []:
        context = signal.get("context") or {}
        learning = context.get("learning") or {} if isinstance(context, dict) else {}
        if not isinstance(learning, dict):
            continue
        if learning.get("cohort") != "FUTURES_PERPETUAL_REAL_CLOSED_V1":
            continue
        q7 = learning.get("q7_strategy_lab_shadow") or {}
        trendline = learning.get("trendline_strategy_lab_shadow") or {}
        strategy_sets = []
        if isinstance(q7, dict) and q7.get("shadow_only", False):
            q7_strategies = q7.get("strategies") or {}
            if isinstance(q7_strategies, dict):
                strategy_sets.append(q7_strategies)
        if isinstance(trendline, dict) and trendline.get("shadow_only", False):
            tl_strategies = trendline.get("strategies") or {}
            if isinstance(tl_strategies, dict):
                strategy_sets.append(tl_strategies)
        if not strategy_sets:
            continue
        status = str(signal.get("status") or "").lower()
        if status not in {"tp_hit", "sl_hit"}:
            continue
        final_action = str(signal.get("action_normalized") or "")
        r_value = max(0.0, _safe_float(signal.get("risk_reward"), 0.0)) if status == "tp_hit" else -1.0
        for strategies in strategy_sets:
            for strategy in strategies.values():
                if not isinstance(strategy, dict):
                    continue
                key = str(strategy.get("name") or "")
                if key not in {
                    "Q7_RSI_PROFILE_V1",
                    "Q7_ROLLING_VWAP_REVERSION_V1",
                    "Q7_BREAKOUT_RETEST_V1",
                    "TRENDLINE_SUPPORT_REACTION_V1",
                    "TRENDLINE_RESISTANCE_REACTION_V1",
                    "TRENDLINE_BREAK_RETEST_LONG_V1",
                    "TRENDLINE_BREAK_RETEST_SHORT_V1",
                    "TRENDLINE_FIB_CONFLUENCE_V1",
                }:
                    continue
                direction = str(strategy.get("direction") or "NEUTRAL").upper()
                if direction not in {"LONG", "SHORT"} or direction != final_action:
                    continue
                item = agg[key]
                item["n"] += 1
                item["tp"] += int(status == "tp_hit")
                item["sl"] += int(status == "sl_hit")
                item["r_sum"] += r_value
                item["gross_win"] += max(0.0, r_value)
                item["gross_loss"] += abs(min(0.0, r_value))

    out: Dict[str, Dict[str, Any]] = {}
    for key, item in agg.items():
        n = item["n"]
        out[key] = {
            "n": n,
            "tp": item["tp"],
            "sl": item["sl"],
            "wr_pct": round(item["tp"] / n * 100.0, 2) if n else None,
            "expectancy_r": round(item["r_sum"] / n, 4) if n else None,
            "profit_factor": round(item["gross_win"] / item["gross_loss"], 3) if item["gross_loss"] > 0 else (None if item["gross_win"] == 0 else 99.0),
        }
    return out


def _transition_strategy_registry(
    db,
    research: Dict[str, Dict[str, Any]],
    live: Dict[str, Dict[str, Any]],
    governance: Optional[Dict[str, Any]] = None,
    edge: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    if not getattr(db, "enabled", False):
        return changes
    governance = governance or _governance_status(db)
    strategy_veto_allowed = bool(
        governance.get("strategy_veto_authority_allowed", False)
    )
    edge = edge or {}
    try:
        response = db.client.table("strategy_registry").select("*").limit(200).execute()
        rows = response.data or []
    except Exception:
        return changes

    for row in rows:
        key = str(row.get("strategy_key") or "")
        current = str(row.get("state") or "SHADOW").upper()
        if current == "DISABLED":
            continue
        r = research.get(key) or {}
        l = live.get(key) or {}
        val_n = _safe_int(r.get("validation_n"), 0)
        val_exp = r.get("validation_expectancy_r")
        val_pf = r.get("validation_pf_mean")
        positive_runs = _safe_int(r.get("positive_runs"), 0)
        live_n = _safe_int(l.get("n"), 0)
        live_exp = l.get("expectancy_r")
        live_pf = l.get("profit_factor")
        e = edge.get(key) or {}
        edge_positive_snapshots = _safe_int(e.get("positive_snapshots"), 0)
        edge_val_n = _safe_int(e.get("latest_validation_n"), 0)
        edge_val_exp = e.get("latest_validation_expectancy_r")
        edge_val_pf = e.get("latest_validation_profit_factor")
        edge_total_n = _safe_int(e.get("latest_total_n"), 0)
        edge_total_exp = e.get("latest_total_expectancy_r")
        edge_filter = e.get("observation_filter") or {}
        edge_signature = str(e.get("filter_signature") or "")
        existing_config = row.get("config") or {}
        if not isinstance(existing_config, dict):
            existing_config = {}
        existing_filter = existing_config.get("observation_filter") or {}
        if not isinstance(existing_filter, dict):
            existing_filter = {}
        existing_signature = (
            json.dumps(existing_filter, sort_keys=True, separators=(",", ":"))
            if existing_filter else ""
        )
        # Once a strategy reaches CANARY, its validated subtype predicate is
        # pinned. A later run cannot silently swap FAST|ALIGNED for another RSI
        # subtype under the same broad registry key.
        predicate_compatible = bool(
            edge_filter
            and (not existing_signature or existing_signature == edge_signature)
        )
        edge_positive = bool(
            predicate_compatible
            and edge_positive_snapshots >= 1
            and edge_total_n >= 25
            and edge_val_n >= 10
            and edge_val_exp is not None and _safe_float(edge_val_exp) >= 0.10
            and edge_total_exp is not None and _safe_float(edge_total_exp) >= 0.05
            and (edge_val_pf is None or _safe_float(edge_val_pf) >= 1.10)
        )

        historical_research_positive = bool(
            val_n >= MIN_RESEARCH_VALIDATION_N
            and val_exp is not None and _safe_float(val_exp) >= MIN_RESEARCH_EXPECTANCY_R
            and (val_pf is None or _safe_float(val_pf) >= MIN_RESEARCH_PF)
        )
        research_positive = bool(historical_research_positive or edge_positive)
        # Historical replay can nominate a broad family as CHALLENGER, but only
        # an exact Commit-7 predicate with repeated time-separated evidence can
        # reach CANARY/ACTIVE. This prevents broad-family overpromotion.
        repeated_edge_positive = bool(edge_positive and edge_positive_snapshots >= 2)
        live_positive = bool(
            live_n >= MIN_LIVE_STRATEGY_N
            and live_exp is not None and _safe_float(live_exp) >= MIN_LIVE_EXPECTANCY_R
            and live_pf is not None and _safe_float(live_pf) >= MIN_LIVE_PF
        )
        live_degraded = bool(
            live_n >= MIN_LIVE_STRATEGY_N
            and live_exp is not None and _safe_float(live_exp) <= -0.15
        )

        new_state = current
        reason = None
        if current == "SHADOW" and research_positive:
            new_state = "CHALLENGER"
            reason = (
                "HISTORICAL_VALIDATION_POSITIVE"
                if historical_research_positive
                else "EDGE_VALIDATION_POSITIVE_RESEARCH_ONLY"
            )
        elif (
            current == "CHALLENGER"
            and repeated_edge_positive
            and edge_total_n >= 25
            and edge_val_n >= 10
        ):
            new_state = "CANARY"
            reason = "REPEATED_ENFORCEABLE_EDGE_PREDICATE_POSITIVE"
        elif current == "CANARY" and edge_positive and live_positive:
            if strategy_veto_allowed:
                new_state = "ACTIVE"
                reason = "ENFORCEABLE_EDGE_AND_LIVE_EVIDENCE_CONFIRMED_VETO_ONLY"
            else:
                new_state = "CANARY"
                reason = "GLOBAL_COVERAGE_GATE_BLOCKS_ACTIVE_VETO"
        elif current == "ACTIVE" and live_degraded:
            new_state = "DEGRADED"
            reason = "LIVE_EDGE_DEGRADED"
        elif current == "ACTIVE" and not strategy_veto_allowed:
            # Global evidence became incomplete/stale: fail closed immediately.
            new_state = "CANARY"
            reason = "GLOBAL_GOVERNANCE_GATE_CLOSED"
        elif current == "DEGRADED" and edge_positive and live_positive:
            new_state = "CANARY"
            reason = "RECOVERY_REQUIRES_CANARY_REVALIDATION"

        evidence = {
            "research": r,
            "edge_discovery": e,
            "live_shadow": l,
            "global_governance": {
                "strategy_veto_authority_allowed": strategy_veto_allowed,
                "risk_growth_allowed": bool(governance.get("risk_growth_allowed", False)),
                "block_reasons": list(governance.get("block_reasons") or []),
                "risk_block_reasons": list(governance.get("risk_block_reasons") or []),
            },
            "governance_version": STRATEGY_GOVERNANCE_VERSION,
            "reason": reason or "NO_TRANSITION",
        }
        if new_state != current:
            try:
                next_config = dict(existing_config)
                # Pin the exact runtime predicate when a strategy advances into
                # CANARY. ACTIVE may only consume this explicit filter.
                if new_state in {"CANARY", "ACTIVE"} and edge_positive and edge_filter:
                    next_config["observation_filter"] = dict(edge_filter)
                    next_config["filter_signature"] = edge_signature
                    next_config["authority_mode"] = "CONFLICT_VETO_ONLY"
                db.client.table("strategy_registry").update({
                    "state": new_state,
                    "config": next_config,
                    "evidence": evidence,
                    "version": STRATEGY_GOVERNANCE_VERSION,
                    "updated_at": _now_iso(),
                }).eq("strategy_key", key).eq("symbol", row.get("symbol") or "*").eq("timeframe", row.get("timeframe") or "*").eq("market_regime", row.get("market_regime") or "*").execute()
                _record_event(db, "STRATEGY_STATE", key, current, new_state, reason or "", evidence)
                changes.append({"strategy": key, "from": current, "to": new_state, "reason": reason})
            except Exception:
                pass
    try:
        from strategy_registry import invalidate_registry_cache
        invalidate_registry_cache()
    except Exception:
        pass
    return changes


def _run_one_bounded_auto_research(db, price_fetcher) -> Dict[str, Any]:
    """One symbol/TF per 4h slot; all 30 combinations rotate in ~5 days."""
    status = {
        "attempted": False,
        "persisted": False,
        "symbol": None,
        "timeframe": None,
        "reason": "NO_PRICE_FETCHER",
    }
    if price_fetcher is None:
        return status
    try:
        slot = int(time.time() // (4 * 60 * 60))
        symbol, timeframe = AUTO_RESEARCH_UNIVERSE[slot % len(AUTO_RESEARCH_UNIVERSE)]
        status.update({"attempted": True, "symbol": symbol, "timeframe": timeframe})
        df = price_fetcher(symbol, timeframe)
        if df is None or getattr(df, "empty", True):
            status["reason"] = "NO_CLOSED_CANDLES"
            return status
        from historical_research import run_historical_strategy_research
        research = run_historical_strategy_research(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            max_observations=120,
        )
        status["persisted"] = persist_research_run(db, research, user_id="AUTOPILOT")
        status["reason"] = "OK" if status["persisted"] else "PERSIST_SKIPPED"
        status["resolved"] = research.get("resolved", 0)
        status["validation"] = (research.get("split") or {}).get("validation_30", {})
        return status
    except Exception as exc:
        status["reason"] = f"AUTO_RESEARCH_FAIL_OPEN:{type(exc).__name__}"
        status["error"] = str(exc)[:180]
        return status


def run_autopilot_cycle(db=None, price_fetcher=None) -> Dict[str, Any]:
    """Runs bounded governance work. Safe to call every 4h."""
    if db is None:
        try:
            from supabase_client import supabase_db as db
        except Exception:
            db = None
    result = {
        "version": AUTOPILOT_VERSION,
        "success": False,
        "profiles_updated": 0,
        "strategy_transitions": [],
        "execution_rows": 0,
        "auto_research": {},
        "promotion_governance": {},
        "reason": None,
        "timestamp": _now_iso(),
    }
    if db is None or not getattr(db, "enabled", False):
        result["reason"] = "SUPABASE_DISABLED"
        return result

    # Commit 8: refresh one persisted global gate before any positive authority
    # is considered. This is the only heavy governance read; per-signal reads use
    # the cached singleton state. Failure closes positive authority, never PROTECT.
    try:
        from promotion_governance import refresh_promotion_governance
        result["promotion_governance"] = refresh_promotion_governance(db)
        invalidate_profile_cache()
        try:
            from strategy_registry import invalidate_registry_cache
            invalidate_registry_cache()
        except Exception:
            pass
    except Exception as governance_error:
        result["promotion_governance"] = {
            "quality_optimization_allowed": False,
            "strategy_veto_authority_allowed": False,
            "risk_growth_allowed": False,
            "block_reasons": [f"GOVERNANCE_REFRESH_FAILED:{type(governance_error).__name__}"],
        }

    # Research runs sequentially inside the caller's existing heavy-analysis
    # turn. It never spawns threads and processes only one symbol/TF per cycle.
    result["auto_research"] = _run_one_bounded_auto_research(
        db,
        price_fetcher,
    )

    rows = _fetch_execution_rows(db, limit=500)
    result["execution_rows"] = len(rows)
    groups = _group_execution_rows(rows)
    profiles_updated = 0
    for (symbol, timeframe), group in groups.items():
        metrics = calculate_execution_metrics(group)
        profile = derive_execution_profile(metrics, symbol=symbol, timeframe=timeframe)
        if _upsert_profile(db, profile):
            profiles_updated += 1
    result["profiles_updated"] = profiles_updated

    research = _research_evidence(db)
    edge = _edge_family_evidence(db)
    live = _bounded_q7_live_evidence(db)
    result["strategy_transitions"] = _transition_strategy_registry(
        db,
        research,
        live,
        result.get("promotion_governance") or {},
        edge,
    )
    result["research_evidence"] = research
    result["edge_strategy_evidence"] = edge
    result["live_strategy_evidence"] = live
    result["success"] = True
    result["reason"] = "OK"
    return result


def get_autopilot_status(db=None) -> Dict[str, Any]:
    if db is None:
        try:
            from supabase_client import supabase_db as db
        except Exception:
            db = None
    governance = _governance_status(db)
    status = {
        "version": AUTOPILOT_VERSION,
        "enabled": bool(db is not None and getattr(db, "enabled", False)),
        "positive_authority_enabled": bool(governance.get("quality_optimization_allowed", False)),
        "positive_authority_reason": (
            "EVIDENCE_GATE_OPEN"
            if governance.get("quality_optimization_allowed", False)
            else "EVIDENCE_GATE_CLOSED"
        ),
        "risk_growth_enabled": False,
        "promotion_governance": governance,
        "profiles": [],
        "strategies": [],
        "recent_events": [],
    }
    if not status["enabled"]:
        return status
    try:
        status["profiles"] = (
            db.client.table("adaptive_execution_profiles")
            .select("system_type,symbol,timeframe,market_regime,state,config,evidence,version,updated_at")
            .order("updated_at", desc=True)
            .limit(50)
            .execute().data or []
        )
        status["strategies"] = (
            db.client.table("strategy_registry")
            .select("strategy_key,symbol,timeframe,market_regime,state,evidence,version,updated_at")
            .order("updated_at", desc=True)
            .limit(100)
            .execute().data or []
        )
        status["recent_events"] = (
            db.client.table("adaptive_autopilot_events")
            .select("event_type,component,old_state,new_state,reason,evidence,created_at")
            .order("created_at", desc=True)
            .limit(20)
            .execute().data or []
        )
    except Exception as exc:
        status["error"] = str(exc)[:180]
    return status
