"""Stable import path for the current core candidate router.

Commit 33.3 intentionally advances the core module without a WSGI/runtime
monkeypatch.  app.py keeps its historical import path.
"""
from pipeline_integrity_175103 import *  # noqa: F401,F403
from pipeline_integrity_175103 import _multiasset_strategy_from_live_layers  # noqa: F401
