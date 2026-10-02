"""Commit 17.5.10.2 — Black-Scholes / Greeks / GEX context.

This module is context-only.  It does NOT create LONG/SHORT, approve Entry/SL/TP,
increase leverage or bypass Safety.

17.5.10.2 changes:
- fixes net option Delta aggregation (put Delta remains negative; it is not
  multiplied by the CALL+/PUT- GEX sign a second time);
- keeps signed GEX explicitly heuristic because dealer inventory sign is not
  observable from public OI alone;
- adds compact curve-shape / distance features for specialist SHADOW reasoning;
- keeps curves compact to protect bandwidth.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import erf, exp, log, pi, sqrt
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

VERSION = "COMMIT19_1_GREEKS_EXECUTION_QA_V1"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _opt_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"C", "CALL", "CALL_OPTION"}:
        return "CALL"
    if raw in {"P", "PUT", "PUT_OPTION"}:
        return "PUT"
    return raw


def _utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        v = float(value)
        if v > 10_000_000_000:
            v /= 1000.0
        try:
            dt = datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def black_scholes_greeks(
    *, spot: float, strike: float, t_years: float, volatility: float,
    option_type: str, rate: float = 0.0, dividend_yield: float = 0.0,
) -> Dict[str, float]:
    s = max(_f(spot), 1e-12)
    k = max(_f(strike), 1e-12)
    t = max(_f(t_years), 1.0 / (365.0 * 24.0 * 60.0))
    sigma = max(_f(volatility), 1e-6)
    r = _f(rate)
    q = _f(dividend_yield)
    typ = _opt_type(option_type)
    st = sigma * sqrt(t)
    d1 = (log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / st
    d2 = d1 - st
    disc_r = exp(-r * t)
    disc_q = exp(-q * t)
    pdf = _norm_pdf(d1)

    if typ == "PUT":
        price = k * disc_r * _norm_cdf(-d2) - s * disc_q * _norm_cdf(-d1)
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta = (
            -(s * disc_q * pdf * sigma) / (2.0 * sqrt(t))
            + q * s * disc_q * _norm_cdf(-d1)
            - r * k * disc_r * _norm_cdf(-d2)
        ) / 365.0
    else:
        price = s * disc_q * _norm_cdf(d1) - k * disc_r * _norm_cdf(d2)
        delta = disc_q * _norm_cdf(d1)
        theta = (
            -(s * disc_q * pdf * sigma) / (2.0 * sqrt(t))
            - q * s * disc_q * _norm_cdf(d1)
            - r * k * disc_r * _norm_cdf(d2)
        ) / 365.0

    gamma = disc_q * pdf / (s * st)
    vega = s * disc_q * pdf * sqrt(t) / 100.0
    return {
        "price": float(price), "delta": float(delta), "gamma": float(gamma),
        "vega": float(vega), "theta_per_day": float(theta),
        "d1": float(d1), "d2": float(d2),
    }


def _normalize_chain_row(row: Mapping[str, Any], *, as_of: datetime) -> Optional[Dict[str, Any]]:
    strike = _f(row.get("strike") or row.get("strike_price"))
    oi = _f(row.get("open_interest") or row.get("oi"))
    iv_raw = _f(row.get("iv") or row.get("mark_iv") or row.get("implied_volatility"))
    iv = iv_raw / 100.0 if iv_raw > 3.0 else iv_raw
    typ = _opt_type(row.get("option_type") or row.get("type") or row.get("put_call"))
    expiry = _utc(
        row.get("expiry") or row.get("expiration")
        or row.get("expiration_timestamp") or row.get("expiry_timestamp")
    )
    if strike <= 0 or oi <= 0 or iv <= 0 or typ not in {"CALL", "PUT"} or expiry is None:
        return None
    seconds = (expiry - as_of).total_seconds()
    if seconds <= 0:
        return None
    seconds = max(60.0, seconds)
    t_years = seconds / (365.0 * 24.0 * 3600.0)
    multiplier = max(_f(row.get("contract_multiplier") or row.get("multiplier"), 1.0), 1e-12)
    return {
        "strike": strike, "open_interest": oi, "iv": iv, "option_type": typ,
        "expiry": expiry, "t_years": t_years, "multiplier": multiplier,
        "volume": max(0.0, _f(row.get("volume") or row.get("option_volume"))),
    }


def _exposure_at_spot(
    rows: Iterable[Dict[str, Any]], spot: float, *, rate: float = 0.0
) -> Tuple[float, float]:
    """Return heuristic signed GEX and OI-net option Delta dollars.

    GEX uses CALL+/PUT- solely as a visualization heuristic.
    Delta uses the option Delta's own sign: calls positive, puts negative.
    """
    signed_gex = 0.0
    net_delta_dollars = 0.0
    for row in rows:
        g = black_scholes_greeks(
            spot=spot, strike=row["strike"], t_years=row["t_years"],
            volatility=row["iv"], option_type=row["option_type"], rate=rate,
        )
        abs_gex = (
            g["gamma"] * row["open_interest"] * row["multiplier"]
            * spot * spot * 0.01
        )
        gex_sign = 1.0 if row["option_type"] == "CALL" else -1.0
        signed_gex += gex_sign * abs_gex
        net_delta_dollars += (
            g["delta"] * row["open_interest"] * row["multiplier"] * spot
        )
    return signed_gex, net_delta_dollars


def _nearest_zero(points: List[Tuple[float, float]], fallback: Optional[float] = None) -> Optional[float]:
    """Return a zero only when the sampled curve actually crosses zero.

    A smallest absolute value is not a zero-gamma/delta-neutral level.  Using
    it as one produced false precision in the UI and in shadow context.
    """
    if len(points) < 2:
        return None
    values = [float(y) for _, y in points]
    if not any(v > 0 for v in values) or not any(v < 0 for v in values):
        return None
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if y1 == 0 and y2 != 0:
            return float(x1)
        if y1 * y2 < 0:
            w = abs(y1) / max(abs(y1) + abs(y2), 1e-12)
            return float(x1 + (x2 - x1) * w)
    return None


def _distance_pct(level: Any, spot: float) -> Optional[float]:
    n = _f(level, 0.0)
    if n <= 0 or spot <= 0:
        return None
    return round((n / spot - 1.0) * 100.0, 4)


def _local_shape(curve: List[Tuple[float, float]], spot: float) -> Dict[str, Any]:
    if len(curve) < 3 or spot <= 0:
        return {"slope_norm": None, "curvature_norm": None}
    idx = min(range(len(curve)), key=lambda i: abs(curve[i][0] - spot))
    idx = max(1, min(len(curve) - 2, idx))
    x0, y0 = curve[idx - 1]
    x1, y1 = curve[idx]
    x2, y2 = curve[idx + 1]
    dx = max((x2 - x0) / max(spot, 1e-12), 1e-12)
    scale = max(abs(y0), abs(y1), abs(y2), 1.0)
    slope = ((y2 - y0) / scale) / dx
    curvature = ((y2 - 2.0 * y1 + y0) / scale) / max((dx / 2.0) ** 2, 1e-12)
    return {
        "slope_norm": round(float(slope), 6),
        "curvature_norm": round(float(curvature), 6),
    }


def _shadow_context(
    *, spot: float, contracts_used: int, confidence: str, observed: bool,
    gamma_regime: str, zero_dte_share: float, zero_gamma: Any,
    delta_neutral: Any, gamma_wall: Any, call_wall: Any, put_wall: Any,
    gex_curve: List[Tuple[float, float]], as_of: datetime,
) -> Dict[str, Any]:
    distances = {
        "zero_gamma_pct": _distance_pct(zero_gamma, spot),
        "delta_neutral_pct": _distance_pct(delta_neutral, spot),
        "gamma_wall_pct": _distance_pct(gamma_wall, spot),
        "call_wall_pct": _distance_pct(call_wall, spot),
        "put_wall_pct": _distance_pct(put_wall, spot),
    }
    wall_pairs = [
        ("CALL_WALL", distances["call_wall_pct"]),
        ("PUT_WALL", distances["put_wall_pct"]),
        ("GAMMA_WALL", distances["gamma_wall_pct"]),
    ]
    wall_pairs = [(name, val) for name, val in wall_pairs if val is not None]
    nearest_wall = min(wall_pairs, key=lambda x: abs(x[1])) if wall_pairs else (None, None)

    quality = 0.0
    if observed:
        quality += 45.0
        quality += min(25.0, contracts_used * 1.0)
        if zero_dte_share > 0:
            quality += 10.0
        if confidence == "HIGH":
            quality += 15.0
        elif confidence == "MEDIUM":
            quality += 8.0
    quality = min(95.0, quality)
    shape = _local_shape(gex_curve, spot)

    flags = []
    for key in ("zero_gamma_pct", "delta_neutral_pct", "gamma_wall_pct"):
        val = distances.get(key)
        if val is not None and abs(val) <= 1.0:
            flags.append("NEAR_" + key.replace("_pct", "").upper())
    if zero_dte_share >= 0.50:
        flags.append("HIGH_NEAR_EXPIRY_GAMMA_SHARE")

    return {
        "version": "COMMIT19_1_GREEKS_REACTION_CONTEXT_V1",
        "authority": ("OBSERVED_CONFLUENCE_RANKER_ONLY" if observed else "SHADOW_THEORETICAL_ONLY"),
        "observed_chain": bool(observed),
        "context_quality_score": round(quality, 2),
        "gamma_regime": gamma_regime,
        "zero_dte_gamma_share": round(float(zero_dte_share), 6),
        "distances_from_spot_pct": distances,
        "nearest_wall": {
            "name": nearest_wall[0],
            "distance_pct": nearest_wall[1],
        },
        "local_gex_shape": shape,
        "flags": flags,
        "consumers": [
            "EXECUTION_CONTEXT",
            "ENTRY_LOCATION_CONFLUENCE",
            "SL_REACTION_COLLISION",
            "TP_BARRIER_CONFLUENCE",
            "RISK_CONTEXT_SHADOW",
            "REVIEWTRADER_POINT_IN_TIME_LEARNING",
        ],
        "can_create_direction": False,
        # Observed chains may rank ALREADY-EXISTING technical candidates only.
        # They never manufacture a price and theoretical surfaces retain zero authority.
        "can_modify_entry": bool(observed),
        "can_modify_sl": bool(observed),
        "can_modify_tp": bool(observed),
        "can_create_standalone_execution_level": False,
        "can_raise_leverage": False,
        "can_bypass_safety": False,
        "requires_point_in_time_oos_before_direction_authority": True,
        "as_of": as_of.isoformat(),
    }


def aggregate_gamma_exposure(
    option_chain: Iterable[Mapping[str, Any]], *, spot: float, as_of: Any = None,
    rate: float = 0.0, grid_points: int = 41,
) -> Dict[str, Any]:
    s = max(_f(spot), 0.0)
    now = _utc(as_of) or datetime.now(timezone.utc)
    if s <= 0:
        return {
            "version": VERSION, "available": False,
            "reason": "INVALID_SPOT", "authority": "NO_AUTHORITY",
        }

    rows: List[Dict[str, Any]] = []
    # Hard CPU/RAM bound: option-chain context is shadow-only and must never
    # turn a large provider payload/generator into unbounded work.
    for raw in option_chain or []:
        if isinstance(raw, Mapping):
            normalized = _normalize_chain_row(raw, as_of=now)
            if normalized is not None:
                rows.append(normalized)
                if len(rows) >= 128:
                    break
    if not rows:
        return {
            "version": VERSION, "available": False,
            "reason": "NO_VALID_OBSERVED_CHAIN", "authority": "NO_AUTHORITY",
        }

    calls = [r for r in rows if r["option_type"] == "CALL"]
    puts = [r for r in rows if r["option_type"] == "PUT"]
    total_abs = 0.0
    signed = 0.0
    delta_net = 0.0
    aggregate_vega = 0.0
    aggregate_theta = 0.0
    zero_dte_abs = 0.0
    by_strike: Dict[float, Dict[str, float]] = {}
    min_expiry_hours = None

    for r in rows:
        g = black_scholes_greeks(
            spot=s, strike=r["strike"], t_years=r["t_years"],
            volatility=r["iv"], option_type=r["option_type"], rate=rate,
        )
        abs_gex = (
            g["gamma"] * r["open_interest"] * r["multiplier"]
            * s * s * 0.01
        )
        sign = 1.0 if r["option_type"] == "CALL" else -1.0
        signed_component = sign * abs_gex
        total_abs += abs(abs_gex)
        signed += signed_component
        # FIX 17.5.10.2: option Delta already contains the PUT negative sign.
        delta_net += g["delta"] * r["open_interest"] * r["multiplier"] * s
        aggregate_vega += g["vega"] * r["open_interest"] * r["multiplier"]
        aggregate_theta += g["theta_per_day"] * r["open_interest"] * r["multiplier"]

        hours = r["t_years"] * 365.0 * 24.0
        min_expiry_hours = hours if min_expiry_hours is None else min(min_expiry_hours, hours)
        if hours <= 24.0:
            zero_dte_abs += abs(abs_gex)

        bucket = by_strike.setdefault(
            r["strike"], {"call": 0.0, "put": 0.0, "signed": 0.0, "abs": 0.0}
        )
        bucket["call" if r["option_type"] == "CALL" else "put"] += abs(abs_gex)
        bucket["signed"] += signed_component
        bucket["abs"] += abs(abs_gex)

    call_wall = max(by_strike, key=lambda k: by_strike[k]["call"]) if calls else None
    put_wall = max(by_strike, key=lambda k: by_strike[k]["put"]) if puts else None
    gamma_wall = max(by_strike, key=lambda k: by_strike[k]["abs"]) if by_strike else None

    strikes = sorted(by_strike)
    # 17.5.10.2 visual window: use observed strikes but avoid a uselessly wide
    # chart caused by extreme OTM strikes.
    lo = max(s * 0.86, min(strikes) if strikes else s * 0.86)
    hi = min(s * 1.14, max(strikes) if strikes else s * 1.14)
    if hi <= lo or (hi - lo) / s < 0.04:
        lo, hi = s * 0.90, s * 1.10

    ngrid = max(21, min(61, int(grid_points or 41)))
    grid = [lo + (hi - lo) * i / (ngrid - 1) for i in range(ngrid)]
    gex_curve: List[Tuple[float, float]] = []
    delta_curve: List[Tuple[float, float]] = []
    theta_curve: List[Tuple[float, float]] = []
    for px in grid:
        sg, sd = _exposure_at_spot(rows, px, rate=rate)
        total_theta = 0.0
        for r in rows:
            g = black_scholes_greeks(
                spot=px, strike=r["strike"], t_years=r["t_years"],
                volatility=r["iv"], option_type=r["option_type"], rate=rate,
            )
            total_theta += g["theta_per_day"] * r["open_interest"] * r["multiplier"]
        gex_curve.append((px, sg))
        delta_curve.append((px, sd))
        theta_curve.append((px, total_theta))

    zero_gamma = _nearest_zero(gex_curve, s)
    delta_neutral = _nearest_zero(delta_curve, s)

    if len(rows) >= 20 and total_abs > 0:
        confidence = "HIGH"
    elif len(rows) >= 8 and total_abs > 0:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    ratio = signed / max(total_abs, 1e-12)
    regime = (
        "POSITIVE_GAMMA" if ratio >= 0.12
        else "NEGATIVE_GAMMA" if ratio <= -0.12
        else "MIXED_GAMMA"
    )

    atm_rows = sorted(rows, key=lambda r: (abs(r["strike"] - s), r["t_years"]))[:8]
    atm_by_type: Dict[str, Any] = {}
    for typ in ("CALL", "PUT"):
        typed = [r for r in atm_rows if r["option_type"] == typ]
        if not typed:
            continue
        r = typed[0]
        g = black_scholes_greeks(
            spot=s, strike=r["strike"], t_years=r["t_years"],
            volatility=r["iv"], option_type=typ, rate=rate,
        )
        atm_by_type[typ.lower()] = {
            "strike": round(float(r["strike"]), 10),
            "expiry_hours": round(float(r["t_years"] * 365.0 * 24.0), 4),
            "iv": round(float(r["iv"]), 6),
            "delta": round(float(g["delta"]), 6),
            "gamma": round(float(g["gamma"]), 10),
            "vega": round(float(g["vega"]), 6),
            "theta_per_day": round(float(g["theta_per_day"]), 6),
        }

    zero_share = zero_dte_abs / max(total_abs, 1e-12)
    specialist_shadow = _shadow_context(
        spot=s,
        contracts_used=len(rows),
        confidence=confidence,
        observed=True,
        gamma_regime=regime,
        zero_dte_share=zero_share,
        zero_gamma=zero_gamma,
        delta_neutral=delta_neutral,
        gamma_wall=gamma_wall,
        call_wall=call_wall,
        put_wall=put_wall,
        gex_curve=gex_curve,
        as_of=now,
    )

    return {
        "version": VERSION,
        "available": True,
        "authority": "CONTEXT_ONLY_NOT_DIRECTION",
        "observed_option_chain": True,
        "execution_reaction_map_authority": "OBSERVED_CONFLUENCE_RANKER_ONLY",
        "context_quality_score": specialist_shadow.get("context_quality_score"),
        "can_refine_entry": True,
        "can_refine_sl": True,
        "can_refine_tp": True,
        "can_create_standalone_execution_level": False,
        "can_raise_leverage": False,
        "dealer_position_sign": "HEURISTIC_CALL_PLUS_PUT_MINUS_NOT_OBSERVED",
        "delta_exposure_semantics": "OPTION_DELTA_OI_NET_NOT_DEALER_INVENTORY",
        "confidence": confidence,
        "contracts_used": len(rows),
        "spot": round(s, 10),
        "gamma_regime": regime,
        "signed_gex_ratio": round(ratio, 6),
        "absolute_gamma_exposure": round(total_abs, 6),
        "heuristic_signed_gamma_exposure": round(signed, 6),
        "heuristic_signed_delta_dollars": round(delta_net, 6),
        "aggregate_vega_per_iv_point": round(aggregate_vega, 6),
        "aggregate_theta_per_day": round(aggregate_theta, 6),
        "representative_atm_greeks": atm_by_type,
        "zero_dte_gamma_share": round(zero_share, 6),
        "nearest_expiry_hours": round(float(min_expiry_hours or 0.0), 4),
        "gamma_wall": round(float(gamma_wall), 10) if gamma_wall is not None else None,
        "call_wall": round(float(call_wall), 10) if call_wall is not None else None,
        "put_wall": round(float(put_wall), 10) if put_wall is not None else None,
        "zero_gamma_level": round(float(zero_gamma), 10) if zero_gamma is not None else None,
        "delta_neutral_level": round(float(delta_neutral), 10) if delta_neutral is not None else None,
        "gex_curve": [
            [round(float(px), 10), round(float(value), 6)]
            for px, value in gex_curve
        ],
        "delta_curve": [
            [round(float(px), 10), round(float(value), 6)]
            for px, value in delta_curve
        ],
        "theta_curve": [
            [round(float(px), 10), round(float(value), 6)]
            for px, value in theta_curve
        ],
        "specialist_shadow_context": specialist_shadow,
        "production_score_adjustment": 0.0,
        "can_create_direction": False,
        "can_bypass_safety": False,
        "can_move_levels_without_execution_validation": False,
    }


def theoretical_gamma_shape(
    *, spot: float, volatility: float, as_of: Any = None, expiry_hours: float = 6.5
) -> Dict[str, Any]:
    """Black-Scholes shape only; no option-chain/OI levels are invented."""
    s = max(_f(spot), 0.0)
    vol = max(_f(volatility), 1e-4)
    if vol > 3.0:
        vol /= 100.0
    if s <= 0:
        return {
            "version": VERSION, "available": False,
            "reason": "INVALID_SPOT", "authority": "NO_AUTHORITY",
        }
    now = _utc(as_of) or datetime.now(timezone.utc)
    t = max(1.0, _f(expiry_hours, 6.5)) / (365.0 * 24.0)
    ngrid = 41
    grid = [s * (0.90 + 0.20 * i / (ngrid - 1)) for i in range(ngrid)]
    gex_curve = []
    delta_curve = []
    theta_curve = []
    # ATM theoretical contract: gamma is unsigned/positive by construction.
    # It illustrates convexity concentration only; it cannot imply dealer sign,
    # gamma walls, zero-gamma or delta-neutral levels without observed OI.
    for px in grid:
        call = black_scholes_greeks(
            spot=px, strike=s, t_years=t, volatility=vol, option_type="CALL"
        )
        put = black_scholes_greeks(
            spot=px, strike=s, t_years=t, volatility=vol, option_type="PUT"
        )
        gex_curve.append([round(float(px),10), round(float((call["gamma"] + put["gamma"]) * px * px * 0.01),6)])
        delta_curve.append([round(float(px),10), round(float(call["delta"] + put["delta"]),6)])
        theta_curve.append([round(float(px),10), round(float(call["theta_per_day"] + put["theta_per_day"]),6)])

    shadow = _shadow_context(
        spot=s, contracts_used=0, confidence="THEORETICAL", observed=False,
        gamma_regime="THEORETICAL_SHAPE", zero_dte_share=0.0,
        zero_gamma=None, delta_neutral=None, gamma_wall=None, call_wall=None,
        put_wall=None, gex_curve=[(float(x),float(y)) for x,y in gex_curve], as_of=now,
    )
    shadow.update({
        "authority": "SHADOW_THEORETICAL_ONLY",
        "observed_chain": False,
        "context_quality_score": 0.0,
        "requires_observed_chain_for_learning": True,
    })
    atm_call = black_scholes_greeks(
        spot=s, strike=s, t_years=t, volatility=vol, option_type="CALL"
    )
    atm_put = black_scholes_greeks(
        spot=s, strike=s, t_years=t, volatility=vol, option_type="PUT"
    )
    representative = {
        "call": {
            "strike": round(s, 10), "expiry_hours": round(t * 365.0 * 24.0, 4),
            "iv": round(vol, 6), "delta": round(atm_call["delta"], 6),
            "gamma": round(atm_call["gamma"], 10), "vega": round(atm_call["vega"], 6),
            "theta_per_day": round(atm_call["theta_per_day"], 6),
        },
        "put": {
            "strike": round(s, 10), "expiry_hours": round(t * 365.0 * 24.0, 4),
            "iv": round(vol, 6), "delta": round(atm_put["delta"], 6),
            "gamma": round(atm_put["gamma"], 10), "vega": round(atm_put["vega"], 6),
            "theta_per_day": round(atm_put["theta_per_day"], 6),
        },
    }
    return {
        "version": VERSION, "available": True,
        "authority": "SHADOW_THEORETICAL_ONLY",
        "observed_option_chain": False,
        "execution_reaction_map_authority": "NO_LIVE_EXECUTION_AUTHORITY",
        "context_quality_score": 0.0,
        "can_refine_entry": False, "can_refine_sl": False, "can_refine_tp": False,
        "can_create_standalone_execution_level": False, "can_raise_leverage": False,
        "dealer_position_sign": "NOT_AVAILABLE_THEORETICAL_SHAPE_ONLY",
        "confidence": "THEORETICAL", "contracts_used": 0, "spot": round(s,10),
        "gamma_regime": "THEORETICAL_SHAPE",
        "gamma_wall": None, "call_wall": None, "put_wall": None,
        "zero_gamma_level": None, "delta_neutral_level": None,
        "representative_atm_greeks": representative,
        "aggregate_vega_per_iv_point": None,
        "aggregate_theta_per_day": None,
        "heuristic_signed_delta_dollars": None,
        "heuristic_signed_gamma_exposure": None,
        "zero_dte_gamma_share": 0.0,
        "gex_curve": gex_curve, "delta_curve": delta_curve, "theta_curve": theta_curve,
        "specialist_shadow_context": shadow, "production_score_adjustment": 0.0,
        "can_create_direction": False, "can_bypass_safety": False,
        "can_move_levels_without_execution_validation": False,
    }

def build_market_maker_context(
    *, spot: float, option_chain: Optional[Iterable[Mapping[str, Any]]] = None,
    realized_or_implied_volatility: float = 0.0, as_of: Any = None,
) -> Dict[str, Any]:
    if option_chain:
        observed = aggregate_gamma_exposure(
            option_chain, spot=spot, as_of=as_of
        )
        if observed.get("available"):
            return observed
    return theoretical_gamma_shape(
        spot=spot,
        volatility=max(_f(realized_or_implied_volatility, 0.60), 0.05),
        as_of=as_of,
    )
