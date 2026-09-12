from pathlib import Path


def _promotion(key, engine, tf):
    return {
        'candidate_key': key,
        'source_engine': engine,
        'stage': 'OBSERVE',
        'scope': {'timeframe': tf, 'market_family': 'CRYPTO_FUTURES'},
        'meta': {'is_current': True},
    }


def test_bridge_balances_strategic_timeframes(monkeypatch):
    import sys, types
    flask_stub=types.SimpleNamespace(Blueprint=lambda *a,**k: object(), jsonify=lambda *a,**k: None, render_template=lambda *a,**k: None, Response=object)
    monkeypatch.setitem(sys.modules, 'flask', flask_stub)
    import research_bridge as rb
    rows=[_promotion(f'5m-{i}','risk','5M') for i in range(500)]
    rows += [
        _promotion('4h-e','execution','4H'),
        _promotion('12h-s','strategy','12H'),
        _promotion('1d-t','traders','1D'),
        _promotion('1w-r','risk','1W'),
    ]
    selected=rb._balanced_candidates(rows, 40)
    tfs={str((x.get('scope') or {}).get('timeframe')).upper() for x in selected}
    assert {'4H','12H','1D','1W'}.issubset(tfs)
    cov=rb._coverage(rows)
    assert cov['strategic_timeframes']['1D']==1
    assert cov['strategic_timeframes']['1W']==1


def test_analytics_deferred_is_not_rendered_as_error():
    root=Path(__file__).resolve().parent
    app=(root/'app.py').read_text(encoding='utf-8')
    js=(root/'static'/'analytics.js').read_text(encoding='utf-8')
    assert "'success': True" in app
    assert "'retry_after_seconds': 15" in app
    assert "json.deferred && !json.data" in js
    assert "__qualityV2DeferredRetry" in js


def test_research_ui_has_strategic_coverage_indicator():
    root=Path(__file__).resolve().parent
    html=(root/'templates'/'analytics.html').read_text(encoding='utf-8')
    js=(root/'static'/'analytics.js').read_text(encoding='utf-8')
    assert 'rf-analytics-coverage' in html
    assert "['4H','12H','1D','1W']" in js
