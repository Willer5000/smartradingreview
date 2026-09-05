// futures.js - Solo se carga en la página /futures
// SOBREESCRIBE las funciones de script.js que consultan spot para que consulten
// solo los endpoints /api/futures/* con los símbolos y timeframes de futuros.
// También añade el panel del ReviewTrader y adapta la correlación.

console.log('🚀 futures.js cargado - modo Futuros activo');

// ============================================================================
// CONTROL DE CARGA DE SEÑALES FUTUROS
// Evita peticiones simultáneas al mismo caché pesado.
// ============================================================================
window._futuresSignalsState = {
    activeLoading: false,
    previousLoading: false,
    activeTimer: null,
    previousTimer: null
};
// Helper global: nunca mostrar confianza > 100% (defensa contra datos viejos).
function fmtConfidence(c) {
    const n = Number(c) || 0;
    const capped = Math.max(0, Math.min(100, n));
    return capped.toFixed(0);
}
window.fmtConfidence = fmtConfidence;


// ============================================================================
// UTILIDADES
// ============================================================================

function futShowToast(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(msg, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${msg}`);
    }
}

function futFormatPct(val, decimals = 2) {
    if (val === null || val === undefined) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(decimals)}%`;
}

function futFormatPrice(price, symbol) {
    if (price === null || price === undefined) return '--';
    const decimals = (symbol && (symbol.includes('XRP') || symbol.includes('ADA'))) ? 4 : 2;
    return '$' + Number(price).toFixed(decimals);
}

function futFormatDuration(seconds) {
    if (!seconds || seconds <= 0) return '--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function futEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function futRenderDecisionAudit(audit) {
    if (!audit || audit.schema_version !== 'DECISION_AUDIT_V1') {
        return '';
    }

    const trace = audit.moderator_trace || {};
    const input = audit.input_snapshot || {};
    const contract = audit.data_contract || {};
    const votes = Array.isArray(audit.votes) ? audit.votes : [];

    const numberText = (value, decimals = 2) => {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(decimals) : '--';
    };
    const dispositionMeta = {
        APOYO_FINAL: ['success', 'APOYÓ EL RESULTADO'],
        APOYO_AL_VETO: ['danger', 'ACTIVÓ/RESPALDÓ VETO'],
        OPOSICION_DIRECCIONAL: ['warning text-dark', 'QUEDÓ EN MINORÍA'],
        CAUTELA_ESPERAR: ['info text-dark', 'PIDIÓ ESPERAR'],
        CAUTELA_NO_OPERAR: ['secondary', 'PIDIÓ NO OPERAR'],
        ABSTENCION: ['secondary', 'SE ABSTUVO'],
        ERROR_CONTROLADO: ['danger', 'FALLÓ; VOTO NEUTRALIZADO']
    };

    let votesHtml = '';
    votes.forEach(vote => {
        const disposition = String(vote.disposition || 'ABSTENCION');
        const meta = dispositionMeta[disposition]
            || dispositionMeta.ABSTENCION;
        const originalAction = String(vote.original_action || 'NO_OPERAR');
        const normalizedAction = String(
            vote.normalized_action || originalAction
        );
        const actionText = originalAction === normalizedAction
            ? futEscapeHtml(normalizedAction)
            : `${futEscapeHtml(originalAction)} → ${futEscapeHtml(normalizedAction)}`;
        const counted = vote.counted_confidence;
        const countedText = counted === null || counted === undefined
            ? 'no entró al conteo principal'
            : `conteo final ${numberText(counted, 1)}%`;
        const reasons = Array.isArray(vote.reasons) ? vote.reasons : [];
        const strategies = Array.isArray(vote.strategies) ? vote.strategies : [];
        const explanation = reasons[0]
            || (strategies.length > 0 ? strategies.join(', ') : 'Sin razón declarada');

        votesHtml += `
            <div class="border-top border-secondary py-2">
                <div class="d-flex flex-wrap justify-content-between gap-1">
                    <strong>${futEscapeHtml(vote.trader || 'Trader')}</strong>
                    <span class="badge bg-${meta[0]}">${meta[1]}</span>
                </div>
                <div class="small text-light mt-1">
                    Voto: <strong>${actionText}</strong> ·
                    confianza ${numberText(vote.original_confidence, 1)}%
                </div>
                <div class="small text-muted">
                    ${numberText(vote.original_confidence, 1)}%
                    × peso ${numberText(vote.base_weight, 2)}
                    × régimen ${numberText(vote.regime_multiplier, 2)}
                    × aprendizaje ${numberText(vote.review_multiplier, 2)}
                    = ${numberText(vote.weighted_confidence, 1)}%
                    · ${countedText}
                </div>
                <div class="small text-secondary mt-1">
                    ${futEscapeHtml(explanation)}
                </div>
            </div>
        `;
    });

    const provider = futEscapeHtml(contract.provider || 'pendiente del wrapper');
    const candleTimestamp = futEscapeHtml(
        contract.source_candle_timestamp
        || input.analysis_candle_timestamp
        || '--'
    );
    const synthetic = contract.is_synthetic;
    const syntheticText = synthetic === false
        ? 'datos reales (no sintéticos)'
        : (synthetic === true ? 'datos sintéticos' : 'origen aún no declarado');
    const finalReasons = Array.isArray(trace.final_reasons)
        ? trace.final_reasons
        : [];

    return `
        <details class="mt-2 border border-secondary rounded p-2"
                 onclick="event.stopPropagation();">
            <summary class="text-info" style="cursor:pointer;">
                🔎 Auditor de la decisión · ${votes.length} traders
            </summary>
            <div class="small mt-2">
                <div>
                    <strong>Datos recibidos:</strong> ${provider} ·
                    ${futEscapeHtml(syntheticText)} · vela ${candleTimestamp}
                </div>
                <div class="text-muted">
                    Régimen ${futEscapeHtml(input.market_regime || 'DESCONOCIDO')}
                    (${numberText(input.market_regime_confidence, 1)}%) ·
                    ADX ${numberText(input.adx, 1)} ·
                    ATR ${numberText(input.atr_pct, 2)}% ·
                    volumen ${numberText(input.volume_ratio, 2)}x
                </div>
                <div class="mt-2">
                    <strong>Moderador:</strong>
                    ${futEscapeHtml(trace.decision_basis || 'SIN_TRAZA')} ·
                    resultado ${futEscapeHtml(trace.final_action || 'NO_OPERAR')}
                    (${numberText(trace.final_confidence, 1)}%) ·
                    veto ${futEscapeHtml(trace.veto_state || 'SIN_VETO')}
                </div>
                ${finalReasons.length > 0 ? `
                    <div class="text-light mt-1">
                        ${futEscapeHtml(finalReasons.join(' · '))}
                    </div>
                ` : ''}
                <div class="text-secondary mt-1">
                    Auditoría de sólo lectura: explica la decisión, no la modifica.
                </div>
                <div class="mt-2">${votesHtml}</div>
            </div>
        </details>
    `;
}
// ============================================================================
// COMMIT 36M — GUARDADO MANUAL DE ANALYSIS_ONLY CLASIFICADO POR RIESGO
// ============================================================================

window._manualAnalysisCandidates = (
    window._manualAnalysisCandidates
    || {}
);


window.openManualAnalysisSave = function(
    manualKey
) {
    const candidate = (
        window._manualAnalysisCandidates[
            manualKey
        ]
    );

    if (!candidate) {
        futShowToast(
            'El análisis ya no está disponible. Actualiza la lista.',
            'warning'
        );
        return;
    }

    if (
        candidate.manual_save_allowed
        !== true
    ) {
        futShowToast(
            candidate.manual_risk_reason
            || 'Este análisis no puede guardarse como operación.',
            'warning'
        );
        return;
    }

    const riskClass = String(
        candidate.manual_risk_class
        || ''
    ).toUpperCase();

    const confirmationText = (
        riskClass === 'MEDIUM'
            ? (
                'RIESGO MEDIO: esta hipótesis superó el Safety mínimo, '
                + 'pero NO superó la publicación Premium.\n\n'
                + 'Guardarla no significa que el sistema la recomiende. '
                + '¿Deseas seguirla manualmente?'
            )
            : (
                'RIESGO ALTO: esta hipótesis NO supera el Safety mínimo '
                + 'operativo; sólo está en la banda BAJA 55–64.9.\n\n'
                + 'No es una señal oficial. ¿Deseas guardarla como '
                + 'seguimiento manual experimental?'
            )
    );

    if (!window.confirm(confirmationText)) {
        return;
    }

    const sig = {
        symbol:
            candidate.symbol,

        timeframe:
            candidate.timeframe,

        action:
            candidate.action,

        confidence:
            candidate.confidence,

        entry:
            candidate.entry,

        stop_loss:
            candidate.stop_loss,

        take_profit:
            candidate.take_profit,

        leverage:
            candidate.leverage || 1,

        risk_reward:
            candidate.risk_reward,

        candle_timestamp:
            candidate.source_candle_timestamp,

        source_signal_id:
            candidate.signal_id,

        execution_origin:
                    'USER_MANUAL_ANALYSIS',

        source_context:
            'PREVIOUS_ANALYSIS_ONLY',

        manual_risk_class:
            riskClass,

        manual_save_allowed:
            true,

        manual_override_ack:
            true,

        manual_risk_reason:
            candidate.manual_risk_reason,

        execution_safety:
            candidate.execution_safety,

        execution_safety_minimum:
            candidate.execution_safety_minimum
    };

    // En un override manual NO generamos niveles artificiales.
    if (
        !(Number(sig.entry) > 0)
        || !(Number(sig.stop_loss) > 0)
        || !(Number(sig.take_profit) > 0)
    ) {
        futShowToast(
            'El análisis no conserva Entry/SL/TP válidos; no puede guardarse.',
            'warning'
        );
        return;
    }

    window.openSaveSignalModal(
        sig,
        false
    );
};
function futRenderAnalysisDiagnostics(json, context) {
    const summary = json && json.analysis_summary;
    const candidates = Array.isArray(json && json.analysis_candidates)
        ? json.analysis_candidates
        : [];

    // Compatibilidad durante despliegues: si el backend todavía es anterior
    // al commit 7, no insertar un panel vacío ni romper las listas existentes.
    if (!summary || candidates.length === 0) {
        return '';
    }

    const executable = Number(summary.executable || 0);
    const activeNow = Number(summary.active_now || 0);
    const analysisOnly = Number(summary.analysis_only || 0);
    const noTrade = Number(summary.no_trade || 0);
    const errors = Number(summary.errors || 0);

    const excluded = candidates.filter(candidate => {
        if (context === 'active') {
            return !candidate.is_active;
        }
        return candidate.classification !== 'EXECUTABLE_SIGNAL';
    });

    const shouldOpen = (
        context === 'active'
            ? activeNow === 0
            : executable === 0
    );

    const statusMeta = {
        EXECUTABLE_SIGNAL: {
            badge: 'success',
            label: 'EJECUTABLE'
        },
        ANALYSIS_ONLY: {
            badge: 'warning text-dark',
            label: 'SOLO ANÁLISIS'
        },
        NO_TRADE: {
            badge: 'secondary',
            label: 'NO OPERAR'
        },
        ANALYSIS_ERROR: {
            badge: 'danger',
            label: 'ERROR DE DATOS'
        }
    };

    let excludedHtml = '';

    excluded.forEach(candidate => {
        const classification = String(
            candidate.classification || 'ANALYSIS_ERROR'
        );
        const meta = statusMeta[classification]
            || statusMeta.ANALYSIS_ERROR;
        const rawSymbol = String(
                    candidate.symbol || ''
                );
        
                const rawTimeframe = String(
                    candidate.timeframe || ''
                );
        
                const symbol = futEscapeHtml(
                    rawSymbol.replace('-', '/')
                );
        
                const timeframe = futEscapeHtml(
                    rawTimeframe || '--'
                );
        
                const navSymbol = futEscapeHtml(
                    rawSymbol
                );
        
                const navTimeframe = futEscapeHtml(
                    rawTimeframe
                );
        const action = futEscapeHtml(candidate.action || 'NO_OPERAR');
        const confidence = fmtConfidence(candidate.confidence);
        const reason = futEscapeHtml(
            candidate.reason || candidate.active_reason || 'Sin motivo disponible'
        );
        const safety = candidate.execution_safety;
        const safetyMinimum = candidate.execution_safety_minimum;

        let safetyHtml = '';
        if (safety !== null && safety !== undefined) {
            safetyHtml = `
                <span class="text-info ms-2">
                    Safety ${Number(safety).toFixed(1)}
                    ${
                        safetyMinimum !== null && safetyMinimum !== undefined
                            ? `/ mínimo ${Number(safetyMinimum).toFixed(1)}`
                            : ''
                    }
                </span>
            `;
        }
        let manualSaveHtml = '';

        if (
            context === 'previous'
            && classification === 'ANALYSIS_ONLY'
            && candidate.manual_save_allowed === true
            && candidate.signal_id
        ) {
            const manualKey = String(
                candidate.signal_id
            );

            window._manualAnalysisCandidates[
                manualKey
            ] = candidate;

            const riskClass = String(
                candidate.manual_risk_class
                || ''
            ).toUpperCase();

            const isMedium = (
                riskClass === 'MEDIUM'
            );

            manualSaveHtml = `
                <div class="mt-2">
                    <span class="badge ${isMedium ? 'bg-warning text-dark' : 'bg-danger'} me-1">
                        ${isMedium ? 'RIESGO MEDIO' : 'RIESGO ALTO'}
                    </span>

                    <button
                        type="button"
                        class="btn btn-sm ${isMedium ? 'btn-outline-warning' : 'btn-outline-danger'}"
                        onclick="event.stopPropagation(); window.openManualAnalysisSave('${manualKey}');"
                    >
                        ${isMedium
                            ? '💾 Guardar manual'
                            : '🧪 Guardar experimental'}
                    </button>

                    <div class="small text-muted mt-1">
                        ${futEscapeHtml(
                            candidate.manual_risk_reason
                            || ''
                        )}
                    </div>
                </div>
            `;
        }
        let lifecycleHtml = '';
        if (
            classification === 'EXECUTABLE_SIGNAL'
            && !candidate.is_active
        ) {
            lifecycleHtml = `
                <div class="small text-secondary mt-1">
                    ${futEscapeHtml(candidate.active_reason || '')}
                </div>
            `;
        }

        excludedHtml += `
                    <div
                        class="border-bottom border-secondary py-2"
                        style="cursor:pointer;"
                        data-nav-symbol="${navSymbol}"
                        data-nav-timeframe="${navTimeframe}"
                        onclick="window.changeToSignal(
                            this.dataset.navSymbol,
                            this.dataset.navTimeframe
                        )"
                    >
                <div class="d-flex flex-wrap justify-content-between gap-1">
                    <div>
                        <span class="badge bg-${meta.badge} me-1">
                            ${meta.label}
                        </span>
                        <strong>${symbol}</strong>
                        <span class="badge bg-dark ms-1">${timeframe}</span>
                    </div>
                    <small class="text-muted">
                        ${action} · ${confidence}%
                    </small>
                </div>
                <div class="small text-light mt-1">
                    ${reason}
                    ${safetyHtml}
                </div>
                ${lifecycleHtml}
                ${manualSaveHtml}

                <div class="small text-muted mt-1">
                    ${
                        manualSaveHtml
                            ? (
                                'Sigue siendo ANALYSIS_ONLY: guardarla '
                                + 'sólo crea seguimiento personal.'
                            )
                            : (
                                'Información diagnóstica: '
                                + 'no se puede guardar como operación.'
                            )
                    }
                </div>
                ${futRenderDecisionAudit(candidate.decision_audit)}
            </div>
        `;
    });

    const detailHtml = excluded.length > 0
        ? `
            <details class="mt-2" ${shouldOpen ? 'open' : ''}>
                <summary class="text-warning" style="cursor:pointer;">
                    Por qué no aparecen otras señales (${excluded.length})
                </summary>
                <div class="mt-2 px-2"
                     style="max-height:360px; overflow-y:auto;">
                    ${excludedHtml}
                </div>
            </details>
        `
        : `
            <div class="small text-success mt-2">
                No existen análisis ocultos por los filtros actuales.
            </div>
        `;

    return `
        <div class="list-group-item bg-dark text-white border-info">
            <div class="d-flex flex-wrap justify-content-between gap-2">
                <strong>🛡️ Diagnóstico del ciclo</strong>
                <small class="text-muted">
                    ${Number(summary.total_analyzed || 0)} combinaciones
                </small>
            </div>
            <div class="d-flex flex-wrap gap-1 mt-2">
                <span class="badge bg-success">Activas: ${activeNow}</span>
                <span class="badge bg-info text-dark">Ejecutables: ${executable}</span>
                <span class="badge bg-warning text-dark">Solo análisis: ${analysisOnly}</span>
                <span class="badge bg-secondary">No operar: ${noTrade}</span>
                ${errors > 0 ? `<span class="badge bg-danger">Errores: ${errors}</span>` : ''}
            </div>
            <div class="small text-muted mt-2">
                “Solo análisis” indica que hubo dirección LONG/SHORT,
                pero un filtro de seguridad impidió publicarla.
            </div>
            ${detailHtml}
        </div>
    `;
}


// ============================================================================
// PANEL DE REVIEWTRADER (mantenido de la versión anterior)
// ============================================================================

function insertReviewTraderPanel() {
    const cards = document.querySelectorAll('.col-lg-3 .card');
    if (cards.length === 0) {
        setTimeout(insertReviewTraderPanel, 1000);
        return;
    }
    
    const container = cards[0].parentElement;
    if (!container) return;
    
    // Evitar duplicados
    if (document.getElementById('review-trader-panel-container')) return;
    
    const reviewCard = document.createElement('div');
    reviewCard.className = 'card bg-dark border-info mb-4';
    reviewCard.id = 'review-trader-panel-container';
    reviewCard.innerHTML = `
        <div class="card-header bg-info bg-opacity-25 d-flex justify-content-between align-items-center">
            <h6 class="mb-0">
                <i class="fas fa-graduation-cap me-2"></i>
                🎓 TRADER DE REVISIÓN
            </h6>
            <button class="btn btn-sm btn-outline-info" onclick="window.refreshReviewPanel()" title="Refrescar">
                <i class="fas fa-sync-alt"></i>
            </button>
        </div>
        <div class="card-body" id="review-trader-panel-body">
            <div class="text-muted small text-center py-3">Cargando recomendaciones...</div>
        </div>
    `;
    container.insertBefore(reviewCard, cards[0]);
    
    const globalCard = document.createElement('div');
    globalCard.className = 'card bg-dark border-primary mb-4';
    globalCard.id = 'review-global-panel-container';
    globalCard.innerHTML = `
        <div class="card-header bg-primary bg-opacity-25">
            <h6 class="mb-0"><i class="fas fa-globe me-2"></i>🌐 Estrategias Globales</h6>
        </div>
        <div class="card-body" id="review-global-panel-body">
            <div class="text-muted small text-center py-3">Cargando...</div>
        </div>
    `;
    container.insertBefore(globalCard, cards[0]);
    
    window.refreshReviewPanel();
    window.loadGlobalStats();
}


window.refreshReviewPanel = async function() {
    const body = document.getElementById('review-trader-panel-body');
    if (!body) return;
    
    const symbol = document.getElementById('symbol-select')?.value || 'BTC-USDT';
    const timeframe = document.getElementById('interval-select')?.value || '1h';
    
    let action = 'LONG';
    if (window.currentAnalysis && window.currentAnalysis.decision) {
        const a = window.currentAnalysis.decision.action;
        if (a === 'SHORT' || a === 'VENTA_SPOT') action = 'SHORT';
    }
    
    body.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-info"></div>
            <p class="small mt-2 mb-0">Consultando historial...</p>
        </div>
    `;
    
    try {
        const res = await fetch(`/api/review/recommendations/${symbol}/${timeframe}/${action}`);
        const json = await res.json();
        
        if (!json.success || !json.data) {
            body.innerHTML = `<div class="text-muted small text-center py-3">Sin datos aún</div>`;
            return;
        }
        
        const rec = json.data;
        if (!rec.available) {
            body.innerHTML = `
                <div class="text-muted small text-center py-3">
                    <i class="fas fa-hourglass-half me-1"></i>
                    ${rec.message || 'Aún no hay historial suficiente.'}<br>
                    <small class="text-info">El sistema aprenderá con el tiempo.</small>
                </div>
            `;
            return;
        }
        
        const winners = rec.winning_strategies || [];
        const losers = rec.losing_strategies || [];
        
        let winnersHTML = '';
        if (winners.length > 0) {
            winnersHTML = `
                <div class="mb-2">
                    <h6 class="text-success mb-1" style="font-size: 0.85rem;">
                        <i class="fas fa-trophy me-1"></i>Top Ganadoras (${action})
                    </h6>
                    ${winners.slice(0, 4).map((w, idx) => `
                        <div class="d-flex justify-content-between mb-1" style="font-size: 0.75rem;">
                            <span>${idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '•'} ${(w.strategy || '').length > 20 ? w.strategy.substring(0, 18) + '...' : w.strategy}</span>
                            <span class="badge bg-success">${w.win_rate}%</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        let losersHTML = '';
        if (losers.length > 0) {
            losersHTML = `
                <div class="mt-2">
                    <h6 class="text-danger mb-1" style="font-size: 0.85rem;">
                        <i class="fas fa-times-circle me-1"></i>Evitar
                    </h6>
                    ${losers.slice(0, 3).map(l => `
                        <div class="d-flex justify-content-between mb-1" style="font-size: 0.75rem;">
                            <span>⚠️ ${(l.strategy || '').length > 20 ? l.strategy.substring(0, 18) + '...' : l.strategy}</span>
                            <span class="badge bg-danger">${l.win_rate}%</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        body.innerHTML = `
            <div class="text-center mb-2 pb-2 border-bottom border-secondary">
                <div class="small text-muted">Basado en <strong>${rec.sample_size || 0}</strong> señales</div>
                <div class="d-flex justify-content-around mt-1">
                    <div>
                        <small class="text-muted d-block">Multiplier</small>
                        <strong style="color: #FFD700;">${(rec.multiplier || 1).toFixed(2)}x</strong>
                    </div>
                    <div>
                        <small class="text-muted d-block">Leverage</small>
                        <strong>${rec.leverage || 1}x</strong>
                    </div>
                </div>
            </div>
            ${winnersHTML}
            ${losersHTML}
            ${!winnersHTML && !losersHTML ? '<div class="text-muted small text-center py-2">Sin patrones detectados aún</div>' : ''}
        `;
    } catch (err) {
        body.innerHTML = `<div class="alert alert-warning small mb-0">Error de conexión</div>`;
    }
};


window.loadGlobalStats = async function() {
    const body = document.getElementById('review-global-panel-body');
    if (!body) return;
    
    try {
        const res = await fetch('/api/review/general_stats');
        const json = await res.json();
        
        if (!json.success || !json.stats || json.stats.length === 0) {
            body.innerHTML = `<div class="text-muted small text-center py-3"><i class="fas fa-hourglass-half me-1"></i>Aún no hay estadísticas globales.</div>`;
            return;
        }
        
        let html = '';
        json.stats.slice(0, 5).forEach((s, idx) => {
            const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx+1}.`;
            const wrColor = s.win_rate >= 60 ? 'text-success' : s.win_rate >= 40 ? 'text-warning' : 'text-danger';
            html += `
                <div class="mb-2 pb-2 border-bottom border-secondary" style="font-size: 0.75rem;">
                    <div class="d-flex justify-content-between align-items-center">
                        <strong>${medal} ${(s.strategy || '').length > 25 ? s.strategy.substring(0, 23) + '...' : s.strategy}</strong>
                        <span class="${wrColor}">${s.win_rate}%</span>
                    </div>
                    <div class="text-muted" style="font-size: 0.7rem;">
                        Muestras: ${s.sample || 0} · Exp: ${(s.expectancy || 0).toFixed(2)}
                        ${s.is_degrading ? '<span class="badge bg-warning ms-1" style="font-size: 0.55rem;">⚠️</span>' : ''}
                    </div>
                </div>
            `;
        });
        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = `<div class="alert alert-warning small mb-0">Error</div>`;
    }
};


// ============================================================================
// SOBREESCRIBIR: updateActiveSignals (vela ACTUAL — dinámica)
// ============================================================================
// Solo se ejecuta si estamos en /futures. Usa /api/futures/signals/active
// que retorna SOLO las 5 cripto × 6 TF × LONG/SHORT

window.updateActiveSignals = async function() {

    // futures.js solo se carga en /futures.
    // No dependemos de IS_FUTURES_PAGE para evitar salidas prematuras.
    console.log('🔵 ACTIVE: función llamada');

    // Asegurar que el estado exista aunque otro script
    // lo haya eliminado o reinicializado.
    if (!window._futuresSignalsState) {
        window._futuresSignalsState = {
            activeLoading: false,
            previousLoading: false,
            activeTimer: null,
            previousTimer: null
        };
    }

    const signalsList =
        document.getElementById('active-signals-list');

    const signalsCount =
        document.getElementById('active-signals-count');

    console.log('🔎 ACTIVE estado inicial:', {
        isFuturesPage: window.IS_FUTURES_PAGE,
        state: window._futuresSignalsState,
        hasList: !!signalsList,
        hasCount: !!signalsCount
    });

    if (!signalsList) {
        console.error(
            '❌ ACTIVE: no existe #active-signals-list'
        );
        return;
    }

    // Si ya hay una petición, no crear otra.
    if (window._futuresSignalsState.activeLoading) {
        console.warn(
            '⚠️ ACTIVE: petición anterior marcada como activa.'
        );

        // IMPORTANTE:
        // No nos quedamos bloqueados para siempre.
        // Como no tenemos referencia al fetch anterior,
        // liberamos el estado y permitimos una nueva consulta.
        window._futuresSignalsState.activeLoading = false;
    }

    window._futuresSignalsState.activeLoading = true;

    console.log(
        '🚀 ACTIVE: iniciando consulta...'
    );
    signalsList.innerHTML = `
        <div class="list-group-item bg-dark text-info text-center py-3">
            <div class="spinner-border spinner-border-sm me-2"></div>
            Consultando servidor de Futuros...
        </div>
    `;

    if (signalsCount) {
        signalsCount.textContent = '...';
        signalsCount.className = 'badge bg-info';
    }

    const startedAt = performance.now();

    try {

        const response = await fetch(
            '/api/futures/signals/active?min_confidence=55&_ts=' + Date.now(),
            {
                method: 'GET',
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            }
        );

        const elapsed = (
            (performance.now() - startedAt) / 1000
        ).toFixed(1);

        console.log(
            `📥 ACTIVE HTTP ${response.status} en ${elapsed}s`
        );

        if (!response.ok) {

            const text = await response.text();

            throw new Error(
                `HTTP ${response.status}: ${text.substring(0, 500)}`
            );
        }

        const json = await response.json();

        console.log('📦 ACTIVE JSON:', json);

        // ------------------------------------------------------------
        // ERROR DEL BACKEND
        // ------------------------------------------------------------
        if (!json.success) {

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-danger text-center py-3">

                    <strong>❌ Error del servidor</strong>

                    <br>

                    <small>
                        ${json.error || 'Error desconocido'}
                    </small>

                </div>
            `;

            if (signalsCount) {
                signalsCount.textContent = 'ERR';
                signalsCount.className = 'badge bg-danger';
            }

            return;
        }

        const signals = Array.isArray(json.signals)
            ? json.signals
            : [];

        const progress = json.progress || {};
        const filterStats =
            json.filter_stats || null;

        const diagnosticsHtml =
            futRenderAnalysisDiagnostics(
                json,
                'active'
            );

        const completed = Number(
            progress.completed || 0
        );

        const total = Number(
            progress.total || 30
        );

        const running = Boolean(
            json.running ||
            json.warming_up
        );

        console.log(
            '📊 ACTIVE:',
            {
                signals: signals.length,
                completed,
                total,
                running
            }
        );

        // ------------------------------------------------------------
        // SERVIDOR TODAVÍA PROCESANDO
        // ------------------------------------------------------------
        if (running) {

            const pct = total > 0
                ? Math.min(
                    100,
                    (completed / total) * 100
                )
                : 0;

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-info text-center py-3">

                    <div class="spinner-border spinner-border-sm me-2"></div>

                    <strong>
                        Analizando Futuros: ${completed}/${total}
                    </strong>

                    <br>

                    <small class="text-muted">
                        ${progress.current || 'Preparando análisis...'}
                    </small>

                    <div class="progress mt-2"
                         style="height: 6px;">

                        <div
                            class="progress-bar bg-info"
                            style="width: ${pct}%;">
                        </div>

                    </div>

                    <small class="d-block mt-2 text-secondary">
                        Resultado recibido del servidor en ${elapsed}s
                    </small>

                </div>
            `;

            if (signalsCount) {
                signalsCount.textContent =
                    `${completed}/${total}`;

                signalsCount.className =
                    'badge bg-info';
            }

            return;
        }

        // ------------------------------------------------------------
        // SERVIDOR TERMINÓ
        // ------------------------------------------------------------
        window.futuresActiveLoaded = true;

        if (signalsCount) {

            signalsCount.textContent =
                String(signals.length);

            signalsCount.className =
                `badge bg-${
                    signals.length > 0
                        ? 'success'
                        : 'secondary'
                }`;
        }

        // ------------------------------------------------------------
        // SIN SEÑALES
        // ------------------------------------------------------------
        if (signals.length === 0) {

            signalsList.innerHTML = diagnosticsHtml + `
                <div class="list-group-item bg-dark text-warning text-center py-3">

                    <strong>
                        ✅ Análisis de Futuros completado
                    </strong>

                    <br>

                    <small>
                        No hay señales LONG/SHORT que superen
                        los filtros actuales.
                        ${
                            filterStats
                                ? `
                                <div class="small text-secondary mt-2">
                                    Procesados:
                                    ${filterStats.total_processed || 0}
                                    ·
                                    NO_OPERAR:
                                    ${filterStats.non_directional || 0}
                                    ·
                                    Confianza:
                                    ${filterStats.low_confidence || 0}
                                    ·
                                    Niveles inválidos:
                                    ${filterStats.invalid_levels || 0}
                                    ·
                                    Leverage:
                                    ${filterStats.leverage_out_of_range || 0}
                                </div>
                                `
                                : ''
                        }
                    </small>

                    <br>

                    <small class="text-muted">
                        ${completed}/${total} análisis procesados.
                    </small>

                </div>
            `;

            return;
        }

        // ------------------------------------------------------------
        // RENDER DE SEÑALES
        // ------------------------------------------------------------
        let html = '';

        signals.forEach(sig => {

            const isLong =
                sig.action === 'LONG';

            const badgeColor =
                isLong
                    ? 'success'
                    : 'danger';

            const icon =
                isLong
                    ? '📈'
                    : '📉';

            const symbolName =
                String(sig.symbol || '')
                    .replace('-', '/');

            const confidence =
                Number(sig.confidence || 0);

            const leverage =
                Number(sig.leverage || 1);

            const rr =
                Number(sig.risk_reward || 0);

            const roiTp =
                sig.roi_tp == null ? null : Number(sig.roi_tp);

            const roiSl =
                sig.roi_sl == null ? null : Number(sig.roi_sl);
         
            const remainingSeconds =
                Math.max(
                    0,
                    Number(
                        sig.tiempo_restante
                        || 0
                    )
                );
            
            const validityText =
                _formatPreviousSignalValidity(
                    remainingSeconds
                );
            
            let validityHtml = '';
            
            if (sig.lifecycle_status === 'waiting_entry') {
            
                validityHtml = `
                    <div
                        class="
                            small
                            text-warning
                            mt-1
                        "
                    >
                        ⏳ Esperando que el precio toque Entry · vigente por:
                        <strong>
                            ${validityText}
                        </strong>
                    </div>
                `;
            
            } else if (sig.lifecycle_status === 'entry_touched') {

                validityHtml = `
                    <div class="small text-info mt-1">
                        📍 Entry tocado: operación en seguimiento ·
                        <strong>${validityText}</strong> restantes
                    </div>
                `;

            } else if (sig.lifecycle_status === 'expired') {
            
                validityHtml = `
                    <div
                        class="
                            small
                            text-secondary
                            mt-1
                        "
                    >
                        ⌛ Esta señal ya no es vigente.
                    </div>
                `;
            }
            html += `
                <div
                    class="list-group-item bg-dark text-white border-secondary"
                    style="cursor:pointer;"
                    onclick="window.changeToSignal(
                        '${sig.symbol}',
                        '${sig.timeframe}'
                    )"
                >

                    <div class="d-flex justify-content-between align-items-center">

                        <div>

                            <span class="badge bg-${badgeColor} me-2">
                                ${icon} ${sig.action}
                            </span>

                            <strong>
                                ${symbolName}
                            </strong>

                            <span class="badge bg-dark ms-1">
                                ${sig.timeframe}
                            </span>

                        </div>

                        <span class="badge bg-warning text-dark">
                            ${Math.max(
                                0,
                                Math.min(
                                    100,
                                    confidence
                                )
                            ).toFixed(0)}%
                        </span>

                    </div>

                    <div
                        class="mt-2 d-flex justify-content-between align-items-center"
                        style="font-size:0.75rem;"
                    >

                        <div>

                            <span class="badge bg-secondary me-1">
                                Lev ${leverage}x
                            </span>

                            <span class="badge bg-dark">
                                R/R 1:${rr.toFixed(1)}
                            </span>

                        </div>

                        <div>

                            <span class="text-success">
                                TP ${roiTp == null ? '--' : `${roiTp >= 0 ? '+' : ''}${roiTp.toFixed(1)}%`}
                            </span>

                            <span class="mx-1 text-muted">
                                |
                            </span>

                            <span class="text-danger">
                                SL ${roiSl == null ? '--' : `${roiSl.toFixed(1)}%`}
                            </span>

                        </div>

                    </div>

                    ${validityHtml}

                    ${futRenderDecisionAudit(sig.decision_audit)}

                </div>
            `;
        });

        signalsList.innerHTML = diagnosticsHtml + html;

    } catch (err) {

        console.error(
            '❌ ACTIVE FETCH:',
            err
        );

        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-danger text-center py-3">

                <strong>
                    ❌ No se pudo consultar Futuros
                </strong>

                <br>

                <small>
                    ${err.message || 'Error de conexión'}
                </small>

            </div>
        `;

        if (signalsCount) {

            signalsCount.textContent =
                'ERR';

            signalsCount.className =
                'badge bg-danger';
        }

    } finally {

        window._futuresSignalsState.activeLoading = false;

        console.log(
            '🏁 ACTIVE: request finalizado.'
        );
    }
};


// ============================================================================
// FASE 8.2 — VIGENCIA VISUAL DE SEÑALES DE VELA ANTERIOR
// ============================================================================

function _formatPreviousSignalValidity(seconds) {

    const totalSeconds = Math.max(
        0,
        Number(
            seconds
            || 0
        )
    );

    if (totalSeconds <= 0) {
        return 'vigencia finalizada';
    }

    const days = Math.floor(
        totalSeconds
        / 86400
    );

    const hours = Math.floor(
        (
            totalSeconds
            % 86400
        )
        / 3600
    );

    const minutes = Math.floor(
        (
            totalSeconds
            % 3600
        )
        / 60
    );

    if (days > 0) {

        return (
            `${days}d `
            + `${hours}h`
        );
    }

    if (hours > 0) {

        return (
            `${hours}h `
            + `${minutes}m`
        );
    }

    return `${minutes}m`;
}

function _encodeFuturesSignal(sig) {
    return encodeURIComponent(JSON.stringify(sig)).replace(/'/g, '%27');
}

function _decodeFuturesSignal(encodedSignal) {
    return JSON.parse(decodeURIComponent(encodedSignal));
}

window.openSaveSignalFromCard = function(event, encodedSignal, alreadyInPosition) {
    if (event) event.stopPropagation();

    const sig = _decodeFuturesSignal(
        encodedSignal
    );

    sig.source_context =
        'PREVIOUS_CONFIRMED';

    window.openSaveSignalModal(
        sig,
        Boolean(alreadyInPosition)
    );
};

// ============================================================================
// SOBREESCRIBIR: updatePreviousSignals (vela ANTERIOR — estática)
// ============================================================================

window.updatePreviousSignals = async function() {

    // futures.js solo se carga en /futures.
    console.log('🟣 PREVIOUS: función llamada');

    if (!window._futuresSignalsState) {
        window._futuresSignalsState = {
            activeLoading: false,
            previousLoading: false,
            activeTimer: null,
            previousTimer: null
        };
    }

    const signalsList =
        document.getElementById(
            'prev-signals-list'
        );

    const signalsCount =
        document.getElementById(
            'prev-signals-count'
        );

    console.log(
        '🔎 PREVIOUS estado inicial:',
        {
            isFuturesPage:
                window.IS_FUTURES_PAGE,

            state:
                window._futuresSignalsState,

            hasList:
                !!signalsList,

            hasCount:
                !!signalsCount
        }
    );

    if (!signalsList) {
        console.error(
            '❌ PREVIOUS: no existe #prev-signals-list'
        );
        return;
    }

    if (
        window._futuresSignalsState
            .previousLoading
    ) {

        console.warn(
            '⚠️ PREVIOUS: petición anterior marcada como activa.'
        );

        // Evitar bloqueo permanente.
        window._futuresSignalsState
            .previousLoading = false;
    }

    window._futuresSignalsState
        .previousLoading = true;

    console.log(
        '🚀 PREVIOUS: iniciando consulta...'
    );

    signalsList.innerHTML = `
        <div class="list-group-item bg-dark text-info text-center py-3">

            <div class="spinner-border spinner-border-sm me-2"></div>

            Consultando vela anterior...

        </div>
    `;

    if (signalsCount) {

        signalsCount.textContent =
            '...';

        signalsCount.className =
            'badge bg-info';
    }

    const startedAt =
        performance.now();

    try {

        const response = await fetch(
            '/api/futures/signals/previous?min_confidence=55&_ts='
            + Date.now(),
            {
                method: 'GET',
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            }
        );

        const elapsed =
            (
                (performance.now() -
                    startedAt) / 1000
            ).toFixed(1);

        console.log(
            `📥 PREVIOUS HTTP ${response.status} en ${elapsed}s`
        );

        if (!response.ok) {

            const text =
                await response.text();

            throw new Error(
                `HTTP ${response.status}: ${text.substring(0, 500)}`
            );
        }

        const json =
            await response.json();

        console.log(
            '📦 PREVIOUS JSON:',
            json
        );

        if (!json.success) {

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-danger text-center py-3">

                    <strong>
                        ❌ Error del servidor
                    </strong>

                    <br>

                    <small>
                        ${json.error || 'Error desconocido'}
                    </small>

                </div>
            `;

            if (signalsCount) {

                signalsCount.textContent =
                    'ERR';

                signalsCount.className =
                    'badge bg-danger';
            }

            return;
        }

        const signals =
            Array.isArray(json.signals)
                ? json.signals
                : [];

        const progress =
            json.progress || {};

        const filterStats =
            json.filter_stats || null;

        const diagnosticsHtml =
            futRenderAnalysisDiagnostics(
                json,
                'previous'
            );

        const completed =
            Number(
                progress.completed || 0
            );

        const total =
            Number(
                progress.total || 30
            );

        const running =
            Boolean(
                json.running ||
                json.warming_up
            );

        console.log(
            '📊 PREVIOUS:',
            {
                signals: signals.length,
                completed,
                total,
                running
            }
        );

        // ------------------------------------------------------------
        // SERVIDOR TODAVÍA TRABAJANDO
        // ------------------------------------------------------------
        if (running) {

            const pct =
                total > 0
                    ? Math.min(
                        100,
                        (completed / total) * 100
                    )
                    : 0;

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-info text-center py-3">

                    <div class="spinner-border spinner-border-sm me-2"></div>

                    <strong>
                        Analizando vela anterior:
                        ${completed}/${total}
                    </strong>

                    <br>

                    <small class="text-muted">
                        ${progress.current || 'Preparando análisis...'}
                    </small>

                    <div
                        class="progress mt-2"
                        style="height:6px;"
                    >

                        <div
                            class="progress-bar bg-warning"
                            style="width:${pct}%;">
                        </div>

                    </div>

                    <small
                        class="d-block mt-2 text-secondary"
                    >
                        Respuesta recibida en ${elapsed}s
                    </small>

                </div>
            `;

            if (signalsCount) {

                signalsCount.textContent =
                    `${completed}/${total}`;

                signalsCount.className =
                    'badge bg-info';
            }

            return;
        }

        // ------------------------------------------------------------
        // SERVIDOR TERMINÓ
        // ------------------------------------------------------------
        window.futuresPrevLoaded =
            true;

        if (signalsCount) {
        
            const activeCount =
                Number.isFinite(
                    Number(
                        json.active_count
                    )
                )
                    ? Number(
                        json.active_count
                    )
                    : signals.filter(
                        signal =>
                            signal.activa === 1
                    ).length;
        
            signalsCount.textContent =
                String(
                    activeCount
                );
        
            signalsCount.className =
                `badge bg-${
                    activeCount > 0
                        ? 'warning'
                        : 'secondary'
                }`;
        
            signalsCount.title =
                `${activeCount} señal(es) `
                + 'de vela anterior '
                + 'todavía vigente(s)';
        }

        // ------------------------------------------------------------
        // SIN SEÑALES
        // ------------------------------------------------------------
        if (signals.length === 0) {

            signalsList.innerHTML = diagnosticsHtml + `
                <div class="list-group-item bg-dark text-warning text-center py-3">

                    <strong>
                        ✅ Análisis completado
                    </strong>

                    <br>

                    <small>
                        No hay señales LONG/SHORT ejecutables
                        para la vela anterior.
                    </small>

                    ${filterStats ? `
                        <div class="small text-secondary mt-2">
                            Analizados: ${filterStats.total_processed || 0}
                            · Sin dirección: ${filterStats.non_directional || 0}
                            · Solo análisis / rechazadas por seguridad: ${filterStats.non_executable || 0}
                            · Confianza insuficiente: ${filterStats.low_confidence || 0}
                            · Niveles inválidos: ${filterStats.invalid_levels || 0}
                            · Leverage fuera de rango: ${filterStats.leverage_out_of_range || 0}
                        </div>
                    ` : ''}

                    <br>

                    <small class="text-muted">
                        ${completed}/${total} análisis procesados.
                    </small>

                </div>
            `;

            return;
        }

        // ------------------------------------------------------------
        // RENDER
        // ------------------------------------------------------------
        let html = '';

        signals.forEach(sig => {

            const isLong =
                sig.action === 'LONG';

            const badgeColor =
                isLong
                    ? 'success'
                    : 'danger';

            const icon =
                isLong
                    ? '📈'
                    : '📉';

            const symbolName =
                String(sig.symbol || '')
                    .replace('-', '/');

            const confidence =
                Number(sig.confidence || 0);

            const leverage =
                Number(sig.leverage || 1);

            const rr =
                Number(sig.risk_reward || 0);

            const roiTp =
                sig.roi_tp == null ? null : Number(sig.roi_tp);

            const roiSl =
                sig.roi_sl == null ? null : Number(sig.roi_sl);

            let statusBadge =
                '<span class="badge bg-warning text-dark">⏱️ Activa</span>';

            if (
                sig.resultado === 'tp_hit'
            ) {

                statusBadge =
                    '<span class="badge bg-success">✅ TP</span>';

            } else if (
                sig.resultado === 'sl_hit'
            ) {

                statusBadge =
                    '<span class="badge bg-danger">❌ SL</span>';
            }
            else if (
                sig.resultado === 'expired'
            ) {

                statusBadge =
                    '<span class="badge bg-secondary">⌛ Vencida</span>';
            }
            const inactive =
                sig.activa !== 1;

            const opacity =
                inactive
                    ? 'opacity-50'
                    : '';

            const signalData =
                _encodeFuturesSignal(sig);

            const saveButtons = inactive
                ? ''
                : `
                    <div class="d-flex flex-wrap gap-2 mt-2">
                        <button
                            type="button"
                            class="btn btn-sm btn-outline-success"
                            onclick="window.openSaveSignalFromCard(event, '${signalData}', false)"
                            title="Guardar y esperar a que el precio toque Entry"
                        >
                            🔖 Guardar
                        </button>
                        <button
                            type="button"
                            class="btn btn-sm btn-success"
                            onclick="window.openSaveSignalFromCard(event, '${signalData}', true)"
                            title="Ya entré: usar el precio actual como Entry editable"
                        >
                            ✅ Guardar en operación
                        </button>
                    </div>
                `;

            html += `
                <div
                    class="list-group-item bg-dark text-white border-secondary ${opacity}"
                    style="cursor:pointer;"
                    data-signal="${signalData}"
                    onclick="window.showFuturesPrevJustif(_decodeFuturesSignal(this.getAttribute('data-signal')))"
                >

                    <div class="d-flex justify-content-between align-items-center">

                        <div>

                            <span class="badge bg-${badgeColor} me-2">
                                ${icon} ${sig.action}
                            </span>

                            <strong>
                                ${symbolName}
                            </strong>

                            <span class="badge bg-dark ms-1">
                                ${sig.timeframe}
                            </span>

                        </div>

                        <div>
                            ${statusBadge}

                            <span
                                class="badge bg-secondary ms-1"
                            >
                                ${Math.max(
                                    0,
                                    Math.min(
                                        100,
                                        confidence
                                    )
                                ).toFixed(0)}%
                            </span>
                        </div>

                    </div>

                    <div
                        class="mt-2 d-flex justify-content-between"
                        style="font-size:0.72rem;"
                    >

                        <div>

                            <span class="badge bg-dark me-1">
                                Lev ${leverage}x
                            </span>

                            <span class="badge bg-dark">
                                R/R 1:${rr.toFixed(1)}
                            </span>

                        </div>

                        <div>

                            <span class="text-success">
                                TP ${roiTp == null ? '--' : `${roiTp >= 0 ? '+' : ''}${roiTp.toFixed(1)}%`}
                            </span>

                            <span class="mx-1 text-muted">
                                |
                            </span>

                            <span class="text-danger">
                                SL ${roiSl == null ? '--' : `${roiSl.toFixed(1)}%`}
                            </span>

                        </div>

                    </div>

                    ${saveButtons}

                    ${futRenderDecisionAudit(sig.decision_audit)}

                </div>
            `;
        });

        signalsList.innerHTML =
            diagnosticsHtml + html;

    } catch (err) {

        console.error(
            '❌ PREVIOUS FETCH:',
            err
        );

        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-danger text-center py-3">

                <strong>
                    ❌ No se pudo consultar la vela anterior
                </strong>

                <br>

                <small>
                    ${err.message || 'Error de conexión'}
                </small>

            </div>
        `;

        if (signalsCount) {

            signalsCount.textContent =
                'ERR';

            signalsCount.className =
                'badge bg-danger';
        }

    } finally {

        window._futuresSignalsState
            .previousLoading = false;

        console.log(
            '🏁 PREVIOUS: request finalizado.'
        );
    }
};
// ============================================================================
// GUARDAR REFERENCIAS DE LAS FUNCIONES PROPIAS DE FUTUROS
// ============================================================================
// script.js define posteriormente sus propias versiones Spot dentro de
// DOMContentLoaded y puede sobrescribir window.updateActiveSignals y
// window.updatePreviousSignals.
// Guardamos aquí las funciones correctas de Futuros para restaurarlas después.
// ============================================================================

window._futuresUpdateActiveSignals =
    window.updateActiveSignals;

window._futuresUpdatePreviousSignals =
    window.updatePreviousSignals;

// Modal específico de justificación (vela anterior futuros)
window.showFuturesPrevJustif = function(sig) {
    const body = document.getElementById('prev-signal-details');
    if (!body) return;
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    
    const modal = new bootstrap.Modal(document.getElementById('prevSignalModal'));
    modal.show();
    
    // Renderizar de inmediato
    setTimeout(() => {
        const symbolName = sig.symbol.replace('-', '/');
        const isLong = sig.action === 'LONG';
        const emoji = isLong ? '📈' : '📉';
        const bgColor = isLong ? 'success' : 'danger';
        
        let estadoHTML;
        if (sig.resultado === 'tp_hit') {
            estadoHTML = `<div class="alert alert-success mt-3"><strong>✅ TP ALCANZADO</strong> - operación exitosa</div>`;
        } else if (sig.resultado === 'sl_hit') {

            estadoHTML = `
                <div class="alert alert-danger mt-3">
                    <strong>❌ SL ALCANZADO</strong>
                    - operación invalidada
                </div>
            `;

        } else if (sig.resultado === 'expired') {

            estadoHTML = `
                <div class="alert alert-secondary mt-3">
                    <strong>⌛ VIGENCIA FINALIZADA</strong>
                    <br>
                    Esta señal pertenecía a la vela anterior y
                    su ventana operativa ya terminó.
                    No persigas el precio; espera una nueva señal.
                </div>
            `;

        } else {
        
            const remainingText =
                _formatPreviousSignalValidity(
                    sig.tiempo_restante
                );
        
            estadoHTML = `
                <div
                    class="
                        alert
                        alert-warning
                        mt-3
                    "
                >
                    <strong>
                        ⏱️ SEÑAL TODAVÍA VIGENTE
                    </strong>
        
                    <br>
        
                    La señal pertenece a la vela anterior
                    y todavía se encuentra dentro de su
                    ventana operativa.
        
                    <br>
        
                    <small>
                        Tiempo restante aproximado:
                        <strong>
                            ${remainingText}
                        </strong>
                    </small>
        
                    <br>
        
                    <small class="text-muted">
                        Si no se activa dentro de esta
                        ventana, no debe perseguirse el
                        precio; debe esperarse una nueva señal.
                    </small>
                </div>
            `;
        }
        
        body.innerHTML = `
            <div>
                <div class="d-flex align-items-center mb-3">
                    <span class="badge bg-${bgColor} p-3 me-3" style="font-size: 1.2rem;">
                        ${emoji} ${sig.action}
                    </span>
                    <div>
                        <span class="badge bg-dark d-block mb-1">${symbolName} · ${sig.timeframe}</span>
                        <span class="badge bg-secondary">Confianza: ${fmtConfidence(sig.confidence)}%</span>
                    </div>
                </div>
                ${estadoHTML}
                <div class="row mt-3 g-2">
                    <div class="col-md-3">
                        <div class="border-start border-3 border-primary ps-2">
                            <small class="text-muted d-block">ENTRADA</small>
                            <strong>${futFormatPrice(sig.entry, sig.symbol)}</strong>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-danger ps-2">
                            <small class="text-muted d-block">STOP LOSS</small>
                            <strong>${futFormatPrice(sig.stop_loss, sig.symbol)}</strong>
                            <div class="small text-danger">${futFormatPct(sig.roi_sl, 1)} ROI</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-success ps-2">
                            <small class="text-muted d-block">TAKE PROFIT</small>
                            <strong>${futFormatPrice(sig.take_profit, sig.symbol)}</strong>
                            <div class="small text-success">${futFormatPct(sig.roi_tp, 1)} ROI</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-warning ps-2">
                            <small class="text-muted d-block">APALANCAMIENTO</small>
                            <strong class="text-warning">${sig.leverage}x</strong>
                            <div class="small">R/R 1:${sig.risk_reward.toFixed(1)}</div>
                        </div>
                    </div>
                </div>
                <div class="mt-3 p-3 bg-dark rounded" style="border-left: 3px solid #FFD700;">
                    <small class="text-muted">
                        <strong>Origen TP:</strong> ${sig.tp_source || '--'}<br>
                        <strong>Origen SL:</strong> ${sig.sl_source || '--'}<br>
                        <strong>Precio actual:</strong> ${futFormatPrice(sig.current_price, sig.symbol)}<br>
                        <strong>Vela evaluada:</strong> ${sig.candle_timestamp || '--'}
                    </small>
                </div>
                <div class="mt-3 text-center">
                    <small class="text-muted">
                        <i class="fas fa-info-circle me-1"></i>
                        Con 10 USDT y ${sig.leverage}x apalancamiento:
                        <strong class="text-success">+${(10 * (sig.roi_tp / 100)).toFixed(2)} USDT</strong> si TP,
                        <strong class="text-danger">${(10 * (sig.roi_sl / 100)).toFixed(2)} USDT</strong> si SL
                    </small>
                </div>
            </div>
        `;
    }, 100);
};


// ============================================================================
// SOBREESCRIBIR: updateCorrelationInfo (vista intra-cripto para futuros)
// ============================================================================

window.updateCorrelationInfo = function(data) {
    if (!window.IS_FUTURES_PAGE) {
        // No es futuros → dejamos la implementación de script.js
        // Pero como el objeto window.updateCorrelationInfo lo estamos redefiniendo,
        // aquí retornamos y no hacemos nada (script.js ya fue reemplazado).
        return;
    }
    
    // En futuros: ignoramos el 'data' pasado desde script.js y consultamos
    // directamente /api/futures/correlation
    const tf = document.getElementById('interval-select')?.value || '1h';
    
    fetch(`/api/futures/correlation?timeframe=${tf}`)
        .then(r => r.json())
        .then(json => {
            if (!json.success) return;
            renderFuturesCorrelation(json);
        })
        .catch(err => console.error('Error correlación futuros:', err));
};


function renderFuturesCorrelation(payload) {
    const pairs = payload.pairs || {};
    const ranking = payload.ranking || [];
    const topLong = payload.top_long_candidates || [];
    const topShort = payload.top_short_candidates || [];
    
    // Reemplazar el contenido de la sección correlation-info si existe
    const container = document.getElementById('correlation-info');
    if (!container) return;
    
    // Badge del timeframe
    const tfBadge = document.getElementById('correlation-timeframe');
    if (tfBadge) tfBadge.textContent = payload.timeframe || '1h';
    
    // Helper para colorear dirección
    const dirBadge = (dir, adx) => {
        if (dir === 'bullish') return `<span class="badge bg-success">ALCISTA</span>`;
        if (dir === 'bearish') return `<span class="badge bg-danger">BAJISTA</span>`;
        return `<span class="badge bg-secondary">NEUTRAL</span>`;
    };
    
    // HTML de los 5 pares
    let pairsHTML = '';
    const orderedSymbols = ['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT'];
    orderedSymbols.forEach(sym => {
        const d = pairs[sym];
        if (!d) return;
        const colorMap = {
            'BTC-USDT': '#FFD700',
            'ETH-USDT': '#3A8BFF',
            'SOL-USDT': '#8A63D2',
            'XRP-USDT': '#00C076',
            'ADA-USDT': '#FF69B4'
        };
        const symbolName = sym.replace('-', '/');
        pairsHTML += `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span class="fw-bold" style="color: ${colorMap[sym]};">${symbolName}</span>
                <div class="text-end">
                    ${dirBadge(d.direction, d.adx)}
                    <span class="badge bg-dark ms-1">ADX: ${d.adx.toFixed(1)}</span>
                    ${d.action !== 'NO_OPERAR' ? `<span class="badge bg-info ms-1">${d.action}</span>` : ''}
                </div>
            </div>
        `;
    });
    
    // Top LONG y Top SHORT candidatos
    let topHTML = '<div class="mt-3 pt-3 border-top border-secondary">';
    
    if (topLong.length > 0) {
        topHTML += `
            <div class="mb-2">
                <small class="text-success fw-bold">
                    <i class="fas fa-arrow-up me-1"></i>🚀 Mayor fuerza ALCISTA (LONG):
                </small>
                <div class="mt-1">
                    ${topLong.map((r, idx) => {
                        const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉';
                        return `
                            <div class="d-flex justify-content-between small">
                                <span>${medal} ${r.symbol.replace('-', '/')}</span>
                                <span class="text-success">ADX ${r.adx.toFixed(1)}</span>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }
    
    if (topShort.length > 0) {
        topHTML += `
            <div class="mb-2">
                <small class="text-danger fw-bold">
                    <i class="fas fa-arrow-down me-1"></i>📉 Mayor fuerza BAJISTA (SHORT):
                </small>
                <div class="mt-1">
                    ${topShort.map((r, idx) => {
                        const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉';
                        return `
                            <div class="d-flex justify-content-between small">
                                <span>${medal} ${r.symbol.replace('-', '/')}</span>
                                <span class="text-danger">ADX ${r.adx.toFixed(1)}</span>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }
    
    if (topLong.length === 0 && topShort.length === 0) {
        topHTML += '<div class="text-muted small text-center">Ninguna cripto muestra tendencia fuerte (ADX < 20 en todas)</div>';
    }
    
    topHTML += '</div>';
    
    // Explicación
    const corr = payload.correlation || {};
    const explanation = `
        <div class="mt-3 p-3 bg-dark rounded" style="border-left: 4px solid #17a2b8;">
            <small>
                <i class="fas fa-info-circle me-1 text-info"></i>
                <strong>${corr.rotation_signal || 'MIXED'}:</strong> 
                ${corr.description || 'Sin descripción'}
            </small>
        </div>
    `;
    
    container.innerHTML = `
        <div class="mb-2">
            <small class="text-muted">Direcciones y fuerza de las 5 cripto de futuros en <strong>${payload.timeframe}</strong>:</small>
        </div>
        ${pairsHTML}
        ${topHTML}
        ${explanation}
    `;
}

// ============================================================================
// COMMIT 36L — UI DE PREFERENCIAS DE SCALPING FUTURES
// ============================================================================
//
// Este bloque sólo lee/guarda preferencias del endpoint creado en 36K.
// NO modifica análisis, señales, Safety, Entry, SL, TP ni leverage.
// ============================================================================

window._futuresScalpingPreferencesLoaded = false;


function _futScalpingSetMessage(
    message,
    type = 'secondary'
) {
    const box = document.getElementById(
        'futures-scalping-message'
    );

    if (!box) return;

    box.className = (
        `alert alert-${type} py-2 px-2 small mb-3`
    );

    box.textContent = String(
        message || ''
    );
}


function _futScalpingSetStatus(
    status
) {
    const badge = document.getElementById(
        'futures-scalping-status-badge'
    );

    if (!badge) return;

    if (status === 'ON') {
        badge.textContent = 'ON';
        badge.className = 'badge bg-success';
        return;
    }

    if (status === 'LOGIN') {
        badge.textContent = 'LOGIN';
        badge.className = 'badge bg-secondary';
        return;
    }

    if (status === 'ERROR') {
        badge.textContent = 'ERROR';
        badge.className = 'badge bg-danger';
        return;
    }

    badge.textContent = 'OFF';
    badge.className = 'badge bg-secondary';
}


function _futScalpingApplyPreferences(
    preferences,
    user = null
) {
    const prefs = (
        preferences
        && typeof preferences === 'object'
    )
        ? preferences
        : {};

    const enabled = Boolean(
        prefs.futures_scalping_telegram_enabled
    );

    const enabledInput = document.getElementById(
        'futures-scalping-enabled'
    );

    if (enabledInput) {
        enabledInput.checked = enabled;
    }

    const selectedTimeframes = new Set(
        Array.isArray(
            prefs.futures_scalping_timeframes
        )
            ? prefs.futures_scalping_timeframes
            : []
    );

    document.querySelectorAll(
        '[data-scalping-tf]'
    ).forEach(input => {
        input.checked = selectedTimeframes.has(
            input.value
        );
    });

    const startInput = document.getElementById(
        'futures-scalping-start-time'
    );

    const endInput = document.getElementById(
        'futures-scalping-end-time'
    );

    if (startInput) {
        startInput.value = (
            prefs.futures_scalping_start_time
            || ''
        );
    }

    if (endInput) {
        endInput.value = (
            prefs.futures_scalping_end_time
            || ''
        );
    }

    const selectedDays = new Set(
        (
            Array.isArray(
                prefs.futures_scalping_weekdays
            )
                ? prefs.futures_scalping_weekdays
                : []
        ).map(
            value => Number(value)
        )
    );

    document.querySelectorAll(
        '[data-scalping-day]'
    ).forEach(input => {
        input.checked = selectedDays.has(
            Number(input.value)
        );
    });

    const timezoneInput = document.getElementById(
        'futures-scalping-timezone'
    );

    if (timezoneInput) {
        timezoneInput.value = String(
            prefs.futures_scalping_timezone
            || 'UTC'
        );
    }

    const userLabel = document.getElementById(
        'futures-scalping-user-label'
    );

    if (userLabel) {
        userLabel.textContent = (
            user
            ? String(user)
            : '—'
        );
    }

    _futScalpingSetStatus(
        enabled
            ? 'ON'
            : 'OFF'
    );

    _futScalpingSetMessage(
        enabled
            ? 'Alertas de scalping activadas con tu horario personal.'
            : 'Alertas de scalping desactivadas.',
        enabled
            ? 'success'
            : 'secondary'
    );
}


window.loadFuturesScalpingPreferences = async function(
    options = {}
) {
    if (!window.IS_FUTURES_PAGE) {
        return false;
    }

    const silent = Boolean(
        options.silent
    );

    if (!silent) {
        _futScalpingSetMessage(
            'Cargando preferencias...',
            'info'
        );
    }

    try {
        const response = await fetch(
            '/api/user/futures-scalping-preferences',
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );

        let data = {};

        try {
            data = await response.json();
        } catch (jsonError) {
            data = {};
        }

        if (response.status === 401) {
            window._futuresScalpingPreferencesLoaded = false;

            _futScalpingSetStatus(
                'LOGIN'
            );

            _futScalpingSetMessage(
                'Inicia sesión para configurar tus alertas de scalping.',
                'secondary'
            );

            const userLabel = document.getElementById(
                'futures-scalping-user-label'
            );

            if (userLabel) {
                userLabel.textContent = 'Invitado';
            }

            return false;
        }

        if (
            !response.ok
            || data.success !== true
            || !data.preferences
        ) {
            throw new Error(
                data.error
                || `HTTP ${response.status}`
            );
        }

        _futScalpingApplyPreferences(
            data.preferences,
            data.user
        );

        window._futuresScalpingPreferencesLoaded = true;

        return true;

    } catch (error) {
        console.error(
            '❌ FUTURES SCALPING PREF GET:',
            error
        );

        window._futuresScalpingPreferencesLoaded = false;

        _futScalpingSetStatus(
            'ERROR'
        );

        _futScalpingSetMessage(
            'No se pudieron cargar las preferencias de scalping.',
            'danger'
        );

        return false;
    }
};


function _futScalpingCollectForm() {
    const enabled = Boolean(
        document.getElementById(
            'futures-scalping-enabled'
        )?.checked
    );

    const timeframes = Array.from(
        document.querySelectorAll(
            '[data-scalping-tf]:checked'
        )
    ).map(
        input => input.value
    );

    const weekdays = Array.from(
        document.querySelectorAll(
            '[data-scalping-day]:checked'
        )
    ).map(
        input => Number(input.value)
    ).filter(
        value => (
            Number.isInteger(value)
            && value >= 1
            && value <= 7
        )
    );

    const startTime = (
        document.getElementById(
            'futures-scalping-start-time'
        )?.value
        || null
    );

    const endTime = (
        document.getElementById(
            'futures-scalping-end-time'
        )?.value
        || null
    );

    const timezone = String(
        document.getElementById(
            'futures-scalping-timezone'
        )?.value
        || 'UTC'
    ).trim() || 'UTC';

    return {
        futures_scalping_telegram_enabled:
            enabled,

        futures_scalping_timeframes:
            timeframes,

        futures_scalping_start_time:
            startTime,

        futures_scalping_end_time:
            endTime,

        futures_scalping_weekdays:
            weekdays,

        futures_scalping_timezone:
            timezone
    };
}


function _futScalpingValidateForm(
    payload
) {
    if (
        !payload
        || typeof payload !== 'object'
    ) {
        return 'Configuración inválida.';
    }

    if (
        payload.futures_scalping_telegram_enabled
        !== true
    ) {
        return null;
    }

    if (
        !Array.isArray(
            payload.futures_scalping_timeframes
        )
        || payload.futures_scalping_timeframes.length === 0
    ) {
        return 'Selecciona al menos 5m, 15m o 30m.';
    }

    if (
        !payload.futures_scalping_start_time
        || !payload.futures_scalping_end_time
    ) {
        return 'Define hora inicial y hora final.';
    }

    if (
        !Array.isArray(
            payload.futures_scalping_weekdays
        )
        || payload.futures_scalping_weekdays.length === 0
    ) {
        return 'Selecciona al menos un día de scalping.';
    }

    if (
        !payload.futures_scalping_timezone
    ) {
        return 'Define una zona horaria.';
    }

    return null;
}


window.saveFuturesScalpingPreferences = async function() {
    if (!window.IS_FUTURES_PAGE) {
        return false;
    }

    const payload = (
        _futScalpingCollectForm()
    );

    const validationError = (
        _futScalpingValidateForm(
            payload
        )
    );

    if (validationError) {
        _futScalpingSetMessage(
            validationError,
            'warning'
        );

        futShowToast(
            validationError,
            'warning'
        );

        return false;
    }

    const button = document.getElementById(
        'btn-save-futures-scalping'
    );

    const originalHtml = (
        button
        ? button.innerHTML
        : ''
    );

    if (button) {
        button.disabled = true;
        button.innerHTML = (
            '<span class="spinner-border spinner-border-sm me-1"></span>'
            + 'Guardando...'
        );
    }

    _futScalpingSetMessage(
        'Guardando preferencias...',
        'info'
    );

    try {
        const response = await fetch(
            '/api/user/futures-scalping-preferences',
            {
                method: 'POST',
                credentials: 'same-origin',
                cache: 'no-store',
                headers: {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                    payload
                )
            }
        );

        let data = {};

        try {
            data = await response.json();
        } catch (jsonError) {
            data = {};
        }

        if (response.status === 401) {
            _futScalpingSetStatus(
                'LOGIN'
            );

            _futScalpingSetMessage(
                'Debes iniciar sesión antes de guardar.',
                'warning'
            );

            futShowToast(
                'Debes iniciar sesión para configurar scalping.',
                'warning'
            );

            return false;
        }

        if (
            !response.ok
            || data.success !== true
            || !data.preferences
        ) {
            throw new Error(
                data.error
                || `HTTP ${response.status}`
            );
        }

        _futScalpingApplyPreferences(
            data.preferences,
            data.user
        );

        window._futuresScalpingPreferencesLoaded = true;

        futShowToast(
            data.preferences
                .futures_scalping_telegram_enabled
                ? '⚡ Alertas de scalping activadas.'
                : '🔕 Alertas de scalping desactivadas.',
            'success'
        );

        return true;

    } catch (error) {
        console.error(
            '❌ FUTURES SCALPING PREF POST:',
            error
        );

        _futScalpingSetStatus(
            'ERROR'
        );

        _futScalpingSetMessage(
            (
                'No se pudo guardar: '
                + (
                    error.message
                    || 'error desconocido'
                )
            ),
            'danger'
        );

        futShowToast(
            'No se pudieron guardar las preferencias de scalping.',
            'danger'
        );

        return false;

    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = (
                originalHtml
                || '💾 Guardar'
            );
        }
    }
};


function _futDetectBrowserTimezone() {
    try {
        const timezone = (
            Intl
            .DateTimeFormat()
            .resolvedOptions()
            .timeZone
        );

        if (!timezone) {
            throw new Error(
                'timezone no disponible'
            );
        }

        const input = document.getElementById(
            'futures-scalping-timezone'
        );

        if (input) {
            input.value = timezone;
        }

        _futScalpingSetMessage(
            `Zona detectada: ${timezone}`,
            'info'
        );

        return timezone;

    } catch (error) {
        _futScalpingSetMessage(
            'El navegador no pudo detectar la zona horaria.',
            'warning'
        );

        return null;
    }
}

// ============================================================================
// COMMIT 36P — PERFIL PERSONAL DE RIESGO FUTURES
// ============================================================================

window._futuresRiskProfile = null;


function _futRiskNumber(value) {

    const number = Number(
        value
    );

    if (
        !Number.isFinite(
            number
        )
        || number <= 0
    ) {
        return null;
    }

    return number;
}


function _futRiskInputValue(
    id,
    value
) {

    const element =
        document.getElementById(
            id
        );

    if (!element) {
        return;
    }

    element.value =
        value === null
        || value === undefined
            ? ''
            : value;
}


function _futRiskSetStatus(
    mode
) {

    const badge =
        document.getElementById(
            'futures-risk-status-badge'
        );

    if (!badge) {
        return;
    }

    if (
        mode === 'PROFILE_ADVISORY'
    ) {

        badge.textContent =
            'PERFIL';

        badge.className =
            'badge bg-info text-dark';

    } else {

        badge.textContent =
            'MANUAL';

        badge.className =
            'badge bg-secondary';
    }
}


function _futRiskSetMessage(
    text,
    type = 'secondary'
) {

    const element =
        document.getElementById(
            'futures-risk-message'
        );

    if (!element) {
        return;
    }

    element.className =
        (
            'alert '
            + `alert-${type} `
            + 'py-2 px-2 small mb-3'
        );

    element.textContent =
        text;
}


function _futApplyRiskProfileForm(
    profile,
    user
) {

    profile =
        profile
        || {};

    window._futuresRiskProfile =
        profile;


    const mode =
        String(
            profile.futures_risk_mode
            || 'MANUAL'
        ).toUpperCase();


    const policy =
        String(
            profile.futures_margin_policy
            || 'FIXED_USDT'
        ).toUpperCase();


    const modeEl =
        document.getElementById(
            'futures-risk-mode'
        );

    const policyEl =
        document.getElementById(
            'futures-margin-policy'
        );


    if (modeEl) {
        modeEl.value =
            mode;
    }


    if (policyEl) {
        policyEl.value =
            policy;
    }


    _futRiskInputValue(
        'futures-risk-equity',
        profile.futures_equity_usdt
    );


    _futRiskInputValue(
        'futures-risk-allocation',
        profile.futures_max_allocation_pct
    );


    _futRiskInputValue(
        'futures-risk-max-loss',
        profile
            .futures_max_loss_pct_equity_per_trade
    );


    _futRiskInputValue(
        'futures-risk-preferred-margin',
        profile.futures_preferred_margin_usdt
    );


    _futRiskInputValue(
        'futures-risk-max-leverage',
        profile.futures_personal_max_leverage
    );


    const userLabel =
        document.getElementById(
            'futures-risk-user-label'
        );


    if (userLabel) {

        userLabel.textContent =
            user
            || '—';
    }


    _futRiskSetStatus(
        mode
    );


    if (
        mode === 'PROFILE_ADVISORY'
    ) {

        _futRiskSetMessage(
            (
                'Perfil personal activo. '
                + 'El sistema usará tus límites para '
                + 'sugerirte cuánto margen y leverage usar. '
                + 'No convierte una señal mala en buena.'
            ),
            'info'
        );

    } else {

        _futRiskSetMessage(
            (
                'Modo manual: tú decides cuánto margen '
                + 'y leverage utilizar. '
                + 'Tus límites personales no se aplican '
                + 'automáticamente.'
            ),
            'secondary'
        );
    }
}


window.loadFuturesRiskProfile =
async function({
    silent = false
} = {}) {

    if (
        !window.IS_FUTURES_PAGE
    ) {
        return null;
    }


    try {

        const response =
            await fetch(
                '/api/user/futures-risk-profile',
                {
                    method:
                        'GET',

                    credentials:
                        'same-origin',

                    cache:
                        'no-store'
                }
            );


        const json =
            await response.json();


        if (
            !response.ok
            || !json.success
        ) {

            if (
                response.status === 401
            ) {

                window._futuresRiskProfile =
                    null;

                _futRiskSetStatus(
                    'MANUAL'
                );

                _futRiskSetMessage(
                    (
                        'Inicia sesión para usar '
                        + 'tu perfil de riesgo Futures.'
                    ),
                    'secondary'
                );

                return null;
            }


            throw new Error(
                json.error
                || 'No se pudo cargar el perfil.'
            );
        }


        _futApplyRiskProfileForm(
            json.profile,
            json.user
        );


        return json.profile;


    } catch (error) {

        console.warn(
            '⚠️ 36P perfil de riesgo:',
            error
        );


        if (!silent) {

            _futRiskSetMessage(
                (
                    'No se pudo cargar el perfil. '
                    + 'Se conserva modo manual.'
                ),
                'warning'
            );
        }


        return null;
    }
};


function _futCollectRiskProfile() {

    const mode =
        String(
            document
                .getElementById(
                    'futures-risk-mode'
                )
                ?.value
            || 'MANUAL'
        ).toUpperCase();


    const policy =
        String(
            document
                .getElementById(
                    'futures-margin-policy'
                )
                ?.value
            || 'FIXED_USDT'
        ).toUpperCase();


    const optionalNumber =
        id => {

            const value =
                document
                    .getElementById(
                        id
                    )
                    ?.value;

            if (
                value === ''
                || value === undefined
                || value === null
            ) {
                return null;
            }

            const number =
                Number(
                    value
                );

            return Number.isFinite(
                number
            )
                ? number
                : null;
        };


    return {
        futures_risk_mode:
            mode,

        futures_margin_policy:
            policy,

        futures_equity_usdt:
            optionalNumber(
                'futures-risk-equity'
            ),

        futures_max_allocation_pct:
            optionalNumber(
                'futures-risk-allocation'
            ),

        futures_max_loss_pct_equity_per_trade:
            optionalNumber(
                'futures-risk-max-loss'
            ),

        futures_preferred_margin_usdt:
            optionalNumber(
                'futures-risk-preferred-margin'
            ),

        futures_personal_max_leverage:
            optionalNumber(
                'futures-risk-max-leverage'
            ),
    };
}


window.saveFuturesRiskProfile =
async function() {

    try {

        const profile =
            _futCollectRiskProfile();


        const response =
            await fetch(
                '/api/user/futures-risk-profile',
                {
                    method:
                        'POST',

                    credentials:
                        'same-origin',

                    headers: {
                        'Content-Type':
                            'application/json'
                    },

                    body:
                        JSON.stringify(
                            profile
                        )
                }
            );


        const json =
            await response.json();


        if (
            !response.ok
            || !json.success
        ) {

            throw new Error(
                json.error
                || 'No se pudo guardar.'
            );
        }


        _futApplyRiskProfileForm(
            json.profile,
            json.user
        );


        futShowToast(
            '🛡️ Perfil Futures guardado',
            'success'
        );


    } catch (error) {

        _futRiskSetMessage(
            error.message,
            'danger'
        );


        futShowToast(
            (
                'Perfil de riesgo: '
                + error.message
            ),
            'danger'
        );
    }
};


function _futCalculatePersonalSizing(
    signal,
    entry,
    stopLoss
) {

    const profile =
        window._futuresRiskProfile
        || {};


    const mode =
        String(
            profile.futures_risk_mode
            || 'MANUAL'
        ).toUpperCase();


    const technicalLeverage =
        Math.max(
            1,
            Math.floor(
                Number(
                    signal?.leverage
                )
                || 1
            )
        );


    let appliedLeverage =
        technicalLeverage;


    const personalMax =
        _futRiskNumber(
            profile
                .futures_personal_max_leverage
        );


    if (
        mode === 'PROFILE_ADVISORY'
        && personalMax
    ) {

        appliedLeverage =
            Math.min(
                technicalLeverage,
                Math.max(
                    1,
                    Math.floor(
                        personalMax
                    )
                )
            );
    }


    // ================================================================
    // DEFAULT ANTIGUO
    // ================================================================

    let baseMargin =
        10.0;

    let marginSource =
        'DEFAULT_10_USDT';


    const equity =
        _futRiskNumber(
            profile
                .futures_equity_usdt
        );


    const allocationPct =
        _futRiskNumber(
            profile
                .futures_max_allocation_pct
        );


    const preferredMargin =
        _futRiskNumber(
            profile
                .futures_preferred_margin_usdt
        );


    const maxLossPct =
        _futRiskNumber(
            profile
                .futures_max_loss_pct_equity_per_trade
        );


    const marginPolicy =
        String(
            profile.futures_margin_policy
            || 'FIXED_USDT'
        ).toUpperCase();


    if (
        mode === 'PROFILE_ADVISORY'
    ) {

        if (
            marginPolicy === 'EQUITY_PCT'
            && equity
            && allocationPct
        ) {

            baseMargin =
                equity
                * allocationPct
                / 100.0;

            marginSource =
                'EQUITY_PCT';


        } else if (
            preferredMargin
        ) {

            baseMargin =
                preferredMargin;

            marginSource =
                'FIXED_USDT';
        }
    }


    let suggestedMargin =
        baseMargin;


    let riskBudgetUsdt =
        null;


    let maxMarginBySL =
        null;


    const entryNumber =
        Number(
            entry
        );


    const stopNumber =
        Number(
            stopLoss
        );


    let stopFraction =
        null;


    if (
        Number.isFinite(
            entryNumber
        )
        && entryNumber > 0
        && Number.isFinite(
            stopNumber
        )
        && stopNumber > 0
    ) {

        stopFraction =
            Math.abs(
                entryNumber
                - stopNumber
            )
            / entryNumber;
    }


    // ================================================================
    // PERSONAL MAX LOSS CAP
    // ================================================================
    //
    // NO mueve el SL.
    //
    // Reduce margen sugerido si el sizing original implicaría
    // una pérdida superior al presupuesto personal.
    // ================================================================

    if (
        mode === 'PROFILE_ADVISORY'
        && equity
        && maxLossPct
        && stopFraction
        && stopFraction > 0
    ) {

        riskBudgetUsdt =
            equity
            * maxLossPct
            / 100.0;


        const lossPerMarginUsdt =
            appliedLeverage
            * stopFraction;


        if (
            lossPerMarginUsdt > 0
        ) {

            maxMarginBySL =
                riskBudgetUsdt
                / lossPerMarginUsdt;


            suggestedMargin =
                Math.min(
                    suggestedMargin,
                    maxMarginBySL
                );
        }
    }


    suggestedMargin =
        Math.max(
            0.01,
            suggestedMargin
        );


    const estimatedLossAtSL =
        (
            stopFraction
            && stopFraction > 0
        )
            ? (
                suggestedMargin
                * appliedLeverage
                * stopFraction
            )
            : null;


    return {
        mode:
            mode,

        marginSource:
            marginSource,

        technicalLeverage:
            technicalLeverage,

        appliedLeverage:
            appliedLeverage,

        baseMargin:
            baseMargin,

        suggestedMargin:
            suggestedMargin,

        riskBudgetUsdt:
            riskBudgetUsdt,

        maxMarginBySL:
            maxMarginBySL,

        estimatedLossAtSL:
            estimatedLossAtSL,
    };
}


function _futApplyRiskProfileToSaveModal(
    signal,
    entry,
    stopLoss
) {

    const investmentEl =
        document.getElementById(
            'ss-investment'
        );

    const leverageEl =
        document.getElementById(
            'ss-leverage'
        );

    const leverageHint =
        document.getElementById(
            'ss-leverage-hint'
        );

    const preview =
        document.getElementById(
            'ss-risk-profile-preview'
        );


    if (
        !investmentEl
        || !leverageEl
    ) {
        return;
    }


    const sizing =
        _futCalculatePersonalSizing(
            signal,
            entry,
            stopLoss
        );


    if (
        sizing.mode
        !== 'PROFILE_ADVISORY'
    ) {

        if (preview) {

            preview.className =
                (
                    'alert alert-secondary '
                    + 'py-2 px-3 small mb-0'
                );

            preview.textContent =
                (
                    'Perfil 36P: MANUAL. '
                    + 'Se conserva el sizing actual.'
                );
        }


        return;
    }


    investmentEl.value =
        sizing
            .suggestedMargin
            .toFixed(
                2
            );


    leverageEl.value =
        sizing.appliedLeverage;


    if (leverageHint) {

        leverageHint.textContent =
            (
                'Leverage técnico: '
                + `${sizing.technicalLeverage}x`
                + ' · perfil usado: '
                + `${sizing.appliedLeverage}x`
            );
    }


    if (preview) {

        const lossText =
            sizing.estimatedLossAtSL
            !== null
                ? (
                    sizing
                        .estimatedLossAtSL
                        .toFixed(
                            2
                        )
                    + ' USDT'
                )
                : '--';


        const budgetText =
            sizing.riskBudgetUsdt
            !== null
                ? (
                    sizing
                        .riskBudgetUsdt
                        .toFixed(
                            2
                        )
                    + ' USDT'
                )
                : '--';


        preview.className =
            (
                'alert alert-info '
                + 'py-2 px-3 small mb-0'
            );


        preview.textContent =
            (
                '36P · Margen sugerido: '
                + `${sizing.suggestedMargin.toFixed(2)} USDT`
                + ' · pérdida aprox. al SL: '
                + lossText
                + ' · límite personal: '
                + budgetText
            );
    }
}

// ============================================================================
// INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // =========================================================================
    // RESTAURAR LAS FUNCIONES DE FUTUROS
    // =========================================================================
    // script.js registra su propio DOMContentLoaded antes que futures.js y
    // puede sobrescribir temporalmente estas funciones con la versión Spot.
    // Aquí restauramos explícitamente las versiones de Futuros.
    // =========================================================================

    if (
        typeof window._futuresUpdateActiveSignals === 'function'
    ) {
        window.updateActiveSignals =
            window._futuresUpdateActiveSignals;

        console.log(
            '✅ FUTUROS: updateActiveSignals restaurada'
        );
    } else {
        console.error(
            '❌ FUTUROS: no existe _futuresUpdateActiveSignals'
        );
    }

    if (
        typeof window._futuresUpdatePreviousSignals === 'function'
    ) {
        window.updatePreviousSignals =
            window._futuresUpdatePreviousSignals;

        console.log(
            '✅ FUTUROS: updatePreviousSignals restaurada'
        );
    } else {
        console.error(
            '❌ FUTUROS: no existe _futuresUpdatePreviousSignals'
        );
    }
    setTimeout(() => {
        insertReviewTraderPanel();
    }, 800);
    // =====================================================================
    // COMMIT 36L — PREFERENCIAS SCALPING FUTURES
    // =====================================================================

    const scalpingCollapse = document.getElementById(
        'futures-scalping-settings-body'
    );

    if (scalpingCollapse) {
        scalpingCollapse.addEventListener(
            'shown.bs.collapse',
            () => {
                // Releer al abrir: si el usuario inició sesión después
                // de cargar la página, aquí recuperamos sus preferencias.
                window.loadFuturesScalpingPreferences({
                    silent:
                        window._futuresScalpingPreferencesLoaded
                });
            }
        );
    }

    document.getElementById(
        'btn-save-futures-scalping'
    )?.addEventListener(
        'click',
        window.saveFuturesScalpingPreferences
    );

    document.getElementById(
        'btn-refresh-futures-scalping'
    )?.addEventListener(
        'click',
        () => {
            window.loadFuturesScalpingPreferences({
                silent: false
            });
        }
    );

    document.getElementById(
        'btn-detect-futures-scalping-timezone'
    )?.addEventListener(
        'click',
        _futDetectBrowserTimezone
    );

    // Una lectura silenciosa actualiza el badge ON/OFF.
    // Si todavía no hay login, queda LOGIN y se reintenta al abrir el panel.
    setTimeout(
        () => {
            window.loadFuturesScalpingPreferences({
                silent: true
            });
        },
        1800
    );


    // =====================================================================
    // COMMIT 36P — PERFIL PERSONAL DE RIESGO FUTURES
    // =====================================================================

    const riskCollapse =
        document.getElementById(
            'futures-risk-settings-body'
        );


    if (riskCollapse) {

        riskCollapse.addEventListener(
            'shown.bs.collapse',
            () => {

                window.loadFuturesRiskProfile({
                    silent: false
                });
            }
        );
    }


    const saveRiskButton =
        document.getElementById(
            'btn-save-futures-risk'
        );


    if (saveRiskButton) {

        saveRiskButton.addEventListener(
            'click',
            () => {

                window.saveFuturesRiskProfile();
            }
        );
    }


    const refreshRiskButton =
        document.getElementById(
            'btn-refresh-futures-risk'
        );


    if (refreshRiskButton) {

        refreshRiskButton.addEventListener(
            'click',
            () => {

                window.loadFuturesRiskProfile({
                    silent: false
                });
            }
        );
    }


    setTimeout(
        () => {

            window.loadFuturesRiskProfile({
                silent: true
            });

        },
        2200
    );


    // ============ INICIALIZAR ANÁLISIS PRINCIPAL DE FUTUROS ============

    // Refrescar panel review cada 3 min (v15: reduce carga en Render Free)
    setInterval(() => {
        if (typeof window.refreshReviewPanel === 'function') window.refreshReviewPanel();
    }, 180000);
    
    // Refrescar stats globales cada 5 min
    setInterval(() => {
        if (typeof window.loadGlobalStats === 'function') window.loadGlobalStats();
    }, 300000);
    
    // Cargar señales activas y anteriores inmediatamente (con delay para que
    // futures.js termine de sobrescribir window.updateActiveSignals y updatePreviousSignals)
    setTimeout(async () => {
    
        if (typeof window.updateActiveSignals === 'function') {
            console.log('🚀 futures.js: cargando señales activas iniciales');
            window.updateActiveSignals();
        }
    
        // Dar prioridad a la lista de señales activas.
        // La lista anterior utiliza el mismo caché pesado de 30 análisis.
        setTimeout(() => {
            if (typeof window.updatePreviousSignals === 'function') {
                console.log('📜 futures.js: cargando señales de vela anterior');
                window.updatePreviousSignals();
            }
        }, 5000);
    
    }, 1200);
    
    // Refrescar señales activas cada 2 min (v15: reduce carga)
    setInterval(() => {
        if (typeof window.updateActiveSignals === 'function') window.updateActiveSignals();
    }, 120000);
    
    // Refrescar señales anteriores cada 10 min
    setInterval(() => {
        if (typeof window.updatePreviousSignals === 'function') window.updatePreviousSignals();
    }, 600000);
    
    // Cargar correlación al inicio
    setTimeout(() => {
        if (typeof window.updateCorrelationInfo === 'function') {
            window.updateCorrelationInfo({});
        }
    }, 1500);
    
    // Refrescar correlación cuando cambia el timeframe
    document.getElementById('interval-select')?.addEventListener('change', () => {
        setTimeout(() => {
            if (typeof window.updateCorrelationInfo === 'function') {
                window.updateCorrelationInfo({});
            }
            if (typeof window.updateActiveSignals === 'function') {
                window.updateActiveSignals();
            }
        }, 500);
    });
});


