# SmartradingReview — Commit 17.5.9
## Worker Orchestration + Structural Opportunity Recovery

Base verificada: GitHub HEAD `50de12bcddfdad302bf4f3e36ee2d0b6c2a132f1` (Commit 17.5.8). Los Git blob SHA de `app.py`, `execution_specialist_committees.py` y `preliminary_backtest_prior.py` coinciden exactamente con ese HEAD antes de aplicar 17.5.9.

### Objetivo
Eliminar timidez causada por coordinación redundante sin bajar Safety, sin relajar Entry/SL/TP/RR, sin aumentar apalancamiento y sin introducir cuotas de señales.

### Cambios funcionales
1. **Worker Orchestration** (`worker_orchestration.py`): los 10 traders pasan a ser trabajadores con entregables. El payload legado tipo voto se conserva sólo para atribución/aprendizaje y compatibilidad. Operational Intelligence es dueño de la tesis; ningún trabajador puede ganar por mayoría, vetar o cambiar LONG↔SHORT.
2. **Production moderator**: si `Operational Intelligence` ya construyó `candidate_ready`, el candidato pasa a ejecución sin exigir una segunda mayoría de traders ni contar apoyos/oposiciones. MTF, Research negative states, macro crítico, Strategy Bank, Entry/SL/TP, Safety y Publication permanecen.
3. **Strategy reasoning**: se conserva la selección contextual existente de Strategy Bank y se registra explícitamente por régimen, volatilidad, mercado, activo, TF, evidencia y alternativas ya evaluadas.
4. **Structural Opportunity Recovery**: Futures/Multi-Activo ya no termina inmediatamente cuando el primer selector no encuentra SL/TP o produce una geometría fuera del RR técnico. El Execution Desk puede buscar combinaciones alternativas usando únicamente estructura/valor/liquidez/reacción observados.
5. **Sin geometría inventada**: TP no se fabrica desde ATR/RR; SL usa ATR sólo como buffer detrás de una invalidación observada. La dirección debe existir antes.
6. **Gates intactos**: recuperación exige geometry >=62, Entry >=55, SL >=60, TP >=60, mismo RR floor/ceiling, timing gate existente, setup guard existente y hard guard SL/reacción.
7. **Funnel ampliado**: diagnóstico distingue THESIS, CANDIDATE, DIRECTION_CONFIRMATION, ENTRY, SL, TP, RR, SAFETY, OPPORTUNITY_RECOVERY, PUBLICATION y EXECUTABLE; reporta intentos/éxitos de recuperación.

### Instalación
Arrastrar/reemplazar juntos:
- `app.py`
- `execution_specialist_committees.py`
- `preliminary_backtest_prior.py` (sin cambios respecto de 17.5.8; incluido para árbol autocontenido)
- `worker_orchestration.py` (nuevo)

No requiere SQL nuevo ni dependencia pip nueva.

### QA
`qa_commit17_5_9_worker_orchestration.py`: 26/26 PASS. Incluye compilación, contratos no-voting, preservación de priors 17.5.8, recuperación estructural, no fabricación de geometría y verificación de gates existentes.

### Importante
Este commit no garantiza rentabilidad ni garantiza que aparezca una señal. Su objetivo es que una oportunidad con tesis válida no se pierda por una segunda votación redundante o por abandonar tras el primer intento de geometría. Si no existe solución que pase los mismos filtros técnicos y Safety, debe continuar sin publicarse.
