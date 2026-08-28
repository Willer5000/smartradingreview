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
    if (!window.IS_FUTURES_PAGE) {
        return;
    }

    const signalsList = document.getElementById('active-signals-list');
    const signalsCount = document.getElementById('active-signals-count');

    if (!signalsList) return;

    // Evitar peticiones simultáneas.
    if (window._futuresSignalsState.activeLoading) {
        console.log('⏳ Active Futures: petición anterior todavía en curso. Se omite.');
        return;
    }

    window._futuresSignalsState.activeLoading = true;
    
    if (!window.futuresActiveLoaded) {
        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-muted text-center py-3">
                <div class="spinner-border spinner-border-sm text-warning me-2"></div>
                Escaneando 5 cripto × 6 TF...
            </div>
        `;
    }
    
    // Fetch con timeout de 3 min
    const controllerAS = new AbortController();
    const timeoutASId = setTimeout(() => controllerAS.abort(), 180000);
    
    fetch('/api/futures/signals/active?min_confidence=60', { signal: controllerAS.signal })
        .then(r => {
            clearTimeout(timeoutASId);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(json => {
            if (!json.success) {
                signalsList.innerHTML = `<div class="list-group-item bg-dark text-danger text-center py-3">Error: ${json.error || 'desconocido'}</div>`;
                return;
            }
            
            // Si el servidor está calentando el caché, mostrar mensaje y reintentar
            if (json.warming_up && (!json.signals || json.signals.length === 0)) {
                signalsList.innerHTML = `
                    <div class="list-group-item bg-dark text-info text-center py-3">
                        <div class="spinner-border spinner-border-sm me-2"></div>
                        <i class="fas fa-fire me-1"></i>
                        Servidor calentando caché...<br>
                        <small class="text-muted">Primera carga: 4-5 min (30 análisis). Refresco automático en 60s.</small>
                    </div>
                `;
                if (signalsCount) { signalsCount.textContent = '0'; signalsCount.className = 'badge bg-info'; }
                setTimeout(() => {
                    if (typeof window.updateActiveSignals === 'function') window.updateActiveSignals();
                }, 60000);
                return;
            }
            
            window.futuresActiveLoaded = true;
            window._futuresSignalsState.activeLoading = false;
            
            const signals = json.signals || [];
            if (signalsCount) {
                signalsCount.textContent = signals.length;
                signalsCount.className = `badge bg-${signals.length > 0 ? 'success' : 'secondary'}`;
            }
            
            if (signals.length === 0) {
                signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3">Sin señales LONG/SHORT activas en este momento</div>';
                return;
            }
            
            let html = '';
            signals.forEach(sig => {
                const isLong = sig.action === 'LONG';
                const badgeColor = isLong ? 'success' : 'danger';
                const icon = isLong ? '📈' : '📉';
                const symbolName = sig.symbol.replace('-', '/');
                
                html += `
                    <div class="list-group-item bg-dark text-white border-secondary" 
                         style="cursor: pointer;"
                         onclick="window.changeToSignal('${sig.symbol}', '${sig.timeframe}')"
                         onmouseover="this.style.backgroundColor='#1a1e24'"
                         onmouseout="this.style.backgroundColor=''">
                        <!-- Fila 1: acción + confianza -->
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <span class="badge bg-${badgeColor} me-2">${icon} ${sig.action}</span>
                                <strong>${symbolName}</strong>
                                <span class="badge bg-dark ms-1">${sig.timeframe}</span>
                            </div>
                            <span class="badge bg-warning text-dark">${fmtConfidence(sig.confidence)}%</span>
                        </div>
                        <!-- Fila 2: leverage + R/R + ROI -->
                        <div class="mt-2 d-flex justify-content-between align-items-center" style="font-size: 0.75rem;">
                            <div>
                                <span class="badge bg-secondary me-1">Lev ${sig.leverage}x</span>
                                <span class="badge bg-dark">R/R 1:${sig.risk_reward.toFixed(1)}</span>
                            </div>
                            <div>
                                <span class="text-success">TP ${futFormatPct(sig.roi_tp, 1)}</span>
                                <span class="mx-1 text-muted">|</span>
                                <span class="text-danger">SL ${futFormatPct(sig.roi_sl, 1)}</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            signalsList.innerHTML = html;
        })
        .catch(err => {
            window._futuresSignalsState.activeLoading = false;
            clearTimeout(timeoutASId);
            console.error('Error futures active:', err);
            const isAbort = err.name === 'AbortError';
            const errMsg = isAbort 
                ? 'Servidor calentando caché (~2 min). Reintentando en 30s...'
                : `Error: ${err.message || 'conexión perdida'}`;
            signalsList.innerHTML = `<div class="list-group-item bg-dark text-warning text-center py-3"><i class="fas fa-hourglass-half me-1"></i>${errMsg}</div>`;
            if (isAbort) {
                setTimeout(() => {
                    if (typeof window.updateActiveSignals === 'function') window.updateActiveSignals();
                }, 60000);
            }
        });
};


