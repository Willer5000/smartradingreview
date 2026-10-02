"""Commit 19.1 runtime overlay — Champions + native LIVE Quant Synthesis."""
from __future__ import annotations
import sys
from typing import Any, Dict

VERSION="COMMIT19_2_QUALITY_SIGNAL_RECOVERY_V1"
_ORIGINALS: Dict[str,Any]={}

def _u(v): return str(v or "").strip().upper().replace("/","-")

def _install_contingency_passthrough():
    import contingency_strategy_engine as cse
    if getattr(cse,"_COMMIT19_1_INSTALLED",False): return {"installed":True,"already":True}
    original=cse.build_contingency_playbook; _ORIGINALS["contingency"]=original
    def wrapped(*args,**kwargs):
        out=dict(original(*args,**kwargs) or {})
        layers=kwargs.get("layers") or (args[0] if args and isinstance(args[0],dict) else {})
        op=dict((layers or {}).get("operational_intelligence") or {})
        synth=dict(op.get("live_quant_synthesis") or {})
        if synth.get("authority")!="LIVE_QUANT_SYNTHESIS_COMMIT19_1" or not synth.get("eligible_for_execution_routing"):
            return out
        # Do not run a second generic contingency permission layer.  The
        # synthesis candidate already passed its desk/pattern/context contract;
        # downstream Entry/SL/TP, R/R, Safety and leverage remain untouched.
        out.update({
            "active":False,
            "authority":"LIVE_QUANT_SYNTHESIS_COMMIT19_1",
            "reason":"QUANT_SYNTHESIS_OWNS_CANDIDATE",
            "reason_code":"QUANT_SYNTHESIS_OWNS_CANDIDATE",
            "effective_action":synth.get("action"),
            "direction":synth.get("direction"),
            "strategy":synth.get("synthesis_id"),
            "setup_family":synth.get("setup_family"),
            "strategy_quality":synth.get("synthesis_quality"),
            "candidate_source":"C19_1_LIVE_QUANT_SYNTHESIS",
            "live_synthesis_passthrough":True,
            "downgrade_reason":"",
        })
        return out
    cse.build_contingency_playbook=wrapped; cse._COMMIT19_1_INSTALLED=True
    return {"installed":True,"already":False}

def install_pre_app():
    from commit19_runtime import install_pre_app as base_install
    base=base_install(); contingency=_install_contingency_passthrough()
    return {"version":VERSION,"base19":base,"contingency":contingency}

