# Commit 14 — liquidation heatmap recalibration + visual regression guards
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_backend_keeps_fail_open_and_public_calibration_contract():
    src = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'class LiquidationPublicCalibration' in src
    assert 'LEGACY_FALLBACK' in src
    assert "'long_factor': 1.0" in src
    assert "'short_factor': 1.0" in src
    assert "'data_type': 'MODEL_ESTIMATE_NOT_OBSERVED'" in src
    assert 'OHLCV_PUBLIC_DERIVATIVES_CALIBRATED_V3' in src
    assert 'LiquidationHeatmap(timeframe=timeframe, symbol=symbol)' in src


def test_frontend_uses_true_heatmap_without_exposing_internal_architecture():
    src = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    start = src.index('function updateLiquidationHeatmap(data)')
    end = src.index('// ============ ZONAS DINÁMICAS DE TRADING ============', start)
    block = src[start:end]
    assert "type: 'heatmap'" in block
    assert 'Intensidad relativa' in block
    assert 'PUBLIC_MARKET_CALIBRATED' in block
    lowered = block.lower()
    for forbidden in ('comité', 'committee', 'especialista', 'trader interno'):
        assert forbidden not in lowered


def test_liquidation_card_is_user_facing_and_technically_labeled():
    src = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    marker = 'data-indicator="liquidation-heatmap"'
    pos = src.index(marker)
    fragment = src[pos:pos + 5000]
    assert 'Presión LONG relativa' in fragment
    assert 'Presión SHORT relativa' in fragment
    assert 'no representa posiciones privadas ni montos exactos' in fragment
    lowered = fragment.lower()
    for forbidden in ('comité', 'committee', 'especialista', 'trader interno'):
        assert forbidden not in lowered
