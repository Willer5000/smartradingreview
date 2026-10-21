/* C43.1 — PRESENTACIÓN solamente; no cambia las señales ni su lifecycle.
 * Spot conserva el orden C43 original. Futures y Multi-Activo usan:
 * temporalidad ↑, vigencia restante ↓, riesgo explícito ↑.
 * Solo la vista selecciona un representante por símbolo × temporalidad.
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
  function cellKey(row, includeDirection = false) {
    const symbol = String(row?.symbol || row?.ticker || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
    const tf = String(row?.timeframe || row?.tf || row?.interval || '').trim().toLowerCase();
    if (!symbol || !tf) return null;
    if (!includeDirection) return `${symbol}|${tf}`;
    const action = String(row?.diagnostic_action || row?.action || row?.decision?.action || row?.decision || '').trim().toUpperCase();
    // Only distinguish genuine LONG/SHORT derivative directions. Do not
    // fabricate a side for incomplete rows or change the Spot dedupe key.
    return ['LONG','SHORT'].includes(action) ? `${symbol}|${tf}|${action}` : `${symbol}|${tf}`;
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
    return Number.NEGATIVE_INFINITY;
  }
  function riskRank(row) {
    // No deducir riesgo de CORE 1/CORE 2 ni del apalancamiento.
    const explicit = String(
      row?.manual_risk_class || row?.risk_class || row?.risk_level ||
      row?.risk_category || row?.safety_band || ''
    ).trim().toUpperCase().replace(/[\s_-]+/g, ' ');
    const classes = {
      'VERY LOW': 0, 'MUY BAJO': 0, 'MUY BAJA': 0,
      'LOW': 1, 'BAJO': 1, 'BAJA': 1, 'PREMIUM': 1,
      'MEDIUM': 2, 'MODERATE': 2, 'MEDIO': 2, 'MEDIA': 2, 'MODERADO': 2,
      'HIGH': 3, 'ALTO': 3, 'ALTA': 3,
      'VERY HIGH': 4, 'MUY ALTO': 4, 'MUY ALTA': 4,
      'CRITICAL': 5, 'CRITICO': 5, 'CRÍTICO': 5, 'EXTREME': 5
    };
    const tier = Object.prototype.hasOwnProperty.call(classes, explicit)
      ? classes[explicit] : Number.POSITIVE_INFINITY;
    // Solo orden secundario para campos sin clase explícita. Alta seguridad
    // puede ser menor riesgo; confianza NO se presenta como nivel de riesgo.
    const safety = Number(row?.execution_safety ?? row?.safety_score);
    const confidence = Number(row?.confidence);
    return {
      tier,
      safety: Number.isFinite(safety) && (row?.execution_safety != null || row?.safety_score != null)
        ? -safety : Number.POSITIVE_INFINITY,
      confidence: Number.isFinite(confidence) && row?.confidence != null
        ? -confidence : Number.POSITIVE_INFINITY
    };
  }
  function sourceTime(row) {
    for (const field of ['source_candle_close_timestamp', 'confirmed_at',
      'source_candle_timestamp', 'candle_timestamp', 'created_at']) {
      const ts = epochMillis(row?.[field]);
      if (ts !== null) return ts;
    }
    return 0;
  }
  function quality(row) {
    for (const field of ['diagnostic_quality', 'quality_score', 'thesis_quality', 'confidence']) {
      if (row?.[field] !== undefined && row?.[field] !== null && row?.[field] !== '') {
        const num = Number(row[field]);
        if (Number.isFinite(num)) return num;
      }
    }
    return -1;
  }
  function preferRepresentative(challenger, incumbent) {
    const latestDiff = sourceTime(challenger) - sourceTime(incumbent);
    if (latestDiff !== 0) return latestDiff > 0;
    const qualityDiff = quality(challenger) - quality(incumbent);
    if (qualityDiff !== 0) return qualityDiff > 0;
    return false; // Empate: primera recibida; no altera la fuente.
  }
  function uniqueSignalPresentation(rows, options = {}) {
    if (!Array.isArray(rows)) return [];
    const selected = new Map();
    const unidentified = [];
    rows.forEach((row, index) => {
      const key = cellKey(row, !!options.direction);
      if (!key) { unidentified.push({row, index}); return; }
      const prev = selected.get(key);
      if (!prev || preferRepresentative(row, prev.row)) selected.set(key, {row, index});
    });
    return [...selected.values(), ...unidentified].sort((a, b) => a.index - b.index).map(x => x.row);
  }
  function sortSignalPresentation(rows, now = Date.now(), options = {}) {
    if (!Array.isArray(rows)) return [];
    const input = options.dedupe ? uniqueSignalPresentation(rows, options) : rows;
    const scored = input.map((row, original) => ({
      row, original, tf: timeframeMinutes(row), remaining: remainingSeconds(row, now),
      risk: options.risk ? riskRank(row) : null
    }));
    scored.sort((a, b) => (a.tf - b.tf) || (b.remaining - a.remaining) ||
      (options.risk ? (a.risk.tier - b.risk.tier || a.risk.safety - b.risk.safety ||
        a.risk.confidence - b.risk.confidence) : 0) ||
      (a.original - b.original));
    return scored.map(entry => entry.row);
  }

  // Reconciliación EXCLUSIVAMENTE visual de Confirmadas frente a Vigentes.
  // Los dos endpoints sirven snapshots separados; el registro histórico de
  // Telegram puede replicar una celda aunque backend haya deduplicado el caché.
  // No cambia JSON, señal oficial, fecha, botones, Guardian ni Supabase.
  function reconcileDerivativeLanes(doc = (typeof document === 'undefined' ? null : document)) {
    if (!doc?.getElementById) return;
    const active = doc.getElementById('active-signals-list');
    const previous = doc.getElementById('prev-signals-list');
    if (!active || !previous || active.dataset.strLoaded !== '1' || previous.dataset.strLoaded !== '1') return;
    const nodes = [];
    for (const [panel, lane] of [[previous, 'confirmed'], [active, 'vigent']]) {
      for (const el of panel.querySelectorAll('[data-str-signal]')) {
        let row;
        try { row = JSON.parse(decodeURIComponent(el.getAttribute('data-str-signal'))); }
        catch (_) { continue; }
        el.style.display = ''; // los paneles pueden refrescarse independientemente
        nodes.push({el, row, lane});
      }
    }
    const byCell = new Map();
    for (const item of nodes) {
      const key = cellKey(item.row, true);
      if (!key) continue;
      const old = byCell.get(key);
      if (!old || preferRepresentative(item.row, old.row) ||
          (!preferRepresentative(old.row, item.row) && item.lane === 'confirmed' && old.lane !== 'confirmed')) {
        byCell.set(key, item);
      }
    }
    for (const item of nodes) {
      const key = cellKey(item.row, true);
      if (key && byCell.get(key) !== item) item.el.style.display = 'none';
    }
    for (const [panel, lane, badgeID] of [
      [previous, 'confirmed', 'prev-signals-count'],
      [active, 'vigent', 'active-signals-count']
    ]) {
      const shown = nodes.filter(x => x.lane === lane && x.el.style.display !== 'none'
        && (lane !== 'confirmed' || x.row.activa === undefined || Number(x.row.activa) === 1)).length;
      const badge = doc.getElementById(badgeID);
      if (badge) {
        badge.textContent = String(shown);
        badge.className = `badge bg-${lane === 'confirmed'
          ? (shown ? 'warning' : 'secondary') : (shown ? 'success' : 'secondary')}`;
      }
      // Si todas las tarjetas de este carril se repiten en el otro, mantener
      // el mismo mensaje de carril vacío que ya usa C43 (sin cambiar diseño).
      const duplicateEmpty = panel.querySelector?.('[data-str-dedup-empty]');
      if (shown > 0) duplicateEmpty?.remove();
      else if (!duplicateEmpty && nodes.some(x => x.lane === lane) && panel.insertAdjacentHTML) {
        const message = lane === 'confirmed'
          ? 'No hay nuevas señales confirmadas en el último cierre.'
          : 'No hay señales vigentes de cierres anteriores en este momento.';
        panel.insertAdjacentHTML('afterbegin',
          `<div data-str-dedup-empty class="list-group-item bg-dark text-warning text-center py-3"><strong>✅ Análisis completado</strong><br><small>${message}</small></div>`);
      }
    }
  }
  root.strSignalCellKey = cellKey;
  root.strSortSignalPresentation = sortSignalPresentation;
  root.strReconcileDerivativeLanes = reconcileDerivativeLanes;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      sortSignalPresentation, uniqueSignalPresentation, preferRepresentative,
      cellKey, riskRank, timeframeMinutes, remainingSeconds, reconcileDerivativeLanes
    };
  }
})(typeof window !== 'undefined' ? window : globalThis);