// ============================================================================
// v22.9: SEÑALES GUARDADAS (solo página FUTUROS)
// ============================================================================
// El usuario ve una señal en "Señales de la Vela Anterior" → click → modal
// justificación → botón GUARDAR → modal con inputs → confirmar → señal
// aparece en pestaña "Señales Guardadas" con KPIs propios.
//
// Auto-cierre: el learning_worker cada 30 min evalúa contra precio actual
// y marca entry_touched / tp_hit / sl_hit. Cuando se cierra por TP/SL o
// manualmente, deja de aparecer en la lista de activas.
// ============================================================================

// Referencia global a la señal actualmente mostrada en el modal de justificación
window._currentPrevSignal = null;
// Referencia global a la señal guardada mostrada en el modal detalle
window._currentSavedSignal = null;

// ============ Botón GUARDAR en modal de justificación ============
// Solo visible en la página de FUTUROS. Se hace visible cuando showFuturesPrevJustif se ejecuta.
// ============ Botón GUARDAR en modal de justificación ============
// Solo visible en la página de FUTUROS. Se hace visible cuando showFuturesPrevJustif se ejecuta.
(function _wrapShowPrevJustif() {
    if (!window.IS_FUTURES_PAGE) return;
    const original = window.showFuturesPrevJustif;
    if (typeof original !== 'function') return;

    window.showFuturesPrevJustif = function(sig) {
    
            sig.source_context =
                sig.source_context
                || 'PREVIOUS_CONFIRMED';
    
            // Guardar la señal en una variable global PERO también pasarla directamente al botón
            window._currentPrevSignal = sig;
        original(sig);
        
        // Configurar el botón GUARDAR para que pase la señal DIRECTAMENTE
        setTimeout(() => {
            const btn = document.getElementById('btn-save-signal');
            if (btn) {
                btn.style.display = 'inline-block';
                // PASAR sig DIRECTAMENTE - no depender de window._currentPrevSignal
                btn.onclick = function() {
                    window.openSaveSignalModal(sig, false);
                };
            }
        }, 150);
    };
})();

