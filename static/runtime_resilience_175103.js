/* Commit 17.5.10.3 — UI read resilience and truthful empty-state diagnostics.
 * No polling, no automatic retry and no new endpoint.
 */
(function () {
    'use strict';
    if (window.__RUNTIME_RESILIENCE_175103__) return;
    window.__RUNTIME_RESILIENCE_175103__ = true;

    // Cached signal/risk reads can be delayed by the single Render worker while
    // the heavy slot is yielding CPU. Give them the same bounded window as the
    // interactive Futures analysis, without issuing an extra request.
    if (typeof window._futFetchBounded === 'function') {
        window._futFetchBounded = async function (url, options = {}, timeoutMs = 25000) {
            const method = String(options.method || 'GET').toUpperCase();
            const controller = new AbortController();
            const externalSignal = options.signal;
            const relayAbort = () => controller.abort();
            if (externalSignal) {
                if (externalSignal.aborted) controller.abort();
                else externalSignal.addEventListener('abort', relayAbort, {once: true});
            }
            const effectiveTimeout = Math.max(4000, Number(timeoutMs || 25000));
            const timer = window.setTimeout(() => controller.abort(), effectiveTimeout);
            try {
                return await fetch(url, {...options, method, signal: controller.signal});
            } catch (error) {
                if (error && error.name === 'AbortError') {
                    const bounded = new Error(`La consulta excedió ${Math.round(effectiveTimeout / 1000)} segundos; se conserva la vista y puedes reintentar.`);
                    bounded.name = 'BoundedReadTimeout';
                    throw bounded;
                }
                throw error;
            } finally {
                window.clearTimeout(timer);
                if (externalSignal) externalSignal.removeEventListener?.('abort', relayAbort);
            }
        };
    }

    // Avoid duplicated risk-profile reads during rapid Futures/Multi navigation.
    if (typeof window.loadFuturesRiskProfile === 'function') {
        const originalRiskLoad = window.loadFuturesRiskProfile;
        let inFlight = null;
        let lastSuccessAt = 0;
        window.loadFuturesRiskProfile = function (options = {}) {
            const silent = Boolean(options && options.silent);
            if (silent && Date.now() - lastSuccessAt < 120000) {
                return Promise.resolve(true);
            }
            if (inFlight) return inFlight;
            inFlight = Promise.resolve(originalRiskLoad.call(this, options))
                .then(result => {
                    if (result !== false) lastSuccessAt = Date.now();
                    return result;
                })
                .finally(() => { inFlight = null; });
            return inFlight;
        };
    }

    // Extend the existing user-facing diagnostics with system-vs-market truth.
    if (typeof window.futRenderAnalysisDiagnostics === 'function') {
        const originalDiagnostics = window.futRenderAnalysisDiagnostics;
        window.futRenderAnalysisDiagnostics = function (json, context) {
            const base = originalDiagnostics.call(this, json, context);
            const h = json && json.pipeline_health;
            if (!h || !Number(h.analyzed_cells || 0)) return base;

            const runtimeFailed = Number(h.runtime_failed || 0);
            const dataError = Number(h.data_error || 0);
            const noThesis = Number(h.no_directional_thesis || 0);
            const candidate = Number(h.setup_or_candidate_not_ready || 0);
            const direction = Number(h.direction_not_confirmed || 0);
            const execution = Number(h.entry_not_ready || 0) + Number(h.sl_not_ready || 0) + Number(h.tp_not_ready || 0) + Number(h.rr_not_ready || 0);
            const finalFilter = Number(h.safety_not_ready || 0) + Number(h.publication_not_ready || 0);
            const executable = Number(h.executable || 0);

            let body = '';
            if (runtimeFailed > 0 || dataError > 0) {
                body += `<div class="text-warning"><strong>Estado técnico:</strong> ${runtimeFailed + dataError} análisis no terminaron correctamente. Estos casos no se cuentan como ausencia de oportunidad.</div>`;
            }
            body += `<div class="text-muted mt-1">Celdas analizadas: ${Number(h.analyzed_cells || 0)} · sin tesis direccional: ${noThesis} · setup/estrategia aún no listo: ${candidate} · dirección no confirmada: ${direction} · geometría de ejecución no lista: ${execution} · filtro final: ${finalFilter} · ejecutables: ${executable}.</div>`;

            return base + `
                <details class="mt-2 px-2 pb-2">
                    <summary class="text-info" style="cursor:pointer;">Estado del análisis</summary>
                    <div class="small mt-2">${body}</div>
                </details>`;
        };
    }
})();
