/* Commit 17.5.10.1 — trader-facing Greeks / Gamma / 0DTE.
 * Lightweight: one cache-aware request on load/symbol/TF change. No polling,
 * no full market analysis, no direction/Entry/SL/TP/Safety authority.
 */
(function () {
    'use strict';
    if (window.__MM_OPTIONS_FRONTEND_175101__) return;
    window.__MM_OPTIONS_FRONTEND_175101__ = true;

    const $ = id => document.getElementById(id);
    const finite = v => { const n = Number(v); return Number.isFinite(n) ? n : null; };
    let requestSeq = 0;
    let timer = null;

    function price(v) {
        const n = finite(v); if (n === null) return '--';
        if (Math.abs(n) >= 1000) return n.toLocaleString(undefined,{maximumFractionDigits:2});
        if (Math.abs(n) >= 1) return n.toLocaleString(undefined,{maximumFractionDigits:4});
        return n.toLocaleString(undefined,{maximumFractionDigits:8});
    }
    function compact(v) {
        const n=finite(v); if(n===null) return '--';
        const a=Math.abs(n);
        if(a>=1e12) return `${(n/1e12).toFixed(2)}T`;
        if(a>=1e9) return `${(n/1e9).toFixed(2)}B`;
        if(a>=1e6) return `${(n/1e6).toFixed(2)}M`;
        if(a>=1e3) return `${(n/1e3).toFixed(2)}K`;
        return n.toFixed(a < 1 ? 4 : 2);
    }
    function pct01(v) { const n=finite(v); return n===null?'--':`${(100*n).toFixed(1)}%`; }
    function regime(v) {
        const x=String(v||'').toUpperCase();
        if(x==='POSITIVE_GAMMA') return 'Gamma positiva';
        if(x==='NEGATIVE_GAMMA') return 'Gamma negativa';
        if(x==='MIXED_GAMMA') return 'Gamma mixta';
        return x ? x.replaceAll('_',' ') : '--';
    }
    function text(id,v){ const el=$(id); if(el) el.textContent=v; }
    function mmFrom(data){
        return data?.market_maker_context
            || data?.levels?.market_maker_context
            || data?.data?.levels?.market_maker_context
            || data?.data?.market_maker_context
            || null;
    }
    function greekSummary(row) {
        if(!row || typeof row!=='object') return '--';
        const d=finite(row.delta), g=finite(row.gamma), t=finite(row.theta_per_day);
        if(d===null && g===null && t===null) return '--';
        return `Δ ${d===null?'--':d.toFixed(3)} · Γ ${g===null?'--':g.toExponential(2)} · Θ ${t===null?'--':t.toFixed(3)}`;
    }

    function unavailable(reason) {
        ['mm-gamma-regime','mm-zero-dte-share','mm-zero-gamma','mm-delta-neutral',
         'mm-call-wall','mm-gamma-wall','mm-put-wall','mm-delta-dollar','mm-gex-total',
         'mm-vega','mm-theta','mm-atm-call','mm-atm-put'].forEach(id=>text(id,'--'));
        text('mm-option-source','Sin cadena compatible');
        text('mm-option-note','Black-Scholes/GEX no está disponible para el símbolo seleccionado.');
        text('mm-option-authority',String(reason||'Sin datos observados; no se genera sesgo direccional.'));
        const chart=$('mm-options-chart');
        if(chart){
            try { if(window.Plotly) window.Plotly.purge(chart); } catch(_){}
            chart.innerHTML='<div class="d-flex h-100 align-items-center justify-content-center text-muted text-center px-3">Sin contexto de opciones compatible.</div>';
        }
    }

    function render(data) {
        const chart=$('mm-options-chart');
        if(!chart) return;
        const mm=mmFrom(data);
        if(!mm || mm.available===false){ unavailable(mm?.reason); return; }
        const observed=mm.observed_option_chain===true;
        text('mm-option-source', observed ? 'Cadena observada' : 'Black-Scholes teórico');
        text('mm-gamma-regime',regime(mm.gamma_regime));
        text('mm-zero-dte-share',pct01(mm.zero_dte_gamma_share));
        text('mm-zero-gamma',price(mm.zero_gamma_level));
        text('mm-delta-neutral',price(mm.delta_neutral_level));
        text('mm-call-wall',observed?price(mm.call_wall):'--');
        text('mm-gamma-wall',price(mm.gamma_wall));
        text('mm-put-wall',observed?price(mm.put_wall):'--');
        text('mm-delta-dollar',compact(mm.heuristic_signed_delta_dollars));
        text('mm-gex-total',compact(mm.heuristic_signed_gamma_exposure));
        text('mm-vega',compact(mm.aggregate_vega_per_iv_point));
        text('mm-theta',compact(mm.aggregate_theta_per_day));
        const atm=mm.representative_atm_greeks||{};
        text('mm-atm-call',greekSummary(atm.call));
        text('mm-atm-put',greekSummary(atm.put));
        text('mm-option-note', observed
            ? `Cadena pública observada · ${Number(mm.contracts_used||0)} contratos · vencimiento más cercano ${finite(mm.nearest_expiry_hours)?.toFixed(1)??'--'} h.`
            : 'Superficie Black-Scholes teórica: muestra sensibilidades, no inventario real de dealers.');
        text('mm-option-authority', observed
            ? 'GEX firmado CALL+/PUT− es heurístico: el Open Interest no revela por sí solo el inventario real del market maker.'
            : 'SHADOW teórico: no cambia señal, Entry, SL, TP, leverage ni Safety.');

        const gex=Array.isArray(mm.gex_curve)?mm.gex_curve:[];
        const delta=Array.isArray(mm.delta_curve)?mm.delta_curve:[];
        if(!window.Plotly || !gex.length || !delta.length){
            chart.innerHTML='<div class="d-flex h-100 align-items-center justify-content-center text-muted">Greeks disponibles; curva compacta no disponible.</div>';
            return;
        }
        const traces=[
            {x:gex.map(r=>Number(r?.[0])),y:gex.map(r=>Number(r?.[1])),type:'scatter',mode:'lines',name:'Gamma Exposure',line:{width:2.4},hovertemplate:'Precio %{x:.4f}<br>GEX %{y:.3s}<extra></extra>'},
            {x:delta.map(r=>Number(r?.[0])),y:delta.map(r=>Number(r?.[1])),type:'scatter',mode:'lines',name:'Delta $',yaxis:'y2',line:{width:2,dash:'dot'},hovertemplate:'Precio %{x:.4f}<br>Delta $ %{y:.3s}<extra></extra>'}
        ];
        const shapes=[]; const anns=[];
        function vline(v,label,dash,y){ const n=finite(v); if(n===null)return; shapes.push({type:'line',x0:n,x1:n,y0:0,y1:1,yref:'paper',line:{width:1.2,dash:dash}}); anns.push({x:n,y:y,yref:'paper',text:label,showarrow:false,textangle:-90,xanchor:'right'}); }
        vline(mm.spot,'Spot','solid',0.97); vline(mm.zero_gamma_level,'Zero Γ','dash',0.80); vline(mm.delta_neutral_level,'Δ neutral','dot',0.62);
        window.Plotly.react(chart,traces,{
            margin:{l:60,r:70,t:35,b:48},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:'#cfd8dc'},
            legend:{orientation:'h',y:1.12,x:0},xaxis:{title:'Precio del subyacente',gridcolor:'rgba(255,255,255,.08)'},
            yaxis:{title:'Gamma Exposure',gridcolor:'rgba(255,255,255,.08)',zeroline:true},yaxis2:{title:'Delta $',overlaying:'y',side:'right',showgrid:false,zeroline:true},
            shapes:shapes,annotations:anns,hovermode:'x unified',uirevision:`${window.currentSymbol||''}-${window.currentInterval||''}`
        },{responsive:true,displaylogo:false});
    }

    async function refresh() {
        if(!window.IS_FUTURES_PAGE || window.IS_MULTI_ASSET_PAGE || !$('mm-options-chart')) return;
        const symbol=document.getElementById('symbol-select')?.value || window.currentSymbol || 'BTC-USDT';
        const timeframe=document.getElementById('interval-select')?.value || window.currentInterval || '1h';
        const seq=++requestSeq;
        try {
            const url=`/api/futures/market-maker-context?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`;
            const resp=await fetch(url,{credentials:'same-origin',cache:'no-store'});
            const payload=await resp.json();
            if(seq!==requestSeq) return;
            if(payload?.success) render(payload); else unavailable(payload?.error);
        } catch(err) {
            if(seq===requestSeq) unavailable('Contexto de opciones temporalmente no disponible.');
        }
    }
    function schedule(ms){ clearTimeout(timer); timer=setTimeout(refresh,ms||120); }

    // Also consume the already-computed analysis if present; no request needed.
    function installAnalysisHook(){
        if(window.__MM_OPTIONS_UPDATE_HOOKED_175101__ || typeof window.updateAllCharts!=='function') return;
        const original=window.updateAllCharts;
        window.updateAllCharts=function(data){ const out=original.apply(this,arguments); try{render(data);}catch(_){} return out; };
        window.__MM_OPTIONS_UPDATE_HOOKED_175101__=true;
    }
    function init(){
        if(!window.IS_FUTURES_PAGE || window.IS_MULTI_ASSET_PAGE) return;
        installAnalysisHook();
        document.getElementById('symbol-select')?.addEventListener('change',()=>schedule(180));
        document.getElementById('interval-select')?.addEventListener('change',()=>schedule(180));
        schedule(250);
        // One bounded hook retry only; never poll market data.
        setTimeout(installAnalysisHook,800);
    }
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true}); else init();
    window.updateMarketMakerOptionsChart=render;
})();
