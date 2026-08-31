# portfolio_guardian.py
# Trader Guardián de Portafolio (TGP) - v1.0
# Módulo INDEPENDIENTE del sistema de 9 traders.
# No modifica ni interviene en las señales del sistema principal.
# Genera recomendaciones propias basadas en el portafolio del usuario,
# el estado del mercado, y la señal del sistema.
#
# OBJETIVO: Acumular satoshis, USDT y PAXG como bola de nieve.

import logging
import threading
import time

from datetime import datetime, timezone

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
    # ============================================================================
    # RESERVAS ESTRATÉGICAS
    # ============================================================================
    #
    # El TGP puede rotar BTC ↔ PAXG y BTC/PAXG ↔ USDT,
    # pero nunca debe permitir que una secuencia de recomendaciones
    # termine vaciando completamente un activo estratégico.
    #
    # Estos valores NO son objetivos.
    # Son PISOS DE PROTECCIÓN.
    # ============================================================================
    
    MIN_RESERVE_PCTS = {
        'BTC': 0.10,
        'PAXG': 0.10,
        'USDT': 0.05,
    }
    
    # Para movimientos excepcionales se mantiene todavía el techo
    # de concentración existente.
    MAX_CONCENTRATION_PCT = 0.75
    
    # Diferencia mínima entre BTC y PAXG para considerar una
    # rotación estratégica.
    ROTATION_EDGE_THRESHOLD = 18.0
    
    # Número mínimo de temporalidades que deben favorecer
    # una rotación antes de ejecutarla.
    MIN_ROTATION_TIMEFRAMES = 2
    # ========================================================================
    # FASE 7F.1 — COOLDOWN + ANTI-WHIPSAW
    # ========================================================================
    #
    # Una rotación BTC ↔ PAXG es estratégica.
    # No debe invertirse por pequeñas variaciones de corto plazo.
    #
    # IMPORTANTE:
    # estas reglas NO sustituyen el análisis multitemporal.
    # Sólo protegen una decisión ya generada por ese análisis.
    # ========================================================================

    ROTATION_COOLDOWN_MINUTES = 240

    # Para INVERTIR una rotación reciente exigimos más consenso
    # que para iniciar la primera.
    REVERSAL_MIN_TIMEFRAMES = 3

    # El edge normal sigue siendo 18.
    # Para una reversión exigimos una ventaja claramente mayor.
    REVERSAL_EDGE_THRESHOLD = 28.0

    # Después de 24 horas la memoria se considera vieja y se
    # permite que el análisis multitemporal vuelva a decidir desde cero.
    ROTATION_MEMORY_MAX_MINUTES = 1440
    # ========================================================================
    # FASE 7F.3 — PERSISTENCIA DE MEMORIA
    # ========================================================================

    # Si Supabase falla al guardar, no volver a intentar en
    # cada request. Máximo un intento cada 15 minutos.
    ROTATION_PERSIST_RETRY_MINUTES = 15

    # Una memoria persistida sólo se invalida automáticamente
    # si el portfolio REAL se mueve de forma muy clara en
    # dirección contraria.
    #
    # No usamos una tolerancia pequeña porque 7F.2 trabaja
    # precisamente mediante movimientos progresivos.
    ROTATION_MEMORY_CONTRADICTION_MARGIN = 0.15    
    # ========================================================================
    # FASE 7F.2 — RETORNO GRADUAL A BTC
    # ========================================================================
    #
    # Cuando el portfolio viene de una postura defensiva:
    #
    #     PAXG / USDT
    #
    # y BTC vuelve a ser favorecido, no se recupera toda la
    # exposición BTC de una sola vez.
    #
    # El tamaño máximo aumenta únicamente cuando la confirmación
    # multitemporal mejora.
    #
    # IMPORTANTE:
    #
    # estos valores son TECHOS.
    #
    # Nunca aumentan el tamaño calculado originalmente por el TGP.
    # ========================================================================

    BTC_REENTRY_STAGE_1_MAX_PCT = 0.08

    BTC_REENTRY_STAGE_2_MAX_PCT = 0.15

    BTC_REENTRY_STAGE_3_MAX_PCT = 0.25

    # Stage 2:
    # mínimo 3 TF favoreciendo BTC + confirmación superior.
    BTC_REENTRY_STAGE_2_EDGE = 28.0

    # Stage 3:
    # 4/4 TF + 1D y 1W directamente BTC + edge fuerte.
    BTC_REENTRY_STAGE_3_EDGE = 40.0

    # Evita considerar "defensivo" un pequeño desvío normal
    # respecto al portfolio objetivo.
    BTC_REENTRY_DEFENSIVE_BUFFER = 0.03    
    
    
    # Tamaños de operación
    MIN_TRADE_PCT = 0.08   # Mínimo 8% del activo fuente
    MAX_TRADE_PCT = 0.35   # Máximo 35% del activo fuente (nunca quedarse sin nada)

    def __init__(self):
        self.bolivia_tz = (
            __import__('pytz')
            .timezone(
                'America/La_Paz'
            )
            if 'pytz'
            in __import__('sys').modules
            else None
        )

        # ==============================================================
        # FASE 7F.1 — MEMORIA ANTI-WHIPSAW
        # ==============================================================
        #
        # Memoria ligera en RAM.
        #
        # Clave:
        #     usuario
        #
        # Valor:
        #     última dirección estratégica recomendada.
        #
        # No utiliza:
        #     Supabase
        #     archivos
        #     nuevas llamadas de mercado
        #
        # Si Render reinicia, simplemente vuelve a comenzar sin memoria.
        # ==============================================================

        self._rotation_guard_state = {}

        # El servidor puede recibir más de una petición.
        # Protegemos la pequeña estructura en memoria.
        self._rotation_guard_lock = (
            threading.RLock()
        )
        # ==============================================================
        # FASE 7F.3
        # ==============================================================
        #
        # Sirve para garantizar:
        #
        #     una sola lectura Supabase
        #
        # por usuario y por proceso de Render.
        #
        # Después todo vuelve a funcionar desde RAM.
        # ==============================================================

        self._rotation_state_loaded_users = set()
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
    def _rotation_direction(
        self,
        action
    ):
        """
        Convierte una acción BTC ↔ PAXG en una dirección simple.

        Sólo se controlan swaps estratégicos.

        Las compras desde USDT NO quedan bloqueadas por este
        guardrail porque no representan una reversión directa
        BTC ↔ PAXG.
        """

        action = str(
            action
            or ''
        ).upper()

        if action == 'SWAP_PAXG_TO_BTC':
            return 'BTC'

        if action == 'SWAP_BTC_TO_PAXG':
            return 'PAXG'

        return None

     def _parse_rotation_datetime(
        self,
        value
    ):
        """
        Convierte timestamp Supabase/ISO a UTC aware datetime.
        """

        if not value:
            return None

        try:

            text = str(
                value
            ).strip()

            if text.endswith(
                'Z'
            ):

                text = (
                    text[:-1]
                    + '+00:00'
                )

            parsed = (
                datetime.fromisoformat(
                    text
                )
            )

            if parsed.tzinfo is None:

                parsed = (
                    parsed.replace(
                        tzinfo=timezone.utc
                    )
                )

            else:

                parsed = (
                    parsed.astimezone(
                        timezone.utc
                    )
                )

            return parsed

        except Exception:

            return None


    def _rotation_memory_contradicts_portfolio(
        self,
        direction,
        pct_btc,
        pct_paxg,
        pct_usdt
    ):
        """
        Decide si una memoria persistida contradice de forma
        MUY CLARA el portfolio real actual.

        No se invalida por pequeñas diferencias.

        Ejemplo válido:
            memoria PAXG
            BTC 52%
            PAXG 30%

        puede representar una rotación gradual.

        Ejemplo contradictorio:
            memoria PAXG
            BTC 70%
            PAXG 10%

        tras una actualización posterior del portfolio.
        """

        direction = str(
            direction
            or ''
        ).upper()

        try:

            pct_btc = float(
                pct_btc
                or 0
            )

            pct_paxg = float(
                pct_paxg
                or 0
            )

            pct_usdt = float(
                pct_usdt
                or 0
            )

        except (
            TypeError,
            ValueError
        ):

            return False

        # Portfolio prácticamente en efectivo:
        # la vieja tesis BTC/PAXG ya no debe gobernarlo.
        if pct_usdt >= 0.80:
            return True

        margin = (
            self
            .ROTATION_MEMORY_CONTRADICTION_MARGIN
        )

        # ==============================================================
        # MEMORIA = PAXG
        # ==============================================================

        if direction == 'PAXG':

            btc_clearly_dominant = (
                pct_btc
                >=
                self.TARGET_PCTS[
                    'BTC'
                ]
                + margin
            )

            paxg_clearly_low = (
                pct_paxg
                <=
                max(
                    0.0,
                    self.TARGET_PCTS[
                        'PAXG'
                    ]
                    - margin
                )
            )

            return bool(
                btc_clearly_dominant
                and
                paxg_clearly_low
            )

        # ==============================================================
        # MEMORIA = BTC
        # ==============================================================

        if direction == 'BTC':

            paxg_clearly_dominant = (
                pct_paxg
                >=
                self.TARGET_PCTS[
                    'PAXG'
                ]
                + margin
            )

            btc_clearly_low = (
                pct_btc
                <=
                max(
                    0.0,
                    self.TARGET_PCTS[
                        'BTC'
                    ]
                    - margin
                )
            )

            return bool(
                paxg_clearly_dominant
                and
                btc_clearly_low
            )

        return True


    def _ensure_rotation_state_loaded(
        self,
        user,
        portfolio,
        pct_btc,
        pct_paxg,
        pct_usdt
    ):
        """
        FASE 7F.3

        Recupera la memoria persistida UNA SOLA VEZ por usuario
        después de iniciar el proceso.

        La memoria persistida nunca tiene autoridad absoluta.

        Se descarta cuando:

            - dirección inválida;
            - timestamp inválido;
            - tiene más de 24 horas;
            - el usuario actualizó posteriormente su portfolio
              y la composición real contradice claramente la memoria.

        Si Supabase falla:
            continúa sin memoria.
        """

        user_key = str(
            user
            or 'anonymous'
        )

        # ==============================================================
        # ¿YA SE INTENTÓ CARGAR?
        # ==============================================================

        with self._rotation_guard_lock:

            if (
                user_key
                in self._rotation_state_loaded_users
            ):

                return

            # Marcamos antes de la llamada de red para no provocar
            # múltiples lecturas paralelas para el mismo usuario.
            self._rotation_state_loaded_users.add(
                user_key
            )

            # Si por algún motivo ya existe una memoria RAM,
            # siempre tiene prioridad.
            existing = (
                self._rotation_guard_state
                .get(
                    user_key
                )
            )

            if isinstance(
                existing,
                dict
            ):

                return

        try:

            # Import diferido:
            # evita acoplar la inicialización del Guardian
            # con la inicialización de Supabase.
            from supabase_client import (
                supabase_db
            )

            persisted = (
                supabase_db
                .get_user_rotation_state(
                    user_key
                )
            )

        except Exception as e:

            logger.debug(
                "7F.3 memoria persistente no disponible: "
                f"{e}"
            )

            return

        if not isinstance(
            persisted,
            dict
        ):

            return

        direction = str(
            persisted.get(
                'direction',
                ''
            )
            or ''
        ).upper()

        if direction not in (
            'BTC',
            'PAXG'
        ):

            return

        started_dt = (
            self._parse_rotation_datetime(
                persisted.get(
                    'started_at'
                )
            )
        )

        if started_dt is None:

            # Estado incompleto:
            # limpiar best-effort.
            try:

                supabase_db.update_user_rotation_state(
                    user_key,
                    direction=None
                )

            except Exception:

                pass

            return

        now_utc = (
            datetime.now(
                timezone.utc
            )
        )

        age_seconds = max(
            0.0,
            (
                now_utc
                - started_dt
            ).total_seconds()
        )

        age_minutes = (
            age_seconds
            / 60.0
        )

        # ==============================================================
        # MEMORIA DEMASIADO ANTIGUA
        # ==============================================================

        if (
            age_minutes
            >= self.ROTATION_MEMORY_MAX_MINUTES
        ):

            try:

                supabase_db.update_user_rotation_state(
                    user_key,
                    direction=None
                )

            except Exception:

                pass

            return

        # ==============================================================
        # VALIDAR CONTRA PORTFOLIO REAL
        # ==============================================================
        #
        # IMPORTANTE:
        # sólo invalidamos por contradicción si el portfolio fue
        # actualizado DESPUÉS de que nació esta memoria.
        #
        # Esto evita invalidar una recomendación recién generada
        # simplemente porque el usuario todavía no la ejecutó.
        # ==============================================================

        portfolio_updated_dt = (
            self._parse_rotation_datetime(
                (
                    portfolio
                    or {}
                ).get(
                    'updated_at'
                )
            )
        )

        portfolio_changed_after = bool(
            portfolio_updated_dt
            is not None
            and
            portfolio_updated_dt
            > started_dt
        )

        contradiction = (
            self
            ._rotation_memory_contradicts_portfolio(
                direction,
                pct_btc,
                pct_paxg,
                pct_usdt
            )
        )

        if (
            portfolio_changed_after
            and
            contradiction
        ):

            logger.info(
                "🧹 7F.3: memoria TGP descartada "
                f"para {user_key}. "
                f"Dirección persistida={direction}, "
                "pero el portfolio real actualizado "
                "la contradice claramente."
            )

            try:

                supabase_db.update_user_rotation_state(
                    user_key,
                    direction=None
                )

            except Exception:

                pass

            return

        # ==============================================================
        # RECONSTRUIR time.monotonic()
        # ==============================================================
        #
        # Nunca persistimos el valor monotonic porque sólo tiene
        # significado dentro de un proceso.
        #
        # Reconstruimos:
        #
        #     monotonic actual - edad real
        #
        # ==============================================================

        monotonic_started = (
            time.monotonic()
            - age_seconds
        )

        with self._rotation_guard_lock:

            # No pisar un estado que otro request haya creado
            # mientras consultábamos Supabase.
            if not isinstance(
                self._rotation_guard_state.get(
                    user_key
                ),
                dict
            ):

                self._rotation_guard_state[
                    user_key
                ] = {
                    'direction':
                        direction,

                    'started_at':
                        monotonic_started,

                    'started_at_utc':
                        started_dt.isoformat(),

                    'dirty':
                        False,

                    'last_persist_attempt_at':
                        0.0,

                    'source':
                        'SUPABASE'
                }

        logger.info(
            "♻️ 7F.3 memoria TGP restaurada: "
            f"{user_key} → {direction} "
            f"({age_minutes:.0f} min)"
        )


    def _persist_rotation_state_if_dirty(
        self,
        user
    ):
        """
        Guarda únicamente estados nuevos/cambiados.

        No escribe en cada refresh.

        Si falla Supabase:
            conserva memoria RAM
            y limita reintentos a uno cada 15 minutos.
        """

        user_key = str(
            user
            or 'anonymous'
        )

        now_mono = (
            time.monotonic()
        )

        with self._rotation_guard_lock:

            state = (
                self._rotation_guard_state
                .get(
                    user_key
                )
            )

            if not isinstance(
                state,
                dict
            ):

                return False

            if not bool(
                state.get(
                    'dirty',
                    False
                )
            ):

                return False

            last_attempt = float(
                state.get(
                    'last_persist_attempt_at',
                    0
                )
                or 0
            )

            retry_seconds = (
                self
                .ROTATION_PERSIST_RETRY_MINUTES
                * 60
            )

            if (
                last_attempt > 0
                and
                now_mono
                - last_attempt
                < retry_seconds
            ):

                return False

            direction = str(
                state.get(
                    'direction',
                    ''
                )
                or ''
            ).upper()

            started_at_utc = (
                state.get(
                    'started_at_utc'
                )
            )

            state[
                'last_persist_attempt_at'
            ] = now_mono

        if direction not in (
            'BTC',
            'PAXG'
        ):

            return False

        if not started_at_utc:
            return False

        try:

            from supabase_client import (
                supabase_db
            )

            saved = (
                supabase_db
                .update_user_rotation_state(
                    user_name=user_key,
                    direction=direction,
                    started_at=started_at_utc
                )
            )

        except Exception as e:

            logger.debug(
                "7F.3 persistencia TGP: "
                f"{e}"
            )

            return False

        if not saved:
            return False

        # ==============================================================
        # MARCAR LIMPIO
        # ==============================================================
        #
        # Sólo si sigue siendo exactamente el mismo estado.
        #
        # Si otra petición cambió dirección mientras escribíamos,
        # el nuevo estado permanece dirty.
        # ==============================================================

        with self._rotation_guard_lock:

            current = (
                self._rotation_guard_state
                .get(
                    user_key
                )
            )

            if (
                isinstance(
                    current,
                    dict
                )
                and
                str(
                    current.get(
                        'direction',
                        ''
                    )
                ).upper()
                == direction
                and
                current.get(
                    'started_at_utc'
                )
                == started_at_utc
            ):

                current[
                    'dirty'
                ] = False

                current[
                    'source'
                ] = 'RAM+SUPABASE'

        return True   

    def _apply_rotation_anti_whipsaw(
        self,
        user,
        action,
        reason,
        confidence,
        btc_count,
        paxg_count,
        best_tf_data
    ):
        """
        FASE 7F.1

        Protege las rotaciones BTC ↔ PAXG contra cambios
        repetitivos de dirección.

        Reglas:

        1. Primera dirección:
               permitida.

        2. Misma dirección:
               permitida.

        3. Dirección opuesta durante cooldown:
               bloqueada.

        4. Dirección opuesta después del cooldown:
               exige:
                   >= 3 temporalidades
                   y edge >= 28.

        5. Memoria > 24h:
               se considera antigua y el sistema decide desde cero.

        IMPORTANTE:
        no modifica los análisis técnicos.
        Sólo puede convertir una rotación en HOLD.
        """

        direction = (
            self._rotation_direction(
                action
            )
        )

        base_result = {
            'allowed':
                True,

            'action':
                action,

            'reason':
                reason,

            'confidence':
                confidence,

            'active':
                False,

            'direction':
                direction,

            'previous_direction':
                None,

            'cooldown_remaining_minutes':
                0,

            'reversal_required':
                False,

            'reversal_confirmed':
                False
        }

        # ==============================================================
        # NO ES ROTACIÓN BTC ↔ PAXG
        # ==============================================================

        if direction is None:
            return base_result

        now = time.monotonic()

        now_utc_iso = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        user_key = str(
            user
            or 'anonymous'
        )

        try:

            best_edge = abs(
                float(
                    (
                        best_tf_data
                        or {}
                    ).get(
                        'relative_edge',
                        0
                    )
                    or 0
                )
            )

        except (
            TypeError,
            ValueError
        ):

            best_edge = 0.0

        current_tf_count = (
            int(
                btc_count
            )
            if direction == 'BTC'
            else int(
                paxg_count
            )
        )

        with self._rotation_guard_lock:

            previous = (
                self._rotation_guard_state
                .get(
                    user_key
                )
            )

            # ==========================================================
            # PRIMERA ROTACIÓN OBSERVADA
            # ==============================================================

            if not isinstance(
                previous,
                dict
            ):

                self._rotation_guard_state[
                    user_key
                ] = {
                    'direction':
                        direction,

                    'started_at':
                        now,

                    'started_at_utc':
                        now_utc_iso,

                    # 7F.3:
                    # sólo los cambios nuevos deben escribirse.
                    'dirty':
                        True,

                    'last_persist_attempt_at':
                        0.0,

                    'source':
                        'RAM'
                }

                base_result[
                    'active'
                ] = True

                return base_result

            previous_direction = str(
                previous.get(
                    'direction',
                    ''
                )
                or ''
            )

            started_at = float(
                previous.get(
                    'started_at',
                    now
                )
                or now
            )

            elapsed_minutes = max(
                0.0,
                (
                    now
                    - started_at
                )
                / 60.0
            )

            base_result[
                'active'
            ] = True

            base_result[
                'previous_direction'
            ] = previous_direction

            # ==========================================================
            # MEMORIA ANTIGUA
            # ==============================================================

            if (
                elapsed_minutes
                >= self.ROTATION_MEMORY_MAX_MINUTES
            ):

                self._rotation_guard_state[
                    user_key
                ] = {
                    'direction':
                        direction,

                    'started_at':
                        now,

                    'started_at_utc':
                        now_utc_iso,

                    'dirty':
                        True,

                    'last_persist_attempt_at':
                        0.0,

                    'source':
                        'RAM'
                }

                return base_result

            # ==========================================================
            # MISMA DIRECCIÓN
            # ==========================================================
            #
            # Ejemplo:
            #
            # BTC sigue siendo favorecido.
            #
            # No bloqueamos la recomendación.
            #
            # IMPORTANTE:
            # NO reiniciamos started_at.
            #
            # Si lo reiniciáramos en cada refresh,
            # el cooldown nunca terminaría.
            # ==============================================================

            if (
                direction
                == previous_direction
            ):

                return base_result

            # ==========================================================
            # DIRECCIÓN OPUESTA
            # ==============================================================

            base_result[
                'reversal_required'
            ] = True

            # ==========================================================
            # COOLDOWN DURO
            # ==============================================================

            if (
                elapsed_minutes
                < self.ROTATION_COOLDOWN_MINUTES
            ):

                remaining = max(
                    0,
                    self.ROTATION_COOLDOWN_MINUTES
                    - elapsed_minutes
                )

                return {
                    **base_result,

                    'allowed':
                        False,

                    'action':
                        'HOLD',

                    'confidence':
                        max(
                            70,
                            min(
                                90,
                                float(
                                    confidence
                                    or 0
                                )
                            )
                        ),

                    'cooldown_remaining_minutes':
                        round(
                            remaining,
                            1
                        ),

                    'reason': (
                        f'Anti-whipsaw TGP: apareció una señal '
                        f'de rotación hacia {direction}, pero la '
                        f'última dirección estratégica fue '
                        f'{previous_direction} hace sólo '
                        f'{elapsed_minutes:.0f} minutos. '
                        f'Se mantiene el portafolio durante el '
                        f'cooldown para evitar rotaciones '
                        f'BTC↔PAXG provocadas por ruido.'
                    )
                }

            # ==========================================================
            # REVERSIÓN DESPUÉS DEL COOLDOWN
            # ==========================================================
            #
            # Ya pasó el tiempo mínimo.
            #
            # Pero para cambiar de tesis exigimos:
            #
            #     >= 3 TF
            #
            # y:
            #
            #     edge >= 28
            #
            # ==============================================================

            reversal_confirmed = (
                current_tf_count
                >= self.REVERSAL_MIN_TIMEFRAMES
                and
                best_edge
                >= self.REVERSAL_EDGE_THRESHOLD
            )

            base_result[
                'reversal_confirmed'
            ] = bool(
                reversal_confirmed
            )

            if not reversal_confirmed:

                return {
                    **base_result,

                    'allowed':
                        False,

                    'action':
                        'HOLD',

                    'confidence':
                        max(
                            65,
                            min(
                                85,
                                float(
                                    confidence
                                    or 0
                                )
                            )
                        ),

                    'reason': (
                        f'Anti-whipsaw TGP: el mercado intenta '
                        f'invertir la tesis de '
                        f'{previous_direction} hacia {direction}, '
                        f'pero la reversión todavía no alcanza '
                        f'confirmación reforzada. '
                        f'Consenso actual: '
                        f'{current_tf_count}/4 TF; '
                        f'edge máximo: {best_edge:.1f}. '
                        f'Para invertir una rotación reciente '
                        f'se exigen al menos '
                        f'{self.REVERSAL_MIN_TIMEFRAMES}/4 TF '
                        f'y edge ≥ '
                        f'{self.REVERSAL_EDGE_THRESHOLD:.1f}.'
                    )
                }

            # ==========================================================
            # REVERSIÓN CONFIRMADA
            # ==============================================================

            self._rotation_guard_state[
                user_key
            ] = {
                'direction':
                    direction,

                'started_at':
                    now,

                'started_at_utc':
                    now_utc_iso,

                'dirty':
                    True,

                'last_persist_attempt_at':
                    0.0,

                'source':
                    'RAM'
            }

            base_result[
                'reversal_confirmed'
            ] = True

            return base_result

    def _build_gradual_btc_reentry_plan(
        self,
        user,
        action,
        proposed_trade_size,
        pct_btc,
        pct_paxg,
        pct_usdt,
        btc_count,
        best_tf_data,
        timeframe_results
    ):
        """
        FASE 7F.2

        Construye un plan gradual para volver a BTC cuando el
        portfolio está o estuvo recientemente en modo defensivo.

        Afecta únicamente:

            SWAP_PAXG_TO_BTC
            BUY_BTC

        No afecta:

            SWAP_BTC_TO_PAXG
            BUY_PAXG
            HOLD
            SELL_BTC
            SELL_PAXG

        REGLA CENTRAL:

            adjusted_trade_size
                <=
            proposed_trade_size

        Por tanto 7F.2 puede reducir riesgo,
        pero nunca incrementarlo.
        """

        result = {
            'active':
                False,

            'stage':
                0,

            'proposed_trade_size':
                float(
                    proposed_trade_size
                    or 0
                ),

            'max_trade_size':
                float(
                    proposed_trade_size
                    or 0
                ),

            'adjusted_trade_size':
                float(
                    proposed_trade_size
                    or 0
                ),

            'btc_timeframe_count':
                int(
                    btc_count
                    or 0
                ),

            'higher_btc_count':
                0,

            'higher_paxg_count':
                0,

            'best_btc_edge':
                0.0,

            'portfolio_defensive':
                False,

            'recent_defensive_memory':
                False,

            'previous_direction':
                None,

            'reason':
                'NO_APLICA'
        }

        action = str(
            action
            or ''
        ).upper()

        # ==============================================================
        # SÓLO REENTRADA HACIA BTC
        # ==============================================================

        if action not in (
            'SWAP_PAXG_TO_BTC',
            'BUY_BTC'
        ):

            return result

        try:

            proposed_trade_size = float(
                proposed_trade_size
                or 0
            )

        except (
            TypeError,
            ValueError
        ):

            proposed_trade_size = 0.0

        if proposed_trade_size <= 0:
            return result

        # ==============================================================
        # MEMORIA DE 7F.1
        # ==============================================================

        previous_direction = None

        user_key = str(
            user
            or 'anonymous'
        )

        try:

            with self._rotation_guard_lock:

                state = (
                    self._rotation_guard_state
                    .get(
                        user_key
                    )
                )

                if isinstance(
                    state,
                    dict
                ):

                    previous_direction = str(
                        state.get(
                            'direction',
                            ''
                        )
                        or ''
                    )

        except Exception:

            previous_direction = None

        recent_defensive_memory = (
            previous_direction
            == 'PAXG'
        )

        # ==============================================================
        # ¿EL PORTFOLIO ESTÁ DEFENSIVO?
        # ==============================================================
        #
        # Ejemplo:
        #
        # BTC 30%
        # PAXG 45%
        # USDT 25%
        #
        # Está claramente por debajo del objetivo BTC
        # y sobreponderado defensivamente.
        #
        # El buffer de 3 puntos evita dispararlo por pequeñas
        # diferencias normales.
        # ==============================================================

        btc_below_target = (
            pct_btc
            < self.TARGET_PCTS[
                'BTC'
            ]
        )

        paxg_defensive = (
            pct_paxg
            >
            self.TARGET_PCTS[
                'PAXG'
            ]
            +
            self.BTC_REENTRY_DEFENSIVE_BUFFER
        )

        usdt_defensive = (
            pct_usdt
            >
            self.TARGET_PCTS[
                'USDT'
            ]
            +
            self.BTC_REENTRY_DEFENSIVE_BUFFER
        )

        portfolio_defensive = (
            btc_below_target
            and
            (
                paxg_defensive
                or usdt_defensive
            )
        )

        # ==============================================================
        # SI NO VIENE DE DEFENSA, NO INTERFERIR
        # ==============================================================

        if not (
            portfolio_defensive
            or recent_defensive_memory
        ):

            return result

        # ==============================================================
        # EDGE BTC
        # ==============================================================

        try:

            best_edge = float(
                (
                    best_tf_data
                    or {}
                ).get(
                    'relative_edge',
                    0
                )
                or 0
            )

        except (
            TypeError,
            ValueError
        ):

            best_edge = 0.0

        # Sólo interesa la ventaja positiva hacia BTC.
        best_btc_edge = max(
            0.0,
            best_edge
        )

        # ==============================================================
        # CONFIRMACIÓN DIRECTA DE 1D / 1W
        # ==============================================================

        higher_btc_count = 0
        higher_paxg_count = 0

        for tf in (
            '1D',
            '1W'
        ):

            data = (
                timeframe_results.get(
                    tf,
                    {}
                )
                if isinstance(
                    timeframe_results,
                    dict
                )
                else {}
            )

            preference = str(
                (
                    data
                    or {}
                ).get(
                    'preference',
                    'NEUTRAL'
                )
                or 'NEUTRAL'
            ).upper()

            if preference == 'BTC':

                higher_btc_count += 1

            elif preference == 'PAXG':

                higher_paxg_count += 1

        # ==============================================================
        # STAGE 1 — SONDA
        # ==============================================================
        #
        # Es deliberadamente igual al tamaño mínimo permitido
        # actualmente por el Guardian: 8%.
        #
        # Incluso si el sistema originalmente quería utilizar
        # 20%-35%, el regreso comienza pequeño.
        # ==============================================================

        stage = 1

        max_trade_size = (
            self.BTC_REENTRY_STAGE_1_MAX_PCT
        )

        stage_reason = (
            'REENTRADA_INICIAL'
        )

        # ==============================================================
        # STAGE 2 — CONFIRMACIÓN INTERMEDIA
        # ==============================================================
        #
        # Requiere:
        #
        #     >= 3/4 TF BTC
        #     >= 1 TF mayor directamente BTC
        #     edge >= 28
        # ==============================================================

        if (
            int(
                btc_count
                or 0
            ) >= 3
            and
            higher_btc_count >= 1
            and
            best_btc_edge
            >= self.BTC_REENTRY_STAGE_2_EDGE
        ):

            stage = 2

            max_trade_size = (
                self.BTC_REENTRY_STAGE_2_MAX_PCT
            )

            stage_reason = (
                'REENTRADA_CONFIRMADA'
            )

        # ==============================================================
        # STAGE 3 — CONFIRMACIÓN FUERTE
        # ==============================================================
        #
        # Requiere simultáneamente:
        #
        #     4/4 TF BTC
        #     1D = BTC
        #     1W = BTC
        #     edge >= 40
        #
        # Aun así el máximo es 25%.
        #
        # Nunca volvemos al 35% de una sola vez durante la
        # transición defensiva → BTC.
        # ==============================================================

        if (
            int(
                btc_count
                or 0
            ) >= 4
            and
            higher_btc_count >= 2
            and
            best_btc_edge
            >= self.BTC_REENTRY_STAGE_3_EDGE
        ):

            stage = 3

            max_trade_size = (
                self.BTC_REENTRY_STAGE_3_MAX_PCT
            )

            stage_reason = (
                'REENTRADA_FUERTE'
            )

        # ==============================================================
        # PROTECTION ONLY
        # ==============================================================

        adjusted_trade_size = min(
            proposed_trade_size,
            max_trade_size
        )

        # Protección absoluta adicional.
        adjusted_trade_size = max(
            0.0,
            min(
                proposed_trade_size,
                adjusted_trade_size
            )
        )

        return {
            'active':
                True,

            'stage':
                stage,

            'proposed_trade_size':
                round(
                    proposed_trade_size,
                    4
                ),

            'max_trade_size':
                round(
                    max_trade_size,
                    4
                ),

            'adjusted_trade_size':
                round(
                    adjusted_trade_size,
                    4
                ),

            'btc_timeframe_count':
                int(
                    btc_count
                    or 0
                ),

            'higher_btc_count':
                int(
                    higher_btc_count
                ),

            'higher_paxg_count':
                int(
                    higher_paxg_count
                ),

            'best_btc_edge':
                round(
                    best_btc_edge,
                    2
                ),

            'portfolio_defensive':
                bool(
                    portfolio_defensive
                ),

            'recent_defensive_memory':
                bool(
                    recent_defensive_memory
                ),

            'previous_direction':
                previous_direction,

            'reason':
                stage_reason
        }
    

    def _score_market_snapshot(
        self,
        analysis,
        asset
    ):
        """
        Convierte un análisis de mercado en una puntuación
        direccional para BTC o PAXG.
    
        Rango:
            -100 = fuertemente desfavorable
            +100 = fuertemente favorable
    
        NO representa probabilidad de ganar.
        Es una puntuación comparativa de fortaleza.
        """
    
        if not isinstance(
            analysis,
            dict
        ):
            return 0.0
    
        decision = analysis.get(
            'decision',
            {}
        ) or {}
    
        action = str(
            decision.get(
                'action',
                'NO_OPERAR'
            )
        ).upper()
    
        confidence = float(
            decision.get(
                'confidence',
                0
            )
            or 0
        )
    
        levels = analysis.get(
            'levels',
            {}
        ) or {}
    
        execution_safety = float(
            levels.get(
                'execution_safety',
                0
            )
            or 0
        )
    
        if execution_safety <= 1:
            execution_safety *= 100
    
        trend = analysis.get(
            'trend',
            {}
        ) or {}
    
        trend_direction = str(
            trend.get(
                'direction',
                'neutral'
            )
        ).lower()
    
        adx = float(
            trend.get(
                'adx',
                0
            )
            or 0
        )
    
        momentum = analysis.get(
            'momentum',
            {}
        ) or {}
    
        momentum_direction = str(
            momentum.get(
                'direction',
                'neutral'
            )
        ).lower()
    
        structure = analysis.get(
            'structure',
            {}
        ) or {}
    
        # ==============================================================
        # DIRECCIÓN
        # ==============================================================
    
        direct_sign = 0.0
    
        if action in (
            'COMPRA_SPOT',
            'LONG'
        ):
    
            direct_sign = 1.0
    
        elif action in (
            'VENTA_SPOT',
            'SHORT'
        ):
    
            direct_sign = -1.0
    
        else:
    
            return 0.0
    
        # ==============================================================
        # FUERZA DE LA SEÑAL
        # ==============================================================
    
        confidence_score = max(
            0.0,
            min(
                100.0,
                confidence
            )
        )
    
        # No dejamos que confidence domine.
        base_strength = (
            confidence_score * 0.45
            +
            execution_safety * 0.30
        )
    
        # ==============================================================
        # TENDENCIA
        # ==============================================================
    
        trend_bonus = 0.0
    
        if direct_sign > 0:
    
            if trend_direction in (
                'bullish',
                'alcista'
            ):
                trend_bonus += 12
    
            elif trend_direction in (
                'bearish',
                'bajista'
            ):
                trend_bonus -= 12
    
            if momentum_direction in (
                'bullish',
                'alcista'
            ):
                trend_bonus += 6
    
        else:
    
            if trend_direction in (
                'bearish',
                'bajista'
            ):
                trend_bonus += 12
    
            elif trend_direction in (
                'bullish',
                'alcista'
            ):
                trend_bonus -= 12
    
            if momentum_direction in (
                'bearish',
                'bajista'
            ):
                trend_bonus += 6
    
        # ==============================================================
        # ADX
        # ==============================================================
    
        if adx >= 30:
            adx_factor = 1.10
    
        elif adx >= 25:
            adx_factor = 1.05
    
        elif adx < 15:
            adx_factor = 0.80
    
        else:
            adx_factor = 0.95
    
        # ==============================================================
        # ESTRUCTURA
        # ==============================================================
    
        structure_bonus = 0.0
        
        if (
            structure.get(
                'order_blocks_count',
                0
            ) > 0
            or structure.get(
                'order_blocks'
            )
        ):
            structure_bonus += 5
        
        if (
            structure.get(
                'fair_value_gaps_count',
                0
            ) > 0
            or structure.get(
                'fair_value_gaps'
            )
        ):
            structure_bonus += 5
        
        if (
            structure.get(
                'liquidity_sweeps_count',
                0
            ) > 0
            or structure.get(
                'liquidity_sweeps'
            )
        ):
            structure_bonus += 8
    
        # ==============================================================
        # SCORE
        # ==============================================================
    
        score = (
            base_strength
            + trend_bonus
            + structure_bonus
        )
    
        score *= adx_factor
    
        score *= direct_sign
    
        return max(
            -100.0,
            min(
                100.0,
                score
            )
        )
    def _score_ratio_for_assets(
        self,
        analysis
    ):
        """
        Interpreta PAXG-BTC.
    
        LONG/COMPRA_SPOT:
            PAXG está siendo favorecido frente a BTC.
    
        SHORT/VENTA_SPOT:
            BTC está siendo favorecido frente a PAXG.
    
        Devuelve:
            +100 → BTC claramente favorecido
            -100 → PAXG claramente favorecido
        """
    
        if not isinstance(
            analysis,
            dict
        ):
            return 0.0
    
        decision = analysis.get(
            'decision',
            {}
        ) or {}
    
        action = str(
            decision.get(
                'action',
                'NO_OPERAR'
            )
        ).upper()
    
        confidence = float(
            decision.get(
                'confidence',
                0
            )
            or 0
        )
    
        levels = analysis.get(
            'levels',
            {}
        ) or {}
    
        safety = float(
            levels.get(
                'execution_safety',
                0
            )
            or 0
        )
    
        if safety <= 1:
            safety *= 100
    
        # ==============================================================
        # FASE 7B — FUERZA DEL RATIO
        # ==============================================================
        #
        # Confidence del comité sólo aporta contexto.
        # La ejecución/estructura tiene mayor peso.
        # ==============================================================
        
        strength = (
            safety * 0.65
            +
            confidence * 0.35
        )
    
        if action in (
            'SHORT',
            'VENTA_SPOT'
        ):
    
            return min(
                100,
                strength
            )
    
        if action in (
            'LONG',
            'COMPRA_SPOT'
        ):
    
            return max(
                -100,
                -strength
            )
    
        return 0.0
    def analyze_multi_timeframe(
        self,
        user,
        portfolio,
        prices,
        market_snapshots
    ):
        """
        TGP MULTI-TIMEFRAME.
    
        Analiza simultáneamente:
    
            BTC-USDT
            PAXG-USDT
            PAXG-BTC
    
        en:
    
            4h
            12h
            1D
            1W
    
        No realiza llamadas de mercado.
    
        market_snapshots contiene resúmenes ya calculados por
        TradingExpertSystem.
    
        Objetivos:
    
            1. proteger BTC
            2. proteger PAXG
            3. conservar liquidez estratégica
            4. acumular satoshis
            5. acumular USDT cuando corresponda
            6. rotar BTC ↔ PAXG oportunamente
            7. detectar la reversión después de una rotación
        """
    
        try:
    
            # ==============================================================
            # VALORACIÓN
            # ==============================================================
    
            valuation = self._value_portfolio(
                portfolio,
                prices
            )
    
            total = float(
                valuation.get(
                    'total',
                    0
                )
                or 0
            )
    
            if total <= 0:
    
                return self._build_response(
                    action='HOLD',
                    reason=(
                        'El TGP no puede evaluar el portfolio '
                        'porque no existe una valoración de mercado válida.'
                    ),
                    confidence=0,
                    portfolio=portfolio,
                    valuation=valuation
                )
    
            pct_btc = float(
                valuation.get(
                    'pct_btc',
                    0
                )
            )
    
            pct_paxg = float(
                valuation.get(
                    'pct_paxg',
                    0
                )
            )
    
            pct_usdt = float(
                valuation.get(
                    'pct_usdt',
                    0
                )
            )

            # ==============================================================
            # FASE 7F.3 — RESTAURAR MEMORIA DESPUÉS DE REINICIO
            # ==============================================================
            #
            # UNA sola lectura por usuario/proceso.
            #
            # Si no existe memoria o Supabase falla:
            # el TGP continúa exactamente como antes.
            # ==============================================================

            self._ensure_rotation_state_loaded(
                user=user,
                portfolio=portfolio,
                pct_btc=pct_btc,
                pct_paxg=pct_paxg,
                pct_usdt=pct_usdt
            )
            
            btc_available = float(
                portfolio.get(
                    'BTC',
                    0
                )
                or 0
            )
    
            paxg_available = float(
                portfolio.get(
                    'PAXG',
                    0
                )
                or 0
            )
    
            usdt_available = float(
                portfolio.get(
                    'USDT',
                    0
                )
                or 0
            )
    
            # ==============================================================
            # TEMPORALIDADES SPOT
            # ==============================================================
    
            timeframes = (
                '4h',
                '12h',
                '1D',
                '1W'
            )
    
            timeframe_results = {}
    
            btc_edges = []
            paxg_edges = []
    
            # ==============================================================
            # EVALUAR CADA TF
            # ==============================================================
    
            for tf in timeframes:
    
                tf_data = (
                    market_snapshots.get(
                        tf,
                        {}
                    )
                    or {}
                )
    
                btc_analysis = (
                    tf_data.get(
                        'BTC-USDT'
                    )
                )
    
                paxg_analysis = (
                    tf_data.get(
                        'PAXG-USDT'
                    )
                )
    
                ratio_analysis = (
                    tf_data.get(
                        'PAXG-BTC'
                    )
                )
    
                btc_score = (
                    self._score_market_snapshot(
                        btc_analysis,
                        'BTC'
                    )
                )
    
                paxg_score = (
                    self._score_market_snapshot(
                        paxg_analysis,
                        'PAXG'
                    )
                )
    
                ratio_btc_edge = (
                    self._score_ratio_for_assets(
                        ratio_analysis
                    )
                )
    
                # ==========================================================
                # EDGE RELATIVO
                # ==========================================================
                #
                # positivo → BTC
                # negativo → PAXG
                # ==========================================================
    
                relative_edge = (
                    btc_score * 0.45
                    -
                    paxg_score * 0.30
                    +
                    ratio_btc_edge * 0.25
                )
    
                relative_edge = max(
                    -100,
                    min(
                        100,
                        relative_edge
                    )
                )
    
                # ==========================================================
                # DIRECCIÓN DEL TF
                # ==========================================================
    
                if relative_edge >= self.ROTATION_EDGE_THRESHOLD:
    
                    preference = 'BTC'
    
                elif relative_edge <= -self.ROTATION_EDGE_THRESHOLD:
    
                    preference = 'PAXG'
    
                else:
    
                    preference = 'NEUTRAL'
    
                # ==========================================================
                # CALIDAD DEL TF
                # ==========================================================
    
                analyses_available = sum(
                    1
                    for x in (
                        btc_analysis,
                        paxg_analysis,
                        ratio_analysis
                    )
                    if isinstance(
                        x,
                        dict
                    )
                )
    
                data_quality = (
                    analyses_available
                    / 3
                    * 100
                )
    
                timeframe_results[tf] = {
                    'btc_score': round(
                        btc_score,
                        1
                    ),
    
                    'paxg_score': round(
                        paxg_score,
                        1
                    ),
    
                    'ratio_btc_edge': round(
                        ratio_btc_edge,
                        1
                    ),
    
                    'relative_edge': round(
                        relative_edge,
                        1
                    ),
    
                    'preference': preference,
    
                    'data_quality': round(
                        data_quality,
                        1
                    )
                }
    
                if (
                    relative_edge
                    >= self.ROTATION_EDGE_THRESHOLD
                ):
                    btc_edges.append(
                        tf
                    )
    
                elif (
                    relative_edge
                    <= -self.ROTATION_EDGE_THRESHOLD
                ):
                    paxg_edges.append(
                        tf
                    )
    
            # ==============================================================
            # MEJOR TF
            # ==============================================================
    
            valid_tf = [
                (
                    tf,
                    data
                )
                for tf, data
                in timeframe_results.items()
                if data[
                    'data_quality'
                ] >= 66.0
            ]
    
            if valid_tf:
    
                best_tf, best_tf_data = max(
                    valid_tf,
                    key=lambda x:
                        abs(
                            x[1][
                                'relative_edge'
                            ]
                        )
                )
    
            else:
    
                best_tf = None
                best_tf_data = None
    
            # ==============================================================
            # CONSENSO MULTI-TF
            # ==============================================================
    
            btc_count = len(
                btc_edges
            )
    
            paxg_count = len(
                paxg_edges
            )
    
            # --------------------------------------------------------------
            # CONFIRMACIÓN MAYOR
            # --------------------------------------------------------------
    
            # ==============================================================
            # CONTEXTO DE TEMPORALIDADES MAYORES
            # ==============================================================
            
            higher_timeframes = [
                tf
                for tf in (
                    '1D',
                    '1W'
                )
                if tf in timeframe_results
            ]
            
            # --------------------------------------------------------------
            # Si no existe ningún TF mayor disponible, NO asumir
            # automáticamente que está confirmado.
            # --------------------------------------------------------------
            
            if higher_timeframes:
            
                higher_btc = all(
                    timeframe_results[
                        tf
                    ].get(
                        'preference'
                    ) != 'PAXG'
            
                    for tf
                    in higher_timeframes
                )
            
                higher_paxg = all(
                    timeframe_results[
                        tf
                    ].get(
                        'preference'
                    ) != 'BTC'
            
                    for tf
                    in higher_timeframes
                )
            
            else:
            
                higher_btc = False
                higher_paxg = False
    
            # ==============================================================
            # DECISIÓN DE ROTACIÓN
            # ==============================================================
    
            action = 'HOLD'
            reason = ''
            confidence = 50
            trade_size = 0
            amount_crypto = 0
            amount_usd = 0
            source_asset = None
            target_asset = None
    
            # ==============================================================
            # BTC
            # ==============================================================
    
            if (
                btc_count
                >= self.MIN_ROTATION_TIMEFRAMES
            ) and higher_btc:
    
                # ----------------------------------------------------------
                # PAXG → BTC
                # ----------------------------------------------------------
    
                if (
                    pct_paxg
                    > self.MIN_RESERVE_PCTS['PAXG']
                    and paxg_available > 0
                ):
    
                    size = self._calc_trade_size(
                        'PAXG',
                        75,
                        pct_paxg,
                        self.TARGET_PCTS['PAXG'],
                        0.8
                    )
    
                    if size > 0:
    
                        amount_crypto = (
                            paxg_available
                            * size
                        )
    
                        amount_usd = (
                            amount_crypto
                            * valuation[
                                'paxg_price'
                            ]
                        )
    
                        btc_price = (
                            valuation[
                                'btc_price'
                            ]
                        )
    
                        amount_btc = (
                            amount_usd
                            / btc_price
                            if btc_price > 0
                            else 0
                        )
    
                        action = (
                            'SWAP_PAXG_TO_BTC'
                        )
    
                        trade_size = size
    
                        source_asset = 'PAXG'
                        target_asset = 'BTC'
    
                        confidence = min(
                            95,
                            65
                            + (
                                btc_count
                                * 5
                            )
                            + max(
                                0,
                                best_tf_data[
                                    'relative_edge'
                                ]
                                if best_tf_data
                                else 0
                            ) * 0.10
                        )
    
                        reason = (
                            f'El TGP compara las cuatro '
                            f'temporalidades Spot y encuentra '
                            f'fortaleza relativa de BTC en '
                            f'{btc_count}/4 TF. '
                            f'Best TF={best_tf}. '
                            f'La rotación PAXG→BTC busca '
                            f'recuperar/acumular satoshis '
                            f'sin vaciar la reserva de oro.'
                        )
    
            # ==============================================================
            # PAXG
            # ==============================================================
    
            if (
                action == 'HOLD'
                and paxg_count
                >= self.MIN_ROTATION_TIMEFRAMES
                and higher_paxg
            ):
    
                if (
                    pct_btc
                    > self.MIN_RESERVE_PCTS['BTC']
                    and btc_available > 0
                ):
    
                    size = self._calc_trade_size(
                        'BTC',
                        75,
                        pct_btc,
                        self.TARGET_PCTS['BTC'],
                        0.8
                    )
    
                    if size > 0:
    
                        amount_crypto = (
                            btc_available
                            * size
                        )
    
                        amount_usd = (
                            amount_crypto
                            * valuation[
                                'btc_price'
                            ]
                        )
    
                        action = (
                            'SWAP_BTC_TO_PAXG'
                        )
    
                        trade_size = size
    
                        source_asset = 'BTC'
                        target_asset = 'PAXG'
    
                        confidence = min(
                            95,
                            65
                            + (
                                paxg_count
                                * 5
                            )
                            + max(
                                0,
                                -best_tf_data[
                                    'relative_edge'
                                ]
                                if best_tf_data
                                else 0
                            ) * 0.10
                        )
    
                        reason = (
                            f'El TGP compara las cuatro '
                            f'temporalidades Spot y encuentra '
                            f'fortaleza relativa de PAXG en '
                            f'{paxg_count}/4 TF. '
                            f'Best TF={best_tf}. '
                            f'La rotación BTC→PAXG protege '
                            f'capital ante un entorno favorable '
                            f'al oro sin eliminar la reserva de BTC.'
                        )
    
            # ==============================================================
            # COMPRAR BTC CON USDT
            # ==============================================================
            if (
                action == 'HOLD'
                and btc_count
                >= self.MIN_ROTATION_TIMEFRAMES
                and usdt_available > 0
            ):
    
                usable_usdt = max(
                    0,
                    usdt_available
                    - (
                        total
                        * self.MIN_RESERVE_PCTS[
                            'USDT'
                        ]
                    )
                )
    
                if usable_usdt > 0:
    
                    size = min(
                        0.35,
                        max(
                            0.08,
                            btc_count / 10
                        )
                    )
    
                    amount_usd = (
                        usable_usdt
                        * size
                    )
    
                    btc_price = (
                        valuation[
                            'btc_price'
                        ]
                    )
    
                    if btc_price > 0:
    
                        action = 'BUY_BTC'
                        trade_size = size
    
                        amount_crypto = (
                            amount_usd
                            / btc_price
                        )
    
                        source_asset = 'USDT'
                        target_asset = 'BTC'
    
                        confidence = min(
                            90,
                            60 + btc_count * 7
                        )
    
                        reason = (
                            f'El TGP detecta ventaja '
                            f'multitemporal de BTC y utiliza '
                            f'USDT disponible sin consumir '
                            f'la reserva mínima de liquidez.'
                        )
    
            # ==============================================================
            # COMPRAR PAXG CON USDT
            # ==============================================================
            if (
                action == 'HOLD'
                and paxg_count
                >= self.MIN_ROTATION_TIMEFRAMES
                and usdt_available > 0
            ):
    
                usable_usdt = max(
                    0,
                    usdt_available
                    - (
                        total
                        * self.MIN_RESERVE_PCTS[
                            'USDT'
                        ]
                    )
                )
    
                if usable_usdt > 0:
    
                    size = min(
                        0.35,
                        max(
                            0.08,
                            paxg_count / 10
                        )
                    )
    
                    amount_usd = (
                        usable_usdt
                        * size
                    )
    
                    paxg_price = (
                        valuation[
                            'paxg_price'
                        ]
                    )
    
                    if paxg_price > 0:
    
                        action = 'BUY_PAXG'
                        trade_size = size
    
                        amount_crypto = (
                            amount_usd
                            / paxg_price
                        )
    
                        source_asset = 'USDT'
                        target_asset = 'PAXG'
    
                        confidence = min(
                            90,
                            60 + paxg_count * 7
                        )
    
                        reason = (
                            f'El TGP detecta ventaja '
                            f'multitemporal de PAXG y utiliza '
                            f'USDT disponible sin eliminar '
                            f'la reserva de liquidez.'
                        )
    
            # ==============================================================
            # NO HAY ROTACIÓN
            # ==============================================================
    
            if action == 'HOLD':
    
                if best_tf:
    
                    reason = (
                        f'No existe consenso suficiente '
                        f'para rotación estratégica. '
                        f'Mejor escenario actual: {best_tf} '
                        f'con preferencia '
                        f'{best_tf_data["preference"]}. '
                        f'El TGP conserva BTC, PAXG y USDT '
                        f'hasta que exista una ventaja relativa '
                        f'más clara.'
                    )
    
                else:
    
                    reason = (
                        'No hay suficientes análisis Spot '
                        'recientes para tomar una decisión '
                        'multitemporal segura.'
                    )
    
            # ==============================================================
            # RESPUESTA
            # ==============================================================

            # ==============================================================
            # FASE 7F.1 — ANTI-WHIPSAW DE ROTACIONES BTC ↔ PAXG
            # ==============================================================
            #
            # Se aplica DESPUÉS de que 7B haya terminado todo el
            # análisis multitemporal.
            #
            # Por tanto:
            #
            # 7F NO genera una señal nueva.
            #
            # Únicamente puede:
            #
            #     SWAP → HOLD
            #
            # cuando detecta riesgo de giro repetitivo.
            # ==============================================================

            rotation_guard = (
                self._apply_rotation_anti_whipsaw(
                    user=user,
                    action=action,
                    reason=reason,
                    confidence=confidence,
                    btc_count=btc_count,
                    paxg_count=paxg_count,
                    best_tf_data=best_tf_data
                )
            )
            # ==============================================================
            # FASE 7F.3 — PERSISTENCIA BEST-EFFORT
            # ==============================================================
            #
            # Si el estado no cambió:
            #     0 escrituras.
            #
            # Si cambió:
            #     1 UPDATE pequeño.
            #
            # Si Supabase falla:
            #     memoria RAM continúa funcionando.
            # ==============================================================

            self._persist_rotation_state_if_dirty(
                user
            )
            if not rotation_guard.get(
                'allowed',
                True
            ):

                action = 'HOLD'

                reason = str(
                    rotation_guard.get(
                        'reason',
                        reason
                    )
                )

                confidence = float(
                    rotation_guard.get(
                        'confidence',
                        confidence
                    )
                    or confidence
                )

                # ======================================================
                # HOLD NO DEBE SIMULAR UNA OPERACIÓN
                # ======================================================

                trade_size = 0
                amount_crypto = 0
                amount_usd = 0

                source_asset = None
                target_asset = None

            # ==============================================================
            # FASE 7F.2 — RETORNO GRADUAL A BTC
            # ==============================================================
            #
            # Se ejecuta DESPUÉS del anti-whipsaw.
            #
            # Si 7F.1 convirtió la señal en HOLD,
            # este bloque simplemente no hará nada.
            # ==============================================================

            gradual_btc_reentry = (
                self._build_gradual_btc_reentry_plan(
                    user=user,
                    action=action,
                    proposed_trade_size=trade_size,
                    pct_btc=pct_btc,
                    pct_paxg=pct_paxg,
                    pct_usdt=pct_usdt,
                    btc_count=btc_count,
                    best_tf_data=best_tf_data,
                    timeframe_results=timeframe_results
                )
            )

            if gradual_btc_reentry.get(
                'active',
                False
            ):

                original_trade_size = float(
                    trade_size
                    or 0
                )

                adjusted_trade_size = float(
                    gradual_btc_reentry.get(
                        'adjusted_trade_size',
                        original_trade_size
                    )
                    or 0
                )

                # ======================================================
                # GUARDRAIL FINAL
                # ======================================================
                #
                # Incluso aunque el helper tuviera un bug:
                #
                # 7F.2 JAMÁS puede aumentar el tamaño.
                # ======================================================

                adjusted_trade_size = min(
                    original_trade_size,
                    adjusted_trade_size
                )

                adjusted_trade_size = max(
                    0.0,
                    adjusted_trade_size
                )

                trade_size = (
                    adjusted_trade_size
                )

                # ======================================================
                # RECALCULAR CANTIDADES
                # ======================================================

                if (
                    action
                    == 'SWAP_PAXG_TO_BTC'
                ):

                    amount_crypto = (
                        paxg_available
                        * trade_size
                    )

                    amount_usd = (
                        amount_crypto
                        * float(
                            valuation.get(
                                'paxg_price',
                                0
                            )
                            or 0
                        )
                    )

                elif action == 'BUY_BTC':

                    # Mantener intacta la reserva mínima USDT.
                    usable_usdt_reentry = max(
                        0.0,
                        usdt_available
                        -
                        (
                            total
                            * self.MIN_RESERVE_PCTS[
                                'USDT'
                            ]
                        )
                    )

                    amount_usd = (
                        usable_usdt_reentry
                        * trade_size
                    )

                    btc_price_reentry = float(
                        valuation.get(
                            'btc_price',
                            0
                        )
                        or 0
                    )

                    amount_crypto = (
                        amount_usd
                        / btc_price_reentry
                        if btc_price_reentry > 0
                        else 0
                    )

                # ======================================================
                # EXPLICAR LA REENTRADA
                # ======================================================

                stage = int(
                    gradual_btc_reentry.get(
                        'stage',
                        0
                    )
                    or 0
                )

                reason = (
                    f'{reason} '
                    f'Fase de retorno gradual BTC={stage}/3: '
                    f'el tamaño original era '
                    f'{original_trade_size * 100:.1f}% '
                    f'del activo fuente y el límite actual '
                    f'es {trade_size * 100:.1f}%. '
                    f'Confirmación BTC='
                    f'{gradual_btc_reentry.get("btc_timeframe_count", 0)}/4 TF, '
                    f'1D/1W directos='
                    f'{gradual_btc_reentry.get("higher_btc_count", 0)}/2, '
                    f'edge={gradual_btc_reentry.get("best_btc_edge", 0):.1f}. '
                    f'El retorno se hace por tramos para evitar '
                    f'abandonar la defensa de una sola vez.'
                )
            
            rec = self._build_response(
                action=action,
                reason=reason,
                confidence=confidence,
                trade_size_pct=trade_size,
                amount_crypto=amount_crypto,
                amount_usd=amount_usd,
                source_asset=source_asset,
                target_asset=target_asset,
                portfolio=portfolio,
                valuation=valuation
            )

             # ==============================================================
            # FASE 7F.1
            # ==============================================================

            rec[
                'rotation_guard'
            ] = {
                'active':
                    bool(
                        rotation_guard.get(
                            'active',
                            False
                        )
                    ),

                'allowed':
                    bool(
                        rotation_guard.get(
                            'allowed',
                            True
                        )
                    ),

                'direction':
                    rotation_guard.get(
                        'direction'
                    ),

                'previous_direction':
                    rotation_guard.get(
                        'previous_direction'
                    ),

                'reversal_required':
                    bool(
                        rotation_guard.get(
                            'reversal_required',
                            False
                        )
                    ),

                'reversal_confirmed':
                    bool(
                        rotation_guard.get(
                            'reversal_confirmed',
                            False
                        )
                    ),

                'cooldown_remaining_minutes':
                    float(
                        rotation_guard.get(
                            'cooldown_remaining_minutes',
                            0
                        )
                        or 0
                    )
            }           
            # ==============================================================
            # FASE 7F.2 — RETORNO GRADUAL BTC
            # ==============================================================

            rec[
                'gradual_btc_reentry'
            ] = {
                'active':
                    bool(
                        gradual_btc_reentry.get(
                            'active',
                            False
                        )
                    ),

                'stage':
                    int(
                        gradual_btc_reentry.get(
                            'stage',
                            0
                        )
                        or 0
                    ),

                'proposed_trade_size':
                    float(
                        gradual_btc_reentry.get(
                            'proposed_trade_size',
                            0
                        )
                        or 0
                    ),

                'max_trade_size':
                    float(
                        gradual_btc_reentry.get(
                            'max_trade_size',
                            0
                        )
                        or 0
                    ),

                'adjusted_trade_size':
                    float(
                        gradual_btc_reentry.get(
                            'adjusted_trade_size',
                            0
                        )
                        or 0
                    ),

                'btc_timeframe_count':
                    int(
                        gradual_btc_reentry.get(
                            'btc_timeframe_count',
                            0
                        )
                        or 0
                    ),

                'higher_btc_count':
                    int(
                        gradual_btc_reentry.get(
                            'higher_btc_count',
                            0
                        )
                        or 0
                    ),

                'best_btc_edge':
                    float(
                        gradual_btc_reentry.get(
                            'best_btc_edge',
                            0
                        )
                        or 0
                    ),

                'portfolio_defensive':
                    bool(
                        gradual_btc_reentry.get(
                            'portfolio_defensive',
                            False
                        )
                    ),

                'recent_defensive_memory':
                    bool(
                        gradual_btc_reentry.get(
                            'recent_defensive_memory',
                            False
                        )
                    )
            }            
            rec['timeframe_analysis'] = (
                timeframe_results
            )
    
            rec['best_timeframe'] = (
                best_tf
            )
    
            rec['btc_timeframe_count'] = (
                btc_count
            )
    
            rec['paxg_timeframe_count'] = (
                paxg_count
            )
    
            rec['tgp_mode'] = (
                'MULTI_TIMEFRAME'
            )
    
            rec['reserves'] = {
                'BTC': self.MIN_RESERVE_PCTS['BTC'],
                'PAXG': self.MIN_RESERVE_PCTS['PAXG'],
                'USDT': self.MIN_RESERVE_PCTS['USDT']
            }
    
            return rec
    
        except Exception as e:
    
            logger.error(
                f"TGP multi-timeframe error: {e}"
            )
    
            return self._build_response(
                action='HOLD',
                reason=(
                    f'Error interno del TGP '
                    f'multitemporal: {str(e)}'
                ),
                confidence=0,
                portfolio=portfolio,
                valuation=self._value_portfolio(
                    portfolio,
                    prices
                )
            )

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
        # ==============================================================
        # LÍMITE POR RESERVA ESTRATÉGICA
        # ==============================================================
        
        reserve_pct = self.MIN_RESERVE_PCTS.get(
            source_asset,
            0.0
        )
                
        # Si la fuente ya está en o por debajo de la reserva,
        # no se puede seguir vendiendo/cambiando.
        if current_pct <= reserve_pct:
        
            return 0.0
        
        # Porcentaje máximo del ACTIVO FUENTE que podemos utilizar
        # sin romper la reserva.
        max_source_trade_pct = (
            current_pct - reserve_pct
        ) / current_pct
        
        max_source_trade_pct = max(
            0.0,
            min(
                1.0,
                max_source_trade_pct
            )
        )
        
        allowed_size = min(
            self.MAX_TRADE_PCT,
            max_source_trade_pct
        )
        
        # Si ni siquiera alcanza el tamaño mínimo de operación,
        # no recomendar operación.
        if allowed_size < self.MIN_TRADE_PCT:
        
            return 0.0
        
        return min(
            allowed_size,
            max(
                self.MIN_TRADE_PCT,
                raw_size
            )
        )
    def _calculate_futures_excursion(
        self,
        signal,
        highs,
        lows
    ):
        """
        Calcula MFE/MAE de la ventana disponible.
    
        MFE:
            máximo movimiento favorable.
    
        MAE:
            máximo movimiento adverso.
    
        No es todavía el MFE/MAE histórico completo desde
        entry_at; es la excursión observable en la ventana
        de velas entregada al Guardian.
        """
    
        try:
    
            action = str(
                signal.get(
                    'action',
                    ''
                )
            ).upper()
    
            entry = float(
                signal.get(
                    'entry',
                    0
                )
                or 0
            )
    
            if (
                entry <= 0
                or not highs
                or not lows
            ):
                return {
                    'mfe_pct': 0.0,
                    'mae_pct': 0.0,
                    'mfe_price': entry,
                    'mae_price': entry
                }
    
            highs = [
                float(x)
                for x in highs
                if x is not None
            ]
    
            lows = [
                float(x)
                for x in lows
                if x is not None
            ]
    
            if not highs or not lows:
                return {
                    'mfe_pct': 0.0,
                    'mae_pct': 0.0,
                    'mfe_price': entry,
                    'mae_price': entry
                }
    
            if action == 'LONG':
    
                mfe_price = max(
                    highs
                )
    
                mae_price = min(
                    lows
                )
    
                mfe_pct = max(
                    0.0,
                    (
                        mfe_price
                        - entry
                    )
                    / entry
                    * 100
                )
    
                mae_pct = max(
                    0.0,
                    (
                        entry
                        - mae_price
                    )
                    / entry
                    * 100
                )
    
            else:
    
                mfe_price = min(
                    lows
                )
    
                mae_price = max(
                    highs
                )
    
                mfe_pct = max(
                    0.0,
                    (
                        entry
                        - mfe_price
                    )
                    / entry
                    * 100
                )
    
                mae_pct = max(
                    0.0,
                    (
                        mae_price
                        - entry
                    )
                    / entry
                    * 100
                )
    
            return {
                'mfe_pct': round(
                    mfe_pct,
                    4
                ),
    
                'mae_pct': round(
                    mae_pct,
                    4
                ),
    
                'mfe_price':
                    mfe_price,
    
                'mae_price':
                    mae_price
            }
    
        except Exception as e:
    
            logger.debug(
                f'Excursión Futures: {e}'
            )
    
            return {
                'mfe_pct': 0.0,
                'mae_pct': 0.0,
                'mfe_price':
                    signal.get(
                        'entry',
                        0
                    ),
    
                'mae_price':
                    signal.get(
                        'entry',
                        0
                    )
            }
    def evaluate_futures_position(
        self,
        signal,
        current_price,
        candles
    ):
        """
        Futures Position Guardian.
    
        Sólo asesora:
            HOLD
            REDUCE
            EXIT
            WAIT_ENTRY
    
        NO ejecuta cierres automáticamente.
    
        Evalúa:
            - tiempo transcurrido
            - progreso hacia TP
            - distancia al SL
            - momentum
            - estructura
            - MFE/MAE de la ventana disponible
    
        Diseñado para ser ligero en Render Free.
        """
    
        try:
    
            if not isinstance(signal, dict):
    
                return {
                    'action': 'HOLD',
                    'severity': 'NONE',
                    'reason': 'Señal inválida.'
                }
    
            status = str(
                signal.get(
                    'status',
                    ''
                )
            ).lower()
    
            # ----------------------------------------------------------
            # WAIT_ENTRY
            # ----------------------------------------------------------
            if status != 'entry_touched':
    
                return {
                    'action': 'WAIT_ENTRY',
                    'severity': 'NONE',
                    'reason': (
                        'La señal todavía no ha tocado el ENTRY. '
                        'El Guardian comenzará a gestionar la posición '
                        'cuando la entrada quede activada.'
                    )
                }
    
            action = str(
                signal.get(
                    'action',
                    ''
                )
            ).upper()
    
            entry = float(
                signal.get(
                    'entry',
                    signal.get(
                        'entry_price',
                        0
                    )
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
    
            tp = float(
                signal.get(
                    'take_profit',
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
                entry <= 0
                or sl <= 0
                or tp <= 0
                or current_price <= 0
            ):
    
                return {
                    'action': 'HOLD',
                    'severity': 'NONE',
                    'reason': (
                        'La posición no tiene ENTRY, SL, TP '
                        'o precio actual válidos.'
                    )
                }
    
            # ==========================================================
            # TIEMPO TRANSCURRIDO
            # ==========================================================
    
            raw_entry_at = (
                signal.get(
                    'entry_at'
                )
                or signal.get(
                    'created_at'
                )
            )
    
            elapsed_minutes = 0.0
    
            if raw_entry_at:
    
                try:
    
                    from datetime import (
                        datetime,
                        timezone
                    )
    
                    parsed = datetime.fromisoformat(
                        str(
                            raw_entry_at
                        ).replace(
                            'Z',
                            '+00:00'
                        )
                    )
    
                    if parsed.tzinfo is None:
    
                        parsed = parsed.replace(
                            tzinfo=timezone.utc
                        )
    
                    elapsed_minutes = max(
                        0.0,
                        (
                            datetime.now(
                                timezone.utc
                            )
                            - parsed
                        ).total_seconds()
                        / 60.0
                    )
    
                except Exception:
    
                    elapsed_minutes = 0.0
    
            timeframe = str(
                signal.get(
                    'timeframe',
                    '1h'
                )
            )
    
            # ==========================================================
            # TIEMPO MODERADO
            # ==========================================================
    
            moderate_minutes = {
    
                '5m': 45,
                '15m': 90,
                '30m': 150,
                '1h': 240,
                '2h': 480,
                '4h': 720
    
            }.get(
                timeframe,
                240
            )
    
            # ==========================================================
            # DISTANCIAS
            # ==========================================================
    
            sl_distance_pct = (
                abs(
                    entry - sl
                )
                / entry
                * 100
            )
    
            tp_distance_pct = (
                abs(
                    tp - entry
                )
                / entry
                * 100
            )
    
            # ==========================================================
            # PROGRESO ACTUAL
            # ==========================================================
    
            if action == 'LONG':
    
                favorable_pct = max(
                    0.0,
                    (
                        current_price
                        - entry
                    )
                    / entry
                    * 100
                )
    
                adverse_pct = max(
                    0.0,
                    (
                        entry
                        - current_price
                    )
                    / entry
                    * 100
                )
    
                remaining_to_tp_pct = max(
                    0.0,
                    (
                        tp
                        - current_price
                    )
                    / entry
                    * 100
                )
    
            else:
    
                favorable_pct = max(
                    0.0,
                    (
                        entry
                        - current_price
                    )
                    / entry
                    * 100
                )
    
                adverse_pct = max(
                    0.0,
                    (
                        current_price
                        - entry
                    )
                    / entry
                    * 100
                )
    
                remaining_to_tp_pct = max(
                    0.0,
                    (
                        current_price
                        - tp
                    )
                    / entry
                    * 100
                )
    
            # ==========================================================
            # VELAS
            # ==========================================================
    
            closes = []
            highs = []
            lows = []
    
            if isinstance(candles, dict):
    
                closes = [
                    float(x)
                    for x in (
                        candles.get(
                            'close',
                            []
                        )
                        or []
                    )
                    if x is not None
                ]
    
                highs = [
                    float(x)
                    for x in (
                        candles.get(
                            'high',
                            []
                        )
                        or []
                    )
                    if x is not None
                ]
    
                lows = [
                    float(x)
                    for x in (
                        candles.get(
                            'low',
                            []
                        )
                        or []
                    )
                    if x is not None
                ]
    
            closes = closes[-20:]
            highs = highs[-20:]
            lows = lows[-20:]
            # ==============================================================
            # MFE / MAE OBSERVABLE
            # ==============================================================
            
            excursion = (
                self._calculate_futures_excursion(
                    signal=signal,
                    highs=highs,
                    lows=lows
                )
            )
            
            mfe_pct = excursion[
                'mfe_pct'
            ]
            
            mae_pct = excursion[
                'mae_pct'
            ]
            
            mfe_price = excursion[
                'mfe_price'
            ]
            
            mae_price = excursion[
                'mae_price'
            ]    
            # ==========================================================
            # MFE / MAE DE LA VENTANA DISPONIBLE
            # ==========================================================
    
            mfe_pct = 0.0
            mae_pct = 0.0
    
            if highs and lows:
    
                if action == 'LONG':
    
                    highest = max(
                        highs
                    )
    
                    lowest = min(
                        lows
                    )
    
                    mfe_pct = max(
                        0.0,
                        (
                            highest
                            - entry
                        )
                        / entry
                        * 100
                    )
    
                    mae_pct = max(
                        0.0,
                        (
                            entry
                            - lowest
                        )
                        / entry
                        * 100
                    )
    
                else:
    
                    lowest = min(
                        lows
                    )
    
                    highest = max(
                        highs
                    )
    
                    mfe_pct = max(
                        0.0,
                        (
                            entry
                            - lowest
                        )
                        / entry
                        * 100
                    )
    
                    mae_pct = max(
                        0.0,
                        (
                            highest
                            - entry
                        )
                        / entry
                        * 100
                    )
    
            # ==========================================================
            # MOMENTUM RECIENTE
            # ==========================================================
    
            recent_change_pct = 0.0
            fast_avg = current_price
            slow_avg = current_price
    
            if len(closes) >= 6:
    
                recent_change_pct = (
                    (
                        closes[-1]
                        - closes[-6]
                    )
                    / closes[-6]
                    * 100
                )
    
                fast_values = closes[-5:]
                slow_values = closes[-10:]
    
                fast_avg = (
                    sum(
                        fast_values
                    )
                    / len(
                        fast_values
                    )
                )
    
                slow_avg = (
                    sum(
                        slow_values
                    )
                    / len(
                        slow_values
                    )
                )
    
            # ==========================================================
            # MOMENTUM CONTRARIO
            # ==========================================================
    
            if action == 'LONG':
    
                momentum_against = (
                    recent_change_pct < -0.20
                    and fast_avg < slow_avg
                )
    
            else:
    
                momentum_against = (
                    recent_change_pct > 0.20
                    and fast_avg > slow_avg
                )
    
            # ==========================================================
            # ESTANCAMIENTO
            # ==========================================================
    
            min_progress = max(
                0.15,
                tp_distance_pct * 0.15
            )
    
            stagnant = (
                elapsed_minutes
                >= moderate_minutes
                and favorable_pct
                < min_progress
            )
    
            # ==========================================================
            # DETERIORO ESTRUCTURAL SIMPLE
            # ==========================================================
    
            structure_deteriorated = False
    
            if len(closes) >= 8:
    
                recent_high = max(
                    closes[-5:]
                )
    
                recent_low = min(
                    closes[-5:]
                )
    
                previous_high = max(
                    closes[-10:-5]
                )
    
                previous_low = min(
                    closes[-10:-5]
                )
    
                if action == 'LONG':
    
                    structure_deteriorated = (
                        recent_high
                        < previous_high
                        and recent_low
                        < previous_low
                    )
    
                else:
    
                    structure_deteriorated = (
                        recent_high
                        > previous_high
                        and recent_low
                        > previous_low
                    )
    
            # ==========================================================
            # SCORE DE DETERIORO
            # ==========================================================
    
            deterioration_score = 0
    
            if stagnant:
    
                deterioration_score += 30
                # ==============================================================
                # MFE INSUFICIENTE
                # ==============================================================
                
                # Si la operación ya lleva un tiempo razonable pero
                # prácticamente nunca consiguió avanzar a favor,
                # aumenta la probabilidad de salida preventiva.
                
                expected_progress = max(
                    0.20,
                    tp_distance_pct * 0.20
                )
                
                if (
                    elapsed_minutes >= moderate_minutes
                    and mfe_pct < expected_progress
                ):
                
                    deterioration_score += 20                
    
            if momentum_against:
    
                deterioration_score += 30
                # ==============================================================
                # MAE ELEVADO SIN RECUPERACIÓN
                # ==============================================================
                
                if (
                    elapsed_minutes >= moderate_minutes
                    and mae_pct >= sl_distance_pct * 0.75
                    and mfe_pct < tp_distance_pct * 0.25
                ):
                
                    deterioration_score += 20
    
            if structure_deteriorated:
    
                deterioration_score += 30
    
            if (
                elapsed_minutes
                >= moderate_minutes * 1.5
                and favorable_pct
                < max(
                    0.20,
                    tp_distance_pct * 0.20
                )
            ):
    
                deterioration_score += 15
    
            deterioration_score = min(
                100,
                deterioration_score
            )
    
            # ==========================================================
            # TEXTO COMÚN
            # ==========================================================
    
            metrics = {
                'deterioration_score':
                    deterioration_score,
    
                'elapsed_minutes':
                    round(
                        elapsed_minutes,
                        1
                    ),
    
                'favorable_pct':
                    round(
                        favorable_pct,
                        3
                    ),
    
                'adverse_pct':
                    round(
                        adverse_pct,
                        3
                    ),
    
                'remaining_to_tp_pct':
                    round(
                        remaining_to_tp_pct,
                        3
                    ),
    
                'mfe_pct':
                    round(
                        mfe_pct,
                        3
                    ),
    
                'mae_pct':
                    round(
                        mae_pct,
                        3
                    ),
    
                'tp_distance_pct':
                    round(
                        tp_distance_pct,
                        3
                    ),
    
                'sl_distance_pct':
                    round(
                        sl_distance_pct,
                        3
                    ),
    
                'leverage':
                    int(
                        leverage
                    )
            }
    
            # ==========================================================
            # EXIT
            # ==========================================================
    
            if deterioration_score >= 75:
    
                return {
                    'action': 'EXIT',
                    'severity': 'HIGH',
                    'mfe_pct':
                        mfe_pct,
                    
                    'mae_pct':
                        mae_pct,
                    
                    'mfe_price':
                        mfe_price,
                    
                    'mae_price':
                        mae_price,    

                    'reason': (
                        f'La posición {action} lleva '
                        f'{elapsed_minutes:.0f} min. '
                        f'MFE observado: {mfe_pct:.2f}%. '
                        f'MAE observado: {mae_pct:.2f}%. '
                        f'El progreso hacia TP es insuficiente '
                        f'y se detecta deterioro técnico. '
                        f'Se recomienda evaluar cierre antes de '
                        f'que la posición alcance el SL.'
                    ),
    
                    **metrics
                }
    
            # ==========================================================
            # REDUCE / PROTECT
            # ==========================================================
    
            if deterioration_score >= 45:
    
                return {
                    'action': 'REDUCE',
                    'severity': 'MEDIUM',
                    'mfe_pct':
                        mfe_pct,
                    
                    'mae_pct':
                        mae_pct,
                    
                    'mfe_price':
                        mfe_price,
                    
                    'mae_price':
                        mae_price,    
                    'reason': (
                        f'La posición {action} presenta '
                        f'MFE {mfe_pct:.2f}% y MAE {mae_pct:.2f}%. '
                        f'La estructura/momentum muestran deterioro '
                        f'moderado. Conviene considerar reducción '
                        f'parcial o protección de la posición.'
                    ),
    
                    **metrics
                }
    
            # ==========================================================
            # HOLD
            # ==========================================================
    
            return {
                'action': 'HOLD',
                'severity': 'NONE',
                'mfe_pct':
                    mfe_pct,
                
                'mae_pct':
                    mae_pct,
                
                'mfe_price':
                    mfe_price,
                
                'mae_price':
                    mae_price,    
                'reason': (
                    f'La tesis continúa vigente. '
                    f'MFE observado: {mfe_pct:.2f}%. '
                    f'MAE observado: {mae_pct:.2f}%. '
                    f'No existe deterioro suficiente para '
                    f'justificar una salida anticipada.'
                ),
    
                **metrics
            }
    
        except Exception as e:
    
            logger.error(
                f'Futures Position Guardian: {e}'
            )
    
            return {
                'action': 'HOLD',
                'severity': 'NONE',
                'reason': (
                    'No se pudo evaluar la posición '
                    'de forma segura.'
                )
            }
    
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

            # ============================================================
            # VALORACIÓN REAL UTILIZADA POR EL TGP
            # ============================================================
            # El frontend debe usar exactamente los mismos precios,
            # valores y porcentajes que utilizó el Guardián.
            # ============================================================
            'valuation': dict(
                valuation or {}
            ),

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
