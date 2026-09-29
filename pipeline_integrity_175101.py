"""Compatibility shim for app.py from Commit 17.5.10.1.

17.5.10.4 keeps the historical import path stable while the governed implementation advances.
"""
from pipeline_integrity_175102 import *  # noqa: F401,F403
from pipeline_integrity_175102 import _multiasset_strategy_from_live_layers  # noqa: F401
