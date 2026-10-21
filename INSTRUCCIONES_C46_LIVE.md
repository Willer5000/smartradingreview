# SmartTradingReview C46 — extensión LIVE ADITIVA, rentabilidad NO validada

**Fecha de revisión:** 21 octubre 2026  
**Base exacta:** `Main de smartradingreview Funcional con señales bajo problema de ram ya mucho mejor y con visibilizacion de graficos y recomendaciones.zip`  
**Objetivo:** añadir candidatos de reversión LONG y SHORT a Futures y Multi-Activo, conservando los existentes.

## ADVERTENCIA ESTADÍSTICA: ES EXPERIMENTAL

Los resultados adjuntos NO demuestran rentabilidad IS/OOS del nuevo C46, ni siquiera de su aproximación. El archivo `AUDITORIA_C46_OOS.csv` resume:

- Corrida inicial: 35 preseleccionadas; **0** estrategias con >=30 operaciones OOS, esperanza positiva y PF>=1.3.
- Laboratorio: 148 preseleccionadas; **0** cumplen los tres criterios.
- Combinaciones exhaustivas: 156 preseleccionadas; **0** cumplen los tres criterios.

Existen algunos valores OOS positivos, pero muchos corresponden a 2–10 operaciones y son especialmente susceptibles a suerte y selección múltiple. Los tres experimentos no son independientes, por lo que no deben sumarse sus operaciones ni declararse un resultado positivo. Las entradas y comités en el laboratorio son proxies, no la ejecución exacta del servidor.

Este ZIP está técnicamente preparado para LIVE por solicitud explícita del usuario, **no es una estrategia rentable comprobada**. Desplegarlo implica aceptar un riesgo económico adicional. No puede garantizarse invariancia de calidad, frecuencia, notificaciones o RAM en producción sin prueba real en Render.

## Alcance preciso

- Extiende Futures (30m/1h/2h/4h) y Multi-Activo (1h/4h) con hipótesis de reversión: sweep de mínimo + divergencia RSI + cambio estructural + volumen para LONG, y su imagen para SHORT.
- Actúa únicamente DESPUÉS del motor original cuando este no publicó una señal. No modifica ninguna señal original elegible.
- Nunca sustituye una señal previamente publicada que siga vigente en esa combinación de activo y temporalidad.
- Invoca **el motor original de niveles**, apalancamiento y autoridad de publicación sin modificar sus archivos. Aumenta exigencia de safety de ejecución a 75 para estas oportunidades; no reduce filtros originales.
- Exige Entry en zona de reacción genuina y en el sentido de LIMIT (retroceso LONG/subida SHORT), SL más allá del barrido, TP original, RR al menos 1.8 y coste estimado favorable.
- Utiliza como máximo 130 velas cerradas ya cargadas. Multi-Activo lee caché técnica ya existente sin descargas externas adicionales; si no coincide la misma vela cerrada, se abstiene.
- No crea workers, threads, llamadas LLM ni cron; no toca Guardian, las rutas de guardado, Telegram, Discord, CSS, HTML ni JavaScript.
- NO incorpora un contador persistente independiente de ocho pérdidas por familia. Respeta un veto de Shadow/alpha decay registrado por la gobernanza preexistente, si se suministra. No se afirma que esto habilite automáticamente la transición de estas rutas a Shadow tras ocho operaciones.

## ARCHIVOS DE PRODUCCIÓN: exactamente 4

1. `app.py` (reemplazar; contiene solo dos inserciones después de la autoridad original; `DIFF_APP_C46.patch` contiene el diff).
2. `c46_live_reversal.py` (nuevo).
3. `countertrend_reversal_c46.py` (nuevo).
4. `c46_market_cache.py` (nuevo).

`tests/`, `AUDITORIA_C46_OOS.csv`, `DIFF_APP_C46.patch`, `BASE_SHA256.txt` y este README son documentación/QA; no obligatorios en Render.

### Instalación

1. **Respaldar la versión funcional** y comprobar que `app.py` tiene el SHA256 base especificado en `BASE_SHA256.txt`; si difiere, NO sobrescribir: este parche fue ensamblado sobre una versión específica.
2. Agregar y reemplazar SOLAMENTE los cuatro archivos de producción.
3. Hacer **un solo commit** en GitHub: `C46 LIVE additive countertrend — unvalidated OOS`.
4. El despliegue activa C46 con `C46_LIVE_ENABLED=1` (es el predeterminado).  `C46_FEE_SLIPPAGE_FUNDING_PCT=0.16` es un escenario conservador de costes sobre notional; no son comisiones reales verificadas.
5. Después del despliegue comparar las señales originales de la misma vela con el backup, monitorizar coincidencia web/Telegram/Discord, picos de RAM, y el número de detecciones y bloqueos. **No utilizar las señales nuevas como recomendaciones rentables validadas.**
6. Ante cualquier anomalía, configurar `C46_LIVE_ENABLED=0` en Render y reiniciar. Esto deja sin efecto la extensión sin borrar señales guardadas ni modificar la versión anterior. Para rollback de archivos, revertir el commit C46.

### Pruebas locales

En PowerShell, desde la raíz del repositorio con dependencias instaladas: 

```
python -m unittest discover -s tests -p "test_c46_live_additive.py" -v
```

Se ejecutaron **17 pruebas unitarias**, más compilación de los 4 archivos; esto NO demuestra estabilidad de carga multiusuario ni rentabilidad.
