# QA Commit 33.4

## Pruebas aprobadas
- `python -m py_compile` sobre app y módulos canónicos: PASS.
- `pytest -q test_commit33_4_core.py`: 9 PASS.
- `pytest -q test_commit33_4_core.py test_commit13_execution_geometry_v2.py test_execution_learning.py`: 23 PASS.

## Qué validan las pruebas 33.4
- runtime sin imports de los cores borrados;
- un único pipeline canónico;
- directional impulse conserva rol contextual;
- OOS no mata al candidato antes de geometría;
- ATR stress ausente no se inventa como cero/veto;
- core technical route exige geometría primaria + Safety;
- fallback geometry nunca publica;
- Multi display no llama al fetch pesado;
- `execution_market_type` se inicializa antes del gate de ejecución;
- bootstrap sin overlays.

## Limitación honesta
Estas pruebas demuestran integridad de software y contratos del pipeline. No demuestran rentabilidad futura ni que `CORE_TECHNICAL_ROUTE` tenga edge OOS. Esa ruta debe acumular outcomes forward antes de ser promovida a ruta estadísticamente validada.
