"""C46 local invariants; no third-party libs or market access needed."""
import copy
import os
import unittest
from unittest.mock import patch

import c46_structural_live as c46


def layer(side='BULLISH', both=False):
    o = [{'direction': side}]
    f = [{'direction': side}]
    sweeps = [{'direction': side}]
    if both:
        o.append({'direction': 'BEARISH'})
        f.append({'direction': 'BEARISH'})
        sweeps.append({'direction': 'BEARISH'})
    return {
        'structure':{'order_blocks':o, 'fair_value_gaps':f,
                     'liquidity_sweeps':sweeps},
        'momentum':{'divergences':['bullish RSI divergence' if side=='BULLISH' else 'bearish RSI divergence']},
        'volume': {'volume_ratio':1.5},
    }


def ev(layers, op, desired):
    return {'structure':True,'momentum':True,'volume':True,
            'mss':True,'trend':False,'pullback':True,'range':False}


def selector(op, **kwargs):
    return {'id':'REAL_STRATEGY_BANK', 'family':'SWEEP_REVERSAL', 'quality':88}


def fallback(op, layers, *, symbol='ETH-USDT', timeframe='30m', system_type='futures', multi=lambda x: False):
    return c46.try_add_candidate(op,layers,symbol=symbol,timeframe=timeframe,
                                 system_type=system_type,is_multiasset=multi,
                                 evidence_builder=ev,select_strategy=selector,
                                 official_cell=lambda *args:True)


class C46SafeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ,{'C46_STRUCTURAL_LIVE_ENABLED':'1','C46_MULTI_LIVE_ENABLED':'1'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_new_long_candidate_futures(self):
        original = {'candidate_ready':False,'candidate_action':'NO_OPERAR', 'thesis':{}}
        before=copy.deepcopy(original)
        out = fallback(original,layer())
        self.assertEqual(out['candidate_action'],'LONG')
        self.assertEqual(out['candidate_source'],'C46_ADD_ON_CLOSED_BAR')
        self.assertTrue(out['candidate_contract']['safety_is_downstream'])
        self.assertFalse(out['c46_audit']['publishes_on_its_own'])
        self.assertEqual(original,before)

    def test_short_candidate_futures(self):
        out = fallback({'candidate_ready':False,'candidate_action':'NO_OPERAR', 'thesis':{}},layer('BEARISH'))
        self.assertEqual(out['candidate_action'],'SHORT')

    def test_original_signal_identity(self):
        old={'candidate_ready':True,'candidate_action':'LONG','levels':{'entry':99}, 'candidate_contract':{'passed':True}}
        self.assertIs(fallback(old,layer('BEARISH')),old)

    def test_spot_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        self.assertIs(fallback(old,layer(),system_type='spot'),old)

    def test_disabled_untouched(self):
        with patch.dict(os.environ,{'C46_STRUCTURAL_LIVE_ENABLED':'0'}):
            old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
            self.assertIs(fallback(old,layer()),old)

    def test_critical_macro_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR','thesis':{'macro_risk':'CRITICAL'}}
        self.assertIs(fallback(old,layer()),old)

    def test_no_explicit_signed_zone_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        layers=layer()
        layers['structure']['fair_value_gaps']=[{'price':100}]
        layers['structure']['order_blocks']=[{'price':101}]
        self.assertIs(fallback(old,layers),old)

    def test_mtf_conflict_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR','multi_timeframe':{'conflict':True}}
        self.assertIs(fallback(old,layer()),old)

    def test_no_premium_when_invalid_playbook(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        with patch.object(c46,'_enabled',lambda *args:True):
            ret=c46.try_add_candidate(old,layer(),symbol='ETH-USDT',timeframe='30m',system_type='futures',
                                      is_multiasset=lambda _:False,evidence_builder=ev,
                                      select_strategy=lambda *a,**k:{'id':'NO_PLAYBOOK','family':'NONE','quality':95},
                                      official_cell=lambda *args:True)
        self.assertIs(ret,old)

    def test_low_strategy_quality_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        ret=c46.try_add_candidate(old,layer(),symbol='ETH-USDT',timeframe='30m',system_type='futures',
                                  is_multiasset=lambda _:False,evidence_builder=ev,
                                  select_strategy=lambda *a,**k:{'id':'S','family':'SWEEP','quality':70},
                                  official_cell=lambda *args:True)
        self.assertIs(ret,old)

    def test_no_unsupported_timeframe(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        self.assertIs(fallback(old,layer(),timeframe='12h'),old)

    def test_multiasset_is_supported_if_original_bank_valid(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        self.assertEqual(fallback(old,layer(),symbol='XAG-USDT',timeframe='4h',multi=lambda x:True)['candidate_action'],'LONG')

    def test_multiasset_disabled_individually(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        with patch.dict(os.environ,{'C46_MULTI_LIVE_ENABLED':'0'}):
            self.assertIs(fallback(old,layer(),symbol='XAG-USDT',timeframe='4h',multi=lambda x:True),old)

    def test_mixed_directions_abstention(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        def ev_both(*args):return ev(*args)
        self.assertIs(c46.try_add_candidate(old,layer(both=True), symbol='ETH-USDT',timeframe='30m',system_type='futures',
                                 is_multiasset=lambda _:False,evidence_builder=ev_both,
                                 select_strategy=selector, official_cell=lambda *args:True),old)

    def test_macro_hold_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR','candidate_source':'MACRO_CRITICAL_HOLD'}
        self.assertIs(fallback(old,layer()),old)

    def test_research_veto_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR','research_candidates':{'LONG':{'state':'ALPHA_DECAY'}}}
        self.assertIs(fallback(old,layer()),old)

    def test_nonofficial_cell_untouched(self):
        old={'candidate_ready':False,'candidate_action':'NO_OPERAR'}
        ret=c46.try_add_candidate(old,layer(),symbol='ETH-USDT',timeframe='30m',system_type='futures',
                                  is_multiasset=lambda _:False,evidence_builder=ev,
                                  select_strategy=selector,official_cell=lambda *args:False)
        self.assertIs(ret,old)

if __name__=='__main__':unittest.main()
