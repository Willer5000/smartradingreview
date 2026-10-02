# Resource Budget — Commit 19.1 Greeks Final

## RAM Render 512 MB

Configuración preservada:
- Gunicorn workers: 1
- threads: 2
- soft limit app: 220 MB
- hard limit app: 300 MB
- job start limit: 200 MB

El hard limit de la aplicación queda 212 MB por debajo del límite de instancia de 512 MB.

### Reducciones específicas de Greeks
- No background worker/thread.
- Sólo dos underlyings con cache de cadena observada: BTC y ETH.
- Las curvas completas se eliminan del contexto caliente de ejecución.
- Medición sintética JSON del QA:
  - contexto observado completo: ~4.59 KiB
  - contexto observado compacto hot-path: ~0.88 KiB
  - superficie teórica: ~4.18 KiB
- El gráfico Plotly se construye en el navegador; no crea figuras Plotly persistentes del lado servidor.

## Bandwidth Render 5 GB/mes

Guard específico de proveedor Greeks:
- OPTIONS_MM_DAILY_PROVIDER_BUDGET_MB=12
- ~360 MiB/30 días como techo contable del nuevo proveedor.
- OPTIONS_MM_MAX_RESPONSE_BYTES=1,572,864 bytes por fetch.
- stream de 64 KiB con aborto antes de exceder el límite.
- TTL 7,200 s.
- sólo BTC/ETH pueden consultar cadena directa.
- resto de activos genera superficie teórica local en navegador y no consulta el proveedor de opciones.
- no polling (`setInterval`) del frontend.

Este techo limita el ancho de banda incremental de la nueva función. El total de Render sigue dependiendo de todo el servicio: respuestas al usuario, feeds existentes, descargas, tráfico, reinicios y otros proveedores. Por eso el cumplimiento mensual absoluto se verifica operativamente en Render; el commit no aumenta los presupuestos existentes y deja amplio margen respecto del techo de 5 GB para la nueva función.

## Supabase / Groq
- No nuevas tablas.
- No nuevas llamadas automáticas a Groq.
- No aumenta MAIN_SUPABASE_DAILY_BUDGET_MB.
- No aumenta MULTIASSET_DEEP_LIMIT.
