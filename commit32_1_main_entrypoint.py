"""Commit 32.1 authoritative WSGI entrypoint."""
from __future__ import annotations

import inspect
from pathlib import Path

from app import app
import app as _app_module

# Reinstall Commit32 foundations without importing commit32_main_entrypoint,
# whose old boot guard correctly expects the old entrypoint string.
from commit32_runtime_patch import install as install_commit32
from commit32_1_runtime_patch import VERSION, PUBLICATION_POLICY_VERSION, install as install_commit32_1
from commit32_1_research_registry import assert_no_live_authority


def _assert_file_mentions(path: str, needle: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"Commit32.1 boot guard: {path} does not point to {needle}")


def _boot_guard() -> None:
    _assert_file_mentions("Procfile", "commit32_1_main_entrypoint:app")
    _assert_file_mentions("render.yaml", "commit32_1_main_entrypoint:app")

    import futures_system as fut
    import multiasset_system as multi
    if "execution_observations" not in inspect.signature(fut.FuturesAnalysis.calculate_entry_levels).parameters:
        raise RuntimeError("Commit32.1 boot guard: Futures ABI missing execution_observations")
    if "execution_observations" not in inspect.signature(multi.MultiAssetAnalysis.calculate_entry_levels).parameters:
        raise RuntimeError("Commit32.1 boot guard: Multi class ABI missing execution_observations")
    if "execution_observations" not in inspect.signature(multi.multiasset_system.calculate_entry_levels).parameters:
        raise RuntimeError("Commit32.1 boot guard: Multi singleton ABI missing execution_observations")

    import safety_profiles_commit31 as sp31
    audit = sp31.audit()
    if audit.get("profile_count") != 8 or audit.get("universal_score_threshold") is not None:
        raise RuntimeError("Commit32.1 boot guard: Commit31 specialised Safety contract changed")
    if not audit.get("highest_score_selection_forbidden"):
        raise RuntimeError("Commit32.1 boot guard: Safety score-shopping enabled")
    if not assert_no_live_authority():
        raise RuntimeError("Commit32.1 boot guard: research strategy has LIVE authority")


_install32 = install_commit32(_app_module)
_install321 = install_commit32_1(_app_module)
_boot_guard()

app.config["COMMIT32_1_VERSION"] = VERSION
app.config["COMMIT32_1_PUBLICATION_POLICY"] = PUBLICATION_POLICY_VERSION
app.config["COMMIT32_1_GUARDIAN_UNTOUCHED"] = True
app.config["COMMIT32_1_RESEARCH_LIVE_AUTHORITY"] = False

print(f"[COMMIT32.1] Authoritative entrypoint: {VERSION}")
print("[COMMIT32.1] Multi ABI: class + live singleton execution_observations guarded")
print("[COMMIT32.1] Visuals: OHLC-only lane independent of heavy analysis lock")
print("[COMMIT32.1] Candidate recovery: graded setup contracts; Safety/OOS unchanged")
print("[COMMIT32.1] CRT / Triple RSI / new techniques: SHADOW_ONLY pending IS/OOS")
print("[COMMIT32.1] Guardian remains independent per user/timeframe")
