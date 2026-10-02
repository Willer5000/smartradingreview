# AUDITORÍA COMMIT 19.2.1 — ROOT CAUSE QUALITY RECOVERY

Fecha: 2026-10-02
Base: Commit 19.2 desplegado
Objetivo: recuperar cobertura/frecuencia útil de Futures y Multi-Activo sin bajar parámetros Premium, y completar Greeks numéricos en todos los activos sin fabricar inventario de dealers.

## 1. Diagnóstico

### 1.1 Futures sí estaba analizando; la publicación seguía perdiendo oportunidades válidas
Commit 19.2 consiguió la primera señal Premium nueva, por lo que la ruta LIVE funciona. Sin embargo, una recuperación estructural de Entry/SL/TP podía superar los controles técnicos y seguir necesitando una autorización histórica `validated_liquidity_route` para sustituir una geometría con conflicto de reacción. Esa autorización tiene sentido para preservar la paridad de un Champion histórico, pero no para una señal nativa creada por Live Quant Synthesis ni para Multi-Activo.

Consecuencia: un SL reparado y reevaluado podía continuar como ANALYSIS_ONLY aunque la nueva geometría fuese técnicamente mejor y ya cumpliera los pisos reales.

### 1.2 Multi-Activo recibía la semántica del mercado demasiado tarde
`MultiAssetAnalysis` heredaba el flujo Futures. El `asset_class`, el contexto macro propio de la clase y el banco de estrategias Multi se incorporaban principalmente en el hook posterior a la decisión. En otras palabras: los nueve especialistas podían razonar sobre CL, SPY, oro o China como si fueran un futuro cripto genérico y recién después se agregaba la especialidad de mercado.

Esto reducía la capacidad de Live Quant Synthesis de reconocer un patrón propio del activo antes de formar la tesis.

### 1.3 El scheduler Multi dependía de la hora del proceso y de caché RAM
Las secciones `confirmadas`, `vigentes` y `activas` de Multi se nutren del análisis profundo guardado en la caché operativa. Si Render recicla el worker (el release usa `--max-requests 120`) esa caché desaparecía. Además, el análisis profundo estaba demasiado asociado a ventanas de cierre y gates del router; un deploy/reinicio fuera de la ventana podía dejar la UI en 0 aunque existiese una última vela cerrada no analizada.

El defecto, por tanto, no era solamente la calidad de la tesis: faltaba garantía de **cobertura de la última vela cerrada**.

### 1.4 Greeks: se confundían métricas que sí pueden modelarse con niveles que exigen OI
En activos sin cadena directa observada el gráfico Black-Scholes ya existía, pero el resumen mostraba muchos N/A. Delta, Gamma, Vega y Theta sí se pueden calcular con precio/volatilidad/tiempo; en cambio Gamma Wall, Call Wall, Put Wall y un Zero-Gamma firmado por inventario requieren cadena/Open Interest y no deben inventarse.

## 2. Solución 19.2.1

### 2.1 Contexto Multi PRE-decision
Se añade `_market_pre_analysis_context()` y `app.py` lo ejecuta antes de `prepare_operational_intelligence` y antes de los nueve especialistas.

Ahora los especialistas reciben previamente:
- `market_segment=MULTIASSET`
- `asset_class`
- nombre humano
- contexto macro de la clase
- banco de estrategias por clase/TF
- sesión relevante

El banco de estrategias aporta contexto, no dirección. Una preferencia de familia sólo aporta un pequeño bonus después de que el patrón sea válido por evidencia propia.

### 2.2 Scheduler por vela cerrada, no por ventana de reloj
El scheduler automático Multi ahora:
- identifica la última vela cerrada por `source_candle_timestamp`;
- deduplica por símbolo/TF/vela;
- hace catch-up aunque el worker haya reiniciado fuera del minuto de cierre;
- prioriza por router score, pero el score no es un gate de elegibilidad;
- 4h: hasta 1 mejor celda por ciclo 4h;
- 1h: hasta 1 mejor celda por ciclo de 4h;
- 1D: conserva el pequeño cupo contextual existente;
- ejecuta máximo un deep job por tick;
- conserva `MULTIASSET_AUTO_DEEP_DAILY_MAX=12` para 1h+4h.

Esto aumenta cobertura útil sin aumentar el techo diario de análisis pesado.

### 2.3 Snapshot local compacto para sobrevivir al reciclado de Gunicorn
La caché Multi conserva un snapshot compacto en `/tmp/smartradingreview_multi_cache_19_2_1.json`:
- máximo 2 MB;
- máximo 24 análisis compactos;
- vida máxima 8h;
- sin Supabase;
- sin red externa.

