"""
saved_signals.py
================
Módulo para gestionar las señales que el usuario guarda manualmente desde el
modal de "Justificación de Señal Anterior" en la página de FUTUROS.

Funcionalidades:
- create: crea una nueva señal guardada con monto/apal/entry/TP/SL del usuario
- list_active: lista señales guardadas activas (para la pestaña)
- update: modifica valores de una señal activa
- close_manual: cierra manualmente con precio actual y calcula PnL
- delete: elimina permanentemente
- evaluate_all: evalúa todas las activas contra el precio actual (llamado por
  learning_worker cada 30 min) para detectar entry_touched, tp_hit, sl_hit

Reglas de negocio:
- Solo se aplica a FUTUROS (action ∈ {'LONG', 'SHORT'})
- Solo cuentan para KPIs las señales cerradas cuyo entry_touched=True
- Rentabilidad usa ROI apalancado real: pnl_pct = (Δprecio/entry) * leverage * direccion
- pnl_usdt = investment_usdt * (pnl_pct / 100)

Requiere: supabase_client.supabase_db habilitado + tabla saved_signals creada.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger('SAVED_SIGNALS')
# ============================================================================
# FASE 7G.2 — VIGENCIA DE SETUPS GUARDADOS
# ============================================================================
#
# Una señal que todavía NO tocó Entry puede esperar como máximo
# 6 velas CERRADAS desde el inicio de seguimiento.
#
# Al tocar Entry deja de aplicarse esta expiración.
# ============================================================================

SAVED_SIGNAL_MAX_WAIT_BARS = 6

def _get_db():
    """Obtiene el cliente Supabase o None si no está disponible."""
    try:
        from supabase_client import supabase_db
        if supabase_db and supabase_db.enabled:
            return supabase_db
        return None
    except Exception as e:
        logger.warning(f"Supabase no disponible: {e}")
        return None


def _calc_pnl(entry: float, current: float, leverage: int, investment: float,
              action: str) -> Dict[str, float]:
    """
    Calcula el PnL apalancado real.
    
    Retorna: {'pct': ROI apalancado en %, 'usdt': ganancia/pérdida en USDT}
    """
    if entry <= 0 or current <= 0:
        return {'pct': 0.0, 'usdt': 0.0}
    
    price_change_pct = ((current - entry) / entry) * 100
    direction = 1 if action == 'LONG' else -1
    leveraged_pct = price_change_pct * leverage * direction
    pnl_usdt = investment * (leveraged_pct / 100.0)
    
    return {
        'pct': round(leveraged_pct, 4),
        'usdt': round(pnl_usdt, 4)
    }
# ============================================================================
# COMMIT 36O.2 — COSTES POR PROCEDENCIA + FUNDING PÚBLICO OBSERVADO
# ============================================================================
#
# PRINCIPIOS:
#
# - NO cambia pnl_pct / pnl_usdt brutos.
# - NO cambia win rate.
# - NO cambia Safety / Entry / SL / TP / leverage.
#
# - Fee + slippage siguen juntos porque el 0.0012 actual es una
#   estimación combinada.
#
#   Separarlos sin evidencia sería inventar.
#
# - Funding se consulta DESPUÉS del cierre.
# - Un fallo de Funding NO puede impedir TP / SL / cierre manual.
# ============================================================================


_SAVED_FUTURES_CONTRACT_SYMBOLS = {
    'BTC-USDT': 'XBTUSDTM',
    'ETH-USDT': 'ETHUSDTM',
    'SOL-USDT': 'SOLUSDTM',
    'XRP-USDT': 'XRPUSDTM',
    'ADA-USDT': 'ADAUSDTM',
}


_KUCOIN_FUNDING_HISTORY_URL = (
    'https://api.kucoin.com/'
    'api/ua/v1/market/funding-rate-history'
)


def _timestamp_to_utc_ms(
    value
) -> Optional[int]:
    """
    Convierte un timestamp de Saved Futures
    a epoch milisegundos UTC.
    """

    if value is None:
        return None

    try:

        import pandas as pd

        ts = pd.Timestamp(
            value
        )

        if ts.tz is None:

            ts = ts.tz_localize(
                'UTC'
            )

        else:

            ts = ts.tz_convert(
                'UTC'
            )

        return int(
            ts.timestamp()
            * 1000
        )

    except Exception:

        return None


def _build_estimated_economics(
    signal: Dict,
    exit_price: float,
    gross_pnl: Dict
) -> Dict:
    """
    COMMIT 36O.2

    Este cálculo ocurre DURANTE el cierre,
    pero NO hace llamadas a Internet.

    Primero persiste:

    - Gross PnL.
    - Fee + slippage estimado.
    - Net provisional SIN funding.
    - Funding = PENDING.

    Funding será completado después por:

        enrich_pending_funding_economics()

    De esta manera un fallo externo jamás puede impedir
    cerrar correctamente una operación.
    """

    try:

        gross_pct = float(
            (
                gross_pnl
                or {}
            ).get(
                'pct',
                0
            )
            or 0
        )

        gross_usdt = float(
            (
                gross_pnl
                or {}
            ).get(
                'usdt',
                0
            )
            or 0
        )

        result = {

            'economics_model_version':
                '36O_V2',

            'gross_pnl_pct':
                round(
                    gross_pct,
                    6
                ),

            'gross_pnl_usdt':
                round(
                    gross_usdt,
                    8
                ),

            'gross_r':
                _calculate_trade_r(
                    signal,
                    exit_price
                ),

            'economics_calculated_at':
                datetime.utcnow()
                .isoformat(),

            # --------------------------------------------------------
            # Todavía FALSE.
            #
            # Fee y slippage siguen siendo una estimación combinada.
            # --------------------------------------------------------

            'economics_cost_components_complete':
                False,

            # --------------------------------------------------------
            # FUNDING
            # --------------------------------------------------------

            'funding_data_source':
                None,

            'funding_calculation_status':
                (
                    'PENDING'
                    if (
                        signal.get(
                            'entry_touched_at'
                        )
                        or signal.get(
                            'entry_at'
                        )
                    )
                    else
                    'NO_ENTRY_TIMESTAMP'
                ),

            'funding_contract_symbol':
                None,

            'funding_settlements_count':
                None,

            'funding_rate_sum':
                None,

            'estimated_funding_cost_usdt':
                None,

            'funding_window_start_at':
                (
                    signal.get(
                        'entry_touched_at'
                    )
                    or signal.get(
                        'entry_at'
                    )
                ),

            'funding_window_end_at':
                None,

            'funding_observed_at':
                None,
        }


        # ============================================================
        # MODELO FEE + SLIPPAGE
        # ============================================================

        source = str(
            signal.get(
                'economics_cost_model_source',
                ''
            )
            or ''
        ).upper()


        rate_raw = signal.get(
            'economics_round_trip_cost_rate'
        )


        # ============================================================
        # LEGACY / COSTE BASE NO VERIFICABLE
        # ============================================================

        if (
            source
            != 'ESTIMATED_CONFIG_COMBINED'
            or rate_raw is None
        ):

            result.update({

                'economics_cost_model_source':
                    (
                        source
                        or 'UNVERIFIED_LEGACY'
                    ),

                'fee_slippage_cost_source':
                    'UNVERIFIED',

                'estimated_fee_slippage_cost_usdt':
                    None,

                'estimated_total_cost_usdt':
                    None,

                'estimated_net_pnl_pct':
                    None,

                'estimated_net_pnl_usdt':
                    None,

                'estimated_net_r':
                    None,

                # Sin coste base verificable no calculamos
                # un "neto completo".
                'funding_calculation_status':
                    (
                        'NOT_REQUESTED_'
                        'UNVERIFIED_COST_BASE'
                    ),
            })

            return result


        rate = float(
            rate_raw
            or 0
        )


        investment = float(
            signal.get(
                'investment_usdt',
                0
            )
            or 0
        )


        leverage = float(
            signal.get(
                'leverage',
                1
            )
            or 1
        )


        entry = float(
            signal.get(
                'entry',
                0
            )
            or 0
        )


        stop_loss = float(
            signal.get(
                'stop_loss',
                0
            )
            or 0
        )


        if (
            rate < 0
            or investment <= 0
            or leverage <= 0
        ):

            result.update({

                'fee_slippage_cost_source':
                    'INVALID_INPUT',

                'funding_calculation_status':
                    (
                        'NOT_REQUESTED_'
                        'INVALID_INPUT'
                    ),
            })

            return result


        # ============================================================
        # FEE + SLIPPAGE
        # ============================================================
        #
        # Conservamos exactamente la hipótesis que ya usaba 36O.1:
        #
        # notional = margin × leverage
        #
        # estimated cost =
        # notional × round_trip_cost_pct
        #
        # ============================================================

        notional_usdt = (
            investment
            * leverage
        )


        fee_slippage_cost_usdt = (
            notional_usdt
            * rate
        )


        # ============================================================
        # NET PROVISIONAL
        # ============================================================
        #
        # Por ahora sólo descuenta fee + slippage.
        #
        # Funding será agregado DESPUÉS DEL CIERRE.
        # ============================================================

        provisional_total_cost = (
            fee_slippage_cost_usdt
        )


        provisional_net_usdt = (
            gross_usdt
            - provisional_total_cost
        )


        provisional_cost_pct_margin = (
            provisional_total_cost
            / investment
            * 100.0
        )


        provisional_net_pct = (
            gross_pct
            - provisional_cost_pct_margin
        )


        # ============================================================
        # RIESGO ORIGINAL EN USDT
        # ============================================================

        risk_usdt = 0.0


        if (
            entry > 0
            and stop_loss > 0
        ):

            risk_usdt = (
                investment
                * leverage
                * abs(
                    entry
                    - stop_loss
                )
                / entry
            )


        provisional_net_r = None


        if risk_usdt > 0:

            provisional_net_r = (
                provisional_net_usdt
                / risk_usdt
            )


        result.update({

            'economics_cost_model_source':
                (
                    'ESTIMATED_FEE_SLIPPAGE_'
                    'PENDING_FUNDING'
                ),

            'economics_round_trip_cost_rate':
                round(
                    rate,
                    8
                ),

            'fee_slippage_cost_source':
                'ESTIMATED_CONFIG_COMBINED',

            'estimated_fee_slippage_cost_usdt':
                round(
                    fee_slippage_cost_usdt,
                    8
                ),

            # Hasta enriquecer funding conserva el mismo
            # resultado económico que ya producía 36O.1.

            'estimated_total_cost_usdt':
                round(
                    provisional_total_cost,
                    8
                ),

            'estimated_net_pnl_pct':
                round(
                    provisional_net_pct,
                    6
                ),

            'estimated_net_pnl_usdt':
                round(
                    provisional_net_usdt,
                    8
                ),

            'estimated_net_r':
                (
                    round(
                        provisional_net_r,
                        6
                    )
                    if provisional_net_r
                    is not None
                    else None
                ),
        })


        return result


    except Exception as e:

        # ============================================================
        # FAIL OPEN ECONÓMICO
        # ============================================================
        #
        # Un error de métricas económicas JAMÁS debe impedir
        # cerrar TP / SL / manual.
        # ============================================================

        logger.warning(
            "_build_estimated_economics: "
            f"{e}"
        )

        return {}


def _fetch_public_funding_observation(
    signal: Dict
) -> Dict:
    """
    Consulta el historial PÚBLICO de funding de KuCoin.

    IMPORTANTE:

    La TASA es observada del mercado.

    El importe monetario continúa siendo ESTIMADO porque:

    - Saved Futures no confirma fills reales de una cuenta.
    - usamos investment_usdt × leverage como notional aproximado.
    - no conocemos cambios del notional durante la operación.

    Convención:

    estimated_funding_cost_usdt > 0
        = coste.

    estimated_funding_cost_usdt < 0
        = crédito recibido.
    """

    base = {

        'funding_data_source':
            'KUCOIN_PUBLIC_FUNDING_HISTORY',

        'funding_calculation_status':
            'UNAVAILABLE',

        'funding_contract_symbol':
            None,

        'funding_settlements_count':
            None,

        'funding_rate_sum':
            None,

        'estimated_funding_cost_usdt':
            None,

        'funding_window_start_at':
            None,

        'funding_window_end_at':
            None,

        'funding_observed_at':
            datetime.utcnow()
            .isoformat(),
    }


    try:

        symbol = str(
            signal.get(
                'symbol',
                ''
            )
            or ''
        ).upper()


        action = str(
            signal.get(
                'action',
                ''
            )
            or ''
        ).upper()


        contract_symbol = (
            _SAVED_FUTURES_CONTRACT_SYMBOLS
            .get(
                symbol
            )
        )


        base[
            'funding_contract_symbol'
        ] = contract_symbol


        if (
            not contract_symbol
            or action not in (
                'LONG',
                'SHORT'
            )
        ):

            base[
                'funding_calculation_status'
            ] = 'UNSUPPORTED_SIGNAL'

            return base


        # ============================================================
        # VENTANA DE LA POSICIÓN
        # ============================================================

        start_value = (
            signal.get(
                'entry_touched_at'
            )
            or signal.get(
                'entry_at'
            )
        )


        end_value = (
            signal.get(
                'closed_at'
            )
            or signal.get(
                'updated_at'
            )
        )


        start_ms = (
            _timestamp_to_utc_ms(
                start_value
            )
        )


        end_ms = (
            _timestamp_to_utc_ms(
                end_value
            )
        )


        base[
            'funding_window_start_at'
        ] = start_value


        base[
            'funding_window_end_at'
        ] = end_value


        if (
            start_ms is None
            or end_ms is None
            or end_ms <= start_ms
        ):

            base[
                'funding_calculation_status'
            ] = 'INVALID_WINDOW'

            return base


        # ============================================================
        # CONSULTA PÚBLICA
        # ============================================================

        import requests


        response = requests.get(

            _KUCOIN_FUNDING_HISTORY_URL,

            params={

                'symbol':
                    contract_symbol,

                'startAt':
                    start_ms,

                'endAt':
                    end_ms,
            },

            timeout=6
        )


        if response.status_code != 200:

            base[
                'funding_calculation_status'
            ] = (
                'HTTP_'
                f'{response.status_code}'
            )

            return base


        payload = response.json()


        if (
            not isinstance(
                payload,
                dict
            )
            or payload.get(
                'code'
            ) != '200000'
        ):

            base[
                'funding_calculation_status'
            ] = 'API_REJECTED'

            return base


        data = (
            payload.get(
                'data'
            )
            or {}
        )


        if isinstance(
            data,
            dict
        ):

            rows = (
                data.get(
                    'list'
                )
                or []
            )

        elif isinstance(
            data,
            list
        ):

            rows = data

        else:

            rows = []


        # ============================================================
        # FILTRAR SETTLEMENTS REALES DENTRO DE LA POSICIÓN
        # ============================================================

        valid_rates = []


        for item in rows:

            if not isinstance(
                item,
                dict
            ):

                continue


            try:

                rate = float(
                    item.get(
                        'fundingRate'
                    )
                )


                ts_ms = int(
                    item.get(
                        'ts',
                        item.get(
                            'timepoint',
                            0
                        )
                    )
                    or 0
                )


            except (
                TypeError,
                ValueError
            ):

                continue


            if (
                start_ms
                <= ts_ms
                <= end_ms
            ):

                valid_rates.append(
                    rate
                )


        funding_rate_sum = sum(
            valid_rates
        )


        investment = float(
            signal.get(
                'investment_usdt',
                0
            )
            or 0
        )


        leverage = float(
            signal.get(
                'leverage',
                1
            )
            or 1
        )


        if (
            investment <= 0
            or leverage <= 0
        ):

            base.update({

                'funding_calculation_status':
                    'INVALID_POSITION_SIZE',

                'funding_settlements_count':
                    len(
                        valid_rates
                    ),

                'funding_rate_sum':
                    round(
                        funding_rate_sum,
                        10
                    ),
            })

            return base


        notional_usdt = (
            investment
            * leverage
        )


        # ============================================================
        # DIRECCIÓN DEL FUNDING
        # ============================================================
        #
        # Funding positivo:
        #
        # LONG  paga   -> coste positivo
        # SHORT recibe -> coste negativo
        #
        # Funding negativo:
        #
        # LONG  recibe
        # SHORT paga
        # ============================================================

        side_multiplier = (
            1.0
            if action == 'LONG'
            else -1.0
        )


        estimated_funding_cost = (
            notional_usdt
            * funding_rate_sum
            * side_multiplier
        )


        base.update({

            'funding_calculation_status':
                (
                    'OBSERVED_RATES'
                    if valid_rates
                    else
                    'NO_SETTLEMENTS_IN_WINDOW'
                ),

            'funding_settlements_count':
                len(
                    valid_rates
                ),

            'funding_rate_sum':
                round(
                    funding_rate_sum,
                    10
                ),

            'estimated_funding_cost_usdt':
                round(
                    estimated_funding_cost,
                    8
                ),
        })


        return base


    except Exception as e:

        logger.warning(
            "_fetch_public_funding_observation: "
            f"{e}"
        )

        return base


def enrich_pending_funding_economics(
    limit: int = 20
) -> Dict:
    """
    Enriquece operaciones YA CERRADAS cuyo funding quedó PENDING.

    SEGURIDAD:

    - No toca señales abiertas.
    - No cambia status.
    - No cambia PnL bruto.
    - No cambia Entry.
    - No cambia SL.
    - No cambia TP.
    - No cambia leverage.
    - No hace backfill de históricos cuyo funding status sea NULL.
    """

    stats = {

        'pending': 0,
        'enriched': 0,
        'no_settlements': 0,
        'unavailable': 0,
        'errors': 0,
    }


    db = _get_db()


    if db is None:

        return stats


    try:

        # ============================================================
        # SÓLO CERRADAS GENERADAS POR 36O.2
        # ============================================================

        def _op():

            return (

                db.client

                .table(
                    'saved_signals'
                )

                .select(
                    '*'
                )

                .in_(
                    'status',
                    [
                        'tp_hit',
                        'sl_hit',
                        'closed_manual'
                    ]
                )

                .eq(
                    'entry_touched',
                    True
                )

                .eq(
                    'funding_calculation_status',
                    'PENDING'
                )

                .order(
                    'closed_at',
                    desc=False
                )

                .limit(
                    max(
                        1,
                        min(
                            int(
                                limit
                            ),
                            100
                        )
                    )
                )

                .execute()
            )


        response = db._with_retry(
            _op
        )


        signals = (
            response.data

            if (
                response
                and response.data
            )

            else []
        )


        stats[
            'pending'
        ] = len(
            signals
        )


        # ============================================================
        # ENRIQUECER UNA POR UNA
        # ============================================================

        for signal in signals:

            try:

                signal_id = (
                    signal.get(
                        'id'
                    )
                )


                if not signal_id:

                    continue


                funding = (
                    _fetch_public_funding_observation(
                        signal
                    )
                )


                funding_status = str(

                    funding.get(
                        'funding_calculation_status',
                        'UNAVAILABLE'
                    )

                    or 'UNAVAILABLE'

                )


                updates = dict(
                    funding
                )


                # ====================================================
                # COSTE BASE FEE + SLIPPAGE YA CALCULADO AL CIERRE
                # ====================================================

                fee_slippage_raw = (
                    signal.get(
                        'estimated_fee_slippage_cost_usdt'
                    )
                )


                gross_usdt_raw = (
                    signal.get(
                        'gross_pnl_usdt'
                    )
                )


                if gross_usdt_raw is None:

                    gross_usdt_raw = (
                        signal.get(
                            'pnl_usdt'
                        )
                    )


                gross_pct_raw = (
                    signal.get(
                        'gross_pnl_pct'
                    )
                )


                if gross_pct_raw is None:

                    gross_pct_raw = (
                        signal.get(
                            'pnl_pct'
                        )
                    )


                funding_cost_raw = (
                    funding.get(
                        'estimated_funding_cost_usdt'
                    )
                )


                funding_usable = (

                    funding_status
                    in (
                        'OBSERVED_RATES',
                        'NO_SETTLEMENTS_IN_WINDOW'
                    )

                    and funding_cost_raw
                    is not None
                )


                # ====================================================
                # RECALCULAR NET SÓLO SI AMBAS PARTES SON UTILIZABLES
                # ====================================================

                if (
                    fee_slippage_raw is not None
                    and gross_usdt_raw is not None
                    and gross_pct_raw is not None
                    and funding_usable
                ):

                    fee_slippage_cost = float(
                        fee_slippage_raw
                    )


                    funding_cost = float(
                        funding_cost_raw
                    )


                    gross_usdt = float(
                        gross_usdt_raw
                    )


                    gross_pct = float(
                        gross_pct_raw
                    )


                    investment = float(
                        signal.get(
                            'investment_usdt',
                            0
                        )
                        or 0
                    )


                    leverage = float(
                        signal.get(
                            'leverage',
                            1
                        )
                        or 1
                    )


                    entry = float(
                        signal.get(
                            'entry',
                            0
                        )
                        or 0
                    )


                    stop_loss = float(
                        signal.get(
                            'stop_loss',
                            0
                        )
                        or 0
                    )


                    total_cost = (
                        fee_slippage_cost
                        + funding_cost
                    )


                    net_usdt = (
                        gross_usdt
                        - total_cost
                    )


                    net_pct = None


                    if investment > 0:

                        net_pct = (

                            gross_pct

                            - (
                                total_cost
                                / investment
                                * 100.0
                            )
                        )


                    # ================================================
                    # NET R
                    # ================================================

                    risk_usdt = 0.0


                    if (
                        investment > 0
                        and leverage > 0
                        and entry > 0
                        and stop_loss > 0
                    ):

                        risk_usdt = (

                            investment
                            * leverage

                            * abs(
                                entry
                                - stop_loss
                            )

                            / entry
                        )


                    net_r = None


                    if risk_usdt > 0:

                        net_r = (
                            net_usdt
                            / risk_usdt
                        )


                    updates.update({

                        'economics_model_version':
                            '36O_V2',

                        'economics_cost_model_source':
                            (
                                'ESTIMATED_FEE_SLIPPAGE'
                                '+PUBLIC_FUNDING_RATES'
                            ),

                        'estimated_total_cost_usdt':
                            round(
                                total_cost,
                                8
                            ),

                        'estimated_net_pnl_usdt':
                            round(
                                net_usdt,
                                8
                            ),

                        'estimated_net_pnl_pct':
                            (
                                round(
                                    net_pct,
                                    6
                                )

                                if net_pct
                                is not None

                                else None
                            ),

                        'estimated_net_r':
                            (
                                round(
                                    net_r,
                                    6
                                )

                                if net_r
                                is not None

                                else None
                            ),

                        'economics_calculated_at':
                            datetime.utcnow()
                            .isoformat(),
                    })


                updates[
                    'updated_at'
                ] = (
                    datetime.utcnow()
                    .isoformat()
                )


                # ====================================================
                # UPDATE CON CONDICIÓN
                # ====================================================
                #
                # Sólo actualiza si sigue PENDING.
                #
                # Evita que dos ciclos simultáneos pisen el mismo
                # enriquecimiento.
                # ====================================================

                def _update():

                    return (

                        db.client

                        .table(
                            'saved_signals'
                        )

                        .update(
                            updates
                        )

                        .eq(
                            'id',
                            signal_id
                        )

                        .eq(
                            'funding_calculation_status',
                            'PENDING'
                        )

                        .execute()
                    )


                db._with_retry(
                    _update
                )


                if (
                    funding_status
                    == 'OBSERVED_RATES'
                ):

                    stats[
                        'enriched'
                    ] += 1


                elif (
                    funding_status
                    == 'NO_SETTLEMENTS_IN_WINDOW'
                ):

                    stats[
                        'no_settlements'
                    ] += 1


                else:

                    stats[
                        'unavailable'
                    ] += 1


            except Exception as signal_err:

                stats[
                    'errors'
                ] += 1


                logger.warning(

                    "enrich_pending_funding_economics "
                    f"{signal.get('id')}: "
                    f"{signal_err}"

                )


        return stats


    except Exception as e:

        stats[
            'errors'
        ] += 1


        logger.warning(
            "enrich_pending_funding_economics: "
            f"{e}"
        )


        return stats


def _check_entry_touched(entry: float, high: float, low: float,
                          action: str, tolerance_pct: float = 0.15) -> bool:
    """
    Verifica si el precio 'tocó' el entry en el rango [low, high].
    Tolerancia: 0.15% de margen.
    """
    if entry <= 0 or high <= 0 or low <= 0:
        return False
    tol = entry * (tolerance_pct / 100.0)
    return (low - tol) <= entry <= (high + tol)

def _calculate_open_excursions(
    signal: Dict,
    df_after,
    start_ts
) -> Optional[Dict]:
    """
    FASE 7D.2

    Calcula MFE / MAE de una señal guardada que ya tocó Entry.

    IMPORTANTE:
    - No modifica Entry.
    - No modifica SL.
    - No modifica TP.
    - No modifica leverage.
    - No decide cerrar.
    - No hace llamadas de mercado.
    - Reutiliza las velas que evaluate_saved_signals() ya descargó.

    Sólo conserva nuevos extremos.
    """

    try:
        import pandas as pd

        action = str(
            signal.get(
                'action',
                ''
            )
            or ''
        ).upper()

        entry = float(
            signal.get(
                'entry',
                0
            )
            or 0
        )

        sl = float(
            signal.get(
                'stop_loss',
                0
            )
            or 0
        )

        if (
            action not in (
                'LONG',
                'SHORT'
            )
            or entry <= 0
            or sl <= 0
        ):
            return None

        risk_abs = abs(
            entry - sl
        )

        if risk_abs <= 0:
            return None

        # ==============================================================
        # EXTREMOS YA GUARDADOS
        # ==============================================================

        old_mfe = float(
            signal.get(
                'mfe_price',
                0
            )
            or 0
        )

        old_mae = float(
            signal.get(
                'mae_price',
                0
            )
            or 0
        )

        old_candles_mfe = int(
            signal.get(
                'candles_to_mfe',
                0
            )
            or 0
        )

        old_candles_mae = int(
            signal.get(
                'candles_to_mae',
                0
            )
            or 0
        )

        # ==============================================================
        # VALORES INICIALES
        # ==============================================================

        if action == 'LONG':

            mfe_price = (
                max(
                    entry,
                    old_mfe
                )
                if old_mfe > 0
                else entry
            )

            mae_price = (
                min(
                    entry,
                    old_mae
                )
                if old_mae > 0
                else entry
            )

        else:

            mfe_price = (
                min(
                    entry,
                    old_mfe
                )
                if old_mfe > 0
                else entry
            )

            mae_price = (
                max(
                    entry,
                    old_mae
                )
                if old_mae > 0
                else entry
            )

        candles_to_mfe = (
            old_candles_mfe
        )

        candles_to_mae = (
            old_candles_mae
        )

        observed_candles = 0

        # ==============================================================
        # RECORRER VELAS
        # ==============================================================

        for _, row in df_after.iterrows():

            try:
                row_ts = pd.Timestamp(
                    row['time']
                )

                if row_ts.tz is None:
                    row_ts = (
                        row_ts.tz_localize(
                            'UTC'
                        )
                    )
                else:
                    row_ts = (
                        row_ts.tz_convert(
                            'UTC'
                        )
                    )

            except Exception:
                row_ts = None

            # No contar velas anteriores a Entry.
            if (
                start_ts is not None
                and row_ts is not None
                and row_ts < start_ts
            ):
                continue

            try:
                high = float(
                    row['high']
                )

                low = float(
                    row['low']
                )

            except (
                TypeError,
                ValueError,
                KeyError
            ):
                continue

            if (
                high <= 0
                or low <= 0
            ):
                continue

            observed_candles += 1

            # ==========================================================
            # LONG
            # ==========================================================

            if action == 'LONG':

                if high > mfe_price:

                    mfe_price = high

                    candles_to_mfe = (
                        observed_candles
                    )

                if low < mae_price:

                    mae_price = low

                    candles_to_mae = (
                        observed_candles
                    )

            # ==========================================================
            # SHORT
            # ==========================================================

            else:

                if low < mfe_price:

                    mfe_price = low

                    candles_to_mfe = (
                        observed_candles
                    )

                if high > mae_price:

                    mae_price = high

                    candles_to_mae = (
                        observed_candles
                    )

        # ==============================================================
        # CONVERTIR A % Y R
        # ==============================================================

        if action == 'LONG':

            favorable_abs = max(
                0.0,
                mfe_price - entry
            )

            adverse_abs = max(
                0.0,
                entry - mae_price
            )

        else:

            favorable_abs = max(
                0.0,
                entry - mfe_price
            )

            adverse_abs = max(
                0.0,
                mae_price - entry
            )

        mfe_pct = (
            favorable_abs
            / entry
            * 100
        )

        mae_pct = (
            adverse_abs
            / entry
            * 100
        )

        mfe_r = (
            favorable_abs
            / risk_abs
        )

        mae_r = (
            adverse_abs
            / risk_abs
        )

        # ==============================================================
        # ¿REALMENTE CAMBIÓ ALGÚN EXTREMO?
        # ==============================================================

        epsilon = 1e-12

        if action == 'LONG':

            changed = (
                old_mfe <= 0
                or old_mae <= 0
                or mfe_price
                > old_mfe + epsilon
                or mae_price
                < old_mae - epsilon
            )

        else:

            changed = (
                old_mfe <= 0
                or old_mae <= 0
                or mfe_price
                < old_mfe - epsilon
                or mae_price
                > old_mae + epsilon
            )

        return {
            'mfe_price': round(
                float(mfe_price),
                8
            ),

            'mae_price': round(
                float(mae_price),
                8
            ),

            'mfe_pct': round(
                float(mfe_pct),
                4
            ),

            'mae_pct': round(
                float(mae_pct),
                4
            ),

            'mfe_r': round(
                float(mfe_r),
                4
            ),

            'mae_r': round(
                float(mae_r),
                4
            ),

            'candles_to_mfe': int(
                candles_to_mfe
            ),

            'candles_to_mae': int(
                candles_to_mae
            ),

            '_changed': bool(
                changed
            )
        }

    except Exception as e:

        logger.warning(
            f"_calculate_open_excursions: {e}"
        )

        return None

def _calculate_trade_r(
    signal: Dict,
    exit_price: float
) -> float:
    """
    Calcula el resultado de una salida en unidades R.

    R = movimiento realizado / riesgo original.

    LONG:
        R positivo si exit > entry.

    SHORT:
        R positivo si exit < entry.
    """

    try:
        action = str(
            signal.get(
                'action',
                ''
            )
            or ''
        ).upper()

        entry = float(
            signal.get(
                'entry',
                0
            )
            or 0
        )

        sl = float(
            signal.get(
                'stop_loss',
                0
            )
            or 0
        )

        exit_price = float(
            exit_price
            or 0
        )

        if (
            action not in (
                'LONG',
                'SHORT'
            )
            or entry <= 0
            or sl <= 0
            or exit_price <= 0
        ):
            return 0.0

        risk_abs = abs(
            entry - sl
        )

        if risk_abs <= 0:
            return 0.0

        if action == 'LONG':

            realized = (
                exit_price - entry
            )

        else:

            realized = (
                entry - exit_price
            )

        return round(
            realized / risk_abs,
            4
        )

    except Exception as e:

        logger.warning(
            f"_calculate_trade_r: {e}"
        )

        return 0.0


def _build_early_exit_comparison(
    signal: Dict,
    actual_exit_price: float
) -> Dict:
    """
    Compara el resultado real contra la primera salida
    anticipada hipotética registrada por 7D.3.

    NO altera el resultado real.
    """

    try:
        actual_r = _calculate_trade_r(
            signal,
            actual_exit_price
        )

        result = {
            'actual_close_r':
                actual_r
        }

        candidate_at = (
            signal.get(
                'early_exit_candidate_at'
            )
        )

        candidate_price = float(
            signal.get(
                'early_exit_candidate_price',
                0
            )
            or 0
        )

        if (
            not candidate_at
            or candidate_price <= 0
        ):
            return result

        candidate_r_raw = (
            signal.get(
                'early_exit_candidate_r'
            )
        )

        if candidate_r_raw is None:

            candidate_r = (
                _calculate_trade_r(
                    signal,
                    candidate_price
                )
            )

        else:

            candidate_r = float(
                candidate_r_raw
                or 0
            )

        delta_r = (
            candidate_r
            - actual_r
        )

        result.update({
            'early_exit_evaluated':
                True,

            'early_exit_delta_r':
                round(
                    delta_r,
                    4
                ),

            'early_exit_would_help':
                bool(
                    delta_r > 0
                )
        })

        return result

    except Exception as e:

        logger.warning(
            f"_build_early_exit_comparison: {e}"
        )

        return {}


def _observe_early_exit_shadow(
    signal: Dict,
    df_after,
    start_ts,
    excursion: Optional[Dict] = None
) -> Optional[Dict]:
    """
    FASE 7D.3 — SHADOW MODE

    Ejecuta el Futures Position Guardian sólo como observador.

    Si el Guardian dice EXIT:
        guarda esa PRIMERA oportunidad.

    NO:
        - cierra la operación,
        - cambia status,
        - cambia SL,
        - cambia TP,
        - cambia leverage,
        - cambia el Guardian visible.

    Reutiliza las mismas velas ya cargadas.
    """

    try:
        import pandas as pd

        # ==============================================================
        # UNA SOLA OBSERVACIÓN EXIT POR OPERACIÓN
        # ==============================================================

        if signal.get(
            'early_exit_candidate_at'
        ):
            return None

        if str(
            signal.get(
                'status',
                ''
            )
        ).lower() != 'entry_touched':

            return None

        if (
            df_after is None
            or len(df_after) < 8
        ):
            return None

        # ==============================================================
        # FILTRAR DESDE ENTRY TOUCHED
        # ==============================================================

        working = df_after

        if (
            start_ts is not None
            and 'time' in working.columns
        ):

            df_time = pd.to_datetime(
                working['time'],
                utc=True
            )

            working = working[
                df_time >= start_ts
            ]

        if len(working) < 8:
            return None

        # Sólo las últimas 20 velas.
        recent = working.tail(
            20
        )

        current_price = float(
            recent[
                'close'
            ].iloc[-1]
        )

        if current_price <= 0:
            return None

        candles = {
            'close': [
                float(v)
                for v in recent[
                    'close'
                ].tolist()
            ],

            'high': [
                float(v)
                for v in recent[
                    'high'
                ].tolist()
            ],

            'low': [
                float(v)
                for v in recent[
                    'low'
                ].tolist()
            ]
        }

        # ==============================================================
        # REUTILIZAR EL GUARDIAN EXISTENTE
        # ==============================================================

        from portfolio_guardian import (
            portfolio_guardian
        )

        advice = (
            portfolio_guardian
            .evaluate_futures_position(
                signal=signal,
                current_price=current_price,
                candles=candles
            )
        )

        if not isinstance(
            advice,
            dict
        ):
            return None

        if str(
            advice.get(
                'action',
                ''
            )
        ).upper() != 'EXIT':

            return None

        # ==============================================================
        # SNAPSHOT DEL MOMENTO DEL EXIT HIPOTÉTICO
        # ==============================================================

        excursion = (
            excursion
            if isinstance(
                excursion,
                dict
            )
            else {}
        )

        mfe_r = float(
            excursion.get(
                'mfe_r',
                signal.get(
                    'mfe_r',
                    0
                )
            )
            or 0
        )

        mae_r = float(
            excursion.get(
                'mae_r',
                signal.get(
                    'mae_r',
                    0
                )
            )
            or 0
        )

        candidate_r = (
            _calculate_trade_r(
                signal,
                current_price
            )
        )

        now_iso = (
            datetime.utcnow()
            .isoformat()
        )

        return {
            'early_exit_candidate_at':
                now_iso,

            'early_exit_candidate_price':
                round(
                    current_price,
                    8
                ),

            'early_exit_candidate_r':
                candidate_r,

            'early_exit_score':
                round(
                    float(
                        advice.get(
                            'deterioration_score',
                            0
                        )
                        or 0
                    ),
                    2
                ),

            'early_exit_reason':
                str(
                    advice.get(
                        'reason',
                        ''
                    )
                    or ''
                )[:1000],

            'early_exit_mfe_r':
                round(
                    mfe_r,
                    4
                ),

            'early_exit_mae_r':
                round(
                    mae_r,
                    4
                ),

            'early_exit_evaluated':
                False
        }

    except Exception as e:

        logger.warning(
            f"_observe_early_exit_shadow: {e}"
        )

        return None

# ============================================================================
# CRUD
# ============================================================================

def create_saved_signal(data: Dict) -> Optional[Dict]:
    """
    Crea una nueva señal guardada.
    
    data (dict) debe incluir:
      symbol, timeframe, action, entry, stop_loss, take_profit, leverage,
      investment_usdt, confidence (opcional), candle_timestamp (opcional),
      original_* (opcional, snapshot de valores originales)
    
    Retorna: tupla (row_dict|None, error_msg|None)
      - Éxito: (dict con la fila creada + id, None)
      - Fallo: (None, "mensaje explicativo")
    """
    db = _get_db()
    if db is None:
        msg = "Supabase no está configurado o no está conectado"
        logger.warning(f"create_saved_signal: {msg}")
        return None, msg
    
    try:
        # ============ VALIDACIONES ============
        action = str(data.get('action', '')).upper()
        if action not in ('LONG', 'SHORT'):
            msg = f"acción inválida '{action}' (debe ser LONG o SHORT)"
            logger.warning(f"create_saved_signal: {msg}")
            return None, msg
        
        try:
            entry = float(data.get('entry', 0))
            stop_loss = float(data.get('stop_loss', 0))
            take_profit = float(data.get('take_profit', 0))
            leverage = int(data.get('leverage', 1) or 1)
            investment = float(data.get('investment_usdt', 10))
        except (TypeError, ValueError) as e:
            msg = f"campos numéricos inválidos: {e}"
            logger.warning(f"create_saved_signal: {msg}")
            return None, msg
        
        if entry <= 0 or stop_loss <= 0 or take_profit <= 0:
            msg = f"entry/SL/TP deben ser > 0 (entry={entry}, sl={stop_loss}, tp={take_profit})"
            logger.warning(f"create_saved_signal: {msg}")
            return None, msg
        
        symbol = str(data.get('symbol', '')).strip()
        timeframe = str(data.get('timeframe', '')).strip()
        if not symbol or not timeframe:
            msg = "symbol y timeframe son obligatorios"
            logger.warning(f"create_saved_signal: {msg}")
            return None, msg
        
        # ============ CANDLE_TIMESTAMP: parseo tolerante ============
        # El frontend envía candle_timestamp como string ("2026-08-24 12:00:00")
        # o null. Supabase espera TIMESTAMPTZ (ISO 8601). Normalizamos aquí.
        raw_ts = data.get('candle_timestamp')
        candle_ts = None
        if raw_ts:
            try:
                import pandas as pd
                candle_ts = pd.Timestamp(raw_ts).isoformat()
            except Exception as e:
                logger.warning(f"candle_timestamp no parseable ({raw_ts}): {e} - se guarda como null")
                candle_ts = None
        
        # v22.9.4: entry_at (fecha/hora de ingreso editable por el usuario)
        # Si viene, se parsea. Si no, se usa datetime.utcnow() por default.
        raw_entry_at = data.get('entry_at')
        entry_at = None
        if raw_entry_at:
            try:
                import pandas as pd
                entry_at = pd.Timestamp(raw_entry_at).isoformat()
            except Exception as e:
                logger.warning(f"entry_at no parseable ({raw_entry_at}): {e} - se usa now()")
                entry_at = datetime.utcnow().isoformat()
        else:
            entry_at = datetime.utcnow().isoformat()

        # ============================================================
        # COMMIT 36N.1 — ARMAR LIFECYCLE SÓLO PARA SAVED NUEVAS
        # ============================================================
        #
        # No existe DEFAULT en Supabase.
        #
        # Sólo create_saved_signal() asigna este timestamp.
        # Por tanto:
        #
        # - históricos anteriores a 36N -> NULL
        # - señales nuevas -> timestamp
        #
        # Esto evita backfill después de deploy/restart.
        # ============================================================

        lifecycle_armed_at = (
            datetime.utcnow()
            .isoformat()
        )

        # El frontend ya envía already_in_position.
        # Hasta ahora Python ignoraba ese dato.
        already_in_position = (
            data.get(
                'already_in_position'
            )
            is True
        )

        initial_status = (
            'entry_touched'
            if already_in_position
            else 'active'
        )

        payload = {
            'symbol': symbol,
            'timeframe': timeframe,
            'action': action,
            'confidence': float(data.get('confidence', 0) or 0),
            'entry': entry,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'leverage': leverage,
            'investment_usdt': investment,
            'original_confidence': float(data.get('original_confidence', 0) or 0),
            'original_entry': float(data.get('original_entry', 0) or 0) or None,
            'original_stop_loss': float(data.get('original_stop_loss', 0) or 0) or None,
            'original_take_profit': float(data.get('original_take_profit', 0) or 0) or None,
            'original_leverage': int(data.get('original_leverage', 0) or 0) or None,
            'candle_timestamp': candle_ts,
            'entry_at': entry_at,
            'status':
                initial_status,

            'entry_touched':
                already_in_position,

            'entry_touched_at':
                (
                    entry_at
                    if already_in_position
                    else None
                ),

            'entry_touched_price':
                (
                    entry
                    if already_in_position
                    else None
                ),

            'notes':
                str(
                    data.get(
                        'notes',
                        ''
                    )
                    or ''
                )[:500],
            'user_name':
                str(
                    data.get(
                        'user_name',
                        data.get(
                            'user',
                            'Invitado'
                        )
                    )
                 ).strip(),

              # ========================================================
            # COMMIT 36O.1 — SNAPSHOT ECONÓMICO
            # ========================================================
            #
            # Estos campos describen el modelo vigente al guardar.
            #
            # No significan que el coste haya sido observado
            # realmente en el exchange.
            # ========================================================

            'economics_model_version':
                str(
                    data.get(
                        'economics_model_version',
                        '36O_V1'
                    )
                    or '36O_V1'
                )[:40],

            'economics_cost_model_source':
                str(
                    data.get(
                        'economics_cost_model_source',
                        'UNVERIFIED'
                    )
                    or 'UNVERIFIED'
                )[:60],

            'economics_round_trip_cost_rate':
                (
                    float(
                        data.get(
                            'economics_round_trip_cost_rate'
                        )
                    )
                    if data.get(
                        'economics_round_trip_cost_rate'
                    ) is not None
                    else None
                ),

            'economics_cost_components_complete':
                False,
        
            # ========================================================
            # COMMIT 36N — LIFECYCLE TELEGRAM
            # ========================================================

            'telegram_lifecycle_armed_at':
                lifecycle_armed_at,

            # Si el usuario eligió "Guardar en operación",
            # ya sabe que el Entry ocurrió.
            #
            # No necesitamos enviarle inmediatamente un mensaje
            # "ENTRY TOCADO" de algo que él acaba de declarar.
            'telegram_entry_notified_at':
                (
                    lifecycle_armed_at
                    if already_in_position
                    else None
                ),

            'telegram_tp_notified_at':
                None,

            'telegram_sl_notified_at':
                None,

            'telegram_guardian_last_notified_at':
                None,

            'telegram_guardian_last_action':
                None,

            'telegram_guardian_last_bucket':
                None,

            # Commit 36M — procedencia/riesgo del guardado.
            'execution_origin':
                str(
                    data.get(
                        'execution_origin',
                        'SYSTEM_EXECUTABLE'
                    )
                    or 'SYSTEM_EXECUTABLE'
                ).upper(),

            'risk_class':
                str(
                    data.get(
                        'risk_class',
                        'PREMIUM'
                    )
                    or 'PREMIUM'
                ).upper(),

            'system_executable':
                bool(
                    data.get(
                        'system_executable',
                        True
                    )
                ),

            'engine_publication_status':
                str(
                    data.get(
                        'engine_publication_status',
                        ''
                    )
                    or ''
                )[:60]
                or None,

            'execution_safety_at_save':
                (
                    float(
                        data.get(
                            'execution_safety_at_save'
                        )
                    )
                    if data.get(
                        'execution_safety_at_save'
                    ) is not None
                    else None
                ),

            'execution_safety_minimum_at_save':
                (
                    float(
                        data.get(
                            'execution_safety_minimum_at_save'
                        )
                    )
                    if data.get(
                        'execution_safety_minimum_at_save'
                    ) is not None
                    else None
                ),

            'original_risk_reward':
                (
                    float(
                        data.get(
                            'original_risk_reward'
                        )
                    )
                    if data.get(
                        'original_risk_reward'
                    ) is not None
                    else None
                ),

            'source_signal_id':
                str(
                    data.get(
                        'source_signal_id',
                        ''
                    )
                    or ''
                )[:120]
                or None,

            'source_context':
                  str(
                      data.get(
                          'source_context',
                          ''
                      )
                      or ''
                  ).upper()
                  or None,
          
            'manual_override_ack':
                bool(
                    data.get(
                        'manual_override_ack',
                        False
                    )
                ),

            'original_rejection_reason':
                str(
                    data.get(
                        'original_rejection_reason',
                        ''
                    )
                    or ''
                )[:1000]
                or None,

        }
        
        # ============ INSERT ============
        def _op():
            return db.client.table('saved_signals').insert(payload).execute()
        
        try:
            r = db._with_retry(_op)
        except Exception as db_err:
            # Errores comunes de Supabase que capturamos aquí:
            # - Tabla no existe: 'relation "saved_signals" does not exist'
            # - RLS: 'new row violates row-level security policy'
            # - Column desconocida: 'column "X" does not exist'
            err_str = str(db_err)
            if 'does not exist' in err_str and 'saved_signals' in err_str:
                msg = ('La tabla saved_signals no existe en Supabase. '
                       'Aplica el schema schema_saved_signals.sql en el SQL Editor de Supabase.')
            elif 'row-level security' in err_str.lower() or 'rls' in err_str.lower():
                msg = ('La tabla saved_signals tiene Row Level Security activo. '
                       'Deshabilita RLS en Supabase: ALTER TABLE saved_signals DISABLE ROW LEVEL SECURITY;')
            elif 'column' in err_str.lower() and 'does not exist' in err_str.lower():
                msg = f"Columna desconocida en el schema: {err_str[:200]}"
            else:
                msg = f"Error de Supabase: {err_str[:250]}"
            logger.error(f"create_saved_signal insert: {msg}")
            return None, msg
        
        if r and r.data:
            return r.data[0], None
        
        return None, "Supabase no devolvió datos tras el insert (respuesta vacía)"
    except Exception as e:
        msg = f"Excepción interna: {type(e).__name__}: {str(e)[:200]}"
        logger.error(f"create_saved_signal: {msg}")
        import traceback
        traceback.print_exc()
        return None, msg


def list_saved_signals(status_filter: Optional[List[str]] = None,
                        limit: int = 200,
                        user_name: Optional[str] = None) -> List[Dict]:
    """
    Lista señales guardadas.
    
    status_filter: lista de status a incluir. Si None, incluye TODAS excepto
    'deleted'. Ejemplo: ['active', 'entry_touched'] para ver solo abiertas.
    """
    db = _get_db()
    if db is None:
        return []
    
    try:
        def _op():
            q = db.client.table('saved_signals').select('*')
            if user_name:
                q = q.eq('user_name', user_name)
            if status_filter is not None:
                q = q.in_('status', status_filter)
            else:
                q = q.neq('status', 'deleted')
            return q.order('created_at', desc=True).limit(limit).execute()
        r = db._with_retry(_op)
        return r.data if r and r.data else []
    except Exception as e:
        logger.error(f"list_saved_signals: {e}")
        return []


def get_saved_signal(signal_id: str) -> Optional[Dict]:
    """Retorna una señal guardada por id."""
    db = _get_db()
    if db is None:
        return None
    try:
        def _op():
            return (db.client.table('saved_signals')
                    .select('*')
                    .eq('id', signal_id)
                    .limit(1)
                    .execute())
        r = db._with_retry(_op)
        return r.data[0] if r and r.data else None
    except Exception as e:
        logger.error(f"get_saved_signal: {e}")
        return None

# ============================================================================
# COMMIT 36N — ESTADO TELEGRAM PERSISTENTE
# ============================================================================

_TELEGRAM_STATE_FIELDS = {
    'telegram_entry_notified_at',
    'telegram_tp_notified_at',
    'telegram_sl_notified_at',
    'telegram_guardian_last_notified_at',
    'telegram_guardian_last_action',
    'telegram_guardian_last_bucket',
}


def update_saved_signal_telegram_state(
    signal_id: str,
    updates: Dict
) -> Optional[Dict]:
    """
    Actualiza exclusivamente campos de lifecycle Telegram.

    No puede modificar:
    - status
    - Entry
    - SL
    - TP
    - leverage
    - riesgo
    - resultado

    Esto mantiene separado:
    lifecycle de comunicación
    vs.
    lifecycle económico de la operación.
    """

    db = _get_db()

    if db is None:
        return None

    safe_updates = {
        key: value
        for key, value in (
            updates
            or {}
        ).items()
        if key
        in _TELEGRAM_STATE_FIELDS
    }

    if not safe_updates:
        return get_saved_signal(
            signal_id
        )

    safe_updates[
        'updated_at'
    ] = (
        datetime.utcnow()
        .isoformat()
    )

    try:

        def _op():
            return (
                db.client
                .table(
                    'saved_signals'
                )
                .update(
                    safe_updates
                )
                .eq(
                    'id',
                    signal_id
                )
                .execute()
            )

        result = db._with_retry(
            _op
        )

        if (
            result
            and result.data
        ):
            return result.data[0]

        return None

    except Exception as e:

        logger.error(
            "update_saved_signal_telegram_state: "
            f"{e}"
        )

        return None


def update_saved_signal(signal_id: str, updates: Dict) -> Optional[Dict]:
    """
    Modifica campos editables de una señal activa.
    Campos permitidos: entry, stop_loss, take_profit, leverage, investment_usdt, notes.
    NO permite editar señales cerradas.
    """
    db = _get_db()
    if db is None:
        return None
    
    try:
        current = get_saved_signal(signal_id)
        if not current:
            return None
        if current.get('status') not in ('active', 'entry_touched'):
            logger.warning(f"update_saved_signal: no editable en status {current.get('status')}")
            return None
        
        allowed = {}
        for k in ('entry', 'stop_loss', 'take_profit'):
            if k in updates and updates[k] is not None:
                try:
                    v = float(updates[k])
                    if v > 0:
                        allowed[k] = v
                except (TypeError, ValueError):
                    pass
        if 'leverage' in updates and updates['leverage'] is not None:
            try:
                lv = int(updates['leverage'])
                if lv > 0:
                    allowed['leverage'] = lv
            except (TypeError, ValueError):
                pass
        if 'investment_usdt' in updates and updates['investment_usdt'] is not None:
            try:
                inv = float(updates['investment_usdt'])
                if inv > 0:
                    allowed['investment_usdt'] = inv
            except (TypeError, ValueError):
                pass
        if 'notes' in updates:
            allowed['notes'] = str(updates['notes'] or '')[:500]
        
        # v22.9.4: entry_at editable
        if 'entry_at' in updates and updates['entry_at']:
            try:
                import pandas as pd
                allowed['entry_at'] = pd.Timestamp(updates['entry_at']).isoformat()
            except Exception as e:
                logger.warning(f"update entry_at no parseable ({updates['entry_at']}): {e}")
        
        if not allowed:
            return current
        
        allowed['updated_at'] = datetime.utcnow().isoformat()
        
        def _op():
            return (db.client.table('saved_signals')
                    .update(allowed)
                    .eq('id', signal_id)
                    .execute())
        r = db._with_retry(_op)
        return r.data[0] if r and r.data else None
    except Exception as e:
        logger.error(f"update_saved_signal: {e}")
        return None


def close_saved_signal_manual(signal_id: str, current_price: float) -> Optional[Dict]:
    """
    Cierra manualmente una señal activa con el precio actual.
    
    Reglas:
    - Si entry_touched=False → status='closed_manual' pero pnl no cuenta para KPIs.
    - Si entry_touched=True → status='closed_manual' + calcular PnL apalancado.
    """
    db = _get_db()
    if db is None:
        return None
    
    try:
        sig = get_saved_signal(signal_id)
        if not sig:
            return None
        if sig.get('status') not in ('active', 'entry_touched'):
            logger.warning(f"close_saved_signal_manual: ya cerrada ({sig.get('status')})")
            return sig
        
        entry_touched = bool(sig.get('entry_touched'))
        
        if entry_touched:
            pnl = _calc_pnl(
                entry=float(sig['entry']),
                current=float(current_price),
                leverage=int(sig.get('leverage', 1)),
                investment=float(sig.get('investment_usdt', 10)),
                action=sig['action']
            )
        else:
            # No tocó entry → no cuenta para PnL/winrate
            pnl = {
                'pct': 0.0,
                'usdt': 0.0
            }

        # ==============================================================
        # FASE 7D.3
        # ==============================================================
        # Sólo existe R real si la posición llegó a activar Entry.
        # ==============================================================

        early_exit_comparison = (
            _build_early_exit_comparison(
                sig,
                current_price
            )
            if entry_touched
            else {}
        )
        economics_snapshot = (
            _build_estimated_economics(
                sig,
                current_price,
                pnl
            )
            if entry_touched
            else {}
        )
        updates = {
            'status': 'closed_manual',
            'closed_at': datetime.utcnow().isoformat(),
            'closed_price': float(current_price),
            'pnl_pct': pnl['pct'],
            'pnl_usdt': pnl['usdt'],

            # COMMIT 36O.1
            # Economía paralela; NO reemplaza el PnL bruto.
            **economics_snapshot,

            'close_reason': 'manual',

            **early_exit_comparison,

            'updated_at':
                datetime.utcnow()
                .isoformat(),
        }
        
        def _op():
            return (db.client.table('saved_signals')
                    .update(updates)
                    .eq('id', signal_id)
                    .execute())
        r = db._with_retry(_op)
        return r.data[0] if r and r.data else None
    except Exception as e:
        logger.error(f"close_saved_signal_manual: {e}")
        return None


def delete_saved_signal(signal_id: str) -> bool:
    """Elimina permanentemente (soft delete: status='deleted')."""
    db = _get_db()
    if db is None:
        return False
    
    try:
        def _op():
            return (db.client.table('saved_signals')
                    .update({
                        'status': 'deleted',
                        'updated_at': datetime.utcnow().isoformat()
                    })
                    .eq('id', signal_id)
                    .execute())
        db._with_retry(_op)
        return True
    except Exception as e:
        logger.error(f"delete_saved_signal: {e}")
        return False


# ============================================================================
# EVALUACIÓN AUTOMÁTICA (llamado desde learning_worker cada 30 min)
# ============================================================================

def evaluate_saved_signals(price_fetcher) -> Dict:
    """
    Recorre señales activas y verifica:
    - Si el precio tocó entry → marca entry_touched=True + timestamp/precio
    - Si tocó TP → status='tp_hit' + calcular PnL
    - Si tocó SL → status='sl_hit' + calcular PnL
    
    price_fetcher(symbol, timeframe) → DataFrame con velas (time, high, low, close).
    Se usan las velas POSTERIORES a created_at para verificar.
    
    Retorna: stats {'checked', 'entry_touched', 'tp_hit', 'sl_hit', 'errors'}
    """
    db = _get_db()
    if db is None:
        return {
            'checked': 0,
            'entry_touched': 0,
            'tp_hit': 0,
            'sl_hit': 0,
            'mfe_mae_updated': 0,
            'early_exit_observed': 0,
            'expired':0,
            'errors': 0
        }

    stats = {
        'checked': 0,
        'entry_touched': 0,
        'tp_hit': 0,
        'sl_hit': 0,
        'mfe_mae_updated': 0,
        'early_exit_observed': 0,
        'expired':0,
        'errors': 0
    }
    
    try:
        actives = list_saved_signals(status_filter=['active', 'entry_touched'], limit=500)
        
        for sig in actives:
            stats['checked'] += 1
            try:
                symbol = sig.get('symbol')
                tf = sig.get('timeframe')
                action = sig.get('action')
                entry = float(sig.get('entry', 0))
                sl = float(sig.get('stop_loss', 0))
                tp = float(sig.get('take_profit', 0))
                leverage = int(sig.get('leverage', 1))
                investment = float(sig.get('investment_usdt', 10))
                already_touched = bool(sig.get('entry_touched'))
                
                if not symbol or not tf or entry <= 0:
                    continue
                
                # Obtener velas del par/TF
                df = price_fetcher(symbol, tf)
                if df is None or len(df) == 0:
                    continue
                
                # v22.9.4: Filtrar velas POSTERIORES al entry_at (o created_at si no hay entry_at).
                # entry_at es la fecha que el usuario declaró como ingreso teórico;
                # created_at es cuando se registró en el sistema. Priorizamos entry_at.
                import pandas as pd
                ts_source = sig.get('entry_at') or sig.get('created_at')
                start_ts = pd.Timestamp(ts_source)
                if start_ts.tz is None:
                    start_ts = start_ts.tz_localize('UTC')
                else:
                    start_ts = start_ts.tz_convert('UTC')
                df_time = (
                    pd.to_datetime(
                        df['time'],
                        utc=True
                    )
                    if df['time'].dtype
                    != 'datetime64[ns, UTC]'
                    else df['time']
                )

                df_after = (
                    df[
                        df_time > start_ts
                    ]
                )

                if len(df_after) == 0:
                    # No hay velas nuevas aún.
                    continue

                # ============================================================
                # FASE 7G.2 — EXPIRACIÓN ESPERANDO ENTRY
                # ============================================================
                #
                # KuCoin normalmente incluye como última fila
                # la vela que todavía está abierta.
                #
                # Para EXPIRAR sólo contamos velas cerradas.
                #
                # Sin embargo, la vela actual sí podrá tocar Entry
                # más abajo mientras la señal siga vigente.
                # ============================================================

                if not already_touched:

                    completed_after = (
                        df_after.iloc[:-1]
                        if len(df_after) > 1
                        else df_after.iloc[0:0]
                    )

                    if (
                        len(completed_after)
                        >= SAVED_SIGNAL_MAX_WAIT_BARS
                    ):

                        # ----------------------------------------------------
                        # Antes de expirar comprobar que Entry NO haya sido
                        # tocado dentro de las seis velas válidas.
                        # ----------------------------------------------------

                        valid_window = (
                            completed_after.iloc[
                                :SAVED_SIGNAL_MAX_WAIT_BARS
                            ]
                        )

                        entry_touched_in_window = False

                        for _, validity_row in (
                            valid_window.iterrows()
                        ):

                            if _check_entry_touched(
                                entry,
                                float(
                                    validity_row['high']
                                ),
                                float(
                                    validity_row['low']
                                ),
                                action
                            ):

                                entry_touched_in_window = (
                                    True
                                )

                                break

                        # ----------------------------------------------------
                        # 6 velas cerradas y nunca hubo Entry.
                        # ----------------------------------------------------

                        if not entry_touched_in_window:

                            now_iso = (
                                datetime.utcnow()
                                .isoformat()
                            )

                            try:

                                expiry_price = float(
                                    df['close'].iloc[-1]
                                    or 0
                                )

                            except Exception:

                                expiry_price = 0.0

                            db.client.table(
                                'saved_signals'
                            ).update({
                                'status':
                                    'expired',

                                'closed_at':
                                    now_iso,

                                'closed_price':
                                    (
                                        expiry_price
                                        if expiry_price > 0
                                        else None
                                    ),

                                'pnl_pct':
                                    0.0,

                                'pnl_usdt':
                                    0.0,

                                'close_reason':
                                    'expired_no_entry',

                                'updated_at':
                                    now_iso,
                            }).eq(
                                'id',
                                sig['id']
                            ).execute()

                            stats[
                                'expired'
                            ] += 1

                            logger.info(
                                "⌛ Señal expirada sin Entry: "
                                f"{symbol} {tf} {action} "
                                f"después de "
                                f"{SAVED_SIGNAL_MAX_WAIT_BARS} "
                                "velas cerradas."
                            )

                            continue
                
                # ============================================================
                # 1. DETERMINAR DESDE CUÁNDO EXISTE REALMENTE LA POSICIÓN
                # ============================================================

                excursion_start_ts = None

                if already_touched:

                    raw_touch_ts = (
                        sig.get(
                            'entry_touched_at'
                        )
                        or ts_source
                    )

                    try:
                        excursion_start_ts = (
                            pd.Timestamp(
                                raw_touch_ts
                            )
                        )

                        if (
                            excursion_start_ts.tz
                            is None
                        ):
                            excursion_start_ts = (
                                excursion_start_ts
                                .tz_localize(
                                    'UTC'
                                )
                            )
                        else:
                            excursion_start_ts = (
                                excursion_start_ts
                                .tz_convert(
                                    'UTC'
                                )
                            )

                    except Exception:
                        excursion_start_ts = (
                            start_ts
                        )

                # ============================================================
                # 2. VERIFICAR ENTRY
                # ============================================================

                if not already_touched:

                    for _, row in df_after.iterrows():

                        if not _check_entry_touched(
                            entry,
                            float(
                                row['high']
                            ),
                            float(
                                row['low']
                            ),
                            action
                        ):
                            continue

                        # ====================================================
                        # GUARDAR EL TIMESTAMP REAL DE LA VELA
                        # ====================================================

                        try:
                            touch_ts = (
                                pd.Timestamp(
                                    row['time']
                                )
                            )

                            if touch_ts.tz is None:
                                touch_ts = (
                                    touch_ts
                                    .tz_localize(
                                        'UTC'
                                    )
                                )
                            else:
                                touch_ts = (
                                    touch_ts
                                    .tz_convert(
                                        'UTC'
                                    )
                                )

                        except Exception:
                            touch_ts = (
                                pd.Timestamp.now(
                                    tz='UTC'
                                )
                            )

                        touch_iso = (
                            touch_ts.isoformat()
                        )

                        db.client.table(
                            'saved_signals'
                        ).update({
                            'entry_touched':
                                True,

                            'entry_touched_at':
                                touch_iso,

                            'entry_touched_price':
                                entry,

                            'status':
                                'entry_touched',

                            'updated_at':
                                datetime.utcnow()
                                .isoformat(),
                        }).eq(
                            'id',
                            sig['id']
                        ).execute()

                        already_touched = True

                        excursion_start_ts = (
                            touch_ts
                        )

                        # Mantener también el snapshot local
                        # coherente durante esta misma evaluación.
                        sig[
                            'entry_touched'
                        ] = True

                        sig[
                            'entry_touched_at'
                        ] = touch_iso

                        stats[
                            'entry_touched'
                        ] += 1

                        logger.info(
                            f"Entry tocado: "
                            f"{symbol} "
                            f"{tf} "
                            f"{action} "
                            f"@ {entry}"
                        )

                        break

                # ============================================================
                # SI TODAVÍA NO HAY ENTRY, NO EXISTE POSICIÓN
                # ============================================================

                if not already_touched:
                    continue

                if excursion_start_ts is None:
                    excursion_start_ts = (
                        start_ts
                    )

                # ============================================================
                # 3. TP / SL
                # ============================================================
                #
                # IMPORTANTE:
                # este bloque conserva exactamente el orden conservador
                # actual de resolución:
                #
                # LONG  → primero SL, después TP
                # SHORT → primero SL, después TP
                #
                # No cambiamos ninguna decisión.
                # ============================================================

                closed_this_cycle = False

                for _, row in df_after.iterrows():

                    high = float(
                        row['high']
                    )

                    low = float(
                        row['low']
                    )

                    if action == 'LONG':

                        # LONG: SL abajo, TP arriba
                        if low <= sl:

                            pnl = _calc_pnl(
                                entry,
                                sl,
                                leverage,
                                investment,
                                action
                            )

                            db.client.table(
                                'saved_signals'
                            ).update({
                                'status':
                                    'sl_hit',

                                'closed_at':
                                    datetime.utcnow()
                                    .isoformat(),

                                'closed_price':
                                    sl,

                                'pnl_pct':
                                    pnl['pct'],

                                'pnl_usdt':
                                    pnl['usdt'],

                                # COMMIT 36O.1
                                **_build_estimated_economics(
                                    sig,
                                    sl,
                                    pnl
                                ),

                                'close_reason':
                                    'sl_hit',
                                # ======================================
                                # FASE 7D.3
                                # ======================================
                                # Comparar el SL real contra la salida
                                # anticipada hipotética, si existió.
                                # ======================================

                                **_build_early_exit_comparison(
                                    sig,
                                    sl
                                ),

                                'updated_at':
                                    datetime.utcnow()
                                    .isoformat(),
                            }).eq(
                                'id',
                                sig['id']
                            ).execute()

                            stats[
                                'sl_hit'
                            ] += 1

                            closed_this_cycle = (
                                True
                            )

                            logger.info(
                                f"SL golpeado: "
                                f"{symbol} {tf} "
                                f"LONG @ {sl} "
                                f"({pnl['pct']:.2f}%)"
                            )

                            break

                        elif high >= tp:

                            pnl = _calc_pnl(
                                entry,
                                tp,
                                leverage,
                                investment,
                                action
                            )

                            db.client.table(
                                'saved_signals'
                            ).update({
                                'status':
                                    'tp_hit',

                                'closed_at':
                                    datetime.utcnow()
                                    .isoformat(),

                                'closed_price':
                                    tp,

                                'pnl_pct':
                                    pnl['pct'],

                                'pnl_usdt':
                                    pnl['usdt'],

                                # COMMIT 36O.1
                                **_build_estimated_economics(
                                    sig,
                                    tp,
                                    pnl
                                ),

                                'close_reason':
                                    'tp_hit',

                                **_build_early_exit_comparison(
                                    sig,
                                    tp
                                ),

                                'updated_at':
                                    datetime.utcnow()
                                    .isoformat(),
                            }).eq(
                                'id',
                                sig['id']
                            ).execute()

                            stats[
                                'tp_hit'
                            ] += 1

                            closed_this_cycle = (
                                True
                            )

                            logger.info(
                                f"TP golpeado: "
                                f"{symbol} {tf} "
                                f"LONG @ {tp} "
                                f"({pnl['pct']:+.2f}%)"
                            )

                            break

                    else:

                        # SHORT: SL arriba, TP abajo
                        if high >= sl:

                            pnl = _calc_pnl(
                                entry,
                                sl,
                                leverage,
                                investment,
                                action
                            )

                            db.client.table(
                                'saved_signals'
                            ).update({
                                'status':
                                    'sl_hit',

                                'closed_at':
                                    datetime.utcnow()
                                    .isoformat(),

                                'closed_price':
                                    sl,

                                'pnl_pct':
                                    pnl['pct'],

                                'pnl_usdt':
                                    pnl['usdt'],

                                # COMMIT 36O.1
                                **_build_estimated_economics(
                                    sig,
                                    sl,
                                    pnl
                                ),

                                'close_reason':
                                    'sl_hit',

                                **_build_early_exit_comparison(
                                    sig,
                                    sl
                                ),
                              
                                'updated_at':
                                    datetime.utcnow()
                                    .isoformat(),
                            }).eq(
                                'id',
                                sig['id']
                            ).execute()

                            stats[
                                'sl_hit'
                            ] += 1

                            closed_this_cycle = (
                                True
                            )

                            logger.info(
                                f"SL golpeado: "
                                f"{symbol} {tf} "
                                f"SHORT @ {sl} "
                                f"({pnl['pct']:.2f}%)"
                            )

                            break

                        elif low <= tp:

                            pnl = _calc_pnl(
                                entry,
                                tp,
                                leverage,
                                investment,
                                action
                            )

                            db.client.table(
                                'saved_signals'
                            ).update({
                                'status':
                                    'tp_hit',

                                'closed_at':
                                    datetime.utcnow()
                                    .isoformat(),

                                'closed_price':
                                    tp,

                                'pnl_pct':
                                    pnl['pct'],

                                'pnl_usdt':
                                    pnl['usdt'],

                                # COMMIT 36O.1
                                **_build_estimated_economics(
                                    sig,
                                    tp,
                                    pnl
                                ),

                                'close_reason':
                                    'tp_hit',

                                # ======================================
                                # FASE 8.1
                                # ======================================
                                # Mantener simetría con:
                                # LONG SL
                                # LONG TP
                                # SHORT SL
                                #
                                # La salida real SHORT+TP también debe
                                # compararse contra el Early Exit shadow.
                                # ======================================

                                **_build_early_exit_comparison(
                                    sig,
                                    tp
                                ),

                                'updated_at':
                                    datetime.utcnow()
                                    .isoformat(),
                            }).eq(
                                'id',
                                sig['id']
                            ).execute()

                            stats[
                                'tp_hit'
                            ] += 1

                            closed_this_cycle = (
                                True
                            )

                            logger.info(
                                f"TP golpeado: "
                                f"{symbol} {tf} "
                                f"SHORT @ {tp} "
                                f"({pnl['pct']:+.2f}%)"
                            )

                            break

                # ============================================================
                # 4. MFE / MAE SÓLO SI LA POSICIÓN SIGUE ABIERTA
                # ============================================================
                #
                # 7D.2 es deliberadamente pasiva.
                #
                # Si TP/SL acaba de cerrar la señal, no hacemos aquí
                # ninguna segunda escritura.
                # ============================================================

                if closed_this_cycle:
                    continue

                excursion = (
                    _calculate_open_excursions(
                        sig,
                        df_after,
                        excursion_start_ts
                    )
                )

                if not excursion:
                    continue

                changed = bool(
                    excursion.pop(
                        '_changed',
                        False
                    )
                )

                # ============================================================
                # FASE 7D.3 — SHADOW EARLY EXIT
                # ============================================================
                #
                # Se evalúa aunque MFE/MAE no hayan cambiado.
                #
                # Esto es importante:
                # el deterioro puede venir de tiempo, momentum o estructura,
                # no necesariamente de un nuevo extremo.
                # ============================================================

                shadow_exit = (
                    _observe_early_exit_shadow(
                        sig,
                        df_after,
                        excursion_start_ts,
                        excursion
                    )
                )

                # ============================================================
                # AGRUPAR EN UNA SOLA ESCRITURA
                # ============================================================

                update_payload = {}

                now_iso = (
                    datetime.utcnow()
                    .isoformat()
                )

                if changed:

                    update_payload.update(
                        excursion
                    )

                    update_payload[
                        'last_excursion_at'
                    ] = now_iso

                    stats[
                        'mfe_mae_updated'
                    ] += 1

                if shadow_exit:

                    update_payload.update(
                        shadow_exit
                    )

                    stats[
                        'early_exit_observed'
                    ] += 1

                    logger.info(
                        f"👁️ EARLY EXIT SHADOW: "
                        f"{symbol} {tf} {action} "
                        f"@ {shadow_exit.get('early_exit_candidate_price')} "
                        f"R={shadow_exit.get('early_exit_candidate_r')} "
                        f"score={shadow_exit.get('early_exit_score')}"
                    )

                # ============================================================
                # CERO CAMBIOS = CERO ESCRITURAS
                # ============================================================

                if not update_payload:
                    continue

                update_payload[
                    'updated_at'
                ] = now_iso

                db.client.table(
                    'saved_signals'
                ).update(
                    update_payload
                ).eq(
                    'id',
                    sig['id']
                ).execute()
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"evaluate_saved_signals: error en {sig.get('id')}: {e}")
        
        return stats
    except Exception as e:
        logger.error(f"evaluate_saved_signals: {e}")
        return stats

def _build_early_exit_learning_summary(
    rows: List[Dict]
) -> Dict:
    """
    FASE 7D.4

    Resume estadísticamente los resultados del Early Exit
    observado durante 7D.3.

    IMPORTANTE:
    - NO modifica señales.
    - NO modifica el Futures Guardian.
    - NO cambia HOLD / REDUCE / EXIT.
    - NO ejecuta operaciones.
    - NO hace consultas adicionales a Supabase.

    Sólo aprende de operaciones que ya tienen:
        early_exit_evaluated = True

    La métrica principal es:

        early_exit_delta_r =
            R del Early Exit hipotético
            -
            R del cierre real

    Interpretación:

        > 0  → Early Exit habría ayudado.
        < 0  → Early Exit habría perjudicado.
        = 0  → resultado equivalente.
    """

    try:

        evaluated = []

        for row in (
            rows
            if isinstance(rows, list)
            else []
        ):

            if not bool(
                row.get(
                    'early_exit_evaluated',
                    False
                )
            ):
                continue

            raw_delta = row.get(
                'early_exit_delta_r'
            )

            if raw_delta is None:
                continue

            try:
                delta_r = float(
                    raw_delta
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            evaluated.append({
                'symbol':
                    str(
                        row.get(
                            'symbol',
                            ''
                        )
                        or ''
                    ),

                'timeframe':
                    str(
                        row.get(
                            'timeframe',
                            ''
                        )
                        or ''
                    ),

                'action':
                    str(
                        row.get(
                            'action',
                            ''
                        )
                        or ''
                    ).upper(),

                'delta_r':
                    delta_r,

                'candidate_r':
                    float(
                        row.get(
                            'early_exit_candidate_r',
                            0
                        )
                        or 0
                    ),

                'actual_r':
                    float(
                        row.get(
                            'actual_close_r',
                            0
                        )
                        or 0
                    )
            })

        sample = len(
            evaluated
        )

        # ==============================================================
        # SIN MUESTRA
        # ==============================================================

        if sample == 0:

            return {
                'sample': 0,

                'helpful': 0,
                'harmful': 0,
                'neutral': 0,

                'helpful_rate': 0.0,

                'avg_delta_r': 0.0,
                'total_delta_r': 0.0,

                'best_delta_r': 0.0,
                'worst_delta_r': 0.0,

                'by_context': {}
            }

        # ==============================================================
        # RESULTADO GLOBAL
        # ==============================================================

        deltas = [
            item['delta_r']
            for item in evaluated
        ]

        helpful = sum(
            1
            for value in deltas
            if value > 0
        )

        harmful = sum(
            1
            for value in deltas
            if value < 0
        )

        neutral = (
            sample
            - helpful
            - harmful
        )

        total_delta_r = sum(
            deltas
        )

        avg_delta_r = (
            total_delta_r
            / sample
        )

        helpful_rate = (
            helpful
            / sample
            * 100
        )

        # ==============================================================
        # APRENDIZAJE POR CONTEXTO
        # ==============================================================
        #
        # No mezclamos, por ejemplo:
        #
        # BTC 4h LONG
        # con
        # ADA 5m SHORT
        #
        # porque el comportamiento temporal puede ser muy diferente.
        # ==============================================================

        context_values = {}

        for item in evaluated:

            key = (
                f"{item['symbol']}|"
                f"{item['timeframe']}|"
                f"{item['action']}"
            )

            context_values.setdefault(
                key,
                []
            ).append(
                item['delta_r']
            )

        by_context = {}

        for (
            key,
            values
        ) in context_values.items():

            context_sample = len(
                values
            )

            context_helpful = sum(
                1
                for value in values
                if value > 0
            )

            context_total = sum(
                values
            )

            by_context[
                key
            ] = {
                'sample':
                    context_sample,

                'helpful_rate':
                    round(
                        (
                            context_helpful
                            / context_sample
                            * 100
                        )
                        if context_sample > 0
                        else 0.0,
                        2
                    ),

                'avg_delta_r':
                    round(
                        (
                            context_total
                            / context_sample
                        )
                        if context_sample > 0
                        else 0.0,
                        4
                    ),

                'total_delta_r':
                    round(
                        context_total,
                        4
                    )
            }

        return {
            'sample':
                sample,

            'helpful':
                helpful,

            'harmful':
                harmful,

            'neutral':
                neutral,

            'helpful_rate':
                round(
                    helpful_rate,
                    2
                ),

            'avg_delta_r':
                round(
                    avg_delta_r,
                    4
                ),

            'total_delta_r':
                round(
                    total_delta_r,
                    4
                ),

            'best_delta_r':
                round(
                    max(
                        deltas
                    ),
                    4
                ),

            'worst_delta_r':
                round(
                    min(
                        deltas
                    ),
                    4
                ),

            'by_context':
                by_context
        }

    except Exception as e:

        logger.warning(
            f"_build_early_exit_learning_summary: {e}"
        )

        return {
            'sample': 0,
            'helpful': 0,
            'harmful': 0,
            'neutral': 0,
            'helpful_rate': 0.0,
            'avg_delta_r': 0.0,
            'total_delta_r': 0.0,
            'best_delta_r': 0.0,
            'worst_delta_r': 0.0,
            'by_context': {}
        }


# ============================================================================
# ESTADÍSTICAS (KPIs propios de la pestaña de señales guardadas)
# ============================================================================
def get_saved_signals_kpis(
    user_name: Optional[str] = None
) -> Dict:
    """
    Retorna KPIs de las señales guardadas cerradas (winrate + PnL).
    
    Reglas:
    - Solo cuentan las cerradas: tp_hit, sl_hit, closed_manual
    - Adicionalmente entry_touched=True
    - Win: pnl_pct > 0 | Loss: pnl_pct < 0 | Neutral: pnl_pct == 0
    """
    db = _get_db()
    if db is None:
        return {'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
                'pnl_total_pct': 0.0, 'pnl_total_usdt': 0.0, 'active': 0}
    
    try:
        # Cerradas (para winrate)
        def _op_closed():

            q = (
                db.client
                .table(
                    'saved_signals'
                )
                .select(
                    (
                        'symbol,'
                        'timeframe,'
                        'action,'
                        'pnl_pct,'
                        'pnl_usdt,'
                        'entry_touched,'
                        'status,'
                        'early_exit_evaluated,'
                        'early_exit_candidate_r,'
                        'actual_close_r,'
                        'early_exit_delta_r,'
                        'early_exit_would_help'
                    )
                )
                .in_(
                    'status',
                    [
                        'tp_hit',
                        'sl_hit',
                        'closed_manual'
                    ]
                )
                .eq(
                    'entry_touched',
                    True
                )
            )

            if user_name:

                q = q.eq(
                    'user_name',
                    str(
                        user_name
                    ).strip()
                )

            return q.execute()
        r_closed = db._with_retry(_op_closed)
        closed = r_closed.data if r_closed and r_closed.data else []
        
        # Activas (no cuentan para winrate pero sí para 'activas')
        def _op_active():

            q = (
                db.client
                .table(
                    'saved_signals'
                )
                .select(
                    'id',
                    count='exact'
                )
                .in_(
                    'status',
                    [
                        'active',
                        'entry_touched'
                    ]
                )
                .limit(
                    1
                )
            )

            if user_name:

                q = q.eq(
                    'user_name',
                    str(
                        user_name
                    ).strip()
                )

            return q.execute()
        r_active = db._with_retry(_op_active)
        active_count = r_active.count if hasattr(r_active, 'count') and r_active.count is not None else 0
        
        wins = sum(1 for s in closed if float(s.get('pnl_pct') or 0) > 0)
        losses = sum(1 for s in closed if float(s.get('pnl_pct') or 0) < 0)
        total = len(closed)
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        pnl_total_pct = sum(
            float(
                s.get(
                    'pnl_pct'
                )
                or 0
            )
            for s in closed
        )

        pnl_total_usdt = sum(
            float(
                s.get(
                    'pnl_usdt'
                )
                or 0
            )
            for s in closed
        )

        # ==============================================================
        # FASE 7D.4 — APRENDIZAJE EARLY EXIT
        # ==============================================================
        # Reutiliza exactamente las mismas filas que ya cargamos
        # para los KPIs.
        # ==============================================================

        early_exit_learning = (
            _build_early_exit_learning_summary(
                closed
            )
        )

        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'pnl_total_pct':
                round(
                    pnl_total_pct,
                    3
                ),

            'pnl_total_usdt':
                round(
                    pnl_total_usdt,
                    3
                ),

            'active':
                int(
                    active_count
                ),

            # FASE 7D.4
            'early_exit_learning':
                early_exit_learning,
        }
    except Exception as e:
        logger.error(f"get_saved_signals_kpis: {e}")
        return {'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
                'pnl_total_pct': 0.0, 'pnl_total_usdt': 0.0, 'active': 0}
