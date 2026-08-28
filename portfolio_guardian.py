# portfolio_guardian.py
# Trader Guardián de Portafolio (TGP) - v1.0
# Módulo INDEPENDIENTE del sistema de 9 traders.
# No modifica ni interviene en las señales del sistema principal.
# Genera recomendaciones propias basadas en el portafolio del usuario,
# el estado del mercado, y la señal del sistema.
#
# OBJETIVO: Acumular satoshis, USDT y PAXG como bola de nieve.

import logging
from datetime import datetime

logger = logging.getLogger('TGP')


class PortfolioGuardian:
    """
    Asesor de portafolio independiente.
    Recibe el portafolio del usuario, los precios actuales, y el análisis
    completo del sistema. Devuelve una recomendación propia con tamaño
    de operación, razón detallada, y proyección de portafolio post-operación.
    """

    # Porcentajes objetivo para modo "acumular satoshis" (meta por defecto)
    # BTC lidera, PAXG como refugio, USDT como munición
    TARGET_PCTS = {
        'BTC':  0.45,   # 45% BTC (motor de crecimiento en satoshis)
        'PAXG': 0.35,   # 35% PAXG (refugio y oportunidad de cambio)
        'USDT': 0.20,   # 20% USDT (efectivo para oportunidades)
    }

    # Límites de concentración (alarmas)
    MAX_PCT = 0.75    # Nunca más del 75% en un solo activo
    MIN_PCT = 0.05    # Nunca menos del 5% en un activo (salvo USDT que puede ser 0)

    # Tamaños de operación
    MIN_TRADE_PCT = 0.08   # Mínimo 8% del activo fuente
    MAX_TRADE_PCT = 0.35   # Máximo 35% del activo fuente (nunca quedarse sin nada)

    def __init__(self):
        self.bolivia_tz = __import__('pytz').timezone('America/La_Paz') if 'pytz' in __import__('sys').modules else None

    # ========================================================================
    # ANÁLISIS PRINCIPAL
    # ========================================================================

    def analyze(self, user, portfolio, prices, system_analysis):
        """
        Analiza el portafolio y genera recomendación del TGP.

        Args:
            user: str - nombre del usuario (Willer, Danilo, etc.)
            portfolio: dict - {'BTC': 0.00158, 'PAXG': 0.23673, 'USDT': 0}
            prices: dict - {'BTC-USDT': 78800.0, 'PAXG-USDT': 2650.0}
            system_analysis: dict - resultado completo de analyze_full_market

        Returns:
            dict - recomendación completa del TGP
        """
        try:
            # --- 1. VALORAR PORTAFOLIO ---
            valuation = self._value_portfolio(portfolio, prices)
            total = valuation['total']

            # ------------------------------------------------------------------
            # VALIDACIÓN REAL DEL PORTAFOLIO
            # ------------------------------------------------------------------
            # NO confundir:
            #   - portfolio realmente vacío
            #   - portfolio con activos pero precios temporalmente no disponibles
            #
            # Un usuario puede tener BTC/PAXG > $10 aunque el precio no haya
            # llegado correctamente desde el frontend.
            # ------------------------------------------------------------------
            
            btc_amt = float(portfolio.get('BTC', 0) or 0)
            paxg_amt = float(portfolio.get('PAXG', 0) or 0)
            usdt_amt = float(portfolio.get('USDT', 0) or 0)
            
            has_assets = btc_amt > 0 or paxg_amt > 0 or usdt_amt > 0
            
            # Si verdaderamente no posee nada
            if not has_assets:
                return self._build_response(
                    action='HOLD',
                    reason='Portafolio realmente vacío. No hay activos disponibles para gestionar.',
                    confidence=100,
                    portfolio=portfolio,
                    valuation=valuation
                )
            
            # Si hay activos pero la valoración es cero, NO decir que está vacío.
            # Es un problema de datos de precios que debe ser visible.
            if valuation['total'] <= 0:
                return self._build_response(
                    action='HOLD',
                    reason=(
                        'El portafolio contiene activos, pero no se pudieron obtener '
                        'precios válidos para valorarlo. No se ejecutará ninguna '
                        'recomendación hasta recuperar precios confiables.'
                    ),
                    confidence=100,
                    portfolio=portfolio,
                    valuation=valuation
                )
            
            # Portafolios muy pequeños pueden no ser operables por comisiones/
            # mínimos de exchange, pero siguen siendo un portafolio real.
            if valuation['total'] <= 10:
                return self._build_response(
                    action='HOLD',
                    reason=(
                        f'Portafolio operativo muy pequeño (${valuation["total"]:.2f}). '
                        'Se conserva el capital y se evita recomendar operaciones '
                        'que puedan ser ineficientes por comisiones o mínimos de mercado.'
                    ),
                    confidence=90,
                    portfolio=portfolio,
                    valuation=valuation
                )

            pct_btc  = valuation['pct_btc']
            pct_paxg = valuation['pct_paxg']
            pct_usdt = valuation['pct_usdt']

            # --- 2. ESTADO DEL PORTAFOLIO ---
            state = self._classify_state(pct_btc, pct_paxg, pct_usdt)

            # --- 3. EXTRAER SEÑAL DEL SISTEMA ---
            sys_decision = system_analysis.get('decision', {})
            sys_action = sys_decision.get('action', 'NO_OPERAR')
            sys_confidence = float(sys_decision.get('confidence', 0))

            # --- 4. EXTRAER MACRO / RATIO ---
            correlation = system_analysis.get('correlation', {})
            rotation_signal = correlation.get('rotation_signal', 'NEUTRAL')
            macro_action = correlation.get('symbol_recommendation', {}).get('action', 'NEUTRAL')

            # --- 5. FAVORABILIDAD DEL RATIO ---
            ratio_fav = self._get_ratio_favorability(rotation_signal)

            # --- 6. GENERAR RECOMENDACIÓN ---
            rec = self._generate_recommendation(
                state=state,
                pct_btc=pct_btc, pct_paxg=pct_paxg, pct_usdt=pct_usdt,
                total=total,
                sys_action=sys_action,
                sys_confidence=sys_confidence,
                rotation_signal=rotation_signal,
                macro_action=macro_action,
                ratio_fav=ratio_fav,
                prices=prices,
                portfolio=portfolio
            )

            # --- 7. ENRIQUECER RESPUESTA ---
            rec['user'] = user
            rec['state'] = state
            rec['portfolio'] = portfolio
            rec['valuation'] = valuation
            rec['system_signal'] = {
                'action': sys_action,
                'confidence': sys_confidence
            }
            rec['macro'] = {
                'rotation_signal': rotation_signal,
                'symbol_recommendation': macro_action
            }
            rec['timestamp'] = datetime.now().isoformat()

            return rec

        except Exception as e:
            logger.error(f"TGP error: {e}")
            return self._build_response(
                action='HOLD',
                reason=f'Error interno del Guardián: {str(e)}',
                confidence=0,
                portfolio=portfolio,
                valuation=self._value_portfolio(portfolio, prices)
            )

    # ========================================================================
    # CAPA 1: VALORACIÓN
    # ========================================================================

    def _value_portfolio(self, portfolio, prices):
        """Convierte cantidades a valores en USDT y porcentajes."""
    
        prices = prices or {}
        portfolio = portfolio or {}
    
        # Precio actual
        btc_price = float(
            prices.get('BTC-USDT')
            or prices.get('BTC')
            or 0
        )
    
        paxg_price = float(
            prices.get('PAXG-USDT')
            or prices.get('PAXG')
            or 0
        )
    
        # Precio histórico guardado junto al portfolio.
        # Solo se utiliza como fallback cuando no hay precio actual.
        if btc_price <= 0:
            btc_price = float(
                portfolio.get('btc_price_at_update', 0) or 0
            )
    
        if paxg_price <= 0:
            paxg_price = float(
                portfolio.get('paxg_price_at_update', 0) or 0
            )
    
        btc_amt = float(portfolio.get('BTC', 0) or 0)
        paxg_amt = float(portfolio.get('PAXG', 0) or 0)
        usdt_amt = float(portfolio.get('USDT', 0) or 0)
    
        btc_value = btc_amt * btc_price
        paxg_value = paxg_amt * paxg_price
        total = btc_value + paxg_value + usdt_amt
    
        if total > 0:
            pct_btc  = btc_value / total
            pct_paxg = paxg_value / total
            pct_usdt = usdt_amt / total
        else:
            pct_btc = pct_paxg = pct_usdt = 0.0

        return {
            'btc_value': round(btc_value, 2),
            'paxg_value': round(paxg_value, 2),
            'usdt_value': round(usdt_amt, 2),
            'total': round(total, 2),
            'pct_btc': round(pct_btc, 4),
            'pct_paxg': round(pct_paxg, 4),
            'pct_usdt': round(pct_usdt, 4),
            'btc_price': btc_price,
            'paxg_price': paxg_price,
        }

    # ========================================================================
    # CAPA 2: ESTADO DEL PORTAFOLIO
    # ========================================================================

    def _classify_state(self, pct_btc, pct_paxg, pct_usdt):
        """Clasifica el portafolio en un estado para decidir la estrategia."""
        if pct_usdt >= 0.80:
            return 'ALL_CASH'
        if pct_usdt <= 0.05 and pct_btc <= 0.05 and pct_paxg <= 0.05:
            return 'EMPTY'
        if pct_btc >= self.MAX_PCT:
            return 'CONCENTRATED_BTC'
        if pct_paxg >= self.MAX_PCT:
            return 'CONCENTRATED_PAXG'
        if pct_usdt <= 0.05:
            return 'NO_CASH'
        if pct_btc <= self.MIN_PCT and pct_paxg <= self.MIN_PCT:
            return 'NO_CRYPTO'
        # Balanceado pero con desviaciones
        if abs(pct_btc - self.TARGET_PCTS['BTC']) <= 0.10 and \
           abs(pct_paxg - self.TARGET_PCTS['PAXG']) <= 0.10:
            return 'BALANCED'
        if pct_btc < self.TARGET_PCTS['BTC'] - 0.15:
            return 'LOW_BTC'
        if pct_paxg < self.TARGET_PCTS['PAXG'] - 0.15:
            return 'LOW_PAXG'
        if pct_usdt < self.TARGET_PCTS['USDT'] - 0.10:
            return 'LOW_USDT'
        return 'REBALANCE_NEEDED'

    # ========================================================================
    # CAPA 3: FAVORABILIDAD DEL RATIO (brújula PAXG/BTC)
    # ========================================================================

    def _get_ratio_favorability(self, rotation_signal):
        """
        Score de -1.0 a +1.0 indicando qué tan favorable es el entorno
        para cambios PAXG ↔ BTC.

        +1.0  = Ideal para cambiar PAXG → BTC (oro caro, BTC fuerte)
        -1.0  = Ideal para cambiar BTC → PAXG (oro barato, BTC débil)
         0.0  = Neutral
        """
        mapping = {
            'RISK_ON':               0.90,   # BTC fuerte → cambiar oro por BTC
            'BTC_STRONGER':          0.70,   # BTC más fuerte que oro
            'BTC_BULLISH':           0.50,   # BTC alcista solo
            'RATIO_BEARISH':         0.60,   # Ratio bajista = BTC gana vs oro
            'POSITIVE_CORRELATION':  0.10,   # Ambos suben, neutral
            'NEUTRAL':               0.00,   # Sin dirección
            'NEGATIVE_CORRELATION': -0.10,   # Ambos bajan, neutral
            'RATIO_BULLISH':        -0.60,   # Ratio alcista = oro gana vs BTC
            'PAXG_STRONGER':        -0.70,   # Oro más fuerte que BTC
            'RISK_OFF':             -0.90,   # Oro fuerte → cambiar BTC por oro
        }
        return mapping.get(rotation_signal, 0.0)

    # ========================================================================
    # CAPA 4: MOTOR DE DECISIÓN
    # ========================================================================

    def _generate_recommendation(self, state, pct_btc, pct_paxg, pct_usdt, total,
                                  sys_action, sys_confidence, rotation_signal,
                                  macro_action, ratio_fav, prices, portfolio):
        """
        El cerebro del TGP. Aquí se toman las decisiones.
        """
        # ------------------------------------------------------------------
        # A. PORTAFOLIO VACÍO / EFECTIVO TOTAL
        # ------------------------------------------------------------------
        if state == 'ALL_CASH':
            return self._handle_all_cash(pct_usdt, sys_action, sys_confidence, prices, portfolio)

        if state == 'EMPTY':
            return self._build_response(
                action='HOLD',
                reason='Portafolio vacío. Depositá fondos para empezar a operar.',
                confidence=100,
                portfolio=portfolio,
                valuation=self._value_portfolio(portfolio, prices)
            )

        # ------------------------------------------------------------------
        # B. SOBRECONCENTRACIÓN (más del 75% en un activo)
        # ------------------------------------------------------------------
        if state == 'CONCENTRATED_BTC':
            return self._handle_concentrated_btc(pct_btc, sys_action, sys_confidence,
                                                  ratio_fav, prices, portfolio)

        if state == 'CONCENTRATED_PAXG':
            return self._handle_concentrated_paxg(pct_paxg, sys_action, sys_confidence,
                                                   ratio_fav, prices, portfolio)

        # ------------------------------------------------------------------
        # C. SIN EFECTIVO (no se puede comprar, solo cambiar)
        # ------------------------------------------------------------------
        if state == 'NO_CASH':
            return self._handle_no_cash(pct_btc, pct_paxg, sys_action, sys_confidence,
                                         ratio_fav, prices, portfolio)

        # ------------------------------------------------------------------
        # D. BALANCEADO / REBALANCEO SUAVE
        # ------------------------------------------------------------------
        if state in ('BALANCED', 'REBALANCE_NEEDED', 'LOW_BTC', 'LOW_PAXG', 'LOW_USDT', 'NO_CRYPTO'):
            return self._handle_balanced(state, pct_btc, pct_paxg, pct_usdt,
                                          sys_action, sys_confidence, ratio_fav,
                                          prices, portfolio)

        # Fallback
        return self._build_response(
            action='HOLD',
            reason='Estado no reconocido. Manteniendo posición por seguridad.',
            confidence=50,
            portfolio=portfolio,
            valuation=self._value_portfolio(portfolio, prices)
        )

    # ========================================================================
    # MANEJADORES POR ESTADO
    # ========================================================================

    def _handle_all_cash(self, pct_usdt, sys_action, sys_confidence, prices, portfolio):
        """100% o gran parte en USDT. Necesitamos entrar al mercado."""
        valuation = self._value_portfolio(portfolio, prices)
        usdt_available = valuation['usdt_value']

        # Si la señal del sistema es fuerte de compra BTC
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'BTC' in str(sys_action) and sys_confidence >= 70:
            size = self._calc_trade_size('USDT', sys_confidence, pct_usdt, 1.0, 0.5)
            amt_usd = usdt_available * size
            btc_price = valuation['btc_price']
            btc_to_buy = amt_usd / btc_price if btc_price > 0 else 0
            return self._build_response(
                action='BUY_BTC',
                reason=f'Todo en efectivo ({pct_usdt*100:.0f}% USDT). Señal de COMPRA BTC fuerte ({sys_confidence}%). '
                       f'Entrada agresiva recomendada para poner el capital a trabajar.',
                confidence=min(95, sys_confidence + 10),
                trade_size_pct=size,
                amount_usd=amt_usd,
                amount_crypto=btc_to_buy,
                source_asset='USDT',
                target_asset='BTC',
                portfolio=portfolio,
                valuation=valuation
            )

        # Si la señal es compra PAXG
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'PAXG' in str(sys_action) and sys_confidence >= 70:
            size = self._calc_trade_size('USDT', sys_confidence, pct_usdt, 1.0, 0.5)
            amt_usd = usdt_available * size
            paxg_price = valuation['paxg_price']
            paxg_to_buy = amt_usd / paxg_price if paxg_price > 0 else 0
            return self._build_response(
                action='BUY_PAXG',
                reason=f'Todo en efectivo. Señal de COMPRA PAXG fuerte ({sys_confidence}%). '
                       f'Diversificación inicial en oro como refugio.',
                confidence=min(95, sys_confidence + 5),
                trade_size_pct=size,
                amount_usd=amt_usd,
                amount_crypto=paxg_to_buy,
                source_asset='USDT',
                target_asset='PAXG',
                portfolio=portfolio,
                valuation=valuation
            )

        # Señal débil o no operar
        if sys_confidence < 60:
            return self._build_response(
                action='HOLD',
                reason=f'Todo en efectivo, pero la señal del sistema es débil ({sys_confidence}%). '
                       f'Esperá una entrada > 70% para deployar capital. La paciencia es rentable.',
                confidence=80,
                portfolio=portfolio,
                valuation=valuation
            )

        # Señal neutra pero sin dirección clara
        return self._build_response(
            action='HOLD',
            reason='Todo en efectivo. El sistema no detecta oportunidad clara. '
                   'Mantener USDT es posición válida hasta que aparezca zona de compra fuerte.',
            confidence=70,
            portfolio=portfolio,
            valuation=valuation
        )

    def _handle_concentrated_btc(self, pct_btc, sys_action, sys_confidence, ratio_fav, prices, portfolio):
        """Más del 75% en BTC. Necesitamos reducir riesgo o cambiar a oro."""
        valuation = self._value_portfolio(portfolio, prices)
        btc_available = portfolio.get('BTC', 0)

        # Si el sistema dice VENTA BTC → alineado con necesidad
        if sys_action in ('VENTA_SPOT', 'SHORT') and sys_confidence >= 60:
            size = self._calc_trade_size('BTC', sys_confidence, pct_btc, self.TARGET_PCTS['BTC'], abs(ratio_fav))
            # Preferir cambio a PAXG si RISK_OFF o ratio favorece oro
            if ratio_fav <= -0.5:
                amt_btc = btc_available * size
                btc_price = valuation['btc_price']
                paxg_price = valuation['paxg_price']
                usd_value = amt_btc * btc_price
                paxg_to_get = usd_value / paxg_price if paxg_price > 0 else 0
                return self._build_response(
                    action='SWAP_BTC_TO_PAXG',
                    reason=f'Sobrepeso crítico en BTC ({pct_btc*100:.1f}%). Sistema dice VENTA. '
                           f'Además, Macro indica fortaleza del oro (ratio favorece PAXG). '
                           f'Cambio estratégico a oro para protección y rebalanceo.',
                    confidence=min(95, sys_confidence + 15),
                    trade_size_pct=size,
                    amount_crypto=amt_btc,
                    amount_usd=usd_value,
                    source_asset='BTC',
                    target_asset='PAXG',
                    portfolio=portfolio,
                    valuation=valuation
                )
            else:
                # Vender a USDT
                amt_btc = btc_available * size
                btc_price = valuation['btc_price']
                usd_value = amt_btc * btc_price
                return self._build_response(
                    action='SELL_BTC',
                    reason=f'Sobrepeso crítico en BTC ({pct_btc*100:.1f}%). Sistema dice VENTA. '
                           f'Vender a USDT genera munición para futuras entradas.',
                    confidence=min(90, sys_confidence + 10),
                    trade_size_pct=size,
                    amount_crypto=amt_btc,
                    amount_usd=usd_value,
                    source_asset='BTC',
                    target_asset='USDT',
                    portfolio=portfolio,
                    valuation=valuation
                )

        # Si no hay señal de venta pero el ratio favorece fuertemente el oro
        if ratio_fav <= -0.7 and sys_confidence < 50:
            size = self._calc_trade_size('BTC', 70, pct_btc, self.TARGET_PCTS['BTC'], 0.8)
            amt_btc = btc_available * size
            btc_price = valuation['btc_price']
            paxg_price = valuation['paxg_price']
            usd_value = amt_btc * btc_price
            paxg_to_get = usd_value / paxg_price if paxg_price > 0 else 0
            return self._build_response(
                action='SWAP_BTC_TO_PAXG',
                reason=f'Sobrepeso en BTC ({pct_btc*100:.1f}%). Aunque el sistema no vende, '
                       f'el Macro detecta RISK_OFF fuerte (oro barato en satoshis, ratio muy favorable). '
                       f'Cambio estratégico preventivo para proteger ganancias.',
                confidence=75,
                trade_size_pct=size,
                amount_crypto=amt_btc,
                amount_usd=usd_value,
                source_asset='BTC',
                target_asset='PAXG',
                portfolio=portfolio,
                valuation=valuation
            )

        # Si el sistema dice COMPRA BTC pero ya estamos sobreconcentrados
        if sys_action in ('COMPRA_SPOT', 'LONG') and sys_confidence > 50:
            return self._build_response(
                action='HOLD',
                reason=f'Sistema dice COMPRA BTC ({sys_confidence}%), pero tenés {pct_btc*100:.1f}% en BTC. '
                       f'Comprar más sería concentrar riesgo excesivo. El Guardián VETA la compra. '
                       f'Considerá vender una parte si el sistema da señal de venta.',
                confidence=85,
                portfolio=portfolio,
                valuation=valuation,
                veto=True
            )

        # Default: esperar señal de venta o cambio
        return self._build_response(
            action='HOLD',
            reason=f'Sobrepeso en BTC ({pct_btc*100:.1f}%). El Guardián está atento. '
                   f'Esperando señal de venta o cambio a oro para rebalancear. No hagas nada por ahora.',
            confidence=60,
            portfolio=portfolio,
            valuation=valuation
        )

    def _handle_concentrated_paxg(self, pct_paxg, sys_action, sys_confidence, ratio_fav, prices, portfolio):
        """Más del 75% en PAXG. Tu caso actual (Willer)."""
        valuation = self._value_portfolio(portfolio, prices)
        paxg_available = portfolio.get('PAXG', 0)

        # CASO 1: Sistema dice COMPRA BTC + Macro favorable a BTC + ratio favorece cambio
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'BTC' in str(sys_action) and sys_confidence >= 60:
            if ratio_fav >= 0.3:
                size = self._calc_trade_size('PAXG', sys_confidence, pct_paxg, self.TARGET_PCTS['PAXG'], ratio_fav)
                amt_paxg = paxg_available * size
                paxg_price = valuation['paxg_price']
                btc_price = valuation['btc_price']
                usd_value = amt_paxg * paxg_price
                btc_to_get = usd_value / btc_price if btc_price > 0 else 0
                return self._build_response(
                    action='SWAP_PAXG_TO_BTC',
                    reason=f'Concentrado en oro ({pct_paxg*100:.1f}%). Sistema dice COMPRA BTC ({sys_confidence}%). '
                           f'Macro alineado (ratio favorable para cambio). '
                           f'Cambio estratégico de oro a BTC: desconcentrás riesgo y entrás en zona fuerte.',
                    confidence=min(95, sys_confidence + 10),
                    trade_size_pct=size,
                    amount_crypto=amt_paxg,
                    amount_usd=usd_value,
                    source_asset='PAXG',
                    target_asset='BTC',
                    portfolio=portfolio,
                    valuation=valuation
                )
            else:
                # Ratio no favorece el cambio → vender PAXG a USDT primero
                size = self._calc_trade_size('PAXG', sys_confidence, pct_paxg, self.TARGET_PCTS['PAXG'], 0.5)
                amt_paxg = paxg_available * size
                paxg_price = valuation['paxg_price']
                usd_value = amt_paxg * paxg_price
                return self._build_response(
                    action='SELL_PAXG',
                    reason=f'Concentrado en oro ({pct_paxg*100:.1f}%). Sistema dice COMPRA BTC, '
                           f'pero el ratio NO favorece cambiar oro por BTC ahora (oro barato en satoshis). '
                           f'Vender una parte del oro a USDT genera efectivo para la compra de BTC '
                           f'cuando el ratio mejore o aparezca mejor entrada.',
                    confidence=min(85, sys_confidence),
                    trade_size_pct=size,
                    amount_crypto=amt_paxg,
                    amount_usd=usd_value,
                    source_asset='PAXG',
                    target_asset='USDT',
                    portfolio=portfolio,
                    valuation=valuation
                )

        # CASO 2: Sistema dice VENTA PAXG → alineado con rebalanceo
        if sys_action in ('VENTA_SPOT', 'SHORT') and 'PAXG' in str(sys_action) and sys_confidence >= 60:
            size = self._calc_trade_size('PAXG', sys_confidence, pct_paxg, self.TARGET_PCTS['PAXG'], 0.5)
            amt_paxg = paxg_available * size
            paxg_price = valuation['paxg_price']
            usd_value = amt_paxg * paxg_price
            return self._build_response(
                action='SELL_PAXG',
                reason=f'Concentrado en oro ({pct_paxg*100:.1f}%). Sistema dice VENTA PAXG ({sys_confidence}%). '
                       f'Vender a USDT genera liquidez y reduce concentración.',
                confidence=min(90, sys_confidence + 10),
                trade_size_pct=size,
                amount_crypto=amt_paxg,
                amount_usd=usd_value,
                source_asset='PAXG',
                target_asset='USDT',
                portfolio=portfolio,
                valuation=valuation
            )

        # CASO 3: No hay señal del sistema, pero Macro dice RISK_ON fuerte + ratio favorable
        if ratio_fav >= 0.6 and sys_confidence < 50:
            size = self._calc_trade_size('PAXG', 70, pct_paxg, self.TARGET_PCTS['PAXG'], ratio_fav)
            amt_paxg = paxg_available * size
            paxg_price = valuation['paxg_price']
            btc_price = valuation['btc_price']
            usd_value = amt_paxg * paxg_price
            btc_to_get = usd_value / btc_price if btc_price > 0 else 0
            return self._build_response(
                action='SWAP_PAXG_TO_BTC',
                reason=f'Concentrado en oro ({pct_paxg*100:.1f}%). Aunque el sistema no da señal clara, '
                       f'el Macro detecta RISK_ON fuerte y el ratio favorece cambiar oro por BTC. '
                       f'El Guardián genera señal propia de cambio estratégico para aprovechar el ciclo. '
                       f'Esto evita que te quedes fuera de la suba de BTC como pasó antes.',
                confidence=75,
                trade_size_pct=size,
                amount_crypto=amt_paxg,
                amount_usd=usd_value,
                source_asset='PAXG',
                target_asset='BTC',
                portfolio=portfolio,
                valuation=valuation
            )

        # CASO 4: Sistema dice COMPRA PAXG pero ya estamos sobreconcentrados
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'PAXG' in str(sys_action):
            return self._build_response(
                action='HOLD',
                reason=f'Sistema dice COMPRA PAXG ({sys_confidence}%), pero tenés {pct_paxg*100:.1f}% en oro. '
                       f'Comprar más oro concentraría demasiado el riesgo en un solo activo. '
                       f'El Guardián VETA la compra. Esperá una señal de cambio o venta.',
                confidence=85,
                portfolio=portfolio,
                valuation=valuation,
                veto=True
            )

        # Default
        return self._build_response(
            action='HOLD',
            reason=f'Concentrado en oro ({pct_paxg*100:.1f}%). El Guardián está atento. '
                   f'Esperando señal de cambio a BTC o venta parcial para generar liquidez.',
            confidence=55,
            portfolio=portfolio,
            valuation=valuation
        )

    def _handle_no_cash(self, pct_btc, pct_paxg, sys_action, sys_confidence, ratio_fav, prices, portfolio):
        """0% o casi 0% USDT. Solo se puede cambiar, no comprar."""
        valuation = self._value_portfolio(portfolio, prices)
        btc_available = portfolio.get('BTC', 0)
        paxg_available = portfolio.get('PAXG', 0)

        # Si hay mucho PAXG y señal de compra BTC + ratio favorable → CAMBIO
        if pct_paxg > pct_btc and ratio_fav >= 0.4 and sys_confidence >= 55:
            size = self._calc_trade_size('PAXG', sys_confidence, pct_paxg, self.TARGET_PCTS['PAXG'], ratio_fav)
            amt_paxg = paxg_available * size
            paxg_price = valuation['paxg_price']
            btc_price = valuation['btc_price']
            usd_value = amt_paxg * paxg_price
            btc_to_get = usd_value / btc_price if btc_price > 0 else 0
            return self._build_response(
                action='SWAP_PAXG_TO_BTC',
                reason=f'Sin efectivo (0% USDT). Tenés más oro que BTC. Sistema indica oportunidad en BTC. '
                       f'Cambio PAXG→BTC es la única forma de entrar sin depósito adicional. '
                       f'Tamaño conservador para no quedar sin refugio.',
                confidence=min(90, sys_confidence + 5),
                trade_size_pct=size,
                amount_crypto=amt_paxg,
                amount_usd=usd_value,
                source_asset='PAXG',
                target_asset='BTC',
                portfolio=portfolio,
                valuation=valuation
            )

        # Si hay mucho BTC y Macro dice RISK_OFF → cambiar a PAXG
        if pct_btc > pct_paxg and ratio_fav <= -0.4 and sys_confidence >= 55:
            size = self._calc_trade_size('BTC', sys_confidence, pct_btc, self.TARGET_PCTS['BTC'], abs(ratio_fav))
            amt_btc = btc_available * size
            btc_price = valuation['btc_price']
            paxg_price = valuation['paxg_price']
            usd_value = amt_btc * btc_price
            paxg_to_get = usd_value / paxg_price if paxg_price > 0 else 0
            return self._build_response(
                action='SWAP_BTC_TO_PAXG',
                reason=f'Sin efectivo (0% USDT). Tenés más BTC que oro. Macro indica RISK_OFF. '
                       f'Cambio BTC→PAXG protege el capital en refugio sin necesidad de vender a fiat.',
                confidence=min(90, sys_confidence + 5),
                trade_size_pct=size,
                amount_crypto=amt_btc,
                amount_usd=usd_value,
                source_asset='BTC',
                target_asset='PAXG',
                portfolio=portfolio,
                valuation=valuation
            )

        # Sin señal clara → hold
        return self._build_response(
            action='HOLD',
            reason=f'Sin efectivo (0% USDT). Sin señal clara de cambio. '
                   f'Mantener posición actual es la única opción sensata hasta que aparezca oportunidad.',
            confidence=50,
            portfolio=portfolio,
            valuation=valuation
        )

    def _handle_balanced(self, state, pct_btc, pct_paxg, pct_usdt,
                          sys_action, sys_confidence, ratio_fav, prices, portfolio):
        """Portafolio razonablemente balanceado. Ajustes finos."""
        valuation = self._value_portfolio(portfolio, prices)
        btc_available = portfolio.get('BTC', 0)
        paxg_available = portfolio.get('PAXG', 0)
        usdt_available = portfolio.get('USDT', 0)

        # ------------------------------------------------------------------
        # D1. Sistema dice COMPRA BTC y tenemos USDT
        # ------------------------------------------------------------------
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'BTC' in str(sys_action) and sys_confidence >= 65 and usdt_available > 10:
            size = self._calc_trade_size('USDT', sys_confidence, pct_usdt, self.TARGET_PCTS['USDT'], max(0, ratio_fav))
            amt_usd = usdt_available * size
            btc_price = valuation['btc_price']
            btc_to_buy = amt_usd / btc_price if btc_price > 0 else 0
            return self._build_response(
                action='BUY_BTC',
                reason=f'Portafolio balanceado. Sistema dice COMPRA BTC ({sys_confidence}%). '
                       f'Comprar con USDT disponible mantiene el portafolio creciendo.',
                confidence=sys_confidence,
                trade_size_pct=size,
                amount_usd=amt_usd,
                amount_crypto=btc_to_buy,
                source_asset='USDT',
                target_asset='BTC',
                portfolio=portfolio,
                valuation=valuation
            )

        # ------------------------------------------------------------------
        # D2. Sistema dice COMPRA PAXG y tenemos USDT
        # ------------------------------------------------------------------
        if sys_action in ('COMPRA_SPOT', 'LONG') and 'PAXG' in str(sys_action) and sys_confidence >= 65 and usdt_available > 10:
            size = self._calc_trade_size('USDT', sys_confidence, pct_usdt, self.TARGET_PCTS['USDT'], max(0, abs(ratio_fav)))
            amt_usd = usdt_available * size
            paxg_price = valuation['paxg_price']
            paxg_to_buy = amt_usd / paxg_price if paxg_price > 0 else 0
            return self._build_response(
                action='BUY_PAXG',
                reason=f'Portafolio balanceado. Sistema dice COMPRA PAXG ({sys_confidence}%). '
                       f'Reforzar el refugio de oro en zona de compra fuerte.',
                confidence=sys_confidence,
                trade_size_pct=size,
                amount_usd=amt_usd,
                amount_crypto=paxg_to_buy,
                source_asset='USDT',
                target_asset='PAXG',
                portfolio=portfolio,
                valuation=valuation
            )

        # ------------------------------------------------------------------
        # D3. Sistema dice VENTA BTC
        # ------------------------------------------------------------------
        if sys_action in ('VENTA_SPOT', 'SHORT') and 'BTC' in str(sys_action) and sys_confidence >= 60 and btc_available > 0:
            size = self._calc_trade_size('BTC', sys_confidence, pct_btc, self.TARGET_PCTS['BTC'], 0.5)
            amt_btc = btc_available * size
            btc_price = valuation['btc_price']
            usd_value = amt_btc * btc_price
            # Preferir cambio a PAXG si RISK_OFF
            if ratio_fav <= -0.3:
                paxg_price = valuation['paxg_price']
                paxg_to_get = usd_value / paxg_price if paxg_price > 0 else 0
                return self._build_response(
                    action='SWAP_BTC_TO_PAXG',
                    reason=f'Sistema dice VENTA BTC ({sys_confidence}%). Macro indica fortaleza del oro. '
                           f'Cambio a PAXG en vez de vender a USDT aprovecha el ciclo de refugio.',
                    confidence=min(90, sys_confidence + 10),
                    trade_size_pct=size,
                    amount_crypto=amt_btc,
                    amount_usd=usd_value,
                    source_asset='BTC',
                    target_asset='PAXG',
                    portfolio=portfolio,
                    valuation=valuation
                )
            return self._build_response(
                action='SELL_BTC',
                reason=f'Sistema dice VENTA BTC ({sys_confidence}%). Vender a USDT genera liquidez '
                       f'para próximas oportunidades.',
                confidence=sys_confidence,
                trade_size_pct=size,
                amount_crypto=amt_btc,
                amount_usd=usd_value,
                source_asset='BTC',
                target_asset='USDT',
                portfolio=portfolio,
                valuation=valuation
            )

        # ------------------------------------------------------------------
        # D4. Sistema dice VENTA PAXG
        # ------------------------------------------------------------------
        if sys_action in ('VENTA_SPOT', 'SHORT') and 'PAXG' in str(sys_action) and sys_confidence >= 60 and paxg_available > 0:
            size = self._calc_trade_size('PAXG', sys_confidence, pct_paxg, self.TARGET_PCTS['PAXG'], 0.5)
            amt_paxg = paxg_available * size
            paxg_price = valuation['paxg_price']
            usd_value = amt_paxg * paxg_price
            return self._build_response(
                action='SELL_PAXG',
                reason=f'Sistema dice VENTA PAXG ({sys_confidence}%). Vender a USDT genera liquidez.',
                confidence=sys_confidence,
                trade_size_pct=size,
                amount_crypto=amt_paxg,
                amount_usd=usd_value,
                source_asset='PAXG',
                target_asset='USDT',
                portfolio=portfolio,
                valuation=valuation
            )

        # ------------------------------------------------------------------
        # D5. Señal propia del TGP: cambio por ratio + desbalance
        # ------------------------------------------------------------------
        # Si tenemos mucho PAXG y el ratio favorece fuertemente BTC
        if pct_paxg > self.TARGET_PCTS['PAXG'] + 0.15 and ratio_fav >= 0.6 and sys_confidence < 55:
            size = self._calc_trade_size('PAXG', 65, pct_paxg, self.TARGET_PCTS['PAXG'], ratio_fav)
            amt_paxg = paxg_available * size
            paxg_price = valuation['paxg_price']
            btc_price = valuation['btc_price']
            usd_value = amt_paxg * paxg_price
            btc_to_get = usd_value / btc_price if btc_price > 0 else 0
            return self._build_response(
                action='SWAP_PAXG_TO_BTC',
                reason=f'Portafolio con sobrepeso en oro ({pct_paxg*100:.1f}%). El sistema no da señal clara, '
                       f'pero el Macro indica RISK_ON y el ratio favorece cambiar oro por BTC. '
                       f'El Guardián genera señal propia de cambio estratégico para no perder satoshis '
                       f'cuando BTC sube más que el oro.',
                confidence=70,
                trade_size_pct=size,
                amount_crypto=amt_paxg,
                amount_usd=usd_value,
                source_asset='PAXG',
                target_asset='BTC',
                portfolio=portfolio,
                valuation=valuation
            )

        # Si tenemos mucho BTC y el ratio favorece fuertemente PAXG
        if pct_btc > self.TARGET_PCTS['BTC'] + 0.15 and ratio_fav <= -0.6 and sys_confidence < 55:
            size = self._calc_trade_size('BTC', 65, pct_btc, self.TARGET_PCTS['BTC'], abs(ratio_fav))
            amt_btc = btc_available * size
            btc_price = valuation['btc_price']
            paxg_price = valuation['paxg_price']
            usd_value = amt_btc * btc_price
            paxg_to_get = usd_value / paxg_price if paxg_price > 0 else 0
            return self._build_response(
                action='SWAP_BTC_TO_PAXG',
                reason=f'Portafolio con sobrepeso en BTC ({pct_btc*100:.1f}%). El sistema no da señal clara, '
                       f'pero el Macro indica RISK_OFF fuerte. Cambio estratégico a oro para protección.',
                confidence=70,
                trade_size_pct=size,
                amount_crypto=amt_btc,
                amount_usd=usd_value,
                source_asset='BTC',
                target_asset='PAXG',
                portfolio=portfolio,
                valuation=valuation
            )

        # ------------------------------------------------------------------
        # D6. Nada que hacer
        # ------------------------------------------------------------------
        return self._build_response(
            action='HOLD',
            reason=f'Portafolio razonablemente balanceado. Sin oportunidad clara que justifique mover capital. '
                   f'La paciencia es parte de la acumulación. Esperando mejor setup.',
            confidence=50,
            portfolio=portfolio,
            valuation=valuation
        )

    # ========================================================================
    # UTILIDADES
    # ========================================================================

    def _calc_trade_size(self, source_asset, confidence, current_pct, target_pct, favorability):
        """
        Calcula el % del activo fuente a usar en la operación.

        source_asset: 'BTC', 'PAXG', 'USDT'
        confidence: 0-100
        current_pct: % actual del activo fuente en el portafolio
        target_pct: % objetivo del activo fuente
        favorability: -1 a 1 (qué tan favorable es el entorno)
        """
        # Base: cuánto nos falta o sobra para llegar al target
        deviation = abs(current_pct - target_pct)

        # Factor de confianza (60-100 → 0.6-1.0)
        conf_factor = max(0.5, confidence / 100)

        # Factor de favorabilidad (más favorable = operación más grande)
        fav_factor = 0.7 + (0.6 * abs(favorability))  # 0.7 a 1.3

        # Tamaño bruto
        raw_size = deviation * conf_factor * fav_factor

        # Límites
        return max(self.MIN_TRADE_PCT, min(self.MAX_TRADE_PCT, raw_size))

    def _build_response(self, action, reason, confidence, portfolio, valuation,
                        trade_size_pct=0, amount_crypto=0, amount_usd=0,
                        source_asset=None, target_asset=None, veto=False):
        """Construye la respuesta estandarizada del TGP."""

        # Calcular portafolio post-operación (simulado)
        portfolio_after = dict(portfolio)
        if action == 'BUY_BTC' and source_asset == 'USDT':
            portfolio_after['USDT'] = portfolio_after.get('USDT', 0) - amount_usd
            portfolio_after['BTC'] = portfolio_after.get('BTC', 0) + amount_crypto
        elif action == 'BUY_PAXG' and source_asset == 'USDT':
            portfolio_after['USDT'] = portfolio_after.get('USDT', 0) - amount_usd
            portfolio_after['PAXG'] = portfolio_after.get('PAXG', 0) + amount_crypto
        elif action == 'SELL_BTC' and target_asset == 'USDT':
            portfolio_after['BTC'] = portfolio_after.get('BTC', 0) - amount_crypto
            portfolio_after['USDT'] = portfolio_after.get('USDT', 0) + amount_usd
        elif action == 'SELL_PAXG' and target_asset == 'USDT':
            portfolio_after['PAXG'] = portfolio_after.get('PAXG', 0) - amount_crypto
            portfolio_after['USDT'] = portfolio_after.get('USDT', 0) + amount_usd
        elif action == 'SWAP_PAXG_TO_BTC':
            portfolio_after['PAXG'] = portfolio_after.get('PAXG', 0) - amount_crypto
            # amount_crypto es PAXG vendido, amount_usd es valor en USD, 
            # necesitamos calcular BTC recibido
            btc_price = valuation.get('btc_price', 1)
            btc_received = amount_usd / btc_price if btc_price > 0 else 0
            portfolio_after['BTC'] = portfolio_after.get('BTC', 0) + btc_received
        elif action == 'SWAP_BTC_TO_PAXG':
            portfolio_after['BTC'] = portfolio_after.get('BTC', 0) - amount_crypto
            paxg_price = valuation.get('paxg_price', 1)
            paxg_received = amount_usd / paxg_price if paxg_price > 0 else 0
            portfolio_after['PAXG'] = portfolio_after.get('PAXG', 0) + paxg_received

        # Calcular valores post-operación
        post_val = self._value_portfolio(portfolio_after, {
            'BTC-USDT': valuation.get('btc_price', 0),
            'PAXG-USDT': valuation.get('paxg_price', 0)
        })

        return {
            'action': action,
            'reason': reason,
            'confidence': confidence,
            'veto': veto,
            'trade_size_pct': round(trade_size_pct, 4),
            'amount_crypto': round(amount_crypto, 8),
            'amount_usd': round(amount_usd, 2),
            'source_asset': source_asset,
            'target_asset': target_asset,
            'portfolio_before': {
                'BTC': portfolio.get('BTC', 0),
                'PAXG': portfolio.get('PAXG', 0),
                'USDT': portfolio.get('USDT', 0),
                'total_usd': valuation['total'],
                'pct_btc': valuation['pct_btc'],
                'pct_paxg': valuation['pct_paxg'],
                'pct_usdt': valuation['pct_usdt'],
            },
            'portfolio_after': {
                'BTC': round(portfolio_after.get('BTC', 0), 8),
                'PAXG': round(portfolio_after.get('PAXG', 0), 8),
                'USDT': round(portfolio_after.get('USDT', 0), 2),
                'total_usd': post_val['total'],
                'pct_btc': post_val['pct_btc'],
                'pct_paxg': post_val['pct_paxg'],
                'pct_usdt': post_val['pct_usdt'],
            }
        }


# Instancia global
portfolio_guardian = PortfolioGuardian()
