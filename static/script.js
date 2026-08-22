/* static/script.js - Frontend interactivo del sistema experto */
/* VERSIÓN DEFINITIVA - TODOS LOS GRÁFICOS CORREGIDOS */

let currentAnalysis = null;
let currentSymbol = 'BTC-USDT';
let currentInterval = '1D';

// Helper global: nunca mostrar confianza > 100% (defensa contra datos viejos).
// Si futures.js ya lo definió, no lo sobreescribe.
if (typeof window.fmtConfidence !== 'function') {
    window.fmtConfidence = function(c) {
        const n = Number(c) || 0;
        return Math.max(0, Math.min(100, n)).toFixed(0);
    };
}

// ============================================================================
// HELPER UNIVERSAL PARA FETCH (Spot o Futuros según window.IS_FUTURES_PAGE)
// ============================================================================
// Devuelve la URL correcta para hacer el análisis según si estamos en /futures
// o en la página principal (Spot). Es transparente para el resto del código.
window.buildAnalyzeURL = function(symbol, interval) {
    if (window.IS_FUTURES_PAGE) {
        // Para futuros usamos POST a /api/futures/analyze, pero seguimos
        // exponiendo una URL "GET-like" aquí. El fetch real se hace más abajo.
        return { url: '/api/futures/analyze', method: 'POST', body: { symbol, timeframe: interval } };
    }
    return { url: `/api/analyze?symbol=${symbol}&interval=${interval}`, method: 'GET', body: null };
};

// Wrapper de fetch que hace POST o GET según corresponda
window.fetchAnalyze = async function(symbol, interval) {
    const req = window.buildAnalyzeURL(symbol, interval);
    const opts = {
        method: req.method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (req.method === 'POST' && req.body) {
        opts.body = JSON.stringify(req.body);
    }
    const response = await fetch(req.url, opts);
    return response.json();
};

// ============ INICIALIZACIÓN ============
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM cargado, inicializando sistema...');
    
    const symbolSelect = document.getElementById('symbol-select');
    const intervalSelect = document.getElementById('interval-select');
    
    if (symbolSelect) {
        symbolSelect.addEventListener('change', function() {
            currentSymbol = this.value;
            currentInterval = document.getElementById('interval-select')?.value || '1D';
            runCompleteAnalysis();
        });
    }
    
    if (intervalSelect) {
        intervalSelect.addEventListener('change', function() {
            currentInterval = this.value;
            currentSymbol = document.getElementById('symbol-select')?.value || 'BTC-USDT';
            runCompleteAnalysis();
        });
    }
    
    initializeEventListeners();
    initializeDragAndDrop();
    loadIndicatorOrder();
    loadInitialData();
    
    setInterval(updateBoliviaClock, 1000);
    setInterval(updateCalendarInfo, 60000);
    setInterval(updateSystemStatus, 60000);
});

// ============ EVENT LISTENERS ============
function initializeEventListeners() {
    document.querySelectorAll('.btn-collapse').forEach(btn => {
        btn.addEventListener('click', function() {
            const card = this.closest('.indicator-card');
            const content = card.querySelector('.indicator-content');
            const isCollapsed = this.getAttribute('data-collapsed') === 'true';
            
            if (isCollapsed) {
                content.style.display = 'block';
                this.innerHTML = '<i class="fas fa-minus"></i>';
                this.setAttribute('data-collapsed', 'false');
            } else {
                content.style.display = 'none';
                this.innerHTML = '<i class="fas fa-plus"></i>';
                this.setAttribute('data-collapsed', 'true');
            }
        });
    });
    
    document.querySelectorAll('.btn-move').forEach(btn => {
        btn.addEventListener('click', function() {
            const card = this.closest('.indicator-card');
            const container = document.getElementById('indicators-container');
            const direction = this.getAttribute('data-direction');
            const cards = Array.from(container.children);
            const index = cards.indexOf(card);
            
            if (direction === 'up' && index > 0) {
                container.insertBefore(card, cards[index - 1]);
            } else if (direction === 'down' && index < cards.length - 1) {
                container.insertBefore(cards[index + 1], card);
            }
            saveIndicatorOrder();
        });
    });
    
    document.querySelectorAll('.indicator-control').forEach(control => {
        control.addEventListener('change', function() {
            const indicator = this.id.replace('show-', '');
            toggleIndicator(indicator, this.checked);
        });
    });
}

function initializeDragAndDrop() {
    const container = document.getElementById('indicators-container');
    if (!container) return;
    
    let draggedItem = null;
    
    container.addEventListener('dragstart', (e) => {
        draggedItem = e.target.closest('.indicator-card');
        if (draggedItem) {
            draggedItem.style.opacity = '0.5';
            e.dataTransfer.effectAllowed = 'move';
        }
    });
    
    container.addEventListener('dragend', (e) => {
        if (draggedItem) {
            draggedItem.style.opacity = '';
            draggedItem = null;
        }
    });
    
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    });
    
    container.addEventListener('drop', (e) => {
        e.preventDefault();
        const target = e.target.closest('.indicator-card');
        if (draggedItem && target && draggedItem !== target) {
            container.insertBefore(draggedItem, target.nextSibling);
            saveIndicatorOrder();
        }
    });
}

function saveIndicatorOrder() {
    const container = document.getElementById('indicators-container');
    if (!container) return;
    const cards = Array.from(container.children);
    const order = cards.map(card => card.getAttribute('data-indicator'));
    localStorage.setItem('indicator_order', JSON.stringify(order));
}

function loadIndicatorOrder() {
    const savedOrder = localStorage.getItem('indicator_order');
    if (!savedOrder) return;
    try {
        const order = JSON.parse(savedOrder);
        const container = document.getElementById('indicators-container');
        if (!container) return;
        const cards = Array.from(container.children);
        order.reverse().forEach(indicatorId => {
            const card = cards.find(c => c.getAttribute('data-indicator') === indicatorId);
            if (card) container.insertBefore(card, container.firstChild);
        });
    } catch (e) {
        console.error('Error loading indicator order:', e);
    }
}

function toggleIndicator(indicator, show) {
    const cards = document.querySelectorAll(`.indicator-card[data-indicator="${indicator}"]`);
    cards.forEach(card => {
        card.style.display = show ? 'block' : 'none';
    });
}

// ============ FUNCIONES PRINCIPALES ============
function loadInitialData() {
    console.log('📥 Cargando datos iniciales...');
    
    // Obtener recomendación instantánea
    try {
        getInstantRecommendation();
        console.log('✅ Recomendación instantánea solicitada');
    } catch (e) {
        console.error('❌ Error en getInstantRecommendation:', e);
    }
    
    // Ejecutar análisis completo
    try {
        runCompleteAnalysis();
        console.log('✅ Análisis completo iniciado');
    } catch (e) {
        console.error('❌ Error en runCompleteAnalysis:', e);
    }
    
    // ============ Cargar señales activas (NUEVO) ============
    try {
        if (typeof window.updateActiveSignals === 'function') {
            // Intentar inmediatamente
            window.updateActiveSignals();
            
            // NOTA: el setInterval periódico se define UNA sola vez más abajo
            // (buscar "ACTUALIZAR SEÑALES PERIÓDICAMENTE"). Antes había DOS
            // setIntervals (uno aquí a 120s, otro a 60s) que se solapaban
            // y duplicaban las llamadas al backend.
            
            console.log('✅ Sistema de señales activas inicializado');
        } else {
            console.warn('⚠️ updateActiveSignals no está definida');
        }
    } catch (e) {
        console.error('❌ Error en updateActiveSignals:', e);
    }
    
    // ============ Inicializar correlación con datos mock (para pruebas) ============
    setTimeout(function() {
        try {
            const mockData = {
                correlation: {
                    btc_analysis: { decision: { action: 'Cargando...' } },
                    paxg_btc_analysis: { decision: { action: 'Cargando...' } },
                    rotation_signal: 'NEUTRAL',
                    weight_modifier: 1.0
                }
            };
            if (typeof window.updateCorrelationInfo === 'function') {
                window.updateCorrelationInfo(mockData);
                console.log('✅ Correlación inicializada con mock');
            } else {
                console.warn('⚠️ updateCorrelationInfo no está definida');
            }
        } catch (e) {
            console.error('❌ Error inicializando correlación:', e);
        }
    }, 100);
    
    // ============ Inicializar gráfico Fear & Greed con datos mock ============
    setTimeout(function() {
        try {
            if (typeof window.updateFearGreedChart === 'function') {
                // Crear datos mock para que el gráfico no se vea vacío
                const mockSentiment = {
                    sentiment: {
                        available: true,
                        current_value: 50,
                        classification: 'Neutral',
                        trend_7d_pct: 0,
                        trend_30d_pct: 0,
                        historical: [
                            // Generar 30 días de datos históricos simulados
                            ...Array.from({ length: 30 }, (_, i) => {
                                const date = new Date();
                                date.setDate(date.getDate() - (29 - i));
                                return {
                                    date: date.toISOString().split('T')[0],
                                    value: 45 + Math.floor(Math.random() * 15)
                                };
                            })
                        ]
                    },
                    timeframe: '1D'
                };
                window.updateFearGreedChart(mockSentiment);
                console.log('✅ Fear & Greed inicializado con mock');
            } else {
                console.warn('⚠️ updateFearGreedChart no está definida');
            }
        } catch (e) {
            console.error('❌ Error inicializando Fear & Greed:', e);
        }
    }, 500);
    
    // ============ Heartbeat para verificar que todo funciona ============
    setTimeout(function() {
        console.log('💓 Sistema inicializado correctamente');
    }, 3000);
}

// ============ FUNCIÓN PRINCIPAL - ANÁLISIS COMPLETO CON VISTA GLOBAL ============
window.runCompleteAnalysis = function() {
    const cfg = window.PAGE_CONFIG || { defaultSymbol: 'BTC-USDT', defaultTimeframe: '1D' };
    const symbol = document.getElementById('symbol-select')?.value || cfg.defaultSymbol;
    const interval = document.getElementById('interval-select')?.value || cfg.defaultTimeframe;
    
    window.currentSymbol = symbol;
    window.currentInterval = interval;
    
    window.showToast('🔍 Iniciando análisis completo...', 'info');
    
    // Usar el wrapper universal (Spot o Futuros según window.IS_FUTURES_PAGE)
    const req = window.buildAnalyzeURL(symbol, interval);
    const fetchOpts = req.method === 'POST' 
        ? { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(req.body) }
        : { method: 'GET' };
    
    fetch(req.url, fetchOpts)
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => {
                    throw new Error(err.error || `Error HTTP ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.data) {
                window.currentAnalysis = data.data;
                
                // ============ ACTUALIZAR TODOS LOS GRÁFICOS (SOLO CON PAR ACTUAL) ============
                if (typeof window.updateAllCharts === 'function') {
                    window.updateAllCharts(data.data);
                }
                
                if (typeof window.updateCandleChart === 'function') {
                    window.updateCandleChart(data.data);
                }
                
                if (typeof window.updatePattern4Chart === 'function') {
                    window.updatePattern4Chart(data.data);
                }
                if (typeof window.updateFormation40Chart === 'function') {
                    window.updateFormation40Chart(data.data);
                }
                if (typeof window.updateRecentPatternsList === 'function') {
                    window.updateRecentPatternsList(data.data);
                }
                
                if (typeof window.updateRecommendation === 'function') {
                    window.updateRecommendation(data.data);
                }
                if (typeof window.updateAnalysisSummary === 'function') {
                    window.updateAnalysisSummary(data.data);
                }
                if (typeof window.updateConfirmedSignals === 'function') {
                    window.updateConfirmedSignals(data.data);
                }
                if (typeof window.updateMarketAlerts === 'function') {
                    window.updateMarketAlerts(data.data);
                }
                if (typeof window.updateInstantRecommendation === 'function') {
                    window.updateInstantRecommendation(data.data);
                }
                
                // Actualizar precio en vivo
                const price = data.data.current_price || 0;
                const livePriceEl = document.getElementById('live-price');
                if (livePriceEl) {
                    livePriceEl.textContent = `$${price.toFixed(2)}`;
                }
                
                const chartTitle = document.getElementById('chart-title');
                if (chartTitle) {
                    const symbolName = symbol.replace('-', '/');
                    const intervalName = window.getIntervalName ? 
                        window.getIntervalName(interval) : interval;
                    chartTitle.innerHTML = `${symbolName} ${intervalName} - <span id="live-price" class="live-price">$${price.toFixed(2)}</span>`;
                }
                
                // ============ ACTUALIZAR CONVICCIÓN (SOLO PAR ACTUAL) ============
                if (typeof window.updateConvictionInfo === 'function') {
                    window.updateConvictionInfo(data.data);
                }
                
                // ============ AHORA OBTENER LOS DATOS DE LOS OTROS DOS PARES SOLO PARA CORRELACIÓN ============
                console.log('📡 Obteniendo datos de los otros pares para vista global de correlación...');
                
                // Determinar qué otros pares necesitamos
                const otrosPares = [];
                if (symbol !== 'BTC-USDT') otrosPares.push('BTC-USDT');
                if (symbol !== 'PAXG-USDT') otrosPares.push('PAXG-USDT');
                if (symbol !== 'PAXG-BTC') otrosPares.push('PAXG-BTC');
                
                // Si no hay otros pares (imposible porque hay 3), igual actualizar con lo que tenemos
                if (otrosPares.length === 0) {
                    // Construir correlación solo con el par actual
                    const correlationSolo = {
                        correlation: {
                            btc_analysis: symbol === 'BTC-USDT' ? {
                                decision: { action: data.data.decision?.action || 'N/A', confidence: data.data.decision?.confidence || 0 },
                                trend: {
                                    direction: data.data.trend?.direction || 'neutral',
                                    adx: data.data.trend?.adx || 0,
                                    plus_di: data.data.trend?.plus_di || 0,
                                    minus_di: data.data.trend?.minus_di || 0
                                }
                            } : null,
                            paxg_analysis: symbol === 'PAXG-USDT' ? {
                                trend: {
                                    direction: data.data.trend?.direction || 'neutral',
                                    adx: data.data.trend?.adx || 0
                                }
                            } : null,
                            paxg_btc_analysis: symbol === 'PAXG-BTC' ? {
                                decision: { action: data.data.decision?.action || 'N/A', confidence: data.data.decision?.confidence || 0 },
                                trend: {
                                    direction: data.data.trend?.direction || 'neutral',
                                    adx: data.data.trend?.adx || 0
                                }
                            } : null,
                            rotation_signal: data.data.correlation?.rotation_signal || 'NEUTRAL',
                            weight_modifier: data.data.correlation?.weight_modifier || 1.0
                        },
                        symbol: symbol,
                        timeframe: interval
                    };
                    
                    if (typeof window.updateCorrelationInfo === 'function') {
                        window.updateCorrelationInfo(correlationSolo);
                    }
                    
                    window.showToast('✅ Análisis completado', 'success');
                    return;
                }
                
                // Hacer fetch en paralelo para los otros pares
                const promesas = otrosPares.map(par => 
                    fetch(`/api/analyze?symbol=${par}&interval=${interval}`)
                        .then(res => res.json())
                        .then(res => {
                            if (res.success && res.data) {
                                return { par, data: res.data };
                            }
                            return { par, data: null };
                        })
                        .catch(err => {
                            console.error(`Error obteniendo ${par}:`, err);
                            return { par, data: null };
                        })
                );
                
                Promise.all(promesas).then(resultadosOtros => {
                    // Construir objeto con datos de los 3 pares (SOLO LOS QUE TENEMOS)
                    const datosGlobales = {
                        // Datos del par actual (SIEMPRE existen)
                        [symbol]: data.data,
                    };
                    
                    // Agregar los otros pares SOLO si tenemos datos reales
                    resultadosOtros.forEach(item => {
                        if (item.data) {
                            datosGlobales[item.par] = item.data;
                        }
                    });
                    
                    // Construir estructura de correlación global SOLO con datos reales
                    const correlationGlobal = {
                        correlation: {
                            btc_analysis: datosGlobales['BTC-USDT'] ? {
                                decision: { 
                                    action: datosGlobales['BTC-USDT'].decision?.action || 'N/A', 
                                    confidence: datosGlobales['BTC-USDT'].decision?.confidence || 0 
                                },
                                trend: {
                                    direction: datosGlobales['BTC-USDT'].trend?.direction || 'neutral',
                                    adx: datosGlobales['BTC-USDT'].trend?.adx || 0,
                                    plus_di: datosGlobales['BTC-USDT'].trend?.plus_di || 0,
                                    minus_di: datosGlobales['BTC-USDT'].trend?.minus_di || 0,
                                    confidence: datosGlobales['BTC-USDT'].trend?.confidence || 50
                                }
                            } : null,  // ← null en lugar de objeto vacío
                            
                            paxg_analysis: datosGlobales['PAXG-USDT'] ? {
                                trend: {
                                    direction: datosGlobales['PAXG-USDT'].trend?.direction || 'neutral',
                                    adx: datosGlobales['PAXG-USDT'].trend?.adx || 0,
                                    plus_di: datosGlobales['PAXG-USDT'].trend?.plus_di || 0,
                                    minus_di: datosGlobales['PAXG-USDT'].trend?.minus_di || 0,
                                    confidence: datosGlobales['PAXG-USDT'].trend?.confidence || 50
                                }
                            } : null,
                            
                            paxg_btc_analysis: datosGlobales['PAXG-BTC'] ? {
                                decision: { 
                                    action: datosGlobales['PAXG-BTC'].decision?.action || 'N/A', 
                                    confidence: datosGlobales['PAXG-BTC'].decision?.confidence || 0 
                                },
                                trend: {
                                    direction: datosGlobales['PAXG-BTC'].trend?.direction || 'neutral',
                                    adx: datosGlobales['PAXG-BTC'].trend?.adx || 0,
                                    plus_di: datosGlobales['PAXG-BTC'].trend?.plus_di || 0,
                                    minus_di: datosGlobales['PAXG-BTC'].trend?.minus_di || 0,
                                    confidence: datosGlobales['PAXG-BTC'].trend?.confidence || 50
                                }
                            } : null,
                            
                            rotation_signal: data.data.correlation?.rotation_signal || 'NEUTRAL',
                            weight_modifier: data.data.correlation?.weight_modifier || 1.0
                        },
                        symbol: symbol,
                        timeframe: interval
                    };
                    
                    // Actualizar SOLO la correlación con los datos globales
                    if (typeof window.updateCorrelationInfo === 'function') {
                        window.updateCorrelationInfo(correlationGlobal);
                    }
                    
                    console.log('✅ Vista global de correlación actualizada con datos reales');
                });
                
                window.showToast('✅ Análisis completado', 'success');
                
            } else {
                window.showToast('❌ Error: ' + (data.error || 'Error desconocido'), 'danger');
            }
        })
        .catch(error => {
            console.error('Error en análisis:', error);
            window.showToast('❌ Error de conexión con el servidor', 'danger');
        });
};

function getInstantRecommendation() {
    const symbol = document.getElementById('symbol-select')?.value || 'BTC-USDT';
    const interval = document.getElementById('interval-select')?.value || '1D';
    
    fetch(`/api/analyze?symbol=${symbol}&interval=${interval}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data) {
                updateInstantRecommendation(data.data);
            }
        })
        .catch(error => console.error('Error:', error));
}

function generateMockAnalysis(symbol, interval) {
    const price = symbol === 'BTC-USDT' ? 50000 + Math.random() * 1000 : 
                 symbol === 'PAXG-USDT' ? 2000 + Math.random() * 50 : 0.04 + Math.random() * 0.002;
    
    const intervalNames = {'4h': '4H', '12h': '12H', '1D': '1D', '1W': '1W'};
    
    return {
        symbol: symbol,
        timeframe: interval,
        decision: {
            action: Math.random() > 0.5 ? 'COMPRA_SPOT' : 'NO_OPERAR',
            confidence: 65 + Math.floor(Math.random() * 20)
        },
        levels: {
            entry: price * (0.995 + Math.random() * 0.01),
            stop_loss: price * (0.98 + Math.random() * 0.01),
            take_profit: price * (1.03 + Math.random() * 0.02),
            leverage: 10,
            risk_reward: 2.5
        },
        current_price: price,
        message: `🔍 Análisis de ${symbol} en ${intervalNames[interval] || interval}`,
        df: generateMockData(100, price),
        trend: {
            direction: Math.random() > 0.5 ? 'bullish' : 'bearish',
            strength: 'normal',
            adx_value: 25 + Math.random() * 10
        },
        momentum: {
            score: Math.random() > 0.5 ? 8 : -5,
            indicators: {rsi: 55 + Math.random() * 20}
        },
        volatility: {
            volatility_level: 'medium',
            atr_pct: 1.5 + Math.random(),
            operability: true,
            ftm_zone: Math.random() > 0.7 ? 'STRONG_UP' : 'NEUTRAL'
        },
        volume: {
            volume_ratio: 1.2 + Math.random() * 0.8,
            volume_participation: 'normal',
            whale_buy: Math.random() > 0.8,
            whale_sell: Math.random() > 0.8
        },
        structure: {
            supports: [price * 0.97, price * 0.95],
            resistances: [price * 1.03, price * 1.05],
            nearest_support: price * 0.97,
            nearest_resistance: price * 1.03,
            fib_levels: {
                '0.236': price * 0.976,
                '0.382': price * 0.962,
                '0.5': price * 0.95,
                '0.618': price * 0.938,
                '0.786': price * 0.921
            },
            fib_extensions: {
                '1.272': price * 1.136,
                '1.618': price * 1.19
            },
            patterns: {count: 2, recent_patterns: []}
        }
    };
}

function generateMockData(n, basePrice) {
    const dates = [];
    const open = [];
    const high = [];
    const low = [];
    const close = [];
    const volume = [];
    
    let now = new Date();
    for (let i = 0; i < n; i++) {
        let date = new Date(now - (n - i) * 3600000);
        dates.push(date.toISOString());
        
        let change = (Math.random() - 0.5) * basePrice * 0.02;
        let c = basePrice + change * (i / 10);
        let o = i === 0 ? c : close[i-1];
        let h = Math.max(o, c) * (1 + Math.random() * 0.01);
        let l = Math.min(o, c) * (1 - Math.random() * 0.01);
        
        open.push(o);
        close.push(c);
        high.push(h);
        low.push(l);
        volume.push(Math.random() * 10000 + 5000);
    }
    
    return {time: dates, open, high, low, close, volume};
}

