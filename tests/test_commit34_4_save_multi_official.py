"""Offline regression: saving a Multi official confirmation must not require Futures cache."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from datetime import datetime

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'app.py').read_text()
TREE=ast.parse(APP)

class DummyApp:
    def route(self,*_args,**_kwargs):return lambda fn:fn

class MultiOfficialSaveTest(unittest.TestCase):
    def test_kstr_official_outbox_signal_can_save_without_futures_snapshot(self):
        node=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='api_saved_signals_create')
        node.decorator_list=[]
        captured={}
        expected={
            'signal_id':'KSTR-official-2026', 'symbol':'KSTR-USDT', 'timeframe':'1h',
            'action':'LONG', 'confidence':87,'entry':90,'stop_loss':88,
            'take_profit':94, 'leverage':7,'risk_reward':2.0,
            'source_candle_timestamp':'2026-10-10T11:00:00+00:00',
            'valid_until':'2026-10-11T16:00:00+00:00',
            'lifecycle_status':'waiting_entry',
        }
        class Request:
            @staticmethod
            def get_json():
                return {'market':'multiasset','source_context':'PREVIOUS_CONFIRMED',
                    'source_signal_id':'KSTR-official-2026',
                    'symbol':'OTHER-USDT','action':'SHORT','timeframe':'1D',
                    'entry':90,'stop_loss':88,'take_profit':94,'leverage':7,
                    'investment_usdt':25}
        def verify(market,sid,context):
            self.assertEqual((market,sid,context),('multiasset','KSTR-official-2026','PREVIOUS_CONFIRMED'))
            return expected.copy()
        def create_saved_signal(row):
            captured.update(row)
            return {'id':'saved-test'},None
        globals_for_fn={
            'app':DummyApp(),'request':Request(), 'jsonify':lambda row:row,
            '_authenticated_user':lambda:'demo_user',
            '_find_official_telegram_row_34_4':verify,
            '_get_futures_analysis_snapshot_read_only':lambda: self.fail('Multi read from Futures!'),
            '_configured_futures_module':lambda: self.fail('heavy Futures module loaded'),
            'datetime':datetime,
        }
        exec(compile(ast.Module(body=[node],type_ignores=[]),'save.py','exec'),globals_for_fn)
        dummy=types.ModuleType('saved_signals');dummy.create_saved_signal=create_saved_signal
        with patch.dict(sys.modules,{'saved_signals':dummy}):
            response=globals_for_fn['api_saved_signals_create']()
        self.assertEqual(response['success'],True,response)
        self.assertEqual(captured['symbol'],'KSTR-USDT')
        self.assertEqual(captured['timeframe'],'1h')
        self.assertEqual(captured['action'],'LONG')
        self.assertEqual(captured['source_signal_id'],'KSTR-official-2026')
        self.assertEqual(captured['source_valid_until'],expected['valid_until'])
        self.assertEqual(captured['original_stop_loss'],88)

if __name__=='__main__':unittest.main()