def _install_moderator_synthesis():
    app_mod=sys.modules.get("app")
    cls=getattr(app_mod,"Moderador",None) if app_mod else None
    if cls is None: return {"installed":False,"reason":"MODERATOR_NOT_FOUND"}
    original=getattr(cls,"procesar_votacion",None)
    if not callable(original): return {"installed":False,"reason":"METHOD_NOT_FOUND"}
    if getattr(original,"_commit19_1",False): return {"installed":True,"already":True}
    _ORIGINALS["moderator"]=original
    def procesar(self,capas,symbol,timeframe):
        result=original(self,capas,symbol,timeframe)
        try:
            action,confidence,strategies,reasons,record=result
        except Exception:
            return result
        if _u(action) in {"LONG","SHORT","COMPRA_SPOT","VENTA_SPOT"}:
            return result
        try:
            from live_quant_synthesis_commit19_1 import synthesize_live_candidate
            synth=synthesize_live_candidate(capas=capas,vote_record=record or {},symbol=symbol,timeframe=timeframe,system_type=(capas or {}).get("system_type"),review_trader=getattr(self,"_review_trader",None))
            if not synth.get("use"):
                if isinstance(record,dict): record["live_quant_synthesis"]={**synth,"authority":"NO_LIVE_AUTHORITY"}
                return action,confidence,strategies,reasons,record
            from synthesis_decay_commit19_1 import get_decay_state
            decay=get_decay_state(synthesis_id=str(synth.get("synthesis_id")),decay_key=str(synth.get("decay_key")),research_handoff_key=str(synth.get("research_handoff_key")))
            synth["alpha_decay"]=decay
            if decay.get("state")!="LIVE_SYNTHESIS":
                synth.update({"eligible_for_execution_routing":False,"use":False,"reason":"SYNTHESIS_ALPHA_DECAY_RESEARCH_HANDOFF"})
                if isinstance(record,dict): record["live_quant_synthesis"]=synth
                return action,confidence,strategies,reasons,record
            synth["eligible_for_execution_routing"]=True
            op=dict((capas or {}).get("operational_intelligence") or {})
            op.update({
                "candidate_action":synth.get("action"),
                "candidate_ready":True,
                "candidate_source":"C19_1_LIVE_QUANT_SYNTHESIS",
                "selected_specialist_source":"NATIVE_QUANT_SYNTHESIS",
                "research_blocks_selected_action":False,
                "coverage_route_state":"LIVE_QUANT_SYNTHESIS",
                "live_quant_synthesis":synth,
            })
            strategy=dict(op.get("default_strategy") or {})
            strategy.update({
                "id":synth.get("synthesis_id"),"family":synth.get("setup_family"),
                "quality":synth.get("synthesis_quality"),"regime_match":True,"volatility_match":True,
                "live_quant_synthesis":True,
            })
            op["default_strategy"]=strategy
            evidence=dict(op.get("decision_evidence") or {})
            evidence.update({"candidate_source":"C19_1_LIVE_QUANT_SYNTHESIS","live_quant_synthesis":True,"synthesis_id":synth.get("synthesis_id"),"setup_family":synth.get("setup_family")})
            op["decision_evidence"]=evidence
            if isinstance(capas,dict): capas["operational_intelligence"]=op
            if isinstance(record,dict):
                record.update({"accion_ganadora":synth.get("action"),"confianza_final":synth.get("confidence"),"live_quant_synthesis":synth})
            synth_strategies=list(strategies or [])
            if synth.get("setup_family") and synth.get("setup_family") not in synth_strategies: synth_strategies.append(str(synth.get("setup_family")))
            return str(synth.get("action")),float(synth.get("confidence") or 0),synth_strategies,list(synth.get("public_reasons") or reasons or []),record
        except Exception as exc:
            if isinstance(record,dict): record["live_quant_synthesis"]={"use":False,"authority":"NO_LIVE_AUTHORITY","reason":f"SYNTHESIS_RUNTIME_ERROR:{type(exc).__name__}","error":str(exc)[:160]}
            return action,confidence,strategies,reasons,record
    procesar._commit19_1=True; cls.procesar_votacion=procesar
    return {"installed":True,"already":False}

