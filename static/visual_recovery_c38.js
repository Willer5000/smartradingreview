/* C38: READ-ONLY chart availability lane. NO trading/Telegram requests.
 * Keeps the original charts as primary. Loads independently only if the
 * original view is empty, using the existing lightweight OHLCV endpoints.
 */
(function () {
  'use strict';
  if (window.__C38_VISUAL_RECOVERY_INSTALLED__) return;
  window.__C38_VISUAL_RECOVERY_INSTALLED__ = true;
  const market = window.IS_MULTI_ASSET_PAGE ? 'multiasset' : (window.IS_FUTURES_PAGE ? 'futures' : 'spot');
  const states = new Map();
  let epoch = 0;
  let pending = false;
  let vendorPromise = null;
  const TIMEOUT = 8500;
  function missingVisualLayers() {
    return [['fvg-ob','fvg-ob-chart'],['liquidation-heatmap','liquidation-heatmap-chart']]
      .filter(([key,id]) => {
        const element = document.getElementById(id);
        if (!element || (window.ChartWorkspace?.shouldRender && !window.ChartWorkspace.shouldRender(key))) return false;
        return !Array.isArray(element.data) || !element.data.length;
      }).map(x=>x[0]);
  }
  function recoverLayers(data,req) {
    if(!valid(data,req) || typeof window.renderIndicatorChart !== 'function') return;
    for (const id of missingVisualLayers()) {
      try { preserveTechnicalDecision(() => window.renderIndicatorChart(id,data)); }
      catch(error) { console.debug('C39 isolated layer:',id,error?.message||error); }
    }
  }

  function plotlyReady() { return Boolean(window.Plotly && typeof window.Plotly.newPlot === 'function'); }
  function ensurePlotly() {
    if (plotlyReady()) return Promise.resolve(true);
    if (vendorPromise) return vendorPromise;
    vendorPromise = new Promise(resolve => {
      // The existing CDN is primary; this immutable local copy is the fallback.
      setTimeout(() => {
        if (plotlyReady()) { resolve(true); return; }
        const script = document.createElement('script');
        script.src = '/static/plotly-3.3.1.min.js?v=C38-20261012';
        script.async = true;
        script.onload = () => resolve(plotlyReady());
        script.onerror = () => resolve(false);
        document.head.appendChild(script);
      }, 2200);
    });
    return vendorPromise;
  }
  function selection() {
    const symbol = String(document.getElementById('symbol-select')?.value || window.PAGE_CONFIG?.defaultSymbol || 'BTC-USDT').trim().toUpperCase().replace('/', '-');
    const tf = String(document.getElementById('interval-select')?.value || window.PAGE_CONFIG?.defaultTimeframe || (market === 'spot' ? '1D' : '1h'));
    return {symbol, tf, key: market + '|' + symbol + '|' + tf};
  }
  function chartReady(div) {
    return !!(div && Array.isArray(div.data) && div.data.some(trace =>
      String(trace?.type || '').toLowerCase() === 'candlestick' && Array.isArray(trace.close) && trace.close.length > 3));
  }
  function status(message) {
    const chart = document.getElementById('candle-chart');
    if (!chart || chartReady(chart)) return;
    let e = document.getElementById('c38-chart-state');
    if (!e) {
      e = document.createElement('div');
      e.id = 'c38-chart-state';
      e.setAttribute('role', 'status');
      e.style.cssText = 'font-size:12px;color:#9fb4c3;text-align:center;padding:10px';
      chart.parentElement?.appendChild(e);
    }
    e.textContent = message;
  }
  function valid(data, req) {
    const df = data?.df;
    if (!df || !Array.isArray(df.time) || df.time.length < 8 || df.time.length > 500) return false;
    if (!['open', 'high', 'low', 'close'].every(k => Array.isArray(df[k]) && df[k].length === df.time.length)) return false;
    if (String(data.symbol || req.symbol).toUpperCase().replace('/', '-') !== req.symbol ||
        String(data.timeframe || req.tf) !== req.tf) return false;
    return true;
  }
  async function read(url, controller) {
    const res = await fetch(url, {credentials:'same-origin', cache:'no-store',signal:controller.signal});
    if (!res.ok) return null;
    const payload = await res.json();
    if (payload?.deferred || payload?.success === false) return null;
    return payload?.data?.df ? payload.data : payload;
  }
  async function requestVisual(req, controller) {
    const params = new URLSearchParams({symbol:req.symbol,timeframe:req.tf});
    if (market === 'multiasset') {
      const multi = await read('/api/multiasset/display?' + params,controller);
      if (valid(multi,req)) return multi;
    }
    params.set('market',market);
    const visuals = await read('/api/futures/visuals?' + params,controller);
    return valid(visuals,req) ? visuals : null;
  }
  function preserveTechnicalDecision(render) {
    // updateAllCharts previously overwrites currentAnalysis; do not replace
    // the official analysis with a display-only OHLCV result.
    const previous = window.currentAnalysis;
    try { return render(); }
    finally { window.currentAnalysis = previous; }
  }
  async function draw(req, data, currentEpoch) {
    if (!valid(data,req) || !(await ensurePlotly())) {
      status('Biblioteca gráfica no disponible. Se reintentará sin cambiar señales.');
      return false;
    }
    if (currentEpoch !== epoch || selection().key !== req.key || document.hidden) return false;
    const chart = document.getElementById('candle-chart');
    if (!chart) return false;
    // A candle chart can be healthy while separate liquidation/FVG panels are blank.
    // Recover their presentation layers without calling the heavy signal engine.
    recoverLayers(data,req);
    if (chartReady(chart)) return true;
    // Prefer the original trading chart renderer. It may compute indicators
    // from genuine OHLCV locally, without running backend specialists.
    // C39: a pure OHLCV fallback must NOT call updateAllCharts: doing so
    // reinitialised the liquidation/FVG panels with missing rich layers.
    // Draw selected-cell candles only; other OHLCV indicators follow below.
    try {
      if (market === 'multiasset' && window.MultiAssetDisplayCore3342?.render)
        window.MultiAssetDisplayCore3342.render(data);
      else preserveTechnicalDecision(() => window.updateCandleChart?.(data));
      await new Promise(resolve => setTimeout(resolve, 180));
    } catch (err) {
      console.debug('C39 isolated candle fallback:',err?.message || err);
    }
    if (!chartReady(chart)) {
      try {
        preserveTechnicalDecision(() => window.updateCandleChart?.(data));
        await new Promise(resolve => setTimeout(resolve, 180));
      }
      catch (err) { console.debug('C38 candle fallback:',err?.message || err); }
    }
    if (!chartReady(chart)) {
      // Standalone candlestick fallback. Never fabricate prices or indicators.
      const d=data.df, times=d.time.map(x=>new Date(x));
      const prices=d.close.map(Number);
      if (prices.some(x=>!Number.isFinite(x) || x<=0)) return false;
      try {
        await window.Plotly.newPlot(chart,[{type:'candlestick',x:times,
          open:d.open.map(Number),high:d.high.map(Number),
          low:d.low.map(Number),close:prices,name:req.symbol}],
          {paper_bgcolor:'#0b1018',plot_bgcolor:'#0b1018',font:{color:'#cbd5e1'},
           margin:{l:55,r:20,t:15,b:40},height:410,xaxis:{rangeslider:{visible:false}}},
          {responsive:true,displaylogo:false});
      } catch (err) { console.debug('C38 Plotly chart failure',err?.message || err); }
    }
    // If an advanced renderer threw due to absent structural extras, render
    // each standalone indicator independently from genuine selected OHLCV.
    // Never fabricate order-flow, liquidity maps or expert decisions.
    const supplementary = [
      ['volume-chart','volume','updateVolumeChart'],
      ['rsi-chart','rsi','updateRSIChart'],
      ['macd-chart','macd','updateMACDChart'],
      ['stochastic-chart','stochastic','updateStochasticChart'],
      ['atr-chart','atr','updateATRChart'],
      ['bollinger-chart','bollinger','updateBollingerChart'],
      ['adx-chart','adx','updateADXChart'],
      ['supertrend-chart','supertrend','updateSuperTrendChart'],
      ['ichimoku-chart','ichimoku','updateIchimokuChart'],
      ['vwap-chart','vwap','updateVWAPChart'],
      ['volume-profile-chart','volume-profile','updateVolumeProfileChart']
    ];
    for (const [id,group,name] of supplementary) {
      const el = document.getElementById(id);
      if (!el || (Array.isArray(el.data) && el.data.length)) continue;
      if (window.ChartWorkspace?.shouldRender && !window.ChartWorkspace.shouldRender(group)) continue;
      try { preserveTechnicalDecision(() => window[name]?.(data)); }
      catch (err) { console.debug('C38 indicator unavailable:',name,err?.message||err); }
    }
    if (chartReady(chart)) {
      const e=document.getElementById('c38-chart-state');
      if(e) e.remove();
      return true;
    }
    status('Velas disponibles, pero el navegador no pudo construir el gráfico.');
    return false;
  }
  async function tick(force=false) {
    if (document.hidden || pending) return;
    const chart = document.getElementById('candle-chart');
    if (!chart || (chartReady(chart) && !missingVisualLayers().length)) return;
    const req=selection();
    const state=states.get(req.key)||{tries:0,next:0};
    if (!force && Date.now()<state.next) return;
    if (state.tries>=5) return; // No unbounded polling or bandwidth leakage.
    pending=true;
    const currentEpoch=epoch;
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),TIMEOUT);
    try {
      status('Recuperando velas e indicadores reales (sin recalcular señales)...');
      // Reuse genuine already fetched OHLCV before consuming another request.
      const local = [window.currentDisplayAnalysis, window.currentAnalysis].find(
        candidate => valid(candidate,req));
      const data = local || await requestVisual(req,controller);
      if (currentEpoch!==epoch || selection().key!==req.key) return;
      if (data && await draw(req,data,currentEpoch)) {
        const remaining=missingVisualLayers();
        const tries=remaining.length ? state.tries+1 : 0;
        // Missing provider-only liquidity must not cause infinite HTTP polling.
        states.set(req.key,{tries,next:Date.now()+(remaining.length ? Math.min(600000,tries*120000) : 120000)});
        return;
      }
      state.tries++;
      state.next=Date.now()+Math.min(60000,15000*state.tries);
      states.set(req.key,state);
      status('Gráficos diferidos por recursos o proveedor; reintento limitado.');
    } catch (err) {
      if (err?.name !== 'AbortError') console.debug('C38 visual read:',err?.message||err);
      state.tries++;
      state.next=Date.now()+Math.min(60000,15000*state.tries);
      states.set(req.key,state);
    } finally {clearTimeout(timer);pending=false;}
  }
  function invalidate() {
    ++epoch;
    states.delete(selection().key);
    setTimeout(()=>tick(true),1800);
  }
  function boot() {
    const candle=document.getElementById('candle-chart');
    if (!candle) return;
    ensurePlotly();
    setTimeout(()=>tick(true),2500);
    // Only a passive check, never a heavy endpoint.
    const interval=setInterval(()=>{
      if (document.hidden) return;
      if (chartReady(candle) && !missingVisualLayers().length) return;
      tick(false);
    },20000);
    ['symbol-select','interval-select'].forEach(id=>document.getElementById(id)?.addEventListener('change',invalidate));
    document.addEventListener('visibilitychange',()=>{if (!document.hidden) setTimeout(()=>tick(false),1500);});
    window.addEventListener('pagehide',()=>clearInterval(interval),{once:true});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
