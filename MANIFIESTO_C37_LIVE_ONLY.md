# Manifiesto técnico del repositorio C37 LIVE-ONLY + Guardian

Archivos existentes en base restaurada: 730
Archivos de la versión completa: 733 (incluye este manifiesto)

## Funciones oficiales intocadas (AST idéntico)

- _send_confirmed_signal_telegram
- _attempt_confirmed_outbox_event_inner
- _confirmed_web_registry_rows_34_4
- api_multiasset_signals_previous
- api_multiasset_signals_active
- api_futures_signals_previous
- api_futures_signals_active
- _merge_official_telegram_rows_34_4
- _core_publication_authority
- _apply_profitability_router
- _run_scheduled_spot_analysis

## Módulos críticos íntegros byte a byte

- official_signal_store.py
- futures_system.py
- multiasset_system.py
- static/futures.js
- runtime_persistence.py
- futures_universe.py
- portfolio_guardian.py
- saved_signals.py
- templates/official_signal.html
- static/chart_workspace.js

## Archivos añadidos frente a la base restaurada

- INSTRUCCIONES_COMMIT37_LIVE_ONLY_GUARDIAN.md
- tests/test_commit37_live_only_guardian.py

## SHA-256 de archivos de operación

- `app.py`: `cc0093dfb7d49dc37bc5951da6b2fdfecfff30e369b1f25d1ee1f96d085fe271`
- `static/script.js`: `8e704493f637eaa766ed75429dbc270c02da2d8b473b4a77df88fc1c69baaff8`
- `render.yaml`: `4b045ded83fe0108487cf04a237c7956634a469ae39bb17ae97e6db5cf37bc60`
- `official_signal_store.py`: `c9b28d93d9ed447b46a2d1a11abb2a6975806d7f3e63b007b81099ebd225b5fc`
- `futures_universe.py`: `6c6482be8d666c2d24217e51dea2b3f4807f708c4a6f3eb3de793937d4f26509`
- `multiasset_system.py`: `ab9888287d4b28a76996e6584d289e044888971de5d348d96fd8024238f37ccf`

Pruebas: 43 tests locales seleccionados pasaron, `py_compile app.py` y `node --check static/script.js` pasaron.
La prueba de importación Flask integrada no se pudo realizar en el contenedor de auditoría (Flask no está instalado).
Pruebas de Render 512MB/Telegram/Supabase real: pendientes.
