# futures_system.py
# Sistema de análisis de FUTUROS - Extiende TradingExpertSystem del sistema principal
# Versión 1.0 - FASE 4
#
# CARACTERÍSTICAS:
# - 5 criptomonedas: BTC, ETH, SOL, XRP, ADA (contra USDT)
# - 6 temporalidades: 5m, 15m, 30m, 1h, 2h, 4h
# - Solo acciones LONG y SHORT (nunca COMPRA_SPOT/VENTA_SPOT)
# - Apalancamiento dinámico: x10-x50 en TF cortas, x5-x20 en TF largas
# - Hereda TODA la lógica del sistema principal (traders, indicadores, patrones)
# - Correlación adaptada: BTC dominancia + BTC vs alts (no PAXG)
# - Usa el mismo Moderador con los 9 traders + ReviewTrader (cuando esté integrado)
# - Registra señales en Supabase con system_type='futures'

import logging
from datetime import datetime
from typing import Dict, List, Optional

# Importamos la clase base del sistema principal
from app import TradingExpertSystem, KUCOIN_INTERVALS, SYMBOLS as SPOT_SYMBOLS

logger = logging.getLogger('FUTURES')
logger.setLevel(logging.INFO)

# ============================================================================
# CONFIGURACIÓN DE FUTUROS
# ============================================================================

# Símbolos disponibles para futuros
FUTURES_SYMBOLS = {
    'BTC-USDT': {'name': 'BTC/USDT', 'type': 'crypto_major', 'decimals': 2},
    'ETH-USDT': {'name': 'ETH/USDT', 'type': 'crypto_major', 'decimals': 2},
    'SOL-USDT': {'name': 'SOL/USDT', 'type': 'crypto_alt', 'decimals': 2},
    'XRP-USDT': {'name': 'XRP/USDT', 'type': 'crypto_alt', 'decimals': 4},
    'ADA-USDT': {'name': 'ADA/USDT', 'type': 'crypto_alt', 'decimals': 4}
}

# Temporalidades para futuros (TF cortas)
FUTURES_TIMEFRAMES = {
    '5m':  {'name': '5 Minutos',  'type': 'scalping',   'kucoin': '5min'},
    '15m': {'name': '15 Minutos', 'type': 'scalping',   'kucoin': '15min'},
    '30m': {'name': '30 Minutos', 'type': 'intraday',   'kucoin': '30min'},
    '1h':  {'name': '1 Hora',     'type': 'intraday',   'kucoin': '1hour'},
    '2h':  {'name': '2 Horas',    'type': 'intraday',   'kucoin': '2hour'},
    '4h':  {'name': '4 Horas',    'type': 'intraday',   'kucoin': '4hour'}
}

# Duración real de cada temporalidad. Se usa únicamente para comprobar
# si la última fila OHLCV ya cerró; no modifica indicadores ni niveles.
FUTURES_TIMEFRAME_SECONDS = {
    '5m': 5 * 60,
    '15m': 15 * 60,
    '30m': 30 * 60,
    '1h': 60 * 60,
    '2h': 2 * 60 * 60,
    '4h': 4 * 60 * 60,
}
# Extender el mapeo de intervalos KuCoin
FUTURES_KUCOIN_INTERVALS = {
    '5m': '5min',
    '15m': '15min',
    '30m': '30min',
    '1h': '1hour',
    '2h': '2hour',
    '4h': '4hour'
}

# ============================================================================
# RANGOS DE LEVERAGE POR TEMPORALIDAD
# ============================================================================
#
# IMPORTANTE:
# Estos valores son TECHOS, NO mínimos obligatorios.
#
# El leverage final se determinará posteriormente usando:
#
#   1. Execution Safety
#   2. Distancia del SL
#   3. Calidad del TP
#   4. RR
#   5. Costes
#   6. Temporalidad
#   7. Viabilidad económica con el margen
#
# El mínimo operativo siempre puede ser 1x.
#
LEVERAGE_RANGES = {
    '5m':  (25, 100),
    '15m': (20, 70),
    '30m': (15, 50),
    '1h':  (10, 35),
    '2h':  (8, 25),
    '4h':  (5, 20),
}
# ============================================================================
# ECONOMÍA DE FUTUROS — CONFIGURACIÓN
# ============================================================================
# El usuario trabaja normalmente con márgenes pequeños (~10 USDT).
#
# IMPORTANTE:
# El leverage no se determina únicamente por confianza.
# Debe ser viable después de costes y estar limitado por el riesgo del SL.
# ============================================================================

FUTURES_RISK_CONFIG = {

    # Margen habitual utilizado por el usuario.
    'default_margin_usdt': 10.0,

    # Beneficio neto mínimo deseado por operación.
    # No significa que todas las operaciones deban alcanzar esto:
    # sólo define el mínimo económico para considerar una entrada.
    'target_net_profit_usdt': 0.50,

    # Coste ida + vuelta estimado.
    #
    # DEBES reemplazar este valor por el coste REAL de tu exchange
    # incluyendo comisión y un margen prudente para slippage.
    #
    # Ejemplo ilustrativo: 0.12% = 0.0012
    'round_trip_cost_pct': 0.0012,

    # Máxima pérdida prevista sobre el margen.
    #
    # No es una garantía de pérdida máxima real.
    # Slippage, gaps y liquidación pueden producir diferencias.
    'max_loss_pct_margin': 10.0,

    # Leverage máximo absoluto que el sistema permitirá.
    # Después también se aplicará el máximo específico del TF.
    'absolute_max_leverage': 100,

    # Porcentaje mínimo del score de seguridad necesario para
    # poder abrir futuros.
    'minimum_execution_safety': 65.0,

    # Con seguridad muy elevada se permite acercarse más al máximo.
    'high_safety_threshold': 90.0,
}

def _leverage_in_valid_range(
    leverage: int,
    timeframe: str
) -> bool:
    """
    Valida el rango de leverage REAL exigido por el timeframe.

    Importante:
    - El mínimo NO se fuerza.
    - El mínimo es un REQUISITO para publicar la señal.
    - Si el sistema sólo puede soportar menos del mínimo:
      la señal debe ser rechazada.

    Ejemplo:

        4h → mínimo 5x
        leverage calculado = 4x
        → inválido
        → NO OPERAR
    """

    try:
        lev = int(leverage)
    except (
        TypeError,
        ValueError
    ):
        return False

    min_leverage, max_leverage = LEVERAGE_RANGES.get(
        timeframe,
        (1, 10)
    )

    return (
        min_leverage
        <= lev
        <= max_leverage
    )


# ============================================================================
# CLASE PRINCIPAL: FUTURES ANALYSIS
# ============================================================================

