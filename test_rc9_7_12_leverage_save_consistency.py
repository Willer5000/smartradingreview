from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_lifecycle_refreshes_leverage_only_for_same_geometry():
    text = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert "same_geometry = (" in text
    assert "existing_record['leverage'] = fresh_leverage" in text
    assert "existing_record['leverage_policy_version']" in text
    assert "valid_until" in text  # lifecycle remains present; migration does not recreate it


def test_manual_modal_uses_canonical_signal_leverage():
    text = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')
    assert 'function futResolveManualCanonicalLeverage(candidate)' in text
    assert 'const canonicalLeverage = futResolveManualCanonicalLeverage(candidate);' in text
    assert 'sig.leverage = safeSaveLeverage;' in text
    assert 'Sugerido por el sistema: ${safeSaveLeverage}x' in text


def test_non_tradable_conviction_does_not_fake_70_100_or_leverage():
    text = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    block = text[text.index('window.updateConvictionInfo'):]
    assert "const tradableAction = ['LONG', 'SHORT', 'COMPRA_SPOT', 'VENTA_SPOT']" in block
    assert 'Number.isFinite(rawConviction) ? rawConviction : 0' in block
    assert 'Number.isFinite(suggestedSize) ? suggestedSize : 0' in block
    assert "leverageEl.textContent = '--';" in block
    assert 'conviction.raw_conviction || 70' not in block
    assert 'conviction.suggested_size || 1.0' not in block