// ============ Abrir modal "Guardar señal" ============
// ============ Abrir modal "Guardar señal" ============
window.openSaveSignalModal = function(sig, alreadyInPosition = false) {
    // Si no recibe parámetro, fallback a la variable global (compatibilidad)
    if (!sig) {
        sig = window._currentPrevSignal;
    }
    
   
    if (!sig) {
        showToast('No hay señal activa ni seleccionada. Esperá a que cargue el análisis o hacé clic en una señal de la vela anterior.', 'warning');
        return;
    }

    window._currentPrevSignal = sig;
    window._saveSignalAlreadyInPosition = Boolean(alreadyInPosition);
    const isManualAnalysis = (
        sig.execution_origin
        === 'USER_MANUAL_ANALYSIS'
    );

    if (
        isManualAnalysis
        && (
            !(Number(sig.entry) > 0)
            || !(Number(sig.stop_loss) > 0)
            || !(Number(sig.take_profit) > 0)
        )
    ) {
        futShowToast(
            'No se puede guardar manualmente: faltan niveles originales válidos.',
            'warning'
        );
        return;
    }

    // Cerrar el modal actual de justificación
    const prevModal = bootstrap.Modal.getInstance(document.getElementById('prevSignalModal'));
    if (prevModal) prevModal.hide();

    // Prefijar inputs con los valores sugeridos por el sistema
    const info = document.getElementById('save-signal-info');
    if (info) {
        const emoji = sig.action === 'LONG' ? '📈' : '📉';
        const badgeClass = sig.action === 'LONG' ? 'success' : 'danger';
        info.innerHTML = `
            <div class="d-flex align-items-center mb-2">
                <span class="badge bg-${badgeClass} p-2 me-3">${emoji} ${sig.action}</span>
                <strong>${(sig.symbol || '???').replace('-', '/')}</strong>
                <span class="badge bg-dark ms-2">${sig.timeframe}</span>
                <span class="badge bg-secondary ms-2">Confianza ${Math.round(sig.confidence || 0)}%</span>
            </div>
        `;
    }

    document.getElementById('ss-investment').value = 10;
    document.getElementById('ss-leverage').value = sig.leverage || 1;
    document.getElementById('ss-leverage-hint').textContent = `Sugerido por el sistema: ${sig.leverage || 1}x`;
    
    // ============================================================
    // 36M FINAL — NO INVENTAR ENTRY / SL / TP
    // ============================================================
    // Las señales Previous deben conservar los niveles estructurales
    // calculados por el sistema.
    //
    // El precio live sólo puede servir como referencia de Entry cuando
    // el usuario declara explícitamente "Guardar en operación".
    // Nunca se fabrican SL/TP porcentuales de respaldo.
    // ============================================================
    
    const sourceEntry = Number(
        sig.entry
        || sig.entry_price
        || 0
    );
    
    const sourceSL = Number(
        sig.stop_loss
        || 0
    );
    
    const sourceTP = Number(
        sig.take_profit
        || 0
    );
    
    // Una Previous guardable debe conservar siempre SL y TP reales.
    if (
        !(sourceSL > 0)
        || !(sourceTP > 0)
    ) {
        futShowToast(
            'No se puede guardar: la señal no conserva SL/TP estructurales válidos.',
            'warning'
        );
        return;
    }
    
    // Si todavía NO estamos en posición, también debe existir
    // el Entry estructural original.
    if (
        !alreadyInPosition
        && !(sourceEntry > 0)
    ) {
        futShowToast(
            'No se puede guardar: la señal no conserva un Entry estructural válido.',
            'warning'
        );
        return;
    }
    
    // Sólo "Guardar en operación" puede sugerir el precio live
    // como Entry editable. Nunca se usa para fabricar SL o TP.
    const liveEntryPrice = alreadyInPosition
        ? Number(
            sig.current_price
            || sig.live_price
            || window.lastPrices?.[sig.symbol]
            || 0
        )
        : 0;
    
    document.getElementById('ss-entry').value =
        alreadyInPosition
            ? (
                liveEntryPrice > 0
                    ? liveEntryPrice.toFixed(2)
                    : sourceEntry
            )
            : sourceEntry;
    
    document.getElementById('ss-sl').value =
        sourceSL;
    
    document.getElementById('ss-tp').value =
        sourceTP;

    // ============================================================
    // COMMIT 36P
    // QUALITY GATE YA OCURRIÓ.
    // AHORA SÓLO APLICAMOS SIZING PERSONAL.
    // ============================================================

    const riskSizingEntry =
        Number(
            document
                .getElementById(
                    'ss-entry'
                )
                ?.value
            || sourceEntry
        );


    _futApplyRiskProfileToSaveModal(
        sig,
        riskSizingEntry,
        sourceSL
    );
    
    document.getElementById('ss-notes').value = '';
    // v22.9.4: fecha/hora de ingreso — default = ahora en zona local del navegador
    document.getElementById('ss-entry-at').value = _nowLocalDatetimeInput();

    const modalElement = document.getElementById('saveSignalModal');
    const modalTitle = modalElement?.querySelector('.modal-title');
    const confirmButton = modalElement?.querySelector('.modal-footer .btn-success');
    if (modalTitle) {
        if (isManualAnalysis) {
            const riskClass = String(
                sig.manual_risk_class
                || ''
            ).toUpperCase();

            modalTitle.innerHTML = (
                riskClass === 'MEDIUM'
                    ? '🟠 Guardar seguimiento manual · Riesgo medio'
                    : '🔴 Guardar seguimiento experimental · Riesgo alto'
            );
        } else {
            modalTitle.innerHTML = alreadyInPosition
                ? '<i class="fas fa-check-circle me-2 text-success"></i>Guardar operación ya iniciada'
                : '<i class="fas fa-bookmark me-2 text-success"></i>Guardar señal y esperar Entry';
        }
    }
    if (confirmButton) {
        confirmButton.innerHTML = alreadyInPosition
            ? '<i class="fas fa-check me-2"></i>Guardar en operación'
            : '<i class="fas fa-check me-2"></i>Guardar señal';
    }

    // Habilitar preview del cálculo
    _updateSaveCalcPreview();
    ['ss-investment', 'ss-leverage', 'ss-entry', 'ss-sl', 'ss-tp'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', _updateSaveCalcPreview);
    });

    const modal = new bootstrap.Modal(document.getElementById('saveSignalModal'));
    modal.show();
};
function _updateSaveCalcPreview() {
    const sig = window._currentPrevSignal;
    if (!sig) return;
    const investment = parseFloat(document.getElementById('ss-investment').value) || 0;
    const leverage = parseInt(document.getElementById('ss-leverage').value) || 1;
    const entry = parseFloat(document.getElementById('ss-entry').value) || 0;
    const sl = parseFloat(document.getElementById('ss-sl').value) || 0;
    const tp = parseFloat(document.getElementById('ss-tp').value) || 0;
    const dir = sig.action === 'LONG' ? 1 : -1;
    
    if (entry <= 0 || sl <= 0 || tp <= 0) {
        document.getElementById('ss-calc-preview').innerHTML = '<span class="text-muted">Completa entry/SL/TP para ver el cálculo.</span>';
        return;
    }
    
    const tpPct = ((tp - entry) / entry) * 100 * leverage * dir;
    const slPct = ((sl - entry) / entry) * 100 * leverage * dir;
    const tpUsdt = investment * (tpPct / 100);
    const slUsdt = investment * (slPct / 100);
    const rr = Math.abs(tpPct / slPct).toFixed(2);
    
    document.getElementById('ss-calc-preview').innerHTML = `
        Si TP: <strong class="text-success">+${tpUsdt.toFixed(2)} USDT (${tpPct.toFixed(2)}%)</strong>
        · Si SL: <strong class="text-danger">${slUsdt.toFixed(2)} USDT (${slPct.toFixed(2)}%)</strong>
        · R/R: <strong>${rr}</strong>
    `;
}

