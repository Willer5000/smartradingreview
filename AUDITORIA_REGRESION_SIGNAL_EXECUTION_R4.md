# Auditoría de regresión — Signal / Execution

## Síntoma observado

La UI mostraba LONG/SHORT `CONFIRMADA · ESPERANDO EJECUCIÓN` sin permitir guardado. En la práctica, una buena tesis no podía convertirse en una orden pendiente porque Entry/SL/TP seguían funcionando como un gate de publicación indirecto.

## Causa raíz

Durante Commit 17.4 se separaron correctamente `signal_confirmed` y `execution_ready`, pero se introdujo una salida normal `CONFIRMED_PENDING_EXECUTION`. Eso cambió el requerimiento original: Entry/SL/TP dejaron de ser solamente especialistas de precio y pasaron a decidir si la señal podía existir operativamente.

También el `execution_setup_guard` y el anti-FOMO podían degradar una señal confirmada al estado pendiente.

## Corrección R4

- Se restaura el contrato original: confirmación direccional y ejecución son independientes en autoridad, no en entrega.
- Una vez confirmada la señal, Entry/SL/TP deben resolver una geometría completa.
- Se amplía el universo de candidatos sin nueva I/O.
- El R/R participa en reconciliación de geometría, no en borrar la señal.
- Setup guard y anti-FOMO pasan a advisory.
- No se toca el motor que confirma la señal.

## Calidad y overfitting

No se redujeron mínimos de calidad, familias, margen direccional, requisitos HIGH, reglas MTF, Research robusto ni Safety de confirmación. La recuperación de geometría ocurre sólo después de que la tesis ya fue confirmada.

## Resultado esperado

Una señal nueva confirmada debe verse como:

LONG/SHORT + Entry + SL + TP + R/R + leverage

con estado normal de espera de Entry, guardable antes de que el precio toque la entrada.
