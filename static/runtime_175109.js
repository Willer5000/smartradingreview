/* Commit 17.5.10.9 — signal-lane truth renderer + request dedupe.
 * No extra fetches, polling, market calls or signal promotion.
 */
(function () {
    'use strict';

    if (window.__ST175109_LOADED__) return;
    window.__ST175109_LOADED__ = true;

    const VERSION = '17.5.10.9';
    const lanePayloads = {vigent: null, previous: null, active: null};
    const laneBusy = {vigent: null, previous: null, active: null};

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function fmtPrice(value) {
        const n = num(value);
        if (n == null || n <= 0) return null;
        return n.toLocaleString(undefined, {maximumFractionDigits: 8});
    }

    function laneFromUrl(rawUrl) {
        const url = String(rawUrl || '');
        if (!/\/api\/(futures|multiasset)\//.test(url)) return null;
        if (/\/signals\/active(?:\?|$)/.test(url)) return 'vigent';
        if (/\/signals\/previous(?:\?|$)/.test(url)) return 'previous';
        if (/\/opportunities(?:\?|$)/.test(url)) return 'active';
        return null;
    }

    function allowedSymbol(row) {
        if (!window.IS_MULTI_ASSET_PAGE) return true;
        const allowed = new Set(Object.keys(window.PAGE_CONFIG?.symbols || {}));
        const symbol = String(row?.symbol || '').toUpperCase().replace('/', '-');
        return !allowed.size || allowed.has(symbol);
    }

    function candidateRows(payload, lane) {
        if (!payload || typeof payload !== 'object') return [];
        let rows = [];
        if (lane === 'vigent') {
            rows = Array.isArray(payload.vigent_other_directional_signals)
                ? payload.vigent_other_directional_signals
                : [];
        } else if (Array.isArray(payload.other_directional_signals)) {
            rows = payload.other_directional_signals;
        } else if (Array.isArray(payload.analysis_candidates)) {
            rows = payload.analysis_candidates;
        }

        const byCell = new Map();
        rows.forEach(raw => {
            if (!raw || typeof raw !== 'object' || !allowedSymbol(raw)) return;
            const action = String(raw.action || raw.diagnostic_action || '').toUpperCase();
            if (action !== 'LONG' && action !== 'SHORT') return;
            const classification = String(raw.classification || 'ANALYSIS_ONLY').toUpperCase();
            if (classification === 'EXECUTABLE_SIGNAL' || raw.is_executable === true) return;
            if (typeof window._isSignalSavedByCurrentUser === 'function' && window._isSignalSavedByCurrentUser(raw)) return;
            const key = `${String(raw.symbol || '')}|${String(raw.timeframe || '')}`;
            const score = num(raw.diagnostic_score) ?? num(raw.confidence) ?? num(raw.diagnostic_quality) ?? 0;
            const prev = byCell.get(key);
            const prevScore = prev ? (num(prev.diagnostic_score) ?? num(prev.confidence) ?? num(prev.diagnostic_quality) ?? 0) : -Infinity;
            if (!prev || score > prevScore) byCell.set(key, {...raw, action});
        });
        return Array.from(byCell.values()).sort((a, b) => {
            const sa = num(a.diagnostic_score) ?? num(a.confidence) ?? num(a.diagnostic_quality) ?? 0;
            const sb = num(b.diagnostic_score) ?? num(b.confidence) ?? num(b.diagnostic_quality) ?? 0;
            return sb - sa;
        });
    }

    function scoreBadge(row) {
        const kind = String(row.diagnostic_score_kind || '').toUpperCase();
        if (kind === 'THESIS_QUALITY') {
            const q = num(row.diagnostic_score) ?? num(row.diagnostic_quality) ?? num(row.thesis_quality);
            return q == null ? '' : `<span class="badge bg-dark">Calidad ${esc(q.toFixed(0))}/100</span>`;
        }
        if (kind === 'UNSCORED_DIRECTIONAL_THESIS') return '';
        const c = num(row.diagnostic_score) ?? num(row.confidence);
        return c == null || c <= 0 ? '' : `<span class="badge bg-dark">Confianza ${esc(c.toFixed(0))}%</span>`;
    }

    function stageBadge(row) {
        const stage = String(row.diagnostic_stage || '').toUpperCase();
        const labels = {
            CANDIDATE: 'CONFIRMACIÓN PENDIENTE',
            DIRECTION_CONFIRMATION: 'DIRECCIÓN PENDIENTE',
            ENTRY: 'ENTRY', SL: 'SL', TP: 'TP', RR: 'R/R', SAFETY: 'SAFETY',
            PUBLICATION: 'PUBLICACIÓN', OPPORTUNITY_RECOVERY: 'VALIDACIÓN FINAL'
        };
        return labels[stage] ? `<span class="badge bg-secondary">${esc(labels[stage])}</span>` : '';
    }

    function statusBadge(row) {
        const risk = String(row.manual_risk_class || '').toUpperCase();
        if (risk === 'MEDIUM') return '<span class="badge bg-warning text-dark">RIESGO MEDIO</span>';
        if (risk === 'HIGH') return '<span class="badge bg-danger">RIESGO ALTO</span>';
        const label = String(row.diagnostic_label || 'NO EJECUTABLE').toUpperCase().replace('PRECAUCION', 'PRECAUCIÓN');
        const cls = label === 'ESPERAR' ? 'bg-info text-dark' : 'bg-secondary';
        return `<span class="badge ${cls}">${esc(label)}</span>`;
    }

    function renderRow(row, lane) {
        const action = String(row.action || '').toUpperCase();
        const dirClass = action === 'LONG' ? 'success' : 'danger';
        const symbol = esc(String(row.display_name || row.symbol || '').replace('-', '/'));
        const tf = esc(row.timeframe || '--');
        const reason = esc(row.reason || row.manual_risk_reason || 'La hipótesis no superó una condición técnica de ejecución/publicación.');
        const metrics = [];
        const entry = fmtPrice(row.entry), sl = fmtPrice(row.stop_loss), tp = fmtPrice(row.take_profit);
        const rr = num(row.risk_reward), safety = num(row.execution_safety);
        if (entry) metrics.push(`Entry ${entry}`);
        if (sl) metrics.push(`SL ${sl}`);
        if (tp) metrics.push(`TP ${tp}`);
        if (rr != null && rr > 0) metrics.push(`R/R 1:${rr.toFixed(2)}`);
        if (safety != null && safety > 0) metrics.push(`Safety ${safety.toFixed(1)}`);
        const finalAction = String(row.final_action || '').toUpperCase().replace('PRECAUCION', 'PRECAUCIÓN');
        const finalHtml = finalAction && finalAction !== action && ['ESPERAR', 'PRECAUCIÓN'].includes(finalAction)
            ? `<div class="small text-info mt-1">Estado actual: ${esc(finalAction)}</div>` : '';

        let timeHtml = '';
        if (lane === 'vigent' && num(row.tiempo_restante) != null) {
            const sec = Math.max(0, Number(row.tiempo_restante));
            const mins = Math.floor(sec / 60);
            const hours = Math.floor(mins / 60);
            const rest = mins % 60;
            const label = hours > 0 ? `${hours}h ${rest}m` : `${mins}m`;
            timeHtml = `<div class="small text-warning mt-1">⏳ Vigencia restante: <strong>${esc(label)}</strong></div>`;
        }

        return `
            <div class="border-top border-secondary py-2 st175109-diagnostic-row">
                <div class="d-flex flex-wrap justify-content-between gap-2">
                    <div class="d-flex flex-wrap gap-1 align-items-center">
                        <span class="badge bg-${dirClass}">${esc(action)}</span>
                        <strong>${symbol}</strong><span class="badge bg-dark">${tf}</span>
                    </div>
                    <div class="d-flex flex-wrap gap-1 align-items-center">
                        ${statusBadge(row)} ${stageBadge(row)} ${scoreBadge(row)}
                    </div>
                </div>
                <div class="small text-light mt-2">${reason}</div>
                ${finalHtml}
                ${metrics.length ? `<div class="small text-muted mt-1">${metrics.map(esc).join(' · ')}</div>` : ''}
                ${timeHtml}
            </div>`;
    }

    function diagnosticsHtml(payload, lane) {
        const rows = candidateRows(payload, lane);
        const market = window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futures';
        if (!rows.length) {
            const health = payload?.pipeline_health || {};
            const analyzed = num(health.analyzed_cells);
            let extra = 'No hay otra hipótesis LONG/SHORT no ejecutable en el snapshot disponible.';
            if (analyzed === 0) {
                extra = `El snapshot de ${market} todavía no contiene celdas analizadas; un “0” aquí no equivale a que el mercado no tenga oportunidades.`;
            }
            return `
                <details class="mt-2 px-2 pb-2 st175109-diagnostics" data-st175109="1">
                    <summary class="text-secondary" style="cursor:pointer;">Por qué no aparecen otras señales (0)</summary>
                    <div class="small text-muted mt-2">${esc(extra)}</div>
                </details>`;
        }
        return `
            <details class="mt-2 px-2 pb-2 st175109-diagnostics" data-st175109="1">
                <summary class="text-warning" style="cursor:pointer;">Por qué no aparecen otras señales (${rows.length})</summary>
                <div class="small text-muted mt-2">
                    Hipótesis LONG/SHORT realmente presentes en el análisis que no fueron publicadas como señales ejecutables. Mostrar una hipótesis aquí no reduce los filtros ni la convierte en operación.
                </div>
                <div class="mt-2" style="max-height:420px; overflow-y:auto;">${rows.map(row => renderRow(row, lane)).join('')}</div>
            </details>`;
    }

    function removeLegacyDiagnostics(container) {
        if (!container) return;
        container.querySelectorAll('details').forEach(details => {
            const summary = details.querySelector('summary');
            if (summary && /Por qué no aparecen otras señales/i.test(summary.textContent || '')) details.remove();
        });
    }

    function renderLane(lane) {
        const payload = lanePayloads[lane];
        if (!payload) return;
        const html = diagnosticsHtml(payload, lane);

        if (lane === 'vigent') {
            const target = document.getElementById('vigent-signals-diagnostics');
            if (target) target.innerHTML = html;
        } else if (lane === 'active') {
            const target = document.getElementById('current-active-diagnostics');
            if (target) target.innerHTML = html;
        } else {
            const list = document.getElementById('prev-signals-list');
            if (!list) return;
            removeLegacyDiagnostics(list);
            let target = document.getElementById('prev-signals-diagnostics-175109');
            if (!target) {
                target = document.createElement('div');
                target.id = 'prev-signals-diagnostics-175109';
                list.insertAdjacentElement('afterend', target);
            }
            target.innerHTML = html;
        }

        if (window.IS_MULTI_ASSET_PAGE) relabelMultiAsset();
    }

    function capturePayload(response, lane) {
        try {
            response.clone().json().then(payload => {
                if (!payload || typeof payload !== 'object') return;
                lanePayloads[lane] = payload;
                window.setTimeout(() => renderLane(lane), 30);
            }).catch(() => {});
        } catch (_) {}
    }

    // Observe existing requests; this never adds one.
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async function(input, init) {
        const rawUrl = typeof input === 'string' ? input : (input && input.url) || '';
        const lane = laneFromUrl(rawUrl);
        const response = await nativeFetch(input, init);
        if (lane) capturePayload(response, lane);
        return response;
    };

    function wrapLaneFunction(name, lane) {
        const original = window[name];
        if (typeof original !== 'function' || original.__st175109Wrapped) return;
        const wrapped = async function(...args) {
            if (laneBusy[lane]) return laneBusy[lane];
            const promise = Promise.resolve().then(() => original.apply(this, args));
            laneBusy[lane] = promise;
            try {
                return await promise;
            } finally {
                laneBusy[lane] = null;
                window.setTimeout(() => renderLane(lane), 40);
            }
        };
        wrapped.__st175109Wrapped = true;
        wrapped.__st175109Original = original;
        window[name] = wrapped;
    }

    function relabelMultiAsset() {
        if (!window.IS_MULTI_ASSET_PAGE) return;
        ['active-signals-list', 'prev-signals-list', 'current-active-signals-list'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.querySelectorAll('*').forEach(node => {
                if (node.children.length === 0 && /Análisis de Futuros/i.test(node.textContent || '')) {
                    node.textContent = (node.textContent || '').replace(/Análisis de Futuros/gi, 'Análisis de Multi-Activo');
                }
            });
        });
    }

    function patchMultiExplanatoryText() {
        if (!window.IS_MULTI_ASSET_PAGE) return;
        const activeList = document.getElementById('current-active-signals-list');
        const card = activeList?.closest('.card');
        const small = card?.querySelector('.p-2.text-center small');
        if (small) {
            small.textContent = 'Oportunidades del análisis Multi-Activo disponible. La publicación conserva los mismos filtros técnicos; las hipótesis no ejecutables se explican por separado.';
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        // futures.js restores these globals in its own DOMContentLoaded handler;
        // ours runs after it because this runtime is injected later in the page.
        wrapLaneFunction('updateActiveSignals', 'vigent');
        wrapLaneFunction('updatePreviousSignals', 'previous');
        wrapLaneFunction('loadFuturesOpportunities96', 'active');
        relabelMultiAsset();
        patchMultiExplanatoryText();
        console.info(`✅ Frontend ${VERSION} activo · sin requests adicionales`);
    });
})();
