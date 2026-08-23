// analytics.js - Lógica de la página /analytics
// Consume /api/analytics/* y /api/review/logs

console.log('📈 analytics.js cargado');

const PLOTLY_LAYOUT_BASE = {
    paper_bgcolor: '#0F1115',
    plot_bgcolor: '#0F1115',
    font: { family: 'Arial', size: 11, color: 'white' },
    margin: { l: 60, r: 30, t: 30, b: 60 }
};

const PLOTLY_CONFIG = {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d']
};


// ============================================================================
// UTILIDADES
// ============================================================================

function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) { console.log('[TOAST]', msg); return; }
    
    const colors = { info: 'bg-info', success: 'bg-success', danger: 'bg-danger', warning: 'bg-warning' };
    const bg = colors[type] || 'bg-secondary';
    
    const id = 'toast-' + Date.now();
    const html = `
        <div id="${id}" class="toast text-white ${bg}" role="alert">
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(id);
    new bootstrap.Toast(el, { delay: 3500 }).show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

function getFilters() {
    return {
        symbol: document.getElementById('f-symbol').value,
        timeframe: document.getElementById('f-timeframe').value,
        system_type: document.getElementById('f-system').value,
        action: document.getElementById('f-action').value,
        days_back: document.getElementById('f-days').value
    };
}

function buildQueryString(filters) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
        if (v) params.append(k, v);
    });
    return params.toString();
}

function formatPct(val, decimals = 2) {
    if (val === null || val === undefined) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(decimals)}%`;
}

