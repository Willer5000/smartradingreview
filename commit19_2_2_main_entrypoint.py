"""Commit 19.2.2 — Runtime Scheduler & Multi Read Recovery.

Preserves Commit 19.2.1 trading quality while fixing background starvation,
cache-only Multi UI reads, and precise execution-downgrade observability.
"""
from commit19_1_runtime import install_pre_app, install_post_app
_PRE = install_pre_app()
from app import app  # noqa: E402
_POST = install_post_app()
