"""Commit 19.2.3 — Candle Close Authority & Telegram Confirmation Timing.

Preserves Commit 19.2.2 runtime/scheduler recovery and all trading-quality
thresholds. Adds exact UTC candle-close authority, Monday-anchored 1W candles,
per-timeframe Spot close watermarks, and fresh-close-only Telegram confirmations
for Spot/Futures/Multi-Asset.
"""
from commit19_1_runtime import install_pre_app, install_post_app
_PRE = install_pre_app()
from app import app  # noqa: E402
_POST = install_post_app()
