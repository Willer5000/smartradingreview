# COMMIT22 — single free worker + bounded timeout + proactive recycling.
web: gunicorn commit20_2_main_entrypoint:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 80 --max-requests-jitter 20
