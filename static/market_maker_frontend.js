/*
 * Commit 17.5.10 FINAL — Black-Scholes / Gamma / 0DTE / Delta frontend.
 *
 * Conventional trader-facing terminology only. This panel reads the market-maker
 * mathematical context already returned by the analysis. It does NOT request a
 * second market analysis, does NOT create LONG/SHORT, and does NOT alter Safety.
 */
(function () {
    'use strict';

    if (window.__MM_OPTIONS_FRONTEND_17510__) return;
    window.__MM_OPTIONS_FRONTEND_17510__ = true;

    const byId = id => document.getElementById(id);
    const finite = value => {
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    };

    function price(value) {
        const n = finite(value);
        if (n === null) return '--';
        if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, {maximumFractionDigits: 2});
        if (Math.abs(n) >= 1) return n.toLocaleString(undefined, {maximumFractionDigits: 4});
        return n.toLocaleString(undefined, {maximumFractionDigits: 8});
    }

    function pct01(value) {
        const n = finite(value);
        if (n === null) return '--';
        return `${(n * 100).toFixed(1)}%`;
    }

    function humanRegime(value) {
        const v = String(value || '').toUpperCase();
        if (v === 'POSITIVE_GAMMA') return 'Gamma positiva';
        if (v === 'NEGATIVE_GAMMA') return 'Gamma negativa';
        if (v === 'MIXED_GAMMA') return 'Gamma mixta';
        return v ? v.replaceAll('_', ' ') : '--';
    }

    function extractContext(data) {
        return data?.levels?.market_maker_context
            || data?.market_maker_context
            || data?.data?.levels?.market_maker_context
            || null;
    }

    function setText(id, value) {
        const el = byId(id);
        if (el) el.textContent = value;
    }

    function renderUnavailable(reason) {
        const chart = byId('mm-options-chart');
        if (!chart) return;
        if (window.Plotly) {
            window.Plotly.purge(chart);
        }
        chart.innerHTML = `<div class="d-flex align-items-center justify-content-center h-100 text-center px-3">
            <div><div class="text-muted mb-1">Contexto de opciones no disponible para este activo.</div>
            <small class="text-muted">${String(reason || 'La fuente falló o no existe una cadena directamente compatible.').replace(/[<>]/g, '')}</small></div>
        </div>`;
        ['mm-gamma-regime','mm-zero-dte-share','mm-zero-gamma','mm-delta-neutral','mm-call-wall','mm-gamma-wall','mm-put-wall']
            .forEach(id => setText(id, '--'));
        setText('mm-option-source', 'Sin cadena compatible');
        setText('mm-option-authority', 'Sin datos observados: no se crea ningún sesgo direccional.');
    }

    function renderMarketMakerOptions(data) {
        const chart = byId('mm-options-chart');
        if (!chart || !window.Plotly) return;

        const mm = extractContext(data);
        if (!mm || mm.available === false) {
            renderUnavailable(mm?.reason);
            return;
        }

        const observed = mm.observed_option_chain === true;
        const authority = String(mm.authority || 'NO_AUTHORITY');
        setText('mm-option-source', observed ? 'Cadena observada' : 'Modelo teórico');
        setText('mm-gamma-regime', humanRegime(mm.gamma_regime));
        setText('mm-zero-dte-share', observed ? pct01(mm.zero_dte_gamma_share) : 'Teórico');
        setText('mm-zero-gamma', price(mm.zero_gamma_level));
        setText('mm-delta-neutral', price(mm.delta_neutral_level));
        setText('mm-call-wall', observed ? price(mm.call_wall) : '--');
        setText('mm-gamma-wall', observed ? price(mm.gamma_wall) : '--');
        setText('mm-put-wall', observed ? price(mm.put_wall) : '--');

        const sourceNote = observed
            ? `Cadena pública observada · ${Number(mm.contracts_used || 0)} contratos usados · vencimiento más cercano ${finite(mm.nearest_expiry_hours)?.toFixed(1) ?? '--'} h.`
            : 'Black-Scholes teórico sin Open Interest observado; sirve sólo para visualizar la forma de Gamma cerca del precio.';
        setText('mm-option-note', sourceNote);
        setText('mm-option-authority', observed
            ? 'GEX firmado usa CALL+ / PUT− como heurística. Open Interest no revela por sí solo el inventario real de market makers.'
            : 'Autoridad: SHADOW teórico. No cambia dirección, Entry, SL, TP, leverage ni Safety.');

        const gex = Array.isArray(mm.gex_curve) ? mm.gex_curve : [];
        const delta = Array.isArray(mm.delta_curve) ? mm.delta_curve : [];
        if (!gex.length || !delta.length) {
            renderUnavailable('El contexto no incluye curvas compactas.');
            return;
        }

        const gx = gex.map(row => Number(row?.[0])).filter(Number.isFinite);
        const gy = gex.map(row => Number(row?.[1]));
        const dx = delta.map(row => Number(row?.[0])).filter(Number.isFinite);
        const dy = delta.map(row => Number(row?.[1]));
        if (!gx.length || !dx.length || gy.some(v => !Number.isFinite(v)) || dy.some(v => !Number.isFinite(v))) {
            renderUnavailable('Curvas Black-Scholes incompletas.');
            return;
        }

        const traces = [
            {
                x: gx, y: gy, type: 'scatter', mode: 'lines',
                name: 'GEX firmado (heurístico)',
                hovertemplate: 'Subyacente %{x:.4f}<br>GEX %{y:.3s}<extra></extra>',
                line: {width: 2.4}
            },
            {
                x: dx, y: dy, type: 'scatter', mode: 'lines', yaxis: 'y2',
                name: 'Delta neta (heurística)',
                hovertemplate: 'Subyacente %{x:.4f}<br>Delta $ %{y:.3s}<extra></extra>',
                line: {width: 2.0, dash: 'dot'}
            }
        ];

        const shapes = [];
        const addVertical = (value, dash) => {
            const v = finite(value);
            if (v === null) return;
            shapes.push({type:'line', x0:v, x1:v, y0:0, y1:1, yref:'paper', line:{width:1.2, dash:dash || 'dot'}});
        };
        addVertical(mm.spot, 'solid');
        addVertical(mm.zero_gamma_level, 'dash');
        addVertical(mm.delta_neutral_level, 'dot');

        const annotations = [];
        const ann = (value, text, ypos) => {
            const v = finite(value);
            if (v === null) return;
            annotations.push({x:v, y:ypos, yref:'paper', text, showarrow:false, textangle:-90, xanchor:'right'});
        };
        ann(mm.spot, 'Spot', 0.97);
        ann(mm.zero_gamma_level, 'Zero Γ', 0.80);
        ann(mm.delta_neutral_level, 'Δ neutral', 0.62);

        const layout = {
            margin: {l:60, r:70, t:32, b:48},
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: {color:'#cfd8dc'},
            legend: {orientation:'h', y:1.12, x:0},
            xaxis: {title:'Precio del subyacente', gridcolor:'rgba(255,255,255,0.08)'},
            yaxis: {title:'Gamma Exposure', gridcolor:'rgba(255,255,255,0.08)', zeroline:true},
            yaxis2: {title:'Delta $', overlaying:'y', side:'right', showgrid:false, zeroline:true},
            shapes,
            annotations,
            hovermode:'x unified',
            uirevision: `${window.currentSymbol || ''}-${window.currentInterval || ''}`
        };
        window.Plotly.react(chart, traces, layout, {responsive:true, displaylogo:false});
    }

    window.updateMarketMakerOptionsChart = renderMarketMakerOptions;

    function installHook() {
        if (window.__MM_OPTIONS_UPDATE_HOOKED__) return;
        if (typeof window.updateAllCharts !== 'function') return;
        const original = window.updateAllCharts;
        window.updateAllCharts = function (data) {
            const result = original.apply(this, arguments);
            try { renderMarketMakerOptions(data); } catch (error) { console.debug('MM options chart:', error); }
            return result;
        };
        window.__MM_OPTIONS_UPDATE_HOOKED__ = true;
        try {
            if (window.currentAnalysis) renderMarketMakerOptions(window.currentAnalysis);
        } catch (_) {}
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installHook, {once:true});
    } else {
        installHook();
    }
    // In case script.js is deferred/reloaded by the page, one bounded retry.
    setTimeout(installHook, 800);
})();
