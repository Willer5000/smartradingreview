"""RC9.7.14 process defaults for the 512 MB Render runtime.

Python imports sitecustomize during interpreter startup, before app.py imports
numpy/pandas. Setting these defaults here prevents native math libraries from
creating avoidable worker pools. Explicit environment settings still win.
"""
import os

for _name in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

os.environ.setdefault("LOW_MEMORY_MODE", "1")
os.environ.setdefault("FREE_RUNTIME_MAX_THREADS", "18")
os.environ.setdefault("FREE_RUNTIME_BACKGROUND_LOCK_WAIT_SECONDS", "1")
os.environ.setdefault("FREE_RUNTIME_INTERACTIVE_LOCK_WAIT_SECONDS", "10")
