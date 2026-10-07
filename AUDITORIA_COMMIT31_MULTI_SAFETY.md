# Commit 31 — Auditoría y arquitectura Multi-Safety

## Causa raíz consolidada

Los commits 28–30.1 corrigieron ABI, deployment truth, memoria, contexto ausente, ABSTAIN, régimen e impulso direccional. Sin embargo, la autoridad final seguía mezclando tres capas distintas:

1. un Safety universal ponderado;
2. Q1..Q10 como filtros/diagnósticos;
3. hard guards + ruta estadística.

El Safety legacy volvía a puntuar Entry, SL, TP, RR, estructura, tendencia y TF y luego la autoridad final volvía a comprobar varias de esas mismas variables. Eso generaba doble penalización y falsos negativos.

## Decisión Commit 31

Se eliminan Q1..Q10 como autoridad conceptual de publicación. Se conservan únicamente como telemetría histórica/diagnóstico para no romper aprendizaje previo.

Se crean **8 Safety base**. Una señal usa exactamente uno, elegido antes de conocer el score:

1. DIRECTIONAL_IMPULSE
2. TREND_CONTINUATION
3. TREND_PULLBACK
4. BREAKOUT_EXPANSION
5. LIQUIDITY_REVERSAL
6. RANGE_REVERSION
7. EVENT_SESSION
8. BALANCED_STRUCTURAL

Dirección LONG/SHORT es simétrica. Cripto, índices, energía, metales, China, timeframe, volatilidad y sesión son contexto/modificadores; no crean Safety adicionales.

## Regla anti-overfitting principal

Está prohibido calcular los ocho Safety y elegir el de mayor score. El selector determina primero el arquetipo por setup/regime/estructura y recién después calcula su Safety.

## Qué decide el Safety

El score del Safety NO tiene un threshold universal de publicación. Se usa para ranking, riesgo y leverage.

La aptitud (`ready`) se decide mediante componentes críticos no compensatorios del perfil. Ejemplos:
- Entry mínimo;
- SL mínimo;
- TP acorde al tipo de trade;
- estructura para liquidity/breakout;
- momentum+DMI para impulse;
- timing explícito para event/session.

Evidencia opcional ausente no se convierte en 0 ni en 50: se omite y los pesos disponibles se renormalizan.

## Autoridades separadas

### Safety específico
Pregunta: ¿la geometría y evidencia encajan con ESTE setup?

### Hard Risk universal
Continúan siendo no compensatorios:
- datos reales;
- vela cerrada;
- geometría primaria válida;
- fallback nunca publica;
- pérdida al SL dentro del límite;
- ATR stress dentro del límite;
- contradicciones direccionales explícitas.

### Statistical Edge
Una operación todavía necesita una ruta LIVE validada. Commit31 no convierte AVAX/NEAR/Multi rápido en LIVE sin OOS.

## Qué se elimina como veto

- `Execution Safety >= 75` como regla universal.
- `minimum_execution_safety` como retorno temprano que mata geometría.
- `CONTEXTUAL_Q1_Q9_QUALITY_NOT_READY` como hard blocker.
- errores del motor Q como veto de publicación.

El Safety legacy se conserva para auditoría histórica y comparación, pero no gobierna publicación.

## Cobertura conceptual

Los ocho perfiles cubren la mayoría de patrones operativos sin fragmentar demasiado las muestras:

- tendencia estable;
- continuación;
- retroceso/retest;
- ruptura/expansión/squeeze;
- impulso direccional temprano;
- sweep/MSS/reversal;
- rango/mean reversion;
- sesiones/eventos específicos de multi-activo;
- fallback estructural balanceado para tesis direccionales que no pertenecen limpiamente a una familia.

No se crean perfiles por símbolo ni dirección. Esto limita grados de libertad.

## Limitación estadística importante

No existe una cohorte histórica completa con todos los componentes de los nuevos Safety, por lo que Commit31 NO declara que sus pesos estén “backtesteados”. Los pesos son política de ejecución predefinida, no alpha optimizado. El edge sigue proviniendo de las rutas OOS existentes.

El siguiente aprendizaje correcto es almacenar profile + components + outcome y recalibrar sólo cuando exista muestra prospectiva suficiente.
