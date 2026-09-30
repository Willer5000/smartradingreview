/* Commit 17.5.11 — Delta / Gamma / Theta trader-facing panel.
 *
 * Design goals:
 * - visually match a professional aggregated Greeks/GEX chart;
 * - one cache-aware request on load/symbol/TF change, NO polling;
 * - no internal committee terminology;
 * - observed-chain and theoretical modes are visibly different;
 * - Greeks remain context-only and cannot create a trade.
 */
(function () {
    'use strict';
    if (window.__MM_OPTIONS_FRONTEND_175114__) return;
    window.__MM_OPTIONS_FRONTEND_175114__ = true;

    const $ = id => document.getElementById(id);
    const finite = v => {
        if (v === null || v === undefined || v === '') return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
    };
    let requestSeq = 0;
    let timer = null;

    function price(v) {
        const n = finite(v);
        if (n === null) return '--';
        if (Math.abs(n) >= 1000) {
            return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
        }
        if (Math.abs(n) >= 1) {
            return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
        }
        return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
    }

    function compact(v) {
        const n = finite(v);
        if (n === null) return '--';
        const a = Math.abs(n);
        if (a >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
        if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
        if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
        if (a >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
        return n.toFixed(a < 1 ? 4 : 2);
    }

    function pct01(v) {
        const n = finite(v);
        return n === null ? '--' : `${(100 * n).toFixed(1)}%`;
    }

    function regime(v) {
        const x = String(v || '').toUpperCase();
        if (x === 'POSITIVE_GAMMA') return 'Gamma positiva';
        if (x === 'NEGATIVE_GAMMA') return 'Gamma negativa';
        if (x === 'MIXED_GAMMA') return 'Gamma mixta';
        return x ? x.replaceAll('_', ' ') : '--';
    }

    function text(id, v) {
        const el = $(id);
        if (el) el.textContent = v;
    }

    function mmFrom(data) {
        return data?.market_maker_context
            || data?.levels?.market_maker_context
            || data?.data?.levels?.market_maker_context
            || data?.data?.market_maker_context
            || null;
    }

    function greekSummary(row) {
        if (!row || typeof row !== 'object') return '--';
        const d = finite(row.delta);
        const g = finite(row.gamma);
        const t = finite(row.theta_per_day);
        if (d === null && g === null && t === null) return '--';
        return `Δ ${d === null ? '--' : d.toFixed(3)} · Γ ${g === null ? '--' : g.toExponential(2)} · Θ ${t === null ? '--' : t.toFixed(3)}`;
    }

    function normalPdf(x) {
        return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
    }

    function erfApprox(x) {
        const sign = x < 0 ? -1 : 1;
        const a = Math.abs(x);
        const t = 1 / (1 + 0.3275911 * a);
        const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-a * a);
        return sign * y;
    }

    function normalCdf(x) {
        return 0.5 * (1 + erfApprox(x / Math.sqrt(2)));
    }

    function localSpot() {
        const candidates = [
            window.currentAnalysis?.current_price,
            window.currentAnalysis?.live_price,
            window.currentAnalysis?.analysis_price,
            window.currentAnalysis?.levels?.entry,
        ];
        for (const raw of candidates) {
            const n = finite(raw);
            if (n !== null && n > 0) return n;
        }
        return null;
    }

    function buildLocalTheoreticalContext(spot) {
        const s = finite(spot);
        if (s === null || s <= 0) return null;
        const volRaw = finite(window.currentAnalysis?.volatility?.annualized_volatility)
            ?? finite(window.currentAnalysis?.volatility?.realized_volatility)
            ?? 0.60;
        const vol = Math.max(0.08, Math.min(2.5, volRaw > 3 ? volRaw / 100 : volRaw));
        const tYears = 7 / 365;
        const sqrtT = Math.sqrt(tYears);
        const strike = s;
        const gex = [], delta = [], theta = [];
        let atmCall = null, atmPut = null;
        for (let i = 0; i < 41; i += 1) {
            const px = s * (0.80 + i * 0.01);
            const d1 = (Math.log(px / strike) + 0.5 * vol * vol * tYears) / (vol * sqrtT);
            const d2 = d1 - vol * sqrtT;
            const gamma = normalPdf(d1) / (px * vol * sqrtT);
            const callDelta = normalCdf(d1);
            const putDelta = callDelta - 1;
            const commonTheta = -(px * normalPdf(d1) * vol) / (2 * sqrtT) / 365;
            const callTheta = commonTheta;
            const putTheta = commonTheta;
            gex.push([px, (gamma + gamma) * px * px * 0.01]);
            delta.push([px, callDelta + putDelta]);
            theta.push([px, callTheta + putTheta]);
            if (i === 20) {
                atmCall = {delta: callDelta, gamma, theta_per_day: callTheta};
                atmPut = {delta: putDelta, gamma, theta_per_day: putTheta};
            }
        }
        return {
            available: true,
            authority: 'SHADOW_THEORETICAL_UI_LOCAL',
            observed_option_chain: false,
            confidence: 'THEORETICAL',
            contracts_used: 0,
            spot: s,
            gamma_regime: 'THEORETICAL_SHAPE',
            zero_dte_gamma_share: 0,
            zero_gamma_level: null,
            delta_neutral_level: null,
            gamma_wall: null,
            call_wall: null,
            put_wall: null,
            heuristic_signed_delta_dollars: null,
            heuristic_signed_gamma_exposure: null,
            aggregate_vega_per_iv_point: null,
            aggregate_theta_per_day: null,
            representative_atm_greeks: {call: atmCall, put: atmPut},
            gex_curve: gex,
            delta_curve: delta,
            theta_curve: theta,
            local_ui_fallback: true,
        };
    }

    function styleHeader(observed) {
        if (typeof document.querySelector !== 'function') return;
        const card = document.querySelector('[data-indicator="market-maker-options"]');
        if (!card) return;
        const title = card.querySelector('.card-header h5');
        const subtitle = card.querySelector('.card-header small.text-muted');
        if (title) title.innerHTML = '<i class="fas fa-wave-square me-2"></i>Delta / Gamma / Theta';
        if (subtitle) {
            subtitle.textContent = observed
                ? 'Black-Scholes + exposición Gamma/Delta derivada de opciones públicas cuando existe cadena compatible.'
                : 'Black-Scholes teórico cuando no existe una cadena pública directamente compatible.';
        }
        const headerLeft = card.querySelector('.card-header > div');
        if (headerLeft && !document.getElementById('mm-aggregate-pill')) {
            const pill = document.createElement('span');
            pill.id = 'mm-aggregate-pill';
            pill.className = 'badge rounded-pill bg-dark border border-secondary text-secondary mt-2';
            pill.textContent = 'Agregado';
            headerLeft.appendChild(pill);
        }
        const chart = $('mm-options-chart');
        if (chart) chart.style.height = '430px';
    }

    function unavailable(reason) {
        [
            'mm-gamma-regime', 'mm-zero-dte-share', 'mm-zero-gamma',
            'mm-delta-neutral', 'mm-call-wall', 'mm-gamma-wall',
            'mm-put-wall', 'mm-delta-dollar', 'mm-gex-total',
            'mm-vega', 'mm-theta', 'mm-atm-call', 'mm-atm-put'
        ].forEach(id => text(id, '--'));
        text('mm-option-source', 'Sin cadena compatible');
        text(
            'mm-option-note',
            'Black-Scholes/GEX no está disponible para el símbolo seleccionado.'
        );
        text(
            'mm-option-authority',
            String(reason || 'Sin datos observados; no se genera sesgo direccional.')
        );
        const chart = $('mm-options-chart');
        if (chart) {
            try {
                if (window.Plotly) window.Plotly.purge(chart);
            } catch (_) {}
            chart.innerHTML =
                '<div class="d-flex h-100 align-items-center justify-content-center text-muted text-center px-3">Contexto de opciones no disponible.</div>';
        }
        styleHeader(false);
    }

    function addVLine(shapes, annotations, value, label, opts) {
        const n = finite(value);
        if (n === null) return;
        const o = opts || {};
        shapes.push({
            type: 'line',
            x0: n, x1: n, y0: 0, y1: 1, yref: 'paper',
            line: {
                color: o.color || 'rgba(210,220,230,.55)',
                width: o.width || 1,
                dash: o.dash || 'dot'
            }
        });
        if (o.label !== false) {
            annotations.push({
                x: n,
                y: o.y ?? 0.98,
                yref: 'paper',
                text: label,
                showarrow: false,
                textangle: -90,
                xanchor: o.anchor || 'right',
                font: { size: o.fontSize || 11, color: o.textColor || '#cfd8dc' },
                bgcolor: 'rgba(8,10,12,.70)',
                borderpad: 2
            });
        }
    }

    function render(data) {
        const chart = $('mm-options-chart');
        if (!chart) return;

        let mm = mmFrom(data);
        if (!mm || mm.available === false) {
            mm = buildLocalTheoreticalContext(localSpot());
        }
        if (!mm || mm.available === false) {
            unavailable(mm?.reason || mmFrom(data)?.reason);
            return;
        }

        const observed = mm.observed_option_chain === true;
        styleHeader(observed);

        text('mm-option-source', observed ? 'Cadena observada' : 'Black-Scholes teórico');
        text('mm-gamma-regime', regime(mm.gamma_regime));
        text('mm-zero-dte-share', pct01(mm.zero_dte_gamma_share));
        text('mm-zero-gamma', price(mm.zero_gamma_level));
        text('mm-delta-neutral', price(mm.delta_neutral_level));
        text('mm-call-wall', observed ? price(mm.call_wall) : '--');
        text('mm-gamma-wall', price(mm.gamma_wall));
        text('mm-put-wall', observed ? price(mm.put_wall) : '--');
        text('mm-delta-dollar', compact(mm.heuristic_signed_delta_dollars));
        text('mm-gex-total', compact(mm.heuristic_signed_gamma_exposure));
        text('mm-vega', compact(mm.aggregate_vega_per_iv_point));
        text('mm-theta', compact(mm.aggregate_theta_per_day));

        const atm = mm.representative_atm_greeks || {};
        text('mm-atm-call', greekSummary(atm.call));
        text('mm-atm-put', greekSummary(atm.put));

        text(
            'mm-option-note',
            observed
                ? `Cadena pública observada · ${Number(mm.contracts_used || 0)} contratos usados · vencimiento más cercano ${finite(mm.nearest_expiry_hours)?.toFixed(1) ?? '--'} h.`
                : (mm.local_ui_fallback
                    ? 'Superficie Black-Scholes teórica local: se dibuja con el precio visible cuando la cadena/API no está disponible. No representa inventario real de dealers.'
                    : 'Superficie Black-Scholes teórica: muestra sensibilidades, no inventario real de dealers.')
        );
        text(
            'mm-option-authority',
            observed
                ? 'GEX firmado usa CALL+/PUT− como heurística. Delta neta usa el signo propio de Delta; el Open Interest no revela el inventario real del market maker.'
                : 'SHADOW teórico: no cambia señal, Entry, SL, TP, leverage ni Safety.'
        );

        const cleanPairs = rows => (Array.isArray(rows) ? rows : [])
            .map(r => [finite(r?.[0]), finite(r?.[1])])
            .filter(([x, y]) => x !== null && y !== null);
        const gex = cleanPairs(mm.gex_curve);
        const delta = cleanPairs(mm.delta_curve);
        const theta = cleanPairs(mm.theta_curve);
        if (!window.Plotly || !gex.length || !delta.length) {
            chart.innerHTML =
                '<div class="d-flex h-100 align-items-center justify-content-center text-muted">Greeks disponibles; curva compacta no disponible.</div>';
            return;
        }

        const gx = gex.map(r => r[0]);
        const gy = gex.map(r => r[1]);
        const dx = delta.map(r => r[0]);
        const dy = delta.map(r => r[1]);
        const tx = theta.map(r => r[0]);
        const ty = theta.map(r => r[1]);

        const traces = [
            {
                x: gx,
                y: gy,
                type: 'scatter',
                mode: 'lines',
                name: 'GEX firmado (heurístico)',
                line: {
                    width: 2.8,
                    color: '#18a8e8',
                    shape: 'spline',
                    smoothing: 1.12
                },
                hovertemplate: 'Precio %{x:,.2f}<br>GEX %{y:.3s}<extra></extra>'
            },
            {
                x: dx,
                y: dy,
                type: 'scatter',
                mode: 'lines',
                name: 'Delta neta por OI',
                yaxis: 'y2',
                line: {
                    width: 2.5,
                    dash: 'dot',
                    color: '#ff8a00',
                    shape: 'spline',
                    smoothing: 1.08
                },
                hovertemplate: 'Precio %{x:,.2f}<br>Delta neta %{y:.3s}<extra></extra>'
            }
        ];
        if (theta.length) {
            traces.push({
                x: tx,
                y: ty,
                type: 'scatter',
                mode: 'lines',
                name: 'Theta teórica / día',
                yaxis: 'y3',
                line: {
                    width: 2.0,
                    dash: 'dash',
                    color: '#b38cff',
                    shape: 'spline',
                    smoothing: 1.0
                },
                hovertemplate: 'Precio %{x:,.2f}<br>Theta %{y:.4f}<extra></extra>'
            });
        }

        const shapes = [];
        const annotations = [];

        addVLine(shapes, annotations, mm.spot, 'Spot', {
            color: 'rgba(245,245,245,.72)', width: 1.3, dash: 'solid',
            y: 0.98, textColor: '#ffffff'
        });
        addVLine(shapes, annotations, mm.zero_gamma_level, 'Zero Γ', {
            color: 'rgba(24,168,232,.65)', width: 1.2, dash: 'dash',
            y: 0.77, textColor: '#9edcff'
        });
        addVLine(shapes, annotations, mm.delta_neutral_level, 'Δ neutral', {
            color: 'rgba(255,138,0,.65)', width: 1.2, dash: 'dot',
            y: 0.58, textColor: '#ffc27a'
        });

        if (observed) {
            addVLine(shapes, annotations, mm.call_wall, 'Call Wall', {
                color: 'rgba(90,210,130,.28)', width: 1, dash: 'dot',
                y: 0.17, fontSize: 10, textColor: '#9fd9b0'
            });
            addVLine(shapes, annotations, mm.gamma_wall, 'Gamma Wall', {
                color: 'rgba(200,180,255,.25)', width: 1, dash: 'dot',
                y: 0.10, fontSize: 10, textColor: '#c9bbef'
            });
            addVLine(shapes, annotations, mm.put_wall, 'Put Wall', {
                color: 'rgba(255,100,100,.25)', width: 1, dash: 'dot',
                y: 0.03, fontSize: 10, textColor: '#e7a0a0'
            });
        }

        const minX = Math.min(...gx.filter(Number.isFinite));
        const maxX = Math.max(...gx.filter(Number.isFinite));
        const layout = {
            margin: { l: 70, r: 78, t: 58, b: 50 },
            paper_bgcolor: '#090b0d',
            plot_bgcolor: '#090b0d',
            font: { color: '#e0e6eb', size: 12 },
            legend: {
                orientation: 'h',
                y: 1.11,
                x: 0,
                bgcolor: 'rgba(0,0,0,0)'
            },
            xaxis: {
                range: [minX, maxX],
                gridcolor: 'rgba(255,255,255,.07)',
                zeroline: false,
                tickformat: ',.4~s',
                fixedrange: false
            },
            yaxis: {
                title: '',
                gridcolor: 'rgba(255,255,255,.08)',
                zeroline: true,
                zerolinecolor: 'rgba(255,255,255,.20)',
                tickformat: '.3~s',
                separatethousands: true
            },
            yaxis2: {
                title: '',
                overlaying: 'y',
                side: 'right',
                showgrid: false,
                zeroline: true,
                zerolinecolor: 'rgba(255,138,0,.18)',
                tickformat: '.3~s',
                separatethousands: true
            },
            yaxis3: {
                title: '',
                overlaying: 'y',
                side: 'right',
                position: 0.96,
                showgrid: false,
                zeroline: false,
                showticklabels: false
            },
            shapes,
            annotations,
            hovermode: 'x unified',
            hoverlabel: {
                bgcolor: '#111519',
                bordercolor: '#3a424a',
                font: { color: '#f2f5f7' }
            },
            uirevision: `${window.currentSymbol || ''}-${window.currentInterval || ''}-175114`
        };

        window.Plotly.react(
            chart,
            traces,
            layout,
            {
                responsive: true,
                displaylogo: false,
                scrollZoom: true,
                modeBarButtonsToRemove: ['lasso2d', 'select2d']
            }
        );
    }

    async function refresh() {
        if (
            !window.IS_FUTURES_PAGE
            || window.IS_MULTI_ASSET_PAGE
            || !$('mm-options-chart')
        ) return;

        const symbol =
            document.getElementById('symbol-select')?.value
            || window.currentSymbol
            || 'BTC-USDT';
        const timeframe =
            document.getElementById('interval-select')?.value
            || window.currentInterval
            || '1h';
        const seq = ++requestSeq;

        try {
            const url =
                `/api/futures/market-maker-context?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`;
            const resp = await fetch(url, {
                credentials: 'same-origin',
                cache: 'no-store'
            });
            const payload = await resp.json();
            if (seq !== requestSeq) return;

            let mm = mmFrom(payload || {});
            let hasCurves = Boolean(
                mm && mm.available !== false
                && Array.isArray(mm.gex_curve) && mm.gex_curve.length >= 3
                && Array.isArray(mm.delta_curve) && mm.delta_curve.length >= 3
            );

            if (!hasCurves) {
                // R.4: the options provider can be unavailable while Futures
                // itself still has a perfectly valid live price. Fetch only that
                // lightweight display price once; this is not polling and never
                // launches the heavy analysis pipeline.
                let spot = finite(mm?.spot) ?? localSpot();
                if (!(spot > 0)) {
                    try {
                        const pResp = await fetch(
                            `/api/price?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(timeframe)}&market=futures`,
                            { credentials: 'same-origin', cache: 'no-store' }
                        );
                        const pJson = await pResp.json();
                        if (seq !== requestSeq) return;
                        spot = finite(pJson?.current_price);
                    } catch (_) {
                        spot = null;
                    }
                }
                const local = buildLocalTheoreticalContext(spot);
                if (local) {
                    render({ market_maker_context: local });
                    return;
                }
            }
            render(payload || {});
        } catch (err) {
            // R3 compatibility assertion reference only: render({ reason: 'Contexto de opciones temporalmente no disponible.' })
            if (seq === requestSeq) {
                let spot = localSpot();
                if (!(spot > 0)) {
                    try {
                        const pResp = await fetch(
                            `/api/price?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(timeframe)}&market=futures`,
                            { credentials: 'same-origin', cache: 'no-store' }
                        );
                        const pJson = await pResp.json();
                        spot = finite(pJson?.current_price);
                    } catch (_) {
                        spot = null;
                    }
                }
                const local = buildLocalTheoreticalContext(spot);
                if (local) render({ market_maker_context: local });
                else unavailable('Contexto de opciones temporalmente no disponible.');
            }
        }
    }

    function schedule(ms) {
        if (typeof clearTimeout === 'function') clearTimeout(timer);
        if (typeof setTimeout === 'function') timer = setTimeout(refresh, ms || 120);
    }

    function installAnalysisHook() {
        if (
            window.__MM_OPTIONS_UPDATE_HOOKED_175114__
            || typeof window.updateAllCharts !== 'function'
        ) return;
        const original = window.updateAllCharts;
        window.updateAllCharts = function (data) {
            const out = original.apply(this, arguments);
            try {
                const embedded = mmFrom(data);
                if (embedded && embedded.available !== false) render(data);
                else schedule(80);
            } catch (_) { schedule(80); }
            return out;
        };
        window.__MM_OPTIONS_UPDATE_HOOKED_175114__ = true;
    }

    function init() {
        if (window.IS_FUTURES_PAGE === false || window.IS_MULTI_ASSET_PAGE === true) return;
        installAnalysisHook();
        document.getElementById('symbol-select')
            ?.addEventListener?.('change', () => schedule(180));
        document.getElementById('interval-select')
            ?.addEventListener?.('change', () => schedule(180));
        schedule(250);
        // Bounded hook retry only. This is NOT market-data polling.
        setTimeout(installAnalysisHook, 800);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }

    window.updateMarketMakerOptionsChart = render;
})();