// ============ GRÁFICO PRINCIPAL - VELAS + EMAs + Soportes/Resistencias ============
function updateCandleChart(data) {
    const chartDiv = document.getElementById('candle-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const open = df.open || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length === 0) return;
    
    const symbolName = data.symbol?.replace('-', '/') || 'BTC/USDT';
    const intervalName = getIntervalName(data.timeframe || '1D');
    
    const closePrices = close.map(Number);
    const ema9 = calculateEMA(closePrices, 9);
    const ema21 = calculateEMA(closePrices, 21);
    const ema50 = calculateEMA(closePrices, 50);
    const ema200 = calculateEMA(closePrices, 200);
    
    const traces = [];
    
    traces.push({
        x: dates,
        open: open,
        high: high,
        low: low,
        close: close,
        type: 'candlestick',
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1.5}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1.5}, fillcolor: '#FF5B5B'},
        showlegend: true,
        yaxis: 'y'
    });
    
    traces.push({
        x: dates,
        y: ema9,
        type: 'scatter',
        mode: 'lines',
        name: 'EMA 9',
        line: {color: '#3A8BFF', width: 1.5},
        yaxis: 'y'
    });
    
    traces.push({
        x: dates,
        y: ema21,
        type: 'scatter',
        mode: 'lines',
        name: 'EMA 21',
        line: {color: '#FFD700', width: 1.5},
        yaxis: 'y'
    });
    
    traces.push({
        x: dates,
        y: ema50,
        type: 'scatter',
        mode: 'lines',
        name: 'EMA 50',
        line: {color: '#FF8C00', width: 1.5},
        yaxis: 'y'
    });
    
    traces.push({
        x: dates,
        y: ema200,
        type: 'scatter',
        mode: 'lines',
        name: 'EMA 200',
        line: {color: '#FF69B4', width: 1.5},
        yaxis: 'y'
    });
    
    if (data.structure) {
        if (data.structure.supports && data.structure.supports.length > 0) {
            data.structure.supports.slice(0, 2).forEach((support, idx) => {
                if (support && support > 0) {
                    traces.push({
                        x: [dates[0], dates[dates.length - 1]],
                        y: [support, support],
                        type: 'scatter',
                        mode: 'lines',
                        name: idx === 0 ? 'Soporte 1' : 'Soporte 2',
                        line: {color: '#00C076', width: 1.5, dash: 'dash'},
                        yaxis: 'y'
                    });
                }
            });
        }
        
        if (data.structure.resistances && data.structure.resistances.length > 0) {
            data.structure.resistances.slice(0, 2).forEach((resistance, idx) => {
                if (resistance && resistance > 0) {
                    traces.push({
                        x: [dates[0], dates[dates.length - 1]],
                        y: [resistance, resistance],
                        type: 'scatter',
                        mode: 'lines',
                        name: idx === 0 ? 'Resistencia 1' : 'Resistencia 2',
                        line: {color: '#FF5B5B', width: 1.5, dash: 'dash'},
                        yaxis: 'y'
                    });
                }
            });
        }
        
        if (data.structure.nearest_support && data.structure.nearest_support > 0) {
            traces.push({
                x: [dates[0], dates[dates.length - 1]],
                y: [data.structure.nearest_support, data.structure.nearest_support],
                type: 'scatter',
                mode: 'lines',
                name: 'Soporte Inmediato',
                line: {color: '#00C076', width: 2, dash: 'solid'},
                yaxis: 'y'
            });
        }
        
        if (data.structure.nearest_resistance && data.structure.nearest_resistance > 0) {
            traces.push({
                x: [dates[0], dates[dates.length - 1]],
                y: [data.structure.nearest_resistance, data.structure.nearest_resistance],
                type: 'scatter',
                mode: 'lines',
                name: 'Resistencia Inmediata',
                line: {color: '#FF5B5B', width: 2, dash: 'solid'},
                yaxis: 'y'
            });
        }
    }
    
    if (data.levels && data.levels.entry && data.levels.entry > 0) {
        traces.push({
            x: [dates[dates.length - 2], dates[dates.length - 1]],
            y: [data.levels.entry, data.levels.entry],
            type: 'scatter',
            mode: 'lines+markers',
            name: 'ENTRADA',
            line: {color: '#8A63D2', width: 3, dash: 'solid'},
            marker: {symbol: 'star', size: 12, color: '#8A63D2'},
            yaxis: 'y'
        });
    }
    
    const layout = {
        title: {
            text: `${symbolName} ${intervalName}`,  // ← SOLO PAR Y TEMPORALIDAD
            font: {size: 18, color: 'white', family: 'Arial Black'},
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            zerolinecolor: 'rgba(128,128,128,0.5)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false},
            title: {
                text: 'Fecha/Hora',
                font: {color: 'white', size: 12},
                standoff: 20  // ← Espacio para la leyenda
            }
        },
        yaxis: {
            title: 'Precio (USDT)',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            zerolinecolor: 'rgba(128,128,128,0.5)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true,
            titlefont: {color: 'white', size: 12}
        },
        template: 'plotly_dark',
        height: 500,
        margin: {l: 50, r: 50, t: 60, b: 80},  // ← MÁS ESPACIO ABAJO PARA LEYENDA
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'top',
            y: -0.2,  // ← DEBAJO DEL GRÁFICO
            xanchor: 'center',
            x: 0.5,
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        }
    };
    
    Plotly.newPlot('candle-chart', traces, layout, {responsive: true, displaylogo: false});
}
// ============ FAIR VALUE GAPS + ORDER BLOCKS + LIQUIDITY SWEEPS + STOP HUNTS ============
function updateFVGAOBChart(data) {
    console.log('🟣🟣🟣 EJECUTANDO updateFVGAOBChart');
    
    const chartDiv = document.getElementById('fvg-ob-chart');
    if (!chartDiv) {
        console.log('❌ No se encontró el div fvg-ob-chart');
        return;
    }
    
    // Limpiar gráfico anterior
    Plotly.purge('fvg-ob-chart');
    chartDiv.innerHTML = '';
    
    if (!data || !data.df) {
        console.log('❌ No hay datos de df');
        chartDiv.innerHTML = '<div class="alert alert-warning text-center">No hay datos disponibles</div>';
        return;
    }
    
    if (!data.structure) {
        console.log('❌ No hay estructura en los datos');
        chartDiv.innerHTML = '<div class="alert alert-warning text-center">No hay datos de estructura</div>';
        return;
    }
    
    console.log('📊 Estructura recibida:', data.structure);
    
    // ============ DEBUG: Verificar qué datos llegan ============
    console.log('🔍 DEBUG - Revisando estructura:');
    console.log('   - keys disponibles:', Object.keys(data.structure));
    
    const df = data.df;
    const dates = df.time || [];
    const open = df.open || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 10) {
        console.log('❌ Menos de 10 velas');
        return;
    }
    
    // ============ EXTRAER FVGs Y ORDER BLOCKS ============
    let fvgList = [];
    let orderBlocks = [];
    let liquiditySweeps = [];
    let stopHunts = [];
    
    // Buscar FVGs en diferentes posibles ubicaciones
    if (data.structure.fair_value_gaps) {
        fvgList = data.structure.fair_value_gaps;
        console.log(`🎯 FVG encontrados en fair_value_gaps: ${fvgList.length}`);
    } else if (data.structure.fvg) {
        fvgList = data.structure.fvg;
        console.log(`🎯 FVG encontrados en fvg: ${fvgList.length}`);
    } else {
        console.log('⚠️ NO HAY FVG en la estructura recibida');
    }
    
    // Mostrar primer FVG si existe para debug
    if (fvgList.length > 0) {
        console.log('   - Primer FVG:', fvgList[0]);
    }
    
    if (data.structure.order_blocks) {
        orderBlocks = data.structure.order_blocks;
        console.log(`🎯 Order Blocks encontrados: ${orderBlocks.length}`);
    }
    
    if (data.structure.liquidity_sweeps) {
        liquiditySweeps = data.structure.liquidity_sweeps;
        console.log(`🎯 Liquidity Sweeps encontrados: ${liquiditySweeps.length}`);
    }
    
    if (data.structure.stop_hunts) {
        stopHunts = data.structure.stop_hunts;
        console.log(`🎯 Stop Hunts encontrados: ${stopHunts.length}`);
    }
    
    // Actualizar interpretación
    const interpretation = document.getElementById('fvg-ob-interpretation');
    if (interpretation) {
        const fvgCount = fvgList.length;
        const obCount = orderBlocks.length;
        const sweepCount = liquiditySweeps.length;
        const huntCount = stopHunts.length;
        
        interpretation.innerHTML = `
            <span style="color: #00C076;">🟢 FVG Alcista</span> | 
            <span style="color: #FF5B5B;">🔴 FVG Bajista</span> | 
            <span style="color: #8A63D2;">🟣 Order Block</span><br>
            <span style="color: #00C076;">▲ SH</span> / 
            <span style="color: #FF5B5B;">▼ SH</span> (Stop Hunt) | 
            <span style="color: #00C076;">▲ SW</span> / 
            <span style="color: #FF5B5B;">▼ SW</span> (Sweep)<br>
            <strong>${fvgCount} FVG | ${obCount} OB | ${sweepCount} Sweeps | ${huntCount} Hunts</strong>
        `;
    }
    
    // Convertir fechas a objetos Date
    const dateObjects = dates.map(d => new Date(d));
    const lastDates = dateObjects.slice(-60);
    const lastOpen = open.slice(-60);
    const lastHigh = high.slice(-60);
    const lastLow = low.slice(-60);
    const lastClose = close.slice(-60);
    
    console.log(`📊 Mostrando últimas ${lastDates.length} velas`);
    
    const traces = [];
    const shapes = [];
    const annotations = [];
    
    // Traza principal: Velas Japonesas
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1.5}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1.5}, fillcolor: '#FF5B5B'},
        showlegend: true,
        yaxis: 'y'
    });
    
    // ============ AÑADIR FAIR VALUE GAPS ============
    fvgList.forEach((fvg, idx) => {
        // Asegurar que tiene los campos necesarios
        const gapBottom = fvg.gap_bottom || fvg.gapBottom || 0;
        const gapTop = fvg.gap_top || fvg.gapTop || 0;
        const fvgType = fvg.type || 'unknown';
        const fvgFilled = fvg.filled || false;
        const fvgIndex = fvg.index || 0;
        
        if (gapBottom === 0 || gapTop === 0 || gapTop <= gapBottom) return;
        
        const totalCandles = dates.length;
        const startIndex = Math.max(0, totalCandles - 60);
        const relativeIndex = fvgIndex - startIndex;
        
        let gapDate;
        if (relativeIndex >= 0 && relativeIndex < lastDates.length) {
            gapDate = lastDates[relativeIndex];
        } else {
            gapDate = lastDates[lastDates.length - 1];
        }
        
        const timeRange = lastDates[lastDates.length - 1].getTime() - lastDates[0].getTime();
        const boxWidth = timeRange * 0.2;
        
        let color, fillColor, lineStyle;
        
        if (fvgType.includes('bullish')) {
            if (fvgFilled) {
                color = '#808080';
                fillColor = 'rgba(128,128,128,0.1)';
                lineStyle = 'dot';
            } else {
                color = '#00C076';
                fillColor = 'rgba(0,192,118,0.15)';
                lineStyle = 'solid';
            }
        } else {
            if (fvgFilled) {
                color = '#808080';
                fillColor = 'rgba(128,128,128,0.1)';
                lineStyle = 'dot';
            } else {
                color = '#FF5B5B';
                fillColor = 'rgba(255,91,91,0.15)';
                lineStyle = 'solid';
            }
        }
        
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: new Date(gapDate.getTime() - boxWidth / 2),
            x1: new Date(gapDate.getTime() + boxWidth / 2),
            y0: gapBottom,
            y1: gapTop,
            fillcolor: fillColor,
            line: { color: color, width: 1.5, dash: lineStyle },
            layer: 'below'
        });
        
        const label = fvgFilled ? 'FVG' : 'FVG';
        traces.push({
            x: [gapDate],
            y: [(gapBottom + gapTop) / 2],
            type: 'scatter',
            mode: 'text',
            text: [label],
            textposition: 'middle right',
            textfont: { color: color, size: 8, family: 'Arial' },
            showlegend: false,
            hoverinfo: 'text',
            hovertext: [`${fvgType} FVG`],
            yaxis: 'y'
        });
    });
    
    // ============ AÑADIR ORDER BLOCKS ============
    orderBlocks.forEach((ob, idx) => {
        const priceRange = ob.price_range || ob.priceRange || [];
        if (priceRange.length < 2 || priceRange[0] === 0 || priceRange[1] === 0) return;
        
        const obIndex = ob.index || 0;
        const totalCandles = dates.length;
        const startIndex = Math.max(0, totalCandles - 60);
        const relativeIndex = obIndex - startIndex;
        
        let obDate;
        if (relativeIndex >= 0 && relativeIndex < lastDates.length) {
            obDate = lastDates[relativeIndex];
        } else {
            obDate = lastDates[lastDates.length - 1];
        }
        
        const timeRange = lastDates[lastDates.length - 1].getTime() - lastDates[0].getTime();
        const boxWidth = timeRange * 0.25;
        
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: new Date(obDate.getTime() - boxWidth / 2),
            x1: new Date(obDate.getTime() + boxWidth / 2),
            y0: priceRange[0],
            y1: priceRange[1],
            fillcolor: 'rgba(138,99,210,0.2)',
            line: { color: '#8A63D2', width: 1.5, dash: 'solid' },
            layer: 'below'
        });
        
        traces.push({
            x: [obDate],
            y: [(priceRange[0] + priceRange[1]) / 2],
            type: 'scatter',
            mode: 'text',
            text: ['OB'],
            textposition: 'middle right',
            textfont: { color: '#8A63D2', size: 8, family: 'Arial' },
            showlegend: false,
            hoverinfo: 'text',
            hovertext: [`Order Block ${ob.type}`],
            yaxis: 'y'
        });
    });
    
    // ============ AÑADIR LIQUIDITY SWEEPS ============
    liquiditySweeps.forEach((sweep, idx) => {
        const sweepIndex = sweep.index || 0;
        const totalCandles = dates.length;
        const startIndex = Math.max(0, totalCandles - 60);
        const relativeIndex = sweepIndex - startIndex;
        
        let sweepDate;
        if (relativeIndex >= 0 && relativeIndex < lastDates.length) {
            sweepDate = lastDates[relativeIndex];
        } else {
            sweepDate = lastDates[lastDates.length - 1];
        }
        
        const sweepLevel = sweep.sweep_level || sweep.level || 0;
        const sweepType = sweep.type || 'unknown';
        
        const color = sweepType === 'bullish' ? '#00C076' : '#FF5B5B';
        const symbol = sweepType === 'bullish' ? '▲' : '▼';
        
        shapes.push({
            type: 'line',
            x0: new Date(sweepDate.getTime() - 24*3600000),
            x1: new Date(sweepDate.getTime() + 24*3600000),
            y0: sweepLevel,
            y1: sweepLevel,
            line: { color: color, width: 1.5, dash: 'dash' },
            layer: 'below'
        });
        
        annotations.push({
            x: sweepDate,
            y: sweepLevel,
            xref: 'x',
            yref: 'y',
            text: `SW${symbol}`,
            showarrow: true,
            arrowhead: 2,
            arrowsize: 1,
            arrowwidth: 2,
            arrowcolor: color,
            font: { color: 'white', size: 8, family: 'Arial Black' },
            bgcolor: color,
            bordercolor: 'white',
            borderwidth: 1,
            borderpad: 2
        });
    });
    
    // ============ AÑADIR STOP HUNTS ============
    stopHunts.forEach((hunt, idx) => {
        const huntIndex = hunt.index || 0;
        const totalCandles = dates.length;
        const startIndex = Math.max(0, totalCandles - 60);
        const relativeIndex = huntIndex - startIndex;
        
        let huntDate;
        if (relativeIndex >= 0 && relativeIndex < lastDates.length) {
            huntDate = lastDates[relativeIndex];
        } else {
            huntDate = lastDates[lastDates.length - 1];
        }
        
        const huntLevel = hunt.level || 0;
        const huntType = hunt.type || 'unknown';
        
        const color = huntType === 'bullish' ? '#00C076' : '#FF5B5B';
        const symbol = huntType === 'bullish' ? '▲' : '▼';
        
        annotations.push({
            x: huntDate,
            y: huntLevel,
            xref: 'x',
            yref: 'y',
            text: `SH${symbol}`,
            showarrow: true,
            arrowhead: 2,
            arrowsize: 1,
            arrowwidth: 2,
            arrowcolor: color,
            font: { color: 'white', size: 8, weight: 'bold', family: 'Arial Black' },
            bgcolor: color,
            bordercolor: 'white',
            borderwidth: 1,
            borderpad: 2
        });
    });
    
    const layout = {
        title: { text: 'Fair Value Gaps (Imbalances) + Order Blocks', font: {color: 'white', size: 14} },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false}
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 60, b: 50},
        showlegend: true,
        legend: { 
            orientation: 'h', 
            yanchor: 'bottom', 
            y: 1.02, 
            xanchor: 'right', 
            x: 1, 
            font: {color: 'white', size: 9} 
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: { 
            bgcolor: '#0A0C10', 
            bordercolor: 'rgba(255,255,255,0.2)', 
            font: {color: 'white', size: 11} 
        },
        shapes: shapes,
        annotations: annotations
    };
    
    try {
        Plotly.newPlot('fvg-ob-chart', traces, layout, {responsive: true, displaylogo: false});
        console.log(`✅ Gráfico actualizado con ${fvgList.length} FVG, ${orderBlocks.length} OB, ${liquiditySweeps.length} Sweeps, ${stopHunts.length} Hunts`);
    } catch (error) {
        console.error('❌ Error al crear gráfico:', error);
        chartDiv.innerHTML = '<div class="alert alert-danger">Error al generar gráfico</div>';
    }
}
// ============ GRÁFICO DE FIBONACCI CON VELAS - VERSIÓN ORIGINAL ============
function updateFibonacciChart(data) {
    const chartDiv = document.getElementById('fibonacci-chart');
    if (!chartDiv) {
        const container = document.querySelector('.col-lg-8');
        if (container) {
            const fibCard = document.createElement('div');
            fibCard.className = 'card bg-dark border-secondary mb-4';
            fibCard.innerHTML = `
                <div class="card-header">
                    <h5 class="mb-0" style="color: white;">Niveles de Fibonacci con Velas</h5>
                </div>
                <div class="card-body">
                    <div id="fibonacci-chart" style="height: 350px;"></div>
                    <div class="mt-2">
                        <small class="text-muted">
                            <strong>Interpretación:</strong> Niveles clave de soporte/resistencia basados en Fibonacci.
                            <span id="fibonacci-interpretation" style="color: #FFD700;">Calculando...</span>
                        </small>
                    </div>
                </div>
            `;
            container.appendChild(fibCard);
        } else {
            return;
        }
    }
    
    if (!data || !data.df || !data.structure) return;
    
    const df = data.df;
    const dates = df.time || [];
    const open = df.open || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 30) return;
    
    // Convertir fechas a objetos Date
    const dateObjects = dates.map(d => new Date(d));
    const lastDates = dateObjects.slice(-30);
    const lastOpen = open.slice(-30);
    const lastHigh = high.slice(-30);
    const lastLow = low.slice(-30);
    const lastClose = close.slice(-30);
    
    const fibLevels = data.structure.fib_levels || {};
    const fibExtensions = data.structure.fib_extensions || {};
    
    const traces = [];
    
    // Velas Japonesas
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1}, fillcolor: '#FF5B5B'},
        showlegend: true,
        yaxis: 'y'
    });
    
    // Líneas de Fibonacci con etiquetas de precio
    const fibLines = [
        {level: '0.236', color: '#FFD700', name: '23.6%'},
        {level: '0.382', color: '#FF8C00', name: '38.2%'},
        {level: '0.5', color: '#FF69B4', name: '50%'},
        {level: '0.618', color: '#00C076', name: '61.8%'},
        {level: '0.786', color: '#3A8BFF', name: '78.6%'},
        {level: '1.272', color: '#8A63D2', name: '127.2%'},
        {level: '1.618', color: '#FF5B5B', name: '161.8%'}
    ];
    
    fibLines.forEach(fib => {
        let price = null;
        if (fib.level.startsWith('1')) {
            price = fibExtensions[fib.level];
        } else {
            price = fibLevels[fib.level];
        }
        
        if (price && price > 0) {
            // Línea horizontal de Fibonacci
            traces.push({
                x: [lastDates[0], lastDates[lastDates.length - 1]],
                y: [price, price],
                type: 'scatter',
                mode: 'lines',
                name: `${fib.name}`,
                line: {
                    color: fib.color,
                    width: 1.5,
                    dash: 'dash'
                },
                opacity: 0.8,
                showlegend: true,
                yaxis: 'y'
            });
            
            // Etiqueta de precio al final de la línea
            traces.push({
                x: [lastDates[lastDates.length - 1]],
                y: [price],
                type: 'scatter',
                mode: 'text',
                text: [`$${price.toFixed(2)}`],
                textposition: 'middle right',
                textfont: {
                    color: fib.color,
                    size: 10,
                    family: 'Arial',
                    weight: 'bold'
                },
                showlegend: false,
                hoverinfo: 'none',
                yaxis: 'y'
            });
        }
    });
    
    // Línea del precio actual
    if (data.current_price) {
        traces.push({
            x: [lastDates[0], lastDates[lastDates.length - 1]],
            y: [data.current_price, data.current_price],
            type: 'scatter',
            mode: 'lines',
            name: 'Precio Actual',
            line: {
                color: 'white',
                width: 1.5,
                dash: 'solid'
            },
            opacity: 0.9,
            showlegend: true,
            yaxis: 'y'
        });
        
        // Etiqueta del precio actual
        traces.push({
            x: [lastDates[lastDates.length - 1]],
            y: [data.current_price],
            type: 'scatter',
            mode: 'text',
            text: [`$${data.current_price.toFixed(2)}`],
            textposition: 'middle right',
            textfont: {
                color: 'white',
                size: 11,
                family: 'Arial',
                weight: 'bold'
            },
            showlegend: false,
            hoverinfo: 'none',
            yaxis: 'y'
        });
    }
    
    const layout = {
        title: {
            text: 'Niveles de Fibonacci con Velas',
            font: {
                color: 'white',
                size: 14,
                family: 'Arial'
            },
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            range: [lastDates[0], lastDates[lastDates.length - 1]],
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false},
            title: {
                text: 'Fecha/Hora',
                font: {color: 'white', size: 11},
                standoff: 20
            }
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true,
            titlefont: {
                color: 'white',
                size: 12
            }
        },
        template: 'plotly_dark',
        height: 350,
        margin: {
            l: 60,
            r: 80,
            t: 50,
            b: 80  // Más espacio abajo para la leyenda
        },
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'top',
            y: -0.2,  // Debajo del gráfico
            xanchor: 'center',
            x: 0.5,
            font: {
                color: 'white',
                size: 8,
                family: 'Arial'
            },
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {
                color: 'white',
                size: 11,
                family: 'Arial'
            }
        }
    };
    
    Plotly.newPlot('fibonacci-chart', traces, layout, {
        responsive: true,
        displaylogo: false,
        displayModeBar: true,
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d']
    });
    
    const interpretation = document.getElementById('fibonacci-interpretation');
    if (interpretation && data.current_price) {
        const currentPrice = data.current_price;
        let nearestFib = '';
        let minDiff = Infinity;
        let nearestPrice = 0;
        
        // Buscar el nivel Fibonacci más cercano
        Object.entries(fibLevels).forEach(([level, price]) => {
            const diff = Math.abs(price - currentPrice);
            if (diff < minDiff) {
                minDiff = diff;
                nearestFib = `${(parseFloat(level) * 100).toFixed(1)}%`;
                nearestPrice = price;
            }
        });
        
        Object.entries(fibExtensions).forEach(([level, price]) => {
            const diff = Math.abs(price - currentPrice);
            if (diff < minDiff) {
                minDiff = diff;
                nearestFib = `${(parseFloat(level) * 100).toFixed(1)}%`;
                nearestPrice = price;
            }
        });
        
        // Determinar si es soporte o resistencia
        const isSupport = nearestPrice < currentPrice;
        const type = isSupport ? 'soporte' : 'resistencia';
        const color = isSupport ? '#00C076' : '#FF5B5B';
        
        interpretation.innerHTML = `Nivel Fibonacci más cercano: <span style="color: ${color}; font-weight: bold;">${nearestFib}</span> ($${nearestPrice.toFixed(2)}) - Actúa como <span style="color: ${color};">${type}</span>`;
    }
}
// ============ DETECTOR DE BALLENAS - SOLO HISTOGRAMA ============
function updateWhaleChart(data) {
    const chartDiv = document.getElementById('whale-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const volume = df.volume || [];
    const close = df.close || [];
    
    if (dates.length === 0) return;
    
    const avgVolume = volume.reduce((a, b) => a + b, 0) / volume.length;
    const whaleStrength = new Array(dates.length).fill(0);
    
    for (let i = Math.max(5, dates.length - 50); i < dates.length; i++) {
        const volumeRatio = volume[i] / avgVolume;
        const priceChange = i > 0 ? ((close[i] - close[i-1]) / close[i-1]) * 100 : 0;
        
        if (volumeRatio > 1.5 && priceChange < -0.3) {
            const strength = Math.min(100, volumeRatio * 25);
            for (let j = i; j < Math.min(i + 7, dates.length); j++) {
                whaleStrength[j] += strength * (1 - (j - i) * 0.12);
            }
        }
        
        if (volumeRatio > 1.5 && priceChange > 0.3) {
            const strength = Math.min(100, volumeRatio * 25);
            for (let j = i; j < Math.min(i + 7, dates.length); j++) {
                whaleStrength[j] -= strength * (1 - (j - i) * 0.12);
            }
        }
    }
    
    const trace = {
        x: dates.slice(-50),
        y: whaleStrength.slice(-50),
        type: 'bar',
        name: 'Actividad Ballenas',
        marker: {
            color: whaleStrength.slice(-50).map(v => 
                v > 30 ? '#00C076' :
                v > 10 ? '#8A63D2' :
                v < -30 ? '#FF5B5B' :
                v < -10 ? '#FF8C00' :
                'rgba(128,128,128,0.3)'
            ),
            line: {
                width: whaleStrength.slice(-50).map(v => Math.abs(v) > 30 ? 1 : 0.5),
                color: 'white'
            }
        },
        hovertemplate: '%{y:.1f}<extra>Fuerza Ballenas</extra>'
    };
    
    const layout = {
        title: {
            text: 'Detector de Actividad Institucional (Ballenas)',
            font: {size: 14, color: 'white'}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Fuerza de Señal',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)',
            zerolinewidth: 1
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        showlegend: false,
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [{
            type: 'line',
            x0: dates.slice(-50)[0],
            y0: 0,
            x1: dates.slice(-50)[dates.slice(-50).length - 1],
            y1: 0,
            line: {color: 'rgba(255,255,255,0.3)', width: 1, dash: 'solid'}
        }]
    };
    
    Plotly.newPlot('whale-chart', [trace], layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('whale-interpretation');
    if (interpretation) {
        const lastValues = whaleStrength.slice(-7);
        const avgStrength = lastValues.reduce((a, b) => a + b, 0) / lastValues.length;
        const maxStrength = Math.max(...lastValues);
        const minStrength = Math.min(...lastValues);
        
        if (avgStrength > 20) {
            interpretation.innerHTML = '🐋 ACUMULACIÓN INSTITUCIONAL DETECTADA - Fuerza: ' + avgStrength.toFixed(0) + '%';
        } else if (avgStrength < -20) {
            interpretation.innerHTML = '🐋 DISTRIBUCIÓN INSTITUCIONAL DETECTADA - Fuerza: ' + Math.abs(avgStrength).toFixed(0) + '%';
        } else if (maxStrength > 30) {
            interpretation.innerHTML = '🐋 PICO DE ACUMULACIÓN - Señal fuerte en las últimas 7 velas';
        } else if (minStrength < -30) {
            interpretation.innerHTML = '🐋 PICO DE DISTRIBUCIÓN - Señal fuerte en las últimas 7 velas';
        } else {
            interpretation.innerHTML = '🐋 Sin actividad institucional significativa';
        }
    }
}

// ============ ADX/DMI CON DETECCIÓN DE CRUCES ============
function detectCrosses(plusDi, minusDi) {
    const crosses = [];
    for (let i = 1; i < plusDi.length; i++) {
        if (plusDi[i] && minusDi[i] && plusDi[i-1] && minusDi[i-1]) {
            if (plusDi[i-1] <= minusDi[i-1] && plusDi[i] > minusDi[i]) {
                crosses.push({type: 'bullish', index: i, value: plusDi[i]});
            }
            if (minusDi[i-1] <= plusDi[i-1] && minusDi[i] > plusDi[i]) {
                crosses.push({type: 'bearish', index: i, value: minusDi[i]});
            }
        }
    }
    return crosses;
}

function updateADXChart(data) {
    const chartDiv = document.getElementById('adx-chart');
    if (!chartDiv) return;
    
    // Limpiar el mensaje de "Calculando..."
    chartDiv.innerHTML = '';
    
    if (!data || !data.df) {
        console.warn('No hay datos para ADX');
        return;
    }
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 30) {
        console.warn('Datos insuficientes para ADX');
        return;
    }

    // Calcular ADX/DMI
    const adxData = calculateADX_PineScript(high, low, close, 14, 14);
    
    const lastDates = dates.slice(-50);
    const adx = adxData.adx.slice(-50);
    const plusDi = adxData.plus.slice(-50);
    const minusDi = adxData.minus.slice(-50);
    
    // Verificar que hay datos válidos
    const hasValidData = adx.some(v => v > 0) || plusDi.some(v => v > 0) || minusDi.some(v => v > 0);
    
    if (!hasValidData) {
        chartDiv.innerHTML = `
            <div class="alert alert-warning text-center" style="background-color: #0A0C10; color: #FFD700; border: 1px solid rgba(255,215,0,0.3);">
                <p class="mb-0">⚠️ No hay suficientes datos para calcular ADX/DMI</p>
            </div>
        `;
        return;
    }
    
    // Detectar cruces
    const crosses = detectCrosses(plusDi, minusDi);
    const bullishCrosses = crosses.filter(c => c.type === 'bullish');
    const bearishCrosses = crosses.filter(c => c.type === 'bearish');
    
    const traces = [
        {
            x: lastDates,
            y: adx,
            type: 'scatter',
            mode: 'lines',
            name: 'ADX',
            line: {color: 'white', width: 2}
        },
        {
            x: lastDates,
            y: plusDi,
            type: 'scatter',
            mode: 'lines',
            name: '+DI',
            line: {color: '#00C853', width: 1.5}
        },
        {
            x: lastDates,
            y: minusDi,
            type: 'scatter',
            mode: 'lines',
            name: '-DI',
            line: {color: '#FF1744', width: 1.5}
        }
    ];
    
    if (bullishCrosses.length > 0) {
        traces.push({
            x: bullishCrosses.map(c => lastDates[c.index]),
            y: bullishCrosses.map(c => c.value),
            type: 'scatter',
            mode: 'markers',
            name: '+DI > -DI',
            marker: {
                color: '#00C853',
                size: 12,
                symbol: 'triangle-up',
                line: {color: 'white', width: 1}
            }
        });
    }
    
    if (bearishCrosses.length > 0) {
        traces.push({
            x: bearishCrosses.map(c => lastDates[c.index]),
            y: bearishCrosses.map(c => c.value),
            type: 'scatter',
            mode: 'markers',
            name: '-DI > +DI',
            marker: {
                color: '#FF1744',
                size: 12,
                symbol: 'triangle-down',
                line: {color: 'white', width: 1}
            }
        });
    }
    
    traces.push({
        x: [lastDates[0], lastDates[lastDates.length - 1]],
        y: [23, 23],
        type: 'scatter',
        mode: 'lines',
        name: 'Key Level (23)',
        line: {color: 'rgba(255,255,255,0.5)', width: 1, dash: 'dash'}
    });
    
    const layout = {
        title: {
            text: 'ADX con DMI (+DI / -DI) - Cruces Detectados',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            title: 'Fecha/Hora',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            zerolinecolor: 'rgba(128,128,128,0.5)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Valor del Indicador',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            zerolinecolor: 'rgba(128,128,128,0.5)',
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        font: {color: 'white'},
        showlegend: true,
        legend: {
            x: 0,
            y: 1.1,
            orientation: 'h',
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        height: 300,
        margin: {l: 50, r: 50, t: 60, b: 50},
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        }
    };
    
    Plotly.newPlot('adx-chart', traces, layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('adx-interpretation');
    if (interpretation) {
        const lastADX = adx[adx.length - 1] || 0;
        const lastPlus = plusDi[plusDi.length - 1] || 0;
        const lastMinus = minusDi[minusDi.length - 1] || 0;
        
        if (lastADX > 23) {
            if (lastPlus > lastMinus) {
                interpretation.innerHTML = `📈 TENDENCIA ALCISTA FUERTE - ADX: ${lastADX.toFixed(1)} > 23, +DI: ${lastPlus.toFixed(1)}`;
            } else {
                interpretation.innerHTML = `📉 TENDENCIA BAJISTA FUERTE - ADX: ${lastADX.toFixed(1)} > 23, -DI: ${lastMinus.toFixed(1)}`;
            }
        } else if (lastADX > 20) {
            interpretation.innerHTML = `⚖️ TENDENCIA EN DESARROLLO - ADX: ${lastADX.toFixed(1)}`;
        } else {
            interpretation.innerHTML = `🔄 SIN TENDENCIA - ADX: ${lastADX.toFixed(1)} < 20`;
        }
    }
}

function calculateADX_PineScript(high, low, close, dilen, adxlen) {
    const n = high.length;
    
    const plus = new Array(n).fill(0);
    const minus = new Array(n).fill(0);
    const adx = new Array(n).fill(0);
    const tr = new Array(n).fill(0);
    const up = new Array(n).fill(0);
    const down = new Array(n).fill(0);
    
    // Calcular True Range y Directional Movement
    for (let i = 1; i < n; i++) {
        const hl = high[i] - low[i];
        const hc = Math.abs(high[i] - close[i-1]);
        const lc = Math.abs(low[i] - close[i-1]);
        tr[i] = Math.max(hl, hc, lc);
        
        up[i] = high[i] - high[i-1];
        down[i] = low[i-1] - low[i];
    }
    
    // RMA (Wilder's Smoothing)
    function rma(values, period, startIdx) {
        const result = new Array(n).fill(0);
        
        // Primer valor: promedio simple
        let sum = 0;
        for (let i = startIdx; i < startIdx + period && i < n; i++) {
            sum += values[i];
        }
        result[startIdx + period - 1] = sum / period;
        
        // Siguientes valores: RMA = (prevRMA * (period-1) + currentValue) / period
        for (let i = startIdx + period; i < n; i++) {
            result[i] = (result[i-1] * (period - 1) + values[i]) / period;
        }
        
        return result;
    }
    
    // Calcular RMA de TR
    const trRMA = rma(tr, dilen, 1);
    
    // Calcular +DI y -DI para cada período
    for (let i = dilen; i < n; i++) {
        // Calcular upRMA y downRMA
        const upValues = new Array(n).fill(0);
        const downValues = new Array(n).fill(0);
        
        for (let j = 0; j <= i; j++) {
            upValues[j] = (up[j] > down[j] && up[j] > 0) ? up[j] : 0;
            downValues[j] = (down[j] > up[j] && down[j] > 0) ? down[j] : 0;
        }
        
        const upRMA = rma(upValues, dilen, i - dilen + 1);
        const downRMA = rma(downValues, dilen, i - dilen + 1);
        
        if (trRMA[i] > 0) {
            plus[i] = 100 * (upRMA[i] || 0) / trRMA[i];
            minus[i] = 100 * (downRMA[i] || 0) / trRMA[i];
        }
        
        // Calcular DX
        const sum = plus[i] + minus[i];
        if (sum > 0) {
            const dx = 100 * Math.abs(plus[i] - minus[i]) / sum;
            
            // ADX Smoothing
            if (i === dilen + adxlen - 1) {
                let dxSum = 0;
                for (let j = i - adxlen + 1; j <= i; j++) {
                    const s = plus[j] + minus[j];
                    if (s > 0) {
                        dxSum += 100 * Math.abs(plus[j] - minus[j]) / s;
                    }
                }
                adx[i] = dxSum / adxlen;
            } else if (i > dilen + adxlen - 1) {
                adx[i] = (adx[i-1] * (adxlen - 1) + dx) / adxlen;
            }
        }
    }
    
    // ELIMINAR LA LIMITACIÓN A 60
    // for (let i = dilen + adxlen; i < n; i++) {
    //     adx[i] = Math.min(60, Math.max(0, adx[i]));
    //     plus[i] = Math.min(60, Math.max(0, plus[i]));
    //     minus[i] = Math.min(60, Math.max(0, minus[i]));
    // }
    
    return {plus, minus, adx};
}
// ============ FTMaverick - HISTOGRAMA (VERSIÓN CORREGIDA) ============
function updateFTMChart(data) {
    const chartDiv = document.getElementById('ftm-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const close = df.close || [];
    
    if (dates.length === 0) return;
    
    // Calcular FTMaverick según el backend
    const length = 20;
    const mult = 2.0;
    const closePrices = close.map(Number);
    const n = closePrices.length;
    
    const bb_width = new Array(n).fill(0);
    const trend_strength = new Array(n).fill(0);
    
    // Calcular Bandas de Bollinger
    for (let i = length - 1; i < n; i++) {
        const window = closePrices.slice(i - length + 1, i + 1);
        const mean = window.reduce((a, b) => a + b, 0) / length;
        const std = Math.sqrt(window.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / length) || 1;
        const upper = mean + std * mult;
        const lower = mean - std * mult;
        
        bb_width[i] = ((upper - lower) / mean) * 100;
        
        // LÓGICA PINESCRIPT ORIGINAL
        if (i > 0) {
            if (bb_width[i] > bb_width[i-1]) {
                trend_strength[i] = bb_width[i];      // Verde - ancho CRECIENTE
            } else {
                trend_strength[i] = -bb_width[i];     // Rojo - ancho DECRECIENTE
            }
        }
    }
    
    // ============ CÁLCULO DEL UMBRAL (percentil 70) ============
    // Usar TODAS las velas, no solo las últimas 50
    const bbWidthValues = bb_width.filter(v => v > 0);
    let highZoneThreshold = 5;
    
    if (bbWidthValues.length > 0) {
        bbWidthValues.sort((a, b) => a - b);
        const thresholdIndex = Math.floor(bbWidthValues.length * 0.7);
        highZoneThreshold = bbWidthValues[thresholdIndex] || 5;
    }
    
    // ============ DETECCIÓN DE ZONAS DE NO OPERACIÓN ============
    // SIGUIENDO LA LÓGICA DEL BACKEND:
    // 1. bb_width[i] > highZoneThreshold (ancho alto)
    // 2. trend_strength[i] < 0 (decreciente)
    // 3. bb_width[i] < Math.max(...bb_width.slice(Math.max(0, i-10), i)) (está cayendo desde un máximo)
    
    const noTradeZones = new Array(n).fill(false);
    
    for (let i = 10; i < n; i++) {
        if (i >= 10) {
            const maxLast10 = Math.max(...bb_width.slice(Math.max(0, i-10), i));
            
            if (bb_width[i] > highZoneThreshold && 
                trend_strength[i] < 0 && 
                bb_width[i] < maxLast10) {
                noTradeZones[i] = true;
            }
        }
    }
    
    // Últimas 50 velas para el gráfico
    const lastDates = dates.slice(-50);
    const lastStrength = trend_strength.slice(-50);
    const lastBBWidth = bb_width.slice(-50);
    const lastNoTrade = noTradeZones.slice(-50);
    
    // VALORES ABSOLUTOS para la altura de las barras
    const absValues = lastStrength.map(val => Math.abs(val));
    
    // COLORES: Verde = ancho CRECIENTE, Rojo = ancho DECRECIENTE
    const colors = lastStrength.map(val => val > 0 ? '#00C076' : '#FF5B5B');
    
    // TEXTO para hover
    const hoverTexts = lastStrength.map(val => 
        val > 0 ? 'CRECIENTE ↑' : 'DECRECIENTE ↓'
    );
    
    // Traza principal
    const trace = {
        x: lastDates,
        y: absValues,
        type: 'bar',
        name: 'FTMaverick',
        marker: {
            color: colors,
            line: { color: 'rgba(255,255,255,0.3)', width: 0.5 }
        },
        text: hoverTexts,
        hovertemplate: 'Ancho: %{y:.1f}%<br>Cambio: %{text}<br>%{x}<extra></extra>'
    };
    
    const layout = {
        title: {
            text: 'FTMaverick - Ancho de Banda de Bollinger',
            font: { color: 'white', size: 14, family: 'Arial' },
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            title: { text: 'Fecha/Hora', font: { color: 'white', size: 11 }, standoff: 20 },
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: false
        },
        yaxis: {
            title: 'Ancho de Banda %',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.5)',
            zerolinewidth: 1
        },
        template: 'plotly_dark',
        height: 300,
        margin: { l: 50, r: 50, t: 50, b: 50 },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: { color: 'white', size: 11, family: 'Arial' }
        },
        showlegend: false,
        barmode: 'relative',
        bargap: 0.1,
        shapes: [
            {
                type: 'line',
                x0: lastDates[0],
                y0: highZoneThreshold,
                x1: lastDates[lastDates.length - 1],
                y1: highZoneThreshold,
                line: { color: '#FFD700', width: 1, dash: 'dot' },
                opacity: 0.7
            }
        ]
    };
    
    // ============ AÑADIR MARCADORES DE ZONA DE NO OPERACIÓN ============
    if (lastNoTrade.some(val => val === true)) {
        const noTradeX = [];
        const noTradeY = [];
        
        for (let i = 0; i < lastNoTrade.length; i++) {
            if (lastNoTrade[i]) {
                noTradeX.push(lastDates[i]);
                noTradeY.push(absValues[i]);
            }
        }
        
        const noTradeTrace = {
            x: noTradeX,
            y: noTradeY,
            type: 'scatter',
            mode: 'markers',
            name: 'Zona No-Operación',
            marker: {
                symbol: 'x',
                size: 12,
                color: '#FFD700',
                line: { color: 'black', width: 1 }
            },
            hovertemplate: '⚠️ ZONA DE NO OPERACIÓN<br>Ancho: %{y:.1f}% (DECRECIENTE)<extra></extra>'
        };
        
        Plotly.newPlot('ftm-chart', [trace, noTradeTrace], layout, { responsive: true, displaylogo: false });
    } else {
        Plotly.newPlot('ftm-chart', [trace], layout, { responsive: true, displaylogo: false });
    }
    
    // ============ INTERPRETACIÓN ============
    const interpretation = document.getElementById('ftm-interpretation');
    if (interpretation) {
        const lastIdx = lastStrength.length - 1;
        const lastVal = lastStrength[lastIdx];
        const lastAbs = absValues[lastIdx];
        const isGrowing = lastVal > 0;
        const isNoTrade = lastNoTrade[lastIdx];
        
        let estado = '';
        let color = '';
        let detalle = '';
        
        if (isNoTrade) {
            estado = '🚫 ZONA DE NO OPERACIÓN';
            color = '#FFD700';
            detalle = `Ancho de banda ALTO (${lastAbs.toFixed(1)}%) pero DECRECIENTE - Alta volatilidad en contracción`;
        } else if (isGrowing && lastAbs > highZoneThreshold) {
            estado = '✅ EXPANSIÓN FUERTE';
            color = '#00C076';
            detalle = `Ancho de banda CRECIENTE y ALTO (${lastAbs.toFixed(1)}% > ${highZoneThreshold.toFixed(1)}%) - Tendencia con fuerza`;
        } else if (isGrowing) {
            estado = '🟢 EXPANSIÓN DÉBIL';
            color = '#8A63D2';
            detalle = `Ancho de banda CRECIENTE (${lastAbs.toFixed(1)}%) - Fuerza emergente`;
        } else if (!isGrowing && lastAbs > highZoneThreshold) {
            estado = '🔴 CONTRACCIÓN FUERTE';
            color = '#FF5B5B';
            detalle = `Ancho de banda ALTO pero DECRECIENTE (${lastAbs.toFixed(1)}%) - Posible agotamiento`;
        } else {
            estado = '🟠 CONTRACCIÓN DÉBIL';
            color = '#FF8C00';
            detalle = `Ancho de banda DECRECIENTE (${lastAbs.toFixed(1)}%) - Consolidación`;
        }
        
        interpretation.innerHTML = `📊 <span style="color: ${color}; font-weight: bold;">${estado}</span> - ${detalle}`;
    }
}
// ============ RSI Maverick ============
// ============ RSI Maverick - VERSIÓN PINESCRIPT ============
function updateRSIMaverickChart(data) {
    const chartDiv = document.getElementById('rsi-maverick-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const close = df.close || [];
    
    // Convertir fechas
    const dateObjects = dates.map(d => new Date(d));
    
    // Calcular RSI Maverick (%B)
    const length = 20;
    const mult = 2.0;
    const rsiM = calculateRSIMaverick(close, length, mult);
    
    // Tomar últimas 100 velas
    const lastDates = dateObjects.slice(-50); //Antes -100
    const lastRSI = rsiM.slice(-50); // Antes -100
    
    const trace = {
        x: lastDates,
        y: lastRSI,
        type: 'scatter',
        mode: 'lines',
        name: '%B',
        line: {color: '#3A8BFF', width: 2}
    };
    
    const layout = {
        title: {
            text: 'RSI Maverick - %B',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: '%B',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)',
            autorange: true,
            rangemode: 'normal'
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        // Líneas de referencia como en PineScript
        shapes: [
            // Línea superior 1.0 (roja punteada)
            {
                type: 'line',
                x0: lastDates[0],
                y0: 1.0,
                x1: lastDates[lastDates.length - 1],
                y1: 1.0,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            // Línea inferior 0.0 (verde punteada)
            {
                type: 'line',
                x0: lastDates[0],
                y0: 0.0,
                x1: lastDates[lastDates.length - 1],
                y1: 0.0,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            },
            // Línea 0.5 (blanca sólida)
            {
                type: 'line',
                x0: lastDates[0],
                y0: 0.5,
                x1: lastDates[lastDates.length - 1],
                y1: 0.5,
                line: {color: '#FFFFFF', width: 1, dash: 'solid'}
            },
            // Línea 0.2 (verde punteada)
            {
                type: 'line',
                x0: lastDates[0],
                y0: 0.2,
                x1: lastDates[lastDates.length - 1],
                y1: 0.2,
                line: {color: '#87DA8A', width: 1, dash: 'dot'}
            },
            // Línea 0.8 (roja punteada)
            {
                type: 'line',
                x0: lastDates[0],
                y0: 0.8,
                x1: lastDates[lastDates.length - 1],
                y1: 0.8,
                line: {color: '#CF5757', width: 1, dash: 'dot'}
            }
        ]
    };
    
    Plotly.newPlot('rsi-maverick-chart', [trace], layout, {responsive: true, displaylogo: false});
}
// ============ Ichimoku Cloud ============
function updateIchimokuChart(data) {
    const chartDiv = document.getElementById('ichimoku-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const open = df.open || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 52) return;
    
    const tenkan = [];
    const kijun = [];
    const senkouA = [];
    const senkouB = [];
    
    for (let i = 0; i < dates.length; i++) {
        if (i >= 8) {
            const high9 = Math.max(...high.slice(i - 8, i + 1));
            const low9 = Math.min(...low.slice(i - 8, i + 1));
            tenkan.push((high9 + low9) / 2);
        } else {
            tenkan.push(null);
        }
        
        if (i >= 25) {
            const high26 = Math.max(...high.slice(i - 25, i + 1));
            const low26 = Math.min(...low.slice(i - 25, i + 1));
            kijun.push((high26 + low26) / 2);
        } else {
            kijun.push(null);
        }
        
        if (i >= 25 && tenkan[i] && kijun[i]) {
            senkouA.push((tenkan[i] + kijun[i]) / 2);
        } else {
            senkouA.push(null);
        }
        
        if (i >= 51) {
            const high52 = Math.max(...high.slice(i - 51, i + 1));
            const low52 = Math.min(...low.slice(i - 51, i + 1));
            senkouB.push((high52 + low52) / 2);
        } else {
            senkouB.push(null);
        }
    }
    
    const senkouAShifted = new Array(dates.length).fill(null);
    const senkouBShifted = new Array(dates.length).fill(null);
    
    for (let i = 0; i < dates.length; i++) {
        if (i >= 26 && senkouA[i - 26]) {
            senkouAShifted[i] = senkouA[i - 26];
        }
        if (i >= 26 && senkouB[i - 26]) {
            senkouBShifted[i] = senkouB[i - 26];
        }
    }
    
    const lastDates = dates.slice(-60);
    const lastOpen = open.slice(-60);
    const lastHigh = high.slice(-60);
    const lastLow = low.slice(-60);
    const lastClose = close.slice(-60);
    const lastTenkan = tenkan.slice(-60);
    const lastKijun = kijun.slice(-60);
    const lastSenkouA = senkouAShifted.slice(-60);
    const lastSenkouB = senkouBShifted.slice(-60);
    
    const traces = [
        {
            x: lastDates,
            open: lastOpen,
            high: lastHigh,
            low: lastLow,
            close: lastClose,
            type: 'candlestick',  // ← VELAS JAPONESAS
            name: 'Precio',
            increasing: {line: {color: '#00C076', width: 1}, fillcolor: '#00C076'},
            decreasing: {line: {color: '#FF5B5B', width: 1}, fillcolor: '#FF5B5B'},
            showlegend: true,
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastTenkan,
            type: 'scatter',
            mode: 'lines',
            name: 'Tenkan-sen (9)',
            line: {color: '#FFD700', width: 1.5},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastKijun,
            type: 'scatter',
            mode: 'lines',
            name: 'Kijun-sen (26)',
            line: {color: '#FF69B4', width: 1.5},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastSenkouA,
            type: 'scatter',
            mode: 'lines',
            name: 'Senkou Span A',
            line: {color: '#00C076', width: 1, dash: 'dot'},
            fill: 'tonexty',
            fillcolor: 'rgba(0,192,118,0.1)',
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastSenkouB,
            type: 'scatter',
            mode: 'lines',
            name: 'Senkou Span B',
            line: {color: '#FF5B5B', width: 1, dash: 'dot'},
            fill: 'tonexty',
            fillcolor: 'rgba(255,91,91,0.1)',
            yaxis: 'y'
        }
    ];
    
    const layout = {
        title: {
            text: 'Ichimoku Cloud',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            range: [lastDates[0], lastDates[lastDates.length - 1]],
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false}
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 50},
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 9},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        }
    };
    
    Plotly.newPlot('ichimoku-chart', traces, layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('ichimoku-interpretation');
    if (interpretation) {
        const lastPrice = close[close.length - 1];
        const lastSenkouA = senkouAShifted[senkouAShifted.length - 1] || 0;
        const lastSenkouB = senkouBShifted[senkouBShifted.length - 1] || 0;
        const lastTenkan = tenkan[tenkan.length - 1] || 0;
        const lastKijun = kijun[kijun.length - 1] || 0;
        
        if (lastPrice > lastSenkouA && lastPrice > lastSenkouB) {
            if (lastTenkan > lastKijun) interpretation.innerHTML = '🟢 SEÑAL ALCISTA FUERTE - Precio sobre nube, TK alcista';
            else interpretation.innerHTML = '🟡 ALCISTA DÉBIL - Precio sobre nube pero TK bajista';
        } else if (lastPrice < lastSenkouA && lastPrice < lastSenkouB) {
            if (lastTenkan < lastKijun) interpretation.innerHTML = '🔴 SEÑAL BAJISTA FUERTE - Precio bajo nube, TK bajista';
            else interpretation.innerHTML = '🟠 BAJISTA DÉBIL - Precio bajo nube pero TK alcista';
        } else {
            interpretation.innerHTML = '⚪ NUBE NEUTRAL - Precio dentro de la nube';
        }
    }
}
// ============ SQUEEZE MOMENTUM - VERSIÓN ORIGINAL CON COLORES ============
function updateSqueezeChart(data) {
    const chartDiv = document.getElementById('squeeze-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    // Convertir fechas
    const dateObjects = dates.map(d => new Date(d));
    
    const squeeze = calculateSqueezeMomentum(high, low, close);
    const momentum = squeeze.momentum || new Array(close.length).fill(0);
    
    // Calcular pendientes
    const pendientes = [];
    for (let i = 0; i < momentum.length; i++) {
        if (i > 0) {
            pendientes.push(momentum[i] - momentum[i-1]);
        } else {
            pendientes.push(0);
        }
    }
    
    // Definir colores según valor y pendiente
    const colors = momentum.slice(-50).map((val, idx) => {
        const indexOriginal = momentum.length - 50 + idx;
        const pendiente = indexOriginal > 0 ? momentum[indexOriginal] - momentum[indexOriginal-1] : 0;
        
        if (val > 0) {
            // Valle verde (positivo)
            if (pendiente > 0) {
                return '#00C076'; // Verde original (pendiente positiva)
            } else {
                return '#7FFF9A'; // Verde claro (pendiente negativa)
            }
        } else {
            // Valle rojo (negativo)
            if (pendiente < 0) {
                return '#FF5B5B'; // Rojo original (pendiente negativa)
            } else {
                return '#FFA07A'; // Rojo claro (pendiente positiva)
            }
        }
    });
    
    const trace = {
        x: dateObjects.slice(-50),
        y: momentum.slice(-50),
        type: 'bar',
        name: 'Squeeze Momentum',
        marker: {
            color: colors,
            line: {
                width: 0.5,
                color: 'rgba(255,255,255,0.3)'
            }
        },
        hovertemplate: 'Momentum: %{y:.2f}<br>%{x}<extra></extra>'
    };
    
    const lastDates = dateObjects.slice(-50);
    const layout = {
        title: {
            text: 'Squeeze Momentum',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Momentum',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)',
            zerolinewidth: 1
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [{
            type: 'line',
            x0: lastDates[0],
            y0: 0,
            x1: lastDates[lastDates.length - 1],
            y1: 0,
            line: {color: 'rgba(255,255,255,0.3)', width: 1, dash: 'solid'}
        }]
    };
    
    Plotly.newPlot('squeeze-chart', [trace], layout, {responsive: true, displaylogo: false});
    
    // Interpretación
    const interpretation = document.getElementById('squeeze-interpretation');
    if (interpretation) {
        const lastVal = momentum[momentum.length - 1];
        const prevVal = momentum[momentum.length - 2];
        const pendiente = lastVal - prevVal;
        
        let estado = '';
        if (lastVal > 0) {
            if (pendiente > 0) {
                estado = '🟢 Momentum positivo ACELERANDO';
            } else {
                estado = '🟢 Momentum positivo DESACELERANDO';
            }
        } else if (lastVal < 0) {
            if (pendiente < 0) {
                estado = '🔴 Momentum negativo ACELERANDO';
            } else {
                estado = '🔴 Momentum negativo DESACELERANDO';
            }
        } else {
            estado = '⚪ Momentum NEUTRO';
        }
        
        interpretation.innerHTML = `${estado} (${lastVal.toFixed(2)})`;
    }
}

// ============ MACD ============
function updateMACDChart(data) {
    const chartDiv = document.getElementById('macd-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const close = df.close || [];
    
    const macdData = calculateMACD(close);
    const colors = macdData.histogram.slice(-50).map(x => x > 0 ? '#00C076' : '#FF5B5B');
    
    const traces = [
        {
            x: dates.slice(-50),
            y: macdData.macd.slice(-50),
            type: 'scatter',
            mode: 'lines',
            name: 'MACD',
            line: {color: '#3A8BFF', width: 2}
        },
        {
            x: dates.slice(-50),
            y: macdData.signal.slice(-50),
            type: 'scatter',
            mode: 'lines',
            name: 'Señal',
            line: {color: '#FFD700', width: 1.5}
        },
        {
            x: dates.slice(-50),
            y: macdData.histogram.slice(-50),
            type: 'bar',
            name: 'Histograma',
            marker: {color: colors}
        }
    ];
    
    const layout = {
        title: {
            text: 'MACD',
            font: {color: 'white', size: 14},
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            title: {
                text: 'Fecha/Hora',
                font: {color: 'white', size: 11},
                standoff: 30
            }
        },
        yaxis: {
            title: 'MACD',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)'
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 80},  // MÁS ESPACIO ABAJO
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        barmode: 'overlay',
        legend: {
            orientation: 'h',
            yanchor: 'top',
            y: -0.25,  // DEBAJO DEL GRÁFICO
            xanchor: 'center',
            x: 0.5,
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        }
    };
    
    Plotly.newPlot('macd-chart', traces, layout, {responsive: true, displaylogo: false});
}

// ============ RSI Tradicional ============
function updateRSIChart(data) {
    const chartDiv = document.getElementById('rsi-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const close = df.close || [];
    
    const rsi = calculateRSI(close);
    
    const trace = {
        x: dates.slice(-50),
        y: rsi.slice(-50),
        type: 'scatter',
        mode: 'lines',
        name: 'RSI',
        line: {color: '#8A63D2', width: 2}
    };
    
    const lastDates = dates.slice(-50);
    const layout = {
        title: {
            text: 'RSI Tradicional',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'RSI',
            range: [0, 100],
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)'
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [
            {
                type: 'line',
                x0: lastDates[0],
                y0: 70,
                x1: lastDates[lastDates.length - 1],
                y1: 70,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            {
                type: 'line',
                x0: lastDates[0],
                y0: 30,
                x1: lastDates[lastDates.length - 1],
                y1: 30,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            }
        ]
    };
    
    Plotly.newPlot('rsi-chart', [trace], layout, {responsive: true, displaylogo: false});
}

// ============ Estocástico ============
function updateStochasticChart(data) {
    const chartDiv = document.getElementById('stochastic-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    const stoch = calculateStochastic(high, low, close);
    
    const traces = [
        {
            x: dates.slice(-50),
            y: stoch.k.slice(-50),
            type: 'scatter',
            mode: 'lines',
            name: '%K',
            line: {color: '#3A8BFF', width: 2}
        },
        {
            x: dates.slice(-50),
            y: stoch.d.slice(-50),
            type: 'scatter',
            mode: 'lines',
            name: '%D',
            line: {color: '#FFD700', width: 2}
        }
    ];
    
    const lastDates = dates.slice(-50);
    const layout = {
        title: {
            text: 'Estocástico',
            font: {color: 'white', size: 14},
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            title: {
                text: 'Fecha/Hora',
                font: {color: 'white', size: 11},
                standoff: 30
            }
        },
        yaxis: {
            title: 'Estocástico',
            range: [0, 100],
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)'
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 80},  // MÁS ESPACIO ABAJO
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [
            {
                type: 'line',
                x0: lastDates[0],
                y0: 80,
                x1: lastDates[lastDates.length - 1],
                y1: 80,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            {
                type: 'line',
                x0: lastDates[0],
                y0: 20,
                x1: lastDates[lastDates.length - 1],
                y1: 20,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            }
        ],
        legend: {
            orientation: 'h',
            yanchor: 'top',
            y: -0.25,  // DEBAJO DEL GRÁFICO
            xanchor: 'center',
            x: 0.5,
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        }
    };
    
    Plotly.newPlot('stochastic-chart', traces, layout, {responsive: true, displaylogo: false});
}
// ============ WILLIAMS %R + CCI ============
// ============ WILLIAMS %R + CCI - EJE Y AUTO ============
function updateWilliamsCCIChart(data) {
    const chartDiv = document.getElementById('williams-cci-chart');
    if (!chartDiv) {
        const container = document.getElementById('indicators-container');
        if (!container) return;
        
        const newCard = document.createElement('div');
        newCard.className = 'card bg-dark border-info mb-4 indicator-card';
        newCard.setAttribute('data-indicator', 'williams-cci');
        newCard.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <i class="fas fa-wave-square me-2" style="color: #FFD700;"></i>
                    Williams %R + CCI
                </h5>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary btn-move" data-direction="up">
                        <i class="fas fa-arrow-up"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-move" data-direction="down">
                        <i class="fas fa-arrow-down"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-collapse" data-collapsed="false">
                        <i class="fas fa-minus"></i>
                    </button>
                </div>
            </div>
            <div class="card-body indicator-content">
                <div id="williams-cci-chart" style="height: 300px;"></div>
                <div class="mt-2">
                    <small class="text-muted">
                        <strong>Interpretación:</strong> 
                        <span style="color: #00C076;">Williams %R</span> y 
                        <span style="color: #FFD700;">CCI (normalizado)</span>.
                        <span id="williams-cci-interpretation">Analizando condiciones extremas...</span>
                    </small>
                </div>
            </div>
        `;
        container.appendChild(newCard);
        
        if (typeof window.initializeEventListeners === 'function') {
            window.initializeEventListeners();
        }
    }
    
    if (!data || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 30) return;
    
    const dateObjects = dates.map(d => new Date(d));
    
    // Calcular Williams %R
    const williams = new Array(close.length).fill(-50);
    const period = 14;
    
    for (let i = period - 1; i < close.length; i++) {
        const highest = Math.max(...high.slice(i - period + 1, i + 1));
        const lowest = Math.min(...low.slice(i - period + 1, i + 1));
        if (highest - lowest !== 0) {
            williams[i] = -100 * (highest - close[i]) / (highest - lowest);
        }
    }
    
    // Calcular CCI
    const cci = new Array(close.length).fill(0);
    const cciPeriod = 20;
    
    for (let i = cciPeriod - 1; i < close.length; i++) {
        const tp = (high[i] + low[i] + close[i]) / 3;
        let smaTP = 0;
        for (let j = i - cciPeriod + 1; j <= i; j++) {
            smaTP += (high[j] + low[j] + close[j]) / 3;
        }
        smaTP /= cciPeriod;
        
        let meanDev = 0;
        for (let j = i - cciPeriod + 1; j <= i; j++) {
            const tpJ = (high[j] + low[j] + close[j]) / 3;
            meanDev += Math.abs(tpJ - smaTP);
        }
        meanDev /= cciPeriod;
        
        if (meanDev !== 0) {
            cci[i] = (tp - smaTP) / (0.015 * meanDev);
        }
    }
    
    const lastDates = dateObjects.slice(-50);
    const lastWilliams = williams.slice(-50);
    const lastCCI = cci.slice(-50);
    
    const traces = [
        {
            x: lastDates,
            y: lastWilliams,
            type: 'scatter',
            mode: 'lines',
            name: 'Williams %R',
            line: {color: '#00C076', width: 2},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastCCI,
            type: 'scatter',
            mode: 'lines',
            name: 'CCI',
            line: {color: '#FFD700', width: 2},
            yaxis: 'y'
        }
    ];
    
    const layout = {
        title: {
            text: 'Williams %R + CCI',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Valor',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)',
            autorange: true  // Ahora es autoajustable
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 50},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [
            {
                type: 'line',
                x0: lastDates[0],
                y0: -20,
                x1: lastDates[lastDates.length - 1],
                y1: -20,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            {
                type: 'line',
                x0: lastDates[0],
                y0: -80,
                x1: lastDates[lastDates.length - 1],
                y1: -80,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            }
        ],
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 9}
        }
    };
    
    Plotly.newPlot('williams-cci-chart', traces, layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('williams-cci-interpretation');
    if (interpretation) {
        const lastW = lastWilliams[lastWilliams.length - 1];
        const lastC = lastCCI[lastCCI.length - 1];
        
        let wState = lastW > -20 ? 'sobrecompra' : (lastW < -80 ? 'sobreventa' : 'neutral');
        let cState = lastC > 100 ? 'sobrecompra' : (lastC < -100 ? 'sobreventa' : 'neutral');
        
        interpretation.innerHTML = `Williams: ${wState} (${lastW.toFixed(1)}) | CCI: ${cState} (${lastC.toFixed(0)})`;
    }
}

// ============ Volumen ============
// ============ VOLUMEN + OBV ============
function updateVolumeChart(data) {
    const chartDiv = document.getElementById('volume-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const volume = df.volume || [];
    const close = df.close || [];
    
    if (dates.length === 0) return;
    
    // Calcular OBV (On-Balance Volume)
    const obv = new Array(close.length).fill(0);
    for (let i = 1; i < close.length; i++) {
        if (close[i] > close[i-1]) {
            obv[i] = obv[i-1] + volume[i];
        } else if (close[i] < close[i-1]) {
            obv[i] = obv[i-1] - volume[i];
        } else {
            obv[i] = obv[i-1];
        }
    }
    
    // Normalizar OBV para que encaje en el mismo gráfico que el volumen
    const maxVol = Math.max(...volume.slice(-50));
    const minVol = Math.min(...volume.slice(-50));
    const maxOBV = Math.max(...obv.slice(-50));
    const minOBV = Math.min(...obv.slice(-50));
    
    const obvNormalized = obv.slice(-50).map(val => {
        // Normalizar OBV al rango del volumen (0.2 * maxVol a 0.8 * maxVol)
        // para que no opaque el volumen pero sea visible
        if (maxOBV === minOBV) return maxVol * 0.5;
        const norm = (val - minOBV) / (maxOBV - minOBV); // 0 a 1
        return minVol * 0.8 + norm * (maxVol * 0.8 - minVol * 0.8);
    });
    
    // Colores para volumen: verde si cierra arriba, rojo si abajo
    const colors = volume.slice(-50).map((_, i) => {
        const idx = dates.length - 50 + i;
        return close[idx] > close[idx-1] ? '#3A8BFF' : '#FF5B5B';
    });
    
    const traces = [
        {
            x: dates.slice(-50),
            y: volume.slice(-50),
            type: 'bar',
            name: 'Volumen',
            marker: {color: colors},
            yaxis: 'y',
            opacity: 0.7
        },
        {
            x: dates.slice(-50),
            y: obvNormalized,
            type: 'scatter',
            mode: 'lines',
            name: 'OBV (normalizado)',
            line: {color: '#FFD700', width: 2},
            yaxis: 'y'
        }
    ];
    
    const layout = {
        title: {
            text: 'Volumen + OBV (On-Balance Volume)',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Volumen',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 9},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        }
    };
    
    Plotly.newPlot('volume-chart', traces, layout, {responsive: true, displaylogo: false});
    
    // Interpretación
    const interpretation = document.getElementById('volume-interpretation');
    if (interpretation) {
        const lastOBV = obv[obv.length - 1];
        const prevOBV = obv[obv.length - 2];
        const obvTrend = lastOBV > prevOBV ? 'alcista' : 'bajista';
        const volRatio = volume[volume.length - 1] / (volume.slice(-20).reduce((a,b) => a+b, 0) / 20);
        
        interpretation.innerHTML = `OBV tendencia ${obvTrend} | Volumen ${volRatio.toFixed(1)}x promedio`;
    }
}

// ============ MFI + FORCE INDEX ============
function updateMFIForceChart(data) {
    const chartDiv = document.getElementById('mfi-force-chart');
    if (!chartDiv) {
        // Crear el contenedor si no existe
        const container = document.getElementById('indicators-container');
        if (!container) return;
        
        const newCard = document.createElement('div');
        newCard.className = 'card bg-dark border-warning mb-4 indicator-card';
        newCard.setAttribute('data-indicator', 'mfi-force');
        newCard.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <i class="fas fa-coins me-2" style="color: #FFD700;"></i>
                    MFI + Force Index
                </h5>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary btn-move" data-direction="up">
                        <i class="fas fa-arrow-up"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-move" data-direction="down">
                        <i class="fas fa-arrow-down"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-collapse" data-collapsed="false">
                        <i class="fas fa-minus"></i>
                    </button>
                </div>
            </div>
            <div class="card-body indicator-content">
                <div id="mfi-force-chart" style="height: 300px;"></div>
                <div class="mt-2">
                    <small class="text-muted">
                        <strong>Interpretación:</strong> 
                        <span style="color: #3A8BFF;">MFI</span> (flujo monetario) y 
                        <span style="color: #FFD700;">Force Index</span> (fuerza compradora/vendedora).
                        <span id="mfi-force-interpretation">Analizando flujo institucional...</span>
                    </small>
                </div>
            </div>
        `;
        container.appendChild(newCard);
        
        if (typeof window.initializeEventListeners === 'function') {
            window.initializeEventListeners();
        }
    }
    
    if (!data || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    const volume = df.volume || [];
    
    if (dates.length < 30) return;
    
    // ============ CALCULAR MFI (Money Flow Index) ============
    const mfi = new Array(close.length).fill(50);
    const period = 14;
    
    for (let i = period; i < close.length; i++) {
        let positiveFlow = 0;
        let negativeFlow = 0;
        
        for (let j = i - period + 1; j <= i; j++) {
            const tp = (high[j] + low[j] + close[j]) / 3;
            const prevTp = j > 0 ? (high[j-1] + low[j-1] + close[j-1]) / 3 : tp;
            
            if (tp > prevTp) {
                positiveFlow += tp * volume[j];
            } else {
                negativeFlow += tp * volume[j];
            }
        }
        
        if (negativeFlow !== 0) {
            const moneyRatio = positiveFlow / negativeFlow;
            mfi[i] = 100 - (100 / (1 + moneyRatio));
        }
    }
    
    // ============ CALCULAR FORCE INDEX ============
    const forceIndex = new Array(close.length).fill(0);
    for (let i = 1; i < close.length; i++) {
        forceIndex[i] = (close[i] - close[i-1]) * volume[i];
    }
    
    // Suavizar Force Index con EMA 13
    const forceSmooth = new Array(close.length).fill(0);
    const alpha = 2 / (13 + 1);
    forceSmooth[0] = forceIndex[0];
    for (let i = 1; i < close.length; i++) {
        forceSmooth[i] = forceIndex[i] * alpha + forceSmooth[i-1] * (1 - alpha);
    }
    
    // Normalizar Force Index para que encaje con MFI (0-100)
    const forceValues = forceSmooth.slice(-50);
    const maxForce = Math.max(...forceValues.map(Math.abs));
    const forceNormalized = forceSmooth.slice(-50).map(val => {
        return 50 + (val / maxForce) * 40; // Mapear de -40 a +40 alrededor de 50
    });
    
    const lastDates = dates.slice(-50);
    const lastMFI = mfi.slice(-50);
    
    // Colores para Force Index
    const forceColors = forceSmooth.slice(-50).map(val => val > 0 ? '#00C076' : '#FF5B5B');
    
    const traces = [
        {
            x: lastDates,
            y: lastMFI,
            type: 'scatter',
            mode: 'lines',
            name: 'MFI',
            line: {color: '#3A8BFF', width: 2},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: forceNormalized,
            type: 'scatter',
            mode: 'lines',
            name: 'Force Index',
            line: {color: '#FFD700', width: 2},
            yaxis: 'y'
        }
    ];
    
    const layout = {
        title: {
            text: 'MFI (Money Flow Index) + Force Index',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'Valor',
            range: [0, 100],
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.3)'
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 50},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        shapes: [
            {
                type: 'line',
                x0: lastDates[0],
                y0: 80,
                x1: lastDates[lastDates.length - 1],
                y1: 80,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            {
                type: 'line',
                x0: lastDates[0],
                y0: 20,
                x1: lastDates[lastDates.length - 1],
                y1: 20,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            }
        ],
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 9}
        }
    };
    
    Plotly.newPlot('mfi-force-chart', traces, layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('mfi-force-interpretation');
    if (interpretation) {
        const lastMFIVal = lastMFI[lastMFI.length - 1];
        const lastForce = forceSmooth[forceSmooth.length - 1];
        
        let mfiState = lastMFIVal > 80 ? 'sobrecompra' : (lastMFIVal < 20 ? 'sobreventa' : 'neutral');
        let forceState = lastForce > 0 ? 'positivo' : 'negativo';
        
        interpretation.innerHTML = `MFI: ${mfiState} (${lastMFIVal.toFixed(1)}) | Force: ${forceState}`;
    }
}

// ============ SuperTrend + Parabolic SAR con Velas ============
function updateSuperTrendChart(data) {
    const chartDiv = document.getElementById('supertrend-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    const open = df.open || [];
    
    if (dates.length < 30) return;
    
    // ============ CALCULAR SUPERTREND ============
    const st = calculateSuperTrend(high, low, close);
    
    // ============ CALCULAR PARABOLIC SAR ============
    const psar = calculateParabolicSAR(high, low);
    
    // Últimas 50 velas para el gráfico
    const lastDates = dates.slice(-50);
    const lastOpen = open.slice(-50);
    const lastHigh = high.slice(-50);
    const lastLow = low.slice(-50);
    const lastClose = close.slice(-50);
    const lastST = st.supertrend.slice(-50);
    const lastTrend = st.trend.slice(-50);
    const lastPSAR = psar.slice(-50);
    
    // ============ TRAZAS ============
    const traces = [];
    
    // Traza 1: Velas Japonesas
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1.5}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1.5}, fillcolor: '#FF5B5B'},
        showlegend: true,
        yaxis: 'y'
    });
    
    // Traza 2: SuperTrend (línea)
    const stX = [], stY = [], stColors = [];
    for (let i = 0; i < lastST.length; i++) {
        if (lastST[i] > 0) {
            stX.push(lastDates[i]);
            stY.push(lastST[i]);
            stColors.push(lastTrend[i] === 1 ? '#00C076' : '#FF5B5B');
        }
    }
    
    traces.push({
        x: stX,
        y: stY,
        mode: 'lines+markers',
        name: 'SuperTrend',
        line: {
            color: 'rgba(255,255,255,0.5)',
            width: 1.5
        },
        marker: {
            symbol: 'circle',
            size: 4,
            color: stColors,
            line: {color: 'white', width: 0.5}
        },
        yaxis: 'y'
    });
    
    // Traza 3: Parabolic SAR (puntos)
    const psarX = [], psarY = [], psarColors = [];
    for (let i = 0; i < lastPSAR.length; i++) {
        if (lastPSAR[i] > 0) {
            psarX.push(lastDates[i]);
            psarY.push(lastPSAR[i]);
            // Color: verde si está debajo del precio (alcista), rojo si está encima (bajista)
            psarColors.push(lastPSAR[i] < lastClose[i] ? '#00C076' : '#FF5B5B');
        }
    }
    
    traces.push({
        x: psarX,
        y: psarY,
        mode: 'markers',
        name: 'Parabolic SAR',
        marker: {
            symbol: 'diamond',
            size: 5,
            color: psarColors,
            line: {color: 'white', width: 1}
        },
        yaxis: 'y'
    });
    
    // ============ DETECTAR CRUCES Y SEÑALES ============
    const signals = [];
    for (let i = 1; i < lastPSAR.length; i++) {
        // Señal alcista: SAR cambia de encima a debajo del precio
        if (lastPSAR[i-1] > lastClose[i-1] && lastPSAR[i] < lastClose[i]) {
            signals.push({
                x: lastDates[i],
                y: lastLow[i] * 0.98,
                text: '🟢 SAR LONG',
                color: '#00C076'
            });
        }
        // Señal bajista: SAR cambia de debajo a encima del precio
        else if (lastPSAR[i-1] < lastClose[i-1] && lastPSAR[i] > lastClose[i]) {
            signals.push({
                x: lastDates[i],
                y: lastHigh[i] * 1.02,
                text: '🔴 SAR SHORT',
                color: '#FF5B5B'
            });
        }
    }
    
    // Añadir señales como anotaciones
    const annotations = signals.slice(-3).map(s => ({
        x: s.x,
        y: s.y,
        xref: 'x',
        yref: 'y',
        text: s.text,
        showarrow: true,
        arrowhead: 2,
        arrowsize: 1,
        arrowwidth: 2,
        arrowcolor: s.color,
        font: {
            family: 'Arial',
            size: 8,
            color: 'white'
        },
        bgcolor: s.color,
        bordercolor: 'white',
        borderwidth: 1,
        borderpad: 2
    }));
    
    const layout = {
        title: {
            text: 'SuperTrend + Parabolic SAR con Velas',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false}
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 50},
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        annotations: annotations
    };
    
    Plotly.newPlot('supertrend-chart', traces, layout, {responsive: true, displaylogo: false});
    
    // ============ INTERPRETACIÓN ============
    const interpretation = document.getElementById('supertrend-interpretation');
    if (interpretation) {
        const lastTrendVal = lastTrend[lastTrend.length - 1];
        const lastPSARVal = lastPSAR[lastPSAR.length - 1];
        const lastCloseVal = lastClose[lastClose.length - 1];
        
        let stState = lastTrendVal === 1 ? '🟢 ALCISTA' : '🔴 BAJISTA';
        let psarState = lastPSARVal < lastCloseVal ? '🟢 alcista' : '🔴 bajista';
        
        interpretation.innerHTML = `SuperTrend: ${stState} | Parabolic SAR: ${psarState}`;
    }
}

// ============ FUNCIÓN AUXILIAR: PARABOLIC SAR ============
function calculateParabolicSAR(high, low, acceleration = 0.02, maxAcceleration = 0.2) {
    const n = high.length;
    const sar = new Array(n).fill(0);
    const ep = new Array(n).fill(0);  // Extreme Point
    const af = new Array(n).fill(acceleration);  // Acceleration Factor
    const trend = new Array(n).fill(1);  // 1 = alcista, -1 = bajista
    
    if (n === 0) return sar;
    
    // Inicialización
    sar[0] = low[0];
    ep[0] = high[0];
    trend[0] = 1;
    
    for (let i = 1; i < n; i++) {
        if (trend[i-1] === 1) {  // Tendencia alcista
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1]);
            
            if (high[i] > ep[i-1]) {
                ep[i] = high[i];
                af[i] = Math.min(af[i-1] + acceleration, maxAcceleration);
            } else {
                ep[i] = ep[i-1];
                af[i] = af[i-1];
            }
            
            if (low[i] < sar[i]) {
                trend[i] = -1;
                sar[i] = ep[i-1];
                ep[i] = low[i];
                af[i] = acceleration;
            } else {
                trend[i] = 1;
            }
        } else {  // Tendencia bajista
            sar[i] = sar[i-1] - af[i-1] * (sar[i-1] - ep[i-1]);
            
            if (low[i] < ep[i-1]) {
                ep[i] = low[i];
                af[i] = Math.min(af[i-1] + acceleration, maxAcceleration);
            } else {
                ep[i] = ep[i-1];
                af[i] = af[i-1];
            }
            
            if (high[i] > sar[i]) {
                trend[i] = 1;
                sar[i] = ep[i-1];
                ep[i] = high[i];
                af[i] = acceleration;
            } else {
                trend[i] = -1;
            }
        }
    }
    
    return sar;
}
// ============ Bandas de Bollinger ============
function updateBollingerChart(data) {
    const chartDiv = document.getElementById('bollinger-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const open = df.open || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    if (dates.length < 20) return;
    
    const bb = calculateBollingerBands(close);
    const lastDates = dates.slice(-50);
    const lastOpen = open.slice(-50);
    const lastHigh = high.slice(-50);
    const lastLow = low.slice(-50);
    const lastClose = close.slice(-50);
    const lastUpper = bb.upper.slice(-50);
    const lastMiddle = bb.middle.slice(-50);
    const lastLower = bb.lower.slice(-50);
    
    const traces = [
        {
            x: lastDates,
            open: lastOpen,
            high: lastHigh,
            low: lastLow,
            close: lastClose,
            type: 'candlestick',
            name: 'Precio',
            increasing: {line: {color: '#00C076', width: 1}, fillcolor: '#00C076'},
            decreasing: {line: {color: '#FF5B5B', width: 1}, fillcolor: '#FF5B5B'},
            showlegend: true,
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastUpper,
            type: 'scatter',
            mode: 'lines',
            name: 'Banda Superior',
            line: {color: '#FF5B5B', width: 1.5, dash: 'dash'},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastMiddle,
            type: 'scatter',
            mode: 'lines',
            name: 'Media (20)',
            line: {color: '#FFD700', width: 1.5},
            yaxis: 'y'
        },
        {
            x: lastDates,
            y: lastLower,
            type: 'scatter',
            mode: 'lines',
            name: 'Banda Inferior',
            line: {color: '#00C076', width: 1.5, dash: 'dash'},
            fill: 'tonexty',
            fillcolor: 'rgba(128,128,128,0.1)',
            yaxis: 'y'
        }
    ];
    
    const layout = {
        title: {
            text: 'Bandas de Bollinger con Velas',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false}
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 30},
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 10},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        }
    };
    
    Plotly.newPlot('bollinger-chart', traces, layout, {responsive: true, displaylogo: false});
}

