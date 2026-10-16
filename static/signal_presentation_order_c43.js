/* C43 — Orden de PRESENTACIÓN solamente. Nunca cambia decisiones, lifecycle,
 * deduplicación, guardado por usuario, Entry, SL, TP ni filtros Safety.
 * Orden: timeframe ascendente; dentro de una temporalidad, vigencia restante
 * descendente. Empates: orden original estable de Array.sort.
 */
(function (root) {
  'use strict';
  const TIMEFRAME_MINUTES = Object.freeze({
    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480,
    '12h': 720, '1d': 1440, '1w': 10080
  });
  function timeframeMinutes(row) {
    const raw = String(row?.timeframe ?? row?.tf ?? row?.interval ?? '').trim().toLowerCase();
    return TIMEFRAME_MINUTES[raw] ?? Number.POSITIVE_INFINITY;
  }
  function epochMillis(raw) {
    if (raw === null || raw === undefined || raw === '') return null;
    if (typeof raw === 'number' || /^\d+(?:\.\d+)?$/.test(String(raw))) {
      const v = Number(raw);
      return Number.isFinite(v) ? (v >= 1e12 ? v : (v >= 1e9 ? v * 1000 : null)) : null;
    }
    const parsed = Date.parse(String(raw));
    return Number.isFinite(parsed) ? parsed : null;
  }
  function remainingSeconds(row, now) {
    for (const field of [
      'tiempo_restante', 'remaining_seconds', 'seconds_remaining',
      'validity_remaining_seconds', 'time_remaining', 'remaining_validity_seconds'
    ]) {
      if (row?.[field] !== undefined && row?.[field] !== null && row?.[field] !== '') {
        const v = Number(row[field]);
        if (Number.isFinite(v)) return Math.max(0, v);
      }
    }
    for (const field of [
      'valid_until', 'source_valid_until', 'expires_at', 'expiry_at',
      'expiration_time', 'signal_expires_at'
    ]) {
      const epoch = epochMillis(row?.[field]);
      if (epoch !== null) return Math.max(0, (epoch - now) / 1000);
    }
    return Number.NEGATIVE_INFINITY; // sin dato: al final de su TF
  }
  function sortSignalPresentation(rows, now = Date.now()) {
    if (!Array.isArray(rows)) return [];
    const scored = rows.map((row, original) => ({
      row, original, tf: timeframeMinutes(row), remaining: remainingSeconds(row, now)
    }));
    scored.sort((a, b) => (a.tf - b.tf) || (b.remaining - a.remaining) || (a.original - b.original));
    return scored.map(entry => entry.row);
  }
  root.strSortSignalPresentation = sortSignalPresentation;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { sortSignalPresentation, timeframeMinutes, remainingSeconds };
  }
})(typeof window !== 'undefined' ? window : globalThis);
