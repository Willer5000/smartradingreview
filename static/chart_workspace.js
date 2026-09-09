(function () {
    'use strict';

    const STORAGE_KEY = 'smartrading.chartWorkspace.v1';
    const MAX_AUTO = 4;
    const ALWAYS = new Set(['trading-zones', 'pattern4']);

    const META = {
        'trading-zones': { label: 'Zonas dinámicas de trading', category: 'Estructura', permanent: true },
        'rsi': { label: 'RSI y divergencias', category: 'Momentum' },
        'vwap': { label: 'Precio medio ponderado por volumen', category: 'Estrategias adaptativas' },
        'adx': { label: 'Fuerza de tendencia', category: 'Tendencia' },
        'macd': { label: 'MACD', category: 'Momentum' },
        'stochastic': { label: 'Estocástico', category: 'Momentum' },
        'volume': { label: 'Volumen y presión de mercado', category: 'Volumen' },
        'volume-profile': { label: 'Perfil de volumen', category: 'Volumen' },
        'fvg-ob': { label: 'Estructura institucional', category: 'Estructura' },
        'fibonacci': { label: 'Niveles de Fibonacci', category: 'Estructura' },
        'liquidation-heatmap': { label: 'Mapa de liquidaciones', category: 'Riesgo' },
        'ftm': { label: 'Fuerza y momentum del mercado', category: 'Tendencia' },
        'whale': { label: 'Actividad de grandes órdenes', category: 'Volumen' },
        'rsi_maverick': { label: 'RSI de bandas', category: 'Momentum' },
        'ichimoku': { label: 'Nube Ichimoku', category: 'Tendencia' },
        'squeeze': { label: 'Compresión de volatilidad', category: 'Riesgo' },
        'supertrend': { label: 'SuperTrend', category: 'Tendencia' },
        'bollinger': { label: 'Bandas de Bollinger', category: 'Riesgo' },
        'atr': { label: 'Volatilidad ATR', category: 'Riesgo' },
        'williams-cci': { label: 'Williams %R y CCI', category: 'Momentum' },
        'mfi-force': { label: 'Flujo monetario y fuerza', category: 'Volumen' },
        'fear-greed': { label: 'Sentimiento de mercado', category: 'Sentimiento' },
        'formation': { label: 'Formación chartista', category: 'Estructura' },
        'pattern4': { label: 'Patrón reciente de velas', category: 'Estructura', permanent: true }
    };

    let state = loadState();
    let lastData = null;
    let autoEvidence = [];
    let initialized = false;
    let originalPattern4 = null;
    let originalFormation = null;

    function loadState() {
        try {
            const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
            return {
                pinned: new Set(Array.isArray(raw.pinned) ? raw.pinned : []),
                manual: new Set(Array.isArray(raw.manual) ? raw.manual : []),
                hidden: new Set(Array.isArray(raw.hidden) ? raw.hidden : [])
            };
        } catch (_) {
            return { pinned: new Set(), manual: new Set(), hidden: new Set() };
        }
    }

    function saveState() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                pinned: [...state.pinned],
                manual: [...state.manual],
                hidden: [...state.hidden]
            }));
        } catch (_) {}
    }

    function ensureVWAPCard() {
        const container = document.getElementById('indicators-container');
        if (!container || document.querySelector('[data-indicator="vwap"]')) return;
        const card = document.createElement('div');
        card.className = 'card indicator-card mb-4';
        card.dataset.indicator = 'vwap';
        card.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="mb-0">Precio medio ponderado por volumen</h5>
                    <small class="text-muted">VWAP · contexto de precio y volumen</small>
                </div>
            </div>
            <div class="card-body indicator-content">
                <div id="vwap-chart" class="workspace-chart"></div>
                <div class="chart-note mt-2">Se muestra cuando el análisis usa VWAP o cuando lo agregas manualmente.</div>
            </div>`;
        container.appendChild(card);
    }

    function tagPatternCards() {
        const formation = document.getElementById('formation-40-chart')?.closest('.pattern-card');
        if (formation) {
            formation.dataset.indicator = 'formation';
            formation.classList.add('workspace-optional-card');
        }
        const pattern4 = document.getElementById('pattern-4-chart')?.closest('.pattern-card');
        if (pattern4) {
            pattern4.dataset.indicator = 'pattern4';
            pattern4.classList.add('workspace-optional-card');
        }
    }

    function cards() {
        return [...document.querySelectorAll('[data-indicator]')];
    }

    function createToolbar() {
        const container = document.getElementById('indicators-container');
        if (!container || document.getElementById('chart-workspace-toolbar')) return;
        const toolbar = document.createElement('section');
        toolbar.id = 'chart-workspace-toolbar';
        toolbar.className = 'chart-workspace-toolbar';
        toolbar.innerHTML = `
            <div class="workspace-toolbar-main">
                <div>
                    <div class="workspace-kicker">Espacio de análisis</div>
                    <div class="workspace-title">Evidencia gráfica de la decisión</div>
                    <div id="workspace-context" class="workspace-context">Los gráficos se adaptan a la justificación actual.</div>
                </div>
                <div class="workspace-actions">
                    <button type="button" class="btn btn-sm btn-outline-light" id="workspace-add-btn">+ Agregar gráfico</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary" id="workspace-show-evidence">Mostrar toda la evidencia</button>
                </div>
            </div>
            <div id="workspace-picker" class="workspace-picker" hidden></div>`;
        container.parentNode.insertBefore(toolbar, container);
        document.getElementById('workspace-add-btn')?.addEventListener('click', togglePicker);
        document.getElementById('workspace-show-evidence')?.addEventListener('click', () => {
            autoEvidence.forEach(id => state.manual.add(id));
            saveState();
            applyVisibility();
            renderVisible();
        });
        renderPicker();
    }

    function renderPicker() {
        const picker = document.getElementById('workspace-picker');
        if (!picker) return;
        const grouped = {};
        Object.entries(META).forEach(([id, meta]) => {
            if (meta.permanent) return;
            if (!document.querySelector(`[data-indicator="${id}"]`)) return;
            (grouped[meta.category] ||= []).push([id, meta]);
        });
        picker.innerHTML = Object.entries(grouped).map(([category, entries]) => `
            <div class="workspace-picker-group">
                <div class="workspace-picker-title">${category}</div>
                <div class="workspace-picker-items">
                    ${entries.map(([id, meta]) => `<button type="button" class="workspace-picker-item" data-add-chart="${id}">${meta.label}</button>`).join('')}
                </div>
            </div>`).join('');
        picker.querySelectorAll('[data-add-chart]').forEach(btn => btn.addEventListener('click', () => {
            const id = btn.dataset.addChart;
            state.manual.add(id);
            state.hidden.delete(id);
            saveState();
            applyVisibility();
            renderVisible();
        }));
    }

    function togglePicker() {
        const picker = document.getElementById('workspace-picker');
        if (!picker) return;
        picker.hidden = !picker.hidden;
    }

    function enhanceCards() {
        cards().forEach(card => {
            const id = card.dataset.indicator;
            const meta = META[id];
            if (!meta) return;
            card.classList.add('workspace-card');
            card.querySelectorAll('.btn-group').forEach(group => {
                const buttons = [...group.querySelectorAll('button')];
                if (buttons.length && buttons.every(btn => btn.classList.contains('btn-move') || btn.classList.contains('btn-collapse'))) group.remove();
            });
            const title = card.querySelector('.card-header h5, .card-header h6');
            if (title && meta.label) title.textContent = meta.label;
            const header = card.querySelector('.card-header') || card.querySelector(':scope > .d-flex');
            if (!header || header.querySelector('.workspace-card-actions') || meta.permanent) return;
            const actions = document.createElement('div');
            actions.className = 'workspace-card-actions';
            actions.innerHTML = `
                <button type="button" class="workspace-icon-btn" data-pin-chart="${id}" title="Fijar gráfico" aria-label="Fijar gráfico"><i class="fas fa-thumbtack"></i></button>
                <button type="button" class="workspace-icon-btn" data-remove-chart="${id}" title="Quitar gráfico" aria-label="Quitar gráfico"><i class="fas fa-xmark"></i></button>`;
            header.appendChild(actions);
            actions.querySelector('[data-pin-chart]')?.addEventListener('click', () => {
                if (state.pinned.has(id)) state.pinned.delete(id); else state.pinned.add(id);
                state.hidden.delete(id);
                saveState();
                applyVisibility();
            });
            actions.querySelector('[data-remove-chart]')?.addEventListener('click', () => {
                state.manual.delete(id);
                state.pinned.delete(id);
                state.hidden.add(id);
                saveState();
                applyVisibility();
            });
        });
    }

    function serverEvidence(data) {
        const list = data?.visual_evidence?.recommended;
        if (!Array.isArray(list)) return [];
        return list.map(item => typeof item === 'string' ? item : item?.chart).filter(Boolean);
    }

    function inferEvidence(data) {
        const ids = [];
        const add = id => { if (META[id] && !ids.includes(id)) ids.push(id); };
        const text = [data?.message, ...(data?.decision?.razones || []), ...(data?.decision?.estrategias || [])].filter(Boolean).join(' ').toLowerCase();
        const momentum = data?.momentum || {};
        const trend = data?.trend || {};
        const structure = data?.structure || {};
        const volume = data?.volume || {};
        const liq = data?.liquidation || {};
        const lab = data?.strategy_lab?.strategies || {};

        if ((momentum.divergences || []).length || (momentum.hidden_divergences || []).length || /\brsi\b|divergen/.test(text)) add('rsi');
        if (Number(trend.adx || 0) >= 22 || /\badx\b|\bdmi\b|tendencia/.test(text)) add('adx');
        if (/macd/.test(text)) add('macd');
        if (/estoc|stoch/.test(text)) add('stochastic');
        if (/volumen|ballena|whale|obv|mfi|flujo/.test(text) || volume.whale_buy || volume.whale_sell) add('volume');
        if (/poc|perfil de volumen|hvn|lvn/.test(text)) add('volume-profile');
        if (/liquida|liquidation/.test(text) || (liq.active_bins || []).length) add('liquidation-heatmap');
        if (/order block|bloque de orden|\bfvg\b|liquidity sweep|barrido de liquidez|mss|displacement/.test(text)) add('fvg-ob');
        if (/fibonacci|\bfib\b/.test(text)) add('fibonacci');
        if (/squeeze|compresi|volatilidad/.test(text)) add('squeeze');
        if (/bollinger/.test(text)) add('bollinger');
        if (/supertrend/.test(text)) add('supertrend');
        if (/ichimoku/.test(text)) add('ichimoku');
        if (/miedo|codicia|sentimiento/.test(text)) add('fear-greed');
        if (/patr[oó]n|vela|marubozu|envolvente|doji/.test(text)) add('pattern4');
        if (/tri[aá]ngulo|bander|doble techo|doble piso|hombro/.test(text)) add('formation');

        const retest = lab.breakout_retest || {};
        if (retest.state && !/NO_EDGE|NOT_|NONE|PENDING/.test(String(retest.state).toUpperCase())) add('trading-zones');
        if ((structure.fair_value_gaps || []).length || (structure.order_blocks || []).length) {
            if (/estructura|liquidez|order|fvg|sweep|mss/.test(text)) add('fvg-ob');
        }
        return ids;
    }

    function computeAutoEvidence(data) {
        const fromServer = serverEvidence(data);
        const inferred = inferEvidence(data);
        const merged = [...fromServer, ...inferred].filter((id, idx, arr) => META[id] && arr.indexOf(id) === idx && !ALWAYS.has(id));
        autoEvidence = merged.slice(0, MAX_AUTO);
        return autoEvidence;
    }

    function shouldRender(id) {
        if (ALWAYS.has(id)) return true;
        if (state.hidden.has(id) && !state.pinned.has(id) && !state.manual.has(id)) return false;
        return state.pinned.has(id) || state.manual.has(id) || autoEvidence.includes(id);
    }

    function visibleSecondaryCount() {
        return Object.keys(META).filter(id => !ALWAYS.has(id) && shouldRender(id)).length;
    }

    function applyVisibility() {
        cards().forEach(card => {
            const id = card.dataset.indicator;
            const visible = shouldRender(id);
            card.classList.toggle('workspace-hidden', !visible);
            card.classList.toggle('workspace-visible', visible);
            card.classList.toggle('workspace-permanent', ALWAYS.has(id));
            card.classList.toggle('workspace-pinned', state.pinned.has(id));
            if (visible && !ALWAYS.has(id)) {
                let badge = card.querySelector('.workspace-state-badge');
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'workspace-state-badge';
                    const header = card.querySelector('.card-header') || card.querySelector(':scope > .d-flex');
                    header?.appendChild(badge);
                }
                badge.textContent = state.pinned.has(id) ? 'Fijado' : autoEvidence.includes(id) ? 'Relacionado con la señal' : 'Agregado';
            }
            card.querySelectorAll('[data-pin-chart]').forEach(btn => btn.classList.toggle('active', state.pinned.has(id)));
        });
        const context = document.getElementById('workspace-context');
        if (context) {
            const action = String(lastData?.decision?.action || 'ESPERAR').replace('_SPOT', '').replace('_', ' ');
            context.textContent = `${action}: ${autoEvidence.length ? `${autoEvidence.length} gráficos destacan la evidencia principal.` : 'sin evidencia secundaria prioritaria; puedes agregar gráficos manualmente.'}`;
        }
        setTimeout(() => window.TradingTheme?.applyVisible(document), 0);
    }

    function renderVisible() {
        if (!lastData || typeof window.renderIndicatorChart !== 'function') return;
        Object.keys(META).forEach(id => {
            if (shouldRender(id)) window.renderIndicatorChart(id, lastData);
        });
        if (shouldRender('pattern4') && originalPattern4) originalPattern4(lastData);
        if (shouldRender('formation') && originalFormation) originalFormation(lastData);
        setTimeout(() => window.TradingTheme?.applyVisible(document), 25);
    }

    function updateAnalysis(data) {
        lastData = data || null;
        computeAutoEvidence(data || {});
        applyVisibility();
        setTimeout(() => humanizeRuntimeText(document.body), 80);
    }

    function humanizeRuntimeText(root) {
        const replacements = new Map([
            ['36W_V2_NORMALIZED', 'Motor de calidad actual'],
            ['SHADOW_ONLY', 'En evaluación · no afecta operaciones'],
            ['HARD_SAFETY', 'Descartada por seguridad'],
            ['PRE_GATE_REJECTION', 'Descartada antes de publicación'],
            ['CAUTIOUS_SHADOW', 'Configuración prudente en evaluación'],
            ['Q7', 'Estrategias adaptativas'],
            ['Q4B', 'protección del Guardián'],
            ['Q3', 'microestructura'],
            ['Q2', 'refinamiento de niveles'],
            ['Q1', 'calidad estructural de entrada'],
            ['Q6', 'control de integridad'],
            ['Shadow', 'en evaluación'],
            ['SHADOW', 'EN EVALUACIÓN'],
            ['Execution Safety', 'Seguridad de ejecución'],
            ['Entry Quality', 'Calidad de entrada'],
            ['SL Quality', 'Calidad del stop'],
            ['TP Quality', 'Calidad del objetivo']
        ]);
        const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            const parent = node.parentElement;
            if (!parent || ['SCRIPT', 'STYLE', 'CODE', 'PRE'].includes(parent.tagName)) return;
            let text = node.nodeValue;
            replacements.forEach((value, key) => { text = text.split(key).join(value); });
            node.nodeValue = text;
        });
    }

    function wrapPatternRenderers() {
        originalPattern4 = window.updatePattern4Chart;
        originalFormation = window.updateFormation40Chart;
        if (typeof originalPattern4 === 'function') {
            window.updatePattern4Chart = function (data) {
                lastData = data || lastData;
                if (shouldRender('pattern4')) return originalPattern4(data);
            };
        }
        if (typeof originalFormation === 'function') {
            window.updateFormation40Chart = function (data) {
                lastData = data || lastData;
                if (shouldRender('formation')) return originalFormation(data);
            };
        }
    }

    function init() {
        if (initialized) return;
        initialized = true;
        ensureVWAPCard();
        tagPatternCards();
        createToolbar();
        enhanceCards();
        const ensurePermanentOrder = () => {
            const zones = document.querySelector('[data-indicator="trading-zones"]');
            const container = document.getElementById('indicators-container');
            if (zones && container && zones.parentElement === container) container.prepend(zones);
        };
        ensurePermanentOrder();
        setTimeout(ensurePermanentOrder, 180);
        document.body.classList.add('workspace-ready');
        wrapPatternRenderers();
        humanizeRuntimeText(document.body);
        applyVisibility();
    }

    window.ChartWorkspace = {
        init,
        updateAnalysis,
        shouldRender,
        renderVisible,
        humanizeRuntimeText,
        get lastData() { return lastData; }
    };

    document.addEventListener('DOMContentLoaded', init);
})();
