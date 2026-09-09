(function () {
    'use strict';

    const palette = {
        bg: '#050505',
        panel: '#0b0b0b',
        panelAlt: '#101010',
        border: '#2a2a2a',
        grid: 'rgba(150, 150, 150, 0.12)',
        text: '#e8e8e8',
        muted: '#a5a5a5',
        bullish: '#22c982',
        bearish: '#f05d6f',
        warning: '#e5b94f',
        info: '#5aa7ff',
        research: '#a78bfa',
        neutral: '#8190a5'
    };

    function baseLayout(title, extra) {
        const common = {
            title: title ? { text: title, font: { color: palette.text, size: 14 }, x: 0.01, xanchor: 'left' } : undefined,
            paper_bgcolor: palette.panel,
            plot_bgcolor: palette.panel,
            font: { color: palette.text, family: '-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif', size: 11 },
            hovermode: 'x unified',
            hoverlabel: { bgcolor: palette.panelAlt, bordercolor: palette.border, font: { color: palette.text } },
            margin: { l: 54, r: 24, t: title ? 46 : 24, b: 44 },
            legend: { orientation: 'h', yanchor: 'bottom', y: 1.01, xanchor: 'right', x: 1, font: { color: palette.muted, size: 10 } },
            xaxis: { gridcolor: palette.grid, linecolor: palette.border, zerolinecolor: palette.grid, automargin: true },
            yaxis: { gridcolor: palette.grid, linecolor: palette.border, zerolinecolor: palette.grid, automargin: true }
        };
        return Object.assign(common, extra || {});
    }

    function _isMobile() {
        return (window.innerWidth || document.documentElement.clientWidth || 1200) < 768;
    }

    function _clonePlain(value) {
        try { return JSON.parse(JSON.stringify(value || {})); }
        catch (_) { return {}; }
    }

    function applyToPlot(plotOrId) {
        if (!window.Plotly) return;
        const el = typeof plotOrId === 'string' ? document.getElementById(plotOrId) : plotOrId;
        if (!el || !el.classList || !el.classList.contains('js-plotly-plot')) return;
        try {
            // Guardar una sola vez la configuración que el gráfico tenía en escritorio.
            // Así, si el usuario rota el dispositivo o vuelve a una pantalla grande,
            // no dejamos la leyenda permanentemente en modo móvil.
            if (!el.__tradingThemeDesktopLayout) {
                el.__tradingThemeDesktopLayout = {
                    legend: _clonePlain(el.layout?.legend),
                    margin: _clonePlain(el.layout?.margin),
                    height: Number(el.layout?.height || 0) || null
                };
            }

            const mobile = _isMobile();
            const desktop = el.__tradingThemeDesktopLayout || {};
            const hasLegend = el.layout?.showlegend !== false
                && Array.isArray(el.data)
                && el.data.some(trace => trace?.showlegend !== false && trace?.name);
            const update = {
                paper_bgcolor: palette.panel,
                plot_bgcolor: palette.panel,
                'font.color': palette.text,
                'xaxis.gridcolor': palette.grid,
                'xaxis.linecolor': palette.border,
                'yaxis.gridcolor': palette.grid,
                'yaxis.linecolor': palette.border,
                'legend.font.color': palette.muted,
                'hoverlabel.bgcolor': palette.panelAlt,
                'hoverlabel.bordercolor': palette.border,
                'hoverlabel.font.color': palette.text
            };

            if (mobile && hasLegend) {
                // En móvil, la leyenda sale completamente del área de datos.
                // TradingView prioriza el precio y evita tapar velas/indicadores.
                update['legend.orientation'] = 'h';
                update['legend.x'] = 0;
                update['legend.xanchor'] = 'left';
                update['legend.y'] = -0.20;
                update['legend.yanchor'] = 'top';
                update['legend.font.size'] = 8;
                update['legend.bgcolor'] = 'rgba(0,0,0,0)';
                update['legend.borderwidth'] = 0;
                update['legend.tracegroupgap'] = 2;
                update['margin.b'] = Math.max(Number(el.layout?.margin?.b || 44), 112);
                update['margin.l'] = Math.max(42, Math.min(Number(el.layout?.margin?.l || 54), 52));
                update['margin.r'] = Math.max(12, Math.min(Number(el.layout?.margin?.r || 24), 24));
                update['height'] = Math.max(Number(el.layout?.height || 340), 390);
            } else if (desktop.legend || desktop.margin) {
                const lg = desktop.legend || {};
                const mg = desktop.margin || {};
                if (Object.prototype.hasOwnProperty.call(lg, 'orientation')) update['legend.orientation'] = lg.orientation;
                if (Object.prototype.hasOwnProperty.call(lg, 'x')) update['legend.x'] = lg.x;
                if (Object.prototype.hasOwnProperty.call(lg, 'xanchor')) update['legend.xanchor'] = lg.xanchor;
                if (Object.prototype.hasOwnProperty.call(lg, 'y')) update['legend.y'] = lg.y;
                if (Object.prototype.hasOwnProperty.call(lg, 'yanchor')) update['legend.yanchor'] = lg.yanchor;
                if (lg.font?.size) update['legend.font.size'] = lg.font.size;
                if (Object.prototype.hasOwnProperty.call(mg, 'b')) update['margin.b'] = mg.b;
                if (Object.prototype.hasOwnProperty.call(mg, 'l')) update['margin.l'] = mg.l;
                if (Object.prototype.hasOwnProperty.call(mg, 'r')) update['margin.r'] = mg.r;
                if (desktop.height) update['height'] = desktop.height;
            }

            window.Plotly.relayout(el, update);
        } catch (err) {
            console.debug('Tema Plotly no aplicado:', err);
        }
    }

    function applyVisible(root) {
        const scope = root || document;
        scope.querySelectorAll('.js-plotly-plot').forEach(applyToPlot);
    }

    let _resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(_resizeTimer);
        _resizeTimer = setTimeout(() => applyVisible(document), 120);
    }, { passive: true });

    window.TradingTheme = { palette, baseLayout, applyToPlot, applyVisible };
})();
