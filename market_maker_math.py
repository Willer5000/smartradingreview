"""Commit 17.5.10 — market-maker math context (Black-Scholes / Greeks / GEX).

Purpose
-------
Provide a deterministic mathematical context layer for option-sensitive markets
without turning options heuristics into an autonomous LONG/SHORT generator.

The module is deliberately provider-agnostic.  It consumes an option-chain
snapshot supplied by the application/provider and computes:
- Black-Scholes price and Greeks (delta, gamma, vega, theta);
- OI-weighted absolute gamma exposure;
- heuristic signed gamma exposure (calls +, puts -; explicitly labelled);
- 0DTE gamma share;
- call/put gamma walls;
- approximate zero-gamma and delta-neutral levels.

Important limitations
---------------------
Dealer inventory/sign is not observable from ordinary option-chain OI.  The
signed GEX convention is therefore a market-maker *heuristic*, not a fact about
actual dealer positioning.  If no observed option chain with IV + OI is supplied,
we can produce a theoretical Black-Scholes gamma shape, but its authority remains
SHADOW_THEORETICAL_ONLY and it cannot gate publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import erf, exp, log, pi, sqrt
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

VERSION = "COMMIT17_5_10_MM_MATH_V1"


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
        # Accept seconds or milliseconds.
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
    """Black-Scholes price/Greeks using continuous compounding.

    `volatility` is decimal annualized volatility (0.50 == 50%).  The function
    is pure and does not infer implied volatility from prices.
    """
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
    # Accept IV in percentage points (e.g. 55) or decimal (0.55).
    iv = iv_raw / 100.0 if iv_raw > 3.0 else iv_raw
    typ = _opt_type(row.get("option_type") or row.get("type") or row.get("put_call"))
    expiry = _utc(row.get("expiry") or row.get("expiration") or row.get("expiration_timestamp") or row.get("expiry_timestamp"))
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


def _exposure_at_spot(rows: Iterable[Dict[str, Any]], spot: float, *, rate: float = 0.0) -> Tuple[float, float]:
    signed_gex = 0.0
    signed_delta_dollars = 0.0
    for row in rows:
        g = black_scholes_greeks(
            spot=spot, strike=row["strike"], t_years=row["t_years"],
            volatility=row["iv"], option_type=row["option_type"], rate=rate,
        )
        # Dollar gamma for an approximate 1% underlying move.
        abs_gex = g["gamma"] * row["open_interest"] * row["multiplier"] * spot * spot * 0.01
        # Common heuristic convention.  It is explicitly NOT observed dealer inventory.
        sign = 1.0 if row["option_type"] == "CALL" else -1.0
        signed_gex += sign * abs_gex
        signed_delta_dollars += g["delta"] * row["open_interest"] * row["multiplier"] * spot
    return signed_gex, signed_delta_dollars


def _nearest_zero(points: List[Tuple[float, float]], fallback: Optional[float]) -> Optional[float]:
    if not points:
        return fallback
    if all(y == 0 for _, y in points):
        return None
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if y1 == 0:
            return x1
        if y1 * y2 < 0:
            # Linear interpolation is adequate for a diagnostic level.
            w = abs(y1) / max(abs(y1) + abs(y2), 1e-12)
            return x1 + (x2 - x1) * w
    return points[-1][0] if points[-1][1] == 0 else None


def aggregate_gamma_exposure(
    option_chain: Iterable[Mapping[str, Any]], *, spot: float, as_of: Any = None,
    rate: float = 0.0, grid_points: int = 41,
) -> Dict[str, Any]:
    """Aggregate an observed chain into market-maker context.

    The output distinguishes observed inputs from the signed-dealer heuristic.
    No field in this function is a calibrated probability of direction/TP/SL.
    """
    s = max(_f(spot), 0.0)
    now = _utc(as_of) or datetime.now(timezone.utc)
    if s <= 0:
        return {"version": VERSION, "available": False, "reason": "INVALID_SPOT", "authority": "NO_AUTHORITY"}

    rows: List[Dict[str, Any]] = []
    for raw in __import__("itertools").islice(option_chain or [], 128):
        if isinstance(raw, Mapping):
            normalized = _normalize_chain_row(raw, as_of=now)
            if normalized is not None:
                rows.append(normalized)
    if not rows:
        return {"version": VERSION, "available": False, "reason": "NO_VALID_OBSERVED_CHAIN", "authority": "NO_AUTHORITY"}

    calls = [r for r in rows if r["option_type"] == "CALL"]
    puts = [r for r in rows if r["option_type"] == "PUT"]
    total_abs = 0.0
    signed = 0.0
    delta_signed = 0.0
    zero_dte_abs = 0.0
    by_strike: Dict[float, Dict[str, float]] = {}
    min_expiry_hours = None
    for r in rows:
        g = black_scholes_greeks(
            spot=s, strike=r["strike"], t_years=r["t_years"], volatility=r["iv"],
            option_type=r["option_type"], rate=rate,
        )
        abs_gex = g["gamma"] * r["open_interest"] * r["multiplier"] * s * s * 0.01
        sign = 1.0 if r["option_type"] == "CALL" else -1.0
        signed_component = sign * abs_gex
        total_abs += abs(abs_gex)
        signed += signed_component
        delta_signed += g["delta"] * r["open_interest"] * r["multiplier"] * s
        hours = r["t_years"] * 365.0 * 24.0
        min_expiry_hours = hours if min_expiry_hours is None else min(min_expiry_hours, hours)
        if hours <= 24.0:
            zero_dte_abs += abs(abs_gex)
        bucket = by_strike.setdefault(r["strike"], {"call": 0.0, "put": 0.0, "signed": 0.0, "abs": 0.0})
        bucket["call" if r["option_type"] == "CALL" else "put"] += abs(abs_gex)
        bucket["signed"] += signed_component
        bucket["abs"] += abs(abs_gex)

    call_wall = max(by_strike, key=lambda k: by_strike[k]["call"]) if calls else None
    put_wall = max(by_strike, key=lambda k: by_strike[k]["put"]) if puts else None
    gamma_wall = max(by_strike, key=lambda k: by_strike[k]["abs"]) if by_strike else None

    strikes = sorted(by_strike)
    lo = max(s * 0.85, min(strikes) if strikes else s * 0.85)
    hi = min(s * 1.15, max(strikes) if strikes else s * 1.15)
    if hi <= lo:
        lo, hi = s * 0.90, s * 1.10
    ngrid = max(11, min(101, int(grid_points or 41)))
    grid = [lo + (hi - lo) * i / (ngrid - 1) for i in range(ngrid)]
    gex_curve: List[Tuple[float, float]] = []
    delta_curve: List[Tuple[float, float]] = []
    theta_curve = []
    absolute_gamma_curve = []
    for px in grid:
        theta = sum(black_scholes_greeks(spot=px, strike=r["strike"], t_years=r["t_years"], volatility=r["iv"], option_type=r["option_type"], rate=rate)["theta_per_day"] * r["open_interest"] * r["multiplier"] for r in rows)
        theta_curve.append((px, theta))
        absolute_gamma_curve.append((px, sum(black_scholes_greeks(spot=px, strike=r["strike"], t_years=r["t_years"], volatility=r["iv"], option_type=r["option_type"], rate=rate)["gamma"] * r["open_interest"] * r["multiplier"] * px * px * .01 for r in rows)))
        sg, sd = _exposure_at_spot(rows, px, rate=rate)
        gex_curve.append((px, sg))
        delta_curve.append((px, sd))
    zero_gamma = _nearest_zero(gex_curve, s)
    delta_neutral = _nearest_zero(delta_curve, s)

    if len(rows) >= 20 and total_abs > 0:
        confidence = "HIGH"
    elif len(rows) >= 8 and total_abs > 0:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    ratio = signed / max(total_abs, 1e-12)
    regime = "POSITIVE_GAMMA" if ratio >= 0.12 else ("NEGATIVE_GAMMA" if ratio <= -0.12 else "MIXED_GAMMA")

    return {
        "version": VERSION,
        "available": True,
        "authority": "CONTEXT_ONLY_NOT_DIRECTION",
        "observed_option_chain": True,
        "dealer_position_sign": "HEURISTIC_CALL_PLUS_PUT_MINUS_NOT_OBSERVED",
        "confidence": confidence,
        "contracts_used": len(rows),
        "spot": round(s, 10),
        "gamma_regime": regime,
        "signed_gex_ratio": round(ratio, 6),
        "absolute_gamma_exposure": round(total_abs, 6),
        "heuristic_signed_gamma_exposure": round(signed, 6),
        "heuristic_signed_delta_dollars": round(delta_signed, 6),
        "zero_dte_gamma_share": round(zero_dte_abs / max(total_abs, 1e-12), 6),
        "nearest_expiry_hours": round(float(min_expiry_hours or 0.0), 4),
        "gamma_wall": round(float(gamma_wall), 10) if gamma_wall is not None else None,
        "call_wall": round(float(call_wall), 10) if call_wall is not None else None,
        "put_wall": round(float(put_wall), 10) if put_wall is not None else None,
        "zero_gamma_level": round(float(zero_gamma), 10) if zero_gamma is not None else None,
        "delta_neutral_level": round(float(delta_neutral), 10) if delta_neutral is not None else None,
        # Compact curves for the frontend indicator.  They are diagnostic
        # mathematics, not probabilities or autonomous trade signals.
        "gex_curve": [[round(float(px), 10), round(float(value), 6)] for px, value in gex_curve],
        "delta_curve": [[round(float(px), 10), round(float(value), 6)] for px, value in delta_curve],
        "absolute_gamma_curve": [[round(float(px),10),round(float(v),6)] for px,v in absolute_gamma_curve],
        "theta_curve": [[round(float(px), 10), round(float(value), 6)] for px, value in theta_curve],
        "delta_theta_convention": "LONG_OPTIONS_OI_WEIGHTED_NOT_DEALER_INVENTORY",
        "production_score_adjustment": 0.0,
        "can_create_direction": False,
        "can_bypass_safety": False,
        "can_move_levels_without_execution_validation": False,
    }


def theoretical_gamma_shape(*, spot: float, volatility: float, as_of: Any = None, expiry_hours: float = 6.5) -> Dict[str, Any]:
    """Black-Scholes-only fallback with equal synthetic OI.

    This is useful to reason about how gamma behaves near expiry, but it is not
    market positioning and never receives production authority.
    """
    s = max(_f(spot), 0.0)
    vol = max(_f(volatility), 1e-4)
    if vol > 3.0:
        vol /= 100.0
    if s <= 0:
        return {"version": VERSION, "available": False, "reason": "INVALID_SPOT", "authority": "NO_AUTHORITY"}
    now = _utc(as_of) or datetime.now(timezone.utc)
    t = max(1.0, _f(expiry_hours, 6.5)) / (365.0 * 24.0)
    rows = []
    for m in (0.94, 0.96, 0.98, 0.99, 1.0, 1.01, 1.02, 1.04, 1.06):
        k = s * m
        for typ in ("CALL", "PUT"):
            rows.append({
                "strike": k, "open_interest": 1.0, "iv": vol,
                "option_type": typ, "expiry": now.timestamp() + t * 365.0 * 24.0 * 3600.0,
                "multiplier": 1.0,
            })
    out = aggregate_gamma_exposure(rows, spot=s, as_of=now)
    out["gex_curve"] = out.pop("absolute_gamma_curve", [])
    out.update({
        "authority": "SHADOW_THEORETICAL_ONLY",
        "observed_option_chain": False,
        "dealer_position_sign": "NOT_AVAILABLE_THEORETICAL_SHAPE_ONLY",
        "confidence": "THEORETICAL",
        "gamma_regime": "THEORETICAL",
        "call_wall": None, "put_wall": None, "gamma_wall": None,
        "zero_gamma_level": None, "delta_neutral_level": None,
        "production_score_adjustment": 0.0,
        "can_create_direction": False,
    })
    return out


def build_market_maker_context(
    *, spot: float, option_chain: Optional[Iterable[Mapping[str, Any]]] = None,
    realized_or_implied_volatility: float = 0.0, as_of: Any = None,
) -> Dict[str, Any]:
    if option_chain:
        observed = aggregate_gamma_exposure(option_chain, spot=spot, as_of=as_of)
        if observed.get("available"):
            return observed
    return theoretical_gamma_shape(
        spot=spot,
        volatility=max(_f(realized_or_implied_volatility, 0.60), 0.05),
        as_of=as_of,
    )
