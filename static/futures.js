// futures.js - Solo se carga en la página /futures
// SOBREESCRIBE las funciones de script.js que consultan spot para que consulten
// solo los endpoints /api/futures/* con los símbolos y timeframes de futuros.
// También añade el panel del ReviewTrader y adapta la correlación.

console.log('🚀 futures.js cargado - modo Futuros activo');

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

window.updateActiveSignals = function() {
    if (!window.IS_FUTURES_PAGE) {
        // No estamos en futuros - dejar que script.js maneje spot
        return;
    }
    
    const signalsList = document.getElementById('active-signals-list');
    const signalsCount = document.getElementById('active-signals-count');
    if (!signalsList) return;
    
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
        return; // deja que script.js maneje spot
    }
    
    const signalsList = document.getElementById('prev-signals-list');
    const signalsCount = document.getElementById('prev-signals-count');
    if (!signalsList) return;
    
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
                        Servidor calentando caché...<br>
                        <small class="text-muted">Primera carga: 4-5 min (30 análisis). Refresco automático en 60s.</small>
                    </div>
                `;
                if (signalsCount) { signalsCount.textContent = '0'; signalsCount.className = 'badge bg-info'; }
                setTimeout(() => {
                    if (typeof window.updatePreviousSignals === 'function') window.updatePreviousSignals();
                }, 60000);
                return;
            }
            
            const signals = json.signals || [];
            const activeCount = json.active_count || 0;
            
            if (signalsCount) {
                signalsCount.textContent = activeCount;
                signalsCount.className = `badge bg-${activeCount > 0 ? 'warning' : 'secondary'}`;
            }
            
            if (signals.length === 0) {
                signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3">Sin señales LONG/SHORT en la vela anterior</div>';
                window.futuresPrevLoaded = true;
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
                         onclick='window.showFuturesPrevJustif(${JSON.stringify(sig).replace(/'/g, "\\'")})'>
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
            clearTimeout(timeoutId);
            console.error('Error futures previous:', err);
            const isAbort = err.name === 'AbortError';
            const errMsg = isAbort 
                ? 'El servidor está calentando la caché (primera vez tarda ~2 min). Reintentando en 30s...'
                : `Error: ${err.message || 'conexión perdida'}`;
            
            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-warning text-center py-3">
                    <i class="fas fa-hourglass-half me-1"></i>
                    ${errMsg}
                </div>
            `;
            
            // Auto-retry en 30s si fue timeout
            if (isAbort) {
                setTimeout(() => {
                    if (typeof window.updatePreviousSignals === 'function') {
                        console.log('🔄 Reintentando updatePreviousSignals después de timeout...');
                        window.updatePreviousSignals();
                    }
                }, 60000);
            }
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
    setTimeout(() => {
        if (typeof window.updateActiveSignals === 'function') {
            console.log('🚀 futures.js: cargando señales activas iniciales');
            window.updateActiveSignals();
        }
        if (typeof window.updatePreviousSignals === 'function') {
            console.log('🚀 futures.js: cargando señales anteriores iniciales');
            window.updatePreviousSignals();
        }
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
