# RECOVERY — COMMIT 24.3

## Base de rollback

Commit base operativo indicado por la especificación:

`1bba17bf51c693d75ef08e96bea6ddfe2452142d`

## Archivos reemplazados/agregados

1. `app.py`
2. `commit24_repair_runtime.py`
3. `commit24_main_entrypoint.py`
4. `render.yaml`
5. `requirements.txt`
6. `test_commit24_3_repair.py`
7. `commit24_3_health.py`
8. `RECOVERY_24_3.md`

## Diff funcional resumido

- **app.py**: la ruta de análisis interactivo reserva el heavy slot de forma no bloqueante. Si el slot está ocupado, usa una cola FIFO acotada a 5 entradas; no crea threads para esperar el lock. Al liberar el slot, el runtime drena los pendientes en el mismo worker que lo liberó.
- **commit24_repair_runtime.py**: añade Q-Cluster Authority, revisión geométrica determinista de Q3/Q6/Q7/Q9, dedupe por `market|symbol|timeframe|direction`, prioridad real sobre trabajos background y reciclaje de último recurso si un holder supera 105 s con UI pendiente.
- **commit24_main_entrypoint.py**: versión de runtime `24.3`.
- **render.yaml**: `PYTHONMALLOC=malloc`, `MALLOC_TRIM_THRESHOLD_=65536`, parámetros del Q-Cluster y cola UI; se mantiene 1 worker / 2 threads.
- **requirements.txt**: `orjson` para serialización compacta del health/diagnóstico. No agrega llamadas de red en runtime.
- **commit24_3_health.py**: `/api/commit24/health` con versión, contrato Q, holder, edad, cola, dedupe, hooks, métricas y RSS peak estimate.
- **test_commit24_3_repair.py**: contrato 24.1 + escenarios 24.3.

## Contrato que NO cambia

- `Q_MIN_SCORE = 75` para autoridad directa.
- `Safety >= 65`.
- Pérdida estimada al SL `<= 8%` del margen.
- ATR stress `> 0` y `<= 25%`.
- `PUBLICATION_GATE` explícito.
- Datos sintéticos rechazados.
- Q10 no obligatorio.
- No nuevas llamadas de red.
- No workers permanentes.

## Q-Cluster 24.3

El cluster NO añade un bono numérico arbitrario. Cuando ninguna Q directa cruza 75, solo puede entrar a revisión si:

- promedio de las 3 Q superiores `>= 72`;
- al menos 2 Q `>= 70`;
- desviación estándar poblacional entre las Q `>= 5`.

En revisión se utilizan las Q directas que el motor ya calcula sobre la misma geometría para `Q3`, `Q6`, `Q7` y `Q9`. La puntuación geométrica puede reemplazar la puntuación paralela únicamente cuando es mayor. Si alguna de esas Q cruza `75`, el candidato puede promocionar, pero solo si todas las guardas universales continúan pasando.

La condición de desviación estándar se usa para la **vía cluster**. Una Q directa `>=75` conserva la regla vigente aunque el conjunto sea muy correlacionado.

## Dedupe

La clave final es:

`market|symbol|timeframe|direction`

Esto preserva simultáneamente:

- distintos timeframes;
- distintas direcciones en el mismo timeframe;
- productos distintos (Spot/Futures/Multi-Activo).

Dentro de una misma clave solo queda el candidato con mayor autoridad/Q.

## Rollback

### Opción A — volver exactamente al commit base

```bash
git fetch --all --prune
git reset --hard 1bba17bf51c693d75ef08e96bea6ddfe2452142d
git clean -fd
```

Usa esta opción solo si el working tree no contiene cambios que deban conservarse.

### Opción B — restaurar solo los archivos de Commit 24.3

```bash
git restore --source=1bba17bf51c693d75ef08e96bea6ddfe2452142d -- \
  app.py \
  commit24_repair_runtime.py \
  commit24_main_entrypoint.py \
  render.yaml \
  requirements.txt
```

Y elimina los archivos agregados por 24.3:

```bash
rm -f commit24_3_health.py
rm -f test_commit24_3_repair.py
```

## Verificación post-rollback

```text
GET /api/commit24/health
```

Debe desaparecer la versión `24.3`. El runtime vuelve al contrato anterior (`24.2`) cuando el despliegue base realmente corresponda a ese commit.

## Importante

Este archivo no declara un deploy exitoso. La validación de producción requiere logs reales de Render posteriores al despliegue.
