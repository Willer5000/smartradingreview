/* Commit 17.5.10.8
 * Frontend-only diagnostic renderer.
 * Does not create signals, change Safety, or enable manual save.
 */
(function () {
    'use strict';

    function esc(value) {
        if (typeof window.futEscapeHtml === 'function') {
            return window.futEscapeHtml(String(value == null ? '' : value));
        }
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function confidence(value) {
        const n = Number(value);
        return Number.isFinite(n) ? `${n.toFixed(0)}%` : '--';
    }

    function fmt(value, digits) {
        const n = Number(value);
        if (!Number.isFinite(n) || n <= 0) return null;
        return n.toLocaleString(undefined, {
            maximumFractionDigits: digits == null ? 6 : digits
        });
    }

    function currentCandidates(json, context) {
        const key = context === 'vigent'
            ? 'vigent_other_directional_signals'
            : 'other_directional_signals';
        let rows = Array.isArray(json && json[key]) ? json[key] : [];

        if (typeof window._isSignalSavedByCurrentUser === 'function') {
            rows = rows.filter(row => !window._isSignalSavedByCurrentUser(row));
        }

        const byCell = new Map();
        rows.forEach(row => {
            if (!row || typeof row !== 'object') return;
            const action = String(row.action || row.diagnostic_action || '').toUpperCase();
            if (action !== 'LONG' && action !== 'SHORT') return;
            const cell = `${String(row.symbol || '')}|${String(row.timeframe || '')}`;
            const prev = byCell.get(cell);
            if (!prev || Number(row.confidence || 0) > Number(prev.confidence || 0)) {
                byCell.set(cell, {...row, action});
            }
        });
        return Array.from(byCell.values());
    }

    function renderSave(row, context) {
        const riskClass = String(row.manual_risk_class || '').toUpperCase();
        const canSave = (
            (context === 'previous' || context === 'vigent')
            && row.manual_save_allowed === true
            && row.signal_id
            && (riskClass === 'MEDIUM' || riskClass === 'HIGH')
            && typeof window.openManualAnalysisSave === 'function'
        );
        if (!canSave) return '';

        window._manualAnalysisCandidates = window._manualAnalysisCandidates || {};
        const key = String(row.signal_id);
        const sourceContext = context === 'vigent'
            ? 'ACTIVE_ANALYSIS_ONLY'
            : 'PREVIOUS_ANALYSIS_ONLY';
        window._manualAnalysisCandidates[key] = {
            ...row,
            source_context: sourceContext
        };

        return `
            <div class="mt-2">
                <button type="button"
                    class="btn btn-sm ${riskClass === 'MEDIUM' ? 'btn-outline-warning' : 'btn-outline-danger'}"
                    onclick="event.stopPropagation(); window.openManualAnalysisSave('${esc(key)}', false);">
                    ${riskClass === 'MEDIUM' ? '💾 Guardar seguimiento' : '🧪 Guardar experimental'}
                </button>
            </div>
        `;
    }

    function renderRow(row, context) {
        const action = String(row.action || '').toUpperCase();
        const isLong = action === 'LONG';
        const actionClass = isLong ? 'success' : 'danger';
        const manualRisk = String(row.manual_risk_class || '').toUpperCase();
        const manual = row.manual_save_allowed === true
            && (manualRisk === 'MEDIUM' || manualRisk === 'HIGH');

        let statusLabel;
        let statusClass;
        if (manualRisk === 'MEDIUM') {
            statusLabel = 'RIESGO MEDIO';
            statusClass = 'warning text-dark';
        } else if (manualRisk === 'HIGH') {
            statusLabel = 'RIESGO ALTO';
            statusClass = 'danger';
        } else {
            statusLabel = String(row.diagnostic_label || 'NO EJECUTABLE').toUpperCase();
            statusClass = statusLabel === 'ESPERAR' ? 'info text-dark' : 'secondary';
        }

        const reason = esc(
            row.reason
            || row.manual_risk_reason
            || 'La hipótesis no superó una condición técnica de ejecución/publicación.'
        );
        const symbol = esc(String(row.symbol || '').replace('-', '/'));
        const tf = esc(row.timeframe || '--');
        const finalAction = String(row.final_action || '').toUpperCase();
        const finalState = (
            finalAction
            && finalAction !== action
            && ['ESPERAR', 'PRECAUCION', 'PRECAUCIÓN'].includes(finalAction)
        )
            ? `<div class="small text-info mt-1">Estado actual: ${esc(finalAction.replace('PRECAUCION', 'PRECAUCIÓN'))}</div>`
            : '';

        const entry = fmt(row.entry, 8);
        const sl = fmt(row.stop_loss, 8);
        const tp = fmt(row.take_profit, 8);
        const rr = Number(row.risk_reward);
        const safety = Number(row.execution_safety);
        const metrics = [];
        if (entry) metrics.push(`Entry ${entry}`);
        if (sl) metrics.push(`SL ${sl}`);
        if (tp) metrics.push(`TP ${tp}`);
        if (Number.isFinite(rr) && rr > 0) metrics.push(`R/R 1:${rr.toFixed(2)}`);
        if (Number.isFinite(safety) && safety > 0) metrics.push(`Safety ${safety.toFixed(1)}`);
        const metricHtml = metrics.length
            ? `<div class="small text-muted mt-1">${metrics.map(esc).join(' · ')}</div>`
            : '';

        const saveHtml = manual ? renderSave(row, context) : '';

        return `
            <div class="border border-secondary rounded p-2 mt-2">
                <div class="d-flex flex-wrap align-items-center gap-2">
                    <span class="badge bg-${actionClass}">${esc(action)}</span>
                    <strong>${symbol}</strong>
                    <span>${tf}</span>
                    <span class="badge bg-${statusClass}">${esc(statusLabel)}</span>
                    <span class="badge bg-dark">${esc(confidence(row.confidence))}</span>
                </div>
                <div class="small mt-2">${reason}</div>
                ${finalState}
                ${metricHtml}
                ${saveHtml}
            </div>
        `;
    }

    window.futRenderAnalysisDiagnostics = function (json, context) {
        const rows = currentCandidates(json, context);
        const title = 'Por qué no aparecen otras señales';

        if (rows.length === 0) {
            return `
                <details class="mt-2 px-2 pb-2">
                    <summary class="text-secondary" style="cursor:pointer;">
                        ${title} (0)
                    </summary>
                    <div class="small text-muted mt-2">
                        No hay otras hipótesis LONG/SHORT clasificadas en el snapshot disponible.
                    </div>
                </details>
            `;
        }

        return `
            <details class="mt-2 px-2 pb-2">
                <summary class="text-secondary" style="cursor:pointer;">
                    ${title} (${rows.length})
                </summary>
                <div class="small text-muted mt-2">
                    Son hipótesis direccionales que el sistema detectó pero no publicó como señal.
                    Verlas aquí no las vuelve ejecutables.
                </div>
                ${rows.map(row => renderRow(row, context)).join('')}
            </details>
        `;
    };

    console.info('✅ Frontend diagnóstico 17.5.10.8 activo');
})();
