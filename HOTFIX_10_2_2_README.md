# Hotfix 10.2.2 · Canal Telegram de señales Spot confirmado

## Motivo
Las preferencias `spot_telegram_enabled` y `spot_telegram_timeframes` pertenecen al Guardian/TGP del portafolio Spot. No deben bloquear las señales técnicas confirmadas del sistema.

## Comportamiento correcto
- Guardian/TGP Spot: respeta preferencias personales de Telegram y temporalidades seleccionadas.
- Señales técnicas Spot: toda `COMPRA_SPOT` / `VENTA_SPOT` confirmada puede alertar en 4h, 12h, 1D y 1W, independientemente de las preferencias del Guardian.
- La alerta se intenta inmediatamente después de confirmar la celda cerrada, sin esperar a terminar el barrido completo Spot.
- Deduplicación: símbolo × timeframe × dirección × cierre de vela.
- Se conserva deep-link por `signal_id`.
- Se conserva la ventana anti-backfill para workers demorados.

## No modifica
Entry, SL, TP, Safety, R:R, leverage, comité, ReviewTrader, Reachability, aprendizaje, Shadow→Canary→Active, Alpha Decay, MFE/MAE ni PDF de aprendizaje.

## Archivo de producción
- `app.py`

## Deploy
Si NO aplicaste Hotfix 10.2.1, no lo apliques: usa directamente este 10.2.2 sobre Commit 10.2 FINAL.
Si ya aplicaste 10.2.1, reemplaza nuevamente `app.py` por el de este ZIP.

## Commit sugerido
`Hotfix 10.2.2 - Separa señales Spot Telegram de preferencias Guardian`