// ============ Confirmar guardar señal ============
// v22.9.4: formatear fecha ISO -> string legible en hora local del navegador
function _fmtLocalDate(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return String(iso);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (e) {
        return String(iso);
    }
}

// v22.9.4: helper para formato datetime-local (YYYY-MM-DDTHH:mm) en hora local
function _nowLocalDatetimeInput() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// v22.9.4: convertir datetime-local (local naive) a ISO UTC
function _localDatetimeToISO(dtLocal) {
    if (!dtLocal) return null;
    try {
        // datetime-local no lleva zona; JS lo interpreta como hora local del navegador
        const d = new Date(dtLocal);
        if (isNaN(d.getTime())) return null;
        return d.toISOString();
    } catch (e) {
        return null;
    }
}

window.confirmSaveSignal = async function() {
    // Usar la señal que se pasó al abrir el modal (guardada en _currentPrevSignal)
    const sig = window._currentPrevSignal;
    if (!sig) {
        showToast('No hay señal seleccionada', 'warning');
        return;
    }

    // OBTENER USUARIO AUTENTICADO
    const user = (typeof getAuthenticatedUser === 'function' && getAuthenticatedUser()) 
              || (typeof currentUser !== 'undefined' && currentUser) 
              || localStorage.getItem('tgp_session_user') 
              || localStorage.getItem('smarttrading_user') 
              || 'Invitado';
    
    if (user === 'Invitado') {
        showToast('Debes iniciar sesión para guardar señales', 'warning');
        return;
    }

    const investment = parseFloat(document.getElementById('ss-investment').value);
    const leverage = parseInt(document.getElementById('ss-leverage').value);
    const entry = parseFloat(document.getElementById('ss-entry').value);
    const sl = parseFloat(document.getElementById('ss-sl').value);
    const tp = parseFloat(document.getElementById('ss-tp').value);
    const notes = document.getElementById('ss-notes').value || '';
    const entryAtLocal = document.getElementById('ss-entry-at').value;
    const entryAtISO = _localDatetimeToISO(entryAtLocal);

    if (!(investment > 0) || !(leverage > 0) || !(entry > 0) || !(sl > 0) || !(tp > 0)) {
        showToast('Todos los campos deben ser mayores que 0', 'warning');
        return;
    }

    const levelsAreOrdered = sig.action === 'LONG'
        ? (sl < entry && entry < tp)
        : (tp < entry && entry < sl);

    if (!levelsAreOrdered) {
        showToast(
            sig.action === 'LONG'
                ? 'LONG inválido: debe cumplirse SL < Entry < TP'
                : 'SHORT inválido: debe cumplirse TP < Entry < SL',
            'warning'
        );
        return;
    }

    const payload = {
        user_name: user,  // <-- AGREGADO: enviar usuario autenticado
        symbol: sig.symbol,
        timeframe: sig.timeframe,
        action: sig.action,
        confidence: sig.confidence,
        entry, stop_loss: sl, take_profit: tp,
        leverage, investment_usdt: investment,
        original_confidence: sig.confidence,
        original_entry: sig.entry,
        original_stop_loss: sig.stop_loss,
        original_take_profit: sig.take_profit,
        original_leverage: sig.leverage,
        candle_timestamp: sig.candle_timestamp,
        entry_at: entryAtISO,
        already_in_position: Boolean(window._saveSignalAlreadyInPosition),
        execution_origin:
            sig.execution_origin
            || 'SYSTEM_EXECUTABLE',

        risk_class:
            sig.manual_risk_class
            || 'PREMIUM',

        source_signal_id:
            sig.source_signal_id
            || sig.signal_id
            || null,
        
                source_context:
                    sig.source_context
                    || null,
        
                manual_override_ack:
                    Boolean(
                sig.manual_override_ack
            ),

        system_executable:
            sig.execution_origin
            !== 'USER_MANUAL_ANALYSIS',

        notes,
    };

    console.log('📤 Guardando señal:', payload);

    try {
        const res = await fetch('/api/saved_signals', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });

        // MANEJO DE ERRORES HTTP
        if (!res.ok) {
            const errorText = await res.text();
            console.error('❌ HTTP error:', res.status, errorText);
            showToast('Error ' + res.status + ': ' + (errorText || 'No autorizado'), 'error');
            return;
        }

        const json = await res.json();
        if (json.success) {
            showToast(
                window._saveSignalAlreadyInPosition
                    ? '✅ Operación guardada con Entry ya tocado'
                    : '✅ Señal guardada; el sistema esperará el Entry',
                'success'
            );
            const modal = bootstrap.Modal.getInstance(document.getElementById('saveSignalModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || 'no se pudo guardar'), 'danger');
        }
    } catch (e) {
        console.error('❌ Fetch error:', e);
        showToast('Error de red: ' + e.message, 'danger');
    }
};
// ============================================================================
// FASE 7G.1 — HISTORIAL CERRADO MINIMIZADO
// ============================================================================

function _closedSavedSignalsHistoryShell() {

    return `
        <details
            class="mt-2 border border-secondary rounded"
            ontoggle="window.loadClosedSavedSignalsHistory(this)"
        >
            <summary
                class="p-2 text-muted"
                style="cursor: pointer;"
            >
                📁 Historial cerrado
                <small>
                    (TP / SL / cierre manual / expiradas)
                </small>
            </summary>

            <div
                class="list-group list-group-flush"
                data-closed-history-list
            >
                <div
                    class="list-group-item bg-dark text-muted text-center"
                >
                    Abre esta sección para cargar
                    las operaciones cerradas.
                </div>
            </div>
        </details>
    `;
}


window.loadClosedSavedSignalsHistory =
async function(detailsEl) {

    if (
        !detailsEl
        || !detailsEl.open
    ) {
        return;
    }

    if (
        detailsEl.dataset.loaded
        === '1'
    ) {
        return;
    }

    const container =
        detailsEl.querySelector(
            '[data-closed-history-list]'
        );

    if (!container) {
        return;
    }

    detailsEl.dataset.loaded =
        '1';

    container.innerHTML = `
        <div
            class="list-group-item bg-dark text-info text-center"
        >
            <div
                class="spinner-border spinner-border-sm me-2"
            ></div>
            Cargando historial...
        </div>
    `;

    try {

        const response =
            await fetch(
                (
                    '/api/saved_signals'
                    + '?status='
                    + 'tp_hit,sl_hit,closed_manual,expired'
                    + '&limit=50'
                ),
                {
                    method:
                        'GET',

                    credentials:
                        'same-origin',

                    cache:
                        'no-store'
                }
            );

        const json =
            await response.json();

        if (
            !response.ok
            || !json.success
        ) {

            throw new Error(
                json.error
                || `HTTP ${response.status}`
            );
        }

        const closed =
            Array.isArray(
                json.signals
            )
                ? json.signals
                : [];

        if (
            closed.length === 0
        ) {

            container.innerHTML = `
                <div
                    class="list-group-item bg-dark text-muted text-center"
                >
                    No hay operaciones cerradas.
                </div>
            `;

            return;
        }

        let html = '';

        closed.forEach(
            s => {

                const emoji =
                    s.action === 'LONG'
                        ? '📈'
                        : '📉';

                const badgeClass =
                    s.action === 'LONG'
                        ? 'success'
                        : 'danger';

                const expiryMessage =
                    s.status === 'expired'
                        ? `
                            <div
                                class="
                                    small
                                    text-secondary
                                    mt-2
                                "
                            >
                                ⌛ Esta señal ya no es vigente:
                                no alcanzó su Entry dentro de
                                la ventana permitida.
                
                                <br>
                
                                <strong>
                                    Recomendación:
                                </strong>
                                no persigas el precio;
                                espera una nueva señal válida.
                            </div>
                        `
                        : '';                
                
                html += `
                    <a
                        href="#"
                        class="
                            list-group-item
                            list-group-item-action
                            bg-dark
                            text-white
                        "
                        onclick="
                            event.preventDefault();
                            window.openSavedSignalDetail(
                                '${s.id}'
                            );
                        "
                    >
                        <div
                            class="
                                d-flex
                                justify-content-between
                                align-items-center
                                flex-wrap
                            "
                        >
                            <div>
                                <span
                                    class="
                                        badge
                                        bg-${badgeClass}
                                        me-2
                                    "
                                >
                                    ${emoji}
                                    ${s.action}
                                </span>

                                <strong>
                                    ${
                                        (
                                            s.symbol
                                            || ''
                                        )
                                        .replace(
                                            '-',
                                            '/'
                                        )
                                    }
                                </strong>

                                <span
                                    class="
                                        badge
                                        bg-dark
                                        ms-1
                                    "
                                >
                                    ${s.timeframe}
                                </span>
                            </div>

                            <div
                                class="text-end"
                            >
                                ${
                                    _statusBadge(
                                        s.status,
                                        s.entry_touched
                                    )
                                }

                                ${
                                    _formatPnl(
                                        s
                                    )
                                }
                            </div>
                        </div>

                        ${expiryMessage}

                    </a>
                `;
            }
        );

        container.innerHTML =
            html;

    } catch (error) {

        detailsEl.dataset.loaded =
            '0';

        container.innerHTML = `
            <div
                class="list-group-item bg-dark text-danger"
            >
                Error cargando historial:
                ${error.message}
            </div>
        `;
    }
};


// ============ Refrescar lista y KPIs ============
window.updateSavedSignalsList = async function() {
    if (!window.IS_FUTURES_PAGE) return;

    if (
        typeof window.isSmartTradingAuthenticated === 'function'
        && !window.isSmartTradingAuthenticated()
    ) {
        console.log(
            '🔒 Futuros: señales guardadas requieren sesión.'
        );

        const card =
            document.getElementById('saved-signals-card');

        if (card) {
            card.style.display = 'none';
        }

        return;
    }

    const card = document.getElementById('saved-signals-card');
    const list = document.getElementById('saved-signals-list');
    if (!card || !list) return;
    
    // Mostrar la card en futuros
    card.style.display = 'block';
    
    try {
        const user =
            typeof window.getSmartTradingUser === 'function'
                ? window.getSmartTradingUser()
                : null;

        if (!user) {
            console.log(
                '🔒 Futuros: usuario no disponible.'
            );
            return;
        }

        // KPIs propios
        const kRes = await fetch(
            '/api/saved_signals/kpis',
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );
        const kJson = await kRes.json();
        if (kJson.success) {
            const k = kJson.data || {};
            const wrEl =
                document.getElementById(
                    'ss-kpi-winrate'
                );

            const pnlEl =
                document.getElementById(
                    'ss-kpi-pnl'
                );

            const netEl =
                document.getElementById(
                    'ss-kpi-net'
                );

            const economicsEl =
                document.getElementById(
                    'ss-kpi-econ-coverage'
                );

            const cntEl =
                document.getElementById(
                    'ss-kpi-count'
                );


            // ========================================================
            // KPI ANTIGUO — WIN RATE
            // ========================================================

            if (wrEl) {

                wrEl.textContent =
                    `WR: ${(k.win_rate || 0).toFixed(1)}%`;

                let cls =
                    'bg-secondary';

                if (k.total >= 5) {

                    cls =
                        k.win_rate >= 55
                            ? 'bg-success'
                            : (
                                k.win_rate >= 40
                                    ? 'bg-warning text-dark'
                                    : 'bg-danger'
                            );
                }

                wrEl.className =
                    'badge ' + cls;
            }


            // ========================================================
            // KPI BRUTO EXISTENTE
            // ========================================================

            if (pnlEl) {

                const grossPnl =
                    Number(
                        k.pnl_total_usdt
                        || 0
                    );

                const sign =
                    grossPnl >= 0
                        ? '+'
                        : '';

                pnlEl.textContent =
                    (
                        `PnL bruto: `
                        + `${sign}`
                        + `${grossPnl.toFixed(2)} USDT`
                    );

                let cls =
                    'bg-secondary';

                if (k.total >= 5) {

                    cls =
                        grossPnl > 0
                            ? 'bg-success'
                            : (
                                grossPnl < 0
                                    ? 'bg-danger'
                                    : 'bg-warning text-dark'
                            );
                }

                pnlEl.className =
                    'badge ' + cls;
            }


            // ========================================================
            // COMMIT 36O.3
            // ECONOMÍA NET ESTIMADA
            // ========================================================

            const economics =
                (
                    k.economics
                    && typeof k.economics === 'object'
                )
                    ? k.economics
                    : {};


            const netSamples =
                Number(
                    economics.net_samples
                    || 0
                );


            const closedTotal =
                Number(
                    economics.closed_total
                    ?? k.total
                    ?? 0
                );


            const coveragePct =
                Number(
                    economics.coverage_pct
                    || 0
                );


            if (netEl) {

                if (netSamples > 0) {

                    const netPnl =
                        Number(
                            economics
                                .estimated_net_pnl_total_usdt
                            || 0
                        );

                    const netSign =
                        netPnl >= 0
                            ? '+'
                            : '';

                    netEl.textContent =
                        (
                            `Neto est.: `
                            + `${netSign}`
                            + `${netPnl.toFixed(2)} USDT`
                        );


                    // Deliberadamente neutral:
                    // es una estimación económica,
                    // NO una señal de trading.

                    netEl.className =
                        'badge bg-secondary';


                    const netExp =
                        economics
                            .estimated_net_expectancy_r;


                    const netExpText =
                        (
                            netExp === null
                            || netExp === undefined
                        )
                            ? '--'
                            : Number(
                                netExp
                            ).toFixed(3);


                    netEl.title =
                        (
                            `36O — Neto ESTIMADO. `
                            + `Muestra: ${netSamples}. `
                            + `Expectancy neta est.: `
                            + `${netExpText}R. `
                            + `Fee/slippage estimados; `
                            + `funding rates públicos observados. `
                            + `No autoriza Commit 37.`
                        );

                } else {

                    netEl.textContent =
                        'Neto est.: --';

                    netEl.className =
                        'badge bg-secondary';

                    netEl.title =
                        (
                            'Todavía no existen operaciones '
                            + 'cerradas con economía 36O '
                            + 'completa.'
                        );
                }
            }


            // ========================================================
            // COMMIT 36O.3
            // COBERTURA ECONÓMICA
            // ========================================================

            if (economicsEl) {

                economicsEl.textContent =
                    (
                        `Costes: `
                        + `${netSamples}/`
                        + `${closedTotal} `
                        + `(${coveragePct.toFixed(0)}%)`
                    );


                // También se mantiene neutral.
                // Cobertura != rentabilidad.

                economicsEl.className =
                    'badge bg-dark';


                const grossExp =
                    economics
                        .gross_expectancy_r;


                const netExp =
                    economics
                        .estimated_net_expectancy_r;


                const grossExpText =
                    (
                        grossExp === null
                        || grossExp === undefined
                    )
                        ? '--'
                        : Number(
                            grossExp
                        ).toFixed(3);


                const netExpText =
                    (
                        netExp === null
                        || netExp === undefined
                    )
                        ? '--'
                        : Number(
                            netExp
                        ).toFixed(3);


                economicsEl.title =
                    (
                        `Cobertura económica 36O: `
                        + `${netSamples}/${closedTotal}. `
                        + `Expectancy bruta: `
                        + `${grossExpText}R. `
                        + `Expectancy neta estimada: `
                        + `${netExpText}R.`
                    );
            }


            // ========================================================
            // CONTADOR EXISTENTE
            // ========================================================

            if (cntEl) {

                cntEl.textContent =
                    (
                        `${k.total || 0} cerradas / `
                        + `${k.active || 0} activas`
                    );
            }
        }
        
        // Lista de todas (activas + cerradas recientes)
        // =============================================================
        // FASE 7G.1
        // =============================================================
        // La pantalla principal sólo necesita señales abiertas.
        //
        // Historial cerrado se carga únicamente cuando el
        // usuario despliega la sección correspondiente.
        // =============================================================

        const lRes = await fetch(
            (
                '/api/saved_signals'
                + '?status=active,entry_touched'
                + '&limit=100'
            ),
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );
        const lJson = await lRes.json();
        if (!lJson.success) {
            list.innerHTML = `<div class="list-group-item bg-dark text-warning">Error: ${lJson.error || 'desconocido'}</div>`;
            return;
        }
        
        const signals = lJson.signals || [];
        if (signals.length === 0) {

            list.innerHTML = `
                <div
                    class="
                        list-group-item
                        bg-dark
                        text-muted
                        text-center
                        py-3
                    "
                >
                    <i
                        class="
                            fas
                            fa-check-circle
                            me-1
                        "
                    ></i>

                    No tienes señales abiertas
                    ni esperando Entry.
                </div>

                ${_closedSavedSignalsHistoryShell()}
            `;

            return;
        }
        // =============================================================
        // FUTURES POSITION GUARDIAN
        // =============================================================
        // Una sola petición para todas las posiciones abiertas.
        // El backend agrupa por símbolo + timeframe.
        // =============================================================
        
        let guardianBySignal = {};
        
        try {
            const gRes = await fetch(
                '/api/futures/position-guardian?user='
                + encodeURIComponent(user)
                + '&_ts='
                + Date.now(),
                {
                    cache: 'no-store'
                }
            );
        
            const gJson = await gRes.json();
        
            if (gJson.success) {
        
                (gJson.positions || []).forEach(
                    p => {
                        guardianBySignal[
                            p.signal_id
                        ] = p.guardian || {};
                    }
                );
            }
        
        } catch (guardianError) {
        
            console.warn(
                '⚠️ Futures Guardian no disponible:',
                guardianError
            );
        }        
        let html = '';
        signals.forEach(s => {
        
            const emoji =
                s.action === 'LONG'
                    ? '📈'
                    : '📉';
            const bgColor =
                s.action === 'LONG'
                    ? 'success'
                    : 'danger';        
            const statusBadge =
                _statusBadge(
                    s.status,
                    s.entry_touched
                );
        
            const pnlDisplay =
                _formatPnl(s);
        
            const guardian =
                guardianBySignal[
                    s.id
                ] || {};
        
            let guardianHtml = '';
            // =========================================================
            // COMMIT 29 — GESTIÓN DINÁMICA DEL FUTURES GUARDIAN
            // =========================================================
            //
            // Retrocompatible:
            //
            // - Si el backend nuevo entrega management_action,
            //   podemos mostrar PROTECT / EXTEND.
            //
            // - Si no existe management_action, el código antiguo
            //   continúa funcionando exactamente igual.
            //
            // IMPORTANTE:
            // Esto sólo muestra recomendaciones.
            // No modifica la posición, SL ni TP.
            // =========================================================

            const managementAction = String(
                guardian.management_action || ''
            ).toUpperCase();

            const guardianNumberOrNull = value => {

                if (
                    value === null
                    || value === undefined
                    || value === ''
                ) {
                    return null;
                }

                const number = Number(
                    value
                );

                return Number.isFinite(
                    number
                )
                    ? number
                    : null;
            };

            const originalGuardianSl =
                guardianNumberOrNull(
                    guardian.original_stop_loss
                )
                ?? guardianNumberOrNull(
                    s.stop_loss
                );

            const suggestedGuardianSl =
                guardianNumberOrNull(
                    guardian.suggested_stop_loss
                );

            const originalGuardianTp =
                guardianNumberOrNull(
                    guardian.original_take_profit
                )
                ?? guardianNumberOrNull(
                    s.take_profit
                );

            const suggestedGuardianTp =
                guardianNumberOrNull(
                    guardian.suggested_take_profit
                );

            const guardianProgressR =
                guardianNumberOrNull(
                    guardian.progress_r
                );

            const guardianTpProgress =
                guardianNumberOrNull(
                    guardian.tp_progress_ratio
                );

            const managementReason =
                guardian.management_reason
                || guardian.reason
                || '';

            const guardianProtects = (
                managementAction === 'PROTECT'
                || managementAction
                    === 'PROTECT_AND_EXTEND'
            );

            const guardianExtends = (
                managementAction === 'EXTEND'
                || managementAction
                    === 'PROTECT_AND_EXTEND'
            );        
            if (
                guardian.action
            ) {
                // =====================================================
                // PROTECT / EXTEND
                // =====================================================

                if (
                    guardianProtects
                    || guardianExtends
                ) {

                    let managementLabel =
                        'GESTIONAR';

                    let managementBadge =
                        'primary';

                    let managementIcon =
                        '🛡️';

                    if (
                        guardianProtects
                        && guardianExtends
                    ) {

                        managementLabel =
                            'PROTEGER + EXTENDER';

                        managementBadge =
                            'info text-dark';

                        managementIcon =
                            '🛡️🎯';

                    } else if (
                        guardianProtects
                    ) {

                        managementLabel =
                            'PROTEGER';

                        managementBadge =
                            'primary';

                        managementIcon =
                            '🛡️';

                    } else if (
                        guardianExtends
                    ) {

                        managementLabel =
                            'EXTENDER OBJETIVO';

                        managementBadge =
                            'success';

                        managementIcon =
                            '🎯';
                    }

                    // =============================================
                    // BLOQUE DE PROTECCIÓN DEL SL
                    // =============================================

                    let protectHtml = '';

                    if (
                        guardianProtects
                    ) {

                        protectHtml = `
                            <div
                                class="
                                    mt-2
                                    p-2
                                    rounded
                                    bg-dark
                                "
                                style="
                                    border-left:
                                    3px solid #3A8BFF;
                                "
                            >
                                <div
                                    class="
                                        small
                                        text-info
                                        mb-1
                                    "
                                >
                                    <strong>
                                        🛡️ Protección del riesgo
                                    </strong>
                                </div>

                                ${
                                    originalGuardianSl
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-muted
                                                    "
                                                >
                                                    SL original
                                                </span>

                                                <strong>
                                                    ${
                                                        futFormatPrice(
                                                            originalGuardianSl,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : ''
                                }

                                ${
                                    suggestedGuardianSl
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                    mt-1
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-info
                                                    "
                                                >
                                                    SL sugerido
                                                </span>

                                                <strong
                                                    class="
                                                        text-info
                                                    "
                                                >
                                                    ${
                                                        futFormatPrice(
                                                            suggestedGuardianSl,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : `
                                            <div
                                                class="
                                                    small
                                                    text-muted
                                                "
                                            >
                                                Nuevo SL todavía
                                                no disponible.
                                            </div>
                                        `
                                }

                                <div
                                    class="
                                        small
                                        text-muted
                                        mt-1
                                    "
                                >
                                    El Guardian sólo puede
                                    reducir el riesgo original;
                                    nunca ampliarlo.
                                </div>
                            </div>
                        `;
                    }

                    // =============================================
                    // BLOQUE DE EXTENSIÓN DEL TP
                    // =============================================

                    let extendHtml = '';

                    if (
                        guardianExtends
                    ) {

                        extendHtml = `
                            <div
                                class="
                                    mt-2
                                    p-2
                                    rounded
                                    bg-dark
                                "
                                style="
                                    border-left:
                                    3px solid #00C076;
                                "
                            >
                                <div
                                    class="
                                        small
                                        text-success
                                        mb-1
                                    "
                                >
                                    <strong>
                                        🎯 Extensión estructural
                                    </strong>
                                </div>

                                ${
                                    originalGuardianTp
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-muted
                                                    "
                                                >
                                                    TP original
                                                </span>

                                                <strong>
                                                    ${
                                                        futFormatPrice(
                                                            originalGuardianTp,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : ''
                                }

                                ${
                                    suggestedGuardianTp
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                    mt-1
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-success
                                                    "
                                                >
                                                    TP sugerido
                                                </span>

                                                <strong
                                                    class="
                                                        text-success
                                                    "
                                                >
                                                    ${
                                                        futFormatPrice(
                                                            suggestedGuardianTp,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : `
                                            <div
                                                class="
                                                    small
                                                    text-muted
                                                "
                                            >
                                                Nuevo TP todavía
                                                no disponible.
                                            </div>
                                        `
                                }

                                <div
                                    class="
                                        small
                                        text-muted
                                        mt-1
                                    "
                                >
                                    El objetivo sólo se extiende
                                    cuando existe una referencia
                                    estructural posterior.
                                </div>
                            </div>
                        `;
                    }

                    // =============================================
                    // PROGRESO DE LA POSICIÓN
                    // =============================================

                    let progressHtml = '';

                    if (
                        guardianProgressR !== null
                        || guardianTpProgress !== null
                    ) {

                        progressHtml = `
                            <div
                                class="
                                    d-flex
                                    flex-wrap
                                    gap-2
                                    mt-2
                                "
                            >

                                ${
                                    guardianProgressR
                                    !== null
                                        ? `
                                            <span
                                                class="
                                                    badge
                                                    bg-dark
                                                    border
                                                    border-secondary
                                                "
                                            >
                                                Progreso:
                                                ${
                                                    guardianProgressR
                                                    >= 0
                                                        ? '+'
                                                        : ''
                                                }${
                                                    guardianProgressR
                                                        .toFixed(
                                                            2
                                                        )
                                                }R
                                            </span>
                                        `
                                        : ''
                                }

                                ${
                                    guardianTpProgress
                                    !== null
                                        ? `
                                            <span
                                                class="
                                                    badge
                                                    bg-dark
                                                    border
                                                    border-secondary
                                                "
                                            >
                                                TP recorrido:
                                                ${
                                                    Math.max(
                                                        0,
                                                        guardianTpProgress
                                                        * 100
                                                    ).toFixed(
                                                        0
                                                    )
                                                }%
                                            </span>
                                        `
                                        : ''
                                }

                            </div>
                        `;
                    }

                    guardianHtml = `
                        <div
                            class="
                                mt-2
                                p-2
                                border
                                border-info
                                rounded
                            "
                        >

                            <div
                                class="
                                    d-flex
                                    flex-wrap
                                    justify-content-between
                                    align-items-center
                                    gap-1
                                "
                            >

                                <span
                                    class="
                                        badge
                                        bg-${managementBadge}
                                    "
                                >
                                    ${managementIcon}
                                    Guardian:
                                    ${managementLabel}
                                </span>

                                <span
                                    class="
                                        badge
                                        bg-dark
                                    "
                                >
                                    Deterioro:
                                    ${
                                        Number(
                                            guardian
                                                .deterioration_score
                                            || 0
                                        ).toFixed(
                                            0
                                        )
                                    }/100
                                </span>

                            </div>

                            ${progressHtml}

                            ${protectHtml}

                            ${extendHtml}

                            ${
                                managementReason
                                    ? `
                                        <div
                                            class="
                                                small
                                                text-light
                                                mt-2
                                            "
                                        >
                                            ${
                                                futEscapeHtml(
                                                    managementReason
                                                )
                                            }
                                        </div>
                                    `
                                    : ''
                            }

                            <div
                                class="
                                    small
                                    text-warning
                                    mt-2
                                "
                            >
                                ⚠️ Recomendación del Guardian.
                                No modifica automáticamente
                                la orden en el exchange.
                            </div>

                        </div>
                    `;

                } else if (
                    guardian.action
                    === 'WAIT_ENTRY'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2">
                            <span class="badge bg-info">
                                🛡️ Guardian: ESPERANDO ENTRY
                            </span>
                
                            <div class="small text-info mt-1">
                                ${guardian.reason || ''}
                            </div>
                        </div>
                    `;
                
                } else if (
                    guardian.action
                    === 'EXIT'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2 p-2 border border-danger rounded">
                
                            <div class="mb-2">
                                <span class="badge bg-danger">
                                    🛡️ Guardian: SALIR
                                </span>
                
                                <span class="badge bg-dark ms-1">
                                    Deterioro:
                                    ${Number(
                                        guardian.deterioration_score || 0
                                    ).toFixed(0)}/100
                                </span>
                            </div>
                
                            <div class="small text-light">
                
                                <div class="mb-1">
                                    ⏱️ <strong>Tiempo:</strong>
                                    ${Number(
                                        guardian.elapsed_minutes || 0
                                    ).toFixed(0)} min
                                </div>
                
                                <div class="mb-1">
                                    📈 <strong>MFE:</strong>
                                    +${Number(
                                        guardian.mfe_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📉 <strong>MAE:</strong>
                                    -${Number(
                                        guardian.mae_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Avance favorable:</strong>
                                    ${Number(
                                        guardian.favorable_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    ⚠️ <strong>Movimiento adverso:</strong>
                                    ${Number(
                                        guardian.adverse_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Distancia restante a TP:</strong>
                                    ${Number(
                                        guardian.remaining_to_tp_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🛡️ <strong>Distancia al SL:</strong>
                                    ${Number(
                                        guardian.sl_distance_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Objetivo total:</strong>
                                    ${Number(
                                        guardian.tp_distance_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    ⚡ <strong>Leverage:</strong>
                                    ${Number(
                                        guardian.leverage || 0
                                    ).toFixed(0)}x
                                </div>
                
                                <div class="mt-2 text-danger">
                                    ${guardian.reason || ''}
                                </div>
                
                            </div>
                        </div>
                    `;
                
                } else if (
                    guardian.action
                    === 'REDUCE'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2">
                            <span class="badge bg-warning text-dark">
                                🛡️ Guardian: REDUCIR / PROTEGER
                            </span>
                            <div class="small text-warning mt-1">
                                ${guardian.reason || ''}
                            </div>
                        </div>
                    `;
                
                } else {
                
                    guardianHtml = `
                        <div class="mt-2 p-2 border border-success rounded">
                
                            <div class="mb-2">
                                <span class="badge bg-success">
                                    🛡️ Guardian: MANTENER
                                </span>
                            </div>
                
                            <div class="small text-light">
                
                                <div class="mb-1">
                                    ⏱️ <strong>Tiempo:</strong>
                                    ${Number(
                                        guardian.elapsed_minutes || 0
                                    ).toFixed(0)} min
                                </div>
                
                                <div class="mb-1">
                                    📈 <strong>MFE:</strong>
                                    +${Number(
                                        guardian.mfe_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📉 <strong>MAE:</strong>
                                    -${Number(
                                        guardian.mae_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>TP restante:</strong>
                                    ${Number(
                                        guardian.remaining_to_tp_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📊 <strong>Deterioro:</strong>
                                    ${Number(
                                        guardian.deterioration_score || 0
                                    ).toFixed(0)}/100
                                </div>
                
                            </div>
                        </div>
                    `;
                }
            }
            
            html += `
                <a href="#" class="list-group-item list-group-item-action bg-dark text-white"
                   onclick="event.preventDefault(); window.openSavedSignalDetail('${s.id}')">
                    <div class="d-flex justify-content-between align-items-center flex-wrap">
                        <div>
                            <span class="badge bg-${bgColor} me-2">${emoji} ${s.action}</span>
                            <strong>${(s.symbol || '').replace('-', '/')}</strong>
                            <span class="badge bg-dark ms-1">${s.timeframe}</span>
                            <span class="badge bg-secondary ms-1">${s.leverage}x</span>
                            <span class="text-muted ms-2 small">$${s.investment_usdt} USDT</span>
                        </div>
                        <div class="text-end">
                            ${statusBadge}
                            ${pnlDisplay}
                        </div>
                    </div>
                    ${guardianHtml}
                </a>
            `;
        });
        list.innerHTML =
            html
            + _closedSavedSignalsHistoryShell();
    } catch (e) {
        list.innerHTML = `<div class="list-group-item bg-dark text-danger">Error: ${e.message}</div>`;
    }
};

function _statusBadge(status, entryTouched) {
    if (status === 'active') return '<span class="badge bg-info">⏳ Esperando entry</span>';
    if (status === 'entry_touched') return '<span class="badge bg-primary">🎯 En operación</span>';
    if (status === 'tp_hit') return '<span class="badge bg-success">✅ TP</span>';
    if (status === 'sl_hit') return '<span class="badge bg-danger">❌ SL</span>';
    if (status === 'expired') {
        return '<span class="badge bg-secondary">⌛ Expirada sin Entry</span>';
    }
    if (status === 'closed_manual') {
        return entryTouched ? '<span class="badge bg-warning text-dark">🔒 Cerrada</span>'
                             : '<span class="badge bg-secondary">🔒 Cerrada (sin entry)</span>';
    }
    return `<span class="badge bg-secondary">${status}</span>`;
}

function _formatPnl(s) {
    if (s.status === 'active' || s.status === 'entry_touched') return '';
    if (!s.entry_touched) {
        return '<div class="small text-muted">Sin operación</div>';
    }
    const pct = parseFloat(s.pnl_pct || 0);
    const usdt = parseFloat(s.pnl_usdt || 0);
    const cls = pct >= 0 ? 'text-success' : 'text-danger';
    const sign = pct >= 0 ? '+' : '';
    return `<div class="small ${cls}"><strong>${sign}${usdt.toFixed(2)} USDT</strong> (${sign}${pct.toFixed(2)}%)</div>`;
}

// ============ Modal DETALLE con gráfico Plotly + zonas TP/SL ============
window.openSavedSignalDetail = async function(signalId) {
    const modal = new bootstrap.Modal(document.getElementById('savedSignalDetailModal'));
    modal.show();
    
    const body = document.getElementById('saved-signal-detail-body');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div><p class="mt-3">Cargando gráfico...</p></div>';
    
    try {
        const res = await fetch(`/api/saved_signals/${signalId}/chart_data`);
        const json = await res.json();
        if (!json.success) {
            body.innerHTML = `<div class="alert alert-warning">${json.error || 'Error cargando datos'}</div>`;
            return;
        }
        
        const sig = json.signal;
        window._currentSavedSignal = sig;
        const c = json.candles;
        const currentPrice = json.current_price;
        
        // Habilitar/deshabilitar botones según estado
        const isOpen = (sig.status === 'active' || sig.status === 'entry_touched');
        document.getElementById('btn-ss-edit').style.display = isOpen ? 'inline-block' : 'none';
        document.getElementById('btn-ss-close-manual').style.display = isOpen ? 'inline-block' : 'none';
        
        // Renderizar body con panel de info + div para el gráfico
        const emoji = sig.action === 'LONG' ? '📈' : '📉';
        const badgeClass = sig.action === 'LONG' ? 'success' : 'danger';
        const statusBadge = _statusBadge(sig.status, sig.entry_touched);
        const pnlDisplay = _formatPnl(sig);
        
        body.innerHTML = `
            <div class="mb-3 d-flex flex-wrap align-items-center gap-2">
                <span class="badge bg-${badgeClass} p-2">${emoji} ${sig.action}</span>
                <strong>${sig.symbol.replace('-', '/')}</strong>
                <span class="badge bg-dark">${sig.timeframe}</span>
                <span class="badge bg-secondary">${sig.leverage}x</span>
                <span class="text-muted">$${sig.investment_usdt} USDT</span>
                ${statusBadge}
                <div class="ms-auto">${pnlDisplay}</div>
            </div>
            <div class="row g-2 mb-3 small">
                <div class="col-md-3"><span class="text-muted">Entry:</span> <strong class="text-primary">${sig.entry}</strong></div>
                <div class="col-md-3"><span class="text-muted">SL:</span> <strong class="text-danger">${sig.stop_loss}</strong></div>
                <div class="col-md-3"><span class="text-muted">TP:</span> <strong class="text-success">${sig.take_profit}</strong></div>
                <div class="col-md-3"><span class="text-muted">Precio actual:</span> <strong>${currentPrice}</strong></div>
            </div>
            <div class="row g-2 mb-3 small">
                <div class="col-md-6"><span class="text-muted">🕒 Ingreso:</span> <strong>${_fmtLocalDate(sig.entry_at || sig.created_at)}</strong></div>
                ${sig.entry_touched_at ? `<div class="col-md-6"><span class="text-muted">🎯 Entry tocado:</span> <strong>${_fmtLocalDate(sig.entry_touched_at)}</strong></div>` : ''}
            </div>
            <div id="saved-signal-chart" style="height: 500px;"></div>
            ${sig.notes ? `<div class="mt-3 p-2 bg-black rounded small"><strong>Notas:</strong> ${sig.notes}</div>` : ''}
        `;
        
        // Renderizar el gráfico Plotly
        if (
            c
            && c.time
            && c.time.length > 0
        ) {
        
            _renderSavedSignalChart(
                c,
                sig,
                currentPrice
            );
        
        } else {
        
            document.getElementById(
                'saved-signal-chart'
            ).innerHTML =
                '<div class="alert alert-warning">No hay datos de velas para este par/timeframe</div>';
        }
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
};

function _renderSavedSignalChart(candles, sig, currentPrice) {
    // GUARDAS DEFENSIVAS
    if (!candles || !candles.time || !Array.isArray(candles.time) || candles.time.length === 0) {
        console.warn('⚠️ Datos de velas inválidos:', candles);
        const chartDiv = document.getElementById('saved-signal-chart');
        if (chartDiv) chartDiv.innerHTML = '<div class="alert alert-warning">No hay datos de velas disponibles</div>';
        return;
    }
    if (!candles.open || !candles.high || !candles.low || !candles.close) {
        console.warn('⚠️ Faltan datos OHLC:', candles);
        return;
    }
    if (typeof Plotly === 'undefined' || !Plotly.newPlot) {
        console.warn('⚠️ Plotly no disponible');
        return;
    }

    const times = candles.time;
    const entry = parseFloat(sig.entry);
    const sl = parseFloat(sig.stop_loss);
    const tp = parseFloat(sig.take_profit);
    const isLong = sig.action === 'LONG';

   
    // Rango X: primer a último candle + un poco de margen a la derecha
    const xStart = times[0];
    const xEnd = times[times.length - 1];
    
    const traces = [{
        type: 'candlestick',
        x: times,
        open: candles.open,
        high: candles.high,
        low: candles.low,
        close: candles.close,
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1}, fillcolor: '#FF5B5B'},
        showlegend: false,
    }];
    
    // Zonas: verde (favorable) y roja (desfavorable) tipo TradingView
    // LONG: entry→TP arriba (verde), entry→SL abajo (rojo)
    // SHORT: entry→TP abajo (verde), entry→SL arriba (rojo)
    const shapes = [
        // Zona de ganancia (verde)
        {
            type: 'rect', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: isLong ? entry : tp,
            y1: isLong ? tp : entry,
            fillcolor: 'rgba(0, 192, 118, 0.15)',
            line: {color: 'rgba(0, 192, 118, 0.5)', width: 1},
            layer: 'below',
        },
        // Zona de pérdida (rojo)
        {
            type: 'rect', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: isLong ? sl : entry,
            y1: isLong ? entry : sl,
            fillcolor: 'rgba(255, 91, 91, 0.15)',
            line: {color: 'rgba(255, 91, 91, 0.5)', width: 1},
            layer: 'below',
        },
        // Línea del entry
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: entry, y1: entry,
            line: {color: '#3A8BFF', width: 2, dash: 'solid'},
        },
        // Línea SL punteada
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: sl, y1: sl,
            line: {color: '#FF5B5B', width: 1.5, dash: 'dash'},
        },
        // Línea TP punteada
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: tp, y1: tp,
            line: {color: '#00C076', width: 1.5, dash: 'dash'},
        },
    ];
    
    const annotations = [
        {x: xEnd, y: entry, xref: 'x', yref: 'y', text: `Entry: ${entry}`,
         showarrow: false, xanchor: 'left', font: {color: '#3A8BFF', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#3A8BFF', borderwidth: 1, borderpad: 3},
        {x: xEnd, y: sl, xref: 'x', yref: 'y', text: `SL: ${sl}`,
         showarrow: false, xanchor: 'left', font: {color: '#FF5B5B', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#FF5B5B', borderwidth: 1, borderpad: 3},
        {x: xEnd, y: tp, xref: 'x', yref: 'y', text: `TP: ${tp}`,
         showarrow: false, xanchor: 'left', font: {color: '#00C076', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#00C076', borderwidth: 1, borderpad: 3},
    ];
    
    const layout = {
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        font: {color: 'white', size: 11},
        xaxis: {rangeslider: {visible: false}, gridcolor: 'rgba(255,255,255,0.08)'},
        yaxis: {gridcolor: 'rgba(255,255,255,0.08)', side: 'right'},
        margin: {l: 40, r: 80, t: 20, b: 40},
        shapes,
        annotations,
        hovermode: 'x unified',
    };
    
    Plotly.newPlot('saved-signal-chart', traces, layout,
                   {responsive: true, displayModeBar: false});
}

// ============ Editar señal guardada ============
window.openEditSavedSignal = function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    document.getElementById('edit-ss-investment').value = sig.investment_usdt;
    document.getElementById('edit-ss-leverage').value = sig.leverage;
    document.getElementById('edit-ss-entry').value = sig.entry;
    document.getElementById('edit-ss-sl').value = sig.stop_loss;
    document.getElementById('edit-ss-tp').value = sig.take_profit;
    document.getElementById('edit-ss-notes').value = sig.notes || '';
    // v22.9.4: entry_at editable — convertir ISO UTC de la BD a datetime-local
    const entryAtEl = document.getElementById('edit-ss-entry-at');
    if (entryAtEl) {
        if (sig.entry_at) {
            try {
                const d = new Date(sig.entry_at);
                const pad = n => String(n).padStart(2, '0');
                entryAtEl.value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
            } catch (e) {
                entryAtEl.value = _nowLocalDatetimeInput();
            }
        } else {
            entryAtEl.value = _nowLocalDatetimeInput();
        }
    }
    
    // Cerrar el detalle para evitar solapamiento
    const detailModal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
    if (detailModal) detailModal.hide();
    
    const modal = new bootstrap.Modal(document.getElementById('editSavedSignalModal'));
    modal.show();
};

window.confirmEditSavedSignal = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const entryAtLocal = document.getElementById('edit-ss-entry-at').value;
    const entryAtISO = _localDatetimeToISO(entryAtLocal);
    
    const payload = {
        investment_usdt: parseFloat(document.getElementById('edit-ss-investment').value),
        leverage: parseInt(document.getElementById('edit-ss-leverage').value),
        entry: parseFloat(document.getElementById('edit-ss-entry').value),
        stop_loss: parseFloat(document.getElementById('edit-ss-sl').value),
        take_profit: parseFloat(document.getElementById('edit-ss-tp').value),
        notes: document.getElementById('edit-ss-notes').value || '',
        entry_at: entryAtISO,  // v22.9.4
    };
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });
        const json = await res.json();
        if (json.success) {
            showToast('✅ Señal modificada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('editSavedSignalModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Cerrar señal manualmente ============
window.closeSavedSignalManual = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const confirmed = confirm(
        sig.entry_touched
            ? '¿Cerrar la operación manualmente? Se calcula PnL con el precio actual.'
            : '⚠️ El precio aún no ha tocado el entry. Al cerrar NO cuenta para winrate ni PnL. ¿Continuar?'
    );
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}/close`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({}),  // el backend obtiene precio actual
        });
        const json = await res.json();
        if (json.success) {
            showToast('✅ Señal cerrada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Eliminar señal guardada ============
window.deleteSavedSignal = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const confirmed = confirm('¿Eliminar esta señal permanentemente? Esta acción no se puede deshacer.');
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}`, {method: 'DELETE'});
        const json = await res.json();
        if (json.success) {
            showToast('🗑️ Señal eliminada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Auto-refresh de la lista cada 5 min ============
if (window.IS_FUTURES_PAGE) {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => window.updateSavedSignalsList(), 1500);
        setInterval(() => window.updateSavedSignalsList(), 5 * 60 * 1000);
    });
}