function formatDate(iso) {
    if (!iso) return '--';
    try {
        return new Date(iso).toLocaleString('es-BO', { 
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    } catch(e) { return iso; }
}


// ============================================================================
// 1. KPIs GLOBALES
// ============================================================================

async function loadSummary() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/summary?' + qs);
        const json = await res.json();
        
        if (!json.success) { console.error('Error summary:', json.error); return; }
        
        const d = json.data;
        
        // ============ KPIs BÁSICOS ============
        document.getElementById('kpi-total').textContent = d.total_signals.toLocaleString();
        document.getElementById('kpi-resolved').textContent = `Resueltas: ${d.resolved.toLocaleString()}`;
        document.getElementById('kpi-winrate').textContent = d.win_rate + '%';
        document.getElementById('kpi-tps').textContent = d.tp_hit;
        document.getElementById('kpi-sls').textContent = d.sl_hit;
        document.getElementById('kpi-expectancy').textContent = (d.expectancy > 0 ? '+' : '') + d.expectancy;
        document.getElementById('kpi-avgwin').textContent = formatPct(d.avg_win_pct, 2);
        document.getElementById('kpi-strategies').textContent = d.unique_strategies;
        document.getElementById('kpi-days').textContent = d.days_back;
        
        // Colorear expectancy según sea positivo o negativo
        const expEl = document.getElementById('kpi-expectancy');
        expEl.style.color = d.expectancy > 0 ? '#00C076' : d.expectancy < 0 ? '#FF5B5B' : '#FFD700';
        
        // ============ KPIs ECONÓMICOS (nuevos v13) ============
        const pnlTotal = d.pnl_total_pct || 0;
        const pnlTotalEl = document.getElementById('kpi-pnl-total');
        if (pnlTotalEl) {
            pnlTotalEl.textContent = (pnlTotal >= 0 ? '+' : '') + pnlTotal.toFixed(2) + '%';
            pnlTotalEl.style.color = pnlTotal > 0 ? '#00C076' : pnlTotal < 0 ? '#FF5B5B' : '#FFD700';
        }
        
        const roi = d.roi_1000usd_estimated || 0;
        const roiEl = document.getElementById('kpi-roi');
        if (roiEl) {
            const usdFinal = 1000 * (1 + roi / 100);
            roiEl.textContent = (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%';
            roiEl.title = `Capital final: $${usdFinal.toFixed(2)}`;
            roiEl.style.color = roi > 0 ? '#00C076' : roi < 0 ? '#FF5B5B' : '#FFD700';
        }
        
        const pf = d.profit_factor || 0;
        const pfEl = document.getElementById('kpi-profit-factor');
        if (pfEl) {
            pfEl.textContent = pf.toFixed(2);
            pfEl.style.color = pf >= 1.5 ? '#00C076' : pf >= 1.0 ? '#FFD700' : '#FF5B5B';
        }
        
        const bestTrade = d.best_trade_pct || 0;
        const worstTrade = d.worst_trade_pct || 0;
        const bestEl = document.getElementById('kpi-best-trade');
        const worstEl = document.getElementById('kpi-worst-trade');
        if (bestEl) bestEl.textContent = (bestTrade >= 0 ? '+' : '') + bestTrade.toFixed(2) + '%';
        if (worstEl) worstEl.textContent = worstTrade.toFixed(2) + '%';
        
        const maxWinsEl = document.getElementById('kpi-max-wins');
        const maxLossesEl = document.getElementById('kpi-max-losses');
        if (maxWinsEl) maxWinsEl.textContent = d.max_consecutive_wins || 0;
        if (maxLossesEl) maxLossesEl.textContent = d.max_consecutive_losses || 0;
        
    } catch (err) {
        console.error('Error loadSummary:', err);
    }
}


// ============================================================================
// 2. RANKING DE ESTRATEGIAS
// ============================================================================

async function loadStrategiesRanking() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/strategies?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.length === 0) {
            Plotly.newPlot('chart-strategies', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos suficientes', font: { size: 14 } },
                height: 500
            });
            return;
        }
        
        const data = json.data;
        // Invertimos para que el top quede arriba en la barra horizontal
        data.reverse();
        
        const trace = {
            type: 'bar',
            orientation: 'h',
            x: data.map(d => d.win_rate),
            y: data.map(d => d.strategy),
            marker: {
                color: data.map(d => d.win_rate >= 60 ? '#00C076' : d.win_rate >= 45 ? '#FFD700' : '#FF5B5B')
            },
            text: data.map(d => `${d.win_rate}% (${d.wins}/${d.wins + d.losses})`),
            textposition: 'outside',
            hovertemplate: '<b>%{y}</b><br>Win Rate: %{x}%<br>Total: %{customdata}<extra></extra>',
            customdata: data.map(d => d.total)
        };
        
        const layout = {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Win Rate (%)', range: [0, 110], gridcolor: 'rgba(255,255,255,0.1)' },
            yaxis: { automargin: true, tickfont: { size: 10 } },
            margin: { l: 250, r: 60, t: 30, b: 40 },
            height: Math.max(500, data.length * 25)
        };
        
        // Línea vertical en 50%
        layout.shapes = [{
            type: 'line', x0: 50, x1: 50, y0: -0.5, y1: data.length - 0.5,
            line: { color: 'rgba(255,255,255,0.3)', dash: 'dash', width: 1 }
        }];
        
        Plotly.newPlot('chart-strategies', [trace], layout, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error strategies:', err);
    }
}


// ============================================================================
// 3. HEATMAP símbolo × timeframe
// ============================================================================

