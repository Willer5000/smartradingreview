"""Compatibility shim for app.py from Commit 17.5.10.1.

17.5.10.2 keeps the old import path so app.py does not need a 2.2 MB replacement.
"""
from pipeline_integrity_175102 import *  # noqa: F401,F403
from pipeline_integrity_175102 import _multiasset_strategy_from_live_layers  # noqa: F401
