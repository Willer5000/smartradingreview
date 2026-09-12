from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
FUTURES = (ROOT / 'static' / 'futures.js').read_text(encoding='utf-8')


def test_f1_wrong_auto_invalidation_is_removed():
    assert '_futures_waiting_record_invalidation_reason' not in APP
    assert '_futures_current_entry_authority' not in APP
    assert "return 'CURRENT_RECOMMENDATION_NOT_EXECUTABLE'" not in APP
    assert "return 'CURRENT_RECOMMENDATION_DIRECTION_CHANGED'" not in APP
    assert "return 'SUPERSEDED_BY_NEW_CLOSED_CANDLE'" not in APP


def test_waiting_entry_keeps_original_lifecycle_policy():
    assert "status == 'waiting_entry'" in APP
    assert "record['lifecycle_status'] = 'expired'" in APP
    assert "record['close_reason'] = 'expired_no_entry'" in APP
    assert "record['lifecycle_status'] = 'entry_touched'" in APP


def test_active_endpoint_exposes_origin_snapshot():
    assert "'recommendation_snapshot': True" in APP
    assert "'recommendation_context': 'ACTIVE_SIGNAL_ORIGIN'" in APP
    assert "'message': record.get('message', '')" in APP
    assert "'source_candle_close_timestamp': record.get(" in APP


def test_active_card_opens_snapshot_context_not_plain_pair_navigation():
    assert 'window.openFuturesActiveSignal(' in FUTURES
    assert 'data-signal="${_encodeFuturesSignal(sig)}"' in FUTURES
    assert 'RECOMENDACIÓN QUE ORIGINÓ ESTA SEÑAL' in FUTURES


def test_current_market_is_secondary_and_does_not_replace_signal():
    assert 'Estado actual del mercado · no reemplaza la señal' in FUTURES
    assert 'No invalida ni reescribe automáticamente una señal' in FUTURES
    assert '_futuresSignalSnapshotToRecommendation' in FUTURES
    assert '_futuresRenderCurrentMarketState' in FUTURES


def test_manual_navigation_clears_pinned_snapshot():
    assert '_futuresClearPinnedSignalRecommendation' in FUTURES
    assert "id === 'symbol-select' || id === 'interval-select'" in FUTURES


def test_f2_recovers_only_wrong_f1_invalidations_while_still_valid():
    assert "f1_wrong_reasons = {" in APP
    assert "'CURRENT_RECOMMENDATION_NOT_EXECUTABLE'" in APP
    assert "'CURRENT_RECOMMENDATION_DIRECTION_CHANGED'" in APP
    assert "'SUPERSEDED_BY_NEW_CLOSED_CANDLE'" in APP
    assert "_record['lifecycle_status'] = 'waiting_entry'" in APP
    assert "_record['recovered_from_f1_at'] = now_iso" in APP
    assert "now_utc < _valid_until" in APP
