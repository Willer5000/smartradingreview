# Auditoría técnica — Commit 17.5 Stable Base Execution Hardening

## Decisión de arquitectura

Este commit parte exclusivamente del `smartradingreview-main(4)` suministrado por el usuario como último baseline útil. No importa la arquitectura de señales de Commit 17.4/17.4.1.

Objetivo: conservar generación de señales, login, Multi-Activo, Telegram, Liquidation Map, leverage y frontend del baseline, y mejorar únicamente la geometría de ejecución Entry/SL/TP.

## Alcance funcional

Archivos funcionales modificados:

- `app.py`
- `execution_geometry_committee.py`

Archivos críticos comprobados byte a byte idénticos al baseline:

- `futures_system.py`
- `leverage_policy.py`
- `operational_intelligence.py`
- `default_strategy_bank.py`
- `multiasset_system.py`
- `portfolio_guardian.py`
- `saved_signals.py`
- `static/script.js`
- `static/futures.js`
- `templates/index.html`

## Correcciones de trading

### Entry

Se conserva el selector existente. Sólo se mejora el desempate entre pools de liquidación cercanos mediante intensidad relativa del heatmap actual. La intensidad no crea dirección ni aumenta la confianza de la señal.

### Stop Loss

El comité ya calculaba un `sl_buffer_atr` contextual, pero la construcción de candidatos no lo aplicaba de forma efectiva: seguía usando offsets fijos. Ahora los candidatos estructurales quedan detrás de la zona de reacción con clearance contextual por tipo de estructura y volatilidad.

La lógica sigue penalizando stops excesivamente anchos. El cambio busca reducir stops colocados exactamente donde el precio probablemente haga sweep/reacción, sin convertirlos en pérdidas desproporcionadas.

### Take Profit

El Liquidation Map moderno utiliza `relative_participation`; el ranking TP todavía conservaba umbrales históricos en supuestos USD. Ahora usa intensidad normalizada del mapa actual.

El TP puede situarse ligeramente antes de la zona de reacción/target estructural para aumentar probabilidad de ejecución. El buffer se reduce automáticamente si compromete el R/R técnico mínimo contextual.

## Elementos deliberadamente NO modificados

- Confirmación LONG/SHORT/Spot/Multi-Activo
- Safety
- filtros de publicación
- CORE/MEDIUM/HIGH
- reglas MTF
- banco de estrategias
- política de leverage
- Guardian
- login/autorización
- Telegram
- frontend
- generación/calibración del Liquidation Map
- llamadas de IA/Groq
- Supabase

## Recursos

El commit no añade polling, workers, llamadas Groq/LLM, endpoints externos, escrituras automáticas a Supabase ni descargas adicionales. Los cálculos nuevos reutilizan datos y estructuras ya presentes en memoria.

## QA

- `python -m py_compile app.py execution_geometry_committee.py`: PASS
- `python -m compileall -q .`: PASS
- `node --check static/script.js`: PASS
- `node --check static/futures.js`: PASS
- `pytest test_rc9_8_execution_geometry.py test_commit17_5_execution_hardening.py`: **25/25 PASS**
- QA específico Commit 17.5: **7/7 PASS**

Los fallos detectados en suites históricas más amplias fueron reproducidos sin cambios en el baseline original y corresponden a aserciones antiguas/artefactos históricos; no son regresiones de este commit.

## Criterio de despliegue

Este commit debe reemplazar la rama 17.4/17.4.1 para volver al motor estable indicado por el usuario. Tras desplegar, congelar la lógica de señal y evaluar estadísticamente Entry/SL/TP antes de nuevos cambios.
