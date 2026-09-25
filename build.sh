#!/usr/bin/env bash
set -euo pipefail

# Commit 12.4.2 — Render Build Artifact Maintenance
#
# Goal: keep the deployed Python application functionally identical while
# reducing avoidable bytecode inside Render's native-runtime build artifact.
#
# Why this is safe:
# - package versions and requirements are unchanged;
# - application/trading code is unchanged;
# - pip still installs the exact same dependencies;
# - Python can import packages directly from .py sources when .pyc files are
#   absent;
# - app.py is still precompiled because it is the largest local module and was
#   the original reason for the build-time compile step.

export PIP_DISABLE_PIP_VERSION_CHECK=1

# Remove stale bytecode copied from the Git repository/build workspace before
# packaging. Some historical commits accidentally tracked __pycache__ files.
find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

# Do not precompile every dependency installed by pip. The native Render image
# otherwise contains both Python sources and a large set of duplicate .pyc
# files, which are not required for correctness and enlarge the upload phase.
python -m pip install --no-cache-dir --no-compile -r requirements.txt

# Defensive cleanup of repository-local bytecode only. Site-packages installed
# by pip are already covered by --no-compile.
find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

# Preserve the useful part of the previous build optimization: precompile only
# the very large Flask entry point. This catches syntax errors during BUILD and
# reduces startup parsing overhead without compiling the entire repository.
python -m py_compile app.py

# Small build diagnostics. They do not change the artifact and make future
# Render failures easier to distinguish from Python/build failures.
echo "==> Build maintenance: dependencies installed without bulk bytecode"
echo "==> Build maintenance: app.py precompiled successfully"
echo "==> Build maintenance: repository size before Render packaging"
du -sh . || true
