from types import SimpleNamespace

from reason_presenter import compose_professional_recommendation
from supabase_client import SupabaseClient


class _FakeTable:
    def __init__(self):
        self.payload = None

    def upsert(self, payload, on_conflict=None):
        self.payload = payload
        return self

    def execute(self):
        return SimpleNamespace(data=[dict(self.payload or {})])


class _FakeDB:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        table = self.tables.setdefault(name, _FakeTable())
        return table


def _client_for_preferences():
    client = SupabaseClient.__new__(SupabaseClient)
    client.enabled = True
    client._preferences_cache = {}
    client.client = _FakeDB()
    client._with_retry = lambda fn, *args, **kwargs: fn()
    client.get_user_preferences = lambda user: {
        'spot_telegram_enabled': True,
        'spot_telegram_timeframes': ['4h', '12h', '1D', '1W'],
        'futures_scalping_telegram_enabled': False,
        'futures_scalping_timeframes': [],
        'futures_scalping_start_time': None,
        'futures_scalping_end_time': None,
        'futures_scalping_weekdays': [],
        'futures_scalping_timezone': 'UTC',
    }
    return client


def test_spot_telegram_preferences_are_cached_per_user_after_write():
    client = _client_for_preferences()

    assert client.upsert_user_preferences('Willer', {
        'spot_telegram_enabled': True,
        'spot_telegram_timeframes': ['4h'],
    }) is True
    assert client._preferences_cache['Willer']['value']['spot_telegram_timeframes'] == ['4h']

    assert client.upsert_user_preferences('Danilo', {
        'spot_telegram_enabled': True,
        'spot_telegram_timeframes': ['12h'],
    }) is True
    assert client._preferences_cache['Danilo']['value']['spot_telegram_timeframes'] == ['12h']
    assert client._preferences_cache['Willer']['value']['spot_telegram_timeframes'] == ['4h']

    assert client.upsert_user_preferences('Damir', {
        'spot_telegram_enabled': True,
        'spot_telegram_timeframes': ['1D'],
    }) is True
    assert client._preferences_cache['Damir']['value']['spot_telegram_timeframes'] == ['1D']
    assert client._preferences_cache['Willer']['value']['spot_telegram_timeframes'] == ['4h']
    assert client._preferences_cache['Danilo']['value']['spot_telegram_timeframes'] == ['12h']


def test_recommendation_is_structured_and_deduplicates_multitimeframe():
    message = compose_professional_recommendation(
        'ESPERAR',
        symbol='BTC-USDT',
        symbol_name='BTC/USDT',
        timeframe_name='1 Día',
        confidence=74,
        trend={
            'adx': 43.4,
            'plus_di': 42.7,
            'minus_di': 12.1,
            'direction': 'bullish',
        },
        momentum={
            'indicators': {
                'rsi': 70.1,
                'macd_histogram': 239.855,
                'stoch_k': 89.0,
            }
        },
        volatility={'atr_pct': 1.2},
        volume={'volume_ratio': 0.68},
        structure={'stop_hunts': [{'direction': 'bullish', 'level': 79000}]},
        confirmation={'status': 'pending'},
        multi_timeframe={
            'public_summary': (
                'Alineación multitemporal: contexto 1W alcista; '
                'estructura 1D alcista.'
            )
        },
        operational_context={
            'thesis': {
                'families': {
                    'multiframe': {
                        'detail': (
                            'Alineación multitemporal: contexto 1W alcista; '
                            'estructura 1D alcista.'
                        ),
                        'score': 0.8,
                    }
                }
            }
        },
        specialist_reasons=[],
        timestamp_text='2026-09-21 06:49:16 Hora Bolivia',
        max_evidence=7,
    )

    assert 'Tendencia:' in message
    assert 'Estructura:' in message
    assert 'Volumen:' in message
    assert 'Momentum:' in message
    assert 'Multitemporal:' in message
    assert 'Decisión: ESPERAR.' in message
    assert message.lower().count('contexto 1w alcista') == 1
    assert 'Lectura multitemporal: Alineación multitemporal:' not in message
    assert 'Existe una tesis potencial' not in message
    assert 'volumen relativo bajo (0.68×)' in message
    assert 'confirmación posterior al barrido de liquidez' in message
