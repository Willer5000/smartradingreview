from __future__ import annotations
import os, sys
ROOT=os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from live_quant_synthesis_commit19_1 import synthesize_live_candidate
from synthesis_decay_commit19_1 import evaluate_decay

class Review:
    def get_confidence_adjustment(self,*a,**k): return 1.0

def _worker(name,desk,direction,conf=78,strategies=None,notes=None):
    return {"worker":name,"desk":desk,"legacy_direction_hint":direction,"legacy_confidence":conf,"timeframe_emphasis":1.0,"strategies_observed":strategies or [],"work_notes":notes or []}

def _case(direction="BULLISH",symbol="BTC-USDT",tf="1H",risk="CORE1"):
    bull=direction
    action="LONG" if direction=="BULLISH" else "SHORT"
    trend="bullish" if direction=="BULLISH" else "bearish"
    plus,minus=(31,18) if direction=="BULLISH" else (18,31)
    workers=[
        _worker("Técnico Puro","SETUP",bull,82,["RSI Trend"]),
        _worker("Chartista","SETUP",bull,78,["Structure Retest"]),
        _worker("Pullback","EXECUTION",bull,80,["Pullback"]),
        _worker("Smart Money","EXECUTION",bull,84,["Order Block","Sweep MSS"]),
        _worker("El Liquidador","EXECUTION",bull,72,["Liquidity"]),
        _worker("Multiframe","CONTEXT",bull,80,["MTF"]),
        _worker("Cazador de Ballenas","CONTEXT",bull,68,["Volume"]),
        _worker("Macroeconomista","CONTEXT","NEUTRAL",60),
        _worker("Escéptico","CONTROL","NEUTRAL",65),
    ]
    capas={
        "system_type":"futures",
        "trend":{"direction":trend,"adx":27,"plus_di":plus,"minus_di":minus},
        "momentum":{"direction":trend,"rsi":56 if direction=="BULLISH" else 44,"macd_histogram":0.3 if direction=="BULLISH" else -0.3},
        "volume":{"volume_ratio":1.28,"obv_trend":trend},
        "volatility":{"atr_pct":1.5,"ftm_state":"NORMAL"},
        "structure":{"direction":trend,"order_blocks":[{"price":100}],"liquidity_sweep":True,"mss":True,"current_price":100},
        "macro_context":{"risk_level":"NORMAL"},
        "operational_intelligence":{
            "candidate_ready":False,"candidate_action":"NO_OPERAR","context":{"regime":"TREND_UP" if direction=="BULLISH" else "TREND_DOWN","volatility":"NORMAL"},
            "multi_timeframe":{"dominant_direction":direction,"alignment":"ALIGNED","conflict":False},
            "thesis":{"long_families":["trend","structure","momentum","volume"] if direction=="BULLISH" else [],"short_families":["trend","structure","momentum","volume"] if direction=="BEARISH" else [],"families":{},"quality":68},
            "default_strategy":{"id":"NO_PLAYBOOK","family":"NONE","quality":0},
        },
    }
    record={"worker_desk_17_5_9":{"workers":workers}}
    return capas,record

def main():
    checks={}
    c,r=_case("BULLISH"); x=synthesize_live_candidate(capas=c,vote_record=r,symbol="BTC-USDT",timeframe="1H",system_type="futures",review_trader=Review())
    checks["native_long_created"]=x.get("use") and x.get("action")=="LONG"
    c,r=_case("BEARISH"); x2=synthesize_live_candidate(capas=c,vote_record=r,symbol="SOL-USDT",timeframe="2H",system_type="futures",review_trader=Review())
    checks["native_short_created"]=x2.get("use") and x2.get("action")=="SHORT"
    c,r=_case("BULLISH"); c["operational_intelligence"]["multi_timeframe"]["conflict"]=True
    checks["mtf_conflict_blocks"]=not synthesize_live_candidate(capas=c,vote_record=r,symbol="BTC-USDT",timeframe="1H",system_type="futures",review_trader=Review()).get("use")
    c,r=_case("BULLISH"); c["macro_context"]["risk_level"]="CRITICAL"
    checks["critical_macro_blocks"]=not synthesize_live_candidate(capas=c,vote_record=r,symbol="BTC-USDT",timeframe="1H",system_type="futures",review_trader=Review()).get("use")
    c,r=_case("BULLISH")
    # Commit 19.2: a mere label count is no longer the anti-noise gate. Test a
    # genuinely single-indicator situation: no POI/sweep/MSS, no momentum, weak
    # ADX/volume, and specialist notes stripped of structural hints.
    c["operational_intelligence"]["thesis"]["long_families"]=["trend"]
    c["structure"]={"current_price":100}
    c["momentum"]={"direction":"neutral","rsi":50,"macd_histogram":0}
    c["volume"]={"volume_ratio":0.6}
    c["trend"]={"direction":"bullish","adx":12}
    for _w in r["worker_desk_17_5_9"]["workers"]:
        _w["strategies_observed"]=["RSI"]
        _w["work_notes"]=[]
    checks["single_indicator_not_enough"]=not synthesize_live_candidate(capas=c,vote_record=r,symbol="BTC-USDT",timeframe="1H",system_type="futures",review_trader=Review()).get("use")
    c,r=_case("BULLISH"); c["operational_intelligence"]["candidate_ready"]=True; c["operational_intelligence"]["candidate_action"]="LONG"
    checks["does_not_override_existing_candidate"]=not synthesize_live_candidate(capas=c,vote_record=r,symbol="BTC-USDT",timeframe="1H",system_type="futures",review_trader=Review()).get("use")
    checks["decay_7_live"]=evaluate_decay(live_consecutive_losses=7)=="LIVE_SYNTHESIS"
    checks["decay_8_live"]=evaluate_decay(live_consecutive_losses=8)=="SHADOW_DECAY"
    checks["decay_8_shadow"]=evaluate_decay(live_consecutive_losses=8,shadow_consecutive_losses=8)=="RETIRED_ALPHA_DECAY"
    rt=open(os.path.join(ROOT,"commit19_1_runtime.py"),encoding="utf-8").read()
    checks["safety_not_modified"]='changes_safety_thresholds":False' in rt
    checks["rr_not_modified"]='changes_rr_floor":False' in rt
    checks["no_llm_threads_bounded_market_requests"]=all(s in rt for s in ['adds_llm_calls":False','adds_background_threads":False']) and 'adds_market_data_requests":"BOUNDED_DIRECT_BTC_ETH_OPTIONS_ONLY"' in rt
    checks["review_tags"]='C19SYNTH::' in rt and 'C19SYNTHCELL::' in rt
    failed=[k for k,v in checks.items() if not v]
    for k,v in checks.items(): print(("PASS" if v else "FAIL"),k)
    print(f"SUMMARY {len(checks)-len(failed)}/{len(checks)} PASS")
    if failed: print("FAILED",failed); raise SystemExit(1)
if __name__=="__main__": main()