def _install_execution_quality_overlay():
    app_mod=sys.modules.get("app"); cls=getattr(app_mod,"TradingExpertSystem",None) if app_mod else None
    original=getattr(cls,"calculate_entry_levels",None) if cls else None
    if not callable(original): return {"installed":False,"reason":"LEVEL_METHOD_NOT_FOUND"}
    if getattr(original,"_commit19_1",False): return {"installed":True,"already":True}
    _ORIGINALS["levels"]=original
    def wrapped(self,decision,trend,momentum,volatility,structure,symbol,timeframe,liquidation=None,execution_observations=None):
        levels=original(self,decision,trend,momentum,volatility,structure,symbol,timeframe,liquidation=liquidation,execution_observations=execution_observations)
        if not isinstance(levels,dict): return levels
        try:
            op=dict((execution_observations or {}).get("operational_intelligence") or {}) if isinstance(execution_observations,dict) else {}
            synth=dict(op.get("live_quant_synthesis") or {})

            # Commit 19.2 QUALITY RECOVERY — score the exact geometry that will
            # reach Futures/Multi publication.  This fixes a state mismatch in
            # which committees or the Champion overlay changed Entry/SL/TP but
            # Safety still consumed scores belonging to the old baseline.  No
            # threshold is lowered and no price is changed here.
            _action=_u(decision)
            _should_rescore=bool(
                _action in {"LONG","SHORT"}
                and (
                    levels.get("execution_refinement_applied")
                    or levels.get("structural_recovery_applied")
                    or levels.get("commit19_geometry_parity")
                    or (synth.get("authority")=="LIVE_QUANT_SYNTHESIS_COMMIT19_1" and synth.get("eligible_for_execution_routing"))
                )
            )
            if _should_rescore:
                try:
                    from execution_specialist_committees import build_execution_context, score_execution_geometry
                    _market="futures"
                    try:
                        from multiasset_system import MULTIASSET_SYMBOLS
                        if str(symbol or "").upper() in set(MULTIASSET_SYMBOLS or {}): _market="multiasset"
                    except Exception:
                        pass
                    _obs=execution_observations if isinstance(execution_observations,dict) else {}
                    _current=float((structure or {}).get("current_price") or _obs.get("current_price") or 0)
                    _atr=float((volatility or {}).get("atr") or 0)
                    _mm=dict(levels.get("market_maker_context") or {}) if isinstance(levels.get("market_maker_context"),dict) else {}
                    _ctx=build_execution_context(
                        structure=structure, volume=_obs.get("volume") or (structure or {}).get("volume_analysis") or {},
                        volatility=volatility, market_hours=_obs.get("market_hours") or {},
                        sentiment=_obs.get("sentiment") or {}, macro_context=_obs.get("macro_context") or {},
                        market_regime=_obs.get("market_regime") or {}, market_maker_context=_mm,
                        symbol=symbol, timeframe=timeframe, market_type=_market,
                    )
                    _family=str(synth.get("setup_family") or ((op.get("default_strategy") or {}).get("family")) or "UNSPECIFIED")
                    _scored=score_execution_geometry(
                        entry=float(levels.get("entry") or 0), stop_loss=float(levels.get("stop_loss") or 0),
                        take_profit=float(levels.get("take_profit") or 0), direction="long" if _action=="LONG" else "short",
                        current_price=_current, atr=_atr, structure=structure, trend=trend, momentum=momentum,
                        volatility=volatility, setup_family=_family, liquidation=liquidation, market_type=_market,
                        symbol=symbol, timeframe=timeframe, execution_context=_ctx,
                        rr_floor=float(levels.get("minimum_viable_rr") or 1.8),
                        rr_ceiling=float(levels.get("maximum_technical_rr") or 4.5),
                        leverage_hint=float(levels.get("leverage") or 1.0),
                    ) or {}
                    if _scored.get("success"):
                        levels["entry_score"]=round(float(_scored.get("entry_quality") or 0),1)
                        levels["entry_quality_score"]=round(float(_scored.get("entry_quality") or 0),1)
                        levels["sl_reliability"]=round(float(_scored.get("sl_quality") or 0)/100.0,2)
                        levels["tp_quality_score"]=round(float(_scored.get("tp_quality") or 0),1)
                        levels["execution_geometry_quality"]=round(float(_scored.get("geometry_quality") or 0),2)
                        levels["final_geometry_quality_rescored"]=True
                        levels["final_geometry_quality_version"]="COMMIT19_2_FINAL_GEOMETRY_SCORE_V1"
                        levels["final_geometry_quality_authority"]="MEASURE_ACTUAL_GEOMETRY_NO_THRESHOLD_CHANGE"
                    else:
                        levels["final_geometry_quality_rescored"]=False
                        levels["final_geometry_quality_reason"]=_scored.get("reason")
                except Exception as _rescore_error:
                    levels["final_geometry_quality_rescored"]=False
                    levels["final_geometry_quality_reason"]=f"RESCORE_FAIL_OPEN:{type(_rescore_error).__name__}"
            if synth.get("authority")!="LIVE_QUANT_SYNTHESIS_COMMIT19_1" or not synth.get("eligible_for_execution_routing"):
                return levels
            levels["live_quant_synthesis_id"]=synth.get("synthesis_id")
            levels["live_quant_setup_family"]=synth.get("setup_family")
            levels["live_quant_synthesis_quality"]=synth.get("synthesis_quality")
            levels["live_quant_alpha_decay_state"]=(synth.get("alpha_decay") or {}).get("state")
            # Quality lane: geometry committees must find a genuinely defendible
            # Entry, SL and TP.  These are additional quality requirements; Safety
            # and the existing technical R/R floors remain unchanged.
            entry_q=float(levels.get("entry_quality_score") or levels.get("entry_score") or 0)
            tp_q=float(levels.get("tp_quality_score") or 0)
            sl_rel=float(levels.get("sl_reliability") or 0)*100.0
            reasons=[]
            if entry_q<65.0: reasons.append(f"Entry quality {entry_q:.0f}/100 < 65")
            if sl_rel<60.0: reasons.append(f"SL reliability {sl_rel:.0f}/100 < 60")
            if tp_q<60.0: reasons.append(f"TP quality {tp_q:.0f}/100 < 60")
            if reasons:
                levels["is_rejected"]=True; levels["is_executable"]=False; levels["publication_status"]="ANALYSIS_ONLY"; levels["suggested_size"]=0
                prior=str(levels.get("rejected_reason") or "").strip()
                levels["rejected_reason"]=(prior+"; " if prior else "")+"; ".join(reasons)
                levels["live_quant_quality_gate_passed"]=False
            else:
                levels["live_quant_quality_gate_passed"]=True
            return levels
        except Exception as exc:
            levels["live_quant_quality_gate_passed"]=False; levels["live_quant_quality_error"]=type(exc).__name__
            return levels
    wrapped._commit19_1=True; cls.calculate_entry_levels=wrapped
    return {"installed":True,"already":False,"entry_quality_min":65,"sl_reliability_min":60,"tp_quality_min":60}

