/* Commit 17.5.10.4 — bounded UI reads without analysis-status noise.
 * No polling, no automatic retry and no new endpoint.
 */
(function () {
    'use strict';
    if (window.__RUNTIME_RESILIENCE_175104__) return;
    window.__RUNTIME_RESILIENCE_175104__ = true;

    // Cached signal/risk reads can be delayed by the single Render worker while
    // the heavy slot is yielding CPU. Extend the same request, never duplicate it.
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
})();
