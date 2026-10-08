# QA Commit 33.3 — Current Core Repair

Resultado final de la batería local reproducible:

- Python compile: **PASS**.
- Tests de contrato: **12/12 PASS**.
- Temporalidad mínima Futures: **30m**.
- Universo Futures: **15 símbolos / 63 combinaciones / 126 celdas LONG-SHORT**.
- Tempo nativo: CORE1 **0.12% / 3 velas**, CORE2 **0.11% / 3**, MEDIUM **0.08% / 2**, HIGH **0.05% / 1**.
- Entry/SL/TP committees: **no reemplazados por el paquete**.
- `safety_profiles_commit31.py`: **no reemplazado**.
- Guardian: **no reemplazado**.
- EntryPoints 31/32/32.1/32.2: **compatibilidad inerte, sin `install()` ni runtime patches**.
- `premium_path_expansion_20`: **sin autoridad de trading, memoria, Safety ni publicación**; conserva sólo runtime truth, invalidación de identidad de snapshot y visual OHLC-only.
- SPOT Market Signal Authority: **preservada como llamada estática desde el router**, no como WSGI monkeypatch.
- Directional Impulse: MTF contextual con confirmación adicional.
- Sweep Reversal: sweep obligatorio + evidencia independiente.
- Trend Pullback: MTF estricto.
- 15m: **no añadido**.

## Lo que este QA NO demuestra

No demuestra rentabilidad futura ni valida nuevas estrategias. Las seis familias de Research requieren OHLCV histórico real 30m y backtest cronológico IS/OOS con costes antes de cualquier promoción LIVE.

- Research runner 30m de seis familias: **compila y queda sin autoridad LIVE hasta backtest real**.
