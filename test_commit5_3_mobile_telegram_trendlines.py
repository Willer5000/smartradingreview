from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_telegram_has_lightweight_report_and_explicit_probe():
    app = read('app.py')
    html = read('templates/index.html')
    assert "@app.route('/api/telegram/test', methods=['POST'])" in app
    assert "default_with_charts = '0' if delivery == 'telegram' else '1'" in app
    assert "sendDocument" in app
    assert "Probar conexión Telegram" in html
    assert "delivery=telegram&with_charts=0" in html


def test_mobile_plotly_legends_are_moved_outside_plot_area():
    theme = read('static/trading_theme.js')
    assert "const hasLegend" in theme
    assert "update['legend.y'] = -0.20" in theme
    assert "update['margin.b']" in theme
    assert "window.addEventListener('resize'" in theme


def test_trendline_channel_is_white_solid_and_projected():
    js = read('static/script.js')
    assert "const trendProjectionBars = 10" in js
    assert "color: '#f2f2f2'" in js
    assert "dash: 'solid'" in js
    assert "['support', 'resistance']" in js
    assert "range: [lastDates[0], trendProjectionDate]" in js


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
