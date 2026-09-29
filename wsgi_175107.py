"""Commit 17.5.10.7 bootstrap.

Imports the existing Flask application first, then installs the 17.5.10.6 ABI
and the 17.5.10.7 repair only after app.py has finished defining every route and
helper.  This guarantees that cache-only reads and the Multi-Asset nonblocking
route are active before Gunicorn serves the first request.

No worker/thread/LLM/market-data source is added here.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from app import app

EXPECTED_SUPABASE_PROJECT_REF = "frganummqwzzsukdefqd"


def _supabase_project_ref() -> str:
    raw = str(
        os.environ.get("CENTRAL_SUPABASE_URL")
        or os.environ.get("SUPABASE_URL")
        or ""
    ).strip()
    try:
        host = urlparse(raw).hostname or ""
        if host.endswith(".supabase.co"):
            return host.split(".", 1)[0]
    except Exception:
        pass
    return ""


def _install_commit_175107() -> None:
    import futures_system
    from execution_abi_175104 import install_futures_execution_abi_175104
    from strategy_quality_extension_175105 import (
        install_strategy_quality_extension_175105,
        VERSION as REPAIR_VERSION,
    )

    # First preserve/install the existing 17.5.10.6 ABI. The extension is
    # already part of that ABI, but a second idempotent call gives us its exact
    # state after app.py is fully imported.
    install_futures_execution_abi_175104(futures_system)
    state = install_strategy_quality_extension_175105()

    critical = (
        "strategy_scope_installed",
        "invalidation_corridor_installed",
        "cache_only_reads_installed",
        "multiasset_nonblocking_ui_installed",
        "risk_profile_bounded_read_installed",
        "leverage_visibility_consistency_installed",
    )
    missing = [name for name in critical if not bool(state.get(name))]
    if missing:
        raise RuntimeError(
            "Commit 17.5.10.7 incompleto; hooks no instalados: "
            + ", ".join(missing)
        )

    actual_ref = _supabase_project_ref()
    if actual_ref and actual_ref != EXPECTED_SUPABASE_PROJECT_REF:
        print(
            "⚠️ [17.5.10.7] SUPABASE_URL apunta a project ref "
            f"{actual_ref}; el proyecto real informado es "
            f"{EXPECTED_SUPABASE_PROJECT_REF}. Revisar variables de Render.",
            flush=True,
        )
    elif actual_ref == EXPECTED_SUPABASE_PROJECT_REF:
        print(
            f"✅ [17.5.10.7] Supabase target verificado: {actual_ref}",
            flush=True,
        )
    else:
        print(
            "⚠️ [17.5.10.7] No se pudo leer el project ref de Supabase desde "
            "CENTRAL_SUPABASE_URL/SUPABASE_URL. No se modifica ninguna URL/clave.",
            flush=True,
        )

    app.config["SMARTRADINGREVIEW_RUNTIME_REPAIR"] = {
        "version": REPAIR_VERSION,
        "state": dict(state),
        "supabase_project_ref": actual_ref or None,
        "expected_supabase_project_ref": EXPECTED_SUPABASE_PROJECT_REF,
    }
    print(
        "✅ [17.5.10.7] Invalidation Corridor + runtime no bloqueante instalado",
        flush=True,
    )


_install_commit_175107()
