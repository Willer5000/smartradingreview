// futures.js - Lógica del modal de FUTUROS (Fase 6)
// Consume los endpoints /api/futures/* y /api/review/* creados en Fase 5

console.log('🚀 futures.js cargado');


// ============================================================================
// UTILIDADES GENÉRICAS
// ============================================================================

function futShowToast(msg, type = 'info') {
    // Usar el sistema existente de toasts si está disponible
    if (typeof window.showToast === 'function') {
        window.showToast(msg, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${msg}`);
    }
}

function futFormatPrice(price, symbol) {
    if (price === null || price === undefined) return '--';
    const decimals = (symbol && (symbol.includes('XRP') || symbol.includes('ADA'))) ? 4 : 2;
    return '$' + Number(price).toFixed(decimals);
}

function futFormatPct(val) {
    if (val === null || val === undefined) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(2)}%`;
}


// ============================================================================
// FUNCIÓN PRINCIPAL: Analizar un par de futuros
// ============================================================================

window.analyzeFutures = async function() {
    const symbol = document.getElementById('fut-symbol-select').value;
    const timeframe = document.getElementById('fut-timeframe-select').value;
    
    console.log(`📡 Analizando futuros: ${symbol} ${timeframe}`);
    futShowToast(`Analizando ${symbol} ${timeframe}...`, 'info');
    
    // Mostrar loader
    const recBody = document.getElementById('fut-recommendation-body');
    recBody.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-warning" role="status"></div>
            <p class="mt-3 mb-0">Analizando ${symbol} en ${timeframe}...</p>
        </div>
    `;
    
    try {
        const res = await fetch('/api/futures/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ symbol, timeframe })
        });
        
        const json = await res.json();
        
        if (!json.success || !json.data) {
            recBody.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Error:</strong> ${json.error || 'Sin datos'}
                </div>
            `;
            futShowToast('Error en el análisis', 'danger');
            return;
        }
        
        renderFuturesRecommendation(json.data);
        renderFuturesLevels(json.data);
        renderFuturesMessage(json.data);
        
        // Consultar recomendaciones del ReviewTrader en paralelo
        loadReviewRecommendations(symbol, timeframe, json.data.decision?.action);
        
        futShowToast('Análisis completado ✅', 'success');
        
    } catch (err) {
        console.error('Error:', err);
        recBody.innerHTML = `<div class="alert alert-danger">Error de conexión: ${err.message}</div>`;
        futShowToast('Error de conexión', 'danger');
    }
};


// ============================================================================
// RENDER: Recomendación grande
// ============================================================================

function renderFuturesRecommendation(data) {
    const body = document.getElementById('fut-recommendation-body');
    const decision = data.decision || {};
    const action = decision.action || 'NO_OPERAR';
    const confidence = decision.confidence || 0;
    const levels = data.levels || {};
    
    let badgeClass = 'bg-secondary';
    let icon = '⏸️';
    let actionText = action;
    
    if (action === 'LONG') { badgeClass = 'bg-success'; icon = '📈'; }
    else if (action === 'SHORT') { badgeClass = 'bg-danger'; icon = '📉'; }
    else if (action === 'NO_OPERAR' || action === 'ESPERAR' || action === 'CAUTION') { icon = '⏸️'; }
    
    // Detección de rechazo
    const rejectedReason = levels.rejected_reason;
    let rejectedAlert = '';
    if (rejectedReason) {
        rejectedAlert = `
            <div class="alert alert-warning mt-3 mb-0">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Señal rechazada:</strong> ${rejectedReason}
            </div>
        `;
    }
    
    body.innerHTML = `
        <div class="row align-items-center">
            <div class="col-md-6">
                <div class="d-flex align-items-center">
                    <span class="badge ${badgeClass} me-3" style="font-size: 1.5rem; padding: 0.75rem 1.5rem;">
                        ${icon} ${actionText.replace('_', ' ')}
                    </span>
                    <div>
                        <div class="text-muted small">Símbolo</div>
                        <div class="fw-bold h5 mb-0">${data.symbol?.replace('-', '/') || '--'}</div>
                    </div>
                </div>
            </div>
            <div class="col-md-6 text-md-end">
                <div class="text-muted small">Confianza del Consenso</div>
                <div class="fw-bold h3 mb-0" style="color: ${confidence >= 75 ? '#00C076' : confidence >= 50 ? '#FFD700' : '#FF5B5B'};">
                    ${confidence.toFixed(0)}%
                </div>
                <div class="small text-muted">Timeframe: ${data.timeframe || '--'}</div>
            </div>
        </div>
        ${rejectedAlert}
    `;
}


