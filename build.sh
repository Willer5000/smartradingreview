#!/usr/bin/env bash
set -euo pipefail

# Commit 33.4.3 — deterministic source authority.
# Never let bytecode/test caches survive a source replacement.  They are not
# application state and must not participate in a deploy or rollback.
find . -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf {} + || true
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete || true

# Low-memory deterministic Render build.
python -m pip install --no-cache-dir -r requirements.txt
python -m compileall -q -j 1 .
