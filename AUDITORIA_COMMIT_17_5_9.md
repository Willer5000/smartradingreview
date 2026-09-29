# Auditoría previa — Commit 17.5.9

## Hallazgo P0 — segunda puerta tipo votación
En 17.5.8, `Operational Intelligence` ya construye una tesis y un `candidate_ready` con familias independientes, MTF, Strategy Bank, Research y macro. Sin embargo `moderator_candidate()` volvía a contar salidas de traders: requería al menos un especialista alineado y convertía en PRECAUCIÓN dos oposiciones fuertes. Esto reintroducía una segunda elección después de una tesis ya gobernada y podía producir timidez por evidencia correlacionada.

**Corrección 17.5.9:** el moderador productivo consume sólo el candidato gobernado. Los traders pasan a work products. Counter-evidence se conserva para explicar/aprender y Safety sigue siendo autoridad final.

## Hallazgo P0 — el Execution Desk no siempre recibía la oportunidad
En `calculate_entry_levels`, si el primer selector devolvía `sl_price is None` se retornaba inmediatamente; si `tp_price is None` también se retornaba antes del bloque de comités avanzados. Además los comités sólo refinaban cuando la baseline ya era geométricamente válida. Por tanto, un equipo capaz de buscar alternativas no podía trabajar precisamente cuando más se lo necesitaba.

**Corrección 17.5.9:** recovery estructural sólo para Futures/Multi-Activo cuando falta SL, falta TP o la baseline completa queda fuera de la geometría/RR técnico. Se usan únicamente zonas observadas. No baja ningún gate.

## Hallazgo P1 — estrategia contextual ya existe, pero no estaba explicitada como trabajo
`default_strategy_bank.select_strategy()` ya filtra por mercado/símbolo/TF/acción, elige familia según régimen/volatilidad/estructura/rotación/whales, evalúa candidatos y conserva alternativas. Multi-Activo mantiene bancos por clase de activo, sesión y contexto macro. 17.5.9 no reoptimiza esos parámetros: registra `strategy_reasoning_17_5_9` para coordinación, aprendizaje y QA.

## Anti-overfitting
- No se modifican thresholds de tesis, Safety, Publication, RR, Entry, SL o TP.
- No se incrementan priors 17.5.8.
- `preliminary_backtest_prior.py` queda byte-identical respecto a 17.5.8.
- No se calibra por resultados recientes para fabricar frecuencia.
- No existe cuota mínima/máxima de señales.

## Riesgo residual
La aplicación completa contiene módulos históricos y compatibilidad extensa. QA 17.5.9 valida los archivos modificados y contratos críticos, pero no sustituye un replay/version-matched OOS de todo el repositorio ni la observación posterior al deploy. El funnel debe usarse para verificar dónde terminan las oportunidades reales.
