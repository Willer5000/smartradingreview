# Commit 33.3 — CURRENT CORE REPAIR

**Este paquete reemplaza el Commit33.3 anterior basado en el main antiguo. No usar el ZIP anterior.**

## Instalación

1. Descomprimir.
2. Arrastrar EL CONTENIDO directamente a la raíz del repo.
3. Replace/Overwrite.
4. Un único commit recomendado:

`Commit 33.3 - current core repair preserve execution committees and specialised safety`

5. En Render Settings, si existe un Start Command manual, debe quedar:

`gunicorn app:app --timeout 120 --workers 1 --threads 2 --worker-class gthread --graceful-timeout 15 --max-requests 50 --max-requests-jitter 10`

## Contratos que NO cambian

- Futures mínimo 30m.
- Tempo Futures nativo: CORE1 0.12%/3 velas; CORE2 0.11%/3; MEDIUM 0.08%/2; HIGH 0.05%/1.
- SPOT Market Signal Authority global preservada sin leer portafolio del usuario.
- Entry committee.
- SL committee.
- TP committee y TP realista/probable.
- 8 Safeties especializados.
- OOS/publication.
- Guardian por usuario.

## Verificación post-deploy

Abrir `/api/runtime/version` y comprobar:

- `version = COMMIT33_3_CORE_REPAIR_V1`
- `entrypoint = app:app`
- `runtime_monkeypatch_stack = false`
- `minimum_operational_timeframe = 30m`

Abrir `/health`:

- `runtime_authority = COMMIT33_3_CORE_REPAIR_V1`
- `geometry_abi_ok = true`

En logs NO debe volver a aparecer el TypeError `execution_observations`.

## Rollback

Como este cambio debe hacerse en UN solo commit, el rollback más seguro es **Revert** de ese único commit en GitHub. Eso restaura exactamente el estado pre-33.3, incluyendo el módulo legacy de 742 líneas; es más seguro que un rollback parcial empaquetado.
