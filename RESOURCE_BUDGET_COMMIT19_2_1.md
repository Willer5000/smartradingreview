# Resource Budget — Commit 19.2.1

Objetivo operativo: mantenerse dentro de Render 512 MB y no ampliar el consumo de ancho de banda respecto de Commit 19.2.

## RAM

Configuración Render preservada:
- workers: 1
- threads: 2
- `MEMORY_SOFT_LIMIT_MB=220`
- `MEMORY_HARD_LIMIT_MB=300`
- `MEMORY_JOB_START_LIMIT_MB=200`
- `MEMORY_ANALYSIS_CACHE_KEEP=1`
- `FUTURES_DATA_CACHE_MAX_ENTRIES=8`
- `MULTIASSET_DEEP_LIMIT=2`
- `LOW_MEMORY_MODE=1`

El hard guard de aplicación (300 MB) deja 212 MB de margen respecto de la instancia de 512 MB antes de considerar memoria externa al proceso. El snapshot Multi es un archivo compacto en `/tmp`, no un segundo dataset caliente: máximo 2 MB/24 filas/8h.

## Bandwidth / service-initiated

19.2.1 no agrega un nuevo proveedor ni aumenta el fan-out de opciones.

Preserva:
- `MAIN_SUPABASE_DAILY_BUDGET_MB=12`
- Options provider: 12 MB/día
- Options TTL: 7200s
- Options respuesta máxima: 1.5 MB
- Options máximo: 220 contratos
- provider observado de options: BTC/ETH únicamente
- Multi automatic observed KuCoin soft guard: 48 MB/día por defecto
- `MULTIASSET_AUTO_DEEP_DAILY_MAX=12`
- `MULTIASSET_AI_AUTOMATIC_ENABLED=0`

Techo configurado de los tres presupuestos explícitos principales (Multi 48 + Options 12 + Supabase 12) = 72 MB/día, aproximadamente 2.16 GB/30 días si todos alcanzasen su soft/daily cap. Esto deja margen para HTTP responses y otros flujos ya existentes dentro de un objetivo mensual de 5 GB.

Importante: Render contabiliza tráfico total real del servicio, por lo que ningún código puede garantizar el valor del dashboard sin observar el tráfico de usuarios y todos los endpoints. 19.2.1 está diseñado para no aumentar materialmente el presupuesto frente a 19.2 y para que la nueva cobertura Multi reutilice el techo de 12 deep jobs/día en lugar de abrir uno nuevo.

## Por qué el scheduler nuevo no aumenta el techo

Antes el sistema podía perder la ventana de cierre y hacer poca cobertura útil. Ahora cambia **qué vela se analiza**, no cuántos análisis máximos se permiten:
- 4h: máximo práctico 6/día
- 1h: máximo práctico 6/día
- total 1h+4h: `MULTIASSET_AUTO_DEEP_DAILY_MAX=12`
- máximo un análisis pesado por tick
- pacing mínimo por defecto 120s
- backpressure RAM a 200 MB antes de arrancar trabajo pesado
- soft network guard 48 MB/día

## Greeks all-market

Los Greeks teóricos de activos no BTC/ETH se calculan localmente con Black-Scholes usando datos que la UI/motor ya tiene. No se consulta una cadena nueva para cada activo. Esto evita multiplicar el egress por el tamaño del universo.

## Groq

0 llamadas automáticas nuevas. El pre-contexto Multi, scheduler, Greeks teóricos y recovery scoring son determinísticos/locales.
