/* SmartTradingReview C45-V — SOLO PRESENTACION.
 * Preserva referencias REALES ya mostradas por el navegador y permite consultar
 * su ultima visualizacion cuando la interfaz notifica que el motor esta ocupado.
 * NO realiza solicitudes HTTP, NO inicia calculos, NO toca app.py, señales,
 * Guardian, portfolio, currentAnalysis, ventanas temporales ni variables de trade.
 */
(function () {
  'use strict';
  if (window.__STR_C45V_VISUAL_ONLY__) return;

  const PREFIX = 'str.c45v.1.';
  const MAX_CHARTS = 4;
  const MAX_TRACE_BARS = 240;
  const MAX_CHART_BYTES = 250000;
  const MAX_REC_BYTES = 13000;
  const KIND = window.IS_MULTI_ASSET_PAGE ? 'multiasset' : (window.IS_FUTURES_PAGE ? 'futures' : 'spot');
  const normalize = v => String(v || '').trim().toUpperCase().replace('/', '-');
  const selected = () => {
    const symbol = document.getElementById('symbol-select')?.value;
    const tf = document.getElementById('interval-select')?.value;
    return symbol && tf ? `${KIND}|${normalize(symbol)}|${String(tf)}` : '';
  };
  const cell = data => data?.symbol && data?.timeframe
    ? `${KIND}|${normalize(data.symbol)}|${String(data.timeframe)}` : '';
  const user = () => {
    const id = window.getSmartTradingUser?.();
    return typeof id === 'string' && /^[\w-]{1,40}$/.test(id) ? id : '';
  };
  const store = () => { try { return window.sessionStorage; } catch (_) { return null; } };
  const limitMs = key => key?.endsWith('|1W') ? 8 * 86400000 :
    key?.endsWith('|1D') ? 3 * 86400000 : 24 * 3600000;
  const storageKey = (type, key) => PREFIX + type + '.' + key;
  let epoch = 0;
  let visibleCell = '';
  let lastNativeDecision = '';
  let currentKey = '';
  let isRenderingHistory = false;
  let restoringChart = false;
  let recObserver = null;

  function read(type, key) {
    try {
      if (!key) return null;
      const row = JSON.parse(store()?.getItem(storageKey(type, key)) || 'null');
      if (!row || !row.value || !Number.isFinite(row.at) || row.at > Date.now() + 60000 ||
          Date.now() - row.at > limitMs(key)) return null;
      return row;
    } catch (_) { return null; }
  }
  function write(type, key, value, maxBytes, maxCells) {
    try {
      if (!key) return;
      const s = store();
      if (!s) return;
      const raw = JSON.stringify({at: Date.now(), value});
      if (raw.length > maxBytes) return;
      s.setItem(storageKey(type, key), raw);
      const prefix = PREFIX + type + '.';
      const all = [];
      for (let i = 0; i < s.length; i++) {
        const k = s.key(i);
        if (!k?.startsWith(prefix)) continue;
        let at = 0;
        try { at = JSON.parse(s.getItem(k)).at || 0; } catch (_) {}
        all.push({k, at});
      }
      all.sort((a, b) => b.at - a.at);
      for (const {k} of all.slice(maxCells)) s.removeItem(k);
    } catch (_) { /* navegador sin permiso o espacio: no afecta al producto */ }
  }

  function validDecision(data) {
    return data && typeof data === 'object' && data.decision != null && typeof data.decision === 'object' &&
      ['LONG','SHORT','COMPRA_SPOT','VENTA_SPOT','ESPERAR','NO_OPERAR','PRECAUCION']
        .includes(String(data.decision.action || '').toUpperCase());
  }
  function recordDecision(data) {
    const key = selected();
    const uid = user();
    if (isRenderingHistory || !uid || cell(data) !== key || !validDecision(data)) return;
    const d = data.decision;
    const saved = {
      symbol: normalize(data.symbol), timeframe: String(data.timeframe),
      action: String(d.action), confidence: Number(d.confidence || 0),
      reason: String(d.reason || '').slice(0, 900),
      message: String(data.message || '').slice(0, 2600),
      candle: String(data.source_candle_close_timestamp || data.source_candle_timestamp || '').slice(0, 80),
      // Solo texto de evidencia historica. Ningun boton de ejecutar o guardar.
      entry: data.levels?.entry ?? null,
      sl: data.levels?.stop_loss ?? null,
      tp: data.levels?.take_profit ?? null
    };
    write('rec', uid + '|' + key, saved, MAX_REC_BYTES, 8);
    lastNativeDecision = key;
    document.getElementById('str-c45v-rec-ref')?.remove();
  }

  function chartIsReal(chart) {
    return Array.isArray(chart?.data) && chart.data.some(t =>
      String(t?.type).toLowerCase() === 'candlestick' &&
      Array.isArray(t.close) && t.close.length > 5 &&
      Array.isArray(t.open) && t.open.length === t.close.length);
  }
  function chartPayload(chart) {
    if (!chartIsReal(chart)) return null;
    const traces = [];
    for (const t of chart.data) {
      if (traces.length >= 9) break;
      if (!['candlestick','scatter'].includes(String(t.type).toLowerCase())) continue;
      const entry = {type:String(t.type), name:String(t.name || '').slice(0,60),
        showlegend:t.showlegend !== false};
      for (const k of ['x','y','open','high','low','close']) {
        const v = t[k];
        if (Array.isArray(v)) entry[k] = v.slice(-MAX_TRACE_BARS).map(x =>
          x instanceof Date ? x.toISOString() : (typeof x === 'number' || typeof x === 'string' ? x : null));
      }
      if (t.mode) entry.mode = t.mode;
      if (t.line && typeof t.line === 'object') entry.line = {
        color:t.line.color, width:t.line.width, dash:t.line.dash};
      for (const part of ['increasing','decreasing']) if (t[part]) entry[part] = {
        line: {color:t[part].line?.color}, fillcolor:t[part].fillcolor};
      traces.push(entry);
    }
    if (!traces.some(t => t.type === 'candlestick')) return null;
    return {traces, layout: {
      paper_bgcolor:'#0A0C10',plot_bgcolor:'#0A0C10',height:450,
      font:{color:'#dae1ed'}, margin:{l:48,r:30,t:35,b:65},
      xaxis:{type:'date',rangeslider:{visible:false},gridcolor:'rgba(128,128,128,.2)'},
      yaxis:{autorange:true,gridcolor:'rgba(128,128,128,.2)'},showlegend:true,
      legend:{orientation:'h'}
    }};
  }
  function noteChart(message) {
    const chart = document.getElementById('candle-chart');
    if (!chart?.parentElement) return;
    let el = document.getElementById('str-c45v-chart-note');
    if (!el) {
      el = document.createElement('div');
      el.id = 'str-c45v-chart-note';
      el.setAttribute('role','status');
      el.style.cssText = 'padding:6px 8px;font-size:12px;color:#e6bd6e';
      chart.insertAdjacentElement('afterend',el);
    }
    el.textContent = message || '';
    el.hidden = !message;
  }
  function captureChart(data, key, seq, expectedEnd) {
    if (isRenderingHistory || key !== selected() || epoch !== seq) return;
    const chart = document.getElementById('candle-chart');
    if (!chartIsReal(chart) || !Array.isArray(data?.df?.close)) return;
    const candles = chart.data.find(t => String(t.type).toLowerCase() === 'candlestick');
    const lastChart = Number(candles?.close?.at(-1));
    const lastInput = Number(data.df.close.at(-1));
    if (!Number.isFinite(lastChart) || !Number.isFinite(lastInput) ||
        Math.abs(lastChart - lastInput) > Math.max(1e-6,Math.abs(lastInput) * 1e-5)) return;
    // Comprobar tambien la identidad temporal de la ultima vela.
    const lastTimeChart = new Date(candles?.x?.at(-1)).getTime();
    const lastTimeSource = new Date(data.df.time?.at(-1)).getTime();
    if (Number.isFinite(lastTimeChart) && Number.isFinite(lastTimeSource) &&
        Math.abs(lastTimeChart - lastTimeSource) > 1000) return;
    const payload = chartPayload(chart);
    if (!payload) return;
    if (expectedEnd && expectedEnd !== selected()) return;
    write('chart',key,payload,MAX_CHART_BYTES,MAX_CHARTS);
    visibleCell = key;
    chart.dataset.c45vCell = key;
    chart.style.visibility = '';
    noteChart('');
  }
  function recordChart(data) {
    if (isRenderingHistory || cell(data) !== selected() || !Array.isArray(data?.df?.close) ||
        !data.df.close.length) return;
    const key = selected();
    const seq = epoch;
    // El motor grafico Plotly termina asincronamente; solo OBSERVAMOS el dibujo.
    setTimeout(() => captureChart(data,key,seq,key),450);
    setTimeout(() => captureChart(data,key,seq,key),1250);
  }
  function restoreChart(key) {
    const chart = document.getElementById('candle-chart');
    const row = read('chart',key);
    if (!chart) return;
    if (!row || !window.Plotly?.newPlot) {
      if (visibleCell && visibleCell !== key) {
        chart.style.visibility = 'hidden';
        noteChart('Esperando velas reales para el activo y la temporalidad seleccionados. No se mostrarán gráficos de otro activo.');
      }
      return;
    }
    restoringChart = true;
    isRenderingHistory = true;
    chart.style.visibility = '';
    chart.dataset.c45vCell = key;
    const seq = epoch;
    try {
      const result = window.Plotly.newPlot(chart,row.value.traces,row.value.layout,
        {responsive:true,displaylogo:false});
      Promise.resolve(result).then(() => {
        if (epoch !== seq || selected() !== key) return;
        visibleCell = key;
        noteChart(`Último gráfico real consultado: ${new Date(row.at).toLocaleString('es-BO')}. Referencia visual histórica; no genera nuevas señales.`);
      }).catch(() => {});
    } catch (_) { noteChart('Gráfico anterior no disponible. Esperando las velas reales.'); }
    finally { isRenderingHistory = false; restoringChart = false; }
  }

  function addText(parent, tag, value, css) {
    const el = document.createElement(tag);
    if (css) el.className = css;
    el.textContent = String(value);
    parent.appendChild(el);
  }
  function referenceRecommendation() {
    const box = document.getElementById('system-recommendation');
    const key = selected();
    const uid = user();
    if (!box || !key || !uid) return;
    // No reemplazar NUNCA una recomendacion actual del motor.
    const existing = box.querySelector('#str-c45v-rec-ref');
    const content = (box.textContent || '').toLowerCase();
    const busy = /ocupado|esperando|preparando|actualizando|reintentar|reintentando|tardó más|analizando|cálculo previo|snapshot/.test(content);
    if (!busy || box.querySelector('.analysis-text')) { existing?.remove(); return; }
    if (existing) return;
    const row = read('rec',uid + '|' + key);
    const d = row?.value;
    if (!d || d.symbol !== key.split('|')[1] || d.timeframe !== key.split('|')[2]) return;
    const card = document.createElement('section');
    card.id = 'str-c45v-rec-ref';
    card.className = 'rounded-3 p-3 mt-3';
    card.style.cssText = 'border:1px solid #75642d;background:rgba(255,193,7,.055);color:#e7e9ee';
    addText(card,'div',`Última recomendación calculada (${new Date(row.at).toLocaleString('es-BO')}) · REFERENCIA HISTÓRICA, no señal actual`, 'small text-warning mb-2');
    addText(card,'strong',`${d.action.replaceAll('_',' ')} · Confianza: ${Number(d.confidence || 0).toFixed(0)}%`, 'd-block mb-2');
    if (d.candle) addText(card,'div',`Vela de origen: ${d.candle}`, 'small mb-2');
    if (d.message || d.reason) addText(card,'div',(d.message || d.reason).slice(0,1800),'small');
    if (d.entry != null && d.sl != null && d.tp != null)
      addText(card,'div',`Niveles del análisis anterior: Entry ${d.entry} · SL ${d.sl} · TP ${d.tp} (históricos)`,'small mt-2');
    box.appendChild(card);
  }

  // Estos dos envoltorios no modifican parametros, retornos, estado ni errores
  // de los renderizadores NATIVOS. Solo guardan una copia visual ya mostrada.
  function installDisplayObservers() {
    if (typeof window.updateRecommendation === 'function') {
      const original = window.updateRecommendation;
      window.updateRecommendation = function (...args) {
        const result = original.apply(this,args);
        try { recordDecision(args[0]); } catch (_) {}
        return result;
      };
    }
    if (typeof window.updateCandleChart === 'function') {
      const original = window.updateCandleChart;
      window.updateCandleChart = function (...args) {
        const result = original.apply(this,args);
        try { recordChart(args[0]); } catch (_) {}
        return result;
      };
    }
  }
  function select() {
    const key = selected();
    if (!key || key === currentKey) return;
    currentKey = key;
    epoch++;
    lastNativeDecision = '';
    document.getElementById('str-c45v-rec-ref')?.remove();
    restoreChart(key);
    setTimeout(referenceRecommendation,500);
  }
  function init() {
    for (const id of ['symbol-select','interval-select'])
      document.getElementById(id)?.addEventListener('change',() => setTimeout(select,0));
    // Observador de cambios DOM, sin polling al servidor.
    const box = document.getElementById('system-recommendation');
    if (box && window.MutationObserver) {
      let queued = false;
      recObserver = new MutationObserver(() => {
        if (queued) return;
        queued = true;
        setTimeout(() => { queued = false; referenceRecommendation(); },250);
      });
      recObserver.observe(box,{childList:true,subtree:false});
    }
    select();
  }
  installDisplayObservers();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
  window.__STR_C45V_VISUAL_ONLY__ = {selected,cell,chartIsReal,validDecision};
})();
