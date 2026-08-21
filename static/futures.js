// futures.js - Solo se carga en la página /futures
// Añade un panel lateral con el ReviewTrader (estrategias ganadoras/perdedoras)
// Los gráficos e indicadores ya vienen de script.js y funcionan igual que en Spot

console.log('🚀 futures.js cargado - modo Futuros activo');


// ============================================================================
// UTILIDAD: mostrar toast
// ============================================================================
function futShowToast(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(msg, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${msg}`);
    }
}


// ============================================================================
// INSERTAR PANEL DEL REVIEWTRADER EN LA PÁGINA
// ============================================================================
// Estrategia: agregar un card en la columna derecha (col-lg-3) con la info del ReviewTrader

function insertReviewTraderPanel() {
    // Buscar la columna derecha (donde está "Resumen del Análisis", "Operación Actual", etc.)
    const cards = document.querySelectorAll('.col-lg-3 .card');
    if (cards.length === 0) {
        console.warn('No se encontró columna lateral - reintentando en 1 seg');
        setTimeout(insertReviewTraderPanel, 1000);
        return;
    }
    
    // Obtener el contenedor padre del primer card
    const container = cards[0].parentElement;
    if (!container) return;
    
    // Crear el card del ReviewTrader
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
            <div class="text-muted small text-center py-3">
                Cargando recomendaciones...
            </div>
        </div>
    `;
    
    // Insertar como primer card (antes del "Resumen del Análisis")
    container.insertBefore(reviewCard, cards[0]);
    
    // Crear también el card de stats globales
    const globalCard = document.createElement('div');
    globalCard.className = 'card bg-dark border-primary mb-4';
    globalCard.id = 'review-global-panel-container';
    globalCard.innerHTML = `
        <div class="card-header bg-primary bg-opacity-25">
            <h6 class="mb-0">
                <i class="fas fa-globe me-2"></i>
                🌐 Estrategias Globales
            </h6>
        </div>
        <div class="card-body" id="review-global-panel-body">
            <div class="text-muted small text-center py-3">
                Cargando...
            </div>
        </div>
    `;
    container.insertBefore(globalCard, cards[0]);
    
    console.log('✅ Panel del ReviewTrader insertado');
    
    // Cargar datos iniciales
    window.refreshReviewPanel();
    window.loadGlobalStats();
}


// ============================================================================
// CARGAR RECOMENDACIONES DEL REVIEWTRADER PARA EL PAR/TF/ACCIÓN ACTUAL
// ============================================================================

window.refreshReviewPanel = async function() {
    const body = document.getElementById('review-trader-panel-body');
    if (!body) return;
    
    const symbol = document.getElementById('symbol-select')?.value || 'BTC-USDT';
    const timeframe = document.getElementById('interval-select')?.value || '1h';
    
    // Determinar acción actual del análisis
    let action = 'LONG'; // por defecto
    if (window.currentAnalysis && window.currentAnalysis.decision) {
        const currentAction = window.currentAnalysis.decision.action;
        if (currentAction === 'LONG' || currentAction === 'COMPRA_SPOT') action = 'LONG';
        else if (currentAction === 'SHORT' || currentAction === 'VENTA_SPOT') action = 'SHORT';
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
        
        // Renderizar
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
                            <span title="${w.strategy}">${idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '•'} ${(w.strategy || '').length > 20 ? w.strategy.substring(0, 18) + '...' : w.strategy}</span>
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
        console.error('Error cargando review:', err);
        body.innerHTML = `<div class="alert alert-warning small mb-0">Error de conexión</div>`;
    }
};


// ============================================================================
// CARGAR ESTADÍSTICAS GLOBALES
// ============================================================================

window.loadGlobalStats = async function() {
    const body = document.getElementById('review-global-panel-body');
    if (!body) return;
    
    try {
        const res = await fetch('/api/review/general_stats');
        const json = await res.json();
        
        if (!json.success || !json.stats || json.stats.length === 0) {
            body.innerHTML = `
                <div class="text-muted small text-center py-3">
                    <i class="fas fa-hourglass-half me-1"></i>
                    Aún no hay estadísticas globales.
                </div>
            `;
            return;
        }
        
        const stats = json.stats.slice(0, 5);
        
        let html = '';
        stats.forEach((s, idx) => {
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
        console.error('Error cargando stats globales:', err);
        body.innerHTML = `<div class="alert alert-warning small mb-0">Error de conexión</div>`;
    }
};


// ============================================================================
// INICIALIZACIÓN
// ============================================================================
// Esperar a que el DOM esté listo y el panel principal cargado

document.addEventListener('DOMContentLoaded', function() {
    // Dar tiempo a que se rendericen los cards del sistema principal
    setTimeout(() => {
        insertReviewTraderPanel();
    }, 800);
    
    // Refrescar el panel cada 60 segundos
    setInterval(() => {
        if (typeof window.refreshReviewPanel === 'function') {
            window.refreshReviewPanel();
        }
    }, 60000);
    
    // Refrescar stats globales cada 5 minutos
    setInterval(() => {
        if (typeof window.loadGlobalStats === 'function') {
            window.loadGlobalStats();
        }
    }, 300000);
});
