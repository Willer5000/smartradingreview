from __future__ import annotations
import os
import requests
from flask import Blueprint, jsonify, render_template, Response

_bp = Blueprint('research_federation_bridge', __name__)
_session = requests.Session()

def _cfg():
    return str(os.getenv('SUPABASE_URL','')).rstrip('/'), str(os.getenv('SUPABASE_KEY','')).strip()

def _get(table, params):
    url,key=_cfg()
    if not url or not key: raise RuntimeError('Supabase no configurado')
    h={'apikey':key,'Authorization':f'Bearer {key}','Accept':'application/json'}
    r=_session.get(f'{url}/rest/v1/{table}',params=params,headers=h,timeout=10)
    r.raise_for_status(); data=r.json(); return data if isinstance(data,list) else []

def _auth_guard(auth_fn): return auth_fn()

def _compact():
    candidates=_get('research_analytics_compact_v1',{'select':'*','order':'updated_at.desc','limit':'120'})
    states=_get('research_engine_state_v1',{'select':'engine,status,last_seen_at,rss_mb,research_version,meta','order':'engine.asc','limit':'10'})
    shadow=_get('research_shadow_live_metrics_v1',{'select':'*','order':'updated_at.desc','limit':'120'})
    return candidates,states,shadow

def _report(candidates,states,shadow):
    lines=['# Research Federation · sistema central','','- Bridge V1.2: evidencia externa + Shadow central observado.','- Nunca concede autoridad productiva automáticamente.','','## Motores']
    for s in states: lines.append(f"- {s.get('engine')}: {s.get('status')} · RSS {s.get('rss_mb')} MB · {s.get('last_seen_at')}")
    lines += ['','## Evidencia Backtest/OOS']
    for x in candidates[:35]:
        lines.append(f"- {x.get('stage')} | {x.get('source_engine')} | {x.get('experiment')} | {x.get('market_family')} {x.get('timeframe')} | N={x.get('backtest_n')} | WR={x.get('backtest_wr')}% | Exp.R={x.get('backtest_exp_r')} | OOS.N={x.get('oos_n')} | OOS.WR={x.get('oos_wr')}% | OOS.Exp.R={x.get('oos_exp_r')} | PF={x.get('oos_pf')}")
    lines += ['','## Shadow central live']
    for x in shadow[:35]:
        lines.append(f"- {x.get('research_stage')} | {x.get('source_engine')} | {x.get('experiment')} | {x.get('market_family')} {x.get('symbol')} {x.get('timeframe')} | señales={x.get('signals_n')} | resueltas={x.get('resolved_n')} | WR={x.get('win_rate_pct')}% | Exp.R={x.get('expectancy_r')} | PF={x.get('profit_factor')} | PnL={x.get('pnl_pct_sum')}% | Safety={x.get('avg_safety')}")
    return '\n'.join(lines)

def register_research_bridge(app, auth_fn):
    @_bp.get('/research-federation')
    def page():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str): return user
        return render_template('research_federation.html')
    @_bp.get('/api/research-federation/summary')
    def summary():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str): return user
        try:
            c,s,l=_compact(); return jsonify({'success':True,'candidates':c,'engines':s,'shadow_live':l,'authority':'RESEARCH_SHADOW_BRIDGE_V1_2'})
        except Exception as exc: return jsonify({'success':False,'error':str(exc)[:240]}),500
    @_bp.get('/api/research-federation/export')
    def export():
        user=_auth_guard(auth_fn)
        if not isinstance(user,str): return user
        try:
            c,s,l=_compact(); return Response(_report(c,s,l),mimetype='text/markdown; charset=utf-8')
        except Exception as exc: return Response(f'# Error\n\n{exc}',status=500,mimetype='text/plain; charset=utf-8')
    app.register_blueprint(_bp)
