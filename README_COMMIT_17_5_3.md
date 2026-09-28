# Commit 17.5.3 — Structure estricta en runtime

Base verificada: `Willer5000/smartradingreview`, commit
`d0a847006120be5bd40ef36d454de43b49da8f0d` (Commit 17.5.2).
Fecha: 2026-09-28.

## Problema y cambio

`analyze_price_structure_layer()` calculaba evidencias estructurales, pero no
devolvía `direction` ni `structure_direction`. El consumidor real
`operational_intelligence.build_independent_thesis()` leía esos campos y asignaba
cero a Structure. HIGH exige cinco familias independientes: con esa omisión sólo
cuatro podían aportar la confirmación necesaria.

Único cambio funcional: dentro de `analyze_price_structure_layer()` en `app.py`.
Se añaden cuatro campos tanto al retorno normal como al retorno por excepción:

| Campo | Contrato |
| --- | --- |
| `direction` | `BULLISH`, `BEARISH` o `NEUTRAL` |
| `structure_direction` | Igual a `direction` |
| `structure_score` | Firmado: ±0.65; hasta ±0.85 con refuerzos; neutral = 0 |
| `structure_reasons` | Lista con tipo de evidencia, índice y nivel, o motivo de neutralidad |

Los campos anteriores y las listas de OB/FVG/sweeps/stop hunts se conservan.

## Evidencia admitida

- **Sweep + rechazo:** parte del detector existente (20 velas, excluyendo las
  cinco inmediatamente anteriores, penetración original del 1%). Además exige
  cuerpo y cierre en la mitad favorable, recuperación por cierre del nivel
  barrido y conservación de ese nivel en todos los cierres posteriores.
- **Stop hunt + recuperación:** parte del detector existente (10 velas,
  penetración original del 0.5%). Exige cuerpo favorable, cierre en la mitad
  favorable, recuperación del nivel y mantenimiento por cierre.
- **BOS por cierre:** cruce inicial de un pivote único de cinco velas por lado,
  confirmado antes de la vela de ruptura. Se considera el último pivote válido
  de cada lado dentro de 60 velas. No sirven una meseta de máximos/mínimos
  iguales, una mecha, un pivote aún no confirmado ni volver a cruzar un nivel
  que ya había sido roto. Todos los cierres posteriores deben mantener la ruptura.

Los eventos primarios sólo son utilizables durante la vela del evento y las dos
siguientes. Si sobreviven evidencias válidas opuestas, Structure queda neutral.
Menos de 21 velas, OHLC no finitos/incoherentes/no positivos o una excepción de
análisis no generan dirección. Se respeta el contrato de velas cerradas que
proveen los callers existentes; no se cambian el fetcher ni la selección de velas.

**OB/FVG sólo refuerzan:** después de un evento primario, cada tipo añade como
máximo 0.10 al valor absoluto del score. Deben coincidir en dirección y tener como
máximo 20 velas; el OB debe conservar su extremo de invalidación por cierre y
el FVG no debe estar completamente mitigado. Ninguna zona crea dirección sola.
**HH/HL y LH/LL por sí solos nunca activan Structure.**

Estas ventanas son reglas conservadoras explícitas de este parche, no parámetros
optimizados por rentabilidad ni una reproducción verificada del replay del chat.

### Compatibilidad con el consumidor

`structure_score` es diagnóstico. El consumidor OI permanece exactamente como
en 17.5.2: toma la dirección y calcula su propio ±0.65/±0.85 según la presencia de
colecciones estructurales. No se cambia su ponderación, su umbral de familia de
0.45 ni su política existente de refuerzo. Aunque haya OB/FVG, una dirección
neutral sigue produciendo cero en el consumidor.

## Alcance preservado

No se modifica ningún código fuera de esa función: umbrales de familias, MTF,
Safety, Publication, Strategy Bank, leverage, comités Entry/SL/TP, Guardian,
login, Liquidation Map, frontend y motores Futures/Multi-Activo quedan fuera
del cambio. HIGH conserva cinco familias y margen 1.45. CORE/Multi-Activo
conservan cuatro familias.

