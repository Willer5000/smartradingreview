# Validación esperada de Commit 21.3

## Evidencia técnica
- HTML cacheado: debe quedar invalidado.
- JS: `COMMIT21-3-FIX`.
- Visual lane: una sola solicitud por celda/45 s.
- Futures lanes: cooldown tras timeout; sin reset artificial de `previousLoading`.

## Evidencia de calidad
No se considera éxito una mera desaparición del spinner. Éxito de calidad = candidatos evaluados por el núcleo 21.2 con contexto CPQE completo y resultados publicables que respeten Safety/RR/SL/TP.
