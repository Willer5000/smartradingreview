# Auditoría general — SmartradingReview 17.5.3 → 17.5.4

## Dictamen

Hay mecanismos existentes para acumulación/rotación Spot y diferenciación de
Futuros/Multi-Activo. El problema verificado en esta revisión no exige rebajar
familias ni Safety: hay incoherencias de datos, puntuación y selección en el
recorrido de ejecución. Se corrigen en 17.5.4. El efecto sobre rentabilidad
permanece pendiente de medición comparable.

Base local revisada: `46217b9`, 17.5.3. El usuario confirmó que había desplegado
17.5.3; no se inspeccionó el servidor desplegado ni una cuenta de trading.
El prompt maestro adjunto se utilizó como contexto histórico y de continuidad.
La solicitud actual autorizó una auditoría más amplia que el parche de Structure.

## Revisión por perspectiva

| Perspectiva | Evidencia del código | Acción de este commit |
| --- | --- | --- |
| Spot/acumulación | Strategy Bank incluye acumulación en suelo, reclaim de valor, pullback, distribución en techo y rotación BTC/PAXG. Guardian usa los tres pares y contexto multitemporal. | Conservar esas estrategias; corregir refinamiento y pasarle el contexto observado. Probar dirección del ratio. |
| Futuros/ejecución | La señal precede a geometría, y después actúan Entry Reaction, timing, Safety y publicación. | Evitar copiar timing de otro precio; buscar geometrías admisibles y conservar la base ante incertidumbre. |
| Multi-Activo | Siete contratos, TF 1h/4h/1D y perfiles por clase, macro y sesión. | Mantener esos perfiles y aprovechar el contexto ya calculado; probar enrutamiento como Multi-Activo. |
| Riesgo y objetivos | SL por invalidación; TP estructural; R/R y límites de refinamiento preexistentes. | Retirar FVG mitigado como ancla SL y OB con invalidación observable; sin targets inventados por ATR/RR. |
| Datos/causalidad | Preparación canónica de velas cerradas y reparación Structure estricta 17.5.3. | Corregir ruta MTF ligera que eludía esa preparación. Mantener Structure intacta. |
| Medición | Research histórico se declara experimental; costes realizados no están disponibles en este entorno. | No convertir QA ni puntuaciones de geometría en WR/PnL de producción. |

## Hallazgos reproducidos y reparados

### A. Comparador base no comparable — prioridad alta

Las filas base del comité utilizaban `type='baseline'`, pero los especialistas
consumen `family`. Además se creaba un objeto separado que volvía a contar el
candidato base existente como evidencia vecina. La misma geometría recibía
puntuaciones distintas según se evaluara como referencia o candidata.

Reproducción sin estructura adicional: Entry 100, SL 98, TP 104, precio 101,
ATR 2. En 17.5.3: candidata 71.55, base 73.21, diferencia -1.66. En 17.5.4:
ambas 71.55, diferencia 0. También se prueba para ambos sentidos y tres mercados.

Se reutiliza el mismo objeto/familia/confluencias, con el mismo redondeo.
No se ajustaron pesos para mejorar resultados históricos.

### B. Se elegía primero una alternativa que podía ser inadmisible — prioridad alta

El comité devolvía su ganador sin conocer los límites adicionales del caller.
Si ese ganador violaba banda de R/R, desplazamiento o riesgo, el caller conservaba
la base aunque existiese otra alternativa admisible. Ahora el mismo predicado
del caller filtra las combinaciones durante la búsqueda y comprueba el ganador
de nuevo. Si no queda una mejora, se conserva la base.

La búsqueda sigue acotada. No se afirma que encuentre un óptimo global entre
todos los precios posibles. El test elimina al ganador original y comprueba
que se devuelve la mejor alternativa restante dentro del conjunto explorado.

### C. Distancia y timing heredados de una Entry diferente — prioridad alta

Después de mover Entry, las salidas conservaban la distancia anterior. Para
comparar el gate se copiaba además `DEEP_PULLBACK_LIMIT` a la nueva entrada.
Una propuesta cercana al mercado podía heredar indebidamente el tratamiento
de límite profundo. Excepciones durante esa comparación se aceptaban como si
el timing estuviese preservado.

Ahora los metadatos se calculan desde el precio propuesto, se exige la misma
clase de timing y se conserva la frontera de confirmación inferior de 0.60 ATR.
Los errores/diagnósticos incompletos impiden sustituir la base. Los scores legacy
que consume Safety conservan su escala; no se trasladan los scores de comité
como probabilidades ni nuevas puntuaciones oficiales de Safety.

### D. Anclas de ejecución ya invalidadas — prioridad alta

El selector avanzado de SL aceptaba FVG incluso con `filled=True`. Los OB se
podían reutilizar después de que cierres posteriores atravesaran su extremo
de invalidación. Se filtran en la vista privada del comité.

Un OB histórico sin índice y sin marca explícita de invalidación se mantiene
por compatibilidad: falta evidencia para reconstruir su ciclo. Los selectores
base y las colecciones originales no se reescriben. Esto no equivale a certificar
la vigencia de todas las zonas antiguas del sistema.

### E. Contexto calculado pero desconectado — prioridad alta

`analyze_full_market()` construye volumen, macro, horas, sentimiento y régimen
en `capas`. El refinador buscaba esos objetos dentro de Structure y recurría a
defaults o aproximaciones. Se añade un argumento opcional con las capas ya
calculadas; los callers antiguos mantienen compatibilidad.

