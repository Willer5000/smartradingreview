# COMMIT 18 MAIN — Reason First + Entry Reaction Repair + Multi Display Lane

Base requerida: **Commit 17.5.11R4**.

## Archivos a reemplazar/agregar
1. `app.py` — reemplazar.
2. `static/script.js` — reemplazar.
3. `templates/index.html` — reemplazar.
4. `reason_first_contract_18.py` — nuevo.
5. `qa_commit18_main.py` — QA opcional, no requerido por runtime.

No reemplazar `leverage_policy.py`. Commit 18 deliberadamente no modifica el modelo de apalancamiento.

## Cambios
- Endpoint liviano `GET /api/multiasset/display`: gráfico seleccionado independiente del heavy slot.
- Invariante de identidad: CL 4h no puede conservar BTC 1D como análisis visible.
- Runtime resilience integrado en `script.js`; se elimina un request estático que estaba produciendo 502.
- La lane manual reevalúa `SL_REACTION_CONFLICT`; si el SL está dentro de una zona válida de reacción, intenta una única recuperación estructural sobre la misma tesis.
- Contrato explícito Reason First: roles diferenciados, sin mayoría de traders, una familia correlacionada = una contribución acotada.
- IA Científica = hipótesis Shadow; Macro = contexto; Consejo/Asistente = explicación/interfaz; Greeks teóricos = UI/contexto.
- Leverage = política actual preservada.

## Implementación
Arrastra los archivos completos respetando `static/` y `templates/`, sobrescribe los existentes y crea **un solo commit físico**:

`Commit 18 Main - reason first entry reaction multi display`

Después de desplegar: Ctrl+F5, abrir Multi, seleccionar CL 4h y comprobar que título/gráfico/patrón/operación no muestran BTC 1D ni durante BUSY.