Las rutas de señales Multi restauran este snapshot antes de leer la caché. El objetivo no es persistencia histórica, sino no perder las últimas decisiones por un recycle del worker.

### 2.4 Recuperación estructural LIVE-first con calidad real
Para Live Quant Synthesis y Multi una geometría reparada puede reemplazar una geometría con conflicto si, y sólo si, la nueva alternativa pasa:
- Geometry Quality >= 68
- Entry Quality >= 65
- SL Quality >= 60
- TP Quality >= 60
- timing real
- setup guard real
- R/R y economía existentes
- `evaluate_sl_reaction_conflict` nuevamente sin colisión
- Safety/publication downstream sin cambios

El requisito histórico `validated_liquidity_route` deja de ser una whitelist para señales nativas. Los Champions exactos conservan su protección/paridad histórica.

Los scores se recalculan y se adjuntan a los precios finalmente seleccionados (`REACTION_RECOVERY_COMMIT19_2_1`), evitando evaluar una geometría nueva con scores viejos.

### 2.5 Greeks numéricos para todo el universo
Para cualquier activo con precio válido y volatilidad disponible (incluidos PAXG-USDT, PAXG-BTC, AVAX, Futures HIGH y Multi):
- Delta teórica: numérica
- Gamma teórica: numérica
- Vega teórica: numérica
- Theta teórica: numérica
- Gamma peak teórico: numérico
- Delta-neutral teórico/modelado: numérico

Para BTC/ETH, cuando la cadena observada está disponible, se conserva la capa observada de opciones.

No se fabrican niveles de dealer que necesitan Open Interest:
- Call Wall por OI
- Put Wall por OI
- Gamma Wall por OI
- GEX firmado observado

En modo teórico la UI los marca explícitamente como `Requiere OI`. Esto evita confundir Black-Scholes con inventario real de market makers.

## 3. Parámetros Premium preservados

No se rebajaron:
- Publication Safety: 75
- Entry Quality (refinement): 65
- Geometry Quality: 68
- SL Quality: 60
- TP refinement quality: 60
- publication TP floor existente: 55
- publication SL floor existente: 60
- política R/R existente por perfil intacta (default/reference 1.8; algunos perfiles heredados tienen floor contextual distinto)
- Leverage V6
- reaction guard
- Alpha Decay 8 LIVE -> Shadow / 8 Shadow -> Retired

Una señal sigue pudiendo no publicarse. El objetivo es eliminar falsos negativos y falta de cobertura, no imponer una cuota de señales.

## 4. Sobre “Señales vigentes = 0”

`Vigentes` no debe forzarse a ser >0. Esa sección contiene señales oficiales previamente confirmadas que aún conservan su ventana técnica. Una nueva señal aparece primero en `Confirmadas`; después sólo puede figurar como vigente mientras siga realmente viva según su ciclo de Entry/validez/Guardian. Convertir una señal a “vigente” sólo para llenar el contador rompería la semántica del sistema.

## 5. QA

- Commit 19.2.1: 49/49 PASS
- Regression Commit 19.2: 28/28 PASS
- Regression Commit 19.1: 13/13 PASS
- Regression 17.5.11R.1: 18/18 PASS
- Python compileall: PASS
- JavaScript `node --check`: PASS
- Commit 19 Champion backtest: PASS

## 6. Backtest y limitación honesta

Los Champions históricos conservan exactamente su evidencia y no se alteró su edge:
- 30m raw replay IS: N=11, +1.702R, E +0.1547R, PF 1.254
- 30m raw replay OOS: N=4, +3.928R, E +0.9820R, PF 4.513
- Total: N=15, +5.630R, E +0.3753R, PF 1.719

Las modificaciones 19.2.1 de scheduler, contexto pre-decision y autoridad de recuperación no pueden presentarse honestamente como un nuevo backtest IS/OOS porque el ZIP Main no contiene snapshots históricos point-in-time completos de los nueve especialistas + Multi + comités para reconstruir esa ruta. Se validan por invariantes/QA y por preservación de los gates Premium. Su efectividad futura debe medirse prospectivamente por ReviewTrader/Alpha Decay.

## 7. Conclusión

19.2.1 corrige tres causas raíz distintas: cobertura profunda Multi, semántica Multi antes del razonamiento y una whitelist histórica impropia después de una reparación de geometría nativa. No baja calidad. Además completa valores de Greeks modelables en todos los activos sin inventar Open Interest o dealer positioning.
