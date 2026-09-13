from __future__ import annotations

"""Commit J — compact CEX reserve/flow context for TraderMacro.

Public transparency data is current context only. It does not claim that an
exchange itself bought/sold assets; deposits, withdrawals, custody and internal
moves can all contribute. Fail-open by design.
"""

import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

import requests

_CACHE={"ts":0.0,"data":None}
_LOCK=threading.Lock()
_TTL=max(600,int(os.getenv("MACRO_EXCHANGE_FLOW_CACHE_SECONDS","1800") or 1800))
_SESSION=requests.Session()
_SESSION.headers.update({"User-Agent":"CryptoTraderAnalystPro/J exchange-flow-context"})


def _money(text: str):
    raw=str(text or "").strip().replace("$","").replace(",","")
    m=re.match(r"^(-?)([0-9]+(?:\.[0-9]+)?)([kmbt]?)$",raw,re.I)
    if not m:return None
    value=float(m.group(2))*{"":1.0,"k":1e3,"m":1e6,"b":1e9,"t":1e12}.get(m.group(3).lower(),1.0)
    return -value if m.group(1) else value


def get_exchange_flow_context(force: bool=False) -> Dict[str,Any]:
    now=time.monotonic()
    with _LOCK:
        if not force and _CACHE["data"] is not None and now-_CACHE["ts"]<_TTL:
            return dict(_CACHE["data"])
    try:
        r=_SESSION.get("https://defillama.com/cexs",timeout=10)
        r.raise_for_status()
        text=re.sub(r"\s+"," ",r.text)
        rows=[]
        for name in ("Binance","OKX","Bybit","Bitfinex","KuCoin"):
            m=re.search(re.escape(name)+r"(.{0,700})",text,re.I)
            if not m: continue
            dollars=re.findall(r"-?\$[0-9][0-9,]*(?:\.[0-9]+)?\s*[kKmMbBtT]?",m.group(1))
            parsed=[_money(x.replace(" ","")) for x in dollars]
            parsed=[x for x in parsed if x is not None]
            if len(parsed)>=4:
                rows.append({"exchange":name,"assets_usd":parsed[0],"clean_assets_usd":parsed[1],"inflow_24h_usd":parsed[2],"inflow_7d_usd":parsed[3]})
        if not rows:
            raise RuntimeError("sin filas CEX parseables")
        d24=sum(float(x.get("inflow_24h_usd") or 0) for x in rows)
        d7=sum(float(x.get("inflow_7d_usd") or 0) for x in rows)
        if d24>250_000_000:
            state="NET_INFLOW_PRESSURE"
            label="Presión de entrada a CEX"
        elif d24<-250_000_000:
            state="NET_OUTFLOW_PRESSURE"
            label="Presión de salida de CEX"
        else:
            state="NEUTRAL"
            label="Flujo CEX neutral"
        # Large absolute movement is treated primarily as volatility/liquidity
        # context, not as an automatic directional call.
        volatility_risk="HIGH" if abs(d24)>=1_000_000_000 else ("MEDIUM" if abs(d24)>=500_000_000 else "LOW")
        data={
            "available":True,"authority":"CONTEXT_ONLY","state":state,"label_es":label,
            "aggregate_inflow_24h_usd":round(d24,2),"aggregate_inflow_7d_usd":round(d7,2),
            "volatility_risk":volatility_risk,"exchanges":rows,
            "source":"DEFILLAMA_PUBLIC_CEX_PAGE",
            "updated_at":datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            "note_es":"No equivale a compras/ventas propias del exchange; puede incluir depósitos, retiros, custodia o movimientos internos.",
        }
    except Exception as exc:
        data={"available":False,"authority":"CONTEXT_ONLY","state":"UNAVAILABLE","label_es":"Flujo CEX no disponible","volatility_risk":"UNKNOWN","exchanges":[],"error":str(exc)[:160]}
    with _LOCK:
        _CACHE.update(ts=now,data=dict(data))
    return data
