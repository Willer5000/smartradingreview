/* SmartTradingReview 33.4.2 — Multi-Asset critical display core.
 * Presentation-only. Uses real OHLCV from /api/multiasset/display and never
 * starts committees, Strategy Bank, AI, DB writes or trading authority.
 * Loaded independently from the large application bundle so charts survive a
 * transient failure of script.js on the small Render worker.
 */
(function () {
  'use strict';
  if (window.__STR_MULTI_DISPLAY_CORE_3342__) return;
  window.__STR_MULTI_DISPLAY_CORE_3342__ = true;

  const state = {seq: 0, controller: null, timer: null, cache: new Map(), ttl: 45000};

  const n = v => Number.isFinite(Number(v)) ? Number(v) : 0;
  const normSym = v => String(v || 'CL-USDT').toUpperCase().replace('/', '-');
  const normTf = v => String(v || '4h');

  function ema(values, period) {
    const k = 2 / (period + 1), out = [];
    let prev = n(values[0]);
    for (let i=0;i<values.length;i++) {
      const v=n(values[i]);
      prev = i ? v*k + prev*(1-k) : v;
      out.push(prev);
    }
    return out;
  }
  function rsi(values, period=14) {
    const out = new Array(values.length).fill(50);
    if (values.length < 2) return out;
    let ag=0, al=0;
    for (let i=1;i<values.length;i++) {
      const d=n(values[i])-n(values[i-1]), g=Math.max(d,0), l=Math.max(-d,0);
      if (i<=period) {
        ag += g/period; al += l/period;
      } else {
        ag=(ag*(period-1)+g)/period; al=(al*(period-1)+l)/period;
      }
      if (i>=period) out[i]=al===0 ? 100 : 100-(100/(1+ag/al));
    }
    return out;
  }
  function atr(high, low, close, period=14) {
    const tr = high.map((h,i)=>Math.max(n(h)-n(low[i]), Math.abs(n(h)-n(close[Math.max(0,i-1)])), Math.abs(n(low[i])-n(close[Math.max(0,i-1)]))));
    const out=[]; let prev=tr[0]||0;
    tr.forEach((v,i)=>{ prev=i ? (prev*(period-1)+v)/period : v; out.push(prev); });
    return out;
  }
  function dmi(high, low, close, period=14) {
    const len=close.length, plusDM=new Array(len).fill(0), minusDM=new Array(len).fill(0), tr=new Array(len).fill(0);
    for(let i=1;i<len;i++){
      const up=n(high[i])-n(high[i-1]), down=n(low[i-1])-n(low[i]);
      plusDM[i]=(up>down&&up>0)?up:0; minusDM[i]=(down>up&&down>0)?down:0;
      tr[i]=Math.max(n(high[i])-n(low[i]),Math.abs(n(high[i])-n(close[i-1])),Math.abs(n(low[i])-n(close[i-1])));
    }
    const smooth = arr => {
      const out=new Array(len).fill(0); let s=0;
      for(let i=0;i<len;i++){ s = i<period ? s+n(arr[i]) : s-(s/period)+n(arr[i]); out[i]=s; }
      return out;
    };
    const st=smooth(tr), sp=smooth(plusDM), sm=smooth(minusDM);
    const plus=st.map((v,i)=>v?100*sp[i]/v:0), minus=st.map((v,i)=>v?100*sm[i]/v:0);
    const dx=plus.map((v,i)=> (v+minus[i]) ? 100*Math.abs(v-minus[i])/(v+minus[i]) : 0);
    const adx=ema(dx, period);
    return {adx, plus, minus};
  }
  function layout(title, height=280) {
    return {
      title:{text:title,font:{size:13}}, template:'plotly_dark', height,
      margin:{l:48,r:24,t:42,b:38}, paper_bgcolor:'#0A0C10', plot_bgcolor:'#0A0C10',
      xaxis:{gridcolor:'rgba(128,128,128,.16)'}, yaxis:{gridcolor:'rgba(128,128,128,.16)'},
      legend:{orientation:'h', y:1.08}
    };
  }
  function plot(id, traces, lay) {
    const el=document.getElementById(id);
    if(!el || !window.Plotly) return;
    try { Plotly.react(el,traces,lay,{responsive:true,displaylogo:false}); } catch(e) { console.debug('3342 plot',id,e?.message||e); }
  }

  function render(data) {
    if (!data?.df?.time?.length || !window.Plotly) return;
    window.currentDisplayAnalysis=data;
    if (!window.currentAnalysis || window.currentAnalysis?.ui_identity_placeholder) window.currentAnalysis=data;
    const d=data.df, x=d.time, o=d.open.map(n), h=d.high.map(n), l=d.low.map(n), c=d.close.map(n), v=d.volume.map(n);
    const start=Math.max(0,x.length-80), xs=x.slice(start);

    plot('candle-chart',[{x:xs,open:o.slice(start),high:h.slice(start),low:l.slice(start),close:c.slice(start),type:'candlestick',name:'Precio'}],layout(`${data.display_name||data.symbol} ${data.timeframe}`,430));
    plot('volume-chart',[{x:xs,y:v.slice(start),type:'bar',name:'Volumen'}],layout('Volumen',260));

    const rs=rsi(c,14);
    plot('rsi-chart',[{x:xs,y:rs.slice(start),type:'scatter',mode:'lines',name:'RSI 14'}],
      {...layout('RSI',280),yaxis:{range:[0,100],gridcolor:'rgba(128,128,128,.16)'},
       shapes:[30,70].map(y=>({type:'line',x0:xs[0],x1:xs[xs.length-1],y0:y,y1:y,line:{dash:'dot',width:1}}))});

    const fast=ema(c,12), slow=ema(c,26), macd=fast.map((z,i)=>z-slow[i]), sig=ema(macd,9), hist=macd.map((z,i)=>z-sig[i]);
    plot('macd-chart',[
      {x:xs,y:macd.slice(start),type:'scatter',mode:'lines',name:'MACD'},
      {x:xs,y:sig.slice(start),type:'scatter',mode:'lines',name:'Señal'},
      {x:xs,y:hist.slice(start),type:'bar',name:'Histograma'}
    ],layout('MACD',300));

    const a=atr(h,l,c,14), ap=a.map((z,i)=>c[i]?100*z/c[i]:0);
    plot('atr-chart',[{x:xs,y:ap.slice(start),type:'scatter',mode:'lines',fill:'tozeroy',name:'ATR %'}],layout('ATR - Volatilidad',270));

    const dm=dmi(h,l,c,14);
    plot('adx-chart',[
      {x:xs,y:dm.adx.slice(start),type:'scatter',mode:'lines',name:'ADX'},
      {x:xs,y:dm.plus.slice(start),type:'scatter',mode:'lines',name:'+DI'},
      {x:xs,y:dm.minus.slice(start),type:'scatter',mode:'lines',name:'-DI'}
    ],layout('ADX / DMI',300));

    const mid=ema(c,20), aa=atr(h,l,c,20), up=mid.map((z,i)=>z+2*aa[i]), dn=mid.map((z,i)=>z-2*aa[i]);
    plot('bollinger-chart',[
      {x:xs,y:c.slice(start),type:'scatter',mode:'lines',name:'Precio'},
      {x:xs,y:up.slice(start),type:'scatter',mode:'lines',name:'Banda sup.'},
      {x:xs,y:mid.slice(start),type:'scatter',mode:'lines',name:'Media'},
      {x:xs,y:dn.slice(start),type:'scatter',mode:'lines',name:'Banda inf.'}
    ],layout('Bandas de volatilidad',300));

    let cumPV=0,cumV=0; const vw=[];
    for(let i=0;i<c.length;i++){ const tp=(h[i]+l[i]+c[i])/3; cumPV+=tp*v[i]; cumV+=v[i]; vw.push(cumV?cumPV/cumV:c[i]); }

    // Additional indicator panels are kept in this tiny display bundle so a
    // transient 502 on the legacy monolith cannot leave Multi-Asset blank.
    const rollingMid=(hh,ll,period)=>hh.map((_,i)=>{
      const a=Math.max(0,i-period+1), H=Math.max(...hh.slice(a,i+1).map(n)), L=Math.min(...ll.slice(a,i+1).map(n));
      return (H+L)/2;
    });
    const tenkan=rollingMid(h,l,9), kijun=rollingMid(h,l,26), spanB=rollingMid(h,l,52), spanA=tenkan.map((z,i)=>(z+kijun[i])/2);
    plot('ichimoku-chart',[
      {x:xs,y:c.slice(start),type:'scatter',mode:'lines',name:'Precio'},
      {x:xs,y:tenkan.slice(start),type:'scatter',mode:'lines',name:'Tenkan'},
      {x:xs,y:kijun.slice(start),type:'scatter',mode:'lines',name:'Kijun'},
      {x:xs,y:spanA.slice(start),type:'scatter',mode:'lines',name:'Span A'},
      {x:xs,y:spanB.slice(start),type:'scatter',mode:'lines',name:'Span B'}
    ],layout('Ichimoku',300));

    const stK=c.map((z,i)=>{ const a0=Math.max(0,i-13), H=Math.max(...h.slice(a0,i+1).map(n)), L=Math.min(...l.slice(a0,i+1).map(n)); return H===L?50:100*(z-L)/(H-L); });
    const stD=ema(stK,3);
    plot('stochastic-chart',[
      {x:xs,y:stK.slice(start),type:'scatter',mode:'lines',name:'%K'},
      {x:xs,y:stD.slice(start),type:'scatter',mode:'lines',name:'%D'}
    ],{...layout('Estocástico',300),yaxis:{range:[0,100],gridcolor:'rgba(128,128,128,.16)'}});

    const rfast=ema(rs,5), rslow=ema(rs,14);
    plot('rsi-maverick-chart',[
      {x:xs,y:rs.slice(start),type:'scatter',mode:'lines',name:'RSI'},
      {x:xs,y:rfast.slice(start),type:'scatter',mode:'lines',name:'RSI EMA 5'},
      {x:xs,y:rslow.slice(start),type:'scatter',mode:'lines',name:'RSI EMA 14'}
    ],{...layout('RSI Maverick',300),yaxis:{range:[0,100],gridcolor:'rgba(128,128,128,.16)'}});

    const width=up.map((z,i)=>mid[i]?100*(z-dn[i])/mid[i]:0), mom=c.map((z,i)=>i>=12?100*(z/c[i-12]-1):0);
    plot('squeeze-chart',[
      {x:xs,y:width.slice(start),type:'scatter',mode:'lines',name:'BB width %'},
      {x:xs,y:mom.slice(start),type:'bar',name:'Momentum 12'}
    ],layout('Compresión / Expansión',300));

    const superTrend=c.map((z,i)=>{
      const hl2=(h[i]+l[i])/2, mult=2.5*a[i];
      return z>=mid[i] ? hl2-mult : hl2+mult;
    });
    plot('supertrend-chart',[
      {x:xs,y:c.slice(start),type:'scatter',mode:'lines',name:'Precio'},
      {x:xs,y:superTrend.slice(start),type:'scatter',mode:'lines',name:'SuperTrend proxy'}
    ],layout('SuperTrend',350));

    const wr=c.map((z,i)=>{ const a0=Math.max(0,i-13), H=Math.max(...h.slice(a0,i+1).map(n)), L=Math.min(...l.slice(a0,i+1).map(n)); return H===L?-50:-100*(H-z)/(H-L); });
    const tp=c.map((z,i)=>(h[i]+l[i]+z)/3), sma20=tp.map((_,i)=>{const a0=Math.max(0,i-19),q=tp.slice(a0,i+1);return q.reduce((A,B)=>A+B,0)/q.length;});
    const cci=tp.map((z,i)=>{const a0=Math.max(0,i-19),q=tp.slice(a0,i+1),m=sma20[i],dev=q.reduce((A,B)=>A+Math.abs(B-m),0)/q.length;return dev? (z-m)/(0.015*dev):0;});
    plot('williams-cci-chart',[
      {x:xs,y:wr.slice(start),type:'scatter',mode:'lines',name:'Williams %R'},
      {x:xs,y:cci.slice(start),type:'scatter',mode:'lines',name:'CCI'}
    ],layout('Williams %R / CCI',300));

    const mfi=c.map((_,i)=>{
      const a0=Math.max(1,i-13); let pos=0,neg=0;
      for(let j=a0;j<=i;j++){ const flow=tp[j]*v[j]; if(tp[j]>=tp[j-1])pos+=flow; else neg+=flow; }
      return neg===0?100:100-(100/(1+pos/neg));
    });
    const force=c.map((z,i)=>i?(z-c[i-1])*v[i]:0), forceNorm=force.map((z,i)=>{const a0=Math.max(0,i-19),q=force.slice(a0,i+1).map(Math.abs),mx=Math.max(...q,1);return 100*z/mx;});
    plot('mfi-force-chart',[
      {x:xs,y:mfi.slice(start),type:'scatter',mode:'lines',name:'MFI'},
      {x:xs,y:forceNorm.slice(start),type:'bar',name:'Force norm.'}
    ],layout('MFI / Force Index',300));

    const fibHi=Math.max(...h.slice(start).map(n)), fibLo=Math.min(...l.slice(start).map(n)), fibRange=fibHi-fibLo;
    const fibs=[0,0.236,0.382,0.5,0.618,0.786,1].map(r=>({r,y:fibHi-r*fibRange}));
    plot('fibonacci-chart',[{x:xs,y:c.slice(start),type:'scatter',mode:'lines',name:'Precio'}],{
      ...layout('Fibonacci dinámico',350),
      shapes:fibs.map(f=>({type:'line',xref:'x',yref:'y',x0:xs[0],x1:xs[xs.length-1],y0:f.y,y1:f.y,line:{dash:'dot',width:1}})),
      annotations:fibs.map(f=>({xref:'paper',x:1,yref:'y',y:f.y,text:`${Math.round(f.r*1000)/10}%`,showarrow:false,xanchor:'left'}))
    });

    // Lightweight volume profile: price-bin aggregation from the same real OHLCV.
    if (fibRange>0) {
      const bins=24, vols=new Array(bins).fill(0), centers=[];
      for(let i=start;i<c.length;i++){ const b=Math.min(bins-1,Math.max(0,Math.floor((c[i]-fibLo)/fibRange*bins))); vols[b]+=v[i]; }
      for(let b=0;b<bins;b++) centers.push(fibLo+(b+.5)*fibRange/bins);
      plot('volume-profile-chart',[{x:vols,y:centers,type:'bar',orientation:'h',name:'Volumen'}],layout('Perfil de volumen',350));
    }

    const st=data.structure||{}, shapes=[];
    (st.fair_value_gaps||[]).forEach(g=>{
      const i=Math.max(start,Math.min(x.length-1,Number(g.index)||x.length-1));
      shapes.push({type:'rect',xref:'x',yref:'y',x0:x[i],x1:x[Math.min(x.length-1,i+4)],y0:n(g.gap_bottom),y1:n(g.gap_top),opacity:.18,line:{width:1}});
    });
    (st.order_blocks||[]).forEach(ob=>{
      const pr=ob.price_range||[]; if(pr.length<2)return;
      const i=Math.max(start,Math.min(x.length-1,Number(ob.index)||x.length-1));
      shapes.push({type:'rect',xref:'x',yref:'y',x0:x[i],x1:x[Math.min(x.length-1,i+6)],y0:n(pr[0]),y1:n(pr[1]),opacity:.20,line:{width:1}});
    });
    plot('fvg-ob-chart',[{x:xs,open:o.slice(start),high:h.slice(start),low:l.slice(start),close:c.slice(start),type:'candlestick',name:'Precio'}],
      {...layout('Estructura institucional',360),shapes});
    const interp=document.getElementById('fvg-ob-interpretation');
    if(interp) interp.textContent=`OHLCV real · ${(st.fair_value_gaps||[]).length} FVG · ${(st.order_blocks||[]).length} OB · ${(st.liquidity_sweeps||[]).length} sweeps`;

    const price=n(data.current_price||c[c.length-1]);
    const live=document.getElementById('live-price'); if(live&&price>0) live.textContent=`$${price.toLocaleString(undefined,{maximumFractionDigits:8})}`;
  }

  async function refresh() {
    // COMMIT34.2: this lightweight lane only belongs to /multiasset, and
    // must never issue a Multi-Asset GET for a Futures selector such as BTC.
    // A selector can still hold its template default before Multi is hydrated.
    if (window.IS_MULTI_ASSET_PAGE !== true ||
        window.location.pathname.replace(/\/+$/, '') !== '/multiasset') return;
    const cfg=window.PAGE_CONFIG || {};
    const universe=cfg.symbols || {};
    const allowedTf=cfg.allowedTimeframesBySymbol || {};
    let sym=normSym(document.getElementById('symbol-select')?.value || cfg.defaultSymbol);
    if (!Object.prototype.hasOwnProperty.call(universe,sym)) sym=normSym(cfg.defaultSymbol);
    if (!Object.prototype.hasOwnProperty.call(universe,sym)) return null;
    let tf=normTf(document.getElementById('interval-select')?.value || cfg.defaultTimeframe);
    if (!Array.isArray(allowedTf[sym]) || !allowedTf[sym].includes(tf)) {
      tf=normTf(cfg.defaultTimeframe);
    }
    if (!Array.isArray(allowedTf[sym]) || !allowedTf[sym].includes(tf)) return null;
    const key=`${sym}|${tf}`, hit=state.cache.get(key);
    if(hit && Date.now()-hit.ts<state.ttl){ render(hit.data); return hit.data; }
    if(state.controller) try{state.controller.abort();}catch(_){}
    state.controller=new AbortController();
    const seq=++state.seq;
    clearTimeout(state.timer); state.timer=setTimeout(()=>state.controller?.abort(),6500);
    try{
      const res=await fetch(`/api/multiasset/display?symbol=${encodeURIComponent(sym)}&timeframe=${encodeURIComponent(tf)}&_v=3342`,
        {credentials:'same-origin',cache:'no-store',signal:state.controller.signal});
      const payload=await res.json();
      if(seq!==state.seq)return null;
      const data=payload?.data||{};
      if(payload?.available===false || !data?.df?.time?.length) return null;
      state.cache.set(key,{ts:Date.now(),data});
      while(state.cache.size>3){ const first=state.cache.keys().next().value; state.cache.delete(first); }
      render(data); return data;
    } catch(e) {
      if(e?.name!=='AbortError') console.debug('Multi display core 33.4.2:',e?.message||e);
      return null;
    } finally { clearTimeout(state.timer); }
  }

  window.MultiAssetDisplayCore3342={refresh,render};
  document.addEventListener('DOMContentLoaded',()=>{
    if(window.IS_MULTI_ASSET_PAGE!==true)return;
    const sym=document.getElementById('symbol-select'), tf=document.getElementById('interval-select');
    sym?.addEventListener('change',()=>setTimeout(refresh,0));
    tf?.addEventListener('change',()=>setTimeout(refresh,0));
    document.getElementById('analyze-btn')?.addEventListener('click',()=>setTimeout(refresh,0));
    refresh();
  },{once:true});
})();