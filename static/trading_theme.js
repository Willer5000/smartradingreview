(function () {
    'use strict';

    const palette = {
        bg: '#08111f',
        panel: '#0d1726',
        panelAlt: '#111d2d',
        border: '#263348',
        grid: 'rgba(120, 142, 170, 0.16)',
        text: '#e7edf5',
        muted: '#9baabd',
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

    function applyToPlot(plotOrId) {
        if (!window.Plotly) return;
        const el = typeof plotOrId === 'string' ? document.getElementById(plotOrId) : plotOrId;
        if (!el || !el.classList || !el.classList.contains('js-plotly-plot')) return;
        try {
            window.Plotly.relayout(el, {
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
            });
        } catch (err) {
            console.debug('Tema Plotly no aplicado:', err);
        }
    }

    function applyVisible(root) {
        const scope = root || document;
        scope.querySelectorAll('.js-plotly-plot').forEach(applyToPlot);
    }

    window.TradingTheme = { palette, baseLayout, applyToPlot, applyVisible };
})();
