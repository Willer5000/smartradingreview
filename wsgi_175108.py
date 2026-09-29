"""WSGI bootstrap for Commit 17.5.10.8.

Import app.py completely first, then install late runtime hooks. This avoids the
partial-import timing problem that 17.5.10.7 was specifically designed to fix.
"""
import app as app_module
from runtime_175108 import install_commit_175108, verify_supabase_target, VERSION

_state = install_commit_175108(app_module)

_required = (
    "base_175107_installed",
    "direction_preservation_installed",
    "futures_diagnostics_installed",
    "intrabar_diagnostics_installed",
    "multiasset_diagnostics_installed",
    "frontend_runtime_injection_installed",
)
_missing = [key for key in _required if not _state.get(key)]
if _missing:
    raise RuntimeError(
        "Commit 17.5.10.8 bootstrap incompleto: " + ", ".join(_missing)
    )

_supabase = verify_supabase_target()
if (
    _supabase.get("configured")
    and _supabase.get("matches_expected") is False
):
    raise RuntimeError(
        "SUPABASE_URL apunta a un proyecto distinto del autorizado: "
        + str(_supabase.get("project_ref") or "UNKNOWN")
    )

print(
    "✅ [17.5.10.8] Bootstrap listo · "
    f"diagnóstico direccional={_state.get('futures_diagnostics_installed')} · "
    f"Multi={_state.get('multiasset_diagnostics_installed')} · "
    f"Supabase={_supabase.get('project_ref') or 'NO_CONFIG'}",
    flush=True,
)

app = app_module.app
