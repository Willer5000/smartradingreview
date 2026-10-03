COMMIT 21 — PREMIUM STRATEGY ROUTE ENGINE
==========================================
Objetivo: aumentar la frecuencia de oportunidades que realmente pueden llegar a
Premium sin relajar ningún umbral Premium y sin optimizar parámetros con el
resultado live.

QUE CAMBIA
----------
1) Reemplaza la antigua expansión de geometría por una expansión de RUTAS DE
   ESTRATEGIA basada exclusivamente en el Default Strategy Bank ya existente.
2) Para un LONG/SHORT ya seleccionado, el motor prueba como máximo 2 familias
   alternativas que ya eran elegibles para el mismo market/symbol/TF/action.
3) Cada alternativa se reevalúa con el MISMO contexto de régimen/volatilidad y
   con la misma exigencia de familias funcionales del Strategy Bank.
4) Cada alternativa ejecuta el pipeline real de Entry/SL/TP + Safety + CPQE +
   Publication Gate. Sólo una alternativa que pase el gate existente puede
   reemplazar la baseline.
5) Si ninguna alternativa pasa Premium, se conserva exactamente la baseline.
6) No se crean direcciones nuevas, no se cambia R/R, Safety, SL, ATR stress,
   Alpha Decay ni leverage.
7) Bajo presión de RAM se prueba 1 alternativa o ninguna. Nunca se paralelizan
   rutas.
8) Se conserva íntegramente el arreglo de Saved Signals Multi-Activo de 20.2.

OVERFITTING
----------
- No se ajustan parámetros con outcomes live.
- No se aprende un nuevo threshold desde resultados recientes.
- No se usa PnL live para escoger la ruta en tiempo real.
- Las familias candidatas están congeladas por el Strategy Bank existente.
- El orden de alternativas proviene del ranking ya producido por ese banco.
- La ruta no obtiene autoridad estadística por ser seleccionada; necesita pasar
  el mismo gate de publicación y CPQE.
- Fallback geometry nunca se convierte en Premium.

ROLLBACK
--------
Usar el ZIP COMMIT20_2_RECOVERY incluido por separado.
