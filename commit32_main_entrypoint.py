"""Commit 32 final authoritative WSGI entrypoint."""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app
import app as _app_module

from commit32_execution_policy import TEMPO_OVERRIDES, VERSION as TEMPO_VERSION
from commit32_runtime_patch import PUBLICATION_POLICY_VERSION, VERSION, install
from commit32_spot_market_authority import VERSION as SPOT_VERSION


def _assert_file_mentions(path: str, needle: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"Commit32 boot guard: {path} does not point to {needle}")


def _boot_guard() -> None:
    _assert_file_mentions("Procfile", "commit32_main_entrypoint:app")
    _assert_file_mentions("render.yaml", "commit32_main_entrypoint:app")

    futures_module = _app_module._configured_futures_module()
    sig = inspect.signature(futures_module.FuturesAnalysis.calculate_entry_levels)
    if "execution_observations" not in sig.parameters:
        raise RuntimeError("Commit32 boot guard: Futures ABI lost execution_observations")

    import safety_profiles_commit31 as sp31
    audit = sp31.audit()
    if audit.get("profile_count") != 8:
        raise RuntimeError("Commit32 boot guard: expected exactly 8 Commit31 Safety profiles")
    if audit.get("universal_score_threshold") is not None:
        raise RuntimeError("Commit32 boot guard: universal Safety threshold reintroduced")
    if not audit.get("highest_score_selection_forbidden"):
        raise RuntimeError("Commit32 boot guard: Safety score-shopping enabled")

    if not (TEMPO_OVERRIDES["HIGH"]["max_entry_wait_bars"] < TEMPO_OVERRIDES["MEDIUM"]["max_entry_wait_bars"] < TEMPO_OVERRIDES["CORE1"]["max_entry_wait_bars"]):
        raise RuntimeError("Commit32 boot guard: Futures execution tempo ordering invalid")


_boot_guard()
_installation = install(_app_module)

app.config["COMMIT32_VERSION"] = VERSION
app.config["COMMIT32_PUBLICATION_POLICY"] = PUBLICATION_POLICY_VERSION
app.config["COMMIT32_SPOT_MARKET_SIGNAL_AUTHORITY"] = SPOT_VERSION
app.config["COMMIT32_EXECUTION_TEMPO"] = TEMPO_VERSION
app.config["COMMIT32_GUARDIAN_UNTOUCHED"] = True

print(f"[COMMIT32] Authoritative entrypoint: {VERSION}")
print(f"[COMMIT32] Publication snapshot policy: {PUBLICATION_POLICY_VERSION}")
print(f"[COMMIT32] SPOT global market signal authority: {SPOT_VERSION}")
print("[COMMIT32] Portfolio Guardian remains independent per user/timeframe")
print(f"[COMMIT32] Futures/Multi execution tempo: {TEMPO_VERSION}; Safety/OOS/RR unchanged")
print("[COMMIT32] RAM: heavy serialization + structure.df compaction + staged checkpoints active")
