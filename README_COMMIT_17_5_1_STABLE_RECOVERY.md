# Commit 17.5.1 — Stable Recovery · Multi-Asset + Leverage Preservation

Base exacta: ZIP del usuario `smartradingreview-main commit 17.5.zip`.

## Objetivo

Corregir el problema histórico de Multi-Activo sin reintroducir la arquitectura 17.4 que alteró la frecuencia de señales Futures, y conservar exactamente la política de apalancamiento V6 que existía antes del nuevo Liquidation Heatmap.

## Cambios funcionales

### Multi-Activo
- Reconoce como celdas operativas sólo los 7 contratos Multi-Activo y sus TF reales: `1h`, `4h`, `1D`.
- NO modifica las 150 celdas auditadas Spot/Crypto-Futures.
- MTF propio de Multi-Activo usa sólo TF que existen realmente; no pide `30m`/`2h` inexistentes.
- El router usa velas cerradas con 15 s de gracia de asentamiento.
- Caché separado por TF, evitando que un scan 4h contamine 1h/1D.
- `1D` se rankea con velas 1D y `1h` con velas 1h; ya no heredan el ranking 4h.
- Un fallo transitorio de red/análisis no sobreescribe el último análisis válido ni consume inmediatamente la vela.
- Reintento acotado: hasta 3 intentos en el bucket, sin tormenta de requests.
- Una sola celda profunda por tick del lifecycle existente; no se crea thread adicional.
- No se agrega snapshot Supabase de 17.2: cero escrituras/egress extra por este arreglo.

### Futures/Spot
No se modifica su razonamiento, banco de estrategias, thresholds, Safety, MTF, Publication Gate ni universo.

### Entry / SL / TP
Se conserva íntegramente el endurecimiento de geometría del Commit 17.5 ya implementado en el ZIP base.

### Apalancamiento
`leverage_policy.py` queda byte por byte idéntico al ZIP 17.5 y al Commit 13 pre-heatmap (`718f4af2...`). Git blob SHA: `9e85a7fc8628799e9590a8a1d0be990c8ef30486`.

La política V6:
- separa leverage de tamaño de posición;
- limita por distancia Entry→SL, ATR stress, distancia de liquidación, maintenance margin, fee y máximo del contrato;
- selecciona el mayor entero técnicamente admisible ponderado por calidad;
- reduce la asignación de margen/posición por separado para controlar pérdida;
- no degrada automáticamente a 1x/2x por un presupuesto monetario fijo.

No se fuerza leverage alto si el contrato o la geometría no lo soportan; eso sería aumentar riesgo, no rentabilidad.

## Recursos gratuitos
El arreglo no añade:
- threads/workers;
- llamadas Groq/LLM;
- tablas/migraciones;
- escrituras automáticas Supabase;
- polling frontend.

El router Multi-Activo mantiene 7 requests secuenciales sólo cuando el caché/ventana lo requiere y un máximo de una celda profunda por tick existente.

## QA
- `qa_commit17_5_1_stable_recovery.py`: PASS.
- Python compile: PASS.
- `node --check static/script.js`: PASS.
- `node --check static/futures.js`: PASS.
- Fingerprint de cinco escenarios Crypto antes/después: idéntico.
- `leverage_policy.py`: byte-identical al Commit 13 pre-heatmap.

Los tests legacy que ya fallaban en el ZIP 17.5 original (asserts de textos antiguos y presencia de SQL histórico) siguen fallando exactamente por las mismas causas; no son regresiones de 17.5.1.
