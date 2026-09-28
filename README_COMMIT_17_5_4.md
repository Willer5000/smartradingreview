# Commit 17.5.4 — contexto cerrado y refinamiento de ejecución

Base: `46217b9` (Commit 17.5.3), descendiente directo de `d0a8470` (17.5.2).
Repositorio: `https://github.com/Willer5000/smartradingreview.git`.
Fecha: 2026-09-28. Preparado localmente; no desplegado ni enviado a GitHub.

## Resultado

Repara inconsistencias que afectaban a la selección de Entry/SL/TP en Spot,
Futuros y Multi-Activo, y a la validez del contexto MTF ligero. Favorece una
selección técnicamente coherente; no demuestra todavía un aumento de WR o PnL.

1. **Comparación justa con la geometría base.** Se puntúa el mismo candidato,
   con sus mismas familias/confluencias, sin contar su propio duplicado.
   Antes una geometría idéntica obtenía 71.55 frente a 73.21 de referencia
   (mejora ficticia de -1.66). Ahora obtiene 71.55 frente a 71.55: mejora cero.
2. **Búsqueda entre alternativas admisibles.** El comité recibe las restricciones
   del caller y busca dentro de ellas. Ya no descarta todas las alternativas
   por haber elegido primero una que el caller rechaza. Se mantiene la búsqueda
   acotada a siete Entries, ocho SL y doce TP, y se vuelve a comprobar el ganador.
3. **Entry y timing coherentes.** Distancia y modo se derivan del precio propuesto.
   Un límite profundo no puede trasladarse cerca del mercado conservando su
   exención de confirmación. Se preservan clase de timing, frontera de 0.60 ATR
   de Entry Reaction y resultado del gate existente. Error o resultado ausente
   conserva la geometría base; no se interpreta como aprobación.
4. **Zonas válidas.** Un FVG mitigado no se usa como invalidación del SL avanzado.
   Un OB con invalidación explícita o con cierres posteriores atravesando su
   extremo se excluye de la vista privada del comité. No se cambia la evidencia
   original de Structure ni se inventan zonas de polaridad inversa.
5. **Contexto realmente conectado.** El análisis ya calculaba volumen, macro,
   sesión, sentimiento y régimen, pero el refinador los buscaba dentro de
   Structure. Ahora recibe las capas existentes directamente, sin nuevas
   peticiones, votos o reglas de publicación.
6. **MTF con velas cerradas.** El contexto ligero usa el proveedor cerrado para
   todos los derivados. En Spot, si falla la preparación de velas cerradas,
   no analiza el frame bruto ni lo etiqueta como cerrado. No cambia TF,
   alineación, umbrales ni el tratamiento del conflicto MTF.
7. **Valores numéricos inválidos.** Infinito/NaN y dirección inválida no pueden
   producir una geometría avanzada.

## Objetivos por mercado

- **Spot:** se preservan compras en zonas de demanda/valor, ventas en oferta y
  los perfiles distintos BTC-USDT, PAXG-USDT y PAXG-BTC. La rotación relativa del
  Guardian se prueba: comprar PAXG/BTC favorece oro; venderlo favorece BTC.
  La corrección del refinador y del contexto beneficia esas rutas existentes;
  no se introduce un sistema nuevo de rotación ni compras/ventas automáticas.
- **Futuros:** límites coherentes con el timing y el R/R existente, invalidación
  detrás de estructura utilizable y targets estructurales alcanzables según
  las heurísticas existentes. No se sube leverage ni se relaja Safety.
- **Multi-Activo:** conserva su universo y perfiles por índices, energía,
  metales industriales, metales preciosos y China, con contexto observado y
  temporalidades propias. No se convierte cada activo en un perfil crypto genérico.

Acumular más BTC y aumentar simultáneamente el valor en USDT no son métricas
equivalentes. Deben medirse por separado después de costes y frente a mantener
BTC, oro o efectivo. Las puntuaciones internas no son probabilidades calibradas.

## Alcance exacto

Dos archivos funcionales:

- `app.py`: `calculate_entry_levels()`, el paso de `capas` desde su caller y
  `_get_operational_mtf_peer_minimal()`.
- `execution_specialist_committees.py`: comparación base, filtro de candidatos,
  vista de zonas utilizables y validación numérica.

Se conservan Structure 17.5.3, requisitos de familias, política MTF, Safety,
Publication, Strategy Bank, leverage V6, Guardian, login, Liquidation Map,
adaptadores Futures/Multi-Activo y perfiles instrumentales. No hay migraciones,
configuración nueva, llamadas de mercado adicionales ni dependencias nuevas.

Límites originales del refinador: mejora mínima 1.50 puntos, calidad conjunta
62, Entry 55, SL 60, TP 60, desplazamiento de Entry ≤0.85 ATR, riesgo entre
0.82 y 1.18 veces la distancia base y la misma banda de R/R de Safety.
Se añaden comprobaciones de coherencia, sin aflojar estos límites. La distancia
al SL puede aumentar dentro de ese margen; no se promete un SL más estrecho
ni menos pérdidas en cada operación.

## Validación

Ejecutar en la raíz del proyecto completo:

```text
python qa_commit17_5_4_execution_audit.py
```

La suite combina 23 pruebas de esta auditoría con las 23 pruebas de comportamiento
de Structure de 17.5.3: **46 pruebas**. La comprobación de alcance antigua,
que fijaba el resto de app.py a 17.5.2, se sustituye únicamente para esta suite
por hashes de los módulos protegidos y del alcance autorizado actual. El script
anterior se conserva intacto y se incluye en el ZIP como dependencia de QA.

Se prueban el caller productivo y los comités reales sin arrancar Flask o tareas
de fondo. Los selectores anteriores se controlan con fixtures para aislar el
refinamiento; no equivale a un replay integral de producción.

La regresión ampliada ejecutó 48 pruebas sobre 17.5.3 y sobre el candidato:
43 aprobadas, los mismos cuatro fallos heredados y un error de entorno por falta
de `requests` en el intérprete de auditoría. No se alteró leverage ni se borraron
migraciones para hacer pasar esos tests históricos. El QA estable 17.5.1 sí
aprueba sus nueve grupos. El detalle y las limitaciones están en la auditoría.

## Aplicación y reversión

1. Usar el proyecto completo 17.5.3. Conservar copia de sus dos archivos funcionales.
2. Extraer el ZIP en la raíz del proyecto y reemplazar únicamente `app.py` y
   `execution_specialist_committees.py`. Los demás archivos son QA/documentación.
3. Ejecutar la suite anterior con las dependencias normales del proyecto.
4. Reiniciar por el procedimiento habitual, renovando también la caché MTF
   ligera en memoria. Observar candidatos, rechazos y motivos de refinamiento.

Rollback: restaurar los dos archivos funcionales de `46217b9` y reiniciar.
No necesita rollback de base de datos.

El objetivo de superar WR 55% y rentabilidad +5% queda **no demostrado**:
no se aportó historial comparable, snapshots históricos completos ni ejecución
real para medirlo. No se reutilizan resultados del chat anterior como evidencia.