async function loadHeatmap() {
    try {
        const f = getFilters();
        const qs = buildQueryString({ system_type: f.system_type, action: f.action, days_back: f.days_back });
        const res = await fetch('/api/analytics/heatmap?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.symbols.length === 0) {
            Plotly.newPlot('chart-heatmap', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos suficientes', font: { size: 14 } },
                height: 400
            });
            return;
        }
        
        const d = json.data;
        
        // Texto de hover: win_rate + tamaño muestra
        const text = d.win_rates.map((row, i) => 
            row.map((val, j) => val !== null ? `${val}%<br>(${d.sample_sizes[i][j]} señales)` : 'Sin datos')
        );
        
        const trace = {
            type: 'heatmap',
            x: d.timeframes,
            y: d.symbols,
            z: d.win_rates,
            text: text,
            texttemplate: '%{z}%',
            textfont: { color: 'white', size: 11 },
            hoverinfo: 'text',
            colorscale: [
                [0, '#FF5B5B'], [0.4, '#FFD700'], [0.6, '#90EE90'], [1, '#00C076']
            ],
            zmin: 0, zmax: 100,
            colorbar: { title: 'WR %', tickfont: { color: 'white' } }
        };
        
        Plotly.newPlot('chart-heatmap', [trace], {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Timeframe' },
            yaxis: { title: 'Símbolo' },
            height: 400
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error heatmap:', err);
    }
}


// ============================================================================
// 4. TIMELINE
// ============================================================================

async function loadTimeline() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/timeline?bucket=week&' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.dates.length === 0) {
            Plotly.newPlot('chart-timeline', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos', font: { size: 14 } },
                height: 400
            });
            return;
        }
        
        const d = json.data;
        
        const traceWR = {
            x: d.dates,
            y: d.win_rates,
            type: 'scatter', mode: 'lines+markers',
            name: 'Win Rate (%)',
            line: { color: '#00C076', width: 2 },
            marker: { size: 8 },
            hovertemplate: '<b>%{x}</b><br>WR: %{y}%<br>Muestras: %{customdata}<extra></extra>',
            customdata: d.sample_sizes,
            yaxis: 'y'
        };
        
        const traceSamples = {
            x: d.dates,
            y: d.sample_sizes,
            type: 'bar',
            name: 'Cantidad señales',
            marker: { color: 'rgba(58, 139, 255, 0.3)' },
            yaxis: 'y2'
        };
        
        Plotly.newPlot('chart-timeline', [traceSamples, traceWR], {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Semana' },
            yaxis: { title: 'Win Rate (%)', range: [0, 100], gridcolor: 'rgba(255,255,255,0.1)' },
            yaxis2: { title: 'Señales', overlaying: 'y', side: 'right', gridcolor: 'rgba(255,255,255,0)' },
            height: 400,
            legend: { orientation: 'h', y: -0.15 },
            shapes: [{
                type: 'line', xref: 'paper',
                x0: 0, x1: 1, y0: 50, y1: 50,
                line: { color: 'rgba(255,255,255,0.3)', dash: 'dash', width: 1 }
            }]
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error timeline:', err);
    }
}


// ============================================================================
// 5. DISTRIBUCIÓN DE PnL
// ============================================================================

async function loadPnLDistribution() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/pnl_distribution?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.total === 0) {
            Plotly.newPlot('chart-pnl', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos', font: { size: 14 } },
                height: 350
            });
            return;
        }
        
        const d = json.data;
        
        const trace = {
            type: 'bar',
            x: d.labels,
            y: d.counts,
            marker: { color: d.colors },
            text: d.counts,
            textposition: 'outside',
            hovertemplate: '<b>%{x}</b><br>Señales: %{y}<extra></extra>'
        };
        
        Plotly.newPlot('chart-pnl', [trace], {
            ...PLOTLY_LAYOUT_BASE,
            title: { 
                text: `Total: ${d.total} señales · Positivas: ${d.positive} · Negativas: ${d.negative} · Media: ${formatPct(d.mean, 2)}`,
                font: { size: 12 }
            },
            xaxis: { title: 'Rango de PnL' },
            yaxis: { title: 'Cantidad', gridcolor: 'rgba(255,255,255,0.1)' },
            height: 350
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error pnl:', err);
    }
}


// ============================================================================
// 6. TABLAS: MEJORES Y PEORES OPERACIONES
// ============================================================================