def _install_review_tags():
    try:
        import review_trader as rt
        cls=getattr(rt,"ReviewTrader",None)
        if cls is None:
            obj=getattr(rt,"review_trader",None); cls=obj.__class__ if obj is not None else None
        if cls is None: return {"installed":False,"reason":"REVIEW_CLASS_NOT_FOUND"}
        orig_s=getattr(cls,"_extract_strategies",None); orig_c=getattr(cls,"_extract_context",None)
        if callable(orig_s) and not getattr(orig_s,"_commit19_1",False):
            _ORIGINALS["review_strategies"]=orig_s
            def exs(self,analysis):
                rows=set(orig_s(self,analysis) or [])
                synth=dict(((analysis or {}).get("operational_intelligence") or {}).get("live_quant_synthesis") or {})
                if synth.get("authority")=="LIVE_QUANT_SYNTHESIS_COMMIT19_1" and synth.get("eligible_for_execution_routing"):
                    sid=str(synth.get("synthesis_id") or "").upper(); key=str(synth.get("decay_key") or "").upper()
                    if sid: rows.add(f"C19SYNTH::{sid}")
                    if key: rows.add(f"C19SYNTHCELL::{key}")
                return sorted(rows)
            exs._commit19_1=True; cls._extract_strategies=exs
        if callable(orig_c) and not getattr(orig_c,"_commit19_1",False):
            _ORIGINALS["review_context"]=orig_c
            def exc(self,analysis):
                out=dict(orig_c(self,analysis) or {})
                synth=dict(((analysis or {}).get("operational_intelligence") or {}).get("live_quant_synthesis") or {})
                if synth.get("authority")=="LIVE_QUANT_SYNTHESIS_COMMIT19_1":
                    out["commit19_1_live_quant_synthesis"]={"synthesis_id":str(synth.get("synthesis_id") or "")[:160],"decay_key":str(synth.get("decay_key") or "")[:240],"setup_family":str(synth.get("setup_family") or "")[:80],"synthesis_quality":synth.get("synthesis_quality"),"alpha_decay_state":str((synth.get("alpha_decay") or {}).get("state") or "")[:40]}
                return out
            exc._commit19_1=True; cls._extract_context=exc
        return {"installed":True,"new_schema":False,"extra_writes":0}
    except Exception as exc:
        return {"installed":False,"error":str(exc)[:160]}

def install_post_app():
    from commit19_runtime import install_post_app as base_install
    base=base_install(); moderator=_install_moderator_synthesis(); levels=_install_execution_quality_overlay(); review=_install_review_tags()
    return {"version":VERSION,"base19":base,"moderator":moderator,"execution_quality":levels,"review":review}

def audit():
    return {"version":VERSION,"base":"COMMIT19_CHAMPION_EDGE_EXECUTION_V1","live_lanes":["PROFITABLE_CHAMPION","NATIVE_QUANT_SYNTHESIS"],"majority_vote_restored":False,"changes_safety_thresholds":False,"changes_rr_floor":False,"changes_leverage_v6":False,"adds_llm_calls":False,"adds_background_threads":False,"adds_market_data_requests":"BOUNDED_DIRECT_BTC_ETH_OPTIONS_ONLY","adds_schema":False,"alpha_decay":"8 LIVE losses per synthesis fingerprint -> SHADOW/Research; 8 Shadow -> RETIRED","greeks_execution":"observed-chain confluence ranker only; theoretical surfaces UI/context only","resource_contract":"1 worker/2 threads; provider <=12 MB/day; no polling"}
