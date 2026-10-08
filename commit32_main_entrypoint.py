"""Compatibility WSGI shim retained by Commit 33.3.

Old Render dashboards may still reference this historical module name.  It is
now intentionally inert: the current native app is the only runtime authority.
No trading/memory/publication monkeypatch is installed here.
"""
from app import app
print("[COMMIT33.3] historical entrypoint redirected to native app:app; no runtime patches", flush=True)