## QA y evidencia

`qa_commit17_5_3_structure_signal_path.py`: **24 pruebas aprobadas**.
Carga por AST los cuerpos reales de la función productiva y sus dependencias
locales, sin iniciar Flask, tareas de fondo, exchanges o bases de datos. Usa
OHLCV sintéticos deterministas; no inyecta dirección ni resultados de detectores
en Structure. Trend/Momentum/Volume/MTF son fixtures controladas para aislar la
reparación, y el consumidor OI/Strategy Bank es el real sin modificaciones.

Cobertura:

- Sweep, stop hunt y BOS, en ambas direcciones.
- Mechas, falta de recuperación, caducidad, invalidación, conflicto y pivotes
  todavía no confirmados; ausencia de nueva activación por recross de BOS.
- HH/HL y LH/LL con pivotes reales, OB aislado y FVG aislado: todos neutrales.
- OB/FVG refuerzan únicamente tras evidencia primaria.
- Retorno neutral por datos insuficientes, OHLC inválidos y excepción.
- Causalidad por prefijos e inmutabilidad del DataFrame de entrada.
- HIGH: cinco símbolos × tres temporalidades × dos direcciones = **30 casos**
  que llegan a `candidate_ready=True`, con cinco familias y margen original.
  Al retirar los cuatro campos nuevos, los mismos casos vuelven a tesis neutral
  con cuatro familias, reproduciendo la omisión de 17.5.2.
- HIGH permanece neutral si falta cualquiera de las otras cuatro familias.
- CORE/Multi-Activo conservan el requisito de cuatro familias; conflicto MTF
  sigue bloqueando el candidato.
- SHA256 del texto normalizado de 13 módulos protegidos y de todo `app.py`
  fuera de la función modificada contra la base 17.5.2.

Validación complementaria realizada al preparar la entrega:

- QA estable 17.5.1: nueve grupos aprobados con su script intacto, en copia LF
  del código. El intento inicial sobre CRLF de Windows fallaba sólo en el hash
  de leverage; el blob Git de leverage es el original exigido por ese QA.
- Siete pruebas existentes de ejecución 17.5 aprobadas.
- Diez fixtures comparadas contra la función original: todos los campos antiguos
  conservan exactamente sus valores; sólo aparecen los cuatro nuevos.
- Compilación de `app.py` completo y revisión de whitespace del diff aprobadas.

Esto prueba el contrato de Structure y la alcanzabilidad de candidatos. No es
un backtest de PnL, ni una prueba de publicación final, ni garantiza frecuencia
de señales, WR 55% o rentabilidad +5%. Los gates posteriores conservan autoridad.
No se presentan como reejecutadas las métricas de backtest de la conversación.

## Instalación

1. Aplicar exclusivamente sobre la base 17.5.2 indicada. Guardar el `app.py`
   previo para rollback.
2. Extraer los cuatro archivos del ZIP en la raíz del proyecto. `app.py` es el
   único archivo funcional a reemplazar; no sustituir otros módulos.
3. Ejecutar con las dependencias normales de la aplicación:

   ```text
   python qa_commit17_5_3_structure_signal_path.py
   ```

   Debe terminar en `Ran 24 tests` y `OK`. El ZIP es un parche: el QA necesita
   los módulos restantes del proyecto 17.5.2, no incluidos deliberadamente.
4. Reiniciar el servicio mediante el procedimiento habitual y observar el
   embudo de candidatos y rechazos. La entrega no realiza despliegue ni push.

Rollback: restaurar únicamente el `app.py` de `d0a8470` y reiniciar el servicio.
No hay migraciones de base de datos, cambios de configuración ni dependencias nuevas.

## Contenido exacto del ZIP

- `app.py`
- `qa_commit17_5_3_structure_signal_path.py`
- `README_COMMIT_17_5_3.md`
- `PROMPT_MACRO_CONTINUIDAD_17_5_3.md`