async function loadTopOperations(mode = 'best') {
    try {
        const qs = buildQueryString({ ...getFilters(), mode, top_n: 10 });
        const res = await fetch('/api/analytics/top_operations?' + qs);
        const json = await res.json();
        
        const tbodyId = mode === 'best' ? 'tbody-best' : 'tbody-worst';
        const tbody = document.getElementById(tbodyId);
        
        if (!json.success || !json.data || json.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">Sin datos</td></tr>';
            return;
        }
        
        let html = '';
        json.data.forEach(op => {
            const pnlClass = op.pnl_pct >= 0 ? 'status-tp' : 'status-sl';
            const actionColor = op.action === 'LONG' ? 'success' : 'danger';
            html += `
                <tr onclick="window.showOperationDetail('${op.id}')">
                    <td><small>${op.symbol.replace('-', '/')}</small></td>
                    <td><small>${op.timeframe}</small></td>
                    <td><span class="badge bg-${actionColor}">${op.action}</span></td>
                    <td class="${pnlClass}">${formatPct(op.pnl_pct)}</td>
                    <td><small>${formatDate(op.created_at)}</small></td>
                    <td><i class="fas fa-search-plus text-info"></i></td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        
    } catch (err) {
        console.error('Error top ops:', err);
    }
}


// ============================================================================
// 7. DETALLE DE OPERACIÓN (modal)
// ============================================================================

window.showOperationDetail = async function(signalId) {
    const body = document.getElementById('opDetailBody');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div></div>';
    
    const modal = new bootstrap.Modal(document.getElementById('opDetailModal'));
    modal.show();
    
    try {
        const res = await fetch(`/api/analytics/operation_detail/${signalId}`);
        const json = await res.json();
        
        if (!json.success) {
            body.innerHTML = `<div class="alert alert-danger">${json.error || 'Error'}</div>`;
            return;
        }
        
        const op = json.data;
        const result = op.result || {};
        const statusColor = {
            'tp_hit': 'success', 'sl_hit': 'danger', 'expired': 'warning', 'pending': 'secondary'
        }[op.status] || 'secondary';
        
        const strategiesHTML = (op.strategies || []).map(s => 
            `<span class="badge bg-secondary me-1 mb-1">${s}</span>`
        ).join('');
        
        // Indicadores snapshot destacados
        const snapshot = op.indicators_snapshot || {};
        const context = op.context || {};
        
        body.innerHTML = `
            <div class="row g-3">
                <!-- Info principal -->
                <div class="col-md-6">
                    <div class="card bg-dark border-secondary">
                        <div class="card-header">
                            <strong>${op.symbol.replace('-', '/')} · ${op.timeframe}</strong>
                            <span class="badge bg-${op.action === 'LONG' ? 'success' : 'danger'} ms-2">${op.action}</span>
                            <span class="badge bg-${statusColor} ms-1">${op.status}</span>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-6"><small class="text-muted">Sistema:</small><br>${op.system_type}</div>
                                <div class="col-6"><small class="text-muted">Confianza:</small><br><strong>${op.confidence}%</strong></div>
                            </div>
                            <hr class="my-2">
                            <div class="row small">
                                <div class="col-6">
                                    <div class="text-muted">Entry:</div>
                                    <strong>${op.entry_price}</strong>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted">Exit:</div>
                                    <strong>${result.exit_price || '--'}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Stop Loss:</div>
                                    <strong class="text-danger">${op.stop_loss}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Take Profit:</div>
                                    <strong class="text-success">${op.take_profit}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">R/R:</div>
                                    <strong>1:${op.risk_reward}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Leverage:</div>
                                    <strong>${op.leverage}x</strong>
                                </div>
                                <div class="col-12 mt-3 text-center">
                                    <div class="text-muted">PnL final</div>
                                    <strong class="h4 ${(result.pnl_pct || 0) >= 0 ? 'text-success' : 'text-danger'}">
                                        ${formatPct(result.pnl_pct, 2)}
                                    </strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Indicadores + Estrategias -->
                <div class="col-md-6">
                    <div class="card bg-dark border-info mb-2">
                        <div class="card-header"><strong>🎯 Estrategias detectadas</strong></div>
                        <div class="card-body">${strategiesHTML || '<em class="text-muted">Ninguna</em>'}</div>
                    </div>
                    
                    <div class="card bg-dark border-secondary">
                        <div class="card-header"><strong>📊 Snapshot de indicadores</strong></div>
                        <div class="card-body small">
                            <div class="row">
                                <div class="col-6">ADX: <strong>${(snapshot.adx || 0).toFixed(1)}</strong></div>
                                <div class="col-6">RSI: <strong>${(snapshot.rsi || 0).toFixed(1)}</strong></div>
                                <div class="col-6">MACD: <strong>${(snapshot.macd_hist || 0).toFixed(2)}</strong></div>
                                <div class="col-6">MFI: <strong>${(snapshot.mfi || 0).toFixed(1)}</strong></div>
                                <div class="col-6">ATR%: <strong>${(snapshot.atr_pct || 0).toFixed(2)}</strong></div>
                                <div class="col-6">Vol ratio: <strong>${(snapshot.volume_ratio || 1).toFixed(2)}</strong></div>
                                <div class="col-6">Trend: <strong>${snapshot.trend_direction || '--'}</strong></div>
                                <div class="col-6">FTM: <strong>${snapshot.ftm_state || '--'}</strong></div>
                            </div>
                            <hr class="my-2">
                            <div class="row">
                                <div class="col-6">🐋 Whale buy: <strong>${snapshot.whale_buy ? 'sí' : 'no'}</strong></div>
                                <div class="col-6">🐋 Whale sell: <strong>${snapshot.whale_sell ? 'sí' : 'no'}</strong></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card bg-dark border-primary mt-2">
                        <div class="card-header"><strong>🌐 Contexto</strong></div>
                        <div class="card-body small">
                            <div>Sesión: <strong>${context.session || '--'}</strong> | Día: <strong>${context.day_type || '--'}</strong></div>
                            ${context.fear_greed ? `<div>Fear & Greed: <strong>${context.fear_greed}</strong> (${context.sentiment_bias || 'neutral'})</div>` : ''}
                            ${context.rotation_signal ? `<div>Rotación: <strong>${context.rotation_signal}</strong></div>` : ''}
                        </div>
                    </div>
                </div>
                
                <!-- Timestamps -->
                <div class="col-12">
                    <div class="card bg-dark border-secondary">
                        <div class="card-body small">
                            <div class="row">
                                <div class="col-md-4">🕐 <strong>Señal creada:</strong> ${formatDate(op.created_at)}</div>
                                <div class="col-md-4">🕒 <strong>Vela evaluada:</strong> ${formatDate(op.candle_timestamp)}</div>
                                <div class="col-md-4">🕓 <strong>Cerrada:</strong> ${formatDate(op.closed_at)}</div>
                            </div>
                            ${result.candles_to_result ? `<div class="mt-2">⏱️ Tardó <strong>${result.candles_to_result}</strong> velas en resolverse</div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
    } catch (err) {
        console.error('Error detail:', err);
        body.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
    }
};


// ============================================================================
// 8. LOGS DEL REVIEWTRADER
// ============================================================================

window.loadLogs = async function() {
    const container = document.getElementById('logs-container');
    container.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm text-info"></div> Cargando logs...</div>';
    
    try {
        const res = await fetch('/api/review/logs?limit=30');
        
        // v22.6: manejar caso de HTML de error (502/504 del gunicorn).
        // Antes: res.json() lanzaba "Unexpected token '<'" y todo caía sin
        // mensaje claro. Ahora: leer como texto primero y validar.
        const text = await res.text();
        let json;
        try {
            json = JSON.parse(text);
        } catch (parseErr) {
            container.innerHTML = `
                <div class="alert alert-warning py-3">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    El servidor respondió con un error (status ${res.status}). Es probable que estuviera saturado. Recarga la página en unos segundos.
                </div>
            `;
            console.error('loadLogs: respuesta no-JSON', text.slice(0, 200));
            return;
        }
        
        if (!json.success || !json.logs || json.logs.length === 0) {
            const errMsg = json.error ? ` (${json.error})` : '';
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-info-circle me-1"></i>
                    Aún no hay logs${errMsg}. Ejecuta el ReviewTrader manualmente o espera al ciclo diario (20:00 Bolivia).
                </div>
            `;
            return;
        }
        
        let html = '';
        json.logs.forEach(log => {
            const statusClass = log.status === 'failed' ? 'log-error' : log.status === 'partial' ? 'log-partial' : '';
            const statusIcon = log.status === 'success' ? '✅' : log.status === 'partial' ? '⚠️' : '❌';
            const triggerIcon = log.trigger_source === 'scheduler' ? '⏰' : '👤';
            
            const errorsHTML = (log.errors && log.errors.length > 0) 
                ? `<div class="mt-2 text-danger small">❌ Errores: ${log.errors.join(' · ')}</div>`
                : '';
            
            const storage = log.storage_stats || {};
            const totalRows = Object.values(storage).reduce((a, b) => a + (b > 0 ? b : 0), 0);
            
            html += `
                <div class="log-entry ${statusClass}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <strong>${statusIcon} ${formatDate(log.run_started_at)}</strong>
                            <span class="badge bg-secondary ms-2">${triggerIcon} ${log.trigger_source}</span>
                            <span class="badge bg-dark ms-1">${log.duration_seconds}s</span>
                        </div>
                        <small class="text-muted">${log.status.toUpperCase()}</small>
                    </div>
                    <div class="mt-2 small">
                        <span class="me-3">📊 Evaluadas: <strong>${log.signals_evaluated}</strong></span>
                        <span class="me-3 text-success">✅ TP: <strong>${log.tp_hits}</strong></span>
                        <span class="me-3 text-danger">❌ SL: <strong>${log.sl_hits}</strong></span>
                        <span class="me-3 text-warning">⏰ Exp: <strong>${log.expired}</strong></span>
                        <span class="me-3 text-info">💡 Oport. perdidas: <strong>${log.missed_opportunities_found}</strong></span>
                    </div>
                    <div class="mt-1 small text-muted">
                        📈 Stats: ${log.stats_specific_updated} específicas · ${log.stats_general_updated} generales
                        · 🧹 TTL: ${log.ttl_deleted} borradas · Compresión: ${log.low_sample_deleted}
                        · 💾 Total BD: ${totalRows} filas
                    </div>
                    ${log.notes ? `<div class="mt-1 small">📝 ${log.notes}</div>` : ''}
                    ${errorsHTML}
                </div>
            `;
        });
        
        container.innerHTML = html;
        
    } catch (err) {
        console.error('Error logs:', err);
        container.innerHTML = `<div class="alert alert-danger">Error cargando logs: ${err.message}</div>`;
    }
};


// ============================================================================
// EJECUTAR REVIEWTRADER MANUALMENTE
// ============================================================================

window.runReviewManually = async function() {
    if (!confirm('¿Ejecutar el ciclo completo del ReviewTrader?\n\nEsto puede tardar 1-2 minutos.')) return;
    
    showToast('🎓 Ejecutando ReviewTrader... esto tardará 1-2 minutos.', 'info');
    
    try {
        const res = await fetch('/api/review/run_now', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Key': 'crypto_trader_analyst_2025'
            }
        });
        
        const json = await res.json();
        
        if (!json.success) {
            showToast('Error: ' + (json.error || 'desconocido'), 'danger');
            return;
        }
        
        const r = json.results || {};
        const ev = r.evaluated || {};
        showToast(
            `✅ ReviewTrader completo: ${ev.tp_hit || 0} TP, ${ev.sl_hit || 0} SL, ${r.missed || 0} oportunidades.`,
            'success'
        );
        
        // Refrescar todos los datos
        window.loadAllAnalytics();
        window.loadLogs();
        
    } catch (err) {
        showToast('Error de conexión: ' + err.message, 'danger');
    }
};


// ============================================================================
// CARGAR TODO
// ============================================================================

window.loadAllAnalytics = async function() {
    showToast('🔄 Actualizando estadísticas...', 'info');
    
    await Promise.all([
        loadSummary(),
        loadStrategiesRanking(),
        loadHeatmap(),
        loadTimeline(),
        loadPnLDistribution(),
        loadTopOperations('best'),
        loadTopOperations('worst')
    ]);
    
    showToast('✅ Estadísticas actualizadas', 'success');
};


// ============================================================================
// INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('📈 Página Analytics inicializada');
    
    // Carga inicial
    window.loadAllAnalytics();
    window.loadLogs();
    
    // Auto-refresh de KPIs y logs cada 5 min
    setInterval(() => {
        loadSummary();
        window.loadLogs();
    }, 300000);
});
