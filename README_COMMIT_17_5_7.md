# Commit 17.5.7 — Backtest Evidence / Execution Quality Final

Base: **Commit 17.5.6 preparado localmente**. 17.5.7 lo reemplaza; no es necesario desplegar 17.5.6 primero.

## Objetivo

Usar evidencia histórica disponible para mejorar SmartradingReview sin volver a la secuencia de ajustes por intuición que rompió la calidad de señales.

17.5.7 **no intenta fabricar un WR objetivo**. Conserva el motor de ejecución de 17.5.6 y añade únicamente cambios que la evidencia permite defender.

## Resultado del backtest

El informe completo está en `BACKTEST_COMMIT_17_5_7.md`.

Resumen:

- Futures histórico limpio: N=346 resueltas, WR 22.25%, expectancy proxy -0.132R, PF proxy 0.830. Es historial de versiones antiguas, no replay exacto de 17.5.6.
- Spot histórico limpio: N=16, WR 56.25%, expectancy proxy +1.366R, PF proxy 4.121. N insuficiente para declarar rentabilidad robusta.
- Multi-Activo: no existe cohorte productiva histórica suficiente; proxy diario 2022–2026 con Structure+geometría genérica resultó negativo (59 resueltas, WR 16.95%, -0.371R, PF 0.553). Esto confirma que no debe reemplazarse el routing específico por clase de activo con un modelo crypto genérico.
- Forensics de 521 SL Futures: sólo 7.10% recuperaron Entry después del stop y 0.58% llegaron luego al TP. No se justifica ensanchar SL globalmente.
- 1,146 expiradas Futures: progreso medio hacia TP 16.8%; sólo 5.5% alcanzaron 70% del objetivo. No se justifica acortar TP globalmente.
- El challenger histórico `LIQUIDITY_SWEEP_MSS_POI` fue mejor que baseline en 30m/1h/2h, pero no se convierte en una estrategia obligatoria porque no es una cohorte version-matched del motor actual.

## Cambios funcionales

### 1. Leverage V6 permanece intacto

No se modifica `futures_system.py` ni `leverage_policy.py`.

V6 sigue decidiendo el máximo leverage técnicamente permisible según contrato, liquidación, SL, ATR, Safety y economía.

17.5.7 añade un **gate de publicación** posterior:

- x1–x3 Futures/Multi-Activo: `ANALYSIS_ONLY`;
- x4 o más: no se modifica por esta regla;
- Entry, SL, TP, RR y leverage calculado se conservan exactamente;
- nunca se sube x2→x4 para aprobar una señal;
- nunca se mueve el SL para conseguir mayor apalancamiento.

La razón se expone como `LOW_LEVERAGE_PRODUCT_FIT`.

### 2. Cohorte de evidencia de Entry

Se añaden campos públicos/diagnósticos:

- `backtest_evidence_policy_version = 17.5.7_BACKTEST_EVIDENCE_V1`
- `entry_evidence_class`
  - `LIQUIDITY_SWEEP_STRUCTURE_POI`
  - `STRUCTURAL_CONFLUENCE`
  - `BASIC_TECHNICAL_EVIDENCE`
- `entry_evidence_probability_status = DIAGNOSTIC_NOT_CALIBRATED`
- `leverage_product_fit`

La clase de Entry **no es un score de probabilidad ni un nuevo veto**. Su finalidad es permitir que la próxima cohorte sea comparable por versión y demostrar con datos actuales si la ventaja histórica de sweep/liquidez/POI sobrevive.

### 3. Fail-safe en todos los canales derivados

La política se aplica antes de:

- caché oficial Futures;
- lifecycle de cierre de vela;
- caché Multi-Activo;
- listas oficiales Confirmadas/Vigentes;
- Telegram confirmado.

No se añade límite diario de señales Telegram.

## Qué se conserva de 17.5.6

- Structure estricta 17.5.3.
- MTF con velas cerradas.
- contexto real hacia el refinador.
- Entry/SL/TP independientes.
- comparación coherente base/candidata.
- OB/FVG inválidos fuera del selector de SL.
- hard guard `SL_INSIDE_STRONG_REACTION_ZONE`.
- Multi-Activo 1h evaluado con su router 1h.
- endpoint Multi-Activo Active no hardcodeado en cero.
- Signal Funnel cache-only.
- sin cuota nueva de 6 señales/análisis rápidos.
- Telegram sin cap de cantidad.

`execution_specialist_committees.py` se incluye completo, pero es **byte-identical a 17.5.6**. Se incluye para que reemplaces ambos archivos y no vuelvas a un estado híbrido app/comités.

## Qué NO cambia

No cambia:

- Strategy Bank;
- pesos de comités;
- mínimos Entry/SL/TP;
- Safety;
- requisitos de familias;
- thresholds de Structure;
- Guardian;
- leverage V6;
- política de RR;
- Liquidation Map;
- login/permisos;
- esquemas de Supabase.

## Instalación

Desde tu estado actual puedes implementar **17.5.7 directamente**. No implementes primero 17.5.6.

1. Guarda copia de los archivos actuales.
2. Arrastra y reemplaza juntos:
   - `app.py`
   - `execution_specialist_committees.py`
3. Ejecuta:

```bash
python -m py_compile app.py execution_specialist_committees.py
python qa_commit17_5_6_execution_quality_visibility.py
python qa_commit17_5_7_backtest_evidence.py
```

Resultado esperado de la entrega:

- QA 17.5.6: **20/20 OK**.
- QA 17.5.7: **14/14 OK**.

No hay migraciones SQL ni nuevas dependencias.

## Rollback

Restaurar ambos archivos de tu versión anterior y reiniciar Render. No requiere rollback de DB.

## Archivos de investigación incluidos

- `BACKTEST_COMMIT_17_5_7.md`
- `BACKTEST_DATA_SNAPSHOT_20260928.json`
- `BACKTEST_SQL_17_5_7.sql`
- `backtest_commit17_5_7_evidence.py`
- `APP_17_5_6_TO_17_5_7.diff`

El backtest es una herramienta de decisión y auditoría; no se presenta como garantía de rentabilidad.
