"""Run: python -m unittest discover -s tests -p 'test_c46_live_integration.py' -v"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.getenv('C46_TEST_BASE', str(ROOT)))
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(BASE))
from c46_incremental_live import ROUTES, augment_candidate


def layers(side='LONG'):
    direction = 'BULLISH' if side=='LONG' else 'BEARISH'
    return {
        'structure': {'current_price': 2500, 'direction': direction,
            'order_blocks':[{'direction':direction}],
            'fair_value_gaps':[{'direction':direction}],
            'liquidity_sweeps':[{'direction':direction}],
            'fib_levels':{'0.618': 2475}, 'retest':True},
        'trend':{'direction':direction,'adx':24,'indicators':{
            'parabolic_sar_trend': direction,'ichimoku_cloud':direction}},
        'momentum':{'direction':direction,'divergences':[
            {'direction':direction,'indicator':'RSI'}, {'direction':direction,'indicator':'MACD'}]},
        'volume': {'vwap': 2460 if side=='LONG' else 2560,'volume_ratio':1.25,'obv_trend':direction},
        'volatility': {'bb_position':0.5},
        'macro_context':{'risk_level':'LOW'},
    }


def op():
    return {'candidate_ready':False,'candidate_action':'NO_OPERAR','candidate_source':'NONE',
        'thesis':{'action':'NO_OPERAR','direction':'NEUTRAL','quality':0},
        'indicator_groups':{}, 'multi_timeframe':{'conflict':False},
        'research_candidates':{}}


def evidence(l, o, d):
    side = 'LONG' if d == 'BULLISH' else 'SHORT'
    s=l.get('structure') or {}; m=l.get('momentum') or {}
    target='BULLISH' if side=='LONG' else 'BEARISH'
    okay=s.get('direction') == target
    return {'structure':okay,'momentum':m.get('direction')==target,
            'sweep': bool(s.get('liquidity_sweeps')) and okay,
            'mss': okay, 'pullback':True, 'trend':okay,
            'volume':True, 'mtf':False}


def selector(*args,**kwargs):
    return {'id':'TEST_EXISTING_BANK','family':kwargs['preferred_family'], 'quality':90}


def official(*args): return True


def augment(o,l=None,sym='ETH-USDT',tf='30M'):
    return augment_candidate(o,layers=l or layers(),symbol=sym,timeframe=tf,system_type='FUTURES',
                             evidence_builder=evidence,select_strategy=selector,official_cell=official)


class C46Tests(unittest.TestCase):
    def setUp(self):
        os.environ['C46_INCREMENTAL_LIVE_ENABLED']='1'
    def tearDown(self):
        os.environ.pop('C46_INCREMENTAL_LIVE_ENABLED', None)

    def test_exact_routes_nine(self):
        self.assertEqual(len(ROUTES),9)
        self.assertEqual(len({(r[0],r[1],r[2],r[3]) for r in ROUTES}),9)

    def test_add_long_when_original_neutral(self):
        out=augment(op())
        self.assertTrue(out['candidate_ready'])
        self.assertEqual(out['candidate_action'],'LONG')
        self.assertEqual(out['candidate_source'],'C46_INCREMENTAL_LIVE')
        self.assertFalse(out['c46_live_audit']['oos_statistically_validated'])
        self.assertTrue(out['candidate_contract']['safety_is_downstream'])

    def test_keep_original_exactly_when_ready(self):
        original=op() | {'candidate_action':'SHORT','candidate_ready':True, 'candidate_source':'THESIS_CORE'}
        self.assertIs(augment(original),original)

    def test_disable_env(self):
        os.environ['C46_INCREMENTAL_LIVE_ENABLED']='0'
        before=op()
        self.assertIs(augment(before),before)

    def test_unsupported_symbol_no_signal(self):
        self.assertFalse(augment(op(),sym='BTC-USDT')['candidate_ready'])

    def test_no_missing_structural_input(self):
        l=layers()
        l['structure']['fair_value_gaps']=[]
        l['structure']['order_blocks']=[]
        l['momentum']['divergences']=[]
        self.assertFalse(augment(op(),l)['candidate_ready'])

    def test_macro_critical(self):
        l=layers();l['macro_context']['risk_level']='CRITICAL'
        self.assertFalse(augment(op(),l)['candidate_ready'])

    def test_mtf_conflict(self):
        o=op();o['multi_timeframe']['conflict']=True
        self.assertFalse(augment(o)['candidate_ready'])

    def test_research_alpha_decay(self):
        o=op();o['research_candidates']={'LONG':{'state':'ALPHA_DECAY'}}
        self.assertFalse(augment(o)['candidate_ready'])

    def test_no_new_threads_or_io(self):
        code=(ROOT/'c46_incremental_live.py').read_text()
        for needle in ('requests.', 'httpx.', 'Thread(', 'Process(', 'supabase', 'socket.', 'open('):
            self.assertNotIn(needle,code)

    def test_baseline_app_not_packaged(self):
        self.assertFalse((ROOT/'app.py').exists())


if __name__=='__main__': unittest.main()

class RealLayerCompatibility(unittest.TestCase):
    def test_app_momentum_string_divergences(self):
        from c46_incremental_live import _divergence_types
        live = {'divergences':['rsi_bull_divergence','macd_bull_divergence'],
                'divergence_details':[{'type':'bullish','oscillator':'MACD'},
                                      {'type':'hidden_bullish','oscillator':'RSI'}]}
        self.assertEqual(_divergence_types(live,'LONG'),{'RSI','MACD'})
        self.assertEqual(_divergence_types(live,'SHORT'),set())
