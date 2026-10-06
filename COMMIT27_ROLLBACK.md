# ROLLBACK COMMIT 27 -> COMMIT 25

1. Descomprimir `SMARTRADINGREVIEW_COMMIT27_RECOVERY_COMMIT25.zip`.
2. Arrastrar su contenido a la raíz del repositorio y aceptar Replace.
3. Commit/push a `main`.
4. Render volverá a usar el `render.yaml`/`Procfile` de Commit 25.
5. Confirmar en logs el entrypoint anterior.

El recovery contiene copias completas del núcleo modificado, no parches.
