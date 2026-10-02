# Commit 19.2.3 — Candle Close Authority

Release incremental sobre 19.2.2.

## Objetivos
1. Telegram CONFIRMADA sólo nace cerca del cierre real de su propia vela.
2. 1W usa calendario lunes 00:00 UTC → lunes 00:00 UTC.
3. Spot deja de recalcular 1D/1W en cada cierre 4h.
4. Futures/Multi heredan la misma autoridad temporal para sus señales Premium confirmadas.
5. Sin bajar filtros de calidad ni aumentar recursos Render.

## No cambia
- Entry >= 65 para Quant Synthesis.
- SL >= 60.
- TP >= 60.
- Safety/RR/Leverage/Guardian/Alpha Decay.
- Champions Commit 19.

## Start Command
`gunicorn commit19_2_3_main_entrypoint:app --timeout 180 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 30 --max-requests 120 --max-requests-jitter 20`

## SQL
No requiere SQL.
