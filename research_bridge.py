from __future__ import annotations
import os
import requests
from flask import Blueprint, jsonify, render_template, Response

_bp = Blueprint("research_federation_bridge", __name__)
_session = requests.Session()


def _cfg():
    return str(os.getenv("SUPABASE_URL", "")).rstrip("/"), str(os.getenv("SUPABASE_KEY", "")).strip()


def _get(table, params):
    url, key = _cfg()
    if not url or not key:
        raise RuntimeError("Supabase no configurado")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    r = _session.get(f"{url}/rest/v1/{table}", params=params, headers=headers, timeout=12)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def _auth_guard(auth_fn):
    return auth_fn()


def _compact():
    candidates = _get(
        "research_bridge_candidates_v1",
        {
            "select": "candidate_key,source_engine,experiment,stage,reason,scope,metrics,meta,research_version,updated_at",
            "order": "updated_at.desc",
            "limit": "100",
        },
    )
    states = _get(
        "research_engine_state_v1",
        {
            "select": "engine,status,last_seen_at,rss_mb,research_version,meta",
            "order": "engine.asc",
            "limit": "10",
        },
    )
    return candidates, states


def _report(candidates, states):
    lines = [
        "# Research Federation · sistema central",
        "",
        "- Sólo lectura: el sistema central no ejecuta backtests.",
        "- Ningún candidato tiene autoridad de producción automática.",
        "",
        "## Motores",
    ]
    for state in states:
        lines.append(
            f"- {state.get('engine')}: {state.get('status')} · RSS {state.get('rss_mb')} MB · visto {state.get('last_seen_at')}"
        )
    lines += ["", "## Candidatos"]
    for candidate in candidates[:30]:
        metrics = candidate.get("metrics") or {}
        allm = metrics.get("all") or {}
        val = metrics.get("validation") or {}
        meta = candidate.get("meta") or {}
        scope = ", ".join(f"{k}={v}" for k, v in (candidate.get("scope") or {}).items())
        lines.append(
            f"- {candidate.get('stage')} | {candidate.get('source_engine')} | {candidate.get('experiment')} | "
            f"{scope} | N={allm.get('resolved')} | Exp.R={allm.get('expectancy_r')} | "
            f"OOS.N={val.get('resolved')} | OOS.Exp.R={val.get('expectancy_r')} | "
            f"PF.OOS={val.get('profit_factor')} | Shadow recomendado={meta.get('recommended_shadow_target')}"
        )
    return "\n".join(lines)


def register_research_bridge(app, auth_fn):
    @_bp.get("/research-federation")
    def page():
        user = _auth_guard(auth_fn)
        if not isinstance(user, str):
            return user
        return render_template("research_federation.html")

    @_bp.get("/api/research-federation/summary")
    def summary():
        user = _auth_guard(auth_fn)
        if not isinstance(user, str):
            return user
        try:
            candidates, states = _compact()
            return jsonify(
                {
                    "success": True,
                    "candidates": candidates,
                    "engines": states,
                    "authority": "READ_ONLY_BRIDGE",
                }
            )
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc)[:240]}), 500

    @_bp.get("/api/research-federation/export")
    def export():
        user = _auth_guard(auth_fn)
        if not isinstance(user, str):
            return user
        try:
            candidates, states = _compact()
            return Response(_report(candidates, states), mimetype="text/markdown; charset=utf-8")
        except Exception as exc:
            return Response(f"# Error\n\n{exc}", status=500, mimetype="text/plain; charset=utf-8")

    app.register_blueprint(_bp)