// ============================================================================
// SOBREESCRIBIR: updatePreviousSignals (vela ANTERIOR — estática)
// ============================================================================

window.updatePreviousSignals = function() {
    if (!window.IS_FUTURES_PAGE) {
        return;
    }

    const signalsList = document.getElementById('prev-signals-list');
    const signalsCount = document.getElementById('prev-signals-count');

    if (!signalsList) return;

    // Evitar peticiones simultáneas.
    if (window._futuresSignalsState.previousLoading) {
        console.log('⏳ Previous Futures: petición anterior todavía en curso. Se omite.');
        return;
    }

    window._futuresSignalsState.previousLoading = true;
    
    if (!window.futuresPrevLoaded) {
        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-muted text-center py-3">
                <div class="spinner-border spinner-border-sm text-warning me-2"></div>
                Cargando señales de la vela anterior...
                <div class="small mt-2 text-info">
                    <i class="fas fa-info-circle me-1"></i>
                    El primer análisis puede tardar hasta 2 minutos (se cachea 5 min)
                </div>
            </div>
        `;
    }
    
    // Fetch con timeout largo (3 minutos)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);
    
    fetch('/api/futures/signals/previous?min_confidence=55', { signal: controller.signal })
        .then(r => {
            clearTimeout(timeoutId);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
        .then(json => {
            if (!json.success) {
                signalsList.innerHTML = `<div class="list-group-item bg-dark text-warning text-center py-3">⚠️ ${json.error || 'Error del servidor'}</div>`;
                if (signalsCount) { signalsCount.textContent = '0'; signalsCount.className = 'badge bg-secondary'; }
                return;
            }
            
            // Si el servidor está calentando el caché
            if (json.warming_up && (!json.signals || json.signals.length === 0)) {
                signalsList.innerHTML = `
                    <div class="list-group-item bg-dark text-info text-center py-3">
                        <div class="spinner-border spinner-border-sm me-2"></div>
                        <i class="fas fa-fire me-1"></i>
                        Servidor preparando análisis de futuros...<br>
                        <small class="text-muted">
                            Los datos aparecerán automáticamente cuando termine el análisis.
                        </small>
                    </div>
                `;
            
                if (signalsCount) {
                    signalsCount.textContent = '0';
                    signalsCount.className = 'badge bg-info';
                }
            
                window._futuresSignalsState.activeLoading = false;
                return;
            }
            
            const signals = json.signals || [];
            const activeCount = json.active_count || 0;
            
            if (signalsCount) {
                signalsCount.textContent = activeCount;
                signalsCount.className = `badge bg-${activeCount > 0 ? 'warning' : 'secondary'}`;
            }
            
            if (signals.length === 0) {
                signalsList.innerHTML =
                    '<div class="list-group-item bg-dark text-muted text-center py-3">Sin señales LONG/SHORT en la vela anterior</div>';
            
                window.futuresPrevLoaded = true;
                window._futuresSignalsState.previousLoading = false;
                return;
            }
            
            let html = '';
            signals.forEach(sig => {
                const isLong = sig.action === 'LONG';
                const badgeColor = isLong ? 'success' : 'danger';
                const icon = isLong ? '📈' : '📉';
                const symbolName = sig.symbol.replace('-', '/');
                const inactive = sig.activa !== 1;
                const opacity = inactive ? 'opacity-50' : '';
                
                let statusBadge = '';
                if (sig.resultado === 'tp_hit') {
                    statusBadge = '<span class="badge bg-success">✅ TP</span>';
                } else if (sig.resultado === 'sl_hit') {
                    statusBadge = '<span class="badge bg-danger">❌ SL</span>';
                } else {
                    statusBadge = '<span class="badge bg-warning text-dark">⏱️ Activa</span>';
                }
                
                html += `
                    <div class="list-group-item bg-dark text-white border-secondary ${opacity}"
                         style="cursor: pointer;"
                         data-signal='${JSON.stringify(sig).replace(/'/g, "\\'")}'
                         onclick="const s=JSON.parse(this.getAttribute('data-signal')); window.showFuturesPrevJustif(s);">
                        <!-- Fila 1 -->
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <span class="badge bg-${badgeColor} me-2">${icon} ${sig.action}</span>
                                <strong>${symbolName}</strong>
                                <span class="badge bg-dark ms-1">${sig.timeframe}</span>
                            </div>
                            <div>
                                ${statusBadge}
                                <span class="badge bg-secondary ms-1">${fmtConfidence(sig.confidence)}%</span>
                            </div>
                        </div>
                        <!-- Fila 2 -->
                        <div class="mt-2 d-flex justify-content-between" style="font-size: 0.72rem;">
                            <div>
                                <span class="badge bg-dark me-1">Lev ${sig.leverage}x</span>
                                <span class="badge bg-dark">R/R 1:${sig.risk_reward.toFixed(1)}</span>
                            </div>
                            <div>
                                <span class="text-success">TP ${futFormatPct(sig.roi_tp, 1)}</span>
                                <span class="mx-1 text-muted">·</span>
                                <span class="text-danger">SL ${futFormatPct(sig.roi_sl, 1)}</span>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            signalsList.innerHTML = html;
            window.futuresPrevLoaded = true;
        })
        .catch(err => {
            window._futuresSignalsState.previousLoading = false;
        
            clearTimeout(timeoutId);
            console.error('Error futures previous:', err);
        
            const isAbort = err.name === 'AbortError';
        
            const errMsg = isAbort
                ? 'El servidor está preparando el análisis de futuros. Se volverá a consultar automáticamente.'
                : `Error: ${err.message || 'conexión perdida'}`;
        
            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-warning text-center py-3">
                    <i class="fas fa-hourglass-half me-1"></i>
                    ${errMsg}
                </div>
            `;
        });
};


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
            estadoHTML = `<div class="alert alert-danger mt-3"><strong>❌ SL ALCANZADO</strong> - operación fallida</div>`;
        } else {
            estadoHTML = `<div class="alert alert-warning mt-3"><strong>⏱️ SEÑAL ACTIVA</strong> - aún no toca TP ni SL</div>`;
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
// INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        insertReviewTraderPanel();
    }, 800);
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
                    window.openSaveSignalModal(sig);
                };
            }
        }, 150);
    };
})();

// ============ Abrir modal "Guardar señal" ============
// ============ Abrir modal "Guardar señal" ============
window.openSaveSignalModal = function(sig) {
    // Si no recibe parámetro, fallback a la variable global (compatibilidad)
    if (!sig) {
        sig = window._currentPrevSignal;
    }
    
    // Si sigue sin haber señal, intentar usar el análisis actual del panel principal
    if (!sig && window.currentAnalysis && window.currentAnalysis.decision) {
        const d = window.currentAnalysis.decision;
        const l = window.currentAnalysis.levels || {};
        sig = {
            symbol: window.currentAnalysis.symbol || window.currentSymbol,
            timeframe: window.currentAnalysis.timeframe || window.currentInterval,
            action: (d.action === 'SHORT' || d.action === 'VENTA_SPOT') ? 'SHORT' : 'LONG',
            confidence: d.confidence || 0,
            entry: l.entry || window.currentAnalysis.current_price,
            stop_loss: l.stop_loss || 0,
            take_profit: l.take_profit || 0,
            leverage: l.leverage || 1
        };
        console.log('✅ Usando análisis actual como fallback:', sig.symbol, sig.action);
    }
    
    if (!sig) {
        showToast('No hay señal activa ni seleccionada. Esperá a que cargue el análisis o hacé clic en una señal de la vela anterior.', 'warning');
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
    
    // Fallback: si no hay entry/sl/tp en la señal, usar el precio actual del mercado como base
    const currentPrice = window.lastPrices?.[sig.symbol] || window.currentAnalysis?.current_price || 0;
    const defaultEntry = currentPrice > 0 ? currentPrice.toFixed(2) : '';
    const defaultSL = currentPrice > 0 ? (currentPrice * 0.95).toFixed(2) : '';  // 5% abajo
    const defaultTP = currentPrice > 0 ? (currentPrice * 1.10).toFixed(2) : '';  // 10% arriba
    
    document.getElementById('ss-entry').value = sig.entry || sig.entry_price || defaultEntry;
    document.getElementById('ss-sl').value = sig.stop_loss || defaultSL;
    document.getElementById('ss-tp').value = sig.take_profit || defaultTP;
    document.getElementById('ss-notes').value = '';
    // v22.9.4: fecha/hora de ingreso — default = ahora en zona local del navegador
    document.getElementById('ss-entry-at').value = _nowLocalDatetimeInput();

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
            showToast('✅ Señal guardada correctamente', 'success');
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
// ============ Refrescar lista y KPIs ============
window.updateSavedSignalsList = async function() {
    if (!window.IS_FUTURES_PAGE) return;
    
    const card = document.getElementById('saved-signals-card');
    const list = document.getElementById('saved-signals-list');
    if (!card || !list) return;
    
    // Mostrar la card en futuros
    card.style.display = 'block';
    
    try {
        // KPIs propios
        const kRes = await fetch('/api/saved_signals/kpis');
        const kJson = await kRes.json();
        if (kJson.success) {
            const k = kJson.data || {};
            const wrEl = document.getElementById('ss-kpi-winrate');
            const pnlEl = document.getElementById('ss-kpi-pnl');
            const cntEl = document.getElementById('ss-kpi-count');
            if (wrEl) {
                wrEl.textContent = `WR: ${(k.win_rate || 0).toFixed(1)}%`;
                let cls = 'bg-secondary';
                if (k.total >= 5) {
                    cls = k.win_rate >= 55 ? 'bg-success' : (k.win_rate >= 40 ? 'bg-warning text-dark' : 'bg-danger');
                }
                wrEl.className = 'badge ' + cls;
            }
            if (pnlEl) {
                const sign = (k.pnl_total_usdt || 0) >= 0 ? '+' : '';
                pnlEl.textContent = `PnL: ${sign}${(k.pnl_total_usdt || 0).toFixed(2)} USDT`;
                let cls = 'bg-secondary';
                if (k.total >= 5) {
                    cls = k.pnl_total_usdt > 0 ? 'bg-success' : (k.pnl_total_usdt < 0 ? 'bg-danger' : 'bg-warning text-dark');
                }
                pnlEl.className = 'badge ' + cls;
            }
            if (cntEl) {
                cntEl.textContent = `${k.total || 0} cerradas / ${k.active || 0} activas`;
            }
        }
        
        // Lista de todas (activas + cerradas recientes)
        const user = (typeof getAuthenticatedUser === 'function' && getAuthenticatedUser()) 
                  || (typeof currentUser !== 'undefined' && currentUser) 
                  || localStorage.getItem('tgp_session_user') 
                  || localStorage.getItem('smarttrading_user') 
                  || 'Invitado';
        const lRes = await fetch('/api/saved_signals?limit=100&user=' + encodeURIComponent(user));
        const lJson = await lRes.json();
        if (!lJson.success) {
            list.innerHTML = `<div class="list-group-item bg-dark text-warning">Error: ${lJson.error || 'desconocido'}</div>`;
            return;
        }
        
        const signals = lJson.signals || [];
        if (signals.length === 0) {
            list.innerHTML = `
                <div class="list-group-item bg-dark text-muted text-center py-3">
                    <i class="fas fa-info-circle me-1"></i>
                    Aún no has guardado ninguna señal.
                </div>`;
            return;
        }
        
        let html = '';
        signals.forEach(s => {
            const emoji = s.action === 'LONG' ? '📈' : '📉';
            const statusBadge = _statusBadge(s.status, s.entry_touched);
            const pnlDisplay = _formatPnl(s);
            const bgColor = s.action === 'LONG' ? 'success' : 'danger';
            
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
                </a>
            `;
        });
        list.innerHTML = html;
    } catch (e) {
        list.innerHTML = `<div class="list-group-item bg-dark text-danger">Error: ${e.message}</div>`;
    }
};

function _statusBadge(status, entryTouched) {
    if (status === 'active') return '<span class="badge bg-info">⏳ Esperando entry</span>';
    if (status === 'entry_touched') return '<span class="badge bg-primary">🎯 En operación</span>';
    if (status === 'tp_hit') return '<span class="badge bg-success">✅ TP</span>';
    if (status === 'sl_hit') return '<span class="badge bg-danger">❌ SL</span>';
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
        // Renderizar el gráfico Plotly
        if (c && c.time && c.time.length > 0) {
            _renderSavedSignalChart(c, sig, currentPrice);
        } else {
            document.getElementById('saved-signal-chart').innerHTML = 
                '<div class="alert alert-warning">No hay datos de velas para este par/timeframe</div>';
        }              
        _renderSavedSignalChart(c, sig, currentPrice);
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
