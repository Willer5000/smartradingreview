"""Commit 18.2 Main entrypoint.

Patches lightweight decision helpers before app.py imports them, then patches
the Multi scanner after the existing application has loaded.
"""
from commit18_2_runtime import install_pre_app, install_post_app

_PRE = install_pre_app()

from app import app  # noqa: E402

_POST = install_post_app()
