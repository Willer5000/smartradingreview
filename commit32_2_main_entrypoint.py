"""Commit 32.2 authoritative WSGI entrypoint."""
from __future__ import annotations

import inspect
import os
from pathlib import Path

# Set authoritative memory/runtime intent BEFORE importing app. Legacy overlays
# may initialize during app import, so the environment must already carry the
# final limits even before runtime monkeypatches are installed.
os.environ["MEMORY_JOB_START_LIMIT_MB"] = "240"
os.environ["MEMORY_SOFT_LIMIT_MB"] = "280"
os.environ["MEMORY_HARD_LIMIT_MB"] = "350"
os.environ["MEMORY_IN_JOB_ABORT_MB"] = "335"
os.environ["COMMIT32_1_JOB_START_MB"] = "240"
os.environ["COMMIT32_1_MEMORY_SOFT_MB"] = "280"
os.environ["COMMIT32_1_MEMORY_HARD_MB"] = "350"
os.environ["COMMIT32_1_RAM_SHED_MB"] = "285"
os.environ["COMMIT32_1_RAM_ABORT_MB"] = "335"
os.environ["COMMIT32_2_EXPECTED_ENTRYPOINT"] = "commit32_2_main_entrypoint:app"

from app import app
import app as _app_module
from commit32_runtime_patch import install as install_commit32
from commit32_1_runtime_patch import install as install_commit32_1
from commit32_2_runtime_patch import VERSION, PUBLICATION_POLICY_VERSION, install as install_commit32_2


def _assert_file_mentions(path: str, needle: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"Commit32.2 boot guard: {path} does not point to {needle}")


def _boot_guard() -> None:
    _assert_file_mentions("Procfile", "commit32_2_main_entrypoint:app")
    _assert_file_mentions("render.yaml", "commit32_2_main_entrypoint:app")
    import futures_system as fut
    import multiasset_system as multi
    for fn, label in ((fut.FuturesAnalysis.calculate_entry_levels, "Futures"), (multi.MultiAssetAnalysis.calculate_entry_levels, "Multi")):
        sig = inspect.signature(fn)
        if "execution_observations" not in sig.parameters and not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            raise RuntimeError(f"Commit32.2 boot guard: {label} ABI missing execution_observations")
    if getattr(_app_module, "_COMMIT245_NATIVE_Q_VERSION", None) != PUBLICATION_POLICY_VERSION:
        raise RuntimeError("Commit32.2 boot guard: publication snapshot version is not authoritative")

_install32 = install_commit32(_app_module)
_install321 = install_commit32_1(_app_module)
_install322 = install_commit32_2(_app_module)
_boot_guard()

app.config["COMMIT32_2_VERSION"] = VERSION
app.config["COMMIT32_2_PUBLICATION_POLICY"] = PUBLICATION_POLICY_VERSION
app.config["COMMIT32_2_GUARDIAN_UNTOUCHED"] = True
print(f"[COMMIT32.2] AUTHORITATIVE ENTRYPOINT {VERSION}")
print("[COMMIT32.2] ABI hardening active: Futures + Multi + live singleton path")
print("[COMMIT32.2] Legacy Safety>=75 reason codes forbidden in current publication policy")
print("[COMMIT32.2] New strategy LIVE authority requires reproducible profitable IS/OOS evidence")
print("[COMMIT32.2] Eight consecutive resolved LIVE losses => SHADOW")
