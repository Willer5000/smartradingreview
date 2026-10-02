# Auditoría Commit 19.1 FINAL — Greeks Execution Context

## Hallazgo previo

El Commit 19.1 anterior ya calculaba/transmitía Market Maker/Greeks, pero los trataba esencialmente como telemetría: no podían refinar Entry, SL ni TP. Además, el gráfico estaba limitado a Futures.

## Corrección

Se habilita una política de autoridad diferenciada:

### Cadena observada directa
`execution_reaction_map_authority = OBSERVED_CONFLUENCE_RANKER_ONLY`

Puede refinar la prioridad de candidatos técnicos ya construidos por los comités. No puede:
- crear dirección;
- fabricar Entry/SL/TP desde cero;
- elevar leverage;
- saltar Safety/R/R;
- sustituir invalidación estructural.

### Superficie teórica
`execution_reaction_map_authority = NO_LIVE_EXECUTION_AUTHORITY`

Se muestra en todos los mercados, pero no altera la operación.

## Entry Committee

Agrega `options_reaction` con peso 0.40. Sólo se calcula para un candidato técnico existente y con cadena observada elegible. `baseline` no puede obtener una entrada por una pared de opciones.

## SL Committee

Agrega `options_collision` con peso 0.45. Un SL muy cercano a Zero-Gamma/Delta-Neutral/Gamma/Call/Put Wall observado es penalizado como posible zona de reacción. El SL sigue necesitando invalidación técnica.

## TP Committee

Agrega `options_barrier` con peso 0.45. Favorece un target técnico antes de la primera barrera observada en la dirección de la operación, siempre sujeto al R/R mínimo y reachability existentes.

## Frontend

La tarjeta Market Maker / Greeks está disponible en:
- Spot
- Futures
- Multi-Activo

Fuente visible:
- `OBSERVED` para cadena real directa disponible;
- `THEORETICAL` para Black-Scholes local sin autoridad productiva.

## Limitación de fuente

El adaptador gratuito incluido usa cadena pública directa sólo para BTC/ETH. No se proyectan niveles de BTC sobre SOL/XRP/ADA ni sobre SPY/CL/GLD. Para esos activos se muestra la matemática teórica del propio activo, no dealer positioning inventado.

## Resultado de QA

34/34 controles específicos de Greeks PASS, incluyendo anti-overfitting, Spot frontend, Futures/Multi, no polling, límite de red, memoria y preservación de Safety/R/R/Leverage.
