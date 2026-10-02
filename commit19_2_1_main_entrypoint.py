"""Commit 19.2.1 — Root-cause Quality Recovery entrypoint.

Closed-candle Multi coverage, pre-decision asset semantics, LIVE-native
structural repair authority, and all-market numerical theoretical Greeks.
"""
from commit19_1_runtime import install_pre_app, install_post_app
_PRE = install_pre_app()
from app import app  # noqa: E402
_POST = install_post_app()
