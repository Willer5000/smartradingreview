/* Commit 19.2.4 — frontend request recovery.
 * No new market-data request. No polling loop. Only deduplicates/throttles
 * duplicate heavy-analysis launches so the backend can keep rendering charts.
 */
(() => {
  'use strict';
  const state = window.__CPQE_1924__ = window.__CPQE_1924__ || {
    lastByKey: Object.create(null),
    wrapped: false,
    minIntervalMs: 15000,
  };

  function currentKey() {
    const s = document.getElementById('symbol-select')?.value || window.currentSymbol || '';
    const t = document.getElementById('interval-select')?.value || window.currentInterval || '';
    return `${location.pathname}|${s}|${t}`;
  }

  function wrap() {
    if (state.wrapped || typeof window.runCompleteAnalysis !== 'function') return false;
    const original = window.runCompleteAnalysis;
    window.runCompleteAnalysis = function(...args) {
      const key = currentKey();
      const now = Date.now();
      const last = Number(state.lastByKey[key] || 0);
      if (last && now - last < state.minIntervalMs) {
        console.debug('[CPQE 19.2.4] Heavy analysis throttled:', key);
        return;
      }
      state.lastByKey[key] = now;
      return original.apply(this, args);
    };
    state.wrapped = true;
    return true;
  }

  const timer = setInterval(() => {
    if (wrap()) clearInterval(timer);
  }, 250);
  setTimeout(() => clearInterval(timer), 15000);
})();
