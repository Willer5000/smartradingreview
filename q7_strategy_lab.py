"""Q7 Adaptive Intraday Strategy Lab — SHADOW ONLY.

No trading authority. This module only observes strategy states so they can be
measured later by ReviewTrader/Analytics. It never changes votes, Safety,
Entry, SL, TP, leverage or publication.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

import numpy as np


Q7_STRATEGY_LAB_VERSION = "Q7_STRATEGY_LAB_SHADOW_V1"


def analyze_q7_strategy_lab(
    df,
    symbol: str,
    timeframe: str,
    system_type: str,
    market_regime: Dict[str, Any] | None,
    momentum: Dict[str, Any] | None,
    volatility: Dict[str, Any] | None,
    volume: Dict[str, Any] | None,
    structure: Dict[str, Any] | None,
    confirmation: Dict[str, Any] | None,
    final_action: str,
    rsi_calculator: Callable,
) -> Dict[str, Any]:
    """Return compact Q7 shadow observations for the current closed candle."""

    result = {
        "version": Q7_STRATEGY_LAB_VERSION,
        "shadow_only": True,
        "affects_vote": False,
        "affects_safety": False,
        "affects_entry": False,
        "affects_levels": False,
        "affects_publication": False,
        "affects_leverage": False,
        "eligible": False,
        "system_type": str(system_type or "").lower(),
        "symbol": str(symbol or ""),
        "timeframe": str(timeframe or ""),
        "final_action_observed": str(final_action or "NO_OPERAR").upper(),
        "final_action_normalized": None,
        "active_profile": None,
        "strategies": {},
        "reason": None,
    }

    try:
        raw_action = str(
            result.get("final_action_observed")
            or "NO_OPERAR"
        ).upper()

        if raw_action in ("LONG", "COMPRA_SPOT", "BUY"):
            normalized_action = "LONG"
        elif raw_action in ("SHORT", "VENTA_SPOT", "SELL"):
            normalized_action = "SHORT"
        else:
            normalized_action = raw_action

        result["final_action_normalized"] = normalized_action

        # Q7 V1 is deliberately limited to Futures. Spot/TGP stays unchanged.
        if result["system_type"] != "futures":
            result["reason"] = "SPOT_OUT_OF_SCOPE_Q7_V1"
            return result

        profiles = {
            "5m": ("FAST", 3, 7, 14),
            "15m": ("FAST", 3, 7, 14),
            "30m": ("BALANCED", 7, 14, 21),
            "1h": ("BALANCED", 7, 14, 21),
            "2h": ("STRUCTURAL", 7, 14, 21),
            "4h": ("STRUCTURAL", None, 14, None),
        }

        if timeframe not in profiles:
            result["reason"] = "TIMEFRAME_OUT_OF_SCOPE_Q7_V1"
            return result

        if df is None or len(df) < 30:
            result["reason"] = "INSUFFICIENT_CLOSED_CANDLES"
            return result

        close = np.asarray(df["close"].values, dtype=float)
        high = np.asarray(df["high"].values, dtype=float)
        low = np.asarray(df["low"].values, dtype=float)
        open_price = np.asarray(df["open"].values, dtype=float)
        raw_volume = np.asarray(df["volume"].values, dtype=float)

        if not all(
            np.isfinite(values).all()
            for values in (close, high, low, open_price, raw_volume)
        ):
            result["reason"] = "INVALID_OHLCV_FOR_Q7"
            return result

        profile, fast_period, medium_period, slow_period = profiles[timeframe]
        result["eligible"] = True
        result["active_profile"] = profile
        result["reason"] = "SHADOW_OBSERVATION_ONLY"

        market_regime = market_regime if isinstance(market_regime, dict) else {}
        momentum = momentum if isinstance(momentum, dict) else {}
        volatility = volatility if isinstance(volatility, dict) else {}
        volume = volume if isinstance(volume, dict) else {}
        structure = structure if isinstance(structure, dict) else {}
        confirmation = confirmation if isinstance(confirmation, dict) else {}

        def alignment(direction: str) -> str:
            direction = str(direction or "NEUTRAL").upper()
            action = str(
                result.get("final_action_normalized")
                or ""
            ).upper()

            if direction not in ("LONG", "SHORT"):
                return "NEUTRAL"
            if action == direction:
                return "ALIGNED"
            if action in ("LONG", "SHORT"):
                return "CONFLICT"
            return "OBSERVATION_ONLY"

        def last_two(series):
            if series is None or len(series) < 2:
                return None, None
            return float(series[-1]), float(series[-2])

        # ------------------------------------------------------------------
        # Q7-RSI — timeframe-adaptive RSI strategy profile
        # ------------------------------------------------------------------
        fast_rsi = rsi_calculator(close, fast_period) if fast_period else None
        medium_rsi = rsi_calculator(close, medium_period)
        slow_rsi = rsi_calculator(close, slow_period) if slow_period else None

        fast_now, fast_prev = last_two(fast_rsi)
        medium_now, medium_prev = last_two(medium_rsi)
        slow_now, slow_prev = last_two(slow_rsi)

        rsi_direction = "NEUTRAL"
        rsi_state = "NO_EDGE"
        long_hits = 0
        short_hits = 0
        max_hits = 0
        cross = "NONE"

        if profile in ("FAST", "BALANCED"):
            lookback = 4 if profile == "FAST" else 5
            recent = np.asarray(fast_rsi[-lookback:], dtype=float)
            low_limit = 30 if profile == "FAST" else 40
            high_limit = 70 if profile == "FAST" else 60

            long_checks = [
                np.min(recent) <= low_limit,
                fast_now > fast_prev,
                fast_now >= medium_now,
                medium_now >= medium_prev,
                slow_now >= (40 if profile == "FAST" else 45),
            ]
            short_checks = [
                np.max(recent) >= high_limit,
                fast_now < fast_prev,
                fast_now <= medium_now,
                medium_now <= medium_prev,
                slow_now <= (60 if profile == "FAST" else 55),
            ]

            long_hits = sum(bool(value) for value in long_checks)
            short_hits = sum(bool(value) for value in short_checks)
            max_hits = 5

            if fast_now > medium_now and fast_prev <= medium_prev:
                cross = "UP"
            elif fast_now < medium_now and fast_prev >= medium_prev:
                cross = "DOWN"

            if long_hits >= 3 and long_hits > short_hits:
                rsi_direction = "LONG"
                rsi_state = (
                    "FAST_RSI_RECOVERY_LONG"
                    if profile == "FAST"
                    else "BALANCED_RSI_PULLBACK_LONG"
                )
            elif short_hits >= 3 and short_hits > long_hits:
                rsi_direction = "SHORT"
                rsi_state = (
                    "FAST_RSI_RECOVERY_SHORT"
                    if profile == "FAST"
                    else "BALANCED_RSI_PULLBACK_SHORT"
                )
            else:
                rsi_state = f"{profile}_RSI_NEUTRAL"

        elif timeframe == "2h":
            long_checks = [
                medium_now >= 50,
                medium_now > medium_prev,
                slow_now >= 45,
                fast_now >= medium_now,
            ]
            short_checks = [
                medium_now <= 50,
                medium_now < medium_prev,
                slow_now <= 55,
                fast_now <= medium_now,
            ]

            long_hits = sum(bool(value) for value in long_checks)
            short_hits = sum(bool(value) for value in short_checks)
            max_hits = 4

            if long_hits >= 3 and long_hits > short_hits:
                rsi_direction = "LONG"
                rsi_state = "STRUCTURAL_RSI_CONTEXT_LONG"
            elif short_hits >= 3 and short_hits > long_hits:
                rsi_direction = "SHORT"
                rsi_state = "STRUCTURAL_RSI_CONTEXT_SHORT"
            else:
                rsi_state = "STRUCTURAL_RSI_NEUTRAL"

        else:
            long_hits = int(medium_now > 50 and medium_now > medium_prev)
            short_hits = int(medium_now < 50 and medium_now < medium_prev)
            max_hits = 1

            if long_hits:
                rsi_direction = "LONG"
                rsi_state = "RSI14_STRUCTURAL_LONG"
            elif short_hits:
                rsi_direction = "SHORT"
                rsi_state = "RSI14_STRUCTURAL_SHORT"
            else:
                rsi_state = "RSI14_STRUCTURAL_NEUTRAL"

        result["strategies"]["rsi_profile"] = {
            "name": "Q7_RSI_PROFILE_V1",
            "profile": profile,
            "direction": rsi_direction,
            "state": rsi_state,
            "alignment_with_system": alignment(rsi_direction),
            "evidence_hits": max(long_hits, short_hits),
            "max_evidence_hits": max_hits,
            "periods": {
                "fast": fast_period,
                "medium": medium_period,
                "slow": slow_period,
            },
            "values": {
                "fast": round(fast_now, 3) if fast_now is not None else None,
                "medium": round(medium_now, 3),
                "slow": round(slow_now, 3) if slow_now is not None else None,
            },
            "slopes": {
                "fast": (
                    round(fast_now - fast_prev, 3)
                    if fast_now is not None
                    else None
                ),
                "medium": round(medium_now - medium_prev, 3),
                "slow": (
                    round(slow_now - slow_prev, 3)
                    if slow_now is not None
                    else None
                ),
            },
            "fast_medium_cross": cross,
            "regular_divergences": list(momentum.get("divergences", []) or []),
            "hidden_divergences": list(
                momentum.get("hidden_divergences", []) or []
            ),
            "shadow_only": True,
        }

        # ------------------------------------------------------------------
        # Q7-VWAP — real rolling 24h VWAP from OHLCV, only for RANGING
        # ------------------------------------------------------------------
        vwap_windows = {
            "5m": 288,
            "15m": 96,
            "30m": 48,
            "1h": 24,
        }

        vwap_result = {
            "name": "Q7_ROLLING_VWAP_REVERSION_V1",
            "method": "ROLLING_24H_TYPICAL_PRICE_VOLUME",
            "direction": "NEUTRAL",
            "state": "OUT_OF_SCOPE",
            "alignment_with_system": "NEUTRAL",
            "vwap": None,
            "deviation_pct": None,
            "distance_atr": None,
            "coverage_pct": None,
            "shadow_only": True,
        }

        if timeframe in vwap_windows:
            target_bars = vwap_windows[timeframe]
            used_bars = min(len(df), target_bars)

            if used_bars >= 12:
                typical = (
                    high[-used_bars:] + low[-used_bars:] + close[-used_bars:]
                ) / 3.0
                used_volume = raw_volume[-used_bars:]
                total_volume = float(np.sum(used_volume))

                if total_volume > 0:
                    vwap = float(np.sum(typical * used_volume) / total_volume)
                    price = float(close[-1])
                    deviation_pct = (
                        (price - vwap) / vwap * 100.0 if vwap > 0 else 0.0
                    )
                    atr_pct = float(volatility.get("atr_pct", 0) or 0)
                    distance_atr = (
                        deviation_pct / atr_pct if atr_pct > 0 else 0.0
                    )

                    vp = structure.get("volume_profile", {}) or {}
                    val = float(vp.get("val", 0) or 0)
                    vah = float(vp.get("vah", 0) or 0)
                    support = structure.get("nearest_support")
                    resistance = structure.get("nearest_resistance")
                    tolerance = max(0.25, min(1.0, atr_pct * 0.60))

                    def near(level) -> bool:
                        if not level or price <= 0:
                            return False
                        return (
                            abs(price - float(level)) / price * 100.0
                            <= tolerance
                        )

                    regime = str(
                        market_regime.get("regime", "UNKNOWN")
                    ).upper()
                    vwap_direction = "NEUTRAL"
                    vwap_state = "NO_EDGE"

                    if regime != "RANGING":
                        vwap_state = "REGIME_NOT_RANGING"
                    elif (
                        distance_atr <= -0.75
                        and (near(val) or near(support))
                        and close[-1] > open_price[-1]
                    ):
                        vwap_direction = "LONG"
                        vwap_state = "VWAP_RANGE_REVERSION_LONG"
                    elif (
                        distance_atr >= 0.75
                        and (near(vah) or near(resistance))
                        and close[-1] < open_price[-1]
                    ):
                        vwap_direction = "SHORT"
                        vwap_state = "VWAP_RANGE_REVERSION_SHORT"

                    vwap_result.update(
                        {
                            "direction": vwap_direction,
                            "state": vwap_state,
                            "alignment_with_system": alignment(vwap_direction),
                            "vwap": round(vwap, 8),
                            "deviation_pct": round(deviation_pct, 4),
                            "distance_atr": round(distance_atr, 4),
                            "coverage_pct": round(
                                min(100.0, used_bars / target_bars * 100.0),
                                2,
                            ),
                            "target_bars": target_bars,
                            "used_bars": used_bars,
                        }
                    )

        result["strategies"]["vwap_reversion"] = vwap_result

        # ------------------------------------------------------------------
        # Q7-BR — breakout + immediate retest acceptance of VAH / VAL
        # ------------------------------------------------------------------
        retest = {
            "name": "Q7_BREAKOUT_RETEST_V1",
            "direction": "NEUTRAL",
            "state": "OUT_OF_SCOPE",
            "alignment_with_system": "NEUTRAL",
            "level": None,
            "level_type": None,
            "shadow_only": True,
        }

        if timeframe in ("15m", "30m", "1h", "2h"):
            atr_pct = float(volatility.get("atr_pct", 0) or 0)
            tolerance = max(0.10, min(0.60, atr_pct * 0.35))
            vp = structure.get("volume_profile", {}) or {}
            vah = float(vp.get("vah", 0) or 0)
            val = float(vp.get("val", 0) or 0)

            prev_close = float(close[-2])
            last_close = float(close[-1])
            last_low = float(low[-1])
            last_high = float(high[-1])

            long_accept = bool(
                vah > 0
                and prev_close > vah
                and last_low <= vah * (1.0 + tolerance / 100.0)
                and last_close > vah
            )
            short_accept = bool(
                val > 0
                and prev_close < val
                and last_high >= val * (1.0 - tolerance / 100.0)
                and last_close < val
            )

            if long_accept:
                br_direction = "LONG"
                br_state = "ACCEPTED_LONG_RETEST"
                level = vah
                level_type = "VAH"
            elif short_accept:
                br_direction = "SHORT"
                br_state = "ACCEPTED_SHORT_RETEST"
                level = val
                level_type = "VAL"
            else:
                br_direction = "NEUTRAL"
                br_state = "NO_RETEST"
                level = None
                level_type = None

                if (
                    confirmation.get("confirmation_status") == "CONFIRMED"
                    and confirmation.get("is_breakout")
                ):
                    br_direction = "LONG"
                    br_state = "BREAKOUT_PENDING_RETEST"
                    level = confirmation.get("breakout_level")
                    level_type = "STRUCTURE"
                elif (
                    confirmation.get("confirmation_status") == "CONFIRMED"
                    and confirmation.get("is_breakdown")
                ):
                    br_direction = "SHORT"
                    br_state = "BREAKDOWN_PENDING_RETEST"
                    level = confirmation.get("breakout_level")
                    level_type = "STRUCTURE"

            retest.update(
                {
                    "direction": br_direction,
                    "state": br_state,
                    "alignment_with_system": alignment(br_direction),
                    "level": round(float(level), 8) if level else None,
                    "level_type": level_type,
                    "tolerance_pct": round(tolerance, 4),
                    "volume_ratio_observed": round(
                        float(volume.get("volume_ratio", 1.0) or 1.0),
                        4,
                    ),
                }
            )

        result["strategies"]["breakout_retest"] = retest
        return result

    except Exception as exc:
        result["eligible"] = False
        result["reason"] = f"Q7_SHADOW_ERROR:{type(exc).__name__}"
        result["error"] = str(exc)[:180]
        return result