// ============ ATR ============
function updateATRChart(data) {
    const chartDiv = document.getElementById('atr-chart');
    if (!chartDiv || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const close = df.close || [];
    
    const atr = calculateATRArray(high, low, close);
    const atrPct = atr.map((v, i) => (v / close[i]) * 100 || 0);
    
    const trace = {
        x: dates.slice(-50),
        y: atrPct.slice(-50),
        type: 'scatter',
        mode: 'lines',
        name: 'ATR %',
        line: {color: '#FFD700', width: 2},
        fill: 'tozeroy',
        fillcolor: 'rgba(255,215,0,0.1)'
    };
    
    const layout = {
        title: {
            text: 'ATR - Volatilidad',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        yaxis: {
            title: 'ATR %',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)'
        },
        template: 'plotly_dark',
        height: 300,
        margin: {l: 50, r: 50, t: 50, b: 30},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        }
    };
    
    Plotly.newPlot('atr-chart', [trace], layout, {responsive: true, displaylogo: false});
}

// ============ PERFIL DE VOLUMEN CON POC - EJE X CORREGIDO ============
function updateVolumeProfileChart(data) {
    const chartDiv = document.getElementById('volume-profile-chart');
    if (!chartDiv) {
        const container = document.getElementById('indicators-container');
        if (!container) return;
        
        const newCard = document.createElement('div');
        newCard.className = 'card bg-dark border-warning mb-4 indicator-card';
        newCard.setAttribute('data-indicator', 'volume-profile');
        newCard.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <i class="fas fa-chart-bar me-2" style="color: #FFD700;"></i>
                    Perfil de Volumen con POC
                </h5>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary btn-move" data-direction="up">
                        <i class="fas fa-arrow-up"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-move" data-direction="down">
                        <i class="fas fa-arrow-down"></i>
                    </button>
                    <button class="btn btn-outline-secondary btn-collapse" data-collapsed="false">
                        <i class="fas fa-minus"></i>
                    </button>
                </div>
            </div>
            <div class="card-body indicator-content">
                <div id="volume-profile-chart" style="height: 350px;"></div>
                <div class="mt-2">
                    <small class="text-muted">
                        <strong>Interpretación:</strong> 
                        <span style="color: #FFD700;">Línea dorada = POC (Point of Control)</span> - Zona de mayor volumen.
                        <span style="color: #3A8BFF;">Líneas azules = Value Area (VAH/VAL)</span>
                        <span id="volume-profile-interpretation" class="ms-2">Calculando perfil...</span>
                    </small>
                </div>
            </div>
        `;
        container.appendChild(newCard);
        
        if (typeof window.initializeEventListeners === 'function') {
            window.initializeEventListeners();
        }
    }
    
    if (!data || !data.df) return;
    
    const df = data.df;
    const dates = df.time || [];
    const high = df.high || [];
    const low = df.low || [];
    const volume = df.volume || [];
    const open = df.open || [];
    const close = df.close || [];
    
    if (dates.length < 30) return;
    
    // Convertir fechas a objetos Date
    const dateObjects = dates.map(d => new Date(d));
    
    // Últimas 50 velas para el análisis
    const lastDates = dateObjects.slice(-50);
    const lastOpen = open.slice(-50);
    const lastHigh = high.slice(-50);
    const lastLow = low.slice(-50);
    const lastClose = close.slice(-50);
    const lastVolume = volume.slice(-50);
    
    // ============ CREAR PERFIL DE VOLUMEN ============
    const minPrice = Math.min(...lastLow);
    const maxPrice = Math.max(...lastHigh);
    const priceRange = maxPrice - minPrice;
    
    const numBuckets = 30;
    const bucketSize = priceRange / numBuckets;
    const buckets = new Array(numBuckets).fill(0);
    const bucketCenters = [];
    
    for (let i = 0; i < numBuckets; i++) {
        bucketCenters.push(minPrice + (i + 0.5) * bucketSize);
    }
    
    for (let i = 0; i < lastDates.length; i++) {
        const candleHigh = lastHigh[i];
        const candleLow = lastLow[i];
        const candleVolume = lastVolume[i];
        const candleRange = candleHigh - candleLow;
        
        if (candleRange <= 0) continue;
        
        for (let b = 0; b < numBuckets; b++) {
            const bucketLow = minPrice + b * bucketSize;
            const bucketHigh = bucketLow + bucketSize;
            
            if (candleHigh > bucketLow && candleLow < bucketHigh) {
                const overlap = Math.min(candleHigh, bucketHigh) - Math.max(candleLow, bucketLow);
                if (overlap > 0) {
                    buckets[b] += candleVolume * (overlap / candleRange);
                }
            }
        }
    }
    
    const maxVolume = Math.max(...buckets);
    const pocIndex = buckets.indexOf(maxVolume);
    const pocPrice = minPrice + (pocIndex + 0.5) * bucketSize;
    
    const totalVolume = buckets.reduce((a, b) => a + b, 0);
    const targetVolume = totalVolume * 0.7;
    let accumulatedVolume = buckets[pocIndex];
    let valIndex = pocIndex;
    let vahIndex = pocIndex;
    
    let expandDown = true;
    let expandUp = true;
    
    while (accumulatedVolume < targetVolume && (expandDown || expandUp)) {
        if (expandDown && valIndex > 0) {
            valIndex--;
            accumulatedVolume += buckets[valIndex];
        } else {
            expandDown = false;
        }
        
        if (accumulatedVolume >= targetVolume) break;
        
        if (expandUp && vahIndex < numBuckets - 1) {
            vahIndex++;
            accumulatedVolume += buckets[vahIndex];
        } else {
            expandUp = false;
        }
    }
    
    const valPrice = minPrice + (valIndex + 0.5) * bucketSize;
    const vahPrice = minPrice + (vahIndex + 0.5) * bucketSize;
    
    // ============ AJUSTE DE EJE X - SOLO 1% ADICIONAL ============
    const timeRange = lastDates[lastDates.length - 1].getTime() - lastDates[0].getTime();
    const extraSpace = timeRange * 0.01; // Solo 1% de espacio extra
    const farRightEdge = new Date(lastDates[lastDates.length - 1].getTime() + extraSpace);
    
    // Ancho máximo de barras: 15% del rango de tiempo
    const maxBarWidth = timeRange * 0.15;
    
    const traces = [];
    
    // Traza 1: Velas Japonesas
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1.5}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1.5}, fillcolor: '#FF5B5B'},
        showlegend: true,
        yaxis: 'y'
    });
    
    // Traza 2: Perfil de Volumen (barras horizontales)
    for (let b = 0; b < numBuckets; b++) {
        const barLength = (buckets[b] / maxVolume) * maxBarWidth;
        
        if (barLength > 0) {
            const rightEdge = new Date(lastDates[lastDates.length - 1].getTime() + barLength * 0.1);
            const leftEdge = new Date(rightEdge.getTime() - barLength);
            
            let color;
            if (b === pocIndex) {
                color = '#FFD700';
            } else if (b >= valIndex && b <= vahIndex) {
                color = '#3A8BFF';
            } else {
                color = 'rgba(58,139,255,0.2)';
            }
            
            traces.push({
                x: [leftEdge, rightEdge],
                y: [bucketCenters[b], bucketCenters[b]],
                type: 'scatter',
                mode: 'lines',
                line: {
                    color: color,
                    width: b === pocIndex ? 6 : 3
                },
                showlegend: false,
                hoverinfo: 'none',
                yaxis: 'y'
            });
        }
    }
    
    // Línea del POC
    traces.push({
        x: [lastDates[0], farRightEdge],
        y: [pocPrice, pocPrice],
        type: 'scatter',
        mode: 'lines',
        name: 'POC',
        line: {
            color: '#FFD700',
            width: 2,
            dash: 'dash'
        },
        showlegend: true,
        yaxis: 'y'
    });
    
    // Línea VAH
    traces.push({
        x: [lastDates[0], farRightEdge],
        y: [vahPrice, vahPrice],
        type: 'scatter',
        mode: 'lines',
        name: 'VAH',
        line: {
            color: '#3A8BFF',
            width: 1.5,
            dash: 'dot'
        },
        showlegend: true,
        yaxis: 'y'
    });
    
    // Línea VAL
    traces.push({
        x: [lastDates[0], farRightEdge],
        y: [valPrice, valPrice],
        type: 'scatter',
        mode: 'lines',
        name: 'VAL',
        line: {
            color: '#3A8BFF',
            width: 1.5,
            dash: 'dot'
        },
        showlegend: true,
        yaxis: 'y'
    });
    
    const layout = {
        title: {
            text: 'Perfil de Volumen con POC (Point of Control)',
            font: {color: 'white', size: 14}
        },
        xaxis: {
            type: 'date',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            rangeslider: {visible: false},
            range: [lastDates[0], farRightEdge]
        },
        yaxis: {
            title: 'Precio',
            gridcolor: 'rgba(128,128,128,0.2)',
            gridwidth: 0.5,
            showgrid: true,
            showline: true,
            mirror: true,
            linecolor: 'rgba(128,128,128,0.5)',
            fixedrange: false,
            autorange: true
        },
        template: 'plotly_dark',
        height: 350,
        margin: {l: 50, r: 50, t: 50, b: 50},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        hovermode: 'x unified',
        hoverlabel: {
            bgcolor: '#0A0C10',
            bordercolor: 'rgba(255,255,255,0.2)',
            font: {color: 'white', size: 11}
        },
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: 1.02,
            xanchor: 'right',
            x: 1,
            font: {color: 'white', size: 9},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        }
    };
    
    Plotly.newPlot('volume-profile-chart', traces, layout, {responsive: true, displaylogo: false});
    
    const interpretation = document.getElementById('volume-profile-interpretation');
    if (interpretation) {
        const pocVolume = (buckets[pocIndex] / 1000).toFixed(0);
        const valueAreaWidth = ((vahPrice - valPrice) / pocPrice * 100).toFixed(1);
        interpretation.innerHTML = `POC en $${pocPrice.toFixed(2)} (${pocVolume}K vol) | Value Area: $${valPrice.toFixed(2)} - $${vahPrice.toFixed(2)} (${valueAreaWidth}% ancho)`;
    }
}
// ============ FUNCIONES DE CÁLCULO ============
function calculateFTMaverick(prices) {
    const n = prices.length;
    const period = 20;
    const bb_width = new Array(n).fill(0);
    const trend_strength = new Array(n).fill(0);
    
    for (let i = period - 1; i < n; i++) {
        const window = prices.slice(i - period + 1, i + 1);
        const mean = window.reduce((a, b) => a + b, 0) / period;
        const std = Math.sqrt(window.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period) || 1;
        const upper = mean + std * 2;
        const lower = mean - std * 2;
        bb_width[i] = ((upper - lower) / mean) * 100 || 0;
        if (i > 0) {
            trend_strength[i] = bb_width[i] > bb_width[i-1] ? bb_width[i] : -bb_width[i];
        }
    }
    return {bb_width, trend_strength};
}

// Modificar también la función de cálculo
function calculateRSIMaverick(prices, length = 20, mult = 2.0) {
    const n = prices.length;
    const result = new Array(n).fill(0.5);
    
    for (let i = length - 1; i < n; i++) {
        const window = prices.slice(i - length + 1, i + 1);
        const mean = window.reduce((a, b) => a + b, 0) / length;
        
        // Calcular desviación estándar
        let sumSq = 0;
        for (let j = 0; j < window.length; j++) {
            sumSq += Math.pow(window[j] - mean, 2);
        }
        const std = Math.sqrt(sumSq / length) || 1;
        
        const upper = mean + std * mult;
        const lower = mean - std * mult;
        
        // %B puede ser >1 o <0
        if (upper !== lower) {
            result[i] = (prices[i] - lower) / (upper - lower);
        } else {
            result[i] = 0.5;
        }
    }
    return result;
}
function calculateSqueezeMomentum(high, low, close) {
    const n = high.length;
    const period = 20;
    const momentum = new Array(n).fill(0);
    
    for (let i = period; i < n; i++) {
        const highest = Math.max(...high.slice(i - period + 1, i + 1));
        const lowest = Math.min(...low.slice(i - period + 1, i + 1));
        const avg = (highest + lowest) / 2;
        momentum[i] = close[i] - avg;
    }
    return {momentum};
}

function calculateMACD(close) {
    const n = close.length;
    const fast = 12, slow = 26, signal = 9;
    const macd = new Array(n).fill(0);
    const signalLine = new Array(n).fill(0);
    const histogram = new Array(n).fill(0);
    
    const emaFast = calculateEMA(close, fast);
    const emaSlow = calculateEMA(close, slow);
    
    for (let i = 0; i < n; i++) {
        macd[i] = (emaFast[i] - emaSlow[i]) || 0;
    }
    
    const emaSignal = calculateEMA(macd, signal);
    for (let i = 0; i < n; i++) {
        signalLine[i] = emaSignal[i] || 0;
        histogram[i] = macd[i] - signalLine[i] || 0;
    }
    
    return {macd, signal: signalLine, histogram};
}

function calculateRSI(prices) {
    const n = prices.length;
    const period = 14;
    const rsi = new Array(n).fill(50);
    
    for (let i = period; i < n; i++) {
        let gains = 0, losses = 0;
        for (let j = i - period + 1; j <= i; j++) {
            const change = prices[j] - prices[j-1];
            if (change > 0) gains += change;
            else losses -= change;
        }
        const rs = gains / (losses || 1);
        rsi[i] = 100 - 100 / (1 + rs);
    }
    return rsi;
}

function calculateStochastic(high, low, close) {
    const n = high.length;
    const period = 14;
    const k = new Array(n).fill(50);
    const d = new Array(n).fill(50);
    
    for (let i = period - 1; i < n; i++) {
        const highest = Math.max(...high.slice(i - period + 1, i + 1));
        const lowest = Math.min(...low.slice(i - period + 1, i + 1));
        k[i] = ((close[i] - lowest) / (highest - lowest || 1)) * 100;
    }
    
    for (let i = period + 2; i < n; i++) {
        d[i] = (k[i] + k[i-1] + k[i-2]) / 3;
    }
    
    return {k, d};
}

function calculateSuperTrend(high, low, close) {
    const n = high.length;
    const period = 10;
    const multiplier = 3;
    const supertrend = new Array(n).fill(0);
    const trend = new Array(n).fill(1);
    
    for (let i = period; i < n; i++) {
        const atr = calculateATR(high, low, close, i, period);
        const hl = (high[i] + low[i]) / 2;
        const upper = hl + multiplier * atr;
        const lower = hl - multiplier * atr;
        
        if (i === period) {
            supertrend[i] = upper;
            trend[i] = -1;
        } else {
            if (close[i] <= supertrend[i-1] && trend[i-1] === 1) {
                trend[i] = -1;
                supertrend[i] = upper;
            } else if (close[i] >= supertrend[i-1] && trend[i-1] === -1) {
                trend[i] = 1;
                supertrend[i] = lower;
            } else {
                trend[i] = trend[i-1];
                supertrend[i] = supertrend[i-1];
            }
        }
    }
    
    return {supertrend, trend};
}

function calculateBollingerBands(close) {
    const n = close.length;
    const period = 20;
    const upper = new Array(n).fill(0);
    const middle = new Array(n).fill(0);
    const lower = new Array(n).fill(0);
    
    for (let i = period - 1; i < n; i++) {
        const window = close.slice(i - period + 1, i + 1);
        const mean = window.reduce((a, b) => a + b, 0) / period;
        const std = Math.sqrt(window.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period) || 0;
        middle[i] = mean;
        upper[i] = mean + std * 2;
        lower[i] = mean - std * 2;
    }
    
    return {upper, middle, lower};
}

function calculateATR(high, low, close, idx, period) {
    let trSum = 0;
    for (let i = idx - period + 1; i <= idx; i++) {
        if (i > 0) {
            const hl = high[i] - low[i];
            const hc = Math.abs(high[i] - close[i-1]);
            const lc = Math.abs(low[i] - close[i-1]);
            trSum += Math.max(hl, hc, lc);
        }
    }
    return trSum / period;
}

function calculateATRArray(high, low, close) {
    const n = high.length;
    const period = 14;
    const atr = new Array(n).fill(0);
    
    for (let i = period; i < n; i++) {
        atr[i] = calculateATR(high, low, close, i, period);
    }
    return atr;
}

function calculateEMA(prices, period) {
    const n = prices.length;
    const ema = new Array(n).fill(prices[0] || 0);
    const alpha = 2 / (period + 1);
    
    for (let i = 1; i < n; i++) {
        ema[i] = (prices[i] * alpha + ema[i-1] * (1 - alpha)) || 0;
    }
    return ema;
}

// ============ UPDATE ALL CHARTS ============
function updateAllCharts(data) {
    if (!data || !data.df) {
        console.warn('No hay datos para actualizar gráficos');
        return;
    }
    
    console.log('Actualizando todos los gráficos...');
    
    // ============ GRÁFICOS EXISTENTES ============
    updateCandleChart(data);
    updateFibonacciChart(data);
    updateFTMChart(data);
    updateWhaleChart(data);
    updateRSIMaverickChart(data);
    updateIchimokuChart(data);
    updateSqueezeChart(data);
    updateADXChart(data);
    updateMACDChart(data);
    updateRSIChart(data);
    updateStochasticChart(data);
    updateSuperTrendChart(data);
    updateBollingerChart(data);
    updateATRChart(data);
    
    // ============ GRÁFICOS FUSIONADOS ============
    updateVolumeChart(data);
    updateVolumeProfileChart(data);
    updateFVGAOBChart(data);
    updateWilliamsCCIChart(data);
    updateMFIForceChart(data);
    
    // ============ NUEVO GRÁFICO FEAR & GREED ============
    if (typeof window.updateFearGreedChart === 'function') {
        window.updateFearGreedChart(data);
        console.log('✅ Gráfico Fear & Greed actualizado');
    } else {
        console.warn('⚠️ updateFearGreedChart no está disponible');
    }
    
    // ============ NUEVO: MAPA DE CALOR DE LIQUIDACIONES ============
    updateLiquidationHeatmap(data);  // <--- AÑADIR ESTA LÍNEA
    // ============ NUEVO: ZONAS DINÁMICAS DE TRADING ============
    updateTradingZones(data); //Se añadio esta linea    
    // ============ ACTUALIZAR INFORMACIÓN DE CORRELACIÓN ============
    if (typeof window.updateCorrelationInfo === 'function') {
        window.updateCorrelationInfo(data);
        console.log('✅ Correlación actualizada');
    } else {
        console.warn('⚠️ updateCorrelationInfo no está disponible');
    }
}


// ============ NUEVO: MAPA DE CALOR DE LIQUIDACIONES ============
// Ubicación: DESPUÉS de la función updateAllCharts

// ============ MAPA DE CALOR DE LIQUIDACIONES (VERSIÓN CORREGIDA - CONSERVA VISIBILIDAD) ============

function updateLiquidationHeatmap(data) {
    console.log('🔥 EJECUTANDO updateLiquidationHeatmap');
    
    const chartDiv = document.getElementById('liquidation-heatmap-chart');
    if (!chartDiv) return;
    
    // Limpiar completamente
    chartDiv.innerHTML = '';
    Plotly.purge('liquidation-heatmap-chart');
    
    // Buscar datos
    let liquidation = data.liquidation || (data.data && data.data.liquidation);
    if (!liquidation) {
        chartDiv.innerHTML = '<div class="text-center py-4"><p class="text-muted">No hay datos de liquidaciones</p></div>';
        return;
    }
    
    const activeBins = liquidation.active_bins || [];
    const frozenBins = liquidation.frozen_bins || [];
    const timeframe = data.timeframe || '4h';
    
    console.log(`🔥 Bins activos: ${activeBins.length}, Congelados: ${frozenBins.length}, Timeframe: ${timeframe}`);
    
    // Calcular pesos totales
    let totalLongWeight = 0;
    let totalShortWeight = 0;
    
    activeBins.forEach(bin => {
        if (bin.side === 'long') {
            totalLongWeight += bin.weight;
        } else {
            totalShortWeight += bin.weight;
        }
    });
    
    // Actualizar estadísticas
    document.getElementById('liquidation-long-weight').innerHTML = `${(totalLongWeight).toFixed(1)}M`;
    document.getElementById('liquidation-short-weight').innerHTML = `${(totalShortWeight).toFixed(1)}M`;
    document.getElementById('liquidation-active-bins').innerHTML = activeBins.length;
    document.getElementById('liquidation-frozen-bins').innerHTML = frozenBins.length;
    
    // Interpretación
    let interpretation = '';
    if (totalLongWeight > totalShortWeight * 2) {
        interpretation = '🔥 FUERTE SOPORTE LONG - Zona de acumulación';
    } else if (totalShortWeight > totalLongWeight * 2) {
        interpretation = '🔥 FUERTE RESISTENCIA SHORT - Zona de distribución';
    } else if (totalLongWeight > totalShortWeight * 1.5) {
        interpretation = '🟢 DOMINANCIA LONG - Soportes probables';
    } else if (totalShortWeight > totalLongWeight * 1.5) {
        interpretation = '🔴 DOMINANCIA SHORT - Resistencias probables';
    } else {
        interpretation = '📊 Múltiples zonas de liquidez';
    }
    document.getElementById('liquidation-interpretation').innerHTML = interpretation;
    
    // ============ PREPARAR DATOS DE VELAS ============
    const df = data.df || (data.data && data.data.df);
    if (!df || !df.time || df.time.length === 0) {
        console.log('❌ No hay datos de velas');
        return;
    }
    
    const dates = df.time.map(d => new Date(d));
    
    // ============ CALCULAR RANGO VISUAL SEGÚN TEMPORALIDAD ============
    let maxBars;
    switch(timeframe) {
        case '4h': maxBars = 300; break;
        case '12h': maxBars = 200; break;
        case '1D': maxBars = 150; break;
        case '1W': maxBars = 100; break;
        default: maxBars = 300;
    }
    
    maxBars = Math.min(maxBars, dates.length);
    const lastDates = dates.slice(-maxBars);
    const lastOpen = df.open.slice(-maxBars);
    const lastHigh = df.high.slice(-maxBars);
    const lastLow = df.low.slice(-maxBars);
    const lastClose = df.close.slice(-maxBars);
    
    console.log(`📊 Mostrando ${maxBars} velas para ${timeframe}`);
    
    // ============ AMPLIAR EL ESPACIO DEL GRÁFICO (30% DE PADDING) ============
    const minPrice = Math.min(...lastLow);
    const maxPrice = Math.max(...lastHigh);
    const priceRange = maxPrice - minPrice;
    const padding = priceRange * 0.30;  // 30% de espacio extra (ANTES ERA 5%)
    
    // ============ PREPARAR TRAZAS Y FORMAS ============
    const traces = [];
    const shapes = [];
    
    // SOLO UNA traza de velas
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: { line: { color: '#00C076', width: 1 }, fillcolor: '#00C076' },
        decreasing: { line: { color: '#FF5B5B', width: 1 }, fillcolor: '#FF5B5B' },
        yaxis: 'y'
    });
    
    // Calcular el peso máximo para el gradiente
    const allWeights = activeBins.map(b => b.weight);
    const maxWeight = allWeights.length > 0 ? Math.max(...allWeights) : 1;
    
    // ============ DIBUJAR BINS ACTIVOS (SIN FILTRO DE PESO MÍNIMO) ============
    activeBins.forEach(bin => {
        const startDate = new Date(lastDates[0]);
        const endDate = new Date(lastDates[lastDates.length - 1]);
        
        // Determinar color basado en el peso
        const ratio = bin.weight / maxWeight;
        let fillColor;
        
        if (ratio > 0.8) {
            fillColor = 'rgba(255, 0, 0, 0.6)';
        } else if (ratio > 0.6) {
            fillColor = 'rgba(255, 165, 0, 0.5)';
        } else if (ratio > 0.4) {
            fillColor = 'rgba(255, 255, 0, 0.4)';
        } else if (ratio > 0.2) {
            fillColor = 'rgba(144, 238, 144, 0.3)';
        } else {
            fillColor = 'rgba(0, 100, 0, 0.2)';
        }
        
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: startDate,
            x1: endDate,
            y0: bin.price_bottom,
            y1: bin.price_top,
            fillcolor: fillColor,
            line: { width: 0 },
            layer: 'below'
        });
    });
    
    // ============ DIBUJAR BINS CONGELADOS (MÁS VISIBLES) ============
    frozenBins.slice(-200).forEach(bin => {
        const startDate = new Date(lastDates[0]);
        const endDate = new Date(lastDates[lastDates.length - 1]);
        
        // Color más visible para congelados
        let fillColor;
        if (bin.side === 'long') {
            fillColor = 'rgba(0, 255, 0, 0.1)';  // Aumentado de 0.05 a 0.1
        } else {
            fillColor = 'rgba(255, 0, 0, 0.1)';  // Aumentado de 0.05 a 0.1
        }
        
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: startDate,
            x1: endDate,
            y0: bin.price_bottom,
            y1: bin.price_top,
            fillcolor: fillColor,
            line: { color: 'rgba(255,255,255,0.2)', width: 0.5, dash: 'dot' },
            layer: 'below'
        });
    });
    
    // Línea del precio actual (sutil)
    const currentPrice = data.current_price || lastClose[lastClose.length - 1];
    shapes.push({
        type: 'line',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: currentPrice,
        y1: currentPrice,
        line: { color: 'rgba(255, 215, 0, 0.3)', width: 1 },
        layer: 'above'
    });
    
    // ============ LAYOUT FINAL CON 30% DE PADDING ============
    const layout = {
        title: {
            text: `Mapa de Calor de Liquidaciones (${timeframe}) - ${activeBins.length} zonas activas, ${frozenBins.length} congeladas`,
            font: { color: 'white', size: 14 }
        },
        xaxis: {
            type: 'date',
            range: [lastDates[0], lastDates[lastDates.length - 1]],
            showgrid: true,
            gridcolor: 'rgba(128,128,128,0.2)',
            title: 'Fecha/Hora'
        },
        yaxis: {
            title: 'Precio',
            range: [minPrice - padding, maxPrice + padding],  // 30% de padding
            showgrid: true,
            gridcolor: 'rgba(128,128,128,0.2)',
            tickformat: ',.0f'
        },
        template: 'plotly_dark',
        height: 450,
        margin: { l: 60, r: 60, t: 50, b: 50 },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        shapes: shapes,
        showlegend: false
    };
    
    try {
        Plotly.newPlot('liquidation-heatmap-chart', traces, layout, { 
            responsive: true,
            displaylogo: false 
        });
        console.log(`✅ Gráfico de liquidaciones ${timeframe}: ${activeBins.length} activos, ${frozenBins.length} congelados`);
    } catch (error) {
        console.error('❌ Error al crear gráfico:', error);
        chartDiv.innerHTML = '<div class="alert alert-danger">Error al generar gráfico</div>';
    }
}

// ============ ZONAS DINÁMICAS DE TRADING ============
function updateTradingZones(data) {
    console.log('🎯 EJECUTANDO updateTradingZones');
    
    const chartDiv = document.getElementById('trading-zones-chart');
    if (!chartDiv) return;
    
    chartDiv.innerHTML = '';
    Plotly.purge('trading-zones-chart');
    
    let zones = data.zones || (data.data && data.data.zones);
    if (!zones || !zones.active_zones) {
        console.log('❌ No hay datos de zonas');
        return;
    }
    
    const activeZones = zones.active_zones;
    const priceStatus = zones.price_status || {};
    const timeframe = data.timeframe || '4h';
    const decision = data.decision?.action || 'NO_OPERAR';
    
    console.log(`🎯 Zonas activas: ${Object.keys(activeZones).length}`);
    
    // ============ GENERAR JUSTIFICACIONES (TODOS LOS INDICADORES) ============
    const zoneJustification = {};
    
    // Extraer datos
    const trend = data.trend || {};
    const momentum = data.momentum || {};
    const structure = data.structure || {};
    const volume = data.volume || {};
    const liquidation = data.liquidation || {};
    
    // DMI
    const adx = trend.adx || 0;
    const plusDI = trend.plus_di || 0;
    const minusDI = trend.minus_di || 0;
    
    // RSI
    const rsi = momentum.indicators?.rsi || 50;
    const rsiM = momentum.indicators?.rsi_maverick || 0.5;
    
    // MACD
    const macdHist = momentum.indicators?.macd_histogram || 0;
    
    // Estocástico
    const stochK = momentum.indicators?.stoch_k || 50;
    
    // Divergencias
    const divergencias = momentum.divergences || [];
    
    // Soportes/Resistencias
    const soporte = structure.nearest_support;
    const resistencia = structure.nearest_resistance;
    
    // POC
    const poc = structure.volume_profile?.poc;
    
    // Ballenas
    const whaleBuy = volume.whale_buy || false;
    const whaleSell = volume.whale_sell || false;
    
    // MFI
    const mfi = volume.mfi || 50;
    
    // OBV
    const obvTrend = volume.obv_trend || 'neutral';
    
    // FTMaverick
    const ftmState = data.volatility?.ftm_state || '';
    
    // Liquidaciones
    const longWeight = liquidation.total_long_weight || 0;
    const shortWeight = liquidation.total_short_weight || 0;
    
    // ============ ZONA COMPRA ============
    if (activeZones.COMPRA) {
        let indicadores = [];
        
        if (plusDI > minusDI && adx > 25) indicadores.push(`DMI alcista`);
        if (rsi > 50) indicadores.push(`RSI ${rsi.toFixed(1)}`);
        if (rsiM < 0.3) indicadores.push(`RSI-M ${rsiM.toFixed(2)}`);
        if (macdHist > 0) indicadores.push(`MACD +${macdHist.toFixed(1)}`);
        if (stochK < 20) indicadores.push(`Estocástico ${stochK.toFixed(1)}`);
        if (divergencias.some(d => d.includes('bull'))) indicadores.push(`Divergencia alcista`);
        
        const fvgAlcistas = structure.fair_value_gaps?.filter(f => f.type === 'bullish' && !f.filled) || [];
        if (fvgAlcistas.length > 0) indicadores.push(`${fvgAlcistas.length} FVG`);
        
        const obAlcistas = structure.order_blocks?.filter(ob => ob.type === 'bullish') || [];
        if (obAlcistas.length > 0) indicadores.push(`${obAlcistas.length} OB`);
        
        if (soporte) indicadores.push(`Soporte $${soporte.toFixed(0)}`);
        if (poc && poc < data.current_price) indicadores.push(`POC $${poc.toFixed(0)}`);
        if (whaleBuy) indicadores.push(`Ballenas`);
        if (mfi < 40) indicadores.push(`MFI ${mfi.toFixed(1)}`);
        if (obvTrend === 'bullish') indicadores.push(`OBV`);
        if (ftmState === 'STRONG_UP') indicadores.push(`FTM`);
        if (longWeight > shortWeight * 1.5) indicadores.push(`Liq LONG`);
        
        zoneJustification['COMPRA'] = indicadores.join(' · ') || 'Consenso alcista';
    }
    
    // ============ ZONA VENTA ============
    if (activeZones.VENTA) {
        let indicadores = [];
        
        if (minusDI > plusDI && adx > 25) indicadores.push(`DMI bajista`);
        if (rsi < 50) indicadores.push(`RSI ${rsi.toFixed(1)}`);
        if (rsiM > 0.7) indicadores.push(`RSI-M ${rsiM.toFixed(2)}`);
        if (macdHist < 0) indicadores.push(`MACD ${macdHist.toFixed(1)}`);
        if (stochK > 80) indicadores.push(`Estocástico ${stochK.toFixed(1)}`);
        if (divergencias.some(d => d.includes('bear'))) indicadores.push(`Divergencia bajista`);
        
        const fvgBajistas = structure.fair_value_gaps?.filter(f => f.type === 'bearish' && !f.filled) || [];
        if (fvgBajistas.length > 0) indicadores.push(`${fvgBajistas.length} FVG`);
        
        const obBajistas = structure.order_blocks?.filter(ob => ob.type === 'bearish') || [];
        if (obBajistas.length > 0) indicadores.push(`${obBajistas.length} OB`);
        
        if (resistencia) indicadores.push(`Resistencia $${resistencia.toFixed(0)}`);
        if (poc && poc > data.current_price) indicadores.push(`POC $${poc.toFixed(0)}`);
        if (whaleSell) indicadores.push(`Ballenas`);
        if (mfi > 60) indicadores.push(`MFI ${mfi.toFixed(1)}`);
        if (obvTrend === 'bearish') indicadores.push(`OBV`);
        if (ftmState === 'STRONG_DOWN') indicadores.push(`FTM`);
        if (shortWeight > longWeight * 1.5) indicadores.push(`Liq SHORT`);
        
        zoneJustification['VENTA'] = indicadores.join(' · ') || 'Consenso bajista';
    }
    
    // ============ ZONA LONG (PRECISIÓN) ============
    if (activeZones.LONG) {
        let indicadores = [];
        
        if (adx > 30 && plusDI > minusDI) indicadores.push('Tendencia');
        if (rsi > 55) indicadores.push('RSI');
        if (rsiM < 0.25) indicadores.push('RSI-M');
        if (soporte) indicadores.push('Soporte');
        if (whaleBuy) indicadores.push('Ballenas');
        if (longWeight > shortWeight * 2) indicadores.push('Liquidez');
        
        zoneJustification['LONG'] = indicadores.join(' · ') || 'Zona LONG';
    }
    
    // ============ ZONA SHORT (PRECISIÓN) ============
    if (activeZones.SHORT) {
        let indicadores = [];
        
        if (adx > 30 && minusDI > plusDI) indicadores.push('Tendencia');
        if (rsi < 45) indicadores.push('RSI');
        if (rsiM > 0.75) indicadores.push('RSI-M');
        if (resistencia) indicadores.push('Resistencia');
        if (whaleSell) indicadores.push('Ballenas');
        if (shortWeight > longWeight * 2) indicadores.push('Liquidez');
        
        zoneJustification['SHORT'] = indicadores.join(' · ') || 'Zona SHORT';
    }
    
    updateZoneStatusCard(activeZones, priceStatus, data.current_price, decision, zoneJustification);
    
    // ============ DATOS DE VELAS ============
    const df = data.df || (data.data && data.data.df);
    if (!df || !df.time || df.time.length === 0) {
        console.log('❌ No hay datos de velas');
        return;
    }
    
    const dates = df.time.map(d => new Date(d));
    
    // ============ 70 VELAS VISIBLES ============
    const maxBars = 70;
    const lastDates = dates.slice(-maxBars);
    const lastOpen = df.open.slice(-maxBars);
    const lastHigh = df.high.slice(-maxBars);
    const lastLow = df.low.slice(-maxBars);
    const lastClose = df.close.slice(-maxBars);
    
    console.log(`📊 Mostrando ${maxBars} velas para ${timeframe}`);
    
    const barWidth = lastDates.length > 1 ? 
        (lastDates[lastDates.length - 1].getTime() - lastDates[lastDates.length - 2].getTime()) : 
        3600000;
    
    // ============ CORRECCIÓN: ANCHO DE ZONAS ============
    // Zonas COMPRA/VENTA: 40 velas atrás + 10 velas adelante = 50 velas
    const buySellPastBars = 40;
    const buySellFutureBars = 10;
    
    // Zonas LONG/SHORT: 10 velas atrás + 4 velas adelante = 14 velas
    const longShortPastBars = 10;
    const longShortFutureBars = 4;
    
    const currentIndex = lastDates.length - 1; // Última vela visible
    
    let minPrice = Math.min(...lastLow);
    let maxPrice = Math.max(...lastHigh);
    
    Object.keys(activeZones).forEach(zoneType => {
        const zone = activeZones[zoneType];
        if (zone) {
            minPrice = Math.min(minPrice, zone.price_min);
            maxPrice = Math.max(maxPrice, zone.price_max);
        }
    });
    
    const priceRange = maxPrice - minPrice;
    const padding = priceRange * 0.10;
    
    // ============ TRAZAS Y FORMAS ============
    const traces = [];
    const shapes = [];
    
    traces.push({
        x: lastDates,
        open: lastOpen,
        high: lastHigh,
        low: lastLow,
        close: lastClose,
        type: 'candlestick',
        name: 'Precio',
        increasing: { line: { color: '#00C076', width: 1 }, fillcolor: '#00C076' },
        decreasing: { line: { color: '#FF5B5B', width: 1 }, fillcolor: '#FF5B5B' },
        yaxis: 'y'
    });
    
    const zoneColors = {
        'COMPRA': 'rgba(0, 255, 0, ',
        'VENTA': 'rgba(255, 0, 0, ',
        'LONG': 'rgba(0, 200, 0, ',
        'SHORT': 'rgba(200, 0, 0, '
    };
    
    Object.keys(activeZones).forEach(zoneType => {
        const zone = activeZones[zoneType];
        if (!zone) return;
        
        const color = zoneColors[zoneType] || 'rgba(128, 128, 128, ';
        const opacity = zone.opacity || 0.3;
        
        // Determinar ancho según tipo de zona
        let pastBars, futureBars;
        if (zoneType === 'LONG' || zoneType === 'SHORT') {
            pastBars = longShortPastBars;
            futureBars = longShortFutureBars;
        } else {
            pastBars = buySellPastBars;
            futureBars = buySellFutureBars;
        }
        
        // Calcular índices de inicio y fin
        const startIndex = Math.max(0, currentIndex - pastBars);
        const endIndex = Math.min(lastDates.length - 1, currentIndex + futureBars);
        
        const startDate = lastDates[startIndex];
        const endDate = lastDates[endIndex];
        
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: startDate,
            x1: endDate,
            y0: zone.price_min,
            y1: zone.price_max,
            fillcolor: color + opacity + ')',
            line: { 
                width: zone.veto_active ? 1 : 0,
                color: zone.veto_active ? 'rgba(255,255,0,0.5)' : 'transparent',
                dash: zone.veto_active ? 'dot' : 'solid'
            },
            layer: 'below',
            hovertext: zoneJustification[zoneType] || 'Zona basada en indicadores',
            hoverinfo: 'text'
        });
    });
    
    const currentPrice = data.current_price || lastClose[lastClose.length - 1];
    shapes.push({
        type: 'line',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: currentPrice,
        y1: currentPrice,
        line: { color: 'rgba(255, 215, 0, 0.3)', width: 1 },
        layer: 'above'
    });
    
    const layout = {
        title: { text: `Zonas de Trading (${timeframe})`, font: { color: 'white', size: 14 } },
        xaxis: {
            type: 'date',
            range: [lastDates[0], lastDates[lastDates.length - 1]],
            showgrid: true,
            gridcolor: 'rgba(128,128,128,0.2)',
            title: 'Fecha/Hora'
        },
        yaxis: {
            title: 'Precio',
            range: [minPrice - padding, maxPrice + padding],
            showgrid: true,
            gridcolor: 'rgba(128,128,128,0.2)',
            tickformat: ',.0f'
        },
        template: 'plotly_dark',
        height: 350,
        margin: { l: 60, r: 60, t: 50, b: 80 },
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        shapes: shapes,
        showlegend: false,
        hovermode: 'x unified',
        annotations: [
            {
                x: 0.5,
                y: -0.25,
                xref: 'paper',
                yref: 'paper',
                text: getZoneAnnotations(activeZones, zoneJustification),
                showarrow: false,
                font: { color: '#FFD700', size: 11, family: 'Arial' },
                align: 'center',
                bgcolor: '#1a1e24',
                bordercolor: '#17a2b8',
                borderwidth: 1,
                borderpad: 8
            }
        ]
    };
    
    try {
        Plotly.newPlot('trading-zones-chart', traces, layout, { responsive: true, displaylogo: false });
        console.log(`✅ Gráfico de zonas: ${Object.keys(activeZones).length} zonas activas`);
    } catch (error) {
        console.error('❌ Error al crear gráfico de zonas:', error);
        chartDiv.innerHTML = '<div class="alert alert-danger">Error al generar gráfico</div>';
    }
}

function getZoneAnnotations(activeZones, zoneJustification) {
    let lines = [];
    let conflictLine = [];
    
    // Detectar si hay ambas zonas
    if (activeZones.COMPRA && activeZones.VENTA) {
        // Extraer indicadores de compra y venta
        const compraInd = zoneJustification.COMPRA ? zoneJustification.COMPRA.split(' · ') : [];
        const ventaInd = zoneJustification.VENTA ? zoneJustification.VENTA.split(' · ') : [];
        
        // Mezclar indicadores alcistas (↑) y bajistas (↓)
        const mixed = [];
        const maxLen = Math.max(compraInd.length, ventaInd.length);
        
        for (let i = 0; i < maxLen; i++) {
            if (i < compraInd.length) mixed.push(`↑${compraInd[i]}`);
            if (i < ventaInd.length) mixed.push(`↓${ventaInd[i]}`);
        }
        
        conflictLine.push(`⚠️ Conflicto: ${mixed.slice(0, 8).join(' · ')}`);
    } else {
        if (activeZones.COMPRA) {
            lines.push(`🟢 COMPRA: ${zoneJustification.COMPRA || 'Consenso alcista'}`);
        }
        if (activeZones.VENTA) {
            lines.push(`🔴 VENTA: ${zoneJustification.VENTA || 'Consenso bajista'}`);
        }
    }
    
    if (activeZones.LONG) {
        lines.push(`🟩 LONG: ${zoneJustification.LONG || 'Zona de precisión'}`);
    }
    if (activeZones.SHORT) {
        lines.push(`🟥 SHORT: ${zoneJustification.SHORT || 'Zona de precisión'}`);
    }
    
    return conflictLine.length > 0 ? conflictLine.join('<br>') : lines.join('<br>');
}




function updateZoneStatusCard(activeZones, priceStatus, currentPrice, decision, zoneJustification) {
    // Actualizar valores de zonas
    document.getElementById('zone-compra-min').innerHTML = activeZones.COMPRA ? `$${activeZones.COMPRA.price_min.toFixed(2)}` : '--';
    document.getElementById('zone-compra-max').innerHTML = activeZones.COMPRA ? `$${activeZones.COMPRA.price_max.toFixed(2)}` : '--';
    document.getElementById('zone-venta-min').innerHTML = activeZones.VENTA ? `$${activeZones.VENTA.price_min.toFixed(2)}` : '--';
    document.getElementById('zone-venta-max').innerHTML = activeZones.VENTA ? `$${activeZones.VENTA.price_max.toFixed(2)}` : '--';
    document.getElementById('zone-long-min').innerHTML = activeZones.LONG ? `$${activeZones.LONG.price_min.toFixed(2)}` : '--';
    document.getElementById('zone-long-max').innerHTML = activeZones.LONG ? `$${activeZones.LONG.price_max.toFixed(2)}` : '--';
    document.getElementById('zone-short-min').innerHTML = activeZones.SHORT ? `$${activeZones.SHORT.price_min.toFixed(2)}` : '--';
    document.getElementById('zone-short-max').innerHTML = activeZones.SHORT ? `$${activeZones.SHORT.price_max.toFixed(2)}` : '--';
    
    document.getElementById('zone-current-price').innerHTML = currentPrice ? `$${currentPrice.toFixed(2)}` : '--';
    
    // ============ DETECTAR CONFLICTO ============
    const conflicto = detectZoneConflict(activeZones, priceStatus, currentPrice);
    const estadoElem = document.getElementById('zone-status');
    
    if (conflicto) {
        if (conflicto.tipo === 'DOMINA_COMPRA' && decision === 'COMPRA_SPOT') {
            estadoElem.innerHTML = `✅ ${conflicto.mensaje} - Coherente con señal`;
            estadoElem.style.color = '#00C076';
        } else if (conflicto.tipo === 'DOMINA_VENTA' && decision === 'VENTA_SPOT') {
            estadoElem.innerHTML = `✅ ${conflicto.mensaje} - Coherente con señal`;
            estadoElem.style.color = '#FF5B5B';
        } else if (decision === 'NO_OPERAR') {
            estadoElem.innerHTML = `⚠️ ${conflicto.mensaje}<br>✅ Decisión: NO OPERAR (esperar definición)`;
            estadoElem.style.color = '#FFD700';
        } else {
            estadoElem.innerHTML = `⚠️ ${conflicto.mensaje}<br>⚠️ Señal ${decision} en conflicto con zonas`;
            estadoElem.style.color = '#FFA500';
        }
    } else {
        estadoElem.innerHTML = priceStatus.estado || 'Analizando...';
        estadoElem.style.color = '';
    }
    
    // Distancias
    document.getElementById('zone-dist-compra').innerHTML = priceStatus.distancia_compra ? `${priceStatus.distancia_compra.toFixed(1)}%` : '--';
    document.getElementById('zone-dist-venta').innerHTML = priceStatus.distancia_venta ? `${priceStatus.distancia_venta.toFixed(1)}%` : '--';
    document.getElementById('zone-dist-long').innerHTML = priceStatus.distancia_long ? `${priceStatus.distancia_long.toFixed(1)}%` : '--';
    document.getElementById('zone-dist-short').innerHTML = priceStatus.distancia_short ? `${priceStatus.distancia_short.toFixed(1)}%` : '--';
    
    // Confianza del sistema
    let totalConf = 0;
    let count = 0;
    Object.keys(activeZones).forEach(key => {
        if (activeZones[key] && activeZones[key].confidence) {
            totalConf += activeZones[key].confidence;
            count++;
        }
    });
    const avgConf = count > 0 ? (totalConf / count).toFixed(0) : '--';
    document.getElementById('zone-confidence').innerHTML = avgConf + '%';
    
    // Justificaciones en tarjeta lateral
    const justificationDiv = document.getElementById('zone-justification-text');
    if (justificationDiv) {
        let text = '';
        if (activeZones.COMPRA) text += `🟢 ${zoneJustification.COMPRA || 'Consenso alcista'}<br>`;
        if (activeZones.VENTA) text += `🔴 ${zoneJustification.VENTA || 'Consenso bajista'}<br>`;
        if (activeZones.LONG) text += `🟩 ${zoneJustification.LONG || 'Zona LONG'}<br>`;
        if (activeZones.SHORT) text += `🟥 ${zoneJustification.SHORT || 'Zona SHORT'}<br>`;
        justificationDiv.innerHTML = text || 'Sin justificaciones disponibles';
    }
}




// ============ NUEVA FUNCIÓN: DETECTAR CONFLICTO ENTRE ZONAS ============
function detectZoneConflict(activeZones, priceStatus, currentPrice) {
    if (!activeZones.COMPRA || !activeZones.VENTA) return null;
    
    const dentroCompra = priceStatus.dentro_compra;
    const dentroVenta = priceStatus.dentro_venta;
    
    if (dentroCompra && dentroVenta) {
        // Calcular fuerza relativa (basado en confianza)
        const confianzaCompra = activeZones.COMPRA.confidence || 0;
        const confianzaVenta = activeZones.VENTA.confidence || 0;
        const total = confianzaCompra + confianzaVenta;
        
        if (total === 0) return { tipo: 'CONFLICTO', mensaje: 'Conflicto equilibrado' };
        
        const ratioCompra = confianzaCompra / total;
        const ratioVenta = confianzaVenta / total;
        
        // Determinar dominancia
        if (ratioCompra > 0.7) {
            return { 
                tipo: 'DOMINA_COMPRA', 
                mensaje: `Conflicto con dominancia COMPRA (${Math.round(ratioCompra*100)}%)`,
                dominante: 'COMPRA'
            };
        } else if (ratioVenta > 0.7) {
            return { 
                tipo: 'DOMINA_VENTA', 
                mensaje: `Conflicto con dominancia VENTA (${Math.round(ratioVenta*100)}%)`,
                dominante: 'VENTA'
            };
        } else {
            return { 
                tipo: 'CONFLICTO_EQUILIBRADO', 
                mensaje: `Conflicto: COMPRA ${Math.round(ratioCompra*100)}% - VENTA ${Math.round(ratioVenta*100)}%`,
                dominante: null
            };
        }
    }
    
    return null;
}




// ============ FUNCIONES DE UTILIDAD ============
function getIntervalName(interval) {
    const names = {'4h': '4H', '12h': '12H', '1D': '1D', '1W': '1W'};
    return names[interval] || interval;
}
// ============ FUNCIONES DE UI ============
// ============ ACTUALIZAR RECOMENDACIÓN ============
window.updateRecommendation = function(data) {
    const container = document.getElementById('system-recommendation');
    const timeElement = document.getElementById('recommendation-time');
    
    if (!container) return;
    
    if (!data || !data.decision) {
        container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div><p class="mt-3">Analizando mercado...</p></div>';
        return;
    }
    
    const action = data.decision.action || 'NO_OPERAR';
    const confidence = data.decision.confidence || 0;
    
    let badgeColor = 'secondary';
    let icon = '';
    
    if (action === 'COMPRA_SPOT') { badgeColor = 'success'; icon = '🟢'; }
    else if (action === 'VENTA_SPOT') { badgeColor = 'danger'; icon = '🔴'; }
    else if (action === 'LONG') { badgeColor = 'info'; icon = '📈'; }
    else if (action === 'SHORT') { badgeColor = 'warning'; icon = '📉'; }
    else if (action === 'NO_OPERAR') { badgeColor = 'secondary'; icon = '⏸️'; }
    else if (action === 'ESPERAR') { badgeColor = 'secondary'; icon = '⏳'; }
    
    // Actualizar badge mini
    const badgeMini = document.getElementById('rec-badge-mini');
    if (badgeMini) {
        badgeMini.innerHTML = `<span class="badge bg-${badgeColor}">${icon} ${action.replace('_', ' ')}</span>`;
    }
    
    // Procesar mensaje
    let messageText = data.message || 'Análisis no disponible';
    
    // Construir HTML base
    let html = `
        <div class="recommendation-content">
            <div class="d-flex align-items-center mb-3">
                <span class="badge bg-${badgeColor} p-3 me-3" style="font-size: 1.2rem;">
                    ${icon} ${action.replace('_', ' ')}
                </span>
                <span class="badge bg-dark p-2">Confianza: ${fmtConfidence(confidence)}%</span>
            </div>
            <div class="analysis-text p-3 bg-dark rounded-3">${messageText.replace(/\n/g, '<br>')}</div>
    `;
    
    // Solo mostrar niveles si es una acción de trading
    if (action === 'COMPRA_SPOT' || action === 'VENTA_SPOT' || action === 'LONG' || action === 'SHORT') {
        html += `
            <div class="row mt-3">
                <div class="col-md-4"><div class="border-start border-3 border-primary ps-3"><small class="text-muted d-block">ENTRADA</small><strong class="h5">$${data.levels?.entry?.toFixed(2) || '0.00'}</strong></div></div>
                <div class="col-md-4"><div class="border-start border-3 border-danger ps-3"><small class="text-muted d-block">STOP LOSS</small><strong class="h5">$${data.levels?.stop_loss?.toFixed(2) || '0.00'}</strong></div></div>
                <div class="col-md-4"><div class="border-start border-3 border-success ps-3"><small class="text-muted d-block">TAKE PROFIT</small><strong class="h5">$${data.levels?.take_profit?.toFixed(2) || '0.00'}</strong></div></div>
            </div>
            <div class="mt-3 pt-3 border-top border-secondary">
                <div class="row">
                    <div class="col-6"><small class="text-muted">Riesgo/Recompensa:</small><strong> 1:${data.levels?.risk_reward?.toFixed(1) || '0.0'}</strong></div>
                    <div class="col-6"><small class="text-muted">Apalancamiento:</small><strong> ${data.levels?.leverage || 1}x</strong></div>
                </div>
            </div>
        `;
    }
    
    html += `</div>`;
    container.innerHTML = html;
    
    // Actualizar hora
    if (timeElement) {
        timeElement.textContent = new Date().toLocaleTimeString('es-BO', {hour12: false});
    }
};

function updateInstantRecommendation(data) {
    if (!data) return;
    
    const badge = document.getElementById('rec-badge');
    const actionEl = document.getElementById('rec-action');
    const symbolEl = document.getElementById('rec-symbol');
    const confidenceEl = document.getElementById('rec-confidence');
    const entryEl = document.getElementById('op-entry');
    const slEl = document.getElementById('op-sl');
    const tpEl = document.getElementById('op-tp');
    const leverageEl = document.getElementById('op-leverage');
    const timeframeEl = document.getElementById('op-timeframe');
    const opTypeEl = document.getElementById('op-type-text');
    
    const action = data.decision?.action || 'NO_OPERAR';
    const confidence = data.decision?.confidence || 0;
    
    let badgeClass = 'bg-secondary', badgeText = 'ESPERANDO';
    if (action === 'COMPRA_SPOT') { badgeClass = 'bg-success'; badgeText = 'COMPRA'; }
    else if (action === 'VENTA_SPOT') { badgeClass = 'bg-danger'; badgeText = 'VENTA'; }
    else if (action === 'LONG') { badgeClass = 'bg-info'; badgeText = 'LONG'; }
    else if (action === 'SHORT') { badgeClass = 'bg-warning'; badgeText = 'SHORT'; }
    
    if (badge) badge.innerHTML = `<span class="badge ${badgeClass}">${badgeText}</span>`;
    if (actionEl) actionEl.textContent = action.replace('_', ' ');
    if (symbolEl) symbolEl.textContent = data.symbol?.replace('-', '/') || 'BTC/USDT';
    if (confidenceEl) confidenceEl.textContent = `Confianza: ${fmtConfidence(confidence)}%`;
    if (entryEl) entryEl.textContent = `$${data.levels?.entry?.toFixed(2) || '0.00'}`;
    if (slEl) slEl.textContent = `$${data.levels?.stop_loss?.toFixed(2) || '0.00'}`;
    if (tpEl) tpEl.textContent = `$${data.levels?.take_profit?.toFixed(2) || '0.00'}`;
    if (leverageEl) leverageEl.textContent = `${data.levels?.leverage || 1}x`;
    if (timeframeEl) timeframeEl.textContent = getIntervalName(data.timeframe || '1D');
    if (opTypeEl) opTypeEl.textContent = action === 'NO_OPERAR' ? 'Esperar' : action.replace('_', ' ');
}

function updateAnalysisSummary(data) {
    const summaryEl = document.getElementById('analysis-summary');
    if (!summaryEl) return;
    
    if (!data || !data.trend) {
        summaryEl.innerHTML = '<div class="text-center py-3"><div class="spinner-border spinner-border-sm text-info"></div><p class="mt-2 mb-0 small">Analizando...</p></div>';
        return;
    }
    
    const trendDir = data.trend.direction?.toUpperCase() || 'NEUTRAL';
    const trendColor = trendDir === 'BULLISH' ? 'success' : trendDir === 'BEARISH' ? 'danger' : 'secondary';
    
    const html = `
        <div class="summary-stats">
            <div class="d-flex justify-content-between mb-2"><span>Tendencia:</span><span class="badge bg-${trendColor}">${trendDir}</span></div>
            <div class="d-flex justify-content-between mb-2"><span>Fuerza (ADX):</span><span>${data.trend.adx_value?.toFixed(1) || '0.0'}</span></div>
            <div class="d-flex justify-content-between mb-2"><span>Momentum:</span><span class="${(data.momentum?.score || 0) > 0 ? 'text-success' : (data.momentum?.score || 0) < 0 ? 'text-danger' : 'text-secondary'}">${(data.momentum?.score || 0) > 0 ? '👍' : (data.momentum?.score || 0) < 0 ? '👎' : '➡️'} ${Math.abs(data.momentum?.score || 0).toFixed(0)}</span></div>
            <div class="d-flex justify-content-between mb-2"><span>RSI:</span><span>${data.momentum?.indicators?.rsi?.toFixed(1) || '50.0'}</span></div>
            <div class="d-flex justify-content-between mb-2"><span>Volatilidad:</span><span class="badge bg-${data.volatility?.volatility_level === 'low' ? 'success' : data.volatility?.volatility_level === 'medium' ? 'warning' : 'danger'}">${data.volatility?.volatility_level?.toUpperCase() || 'UNKNOWN'}</span></div>
            <div class="d-flex justify-content-between mb-2"><span>ATR %:</span><span>${data.volatility?.atr_pct?.toFixed(2) || '0.00'}%</span></div>
            <div class="d-flex justify-content-between mb-2"><span>Volumen:</span><span>${data.volume?.volume_ratio?.toFixed(1) || '1.0'}x</span></div>
            <hr class="my-2"><div class="text-center"><small class="text-muted">${data.decision?.action || 'NO_OPERAR'}</small></div>
        </div>
    `;
    summaryEl.innerHTML = html;
}

function updateConfirmedSignals(data) {
    const tbody = document.getElementById('confirmed-signals');
    if (!tbody) return;
    
    let html = '';
    if (data?.decision?.action && data.decision.action !== 'NO_OPERAR') {
        html += `<tr><td>${data.symbol?.replace('-', '/') || 'BTC/USDT'}</td><td>${getIntervalName(data.timeframe)}</td><td><span class="badge bg-success">${data.decision.action}</span></td></tr>`;
    }
    if (data?.volume?.whale_buy) {
        html += `<tr><td>${data.symbol?.replace('-', '/') || 'BTC/USDT'}</td><td>${getIntervalName(data.timeframe)}</td><td><span class="badge bg-info">🐋 BALLENAS</span></td></tr>`;
    }
    if (data?.volume?.whale_sell) {
        html += `<tr><td>${data.symbol?.replace('-', '/') || 'BTC/USDT'}</td><td>${getIntervalName(data.timeframe)}</td><td><span class="badge bg-warning">🐋 DISTRIBUCIÓN</span></td></tr>`;
    }
    if (html === '') html = '<tr><td colspan="3" class="text-center py-3 small">No hay señales confirmadas</td></tr>';
    tbody.innerHTML = html;
}
// ============ ACTUALIZAR SEÑALES ACTIVAS - VERSIÓN COMPLETA ============
// NOTA: se asigna a window para que futures.js pueda sobreescribirla
window.updateActiveSignals = function updateActiveSignals() {
    // Si estamos en la página de Futuros, futures.js maneja esto con su propia lógica
    // (consulta /api/futures/signals/active en vez de spot)
    if (window.IS_FUTURES_PAGE) {
        return;
    }
    
    const signalsList = document.getElementById('active-signals-list');
    const signalsCount = document.getElementById('active-signals-count');
    
    if (!signalsList) return;
    
    signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3"><div class="spinner-border spinner-border-sm text-success me-2"></div>Buscando señales...</div>';
    
    // ============ CONSULTAR TODAS LAS COMBINACIONES ============
    // 3 pares × 4 temporalidades = 12 consultas
    Promise.all([
        // BTC-USDT
        fetch(`/api/analyze?symbol=BTC-USDT&interval=1D`).then(r => r.json()),
        fetch(`/api/analyze?symbol=BTC-USDT&interval=12h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=BTC-USDT&interval=4h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=BTC-USDT&interval=1W`).then(r => r.json()),  // ← NUEVO
        
        // PAXG-USDT
        fetch(`/api/analyze?symbol=PAXG-USDT&interval=1D`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-USDT&interval=12h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-USDT&interval=4h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-USDT&interval=1W`).then(r => r.json()),  // ← NUEVO
        
        // PAXG-BTC
        fetch(`/api/analyze?symbol=PAXG-BTC&interval=1D`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-BTC&interval=12h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-BTC&interval=4h`).then(r => r.json()),
        fetch(`/api/analyze?symbol=PAXG-BTC&interval=1W`).then(r => r.json())   // ← NUEVO
    ])
    .then(responses => {
        const activeSignals = [];
        const signalColors = {
            'COMPRA_SPOT': 'success',
            'LONG': 'info',
            'VENTA_SPOT': 'danger',
            'SHORT': 'warning'
        };
        
        const signalIcons = {
            'COMPRA_SPOT': '🟢',
            'LONG': '📈',
            'VENTA_SPOT': '🔴',
            'SHORT': '📉'
        };
        
        // Mapeo de índices a pares y temporalidades
        const mappings = [
            // BTC-USDT (índices 0-3)
            { symbol: 'BTC-USDT', tf: '1D' },
            { symbol: 'BTC-USDT', tf: '12h' },
            { symbol: 'BTC-USDT', tf: '4h' },
            { symbol: 'BTC-USDT', tf: '1W' },
            
            // PAXG-USDT (índices 4-7)
            { symbol: 'PAXG-USDT', tf: '1D' },
            { symbol: 'PAXG-USDT', tf: '12h' },
            { symbol: 'PAXG-USDT', tf: '4h' },
            { symbol: 'PAXG-USDT', tf: '1W' },
            
            // PAXG-BTC (índices 8-11)
            { symbol: 'PAXG-BTC', tf: '1D' },
            { symbol: 'PAXG-BTC', tf: '12h' },
            { symbol: 'PAXG-BTC', tf: '4h' },
            { symbol: 'PAXG-BTC', tf: '1W' }
        ];
        
        responses.forEach((response, index) => {
            if (response.success && response.data) {
                const data = response.data;
                const action = data.decision?.action;
                const confidence = data.decision?.confidence || 0;
                
                // Solo mostrar acciones de trading con confianza >= 60
                if (['COMPRA_SPOT', 'LONG', 'VENTA_SPOT', 'SHORT'].includes(action) && confidence >= 60) {
                    
                    const symbol = mappings[index].symbol;
                    const timeframe = mappings[index].tf;
                    
                    activeSignals.push({
                        symbol: symbol,
                        timeframe: timeframe,
                        action: action,
                        confidence: confidence,
                        entry: data.levels?.entry,
                        sl: data.levels?.stop_loss,
                        tp: data.levels?.take_profit,
                        icon: signalIcons[action] || '🔔',
                        color: signalColors[action] || 'secondary'
                    });
                }
            }
        });
        
        // Ordenar por confianza (mayor primero)
        activeSignals.sort((a, b) => b.confidence - a.confidence);
        
        // Actualizar contador
        if (signalsCount) {
            signalsCount.textContent = activeSignals.length;
            signalsCount.className = `badge bg-${activeSignals.length > 0 ? 'success' : 'secondary'}`;
        }
        
        // Generar HTML
        if (activeSignals.length === 0) {
            signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3">No hay señales activas</div>';
            return;
        }
        
        let html = '';
        activeSignals.forEach(signal => {
            const symbolName = signal.symbol.replace('-', '/');
            const timeframeName = {
                '4h': '4H', '12h': '12H', '1D': '1D', '1W': '1W'
            }[signal.timeframe] || signal.timeframe;
            
            html += `
                <div class="list-group-item bg-dark text-white border-secondary signal-item" 
                     style="cursor: pointer; transition: all 0.2s;"
                     onclick="window.changeToSignal('${signal.symbol}', '${signal.timeframe}')"
                     onmouseover="this.style.backgroundColor='#1a1e24'"
                     onmouseout="this.style.backgroundColor=''">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge bg-${signal.color} me-2">${signal.icon}</span>
                            <strong>${signal.action.replace('_', ' ')}</strong>
                        </div>
                        <span class="badge bg-dark">${fmtConfidence(signal.confidence)}%</span>
                    </div>
                    <div class="d-flex justify-content-between mt-1">
                        <small class="text-muted">${symbolName} ${timeframeName}</small>
                        <small class="text-success">E: $${signal.entry?.toFixed(2)}</small>
                    </div>
                </div>
            `;
        });
        
        signalsList.innerHTML = html;
    })
    .catch(error => {
        console.error('Error cargando señales activas:', error);
        signalsList.innerHTML = '<div class="list-group-item bg-dark text-danger text-center py-3">Error al cargar señales</div>';
    });
};
// ============ FUNCIÓN PARA CAMBIAR A UNA SEÑAL ============
window.changeToSignal = function(symbol, timeframe) {
    console.log(`🔄 Cambiando a ${symbol} ${timeframe}`);
    
    // Actualizar selects
    const symbolSelect = document.getElementById('symbol-select');
    const intervalSelect = document.getElementById('interval-select');
    
    if (symbolSelect) symbolSelect.value = symbol;
    if (intervalSelect) intervalSelect.value = timeframe;
    
    // Actualizar variables globales
    window.currentSymbol = symbol;
    window.currentInterval = timeframe;
    
    // Ejecutar análisis
    if (typeof window.runCompleteAnalysis === 'function') {
        window.runCompleteAnalysis();
    }
    
    // Hacer scroll al gráfico principal
    const chartElement = document.getElementById('candle-chart');
    if (chartElement) {
        chartElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
};

// ============ ACTUALIZAR SEÑALES PERIÓDICAMENTE ============
// Único setInterval del sistema para refrescar señales activas.
// Antes había dos (uno a 60s aquí + otro a 120s en la inicialización),
// que causaban peticiones duplicadas al backend.
setInterval(() => {
    if (typeof window.updateActiveSignals === 'function') window.updateActiveSignals();
}, 120000); // Cada 2 minutos


function updateMarketAlerts(data) {
    const tbody = document.getElementById('market-alerts');
    if (!tbody) return;
    
    let html = '';
    if (data?.volatility && !data.volatility.operability) {
        html += `<tr><td><span class="badge bg-danger">ALTA</span></td><td>Volatilidad extrema: ${data.volatility.atr_pct?.toFixed(1) || '0.0'}%</td></tr>`;
    }
    if (data?.volatility?.ftm_no_trade) {
        html += `<tr><td><span class="badge bg-warning">MEDIA</span></td><td>FTMaverick en zona de no-operación</td></tr>`;
    }
    if (data?.trend?.adx_value < 20) {
        html += `<tr><td><span class="badge bg-info">BAJA</span></td><td>ADX bajo: mercado sin dirección</td></tr>`;
    }
    if (data?.momentum?.indicators?.rsi > 70) {
        html += `<tr><td><span class="badge bg-warning">MEDIA</span></td><td>RSI en sobrecompra: ${data.momentum.indicators.rsi.toFixed(1)}</td></tr>`;
    }
    if (data?.momentum?.indicators?.rsi < 30) {
        html += `<tr><td><span class="badge bg-success">BAJA</span></td><td>RSI en sobreventa: ${data.momentum.indicators.rsi.toFixed(1)}</td></tr>`;
    }
    if (html === '') html = '<tr><td colspan="2" class="text-center py-3 small">No hay alertas activas</td></tr>';
    tbody.innerHTML = html;
}



// ============ SEÑALES DE VELA ANTERIOR - VERSIÓN CORREGIDA ============
// NOTA: se asigna a window para que futures.js pueda sobreescribirla
window.updatePreviousSignals = function updatePreviousSignals() {
    // Si estamos en la página de Futuros, futures.js usa su propia lógica
    // (/api/futures/signals/previous en vez de /api/previous_signals que trae PAXG)
    if (window.IS_FUTURES_PAGE) {
        return;
    }
    
    const signalsList = document.getElementById('prev-signals-list');
    const signalsCount = document.getElementById('prev-signals-count');
    
    if (!signalsList) return;
    
    // Mostrar carga solo la primera vez
    if (!window.prevSignalsLoaded) {
        signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3"><div class="spinner-border spinner-border-sm text-warning me-2"></div>Cargando señales anteriores...</div>';
    }
    
    fetch('/api/previous_signals')
        .then(response => response.json())
        .then(data => {
            // Actualizar contador siempre
            if (signalsCount) {
                signalsCount.textContent = '0';
                signalsCount.className = 'badge bg-secondary';
            }
            
            // Si hay error
            if (!data.success) {
                signalsList.innerHTML = `<div class="list-group-item bg-dark text-warning text-center py-3">⚠️ ${data.error || 'Error al cargar'}</div>`;
                window.prevSignalsLoaded = true;
                return;
            }
            
            // Si no hay datos
            if (!data.data || Object.keys(data.data).length === 0) {
                signalsList.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3">No hay señales de velas anteriores</div>';
                window.prevSignalsLoaded = true;
                return;
            }
            
            const señales = Object.values(data.data);
            
            // Filtrar activas (activa === 1)
            const activas = señales.filter(s => s.activa === 1);
            if (signalsCount) {
                signalsCount.textContent = activas.length;
                signalsCount.className = `badge bg-${activas.length > 0 ? 'warning' : 'secondary'}`;
            }
            
            // Ordenar: activas primero, luego por tiempo restante
            señales.sort((a, b) => {
                if (a.activa === 1 && b.activa !== 1) return -1;
                if (a.activa !== 1 && b.activa === 1) return 1;
                return (a.tiempo_restante || 0) - (b.tiempo_restante || 0);
            });
            
            let html = '';
            señales.forEach(senal => {
                const symbolName = senal.symbol.replace('-', '/');
                const tfName = {
                    '4h': '4H', 
                    '12h': '12H', 
                    '1D': '1D', 
                    '1W': '1W'
                }[senal.timeframe] || senal.timeframe;
                
                // Determinar emoji y color según acción
                let emoji = '🟢', bgColor = 'success';
                if (senal.decision.includes('VENTA') || senal.decision.includes('SHORT')) {
                    emoji = '🔴';
                    bgColor = 'danger';
                } else if (senal.decision.includes('LONG')) {
                    emoji = '📈';
                    bgColor = 'info';
                }
                
                // Badge de temporalidad
                const tfBadge = {
                    '4h': 'bg-info', 
                    '12h': 'bg-primary', 
                    '1D': 'bg-success', 
                    '1W': 'bg-warning'
                }[senal.timeframe] || 'bg-secondary';
                
                // Formatear tiempo restante
                let tiempoTexto = '';
                if (senal.activa === 1 && senal.tiempo_restante > 0) {
                    const horas = Math.floor(senal.tiempo_restante / 3600);
                    const minutos = Math.floor((senal.tiempo_restante % 3600) / 60);
                    tiempoTexto = `${horas}h ${minutos}m`;
                }
                
                html += `
                    <div class="list-group-item bg-dark text-white border-secondary signal-item ${senal.activa !== 1 ? 'opacity-50' : ''}" 
                         style="cursor: pointer; transition: all 0.2s;"
                         onclick='window.showPreviousSignalJustification(${JSON.stringify(senal).replace(/'/g, "\\'")})'
                         onmouseover="this.style.backgroundColor='#1a1e24'"
                         onmouseout="this.style.backgroundColor=''">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <span class="badge bg-${bgColor} me-2">${emoji}</span>
                                <strong>${senal.decision.replace('_', ' ')}</strong>
                                <span class="badge ${tfBadge} ms-2">${tfName}</span>
                            </div>
                            <span class="badge bg-dark">${senal.confidence}%</span>
                        </div>
                        <div class="d-flex justify-content-between mt-1">
                            <small class="text-muted">${symbolName}</small>
                            ${senal.activa === 1 ? 
                                `<small class="text-warning">⏱️ ${tiempoTexto}</small>` : 
                                `<small class="text-secondary">⚪ inactiva</small>`
                            }
                        </div>
                        <div class="mt-1">
                            <small class="text-${senal.activa === 1 ? bgColor : 'secondary'}">
                                E: $${senal.entry?.toFixed(2) || '---'} | 
                                SL: $${senal.stop_loss?.toFixed(2) || '---'}
                            </small>
                        </div>
                    </div>
                `;
            });
            
            signalsList.innerHTML = html;
            window.prevSignalsLoaded = true;
            
            if (data.cached) {
                console.log('📦 Datos de caché (10 min)');
            }
        })
        .catch(error => {
            console.error('Error en updatePreviousSignals:', error);
            signalsList.innerHTML = '<div class="list-group-item bg-dark text-danger text-center py-3">Error de conexión</div>';
            if (signalsCount) {
                signalsCount.textContent = '0';
                signalsCount.className = 'badge bg-secondary';
            }
        });
};

// ============ MOSTRAR JUSTIFICACIÓN DE SEÑAL ANTERIOR ============
window.showPreviousSignalJustification = function(senal) {
    const modalBody = document.getElementById('prev-signal-details');
    if (!modalBody) return;
    
    // Limpiar y mostrar carga
    modalBody.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div><p class="mt-3">Cargando justificación...</p></div>';
    
    // Obtener el modal
    const modal = new bootstrap.Modal(document.getElementById('prevSignalModal'));
    modal.show();
    
    // Construir HTML de justificación
    setTimeout(() => {
        const symbolName = senal.symbol.replace('-', '/');
        const timeframeName = {
            '4h': '4 Horas', 
            '12h': '12 Horas', 
            '1D': '1 Día', 
            '1W': '1 Semana'
        }[senal.timeframe] || senal.timeframe;
        
        // Emoji y color según acción
        let emoji = '🟢', bgColor = 'success', bgColorBadge = 'success';
        if (senal.decision.includes('VENTA') || senal.decision.includes('SHORT')) {
            emoji = '🔴';
            bgColor = 'danger';
            bgColorBadge = 'danger';
        } else if (senal.decision.includes('LONG')) {
            emoji = '📈';
            bgColor = 'info';
            bgColorBadge = 'info';
        }
        
        // Estado actual
        let estadoHTML = '';
        if (senal.activa === 1) {
            estadoHTML = `
                <div class="alert alert-success mt-3">
                    <i class="fas fa-check-circle me-2"></i>
                    <strong>ESTADO ACTUAL:</strong> SEÑAL ACTIVA - Precio actual respeta el Stop Loss
                    ${senal.tiempo_restante ? `<br><small>Válida por ${Math.floor(senal.tiempo_restante/3600)}h ${Math.floor((senal.tiempo_restante%3600)/60)}m más</small>` : ''}
                </div>
            `;
        } else {
            estadoHTML = `
                <div class="alert alert-secondary mt-3">
                    <i class="fas fa-pause-circle me-2"></i>
                    <strong>ESTADO ACTUAL:</strong> SEÑAL INACTIVA - Stop Loss fue alcanzado
                </div>
            `;
        }
        
        // Formatear mensaje (reemplazar saltos de línea)
        const mensajeFormateado = (senal.message || 'No hay justificación disponible')
            .replace(/\n/g, '<br>')
            .replace(/\t/g, '&nbsp;&nbsp;');
        
        const html = `
            <div class="recommendation-content">
                <div class="d-flex align-items-center mb-3">
                    <span class="badge bg-${bgColor} p-3 me-3" style="font-size: 1.2rem;">
                        ${emoji} ${senal.decision.replace('_', ' ')}
                    </span>
                    <div>
                        <span class="badge bg-dark d-block mb-1">${symbolName} ${timeframeName}</span>
                        <span class="badge bg-secondary">Confianza: ${senal.confidence}%</span>
                    </div>
                </div>
                
                ${estadoHTML}
                
                <div class="row mt-3 mb-3">
                    <div class="col-md-4">
                        <div class="border-start border-3 border-primary ps-3">
                            <small class="text-muted d-block">ENTRADA (cierre vela)</small>
                            <strong class="h5">$${senal.entry?.toFixed(2) || '---'}</strong>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="border-start border-3 border-danger ps-3">
                            <small class="text-muted d-block">STOP LOSS</small>
                            <strong class="h5">$${senal.stop_loss?.toFixed(2) || '---'}</strong>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="border-start border-3 border-success ps-3">
                            <small class="text-muted d-block">TAKE PROFIT</small>
                            <strong class="h5">$${senal.take_profit?.toFixed(2) || '---'}</strong>
                        </div>
                    </div>
                </div>
                
                <div class="mt-3 pt-3 border-top border-secondary">
                    <div class="row">
                        <div class="col-6">
                            <small class="text-muted">Precio actual:</small>
                            <strong class="ms-1 text-${senal.activa === 1 ? bgColor : 'secondary'}">
                                $${senal.precio_actual?.toFixed(2) || '---'}
                            </strong>
                        </div>
                        <div class="col-6">
                            <small class="text-muted">Vela cerrada en:</small>
                            <strong class="ms-1">${new Date(senal.timestamp).toLocaleString('es-BO')}</strong>
                        </div>
                    </div>
                </div>
                
                <div class="analysis-text p-3 bg-dark rounded-3 mt-3">
                    ${mensajeFormateado}
                </div>
                
                <div class="mt-3 text-end">
                    <small class="text-muted">
                        <i class="fas fa-history me-1"></i>
                        Señal de vela anterior - No se actualiza
                    </small>
                </div>
            </div>
        `;
        
        modalBody.innerHTML = html;
    }, 100);
};

// Actualizar cada 10 minutos
setInterval(() => { if (typeof window.updatePreviousSignals === 'function') window.updatePreviousSignals(); }, 600000);
if (typeof window.updatePreviousSignals === 'function') window.updatePreviousSignals();






// ============ FEAR & GREED INDEX - VERSIÓN MEJORADA ============
window.updateFearGreedChart = function(data) {
    console.log('🟡 EJECUTANDO updateFearGreedChart');
    
    const chartDiv = document.getElementById('fear-greed-chart');
    if (!chartDiv) {
        console.log('❌ No se encontró el div fear-greed-chart');
        return;
    }
    
    // Limpiar gráfico anterior
    Plotly.purge('fear-greed-chart');
    
    if (!data || !data.sentiment || !data.sentiment.available) {
        chartDiv.innerHTML = '<div class="text-center py-4"><p class="text-muted">No hay datos de sentimiento</p></div>';
        document.getElementById('fng-current').textContent = '--';
        document.getElementById('fng-classification').textContent = '--';
        document.getElementById('fng-trend-7d').textContent = '--';
        document.getElementById('fng-trend-30d').textContent = '--';
        document.getElementById('fng-interpretation').textContent = 'Esperando datos...';
        return;
    }
    
    const sentiment = data.sentiment;
    const currentValue = sentiment.current_value || 50;
    const classification = sentiment.classification || 'Neutral';
    const trend7d = sentiment.trend_7d_pct || 0;
    const trend30d = sentiment.trend_30d_pct || 0;
    const historical = sentiment.historical || [];
    const timeframe = data.timeframe || '1D';
    
    // Actualizar valores numéricos
    document.getElementById('fng-current').textContent = currentValue;
    
    const fngClassification = document.getElementById('fng-classification');
    fngClassification.textContent = classification;
    if (classification.includes('Extreme Fear')) {
        fngClassification.className = 'badge bg-danger';
    } else if (classification.includes('Fear')) {
        fngClassification.className = 'badge bg-warning';
    } else if (classification.includes('Neutral')) {
        fngClassification.className = 'badge bg-secondary';
    } else if (classification.includes('Greed')) {
        fngClassification.className = 'badge bg-info';
    } else if (classification.includes('Extreme Greed')) {
        fngClassification.className = 'badge bg-success';
    }
    
    // Tendencia 7 días
    const trend7dEl = document.getElementById('fng-trend-7d');
    const trend7dIcon = document.getElementById('fng-trend-7d-icon');
    trend7dEl.textContent = `${trend7d > 0 ? '+' : ''}${trend7d.toFixed(1)}%`;
    trend7dEl.className = trend7d > 0 ? 'h5 text-success' : (trend7d < 0 ? 'h5 text-danger' : 'h5 text-muted');
    if (trend7dIcon) {
        trend7dIcon.innerHTML = trend7d > 0 ? '▲' : (trend7d < 0 ? '▼' : '◆');
        trend7dIcon.className = trend7d > 0 ? 'text-success ms-1' : (trend7d < 0 ? 'text-danger ms-1' : 'text-muted ms-1');
    }
    
    // Tendencia 30 días
    const trend30dEl = document.getElementById('fng-trend-30d');
    trend30dEl.textContent = `${trend30d > 0 ? '+' : ''}${trend30d.toFixed(1)}%`;
    trend30dEl.className = trend30d > 0 ? 'h5 text-success' : (trend30d < 0 ? 'h5 text-danger' : 'h5 text-muted');
    
    // Badge de temporalidad
    document.getElementById('fng-timeframe-badge').textContent = timeframe;
    
    // Interpretación
    const interpretationEl = document.getElementById('fng-interpretation');
    let interpretation = '';
    if (currentValue < 20 && trend7d > 0) {
        interpretation = '💡 Miedo extremo pero remontando - oportunidad de acumulación';
    } else if (currentValue < 20) {
        interpretation = '⚠️ Miedo extremo persistente - esperar confirmación';
    } else if (currentValue > 80 && trend7d < 0) {
        interpretation = '💡 Avaricia extrema cayendo - oportunidad de toma de ganancias';
    } else if (currentValue > 80) {
        interpretation = '⚠️ Avaricia extrema - mercado sobrecalentado, cautela';
    } else if (currentValue < 40) {
        interpretation = trend7d > 0 ? '📈 Miedo moderado mejorando - sesgo alcista' : '📉 Miedo moderado empeorando - cautela';
    } else if (currentValue > 60) {
        interpretation = trend7d < 0 ? '📉 Avaricia moderada cayendo - posible techo' : '📈 Avaricia moderada - momentum positivo';
    } else {
        interpretation = '⚖️ Sentimiento neutral - mercado equilibrado';
    }
    interpretationEl.textContent = interpretation;
    
    // Si no hay datos históricos, salir
    if (historical.length === 0) {
        chartDiv.innerHTML = '<div class="text-center py-4"><p class="text-muted">Datos históricos no disponibles</p></div>';
        return;
    }
    
    // Preparar datos
    const sortedHistorical = [...historical].reverse();
    const dates = sortedHistorical.map(item => item.date);
    const values = sortedHistorical.map(item => item.value);
    
    // Calcular rango automático para el eje Y (con padding)
    const minVal = Math.min(...values) - 5;
    const maxVal = Math.max(...values) + 5;
    const yRange = [Math.max(0, minVal), Math.min(100, maxVal)];
    
    // Colores para los puntos según valor
    const colors = values.map(v => {
        if (v < 20) return '#FF5B5B';
        if (v < 40) return '#FF8C00';
        if (v < 60) return '#FFD700';
        if (v < 80) return '#3A8BFF';
        return '#00C076';
    });
    
    // Zonas de color de fondo (5 zonas)
    const backgroundZones = [
        { min: 0, max: 20, color: 'rgba(255, 91, 91, 0.15)', name: 'Extreme Fear' },
        { min: 20, max: 40, color: 'rgba(255, 140, 0, 0.15)', name: 'Fear' },
        { min: 40, max: 60, color: 'rgba(255, 215, 0, 0.15)', name: 'Neutral' },
        { min: 60, max: 80, color: 'rgba(58, 139, 255, 0.15)', name: 'Greed' },
        { min: 80, max: 100, color: 'rgba(0, 192, 118, 0.15)', name: 'Extreme Greed' }
    ];
    
    // Crear shapes para las zonas de fondo
    const zoneShapes = [];
    backgroundZones.forEach(zone => {
        zoneShapes.push({
            type: 'rect',
            xref: 'paper',
            yref: 'y',
            x0: 0,
            x1: 1,
            y0: zone.min,
            y1: zone.max,
            fillcolor: zone.color,
            line: { width: 0 },
            layer: 'below'
        });
    });
    
    // Traza principal: línea BLANCA semi-transparente
    const traces = [{
        x: dates,
        y: values,
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Fear & Greed Index',
        line: { 
            color: 'rgba(255, 255, 255, 0.7)',  // BLANCO semi-transparente
            width: 1.5,
            shape: 'spline'
        },
        marker: {
            color: colors,
            size: 3,
            line: { color: 'white', width: 0.5 }
        },
        fill: 'none'
    }];
    
    // ============ LÍNEA DE TENDENCIA 7 DÍAS (AMARILLA) ============
    if (values.length >= 7) {
        const last7Values = values.slice(-7);
        const last7Dates = dates.slice(-7);
        
        const n = last7Values.length;
        let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
        for (let i = 0; i < n; i++) {
            sumX += i;
            sumY += last7Values[i];
            sumXY += i * last7Values[i];
            sumX2 += i * i;
        }
        const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        const intercept = (sumY - slope * sumX) / n;
        
        const trendLineValues = last7Dates.map((_, i) => slope * i + intercept);
        
        const trendDirection = trendLineValues[trendLineValues.length - 1] - trendLineValues[0];
        
        // LÍNEA AMARILLA SÓLIDA
        traces.push({
            x: last7Dates,
            y: trendLineValues,
            type: 'scatter',
            mode: 'lines',
            name: 'Tendencia 7d',
            line: {
                color: '#FFD700',  // AMARILLO
                width: 2,
                dash: 'solid'
            },
            showlegend: true
        });
        
        // Flecha al final
        const arrowX = last7Dates[last7Dates.length - 1];
        const arrowY = trendLineValues[trendLineValues.length - 1];
        
        traces.push({
            x: [arrowX],
            y: [arrowY],
            type: 'scatter',
            mode: 'markers',
            name: 'Dir 7d',
            marker: {
                symbol: trendDirection > 0 ? 'triangle-up' : 'triangle-down',
                size: 10,
                color: '#FFD700',
                line: { color: 'white', width: 1 }
            },
            showlegend: false
        });
    }
    
    // ============ LÍNEA DE TENDENCIA 30 DÍAS (AZUL) ============
    if (values.length >= 30) {
        const last30Values = values.slice(-30);
        const last30Dates = dates.slice(-30);
        
        const n30 = last30Values.length;
        let sumX30 = 0, sumY30 = 0, sumXY30 = 0, sumX2_30 = 0;
        for (let i = 0; i < n30; i++) {
            sumX30 += i;
            sumY30 += last30Values[i];
            sumXY30 += i * last30Values[i];
            sumX2_30 += i * i;
        }
        const slope30 = (n30 * sumXY30 - sumX30 * sumY30) / (n30 * sumX2_30 - sumX30 * sumX30);
        const intercept30 = (sumY30 - slope30 * sumX30) / n30;
        
        const trendLineValues30 = last30Dates.map((_, i) => slope30 * i + intercept30);
        
        const trendDirection30 = trendLineValues30[trendLineValues30.length - 1] - trendLineValues30[0];
        
        // LÍNEA AZUL SÓLIDA
        traces.push({
            x: last30Dates,
            y: trendLineValues30,
            type: 'scatter',
            mode: 'lines',
            name: 'Tendencia 30d',
            line: {
                color: '#3A8BFF',  // AZUL
                width: 1.5,
                dash: 'solid'
            },
            showlegend: true
        });
        
        // Flecha al final
        const arrowX30 = last30Dates[last30Dates.length - 1];
        const arrowY30 = trendLineValues30[trendLineValues30.length - 1];
        
        traces.push({
            x: [arrowX30],
            y: [arrowY30],
            type: 'scatter',
            mode: 'markers',
            name: 'Dir 30d',
            marker: {
                symbol: trendDirection30 > 0 ? 'triangle-up' : 'triangle-down',
                size: 10,
                color: '#3A8BFF',
                line: { color: 'white', width: 1 }
            },
            showlegend: false
        });
    }
    
    // Layout mejorado
    const layout = {
        title: {
            text: 'Fear & Greed Index - Sentimiento de Mercado',
            font: {color: 'white', size: 14, family: 'Arial'},
            x: 0.5,
            xanchor: 'center'
        },
        xaxis: {
            type: 'date',
            showgrid: true,
            gridcolor: 'rgba(128,128,128,0.2)',
            tickfont: {color: 'white', size: 9},
            showticklabels: true,
            tickangle: -45,
            title: {
                text: 'Fecha',
                font: {color: 'white', size: 10}
            }
        },
        yaxis: {
            title: 'Valor',
            range: yRange,  // AUTO-RANGO
            gridcolor: 'rgba(128,128,128,0.2)',
            tickfont: {color: 'white', size: 10},
            showgrid: true,
            zeroline: true,
            zerolinecolor: 'rgba(255,255,255,0.2)'
        },
        template: 'plotly_dark',
        height: 250,
        margin: {l: 40, r: 40, t: 40, b: 80},
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        showlegend: true,
        legend: {
            orientation: 'h',
            yanchor: 'top',
            y: -0.35,
            xanchor: 'center',
            x: 0.5,
            font: {color: 'white', size: 9, family: 'Arial'},
            bgcolor: 'rgba(0,0,0,0.7)',
            bordercolor: 'rgba(255,255,255,0.2)',
            borderwidth: 1
        },
        font: {
            family: 'Arial',
            size: 9,
            color: 'white'
        },
        shapes: [
            ...zoneShapes,  // Zonas de color
            // Líneas horizontales con etiquetas
            {
                type: 'line',
                x0: dates[0],
                y0: 20,
                x1: dates[dates.length - 1],
                y1: 20,
                line: {color: '#FF5B5B', width: 1, dash: 'dot'}
            },
            {
                type: 'line',
                x0: dates[0],
                y0: 80,
                x1: dates[dates.length - 1],
                y1: 80,
                line: {color: '#00C076', width: 1, dash: 'dot'}
            }
        ],
        annotations: [
            {
                x: dates[0],
                y: 20,
                xref: 'x',
                yref: 'y',
                text: 'Extreme Fear (20)',
                showarrow: false,
                xanchor: 'left',
                yanchor: 'bottom',
                font: {color: '#FF5B5B', size: 8}
            },
            {
                x: dates[0],
                y: 80,
                xref: 'x',
                yref: 'y',
                text: 'Extreme Greed (80)',
                showarrow: false,
                xanchor: 'left',
                yanchor: 'top',
                font: {color: '#00C076', size: 8}
            }
        ]
    };
    
    try {
        Plotly.newPlot('fear-greed-chart', traces, layout, {responsive: true, displaylogo: false});
        console.log('✅ Gráfico Fear & Greed generado');
    } catch (error) {
        console.error('❌ Error al crear gráfico:', error);
        chartDiv.innerHTML = '<div class="alert alert-danger">Error al generar gráfico</div>';
    }
};

// Función auxiliar para textos por defecto
function actualizarTextosPorDefecto() {
    document.getElementById('fng-current').textContent = '--';
    document.getElementById('fng-classification').textContent = '--';
    document.getElementById('fng-trend-7d').textContent = '--';
    document.getElementById('fng-trend-30d').textContent = '--';
    document.getElementById('fng-interpretation').textContent = 'Esperando datos...';
}
// ============ FUNCIONES DE TELEGRAM ============
function sendTelegramTest() {
    const symbol = document.getElementById('telegram-symbol')?.value || 'BTC-USDT';
    const interval = document.getElementById('telegram-interval')?.value || '1D';
    const includeChart = document.getElementById('include-chart')?.checked || true;
    
    showToast('📤 Enviando análisis a Telegram...', 'info');
    
    fetch('/api/telegram/test', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol, interval, include_chart: includeChart})
    })
    .then(response => {
        if (!response.ok) throw new Error(`Error HTTP ${response.status}`);
        return response.json();
    })
    .then(data => {
        if (data.success) {
            showToast('✅ ' + data.message, 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('telegramModal'));
            if (modal) modal.hide();
        } else {
            showToast('❌ Error: ' + (data.error || 'Error desconocido'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('❌ Error de conexión: ' + error.message, 'danger');
    });
}

function downloadAnalysisReport() {
    const symbol = document.getElementById('symbol-select')?.value || 'BTC-USDT';
    const interval = document.getElementById('interval-select')?.value || '1D';
    showToast('📥 Generando reporte PDF... (puede tardar ~5s)', 'info');
    
    fetch(`/api/generate_report?symbol=${symbol}&interval=${interval}`)
        .then(response => {
            if (!response.ok) throw new Error('Error en la descarga');
            return response.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `analisis_${symbol}_${interval}_${new Date().toISOString().slice(0,10)}.pdf`;
            a.click();
            window.URL.revokeObjectURL(url);
            showToast('✅ Reporte PDF descargado', 'success');
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('❌ Error al descargar reporte', 'danger');
        });
}

// ============ TOAST ============
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;
    
    const toastId = 'toast-' + Date.now();
    const bgColor = {'info': 'bg-info', 'success': 'bg-success', 'danger': 'bg-danger', 'warning': 'bg-warning'}[type] || 'bg-secondary';
    const icon = {'info': 'ℹ️', 'success': '✅', 'danger': '❌', 'warning': '⚠️'}[type] || '📌';
    
    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgColor} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${icon} ${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    new bootstrap.Toast(toastElement, {delay: 4000}).show();
    toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
}

// ============ RELOJ Y CALENDARIO ============
function updateBoliviaClock() {
    const clockEl = document.getElementById('bolivia-clock');
    const dateEl = document.getElementById('bolivia-date');
    if (!clockEl && !dateEl) return;
    
    const now = new Date();
    const boliviaTime = new Date(now.toLocaleString("en-US", {timeZone: "America/La_Paz"}));
    const timeStr = boliviaTime.toLocaleTimeString('es-BO', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    const dateStr = boliviaTime.toLocaleDateString('es-BO', {weekday: 'short', year: 'numeric', month: 'short', day: 'numeric'});
    
    if (clockEl) clockEl.textContent = timeStr;
    if (dateEl) dateEl.textContent = dateStr;
}

function updateCalendarInfo() {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    
    let nextAlert = 'Próximo ciclo';
    let activeTimeframes = '4H, 12H, 1D';
    
    if (hours === 19 && minutes >= 50 && minutes < 53) { nextAlert = '19:53 (1D)'; activeTimeframes = '1D, 1W'; }
    else if (hours === 19 && minutes >= 53 && minutes < 55) { nextAlert = '19:55 (12H)'; activeTimeframes = '12H, 1D'; }
    else if (hours === 19 && minutes >= 55 && minutes < 57) { nextAlert = '19:57 (4H)'; activeTimeframes = '4H, 12H'; }
    else if (hours === 23 && minutes >= 57) { nextAlert = '03:57 (4H)'; activeTimeframes = '4H'; }
    else if (hours === 3 && minutes >= 57) { nextAlert = '07:57 (4H)'; activeTimeframes = '4H'; }
    else if (hours === 7 && minutes >= 57) { nextAlert = '11:57 (4H)'; activeTimeframes = '4H'; }
    else if (hours === 11 && minutes >= 57) { nextAlert = '15:57 (4H)'; activeTimeframes = '4H'; }
    else if (hours === 15 && minutes >= 57) { nextAlert = '19:57 (4H)'; activeTimeframes = '4H'; }
    
    const nextAlertEl = document.getElementById('next-alert');
    const activeTimeframesEl = document.getElementById('active-timeframes');
    const marketStatusEl = document.getElementById('market-status');
    
    if (nextAlertEl) nextAlertEl.textContent = nextAlert;
    if (activeTimeframesEl) activeTimeframesEl.textContent = activeTimeframes;
    
    if (marketStatusEl) {
        if (hours >= 9 && hours < 17) { marketStatusEl.textContent = 'Horario Principal'; marketStatusEl.className = 'badge bg-success'; }
        else if (hours >= 0 && hours < 5) { marketStatusEl.textContent = 'Horario Asiático'; marketStatusEl.className = 'badge bg-info'; }
        else { marketStatusEl.textContent = 'Horario Americano'; marketStatusEl.className = 'badge bg-warning'; }
    }
}

// ============ ACTUALIZAR INFORMACIÓN DE MERCADO (HORARIOS) ============
window.updateMarketSessionInfo = function() {
    try {
        const now = new Date();
        const boliviaTime = new Date(now.toLocaleString("en-US", {timeZone: "America/La_Paz"}));
        const hour = boliviaTime.getHours();
        const weekday = boliviaTime.getDay(); // 0=Domingo, 1=Lunes, ..., 6=Sábado
        
        let sessionIcon = '🌏';
        let sessionName = 'Asiático';
        let liquidity = 'Baja';
        let sessionClass = 'bg-info';
        
        // Sesión Asiática: 19:00 - 03:00
        if ((hour >= 19 && hour <= 23) || (hour >= 0 && hour < 3)) {
            sessionIcon = '🌏';
            sessionName = 'Asiático';
            liquidity = 'Baja';
            sessionClass = 'bg-info';
        }
        // Sesión Europea: 03:00 - 11:00
        else if (hour >= 3 && hour < 11) {
            sessionIcon = '🇪🇺';
            sessionName = 'Europeo';
            liquidity = 'Alta';
            sessionClass = 'bg-primary';
        }
        // Sesión Americana: 11:00 - 19:00
        else if (hour >= 11 && hour < 19) {
            sessionIcon = '🇺🇸';
            sessionName = 'Americano';
            liquidity = 'Muy Alta';
            sessionClass = 'bg-success';
        }
        
        // Solapamiento Europa-América (11:00 - 15:00)
        if (hour >= 11 && hour < 15) {
            sessionName += ' + América';
            liquidity = 'Máxima';
            sessionClass = 'bg-warning';
        }
        
        // Días de la semana
        const dayNames = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
        const dayIcons = ['🏖️', '📆', '📊', '📊', '📊', '🏁', '🏖️'];
        const dayColors = ['secondary', 'warning', 'success', 'success', 'success', 'danger', 'secondary'];
        
        let dayIcon = dayIcons[weekday];
        let dayName = dayNames[weekday];
        let dayClass = dayColors[weekday];
        
        // Actualizar DOM
        const sessionIconEl = document.getElementById('market-session-icon');
        const sessionBadgeEl = document.getElementById('market-session-badge');
        const liquidityEl = document.getElementById('market-liquidity');
        const dayIconEl = document.getElementById('market-day-icon');
        const dayNameEl = document.getElementById('market-day-name');
        const marketStatusEl = document.getElementById('market-status');
        
        if (sessionIconEl) sessionIconEl.textContent = sessionIcon;
        if (sessionBadgeEl) {
            sessionBadgeEl.textContent = `Sesión ${sessionName}`;
            sessionBadgeEl.className = `badge ${sessionClass} me-2`;
        }
        if (liquidityEl) liquidityEl.textContent = `Liquidez: ${liquidity}`;
        if (dayIconEl) dayIconEl.textContent = dayIcon;
        if (dayNameEl) {
            dayNameEl.textContent = dayName;
            dayNameEl.className = `badge bg-${dayClass} me-3`;
        }
        
        // Actualizar estado del mercado
        if (marketStatusEl) {
            if (weekday === 0 || weekday === 6) {
                marketStatusEl.textContent = 'Fin de Semana';
                marketStatusEl.className = 'badge bg-secondary';
            } else if (hour >= 9 && hour < 17) {
                marketStatusEl.textContent = 'Horario Principal';
                marketStatusEl.className = 'badge bg-success';
            } else {
                marketStatusEl.textContent = 'Horario Extendido';
                marketStatusEl.className = 'badge bg-warning';
            }
        }
    } catch (error) {
        console.error('Error en updateMarketSessionInfo:', error);
    }
};

// Llamar a la función en la inicialización (YA ESTÁ MÁS ABAJO EN TU CÓDIGO)
 //window.updateMarketSessionInfo();  // ← Esta línea puede estar duplicada

// ============ ACTUALIZAR INFORMACIÓN DE CORRELACIÓN - VERSIÓN QUE SOLO MUESTRA DATOS REALES ============
window.updateCorrelationInfo = function(data) {
    try {
        console.log('📊 updateCorrelationInfo llamado con datos globales:', data);
        
        // Obtener elementos del DOM
        const btcStatusEl = document.getElementById('btc-correlation-status');
        const btcAdxEl = document.getElementById('btc-correlation-adx');
        const paxgStatusEl = document.getElementById('paxg-correlation-status');
        const paxgAdxEl = document.getElementById('paxg-correlation-adx');
        const ratioStatusEl = document.getElementById('ratio-correlation-status');
        const ratioAdxEl = document.getElementById('ratio-correlation-adx');
        const rotationSignalEl = document.getElementById('rotation-signal');
        const rotationDescEl = document.getElementById('rotation-description');
        const weightValueEl = document.getElementById('weight-value');
        const explanationEl = document.getElementById('correlation-explanation');
        const tfBadge = document.getElementById('correlation-timeframe');
        
        // Si no hay datos, mostrar mensaje genérico
        if (!data || !data.correlation) {
            if (btcStatusEl) {
                btcStatusEl.innerHTML = '<span class="badge bg-secondary">Esperando...</span>';
            }
            if (rotationSignalEl) {
                rotationSignalEl.textContent = 'NEUTRAL';
                rotationSignalEl.className = 'badge bg-secondary';
            }
            if (explanationEl) explanationEl.innerHTML = 'Seleccione un par para ver el análisis...';
            if (tfBadge) tfBadge.textContent = data?.timeframe || '1D';
            return;
        }
        
        const correlation = data.correlation;
        const currentTimeframe = data.timeframe || '1D';
        
        // Actualizar badge de temporalidad
        if (tfBadge) tfBadge.textContent = currentTimeframe;
        
        // ============ FUNCIÓN AUXILIAR PARA ACTUALIZAR CADA PAR ============
        const actualizarPar = (elementoStatus, elementoAdx, dataPar, nombrePar) => {
            if (!elementoStatus || !elementoAdx) return;
            
            if (!dataPar) {
                // No hay datos para este par - mostrar vacío
                elementoStatus.innerHTML = '<span class="badge bg-secondary">---</span>';
                elementoAdx.textContent = 'ADX: --';
                return;
            }
            
            const trend = dataPar.trend || {};
            const decision = dataPar.decision || {};
            
            let action = decision.action || 'N/A';
            let confidence = decision.confidence || 0;
            let direction = trend.direction || 'neutral';
            let adx = trend.adx || 0;
            
            let displayText = '';
            let badgeColor = 'bg-secondary';
            
            if (action !== 'N/A' && action !== 'NO_OPERAR') {
                displayText = action;
                if (action.includes('COMPRA') || action.includes('LONG')) {
                    badgeColor = 'bg-success';
                } else if (action.includes('VENTA') || action.includes('SHORT')) {
                    badgeColor = 'bg-danger';
                }
            } else {
                if (direction === 'bullish') {
                    displayText = 'ALCISTA';
                    badgeColor = 'bg-success';
                } else if (direction === 'bearish') {
                    displayText = 'BAJISTA';
                    badgeColor = 'bg-danger';
                } else {
                    displayText = 'NEUTRAL';
                    badgeColor = 'bg-secondary';
                }
            }
            
            if (confidence > 0) {
                displayText += ` ${confidence}%`;
            }
            
            elementoStatus.innerHTML = `<span class="badge ${badgeColor} me-2">${displayText}</span>`;
            elementoAdx.textContent = `ADX: ${adx.toFixed(1)}`;
        };
        
        // Actualizar cada par
        actualizarPar(btcStatusEl, btcAdxEl, correlation.btc_analysis, 'BTC');
        actualizarPar(paxgStatusEl, paxgAdxEl, correlation.paxg_analysis, 'PAXG');
        actualizarPar(ratioStatusEl, ratioAdxEl, correlation.paxg_btc_analysis, 'RATIO');
        
        // ============ OBTENER SEÑAL DE ROTACIÓN ============
        let rotationSignal = correlation.rotation_signal || 'NEUTRAL';
        let weightModifier = correlation.weight_modifier || 1.0;
        let weightPercent = ((weightModifier - 1.0) * 100).toFixed(0);
        if (weightPercent === '-100') weightPercent = '0';
        
        // Extraer datos para la explicación (usando valores reales o por defecto)
        const btcAdx = correlation.btc_analysis?.trend?.adx || 0;
        const btcDirection = correlation.btc_analysis?.trend?.direction || 'neutral';
        const ratioAdx = correlation.paxg_btc_analysis?.trend?.adx || 0;
        const ratioDirection = correlation.paxg_btc_analysis?.trend?.direction || 'neutral';
        const paxgAdx = correlation.paxg_analysis?.trend?.adx || 0;
        
        // Actualizar rotación
        if (rotationSignalEl) {
            let rotationBadge = 'bg-secondary';
            let rotationText = rotationSignal;
            let rotationDesc = '';
            let explanation = '';
            
            switch(rotationSignal) {
                case 'RISK_ON':
                    rotationBadge = 'bg-success';
                    rotationText = 'RIESGO-ON 🟢';
                    rotationDesc = 'Rotación hacia activos de riesgo (BTC)';
                    explanation = '🟢 Los inversores prefieren Bitcoin sobre el oro. Favorecer BTC/USDT.';
                    break;
                case 'RISK_OFF':
                    rotationBadge = 'bg-warning';
                    rotationText = 'RIESGO-OFF 🟡';
                    rotationDesc = 'Rotación hacia activos refugio (PAXG)';
                    explanation = '🟡 Los inversores buscan refugio en oro. Favorecer PAXG/USDT.';
                    break;
                case 'BTC_STRONGER':
                    rotationBadge = 'bg-success';
                    rotationText = 'BTC MÁS FUERTE 🟢';
                    rotationDesc = 'Bitcoin supera al oro en fortaleza';
                    explanation = '🟢 Bitcoin muestra mayor fortaleza relativa que el oro.';
                    break;
                case 'PAXG_STRONGER':
                    rotationBadge = 'bg-warning';
                    rotationText = 'ORO MÁS FUERTE 🟡';
                    rotationDesc = 'Oro supera a Bitcoin en fortaleza';
                    explanation = '🟡 El oro muestra mayor fortaleza relativa que Bitcoin.';
                    break;
                case 'POSITIVE_CORRELATION':
                    rotationBadge = 'bg-info';
                    rotationText = 'CORRELACIÓN POSITIVA 🔵';
                    rotationDesc = 'BTC y Oro se mueven en la misma dirección';
                    explanation = '🔵 Ambos activos muestran tendencias similares.';
                    break;
                case 'NEGATIVE_CORRELATION':
                    rotationBadge = 'bg-danger';
                    rotationText = 'CORRELACIÓN NEGATIVA 🔴';
                    rotationDesc = 'BTC y Oro se mueven en direcciones opuestas';
                    explanation = '🔴 Los activos muestran comportamientos opuestos.';
                    break;
                default:
                    rotationBadge = 'bg-secondary';
                    rotationText = 'NEUTRAL ⚪';
                    rotationDesc = 'Sin rotación clara entre activos';
                    
                    // Generar explicación basada en datos REALES disponibles
                    const btcTieneDatos = correlation.btc_analysis !== null;
                    const paxgTieneDatos = correlation.paxg_analysis !== null;
                    const ratioTieneDatos = correlation.paxg_btc_analysis !== null;
                    
                    if (btcTieneDatos && ratioTieneDatos) {
                        if (btcAdx > 25 && ratioAdx > 25) {
                            if (btcDirection === 'bullish' && ratioDirection === 'bearish') {
                                explanation = '⚪ Posible rotación a riesgo, pero falta confirmación.';
                            } else if (btcDirection === 'bearish' && ratioDirection === 'bullish') {
                                explanation = '⚪ Posible rotación a refugio, pero falta confirmación.';
                            } else {
                                explanation = '⚪ Los pares tienen tendencia pero sin oposición clara.';
                            }
                        } else if (btcAdx > 25) {
                            if (btcDirection === 'bearish') {
                                explanation = '⚪ BTC bajista pero el ratio no muestra fortaleza del oro.';
                            } else {
                                explanation = '⚪ BTC alcista pero el ratio no muestra debilidad del oro.';
                            }
                        } else if (btcAdx < 20 && ratioAdx < 20) {
                            explanation = '⚪ Ambos activos sin tendencia definida (ADX bajo). Mercado lateral.';
                        } else {
                            explanation = '⚪ No hay dominancia clara entre riesgo y refugio.';
                        }
                    } else if (btcTieneDatos) {
                        explanation = `⚪ BTC: ${btcDirection.toUpperCase()} (ADX ${btcAdx.toFixed(1)}). Esperando datos de otros pares.`;
                    } else if (ratioTieneDatos) {
                        explanation = `⚪ Ratio: ${ratioDirection.toUpperCase()} (ADX ${ratioAdx.toFixed(1)}). Esperando datos de BTC.`;
                    } else {
                        explanation = '⚪ Seleccione un par para ver el análisis completo.';
                    }
                    break;
            }
            
            rotationSignalEl.textContent = rotationText;
            rotationSignalEl.className = `badge ${rotationBadge}`;
            if (rotationDescEl) rotationDescEl.textContent = rotationDesc;
            if (explanationEl) explanationEl.innerHTML = explanation;
        }
        
        // ============ ACTUALIZAR PESO ============
        if (weightValueEl) {
            let weightColor = parseFloat(weightPercent) > 0 ? 'text-success' : 
                             (parseFloat(weightPercent) < 0 ? 'text-danger' : 'text-muted');
            weightValueEl.textContent = `${weightPercent}%`;
            weightValueEl.className = `badge bg-dark ${weightColor}`;
        }
        
        console.log('✅ Correlación global actualizada correctamente');
        
    } catch (error) {
        console.error('❌ Error en updateCorrelationInfo:', error);
    }
};


// ============ ACTUALIZAR INFORMACIÓN DE CONVICCIÓN ============
window.updateConvictionInfo = function(data) {
    if (!data || !data.decision || !data.decision.conviction) return;
    
    const conviction = data.decision.conviction;
    const action = data.decision.action;
    
    if (action === 'NO_OPERAR') {
        document.getElementById('conviction-section').style.display = 'none';
        document.getElementById('conviction-badge-mini').style.display = 'none';
        return;
    }
    
    // Mostrar sección de convicción
    const convictionSection = document.getElementById('conviction-section');
    const convictionBadgeMini = document.getElementById('conviction-badge-mini');
    
    if (convictionSection) convictionSection.style.display = 'block';
    if (convictionBadgeMini) {
        convictionBadgeMini.style.display = 'inline-block';
        convictionBadgeMini.innerHTML = `${conviction.icon || '🟡'} ${conviction.level || 'MEDIA'}`;
        convictionBadgeMini.className = `badge ${conviction.level === 'ALTA' ? 'bg-success' : conviction.level === 'MEDIA' ? 'bg-warning' : 'bg-danger'} me-3`;
    }
    
    // Actualizar icono y nivel
    const iconEl = document.getElementById('conviction-icon');
    const levelEl = document.getElementById('conviction-level');
    const percentageEl = document.getElementById('conviction-percentage');
    const descriptionEl = document.getElementById('conviction-description');
    const sizeEl = document.getElementById('suggested-size');
    const leverageEl = document.getElementById('suggested-leverage');
    const bonusEl = document.getElementById('bonus-factors');
    const degradationEl = document.getElementById('degradation-factors');
    
    if (iconEl) iconEl.textContent = conviction.icon || '🟡';
    if (levelEl) {
        levelEl.textContent = `CONVICCIÓN ${conviction.level || 'MEDIA'}`;
        levelEl.style.color = conviction.level === 'ALTA' ? '#00C076' : 
                              conviction.level === 'MEDIA' ? '#FFD700' : '#FF5B5B';
    }
    if (percentageEl) percentageEl.textContent = `${Math.round(conviction.raw_conviction || 70)}%`;
    if (descriptionEl) descriptionEl.textContent = conviction.description || '';
    if (sizeEl) sizeEl.textContent = `${Math.round((conviction.suggested_size || 1.0) * 100)}%`;
    if (leverageEl && data.levels) {
        const baseLeverage = data.levels.leverage || 10;
        const modifiedLeverage = Math.round(baseLeverage * (conviction.suggested_leverage_modifier || 1.0));
        leverageEl.textContent = `${modifiedLeverage}x`;
    }
    
    // Factores positivos y negativos
    if (bonusEl) {
        if (conviction.bonus_reasons && conviction.bonus_reasons.length > 0) {
            bonusEl.innerHTML = '✅ ' + conviction.bonus_reasons.join(' • ');
            bonusEl.style.display = 'block';
        } else {
            bonusEl.style.display = 'none';
        }
    }
    
    if (degradationEl) {
        if (conviction.degradation_reasons && conviction.degradation_reasons.length > 0) {
            degradationEl.innerHTML = '⚠️ ' + conviction.degradation_reasons.join(' • ');
            degradationEl.style.display = 'block';
        } else {
            degradationEl.style.display = 'none';
        }
    }
};



function updateSystemStatus() {
    fetch('/health')
        .then(response => response.json())
        .then(data => {
            const apiStatus = document.getElementById('api-status');
            const telegramStatus = document.getElementById('telegram-status');
            const analysisStatus = document.getElementById('analysis-status');
            const lastSignal = document.getElementById('last-signal');
            
            if (apiStatus) { apiStatus.textContent = 'Conectado'; apiStatus.className = 'badge bg-success'; }
            if (telegramStatus) { telegramStatus.textContent = 'Activo'; telegramStatus.className = 'badge bg-success'; }
            if (analysisStatus) { analysisStatus.textContent = 'Ejecutando'; analysisStatus.className = 'badge bg-warning'; }
            if (lastSignal && data.timestamp) {
                const lastUpdate = new Date(data.timestamp);
                const now = new Date();
                const diffMinutes = Math.floor((now - lastUpdate) / 60000);
                lastSignal.textContent = `Hace ${diffMinutes}min`;
            }
        })
        .catch(error => {
            const apiStatus = document.getElementById('api-status');
            if (apiStatus) { apiStatus.textContent = 'Error'; apiStatus.className = 'badge bg-danger'; }
        });
}

function toggleFullScreen() {
    const chartContainer = document.getElementById('main-chart-container');
    if (!chartContainer) return;
    if (!document.fullscreenElement) chartContainer.requestFullscreen();
    else document.exitFullscreen();
}

function downloadChart() {
    const chartDiv = document.getElementById('candle-chart');
    if (!chartDiv) return;
    Plotly.toImage(chartDiv, {format: 'png', width: 1200, height: 600})
        .then(dataUrl => {
            const link = document.createElement('a');
            link.href = dataUrl;
            link.download = `grafico_${currentSymbol}_${currentInterval}_${new Date().toISOString().slice(0,10)}.png`;
            link.click();
            showToast('✅ Gráfico capturado', 'success');
        })
        .catch(error => showToast('❌ Error al capturar gráfico', 'danger'));
}

// ============ ALIAS ============
function updateCharts(data) {
    updateAllCharts(data);
}

// ============ CONSTANTES ============
const SYMBOLS = {'BTC-USDT': {'name': 'BTC/USDT'}, 'PAXG-USDT': {'name': 'PAXG/USDT'}, 'PAXG-BTC': {'name': 'PAXG/BTC'}};
const TIMEFRAMES = {'4h': {'name': '4 Horas'}, '12h': {'name': '12 Horas'}, '1D': {'name': '1 Día'}, '1W': {'name': '1 Semana'}};

// Exponer función globalmente
window.updateFearGreedChart = updateFearGreedChart;

// ============ FUNCIÓN DE EMERGENCIA PARA CORRELACIÓN ============
// Esta función se ejecutará CADA VEZ que se cargue la página
// ============ SOLUCIÓN DEFINITIVA PARA CORRELACIÓN ============
// ============ SOLUCIÓN ULTRA DEFINITIVA PARA CORRELACIÓN ============
// ============ SOLUCIÓN MANUAL DIRECTA PARA CORRELACIÓN ============
// ============ SOLUCIÓN DEFINITIVA COMBINADA ============
// ============ SOLUCIÓN FINAL Y DEFINITIVA ============
