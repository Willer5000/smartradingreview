# Commit 17.5.10 FINAL — instalación

Base esperada: Commit 17.5.9 `e8d5cd0c148cde9d8c9dfeed1ec2bdee3030148a`.

## Archivos que SÍ cambian / se agregan

En la raíz del repositorio:

- REEMPLAZAR `app.py`
- REEMPLAZAR `execution_specialist_committees.py`
- REEMPLAZAR `worker_orchestration.py`
- REEMPLAZAR `preliminary_backtest_prior.py`
- AGREGAR `market_maker_math.py`
- AGREGAR `options_market_context.py`
- AGREGAR `profitability_qualification.py`

Frontend:

- REEMPLAZAR `templates/index.html`
- AGREGAR `static/market_maker_frontend.js`

## Archivos que NO debes reemplazar por 17.5.10

- `futures_system.py`
- `leverage_policy.py`
- `static/script.js`
- `static/futures.js`

17.5.10 depende de sus versiones actuales de 17.5.9 y las congela por SHA en `BASELINE_DEPENDENCIES_17_5_10.json`.

## Orden recomendado en GitHub Web / VSCode Web

1. Verificar que main sigue en 17.5.9 antes de aplicar el paquete.
2. Arrastrar/reemplazar los cuatro archivos Python existentes de raíz.
3. Agregar los tres Python nuevos.
4. Reemplazar `templates/index.html`.
5. Agregar `static/market_maker_frontend.js`.
6. NO tocar `futures_system.py`, `leverage_policy.py`, `static/script.js` ni `static/futures.js`.
7. Hacer un único commit: `Commit 17.5.10 FINAL - coverage integrity, options context and OOS validation`.
8. Esperar deploy completo de Render.
9. Hacer Ctrl+F5.

## Validación post-deploy

Revisar primero que las páginas Spot, Futures y Multi-Activo cargan. En Futures debe aparecer la tarjeta **Opciones · Gamma / Delta / 0DTE**. Para un activo sin cadena compatible debe mostrar “Sin cadena compatible” o modo teórico, nunca inventar GEX observado.

Después observar el funnel de Futures/Multi-Activo. Interesa verificar que las celdas se analicen, que los candidatos Multi 1h reciban turnos sucesivos y que una ausencia de señales se pueda atribuir a un gate técnico concreto.

Telegram: una entrega fallida debe quedar retryable, no marcada como terminada. No forzar backfill de una señal que ya perdió vigencia.

Leverage: comprobar en una señal futura que `leverage_policy_expected_mode` es `STANDARD_TECHNICAL_MAX_V6`. Un 2x/3x es válido sólo si V6 llegó a ese techo técnico; 17.5.10 no debe fijarlo por preferencia ni subirlo artificialmente.

## Pruebas incluidas

Ejecutar desde el ready-tree:

```bash
python qa_commit17_5_10_final.py
python backtest_commit17_5_10_profitability.py
python -m py_compile app.py execution_specialist_committees.py worker_orchestration.py preliminary_backtest_prior.py market_maker_math.py options_market_context.py profitability_qualification.py
node --check static/market_maker_frontend.js
```

Resultado esperado del QA específico: `53/53 PASS`.

## Limitaciones explícitas

- No se ha desplegado desde este entorno.
- El backtest rentable valida preliminarmente una cohorte Futures 30m, no todo el sistema.
- Multi-Activo todavía no posee una cohorte productiva histórica equivalente.
- El OOS es cronológico pero no prospectivo/cego de 17.5.10.
- No existe garantía de rentabilidad futura ni de que deba haber señales todos los días.
