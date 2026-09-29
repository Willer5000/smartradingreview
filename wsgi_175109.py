"""WSGI bootstrap for Commit 17.5.10.9."""
import app as app_module
from runtime_175109 import install_commit_175109, verify_supabase_target

_state = install_commit_175109(app_module)
_required = (
    "base_175108_installed",
    "diagnostic_direction_bridge_installed",
    "futures_diagnostic_enrichment_installed",
    "multiasset_response_bridge_installed",
    "multiasset_lane_truth_installed",
    "frontend_runtime_injection_installed",
)
_missing = [key for key in _required if not _state.get(key)]
if _missing:
    raise RuntimeError("Commit 17.5.10.9 bootstrap incompleto: " + ", ".join(_missing))

_supabase = verify_supabase_target()
if _supabase.get("configured") and _supabase.get("matches_expected") is False:
    raise RuntimeError(
        "SUPABASE_URL apunta a un proyecto distinto del autorizado: "
        + str(_supabase.get("project_ref") or "UNKNOWN")
    )

print(
    "✅ [17.5.10.9] Bootstrap listo · "
    f"direction={_state.get('diagnostic_direction_bridge_installed')} · "
    f"futures_diag={_state.get('futures_diagnostic_enrichment_installed')} · "
    f"multi_render={_state.get('multiasset_response_bridge_installed')} · "
    f"multi_lanes={_state.get('multiasset_lane_truth_installed')} · "
    f"Supabase={_supabase.get('project_ref') or 'NO_CONFIG'}",
    flush=True,
)

app = app_module.app