class FuturesAnalysis(TradingExpertSystem):
    """
    Sistema de análisis de futuros. Hereda TODA la lógica del sistema principal
    (indicadores, traders, moderador, votación) y sobreescribe solo lo específico
    de futuros:
    - Símbolos permitidos (5 cripto sin PAXG)
    - Temporalidades permitidas (5m-4h)
    - Cálculo de apalancamiento óptimo
    - Traducción de acciones (COMPRA_SPOT → LONG, VENTA_SPOT → SHORT)
    - Correlación (BTC dominancia + BTC vs alts)
    """
    
    def __init__(self):
        super().__init__()
        print("=" * 60)
        print("🚀 FUTURES ANALYSIS - INICIALIZANDO")
        print("=" * 60)
        print(f"✅ Símbolos: {list(FUTURES_SYMBOLS.keys())}")
        print(f"✅ Temporalidades: {list(FUTURES_TIMEFRAMES.keys())}")
        print(f"✅ Apalancamiento por TF:")
        for tf, (lo, hi) in LEVERAGE_RANGES.items():
            print(f"   {tf}: x{lo} - x{hi}")
        print("=" * 60)
    
    # ========================================================================
    # OVERRIDE: OBTENER DATOS DE KUCOIN (mapea TF cortas)
    # ========================================================================
    
    def get_kucoin_data(self, symbol: str, interval: str):
        """
        Obtener datos de velas de KuCoin.
        Sobrescribe el método padre para incluir las temporalidades cortas.
        Usa kucoin_cache (Session HTTP + caché con TTL por TF).
        """
        try:
            from kucoin_cache import fetch_kucoin_candles, KUCOIN_INTERVALS as CACHE_INTERVALS
            
            # Validar que el intervalo esté soportado (incluye los TF cortos de futuros)
            all_intervals = {**KUCOIN_INTERVALS, **FUTURES_KUCOIN_INTERVALS}
            if interval not in all_intervals and interval not in CACHE_INTERVALS:
                print(f"❌ Intervalo no soportado: {interval}")
                return self._generate_fallback_data(symbol, interval)
            
            df = fetch_kucoin_candles(symbol, interval, timeout=15)
            if df is None or df.empty:
                return self._generate_fallback_data(symbol, interval)
            return df
        except Exception as e:
            print(f"Excepción en get_kucoin_data (futures): {e}")
            return self._generate_fallback_data(symbol, interval)
    
    def _generate_fallback_data(self, symbol: str, interval: str):
        """Genera datos sintéticos si KuCoin falla"""
        import numpy as np
        import pandas as pd
        from datetime import datetime, timedelta
        
        try:
            # Precios base por símbolo
            base_prices = {
                'BTC-USDT': 68000,
                'ETH-USDT': 3500,
                'SOL-USDT': 150,
                'XRP-USDT': 0.55,
                'ADA-USDT': 0.40
            }
            base_price = base_prices.get(symbol, 100)
            volatility = 0.015  # 1.5%
            
            # Cantidad de velas y frecuencia
            freq_map = {
                '5m': ('5min', 300),
                '15m': ('15min', 200),
                '30m': ('30min', 200),
                '1h': ('1H', 200),
                '2h': ('2H', 200),
                '4h': ('4H', 200)
            }
            freq, periods = freq_map.get(interval, ('1H', 100))
            
            end_date = datetime.now()
            dates = pd.date_range(end=end_date, periods=periods, freq=freq)
            
            np.random.seed(hash(symbol) % 1000)
            returns = np.random.randn(periods) * volatility
            price_series = base_price * np.exp(np.cumsum(returns))
            
            df = pd.DataFrame({
                'time': dates,
                'open': price_series * (1 + np.random.randn(periods) * 0.002),
                'high': price_series * (1 + abs(np.random.randn(periods) * 0.005)),
                'low': price_series * (1 - abs(np.random.randn(periods) * 0.005)),
                'close': price_series * (1 + np.random.randn(periods) * 0.001),
                'volume': np.abs(np.random.randn(periods) * 1000 + 5000)
            })
            df['high'] = df[['open', 'close', 'high']].max(axis=1)
            df['low'] = df[['open', 'close', 'low']].min(axis=1)
            
            return df
        except Exception as e:
            print(f"Error generando fallback: {e}")
            return None
            
    def _calculate_execution_safety(
        self,
        levels: Dict,
        trend: Dict,
        momentum: Dict,
        structure: Dict,
        timeframe: str
    ) -> Dict:
        """
        Calcula la SEGURIDAD DE EJECUCIÓN de una señal de futuros.
    
        IMPORTANTE:
        Este score NO es una probabilidad matemática.
    
        Representa calidad de ejecución:
    
            ENTRY
            SL
            TP
            RR
            SMC
            estructura
            temporalidad
    
        La confianza del comité NO participa directamente.
    
        El score será recalibrado estadísticamente por ReviewTrader
        en una fase posterior.
        """
    
        try:
    
            # ==============================================================
            # SCORES BASE
            # ==============================================================
    
            entry_score = float(
                levels.get(
                    'entry_score',
                    0
                )
                or 0
            )
    
            tp_quality = float(
                levels.get(
                    'tp_quality_score',
                    0
                )
                or 0
            )
    
            sl_reliability_raw = float(
                levels.get(
                    'sl_reliability',
                    0
                )
                or 0
            )
    
            # app.py entrega actualmente sl_reliability
            # normalizado 0-1.
            if sl_reliability_raw <= 1:
                sl_quality = (
                    sl_reliability_raw * 100
                )
            else:
                sl_quality = sl_reliability_raw
    
            rr = float(
                levels.get(
                    'risk_reward',
                    0
                )
                or 0
            )
    
            # ==============================================================
            # 1. ENTRY SMC
            # ==============================================================
            entry_component = max(
                0,
                min(
                    100,
                    entry_score
                )
            )
    
            # ==============================================================
            # 2. SL
            # ==============================================================
            sl_component = max(
                0,
                min(
                    100,
                    sl_quality
                )
            )
    
            # ==============================================================
            # 3. TP
            # ==============================================================
            tp_component = max(
                0,
                min(
                    100,
                    tp_quality
                )
            )
    
            # ==============================================================
            # 4. RR
            # ==============================================================
            if rr < 1.8:
                rr_component = 0
    
            elif rr < 2.0:
                rr_component = 45
    
            elif rr < 2.5:
                rr_component = 65
    
            elif rr < 3.0:
                rr_component = 80
    
            elif rr < 3.5:
                rr_component = 90
    
            elif rr <= 4.5:
                rr_component = 100
    
            else:
                # Un RR demasiado grande suele implicar
                # un TP excesivamente lejano.
                rr_component = 65
    
            # ==============================================================
            # 5. CONDICIONES ESTRUCTURALES
            # ==============================================================
            structure_component = 50
    
            if isinstance(
                structure,
                dict
            ):
    
                order_blocks = structure.get(
                    'order_blocks',
                    []
                ) or []
    
                fvgs = structure.get(
                    'fair_value_gaps',
                    []
                ) or []
    
                sweeps = structure.get(
                    'liquidity_sweeps',
                    []
                ) or []
    
                if order_blocks:
                    structure_component += 10
    
                if fvgs:
                    structure_component += 10
    
                if sweeps:
                    structure_component += 15
    
            structure_component = min(
                100,
                structure_component
            )
    
            # ==============================================================
            # 6. MOMENTUM / TREND
            # ==============================================================
            trend_component = 50
    
            if isinstance(
                trend,
                dict
            ):
    
                adx = float(
                    trend.get(
                        'adx',
                        0
                    )
                    or 0
                )
    
                if adx >= 30:
                    trend_component += 20
    
                elif adx >= 25:
                    trend_component += 10
    
                elif adx < 15:
                    trend_component -= 20
    
            if isinstance(
                momentum,
                dict
            ):
    
                momentum_direction = str(
                    momentum.get(
                        'direction',
                        ''
                    )
                ).lower()
    
                if momentum_direction in (
                    'bullish',
                    'bearish'
                ):
                    trend_component += 10
    
            trend_component = max(
                0,
                min(
                    100,
                    trend_component
                )
            )
    
            # ==============================================================
            # 7. FACTOR TEMPORAL
            # ==============================================================
            #
            # Basado provisionalmente en el histórico del sistema:
            #
            # 4h = mejor desempeño
            # 30m = segunda zona relativamente mejor
            # 5m = peor
            #
            # NO es una probabilidad.
            #
            timeframe_factor = {
                '5m': 0.55,
                '15m': 0.70,
                '30m': 0.78,
                '1h': 0.60,
                '2h': 0.65,
                '4h': 0.95,
            }.get(
                timeframe,
                0.70
            )
    
            timeframe_component = (
                timeframe_factor
                * 100
            )
    
            # ==============================================================
            # SCORE FINAL
            # ==============================================================
            #
            # Pesos:
            #
            # ENTRY SMC       25%
            # SL              20%
            # TP              15%
            # RR              15%
            # estructura      10%
            # tendencia       5%
            # temporalidad    10%
            #
            score = (
                entry_component * 0.25
                + sl_component * 0.20
                + tp_component * 0.15
                + rr_component * 0.15
                + structure_component * 0.10
                + trend_component * 0.05
                + timeframe_component * 0.10
            )
    
            score = max(
                0,
                min(
                    100,
                    score
                )
            )
    
            # ==============================================================
            # CLASIFICACIÓN
            # ==============================================================
            if score >= 85:
                label = 'PREMIUM'
    
            elif score >= 75:
                label = 'ALTA'
    
            elif score >= 65:
                label = 'VALIDA'
    
            elif score >= 55:
                label = 'BAJA'
    
            else:
                label = 'RECHAZAR'
    
            return {
                'score': round(
                    score,
                    1
                ),
                'label': label,
    
                'components': {
                    'entry_smc': round(
                        entry_component,
                        1
                    ),
                    'sl': round(
                        sl_component,
                        1
                    ),
                    'tp': round(
                        tp_component,
                        1
                    ),
                    'rr': round(
                        rr_component,
                        1
                    ),
                    'structure': round(
                        structure_component,
                        1
                    ),
                    'trend': round(
                        trend_component,
                        1
                    ),
                    'timeframe': round(
                        timeframe_component,
                        1
                    )
                },
    
                'timeframe_factor': round(
                    timeframe_factor,
                    3
                )
            }
    
        except Exception as e:
    
            logger.warning(
                f"Error calculando execution safety: {e}"
            )
    
            return {
                'score': 0,
                'label': 'RECHAZAR',
                'components': {},
                'timeframe_factor': 0
            }    
    # ========================================================================
    # CÁLCULO DE APALANCAMIENTO ÓPTIMO
    # ========================================================================
    def _calculate_economic_leverage(
        self,
        margin_usdt,
        tp_distance_pct,
        sl_distance_pct,
        execution_safety,
        timeframe
    ):
        """
        Determina el rango de leverage económicamente viable.
    
        El leverage debe cumplir simultáneamente:
    
        1. Ser suficiente para que el TP produzca utilidad neta mínima.
        2. No superar la pérdida máxima permitida por el SL.
        3. Respetar la seguridad real de ejecución.
        4. Respetar el máximo del timeframe.
        5. Respetar el techo absoluto del sistema.
    
        Si no existe un leverage que cumpla las condiciones,
        devuelve None y la operación debe rechazarse.
        """
    
        try:
    
            margin = float(
                margin_usdt
                or FUTURES_RISK_CONFIG['default_margin_usdt']
            )
    
            tp_pct = abs(float(tp_distance_pct or 0))
            sl_pct = abs(float(sl_distance_pct or 0))
            safety = max(
                0.0,
                min(100.0, float(execution_safety or 0))
            )
    
            if (
                margin <= 0
                or tp_pct <= 0
                or sl_pct <= 0
            ):
                return None
    
            # --------------------------------------------------------------
            # COSTE TOTAL ESTIMADO
            # --------------------------------------------------------------
            round_trip_cost = float(
                FUTURES_RISK_CONFIG['round_trip_cost_pct']
            )
    
            # --------------------------------------------------------------
            # LEVERAGE MÍNIMO ECONÓMICO
            # --------------------------------------------------------------
            #
            # profit_net ≈ margin × leverage ×
            #              (TP% - costes%)
            #
            # Por tanto:
            #
            # leverage >= target_profit /
            #              (margin × (TP% - costes%))
            #
            edge_after_cost = (
                tp_pct / 100.0
                - round_trip_cost
            )
    
            if edge_after_cost <= 0:
                return None
    
            target_profit = float(
                FUTURES_RISK_CONFIG[
                    'target_net_profit_usdt'
                ]
            )
    
            min_leverage_economic = (
                target_profit
                / (margin * edge_after_cost)
            )
    
            # --------------------------------------------------------------
            # LEVERAGE MÁXIMO POR RIESGO DEL SL
            # --------------------------------------------------------------
            max_loss_pct = float(
                FUTURES_RISK_CONFIG[
                    'max_loss_pct_margin'
                ]
            )
    
            max_leverage_by_risk = (
                max_loss_pct
                / sl_pct
            )
    
            # --------------------------------------------------------------
            # LEVERAGE MÁXIMO POR TEMPORALIDAD
            # --------------------------------------------------------------
            _, tf_max = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
    
            absolute_max = float(
                FUTURES_RISK_CONFIG[
                    'absolute_max_leverage'
                ]
            )
    
            max_leverage = min(
                float(tf_max),
                absolute_max
            )
    
            # --------------------------------------------------------------
            # MODULACIÓN POR SEGURIDAD REAL
            # --------------------------------------------------------------
            #
            # No hacemos:
            # safety 90 -> 90x
            #
            # Hacemos:
            # safety bajo -> menor proporción del techo
            # safety alto -> puede aproximarse al techo
            #
            # El riesgo del SL sigue siendo una restricción dura.
            #
            security_factor = (
                0.25
                + 0.75 * (safety / 100.0)
            )
    
            if safety >= FUTURES_RISK_CONFIG[
                'high_safety_threshold'
            ]:
                security_factor = min(
                    1.0,
                    security_factor + 0.05
                )
    
            max_leverage_by_security = (
                max_leverage
                * security_factor
            )
    
            # --------------------------------------------------------------
            # LEVERAGE MÁXIMO FINAL
            # --------------------------------------------------------------
            final_max_leverage = min(
                max_leverage_by_risk,
                max_leverage_by_security,
                max_leverage
            )
            
            # --------------------------------------------------------------
            # MÍNIMO EXIGIDO POR EL TIMEFRAME
            # --------------------------------------------------------------
            min_leverage_tf, _ = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
            
            # --------------------------------------------------------------
            # SI EL MERCADO NO PERMITE ALCANZAR EL MÍNIMO,
            # NO EXISTE UNA OPERACIÓN VÁLIDA PARA ESTE SISTEMA.
            # --------------------------------------------------------------
            if (
                final_max_leverage
                < min_leverage_tf
            ):
            
                logger.info(
                    f"❌ FUTURES {timeframe}: "
                    f"máximo seguro {final_max_leverage:.2f}x "
                    f"< mínimo requerido {min_leverage_tf}x"
                )
            
                return None
            
            # --------------------------------------------------------------
            # REQUISITO MÍNIMO DEL TIMEFRAME
            # --------------------------------------------------------------
            min_leverage_tf, max_leverage_tf = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
            
            # --------------------------------------------------------------
            # MÁXIMO ABSOLUTO
            # --------------------------------------------------------------
            absolute_max = float(
                FUTURES_RISK_CONFIG[
                    'absolute_max_leverage'
                ]
            )
            
            max_leverage = min(
                float(max_leverage_tf),
                absolute_max
            )
            
            # --------------------------------------------------------------
            # ¿EL MÁXIMO SEGURO ALCANZA EL MÍNIMO DEL TF?
            # --------------------------------------------------------------
            if (
                final_max_leverage
                < min_leverage_tf
            ):
            
                logger.info(
                    f"FUTURES rechazado: "
                    f"el riesgo real sólo permite "
                    f"{final_max_leverage:.2f}x, "
                    f"pero {timeframe} exige mínimo "
                    f"{min_leverage_tf}x"
                )
            
                return None
            
            # --------------------------------------------------------------
            # ¿ES ECONÓMICAMENTE VIABLE?
            # --------------------------------------------------------------
            if (
                min_leverage_economic
                > final_max_leverage
            ):
                return None
    
            # Leverage objetivo:
            # suficiente para que la operación sea útil,
            # pero no mayor de lo necesario.
            # ==============================================================
            # LEVERAGE OBJETIVO
            # ==============================================================
            
            leverage_target = (
                final_max_leverage * 0.75
                +
                max(
                    min_leverage_economic,
                    float(min_leverage_tf)
                ) * 0.25
            )
            
            leverage = max(
                float(min_leverage_tf),
                min(
                    final_max_leverage,
                    leverage_target
                )
            )
    
            leverage = int(
                round(leverage)
            )
    
            leverage = max(
                1,
                min(
                    int(final_max_leverage),
                    leverage
                )
            )
    
            return {
                'leverage': leverage,
                'min_economic': round(
                    min_leverage_economic,
                    2
                ),
                'max_by_risk': round(
                    max_leverage_by_risk,
                    2
                ),
                'max_by_security': round(
                    max_leverage_by_security,
                    2
                ),
                'min_by_timeframe': int(
                    min_leverage_tf
                ),
                'max_by_timeframe': int(
                    tf_max
                ),
                'security_factor': round(
                    security_factor,
                    3
                ),
                'economically_viable': True
            }
    
        except Exception as e:
    
            logger.warning(
                f"Error en cálculo económico de leverage: {e}"
            )
    
            return None    
   
    def calculate_optimal_leverage(
        self,
        timeframe: str,
        atr_pct: float,
        confidence: float,
        review_multiplier: float = 1.0,
        sl_distance_pct: float = None,
        max_loss_pct_of_margin: float = 10.0,
        execution_safety: float = 0.0,
        tp_distance_pct: float = None,
        margin_usdt: float = None
    ) -> int:

        """
        Calcula el leverage dinámico de futuros.
        
        El leverage final NO depende directamente de confidence.
        
        Se determina mediante:
        
            - Execution Safety
            - distancia del SL
            - distancia del TP
            - coste operativo
            - temporalidad
            - techo de leverage
        
        La seguridad del SL limita el leverage máximo.
        
        La rentabilidad mínima determina el leverage mínimo
        económicamente necesario.
        
        Si el leverage mínimo económico supera el máximo seguro:
            → NO OPERAR.
        
        El objetivo es que una operación con margen pequeño
        (~10 USDT) siga siendo económicamente útil sin aumentar
        artificialmente el riesgo.
        """
    
        economic = self._calculate_economic_leverage(
            margin_usdt=(
                margin_usdt
                or FUTURES_RISK_CONFIG[
                    'default_margin_usdt'
                ]
            ),
            tp_distance_pct=(
                tp_distance_pct
                or 0
            ),
            sl_distance_pct=(
                sl_distance_pct
                or 0
            ),
            execution_safety=execution_safety,
            timeframe=timeframe
        )
    
        if not economic:
    
            return 0
    
        return int(
            economic.get(
                'leverage',
                0
            )
        )
    
    def calculate_roi_futures(
        self,
        entry: float,
        tp: float,
        sl: float,
        leverage: int,
        direction: str
    ) -> Dict:
        """
        Calcula el ROI potencial de una operación de futuros.
    
        ROI positivo = ganancia potencial si toca TP.
        ROI negativo = pérdida potencial si toca SL.
    
        Además calcula una estimación monetaria basada en el
        margen de referencia configurado para Futuros.
    
        IMPORTANTE:
        - El ROI es sobre el margen.
        - Los importes USDT son estimaciones brutas.
        - Las comisiones/slippage se descuentan posteriormente
          en calculate_entry_levels().
        """
    
        # ==============================================================
        # VALIDACIÓN BÁSICA
        # ==============================================================
    
        if entry <= 0 or leverage <= 0:
            return {
                'roi_tp': 0,
                'roi_sl': 0,
                'move_tp_pct': 0,
                'move_sl_pct': 0,
                'profit_tp_usdt': 0,
                'loss_sl_usdt': 0
            }
    
        if tp <= 0 or sl <= 0:
            return {
                'roi_tp': 0,
                'roi_sl': 0,
                'move_tp_pct': 0,
                'move_sl_pct': 0,
                'profit_tp_usdt': 0,
                'loss_sl_usdt': 0
            }
    
        # ==============================================================
        # MOVIMIENTO DEL PRECIO
        # ==============================================================
    
        if direction == 'long':
    
            move_tp = (
                (tp - entry)
                / entry
                * 100
            )
    
            move_sl = (
                (entry - sl)
                / entry
                * 100
            )
    
        else:
    
            move_tp = (
                (entry - tp)
                / entry
                * 100
            )
    
            move_sl = (
                (sl - entry)
                / entry
                * 100
            )
    
        # ==============================================================
        # VALIDAR QUE TP Y SL ESTÉN DEL LADO CORRECTO
        # ==============================================================
    
        if move_tp < 0:
            move_tp = 0
    
        if move_sl < 0:
            move_sl = 0
    
        # ==============================================================
        # ROI SOBRE EL MARGEN
        # ==============================================================
    
        # ROI TP = movimiento × leverage
        roi_tp = (
            move_tp
            * leverage
        )
    
        # ROI SL siempre se muestra negativo
        roi_sl = (
            -move_sl
            * leverage
        )
    
        # ==============================================================
        # MARGEN DE REFERENCIA
        # ==============================================================
    
        # El sistema actualmente trabaja con una configuración
        # de margen por defecto para poder estimar el resultado
        # monetario.
        #
        # Más adelante Fase 5B:
        # utilizaremos el margen REAL de cada señal.
        try:
    
            margin_usdt = float(
                FUTURES_RISK_CONFIG.get(
                    'default_margin_usdt',
                    10.0
                )
            )
    
        except (
            TypeError,
            ValueError,
            AttributeError
        ):
    
            margin_usdt = 10.0
    
        if margin_usdt <= 0:
            margin_usdt = 10.0
    
        # ==============================================================
        # NOTIONAL
        # ==============================================================
    
        # Ejemplo:
        #
        # margen = 10 USDT
        # leverage = 8x
        #
        # notional = 80 USDT
        #
        notional_usdt = (
            margin_usdt
            * leverage
        )
    
        # ==============================================================
        # GANANCIA BRUTA EN TP
        # ==============================================================
    
        profit_tp_usdt = (
            notional_usdt
            * (move_tp / 100.0)
        )
    
        # ==============================================================
        # PÉRDIDA BRUTA EN SL
        # ==============================================================
    
        loss_sl_usdt = (
            notional_usdt
            * (move_sl / 100.0)
        )
    
        # ==============================================================
        # RESULTADO
        # ==============================================================
    
        return {
            'roi_tp': round(
                roi_tp,
                2
            ),
    
            'roi_sl': round(
                roi_sl,
                2
            ),
    
            'move_tp_pct': round(
                move_tp,
                2
            ),
    
            'move_sl_pct': round(
                move_sl,
                2
            ),
    
            # Ganancia bruta estimada si toca TP
            'profit_tp_usdt': round(
                profit_tp_usdt,
                4
            ),
    
            # Pérdida bruta estimada si toca SL
            'loss_sl_usdt': round(
                loss_sl_usdt,
                4
            ),
    
            # Información adicional útil para debug/UI
            'margin_usdt': round(
                margin_usdt,
                4
            ),
    
            'notional_usdt': round(
                notional_usdt,
                4
            )
        }
    
    # ========================================================================
    # OVERRIDE: CALCULATE_ENTRY_LEVELS (para futuros)
    # ========================================================================
    
    def calculate_entry_levels(self, decision, trend, momentum, volatility, structure, 
                                symbol, timeframe, liquidation=None):
        """
        Override específico para futuros.
        
        1. Traduce COMPRA_SPOT/VENTA_SPOT a LONG/SHORT (nunca operaciones spot en futuros).
        2. Llama al calculate_entry_levels padre para obtener niveles Smart Money.
        3. Recalcula el apalancamiento con la fórmula optimizada para futuros.
        4. Añade cálculos de ROI potencial.
        """
        # Traducción de acción (defensiva)
        original_action = decision
        if decision == 'COMPRA_SPOT':
            decision = 'LONG'
        elif decision == 'VENTA_SPOT':
            decision = 'SHORT'
        
        # Solo procesar acciones de futuros
        if decision not in ('LONG', 'SHORT'):
            return self._get_default_levels(structure.get('current_price', 0), symbol)
        
        # Llamar al método padre para obtener niveles base
        levels = super().calculate_entry_levels(
            decision, trend, momentum, volatility, structure, symbol, timeframe, liquidation
        )
        
        # Si la señal fue rechazada por el padre, propagar
        if levels.get('rejected_reason'):
            return levels
        
        # ==============================================================
        # FASE 5 — EXECUTION SAFETY
        # ==============================================================
        
        atr_pct = float(
            volatility.get(
                'atr_pct',
                1.0
            )
            or 1.0
        )
        
        review_multiplier = getattr(
            self,
            '_current_review_multiplier',
            1.0
        )
        
        entry_price = float(
            levels.get(
                'entry',
                0
            )
            or 0
        )
        
        sl_price = float(
            levels.get(
                'stop_loss',
                0
            )
            or 0
        )
        
        tp_price = float(
            levels.get(
                'take_profit',
                0
            )
            or 0
        )
        
        sl_distance_pct = None
        tp_distance_pct = None
        
        if (
            entry_price > 0
            and sl_price > 0
        ):
            sl_distance_pct = (
                abs(
                    entry_price
                    - sl_price
                )
                / entry_price
                * 100
            )
        
        if (
            entry_price > 0
            and tp_price > 0
        ):
            tp_distance_pct = (
                abs(
                    tp_price
                    - entry_price
                )
                / entry_price
                * 100
            )
        
        # ==============================================================
        # SEGURIDAD REAL DE EJECUCIÓN
        # ==============================================================
        execution_safety = (
            self._calculate_execution_safety(
                levels=levels,
                trend=trend or {},
                momentum=momentum or {},
                structure=structure or {},
                timeframe=timeframe
            )
        )
        
        safety_score = float(
            execution_safety.get(
                'score',
                0
            )
        )
        
        safety_label = execution_safety.get(
            'label',
            'RECHAZAR'
        )
        
        print(
            f"   🛡️ Execution Safety: "
            f"{safety_score:.1f}/100 "
            f"({safety_label})"
        )
        
        # ==============================================================
        # FASE 7E.3 — EXECUTION SAFETY OPERATIVO PROTEGIDO
        # ==============================================================
        #
        # La configuración estática sigue siendo la FUENTE BASE.
        #
        # ReviewTrader puede:
        #
        #     ✅ endurecer el filtro
        #     ✅ reducir Safety usado para leverage
        #
        # Nunca:
        #
        #     ❌ bajar el mínimo base
        #     ❌ aumentar Safety
        #     ❌ aumentar leverage
        #
        # Si ReviewTrader falla:
        #
        #     comportamiento original.
        # ==============================================================

        base_minimum_safety = float(
            FUTURES_RISK_CONFIG[
                'minimum_execution_safety'
            ]
        )

        minimum_safety = (
            base_minimum_safety
        )

        leverage_safety_score = (
            safety_score
        )

        execution_calibration = {
            'active':
                False,

            'mode':
                'STATIC_FALLBACK',

            'minimum_safety':
                base_minimum_safety,

            'raw_safety':
                safety_score,

            'leverage_safety_score':
                safety_score,

            'leverage_factor':
                1.0,

            'reason':
                'REVIEWTRADER_NO_DISPONIBLE'
        }

        try:

            # Import diferido para evitar dependencia circular.
            from review_trader import (
                review_trader
            )

            execution_calibration = (
                review_trader
                .get_execution_safety_operational_policy(
                    timeframe=timeframe,
                    safety_score=safety_score,
                    default_min_safety=(
                        base_minimum_safety
                    )
                )
            )

            if isinstance(
                execution_calibration,
                dict
            ):

                learned_minimum = float(
                    execution_calibration.get(
                        'minimum_safety',
                        base_minimum_safety
                    )
                    or base_minimum_safety
                )

                # ======================================================
                # GUARDRAIL FINAL EN FUTURES
                # ======================================================
                #
                # Aunque ReviewTrader tuviese un bug:
                #
                #     JAMÁS permitir bajar de la configuración base.
                # ======================================================

                minimum_safety = max(
                    base_minimum_safety,
                    learned_minimum
                )

                learned_leverage_safety = float(
                    execution_calibration.get(
                        'leverage_safety_score',
                        safety_score
                    )
                    or safety_score
                )

                # Nunca permitir una bonificación.
                leverage_safety_score = min(
                    safety_score,
                    learned_leverage_safety
                )

        except Exception as e:

            logger.debug(
                "7E.3 Execution Safety fallback: "
                f"{e}"
            )

            minimum_safety = (
                base_minimum_safety
            )

            leverage_safety_score = (
                safety_score
            )

        # ==============================================================
        # GUARDAR CONTEXTO DE CALIBRACIÓN
        # ==============================================================
        #
        # execution_safety sigue siendo el RAW original.
        #
        # Esto es MUY importante porque ReviewTrader debe seguir
        # aprendiendo sobre el score original y no sobre un score
        # ya modificado por sí mismo.
        # ==============================================================

        levels[
            'execution_safety'
        ] = round(
            safety_score,
            1
        )

        levels[
            'execution_safety_label'
        ] = (
            safety_label
        )

        levels[
            'execution_safety_operational_min'
        ] = round(
            minimum_safety,
            2
        )

        levels[
            'execution_safety_leverage_score'
        ] = round(
            leverage_safety_score,
            2
        )

        levels[
            'execution_safety_calibration_active'
        ] = bool(
            execution_calibration.get(
                'active',
                False
            )
        )

        levels[
            'execution_safety_calibration_mode'
        ] = str(
            execution_calibration.get(
                'mode',
                'STATIC_FALLBACK'
            )
        )

        if execution_calibration.get(
            'active',
            False
        ):

            print(
                "   🧠 7E.3 Safety protegido: "
                f"mínimo={minimum_safety:.1f} "
                f"| raw={safety_score:.1f} "
                f"| leverage_score="
                f"{leverage_safety_score:.1f} "
                f"| factor="
                f"{execution_calibration.get('leverage_factor', 1.0):.3f}"
            )

        if safety_score < minimum_safety:

            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"Execution Safety "
                f"{safety_score:.1f} < "
                f"{minimum_safety:.1f}"
            )

            # ==========================================================
            # CONSERVAR NIVELES TÉCNICOS
            # ==========================================================
            # Entry / SL / TP / RR siguen siendo información válida
            # del análisis aunque la operación NO sea ejecutable.
            # ==========================================================

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            return self._mark_levels_non_executable(
                levels,
                (
                    f"Execution Safety insuficiente "
                    f"({safety_score:.1f}/100)"
                )
            )
        
        # ==============================================================
        # LEVERAGE ECONÓMICO
        # ==============================================================
        optimal_leverage = (
            self.calculate_optimal_leverage(
                timeframe=timeframe,
                atr_pct=atr_pct,
                confidence=0,  # deliberadamente NO usado
                review_multiplier=review_multiplier,
                sl_distance_pct=sl_distance_pct,
                max_loss_pct_of_margin=float(
                    FUTURES_RISK_CONFIG[
                        'max_loss_pct_margin'
                    ]
                ),
                execution_safety=leverage_safety_score,
                tp_distance_pct=tp_distance_pct,
                margin_usdt=float(
                    FUTURES_RISK_CONFIG[
                        'default_margin_usdt'
                    ]
                )
            )
        )
        
        if optimal_leverage <= 0:

            print(
                "   ⚠️ FUTUROS ANALYSIS_ONLY: "
                "No existe leverage simultáneamente "
                "seguro y económicamente viable."
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            return self._mark_levels_non_executable(
                levels,
                (
                    "No existe leverage que cumpla "
                    "seguridad + riesgo + rentabilidad"
                )
            )
                
        # ============ CALCULAR ROI POTENCIAL ============
        direction = 'long' if decision == 'LONG' else 'short'
        
        roi = self.calculate_roi_futures(
            levels['entry'],
            levels['take_profit'],
            levels['stop_loss'],
            optimal_leverage,
            direction
        )
        
        levels.update(roi)
        levels['is_futures'] = True
        
        
        # ==============================================================
        # FASE 5 — VALIDACIÓN ECONÓMICA REAL
        # ==============================================================
        #
        # Ya no basta con:
        #
        #     ROI TP > 5%
        #
        # porque una operación puede mostrar ROI atractivo y,
        # después de comisiones, seguir siendo poco rentable.
        #
        # Ahora comprobamos:
        #
        #     1. ROI bruto suficiente
        #     2. coste estimado
        #     3. beneficio neto estimado
        #     4. pérdida estimada en USDT
        # ==============================================================
        
        min_roi_tp = 8.0
        
        if roi['roi_tp'] < min_roi_tp:

            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"ROI potencial "
                f"{roi['roi_tp']:.1f}% "
                f"< mínimo {min_roi_tp:.1f}%"
            )

            levels['leverage'] = int(
                optimal_leverage
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            return self._mark_levels_non_executable(
                levels,
                (
                    f"ROI potencial "
                    f"{roi['roi_tp']:.1f}% "
                    f"< {min_roi_tp:.1f}% mínimo"
                ),
                recommended_leverage=optimal_leverage
            )
        
        
        # ==============================================================
        # COSTE ESTIMADO DE LA OPERACIÓN
        # ==============================================================
        round_trip_cost = float(
            FUTURES_RISK_CONFIG.get(
                'round_trip_cost_pct',
                0.0012
            )
        )
        
        margin_usdt = float(
            FUTURES_RISK_CONFIG.get(
                'default_margin_usdt',
                10.0
            )
        )
        
        notional = (
            margin_usdt
            * optimal_leverage
        )
        
        estimated_cost_usdt = (
            notional
            * round_trip_cost
        )
        
        
        # ==============================================================
        # BENEFICIO NETO ESTIMADO EN TP
        # ==============================================================
        profit_tp_usdt = float(
            roi.get(
                'profit_tp_usdt',
                0
            )
            or 0
        )
        
        net_profit_tp_usdt = (
            profit_tp_usdt
            - estimated_cost_usdt
        )
        
        levels['estimated_cost_usdt'] = round(
            estimated_cost_usdt,
            4
        )
        
        levels['net_profit_tp_usdt'] = round(
            net_profit_tp_usdt,
            4
        )
        
        
        # ==============================================================
        # PÉRDIDA ESTIMADA EN SL
        # ==============================================================
        loss_sl_usdt = abs(
            float(
                roi.get(
                    'loss_sl_usdt',
                    0
                )
                or 0
            )
        )
        
        levels['estimated_loss_sl_usdt'] = round(
            loss_sl_usdt,
            4
        )
        
        
        # ==============================================================
        # BENEFICIO NETO MÍNIMO
        # ==============================================================
        target_net_profit = float(
            FUTURES_RISK_CONFIG.get(
                'target_net_profit_usdt',
                0.50
            )
        )
        
        if (
            net_profit_tp_usdt
            < target_net_profit
        ):
            print(
                f"   ⚠️ FUTUROS ANALYSIS_ONLY: "
                f"beneficio neto estimado "
                f"${net_profit_tp_usdt:.4f} "
                f"< objetivo "
                f"${target_net_profit:.4f}"
            )

            levels['leverage'] = int(
                optimal_leverage
            )

            levels['execution_safety'] = round(
                safety_score,
                1
            )

            levels['execution_safety_label'] = (
                safety_label
            )

            return self._mark_levels_non_executable(
                levels,
                (
                    f"Beneficio neto estimado "
                    f"${net_profit_tp_usdt:.4f} "
                    f"< objetivo "
                    f"${target_net_profit:.4f}"
                ),
                recommended_leverage=optimal_leverage
            )
        # ==============================================================
        # OPERACIÓN APROBADA
        # ==============================================================
        # Si llegamos hasta aquí:
        #
        #   ✅ ENTRY válido
        #   ✅ SL válido
        #   ✅ TP válido
        #   ✅ Execution Safety suficiente
        #   ✅ leverage económicamente viable
        #   ✅ ROI suficiente
        #   ✅ beneficio neto suficiente
        #
        # Debemos devolver los niveles calculados.
        # ==============================================================

        levels['leverage'] = int(
            optimal_leverage
        )

        levels['execution_safety'] = round(
            safety_score,
            1
        )

        levels['execution_safety_label'] = (
            safety_label
        )

        levels['risk_control'] = {
            'max_loss_pct_margin': float(
                FUTURES_RISK_CONFIG[
                    'max_loss_pct_margin'
                ]
            ),
            'leverage': int(
                optimal_leverage
            ),
            
            'leverage_min_tf': int(
                LEVERAGE_RANGES[
                    timeframe
                ][0]
            ),
            
            'leverage_max_tf': int(
                LEVERAGE_RANGES[
                    timeframe
                ][1]
            ),
            
            'leverage_policy': (
                f"{LEVERAGE_RANGES[timeframe][0]}x-"
                f"{LEVERAGE_RANGES[timeframe][1]}x"
            ),
            'margin_usdt': float(
                FUTURES_RISK_CONFIG[
                    'default_margin_usdt'
                ]
            ),
            'estimated_loss_sl_usdt': round(
                loss_sl_usdt,
                4
            ),
            'estimated_cost_usdt': round(
                estimated_cost_usdt,
                4
            ),
            'net_profit_tp_usdt': round(
                net_profit_tp_usdt,
                4
            )
        }
        # ==============================================================
        # VALIDACIÓN FINAL DEL LEVERAGE
        # ==============================================================
        if not _leverage_in_valid_range(
            int(optimal_leverage),
            timeframe
        ):
        
            min_tf, max_tf = LEVERAGE_RANGES.get(
                timeframe,
                (1, 10)
            )
        
            return self._mark_levels_non_executable(
                levels,
                (
                    f"Leverage recomendado "
                    f"{optimal_leverage}x "
                    f"fuera del rango operativo "
                    f"{min_tf}x-{max_tf}x "
                    f"para {timeframe}"
                ),
                recommended_leverage=optimal_leverage
            )
        return levels    
    # ========================================================================
    # ANÁLISIS COMPLETO DE FUTUROS
    # ========================================================================
    def _prepare_closed_candle_analysis_data(
        self,
        symbol: str,
        timeframe: str
    ) -> Dict:
        """
        Separa la información en dos mundos:

        - closed_df: velas completamente cerradas para generar el setup.
        - live_price: último precio OHLCV disponible para seguimiento.

        No asume ciegamente que KuCoin siempre incluye una vela abierta.
        Comprueba el tiempo de apertura de la última fila y la duración del TF.
        """
        try:
            import pandas as pd

            full_df = self.get_kucoin_data(
                symbol,
                timeframe
            )

            if full_df is None or len(full_df) < 3:
                return {
                    'success': False,
                    'error': 'Datos insuficientes para separar vela cerrada'
                }

            tf_seconds = FUTURES_TIMEFRAME_SECONDS.get(
                timeframe
            )

            if not tf_seconds:
                return {
                    'success': False,
                    'error': f'Temporalidad sin duración definida: {timeframe}'
                }

            parsed_times = pd.to_datetime(
                full_df['time'],
                utc=True,
                errors='coerce'
            )

            last_open = parsed_times.iloc[-1]

            if pd.isna(last_open):
                return {
                    'success': False,
                    'error': 'Timestamp inválido en la última vela'
                }

            now_utc = pd.Timestamp.now(tz='UTC')
            candle_duration = pd.Timedelta(seconds=tf_seconds)

            last_row_is_closed = (
                last_open + candle_duration
                <= now_utc
            )

            if last_row_is_closed:
                closed_df = full_df.copy()
                open_candle_present = False
            else:
                closed_df = full_df.iloc[:-1].copy()
                open_candle_present = True

            closed_df = closed_df.reset_index(drop=True)

            if len(closed_df) < 2:
                return {
                    'success': False,
                    'error': 'No existen suficientes velas cerradas'
                }

            source_open = pd.to_datetime(
                closed_df['time'].iloc[-1],
                utc=True,
                errors='coerce'
            )

            if pd.isna(source_open):
                return {
                    'success': False,
                    'error': 'Timestamp inválido en la vela fuente'
                }

            source_close = source_open + candle_duration

            return {
                'success': True,
                'closed_df': closed_df,
                'source_candle_timestamp': source_open.isoformat(),
                'source_candle_close_timestamp': source_close.isoformat(),
                'live_price': float(full_df['close'].iloc[-1]),
                'live_candle_timestamp': last_open.isoformat(),
                'open_candle_present': bool(open_candle_present),
            }

        except Exception as e:
            logger.error(
                f'Error preparando vela cerrada {symbol} {timeframe}: {e}'
            )

            return {
                'success': False,
                'error': str(e)
            }   
            
    def analyze_futures_market(self, symbol: str, timeframe: str, 
                                btc_analysis: Optional[Dict] = None,
                                closed_candle_only: bool = False) -> Dict:
        """
        Análisis completo para futuros.
        
        Wrapper de analyze_full_market del padre pero:
        - Valida símbolo y TF de futuros
        - Fuerza system_type='futures' al registrar en Supabase
        - Adapta la correlación (no usa PAXG)
        - Traduce COMPRA/VENTA a LONG/SHORT en la decisión final

        closed_candle_only=False conserva el comportamiento anterior.
        closed_candle_only=True excluye la vela abierta de todos los
        indicadores, traders, votación y niveles.
        """
        # Validar
        if symbol not in FUTURES_SYMBOLS:
            return {
                'success': False,
                'error': f'Símbolo {symbol} no permitido en futuros. Válidos: {list(FUTURES_SYMBOLS.keys())}',
                'symbol': symbol,
                'timeframe': timeframe
            }
        
        if timeframe not in FUTURES_TIMEFRAMES:
            return {
                'success': False,
                'error': f'Timeframe {timeframe} no permitido en futuros. Válidos: {list(FUTURES_TIMEFRAMES.keys())}',
                'symbol': symbol,
                'timeframe': timeframe
            }
        
        print(f"\n{'='*60}")
        print(f"🚀 FUTUROS: Analizando {symbol} {timeframe}")
        print(f"{'='*60}")

        # Preparación opcional y retrocompatible. app.py activará este modo
        # en un commit posterior; mientras tanto el comportamiento no cambia.
        df_override = None
        closed_context = None

        if closed_candle_only:
            closed_context = self._prepare_closed_candle_analysis_data(
                symbol,
                timeframe
            )

            if not closed_context.get('success'):
                return {
                    'success': False,
                    'error': closed_context.get(
                        'error',
                        'No se pudo preparar la vela cerrada'
                    ),
                    'symbol': symbol,
                    'timeframe': timeframe
                }

            df_override = closed_context['closed_df']
        
        # Llamar al análisis del padre
        # NOTA: paxg_analysis y paxg_btc_analysis se pasan como None
        # (no aplica en futuros)
        # FLAG: evitar doble registro en Supabase (el padre registraría con
        # system_type='spot'. Aquí lo registramos después con 'futures').
        self._skip_supabase_register = True
        try:
            result = self.analyze_full_market(
                symbol=symbol,
                timeframe=timeframe,
                btc_analysis=btc_analysis,
                paxg_analysis=None,
                paxg_btc_analysis=None,
                df_override=df_override
            )
        finally:
            self._skip_supabase_register = False
        
        if not result or not result.get('success'):
            return result
        
        # ============ TRADUCIR ACCIÓN ============
        decision = result.get('decision', {})
        original_action = decision.get('action', 'NO_OPERAR')
        
        translated_action = original_action
        if original_action == 'COMPRA_SPOT':
            translated_action = 'LONG'
        elif original_action == 'VENTA_SPOT':
            translated_action = 'SHORT'
        
        decision['action'] = translated_action
        decision['original_action'] = original_action  # Guardar por si acaso
        result['decision'] = decision
        
        # ============ MARCAR COMO FUTUROS ============
        result['system_type'] = 'futures'
        result['is_futures'] = True

        # ============ IDENTIDAD DE LA VELA FUENTE ============
        # Solo se publica cuando el caller pidió explícitamente analizar
        # velas cerradas. ReviewTrader ya entiende este campo y mantiene
        # fallback para resultados antiguos.
        if closed_context:
            import hashlib

            source_ts = closed_context['source_candle_timestamp']
            signal_seed = (
                f"{symbol}|{timeframe}|{translated_action}|"
                f"{source_ts}|closed_v1"
            )

            result['signal_id'] = hashlib.sha256(
                signal_seed.encode('utf-8')
            ).hexdigest()[:24]
            result['analysis_mode'] = 'CLOSED_CANDLE'
            result['analysis_version'] = 'closed_v1'
            result['source_candle_timestamp'] = source_ts
            result['source_candle_close_timestamp'] = closed_context[
                'source_candle_close_timestamp'
            ]
            result['source_candle_closed'] = True
            result['analysis_price'] = float(
                result.get('current_price', 0) or 0
            )
            result['live_price'] = closed_context['live_price']
            result['live_candle_timestamp'] = closed_context[
                'live_candle_timestamp'
            ]
            result['open_candle_present'] = closed_context[
                'open_candle_present'
            ]
        
        # ============ ADAPTAR JUSTIFICACIÓN AL CONTEXTO DE FUTUROS ============
        # El mensaje se generó con la acción original (COMPRA_SPOT / VENTA_SPOT)
        # usando las plantillas spot. Para futuros necesitamos:
        #   1. Reemplazar títulos: "COMPRA SPOT DE X" → "LONG FUTURES DE X"
        #   2. Reemplazar recomendaciones incorrectas de par-ratio (SOL/XRP/ADA/ETH
        #      caían en la rama "ratio PAXG/BTC" del selector spot)
        try:
            msg = result.get('message', '') or ''
            if msg:
                symbol_name_map = {
                    'BTC-USDT': 'BTC/USDT', 'ETH-USDT': 'ETH/USDT',
                    'SOL-USDT': 'SOL/USDT', 'XRP-USDT': 'XRP/USDT',
                    'ADA-USDT': 'ADA/USDT',
                }
                pretty_name = symbol_name_map.get(symbol, symbol.replace('-', '/'))
                
                if original_action == 'COMPRA_SPOT':
                    # Título
                    msg = msg.replace(
                        f'🟢 COMPRA SPOT DE {pretty_name}',
                        f'📈 LONG FUTURES DE {pretty_name}'
                    )
                    # Fallback si el símbolo no tenía nombre mapeado
                    msg = msg.replace(
                        '🟢 COMPRA SPOT DE',
                        '📈 LONG FUTURES DE'
                    )

                    # También normalizar mensajes fallback.
                    msg = msg.replace(
                        'Recomendación: COMPRA_SPOT',
                        'Recomendación: LONG'
                    )

                    msg = msg.replace(
                        'Recomendación: COMPRA SPOT',
                        'Recomendación: LONG'
                    )

                    # Recomendaciones incorrectas: eliminar todas las variantes spot
                    # y reemplazar por una recomendación futures apropiada
                    for wrong in (
                        'Se recomienda COMPRA del ratio PAXG/BTC.',
                        'Se recomienda COMPRA SPOT de BTC/USDT.',
                        'Se recomienda COMPRA SPOT de Bitcoin.',
                        'Se recomienda COMPRA SPOT de Bitcoin',
                        'Se aconseja COMPRA SPOT de PAXG.',
                    ):
                        msg = msg.replace(
                            wrong,
                            f'Se recomienda LONG en futuros de {pretty_name}.'
                        )
                elif original_action == 'VENTA_SPOT':
                    msg = msg.replace(
                        f'🔴 VENTA SPOT DE {pretty_name}',
                        f'📉 SHORT FUTURES DE {pretty_name}'
                    )
                    msg = msg.replace(
                        '🔴 VENTA SPOT DE',
                        '📉 SHORT FUTURES DE'
                    )

                    msg = msg.replace(
                        'Recomendación: VENTA_SPOT',
                        'Recomendación: SHORT'
                    )

                    msg = msg.replace(
                        'Recomendación: VENTA SPOT',
                        'Recomendación: SHORT'
                    )

                    for wrong in (
                        'Se aconseja VENTA del ratio PAXG/BTC.',
                        'Se recomienda VENTA SPOT de BTC/USDT.',
                        'Se recomienda VENTA SPOT de Bitcoin.',
                        'Se recomienda VENTA SPOT de Bitcoin',
                        'Se sugiere VENTA SPOT de PAXG.',
                    ):
                        msg = msg.replace(
                            wrong,
                            f'Se recomienda SHORT en futuros de {pretty_name}.'
                        )
                
                result['message'] = msg
        except Exception as _msg_err:
            logger.debug(f"No se pudo adaptar mensaje a futures: {_msg_err}")
        
        # ============ RECALCULAR NIVELES CON LÓGICA DE FUTUROS ============
        # (Ya se hizo dentro de analyze_full_market → calculate_entry_levels overrideado)
        # Pero verificamos que la traducción sea consistente
        levels = result.get('levels', {})
        
        # ============ REGISTRAR EN REVIEWTRADER (si está disponible) ============
        # IMPORTANTE: solo registrar si el análisis fue FRESCO (no vino del caché).
        # Antes se registraba SIEMPRE, causando 5-10 duplicados idénticos por
        # cada TF cada vez que el warm-up paralelo tocaba el mismo par.
        if result.get('_from_cache'):
            # Análisis servido desde caché → la señal ya fue registrada antes.
            pass
        else:
            try:
                from review_trader import review_trader
                if review_trader.db.enabled:
                    review_trader.register_signal(result, system_type='futures')
                    print(f"   📝 Señal registrada en ReviewTrader (futures)")
            except Exception as e:
                logger.debug(f"ReviewTrader no disponible: {e}")
        
        return result
    
    # ========================================================================
    # ANÁLISIS DE CORRELACIÓN PARA FUTUROS (BTC + alts, sin PAXG)
    # ========================================================================
    
    def analyze_futures_correlation(self, results: Dict) -> Dict:
        """
        Calcula la correlación entre BTC y las alts para futuros.
        Reemplaza la correlación BTC/PAXG del sistema principal.
        
        results: dict con las análisis por símbolo, ej:
            {'BTC-USDT': {...}, 'ETH-USDT': {...}, 'SOL-USDT': {...}, ...}
        """
        try:
            btc = results.get('BTC-USDT', {})
            btc_trend = btc.get('trend', {})
            btc_direction = btc_trend.get('direction', 'neutral')
            btc_adx = btc_trend.get('adx', 0)
            
            # Alts
            alts = ['ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT']
            alt_directions = {}
            for alt in alts:
                alt_data = results.get(alt, {})
                alt_trend = alt_data.get('trend', {})
                alt_directions[alt] = {
                    'direction': alt_trend.get('direction', 'neutral'),
                    'adx': alt_trend.get('adx', 0)
                }
            
            # Contar cuántas alts van en la misma dirección que BTC
            aligned_with_btc = 0
            opposed_to_btc = 0
            
            for alt, data in alt_directions.items():
                if data['direction'] == btc_direction and data['direction'] != 'neutral':
                    aligned_with_btc += 1
                elif data['direction'] != 'neutral' and data['direction'] != btc_direction:
                    opposed_to_btc += 1
            
            # Interpretación
            if btc_direction == 'bullish' and aligned_with_btc >= 3:
                rotation = 'BULLISH_MARKET'
                description = 'BTC alcista arrastra alts al alza'
            elif btc_direction == 'bearish' and aligned_with_btc >= 3:
                rotation = 'BEARISH_MARKET'
                description = 'BTC bajista arrastra alts a la baja'
            elif btc_direction == 'bullish' and opposed_to_btc >= 2:
                rotation = 'ALTS_DIVERGE'
                description = 'BTC alcista pero alts muestran debilidad'
            elif btc_direction == 'bearish' and opposed_to_btc >= 2:
                rotation = 'ALTS_STRONG'
                description = 'BTC bajista pero alts se mantienen fuertes'
            else:
                rotation = 'MIXED'
                description = 'Mercado sin dirección clara entre BTC y alts'
            
            return {
                'rotation_signal': rotation,
                'description': description,
                'btc_direction': btc_direction,
                'btc_adx': btc_adx,
                'aligned_with_btc': aligned_with_btc,
                'opposed_to_btc': opposed_to_btc,
                'alt_directions': alt_directions
            }
            
        except Exception as e:
            logger.error(f"Error en analyze_futures_correlation: {e}")
            return {
                'rotation_signal': 'NEUTRAL',
                'description': 'Error en cálculo',
                'btc_direction': 'neutral'
            }
    
    # ========================================================================
    # ANÁLISIS DE TODOS LOS PARES DE FUTUROS
    # ========================================================================
    
    def analyze_all_futures_pairs(self, timeframe: str) -> Dict:
        """
        Analiza los 5 pares de futuros en la temporalidad dada.
        Retorna todos los análisis + correlación.
        """
        results = {}
        
        # 1. Analizar BTC primero (base para correlación)
        print(f"\n🚀 FUTUROS: Analizando 5 pares en {timeframe}")
        btc_result = self.analyze_futures_market('BTC-USDT', timeframe)
        results['BTC-USDT'] = btc_result
        
        # 2. Analizar los demás pares con contexto de BTC
        for symbol in ['ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'ADA-USDT']:
            try:
                results[symbol] = self.analyze_futures_market(
                    symbol, timeframe, 
                    btc_analysis=btc_result if btc_result.get('success') else None
                )
            except Exception as e:
                logger.error(f"Error analizando {symbol}: {e}")
                results[symbol] = {
                    'success': False,
                    'error': str(e),
                    'symbol': symbol,
                    'timeframe': timeframe
                }
        
        # 3. Calcular correlación intra-cripto
        correlation = self.analyze_futures_correlation(results)
        results['_correlation'] = correlation
        
        return results


# ============================================================================
# INSTANCIA GLOBAL
# ============================================================================

# Otras partes del sistema importan esta instancia:
# from futures_system import futures_system
futures_system = FuturesAnalysis()
print("✅ FUTURES SYSTEM inicializado y listo")
