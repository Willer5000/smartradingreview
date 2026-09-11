#!/usr/bin/env bash
set -euo pipefail

# Hotfix 14.8 — deterministic/low-memory build for Render Free.
# 1) Install without keeping pip's download cache in the build image.
# 2) Precompile the very large app.py (and local modules) during BUILD.
#    Runtime Gunicorn then loads .pyc instead of spending a large transient
#    amount of RAM parsing/compiling ~1.7 MB / 46k lines of Python source.
python -m pip install --no-cache-dir -r requirements.txt
python -m compileall -q -j 1 .
