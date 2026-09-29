# Auditoría — Commit 17.5.8

## Objetivo

Incorporar evidencia preliminar de backtest de familias, Entry, SL y TP al sistema y al trader de aprendizaje, sin convertirla en una autorización automática de señales.

## Diagnóstico de inoperatividad

La ausencia simultánea de Futures y Multi-Activo puede provenir de dos tipos de causa: mercado realmente sin setups que superen los gates, o problemas de cobertura/visibilidad/scheduling. 17.5.8 no baja filtros para distinguirlas.

Se conserva el Signal Funnel cache-only y se añade `/api/diagnostics/backtest-prior`. Futures ordena el round-robin para evaluar antes celdas con evidencia OOS positiva, pero todas las celdas siguen cubiertas. Multi-Activo conserva el router 1H propio y el lane de señales vigentes corregido en 17.5.6.

## Riesgo de overfitting

Mitigaciones:

- El prior familiar es exacto por celda; no se extrapola universalmente.
- Sólo se almacenaron celdas con N>=10, expectancy >=0.12R, PF>=1.25 y DD<=6R.
- Peso máximo de prior Entry/familia: 4 puntos.
- SL/TP no reciben reajustes globales.
- El prior no crea dirección, no salta MTF/Safety/Publicación, no toca leverage.
- Multi-Activo queda neutral hasta disponer de historial propio point-in-time.

## QA

- 17 tests específicos de 17.5.8: PASS.
- 20 tests heredados de 17.5.6 adaptados sólo al nuevo version string: PASS.
- `py_compile app.py execution_specialist_committees.py preliminary_backtest_prior.py`: PASS.

## Rollback

Para volver a 17.5.7: restaurar juntos `app.py` y `execution_specialist_committees.py` de 17.5.7 y retirar `preliminary_backtest_prior.py`. No mezclar app 17.5.8 con committee 17.5.7.