// ============================================================================
// RENDER: Niveles (Entry / SL / TP / Apalancamiento / ROI)
// ============================================================================

function renderFuturesLevels(data) {
    const body = document.getElementById('fut-levels-body');
    const levels = data.levels || {};
    const symbol = data.symbol;
    const decision = data.decision?.action || 'NO_OPERAR';
    
    // Si es NO_OPERAR o rechazada, mostrar mensaje
    if (['NO_OPERAR', 'ESPERAR', 'CAUTION'].includes(decision) || levels.rejected_reason) {
        body.innerHTML = `
            <div class="text-center text-muted py-3">
                <i class="fas fa-info-circle me-1"></i>
                No hay operación recomendada en este momento.
            </div>
        `;
        return;
    }
    
    const roiTP = levels.roi_tp || 0;
    const roiSL = levels.roi_sl || 0;
    const moveTP = levels.move_tp_pct || 0;
    const moveSL = levels.move_sl_pct || 0;
    
    body.innerHTML = `
        <div class="row g-2">
            <div class="col-md-3">
                <div class="border-start border-3 border-primary ps-2">
                    <small class="text-muted d-block">ENTRADA</small>
                    <strong class="h6 mb-0">${futFormatPrice(levels.entry, symbol)}</strong>
                </div>
            </div>
            <div class="col-md-3">
                <div class="border-start border-3 border-danger ps-2">
                    <small class="text-muted d-block">STOP LOSS</small>
                    <strong class="h6 mb-0">${futFormatPrice(levels.stop_loss, symbol)}</strong>
                    <div class="small text-danger">${futFormatPct(-moveSL)} (${futFormatPct(roiSL)} ROI)</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="border-start border-3 border-success ps-2">
                    <small class="text-muted d-block">TAKE PROFIT</small>
                    <strong class="h6 mb-0">${futFormatPrice(levels.take_profit, symbol)}</strong>
                    <div class="small text-success">${futFormatPct(moveTP)} (${futFormatPct(roiTP)} ROI)</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="border-start border-3 border-warning ps-2">
                    <small class="text-muted d-block">APALANCAMIENTO</small>
                    <strong class="h5 mb-0 text-warning">${levels.leverage || 1}x</strong>
                    <div class="small">R/R 1:${(levels.risk_reward || 0).toFixed(1)}</div>
                </div>
            </div>
        </div>
        <div class="row mt-3 g-2">
            <div class="col-md-6">
                <small class="text-muted">Origen TP:</small>
                <div class="small">${levels.tp_source || '--'} <span class="badge bg-dark ms-1">${((levels.tp_probability || 0) * 100).toFixed(0)}% prob</span></div>
            </div>
            <div class="col-md-6">
                <small class="text-muted">Origen SL:</small>
                <div class="small">${levels.sl_source || '--'} <span class="badge bg-dark ms-1">${((levels.sl_reliability || 0) * 100).toFixed(0)}% confiab</span></div>
            </div>
        </div>
        <div class="row mt-2">
            <div class="col-12">
                <small class="text-muted">
                    <i class="fas fa-info-circle me-1"></i>
                    Con 10 USDT y ${levels.leverage || 1}x apalancamiento, ganancia potencial si TP: <strong class="text-success">${(10 * (roiTP / 100)).toFixed(2)} USDT</strong>
                    | Pérdida si SL: <strong class="text-danger">${(10 * (roiSL / 100)).toFixed(2)} USDT</strong>
                </small>
            </div>
        </div>
    `;
}


// ============================================================================
// RENDER: Justificación del sistema
// ============================================================================

function renderFuturesMessage(data) {
    const body = document.getElementById('fut-message-body');
    const message = data.message || 'Sin justificación disponible';
    
    // Reemplazar saltos de línea por <br>
    const html = message.replace(/\n/g, '<br>');
    
    body.innerHTML = `<div class="small" style="line-height: 1.6;">${html}</div>`;
}


// ============================================================================
// RECOMENDACIONES DEL REVIEWTRADER
// ============================================================================