Ahora los especialistas existentes pueden usar los datos observados. No hay
nuevas descargas ni un calendario convertido automáticamente en señal. Los
perfiles de activos y volatilidad continúan siendo los existentes.

### F. MTF ligero podía etiquetar datos no cerrados — prioridad alta

La ruta mínima usaba el proveedor de velas cerradas para Multi-Activo, pero
para crypto Futures leía directamente `get_kucoin_data()`, que también incluye
la vela en formación. En Spot, una excepción de `prepare_spot_frame()` se
ignoraba. Ambos caminos podían terminar con `source_candle_closed=True`.

Todos los derivados pasan ahora por su preparación canónica. Spot devuelve
contexto no disponible si la validación falla. También se vuelve a comprobar
el mínimo de 80 velas después del filtrado. Las políticas MTF no cambian; la
disponibilidad de candidatos sí puede variar al eliminar confirmaciones inválidas.

Esto concuerda con la necesidad de validar datos de mercado: KuCoin documenta
que sus series de velas pueden ser incompletas y omitir intervalos sin ticks.
Fuente: [KuCoin — Get Klines](https://www.kucoin.com/en-au/docs-new/rest/futures-trading/market-data/get-klines).

## Ejemplo de ejecución comprobado

Fixture controlada, no operación histórica: base LONG Entry 100, SL 98, TP 104,
precio 102 y ATR 2; soporte/POC 99.4, invalidación 97.7 y resistencia 104.2.
Con los comités reales y el caller productivo, el refinador puede escoger una
Entry más favorable en 99.4, SL detrás de 97.7 y captura al llegar a la resistencia.
En la prueba Futures, la mejora heurística fue +3.10 puntos; se verificó que
el refinamiento también funciona en Spot y Multi-Activo. No es +3.10% de PnL.

La mayor distancia de algunos SL puede reducir exposición al ruido pero aumenta
riesgo por unidad si no se ajusta tamaño/leverage. El comité conserva el límite
de distancia respecto a la base y la política posterior de riesgo existente.
No se garantiza simultáneamente un stop más estrecho y menos probable de tocar.

## Resultados de QA

| Verificación | Resultado |
| --- | --- |
| Suite nueva + comportamiento Structure 17.5.3 | 46 pruebas aprobadas |
| QA estable 17.5.1, script intacto sobre copia LF | 9/9 grupos aprobados |
| Regresión ampliada sobre base 17.5.3 | 48: 43 aprobadas, 4 fallos, 1 error de entorno |
| Misma regresión sobre 17.5.4 | Los mismos fallos/error; sin regresión adicional detectada |
| Código no autorizado para cambios | Hashes normalizados de 14 módulos; Structure y resto de app.py protegido salvo las ediciones declaradas |

Los cuatro fallos heredados son: un test antiguo de Multi-Activo exige que no
exista ningún archivo SQL en el repositorio; tres tests de Commit 9 esperan la
política de leverage anterior a V6. El error de entorno corresponde a una prueba
de Q6 que importa `requests`, ausente en el intérprete local de auditoría. Una
suite antigua adicional con fixtures de pytest no se ejecutó por ese runner;
no se incluye en las 48. No se declara que toda la suite histórica esté verde.

El QA 17.5.3 original mantiene un hash que fija el resto de app.py a 17.5.2.
Esa comprobación antigua ya no es aplicable al nuevo alcance. Se ejecutan sus
23 pruebas de comportamiento intactas desde la nueva suite, sustituyendo sólo
la comprobación de alcance por la correspondiente a 17.5.4.

## Qué falta para demostrar la mejora económica

No se recibió el historial que originó WR 55% y rentabilidad +5%, ni un período,
capital inicial, tamaños, fills, costes o snapshots históricos del pipeline.
Por ello no se ejecutó ni se presenta un backtest de rentabilidad comparable.
`historical_research.py` reproduce estrategias experimentales con geometría
estandarizada; utilizarlo como sustituto del runtime completo sería engañoso.

Para una comparación válida:

1. Congelar 17.5.3 y 17.5.4 y evaluarlos sobre los mismos datos y reglas de fill,
   separando fechas de desarrollo y período posterior de validación.
2. Mantener Entry/SL/TP, expiración y orden intrabar reales. Los toques ambiguos
   necesitan datos más finos o tratamiento conservador explícito.
3. Medir comisiones, spread, slippage, funding, rechazos y oportunidades no
   ejecutadas. El módulo económico actual contiene un mapa público de funding
   para cinco pares crypto: no inferir cobertura completa de todo Multi-Activo.
4. Reportar por mercado/clase/TF: fills, WR neto, expectativa en R, PF neto,
   drawdown, riesgo monetario, duración, MAE/MFE y tamaño de muestra.
5. En Spot, separar variación de satoshis, oro y valor en USDT. Comparar rotación
   BTC↔PAXG frente a mantener BTC/oro/USDT, después de costes. Un ratio favorable
   no demuestra por sí solo crecimiento en USDT.

La documentación pública distingue históricos de funding por contrato; su
consulta no sustituye comisiones y fills reales de cuenta.
Fuente: [KuCoin — Public Funding History](https://www.kucoin.com/docs-new/rest/futures-trading/funding-fees/get-public-funding-history).

## Prioridades posteriores

Primero observar el embudo real con 17.5.4: contexto cerrado → familias → tesis
→ estrategia → geometría/refinamiento → Safety/publicación → fill → resultado.
Después completar la cobertura económica y el registro de operaciones. Sólo
con esa evidencia justificar nuevos cambios de selección o calibración. No
subir leverage, bajar filtros ni modificar pesos buscando fabricar un WR deseado.