async function loadReviewRecommendations(symbol, timeframe, action) {
    const body = document.getElementById('fut-review-body');
    
    if (!action || ['NO_OPERAR', 'ESPERAR', 'CAUTION'].includes(action)) {
        body.innerHTML = `
            <div class="text-muted small text-center py-3">
                Sin acción de trading activa.<br>
                (Solo se muestran recomendaciones para LONG/SHORT)
            </div>
        `;
        return;
    }
    
    body.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-info"></div>
            <p class="small mt-2 mb-0">Cargando recomendaciones...</p>
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
                    ${rec.message || 'Aún no hay historial suficiente para esta combinación.'}
                </div>
            `;
            return;
        }
        
        // Renderizar recomendaciones
        const winners = rec.winning_strategies || [];
        const losers = rec.losing_strategies || [];
        
        let winnersHTML = '';
        if (winners.length > 0) {
            winnersHTML = `
                <div class="mb-3">
                    <h6 class="text-success mb-2"><i class="fas fa-trophy me-1"></i>Top Ganadoras</h6>
                    ${winners.slice(0, 5).map((w, idx) => `
                        <div class="d-flex justify-content-between mb-1 small">
                            <span>${idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '•'} ${w.strategy}</span>
                            <span class="badge bg-success">${w.win_rate}%</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        let losersHTML = '';
        if (losers.length > 0) {
            losersHTML = `
                <div class="mb-2">
                    <h6 class="text-danger mb-2"><i class="fas fa-times-circle me-1"></i>Evitar</h6>
                    ${losers.slice(0, 3).map(l => `
                        <div class="d-flex justify-content-between mb-1 small">
                            <span>⚠️ ${l.strategy}</span>
                            <span class="badge bg-danger">${l.win_rate}%</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        body.innerHTML = `
            <div class="text-center mb-3">
                <div class="small text-muted">Basado en <strong>${rec.sample_size || 0}</strong> señales históricas</div>
                <div class="h5 mb-0" style="color: #FFD700;">
                    Multiplier: ${(rec.multiplier || 1).toFixed(2)}x
                </div>
                <div class="small">Leverage sugerido: <strong>${rec.leverage || 1}x</strong></div>
            </div>
            <hr class="my-2 border-secondary">
            ${winnersHTML}
            ${losersHTML}
            ${!winnersHTML && !losersHTML ? '<div class="text-muted small text-center">Sin patrones detectados aún</div>' : ''}
            <div class="text-muted small mt-2 text-center">
                <i class="fas fa-clock me-1"></i>${rec.notes || ''}
            </div>
        `;
        
    } catch (err) {
        console.error('Error cargando review:', err);
        body.innerHTML = `<div class="alert alert-warning small">No se pudieron cargar las recomendaciones</div>`;
    }
}


// ============================================================================
// ANALIZAR LOS 5 PARES DE UNA TEMPORALIDAD
// ============================================================================

window.analyzeAllFuturesInTF = async function() {
    const timeframe = document.getElementById('fut-timeframe-select').value;
    const extraContent = document.getElementById('fut-extra-content');
    
    extraContent.innerHTML = `
        <div class="col-12">
            <div class="card bg-dark border-info">
                <div class="card-header bg-info bg-opacity-25">
                    <h6 class="mb-0"><i class="fas fa-list me-2"></i>Los 5 pares en ${timeframe}</h6>
                </div>
                <div class="card-body">
                    <div class="text-center py-3">
                        <div class="spinner-border text-info"></div>
                        <p class="small mt-2 mb-0">Analizando 5 pares en paralelo...</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    futShowToast(`Analizando 5 pares en ${timeframe}...`, 'info');
    
    try {
        const res = await fetch(`/api/futures/analyze_all/${timeframe}`);
        const json = await res.json();
        
        if (!json.success || !json.data) {
            extraContent.innerHTML = `<div class="col-12"><div class="alert alert-danger">Error: ${json.error || 'Sin datos'}</div></div>`;
            return;
        }
        
        const results = json.data;
        const correlation = results._correlation || {};
        
        let symbolsHTML = '';
        for (const [symbol, result] of Object.entries(results)) {
            if (symbol.startsWith('_')) continue; // Skip _correlation
            
            const decision = result.decision || {};
            const action = decision.action || 'NO_OPERAR';
            const confidence = decision.confidence || 0;
            const levels = result.levels || {};
            
            let badgeClass = 'bg-secondary';
            let icon = '⏸️';
            if (action === 'LONG') { badgeClass = 'bg-success'; icon = '📈'; }
            else if (action === 'SHORT') { badgeClass = 'bg-danger'; icon = '📉'; }
            
            symbolsHTML += `
                <div class="col-md-6 col-xl-4 mb-2">
                    <div class="card bg-dark border-secondary" style="cursor:pointer;" onclick="window.selectFuturesFromCard('${symbol}', '${timeframe}')">
                        <div class="card-body p-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <strong>${symbol.replace('-', '/')}</strong>
                                <span class="badge ${badgeClass}">${icon} ${action}</span>
                            </div>
                            <div class="small text-muted mt-1">
                                Confianza: ${confidence.toFixed(0)}%
                                ${action === 'LONG' || action === 'SHORT' ? `| ${levels.leverage || 1}x | ROI: ${futFormatPct(levels.roi_tp || 0)}` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }
        
        extraContent.innerHTML = `
            <div class="col-12">
                <div class="card bg-dark border-info">
                    <div class="card-header bg-info bg-opacity-25">
                        <h6 class="mb-0"><i class="fas fa-list me-2"></i>Los 5 pares en ${timeframe}</h6>
                    </div>
                    <div class="card-body">
                        <!-- Correlación intra-cripto -->
                        <div class="alert alert-secondary mb-3 small">
                            <strong><i class="fas fa-link me-1"></i>Correlación:</strong> ${correlation.rotation_signal || 'NEUTRAL'}
                            <br><small>${correlation.description || ''}</small>
                        </div>
                        
                        <!-- Grid de pares -->
                        <div class="row">
                            ${symbolsHTML}
                        </div>
                        <div class="text-muted small mt-2">
                            <i class="fas fa-info-circle me-1"></i>Haz clic en cualquier par para ver el análisis detallado
                        </div>
                    </div>
                </div>
            </div>
        `;
        
    } catch (err) {
        console.error('Error:', err);
        extraContent.innerHTML = `<div class="col-12"><div class="alert alert-danger">Error de conexión: ${err.message}</div></div>`;
    }
};


window.selectFuturesFromCard = function(symbol, timeframe) {
    document.getElementById('fut-symbol-select').value = symbol;
    document.getElementById('fut-timeframe-select').value = timeframe;
    window.analyzeFutures();
};


// ============================================================================
// SEÑALES ACTIVAS
// ============================================================================

window.showFuturesActiveSignals = async function() {
    const extraContent = document.getElementById('fut-extra-content');
    
    extraContent.innerHTML = `
        <div class="col-12">
            <div class="card bg-dark border-warning">
                <div class="card-header bg-warning bg-opacity-25">
                    <h6 class="mb-0"><i class="fas fa-bell me-2"></i>Señales LONG/SHORT Activas</h6>
                </div>
                <div class="card-body">
                    <div class="text-center py-3">
                        <div class="spinner-border text-warning"></div>
                        <p class="small mt-2 mb-0">Escaneando 5 pares × 6 temporalidades...</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    try {
        const res = await fetch('/api/futures/signals/active');
        const json = await res.json();
        
        if (!json.success) {
            extraContent.innerHTML = `<div class="col-12"><div class="alert alert-danger">Error: ${json.error || 'Sin datos'}</div></div>`;
            return;
        }
        
        const signals = json.signals || [];
        
        if (signals.length === 0) {
            extraContent.innerHTML = `
                <div class="col-12">
                    <div class="card bg-dark border-warning">
                        <div class="card-body text-center py-4">
                            <i class="fas fa-check-circle text-success" style="font-size: 2rem;"></i>
                            <p class="mt-2 mb-0">Sin señales de trading activas en este momento</p>
                        </div>
                    </div>
                </div>
            `;
            return;
        }
        
        let signalsHTML = signals.map(sig => {
            const badgeClass = sig.action === 'LONG' ? 'bg-success' : 'bg-danger';
            const icon = sig.action === 'LONG' ? '📈' : '📉';
            return `
                <tr style="cursor:pointer;" onclick="window.selectFuturesFromCard('${sig.symbol}', '${sig.timeframe}')">
                    <td><span class="badge ${badgeClass}">${icon} ${sig.action}</span></td>
                    <td>${sig.symbol.replace('-', '/')}</td>
                    <td>${sig.timeframe}</td>
                    <td class="text-warning">${sig.confidence.toFixed(0)}%</td>
                    <td>${sig.leverage}x</td>
                    <td class="text-success">${futFormatPct(sig.roi_tp)}</td>
                    <td class="text-danger">${futFormatPct(sig.roi_sl)}</td>
                    <td>1:${sig.risk_reward.toFixed(1)}</td>
                </tr>
            `;
        }).join('');
        
        extraContent.innerHTML = `
            <div class="col-12">
                <div class="card bg-dark border-warning">
                    <div class="card-header bg-warning bg-opacity-25">
                        <h6 class="mb-0"><i class="fas fa-bell me-2"></i>Señales Activas (${signals.length})</h6>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-dark table-hover table-sm">
                                <thead>
                                    <tr>
                                        <th>Acción</th>
                                        <th>Par</th>
                                        <th>TF</th>
                                        <th>Conf</th>
                                        <th>Lev</th>
                                        <th>ROI TP</th>
                                        <th>ROI SL</th>
                                        <th>R/R</th>
                                    </tr>
                                </thead>
                                <tbody>${signalsHTML}</tbody>
                            </table>
                        </div>
                        <div class="text-muted small">
                            <i class="fas fa-info-circle me-1"></i>Clic en cualquier fila para ver el detalle
                        </div>
                    </div>
                </div>
            </div>
        `;
        
    } catch (err) {
        console.error('Error:', err);
        extraContent.innerHTML = `<div class="col-12"><div class="alert alert-danger">Error: ${err.message}</div></div>`;
    }
};


// ============================================================================
// STATS GLOBALES DEL REVIEWTRADER
// ============================================================================

window.showReviewGlobalStats = async function() {
    const body = document.getElementById('fut-global-body');
    
    body.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border spinner-border-sm text-primary"></div>
            <p class="small mt-2 mb-0">Cargando stats...</p>
        </div>
    `;
    
    try {
        const res = await fetch('/api/review/general_stats');
        const json = await res.json();
        
        if (!json.success) {
            body.innerHTML = `<div class="text-muted small text-center py-3">Sin datos</div>`;
            return;
        }
        
        const stats = json.stats || [];
        
        if (stats.length === 0) {
            body.innerHTML = `
                <div class="text-muted small text-center py-3">
                    <i class="fas fa-hourglass-half me-1"></i>
                    Aún no hay estadísticas globales.<br>
                    Se generarán al ejecutar el ReviewTrader.
                </div>
            `;
            return;
        }
        
        // Top 5 estrategias
        const top5 = stats.slice(0, 5);
        
        let html = '<div class="small">';
        top5.forEach((s, idx) => {
            const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : `${idx+1}.`;
            const wrColor = s.win_rate >= 60 ? 'text-success' : s.win_rate >= 40 ? 'text-warning' : 'text-danger';
            html += `
                <div class="mb-2 pb-2 border-bottom border-secondary">
                    <div class="d-flex justify-content-between align-items-center">
                        <strong>${medal} ${s.strategy}</strong>
                        <span class="${wrColor}">${s.win_rate}%</span>
                    </div>
                    <div class="text-muted" style="font-size: 0.75rem;">
                        Muestras: ${s.sample} | Exp: ${(s.expectancy || 0).toFixed(2)}
                        ${s.is_degrading ? '<span class="badge bg-warning ms-1">⚠️ degradando</span>' : ''}
                    </div>
                </div>
            `;
        });
        html += '</div>';
        
        body.innerHTML = html;
        
    } catch (err) {
        console.error('Error:', err);
        body.innerHTML = `<div class="alert alert-warning small">Error: ${err.message}</div>`;
    }
};


// ============================================================================
// EJECUTAR REVIEW MANUALMENTE
// ============================================================================

window.runReviewNow = async function() {
    if (!confirm('¿Ejecutar el ciclo completo del ReviewTrader?\n\nEste proceso puede tardar 1-2 minutos y evaluará todas las señales pendientes.')) {
        return;
    }
    
    futShowToast('Ejecutando ReviewTrader... esto puede tardar 1-2 minutos.', 'info');
    
    try {
        const res = await fetch('/api/review/run_now', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Key': 'crypto_trader_analyst_2025' // Match con SCHEDULED_AUTH_KEY
            }
        });
        
        const json = await res.json();
        
        if (!json.success) {
            futShowToast('Error: ' + (json.error || 'desconocido'), 'danger');
            return;
        }
        
        const results = json.results || {};
        const evaluated = results.evaluated || {};
        const stats = results.stats || {};
        
        futShowToast(
            `Review completado: ${evaluated.tp_hit || 0} TP, ${evaluated.sl_hit || 0} SL, ${results.missed || 0} oportunidades. Stats: ${stats.specific || 0} específicas, ${stats.general || 0} generales.`,
            'success'
        );
        
        // Refrescar stats globales
        window.showReviewGlobalStats();
        
    } catch (err) {
        console.error('Error:', err);
        futShowToast('Error de conexión: ' + err.message, 'danger');
    }
};


// ============================================================================
// AUTO-CARGA STATS GLOBALES AL ABRIR EL MODAL
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Cargar stats globales cuando se abre el modal por primera vez
    const modal = document.getElementById('futuresModal');
    if (modal) {
        modal.addEventListener('shown.bs.modal', function() {
            console.log('Modal Futuros abierto - cargando stats iniciales');
            window.showReviewGlobalStats();
        });
    }
});
