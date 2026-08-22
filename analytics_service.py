# analytics_service.py
# Servicio de análisis estadístico del sistema
# Consume Supabase y devuelve datos listos para gráficos Plotly
# Fase B - Backend de la pestaña /analytics

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from supabase_client import supabase_db

logger = logging.getLogger('ANALYTICS')


def _cap_confidence(v):
    """
    Cap defensivo para lectura de confianza desde BD.
    Rows históricos pre-fix pueden contener valores >100 que corrompen la UI.
    """
    try:
        return max(0.0, min(100.0, float(v or 0)))
    except (TypeError, ValueError):
        return 0.0


class AnalyticsService:
    """
    Servicio que agrega estadísticas para el frontend de análisis.
    Todos los métodos aceptan filtros opcionales: symbol, timeframe, system_type, action, days_back.
    """
    
    def __init__(self):
        self.db = supabase_db
    
    # ========================================================================
    # HELPER: construir query de signals con filtros
    # ========================================================================
    
    def _fetch_signals_with_results(self, symbol: str = None, timeframe: str = None,
                                     system_type: str = None, action: str = None,
                                     days_back: int = 90) -> List[Dict]:
        """
        Retorna las señales resueltas (tp_hit, sl_hit, expired) 
        con sus estrategias y resultados agregados.
        """
        if not self.db.enabled:
            return []
        
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
            
            query = (self.db.client.table('signals')
                     .select('*, signal_indicators(strategy_name), signal_results(status, pnl_pct, exit_price, exit_timestamp)')
                     .gte('created_at', cutoff)
                     .neq('status', 'pending'))
            
            if symbol:
                query = query.eq('symbol', symbol)
            if timeframe:
                query = query.eq('timeframe', timeframe)
            if system_type and system_type != 'both':
                query = query.eq('system_type', system_type)
            if action and action != 'ALL':
                query = query.eq('action_normalized', action)
            
            response = query.order('created_at', desc=True).limit(2000).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            return []
    
    # ========================================================================
    # 1. RESUMEN (KPIs globales)
    # ========================================================================
    
    def get_summary(self, symbol: str = None, timeframe: str = None,
                    system_type: str = None, action: str = None,
                    days_back: int = 90) -> Dict:
        """
        Retorna KPIs globales: total señales, win_rate, expectancy, PnL total, etc.
        
        AMPLIADO v13: ahora incluye rendimiento económico completo:
          - pnl_total_pct: suma de todos los PnL % de operaciones resueltas
          - profit_factor: ganancia total / pérdida total (>1 rentable)
          - avg_pnl_per_trade: PnL medio por operación
          - best_trade / worst_trade: extremos
          - consecutive_wins / consecutive_losses: rachas
          - roi_estimated_1000_usd: ROI simulado con capital de 1000 USD
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        total = len(signals)
        tp_count = sum(1 for s in signals if s.get('status') == 'tp_hit')
        sl_count = sum(1 for s in signals if s.get('status') == 'sl_hit')
        expired_count = sum(1 for s in signals if s.get('status') == 'expired')
        missed_count = sum(1 for s in signals if s.get('status') == 'missed_opportunity')
        resolved = tp_count + sl_count
        
        win_rate = (tp_count / resolved * 100) if resolved > 0 else 0
        
        # ============ PnL de operaciones REALES (solo tp_hit / sl_hit) ============
        # Excluir missed_opportunity porque son NO_OPERAR con "PnL teórico" que no
        # es dinero real: contaminan el rendimiento económico del sistema.
        pnl_real_trades = []  # lista de PnL de operaciones que realmente se hicieron
        pnl_by_status_order = []  # para calcular rachas (por fecha)
        
        for s in signals:
            status = s.get('status')
            if status not in ('tp_hit', 'sl_hit'):
                continue
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct')
                if pnl is not None:
                    pnl_val = float(pnl)
                    pnl_real_trades.append(pnl_val)
                    pnl_by_status_order.append((
                        s.get('created_at', ''),
                        status,
                        pnl_val
                    ))
        
        wins_pnl = [p for p in pnl_real_trades if p > 0]
        losses_pnl = [p for p in pnl_real_trades if p < 0]
        
        avg_win = sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0
        avg_loss = abs(sum(losses_pnl) / len(losses_pnl)) if losses_pnl else 0
        
        # ============ EXPECTANCY (real, no asumida) ============
        expectancy = 0
        if resolved > 0:
            expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
        
        # ============ MÉTRICAS ECONÓMICAS ============
        # PnL total acumulado (suma de todos los PnL individuales)
        pnl_total_pct = sum(pnl_real_trades)
        
        # Profit factor: ganancia total / pérdida total
        total_wins = sum(wins_pnl) if wins_pnl else 0
        total_losses = abs(sum(losses_pnl)) if losses_pnl else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else (total_wins if total_wins > 0 else 0)
        
        # PnL promedio por trade
        avg_pnl_per_trade = (pnl_total_pct / len(pnl_real_trades)) if pnl_real_trades else 0
        
        # Mejor y peor trade
        best_trade_pct = max(pnl_real_trades) if pnl_real_trades else 0
        worst_trade_pct = min(pnl_real_trades) if pnl_real_trades else 0
        
        # Rachas (ordenadas cronológicamente)
        pnl_by_status_order.sort(key=lambda x: x[0])
        max_consec_wins = 0
        max_consec_losses = 0
        cur_wins = 0
        cur_losses = 0
        for _, status, _ in pnl_by_status_order:
            if status == 'tp_hit':
                cur_wins += 1
                cur_losses = 0
                max_consec_wins = max(max_consec_wins, cur_wins)
            elif status == 'sl_hit':
                cur_losses += 1
                cur_wins = 0
                max_consec_losses = max(max_consec_losses, cur_losses)
        
        # ROI estimado con capital fijo de 1000 USD y sizing 100% (simulación simple)
        # Cada operación multiplica el capital por (1 + pnl/100)
        # Nota: esto asume que se sale exactamente en el toque, sin slippage
        capital = 1000.0
        for _, _, pnl in pnl_by_status_order:
            capital *= (1 + pnl / 100)
        roi_1000 = ((capital - 1000.0) / 1000.0) * 100
        
        # Estrategias únicas activas
        strategies_seen = set()
        for s in signals:
            si = s.get('signal_indicators', [])
            if isinstance(si, list):
                for entry in si:
                    if isinstance(entry, dict) and entry.get('strategy_name'):
                        strategies_seen.add(entry['strategy_name'])
        
        return {
            'total_signals': total,
            'tp_hit': tp_count,
            'sl_hit': sl_count,
            'expired': expired_count,
            'missed_opportunity': missed_count,
            'resolved': resolved,
            'win_rate': round(win_rate, 2),
            'avg_win_pct': round(avg_win, 3),
            'avg_loss_pct': round(avg_loss, 3),
            'expectancy': round(expectancy, 3),
            'unique_strategies': len(strategies_seen),
            # ============ NUEVAS MÉTRICAS ECONÓMICAS ============
            'pnl_total_pct': round(pnl_total_pct, 2),
            'avg_pnl_per_trade': round(avg_pnl_per_trade, 3),
            'profit_factor': round(profit_factor, 2),
            'best_trade_pct': round(best_trade_pct, 2),
            'worst_trade_pct': round(worst_trade_pct, 2),
            'total_gains_pct': round(total_wins, 2),
            'total_losses_pct': round(-total_losses, 2),
            'max_consecutive_wins': max_consec_wins,
            'max_consecutive_losses': max_consec_losses,
            'roi_1000usd_estimated': round(roi_1000, 2),
            'is_profitable': profit_factor >= 1.0,
            # ============ FIN NUEVAS MÉTRICAS ============
            'days_back': days_back,
            'filters': {
                'symbol': symbol, 'timeframe': timeframe,
                'system_type': system_type, 'action': action
            }
        }
    
    # ========================================================================
    # 2. RANKING DE ESTRATEGIAS
    # ========================================================================
    
    def get_strategies_ranking(self, symbol: str = None, timeframe: str = None,
                                system_type: str = None, action: str = None,
                                days_back: int = 90, top_n: int = 30) -> List[Dict]:
        """
        Ranking de estrategias por win rate. Retorna lista ordenada.
        Formato para gráfico de barras.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Agrupar por estrategia
        strategy_data = defaultdict(lambda: {'wins': 0, 'losses': 0, 'expired': 0, 'pnl_sum': 0.0, 'pnl_count': 0})
        
        for s in signals:
            status = s.get('status')
            si = s.get('signal_indicators', [])
            results_data = s.get('signal_results', [])
            pnl = 0
            if isinstance(results_data, list) and results_data:
                pnl = float(results_data[0].get('pnl_pct', 0) or 0)
            
            if not isinstance(si, list):
                continue
            
            for entry in si:
                if not isinstance(entry, dict):
                    continue
                strategy = entry.get('strategy_name')
                if not strategy:
                    continue
                
                d = strategy_data[strategy]
                if status == 'tp_hit':
                    d['wins'] += 1
                elif status == 'sl_hit':
                    d['losses'] += 1
                elif status == 'expired':
                    d['expired'] += 1
                
                if pnl:
                    d['pnl_sum'] += pnl
                    d['pnl_count'] += 1
        
        # Calcular métricas
        results = []
        for strategy, d in strategy_data.items():
            resolved = d['wins'] + d['losses']
            if resolved == 0:
                continue
            
            win_rate = (d['wins'] / resolved) * 100
            avg_pnl = (d['pnl_sum'] / d['pnl_count']) if d['pnl_count'] > 0 else 0
            
            results.append({
                'strategy': strategy,
                'total': resolved + d['expired'],
                'wins': d['wins'],
                'losses': d['losses'],
                'expired': d['expired'],
                'win_rate': round(win_rate, 2),
                'avg_pnl_pct': round(avg_pnl, 3)
            })
        
        # Ordenar por win_rate DESC, con criterio de desempate (más muestras)
        results.sort(key=lambda x: (-x['win_rate'], -x['total']))
        
        return results[:top_n]
    
    # ========================================================================
    # 3. HEATMAP símbolo × timeframe
    # ========================================================================
    
    def get_heatmap_data(self, system_type: str = None, action: str = None,
                          days_back: int = 90) -> Dict:
        """
        Retorna matriz de win_rates por (symbol, timeframe).
        Formato para gráfico de heatmap.
        """
        signals = self._fetch_signals_with_results(
            symbol=None, timeframe=None, system_type=system_type,
            action=action, days_back=days_back
        )
        
        matrix = defaultdict(lambda: defaultdict(lambda: {'wins': 0, 'losses': 0}))
        
        for s in signals:
            symbol = s.get('symbol')
            tf = s.get('timeframe')
            status = s.get('status')
            if not symbol or not tf:
                continue
            
            if status == 'tp_hit':
                matrix[symbol][tf]['wins'] += 1
            elif status == 'sl_hit':
                matrix[symbol][tf]['losses'] += 1
        
        # Recolectar todas las TF y símbolos únicos
        symbols_set = set()
        tfs_set = set()
        for symbol, tf_data in matrix.items():
            symbols_set.add(symbol)
            for tf in tf_data.keys():
                tfs_set.add(tf)
        
        # Ordenar TF por duración
        tf_order = ['5m', '15m', '30m', '1h', '2h', '4h', '12h', '1D', '1W']
        symbols_list = sorted(symbols_set)
        tfs_list = [tf for tf in tf_order if tf in tfs_set]
        
        # Construir matriz z (rows = symbols, cols = timeframes)
        z_win_rate = []
        z_sample_size = []
        for symbol in symbols_list:
            row_wr = []
            row_ss = []
            for tf in tfs_list:
                cell = matrix[symbol].get(tf, {'wins': 0, 'losses': 0})
                resolved = cell['wins'] + cell['losses']
                if resolved > 0:
                    row_wr.append(round((cell['wins'] / resolved) * 100, 1))
                else:
                    row_wr.append(None)
                row_ss.append(resolved)
            z_win_rate.append(row_wr)
            z_sample_size.append(row_ss)
        
        return {
            'symbols': symbols_list,
            'timeframes': tfs_list,
            'win_rates': z_win_rate,
            'sample_sizes': z_sample_size
        }
    
    # ========================================================================
    # 4. EVOLUCIÓN TEMPORAL (serie de tiempo)
    # ========================================================================
    
    def get_timeline(self, symbol: str = None, timeframe: str = None,
                     system_type: str = None, action: str = None,
                     days_back: int = 90, bucket: str = 'week') -> Dict:
        """
        Retorna evolución del win_rate agrupado por semana (o día).
        Formato para gráfico de líneas.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Agrupar por bucket
        buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total': 0})
        
        for s in signals:
            status = s.get('status')
            ts_str = s.get('created_at')
            if not ts_str or status not in ('tp_hit', 'sl_hit'):
                continue
            
            try:
                # Parsear timestamp
                if 'Z' in ts_str:
                    ts_str = ts_str.replace('Z', '+00:00')
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=None)
                
                if bucket == 'week':
                    # Inicio de semana (lunes)
                    week_start = ts - timedelta(days=ts.weekday())
                    key = week_start.strftime('%Y-%m-%d')
                else:
                    key = ts.strftime('%Y-%m-%d')
                
                if status == 'tp_hit':
                    buckets[key]['wins'] += 1
                elif status == 'sl_hit':
                    buckets[key]['losses'] += 1
                buckets[key]['total'] += 1
            except Exception:
                continue
        
        # Ordenar por fecha
        sorted_keys = sorted(buckets.keys())
        
        return {
            'dates': sorted_keys,
            'win_rates': [
                round((buckets[k]['wins'] / (buckets[k]['wins'] + buckets[k]['losses'])) * 100, 2)
                if (buckets[k]['wins'] + buckets[k]['losses']) > 0 else 0
                for k in sorted_keys
            ],
            'sample_sizes': [buckets[k]['total'] for k in sorted_keys],
            'wins': [buckets[k]['wins'] for k in sorted_keys],
            'losses': [buckets[k]['losses'] for k in sorted_keys]
        }
    
    # ========================================================================
    # 5. DISTRIBUCIÓN DE PnL
    # ========================================================================
    
    def get_pnl_distribution(self, symbol: str = None, timeframe: str = None,
                              system_type: str = None, action: str = None,
                              days_back: int = 90) -> Dict:
        """
        Distribución de PnL: cuántas señales cayeron en cada rango.
        Formato para histograma.
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        pnl_values = []
        for s in signals:
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct', 0)
                if pnl:
                    pnl_values.append(float(pnl))
        
        # Bins predefinidos
        bins = [
            (-float('inf'), -5, '<-5%'),
            (-5, -3, '-5 a -3%'),
            (-3, -2, '-3 a -2%'),
            (-2, -1, '-2 a -1%'),
            (-1, 0, '-1 a 0%'),
            (0, 1, '0 a 1%'),
            (1, 2, '1 a 2%'),
            (2, 3, '2 a 3%'),
            (3, 5, '3 a 5%'),
            (5, float('inf'), '>5%')
        ]
        
        counts = []
        labels = []
        colors = []
        for lo, hi, label in bins:
            count = sum(1 for v in pnl_values if lo <= v < hi)
            counts.append(count)
            labels.append(label)
            # Verde para ganancias, rojo para pérdidas
            if lo >= 0:
                colors.append('#00C076')
            else:
                colors.append('#FF5B5B')
        
        return {
            'labels': labels,
            'counts': counts,
            'colors': colors,
            'total': len(pnl_values),
            'mean': round(sum(pnl_values) / len(pnl_values), 3) if pnl_values else 0,
            'positive': sum(1 for v in pnl_values if v > 0),
            'negative': sum(1 for v in pnl_values if v < 0)
        }
    
    # ========================================================================
    # 6. TOP MEJORES Y PEORES OPERACIONES
    # ========================================================================
    
    def get_top_operations(self, top_n: int = 10, mode: str = 'best',
                            symbol: str = None, timeframe: str = None,
                            system_type: str = None, action: str = None,
                            days_back: int = 90) -> List[Dict]:
        """
        Top N mejores o peores operaciones por PnL.
        mode: 'best' | 'worst'
        """
        signals = self._fetch_signals_with_results(symbol, timeframe, system_type, action, days_back)
        
        # Filtrar solo OPERACIONES REALES resueltas (tp_hit / sl_hit)
        # Antes se incluían missed_opportunity (NO_OPERAR con PnL positivo por
        # movimientos no aprovechados), que aparecían como "TOP mejores" siendo
        # oportunidades no tomadas, no ganancias reales. Ahora solo cuentan
        # operaciones que el sistema recomendó ejecutar y que tocaron TP o SL.
        signals_with_pnl = []
        for s in signals:
            # Excluir missed_opportunity y NO_OPERAR — no son operaciones reales
            status = s.get('status', '')
            if status not in ('tp_hit', 'sl_hit'):
                continue
            action_norm = s.get('action_normalized', '')
            if action_norm not in ('LONG', 'SHORT'):
                continue
            
            results_data = s.get('signal_results', [])
            if isinstance(results_data, list) and results_data:
                pnl = results_data[0].get('pnl_pct')
                if pnl is not None:
                    s['_pnl'] = float(pnl)
                    s['_exit_price'] = results_data[0].get('exit_price')
                    s['_exit_ts'] = results_data[0].get('exit_timestamp')
                    signals_with_pnl.append(s)
        
        # Ordenar
        signals_with_pnl.sort(key=lambda s: s['_pnl'], reverse=(mode == 'best'))
        
        top = signals_with_pnl[:top_n]
        
        result = []
        for s in top:
            # Extraer estrategias
            si = s.get('signal_indicators', [])
            strategies = []
            if isinstance(si, list):
                strategies = [e.get('strategy_name') for e in si if isinstance(e, dict) and e.get('strategy_name')]
            
            result.append({
                'id': s.get('id'),
                'symbol': s.get('symbol'),
                'timeframe': s.get('timeframe'),
                'action': s.get('action_normalized'),
                'confidence': _cap_confidence(s.get('confidence')),
                'entry_price': s.get('entry_price'),
                'stop_loss': s.get('stop_loss'),
                'take_profit': s.get('take_profit'),
                'exit_price': s.get('_exit_price'),
                'pnl_pct': s.get('_pnl'),
                'status': s.get('status'),
                'created_at': s.get('created_at'),
                'exit_at': s.get('_exit_ts'),
                'strategies': strategies,
                'system_type': s.get('system_type')
            })
        
        return result
    
    # ========================================================================
    # 7. DETALLE DE UNA OPERACIÓN
    # ========================================================================
    
    def get_operation_detail(self, signal_id: str) -> Optional[Dict]:
        """Retorna el detalle completo de una señal (para modal de gráfico)"""
        if not self.db.enabled:
            return None
        
        try:
            response = (self.db.client.table('signals')
                        .select('*, signal_indicators(strategy_name, indicator_values), signal_results(*)')
                        .eq('id', signal_id)
                        .limit(1)
                        .execute())
            if not response.data:
                return None
            
            signal = response.data[0]
            si = signal.get('signal_indicators', [])
            strategies = []
            if isinstance(si, list):
                strategies = [e.get('strategy_name') for e in si if isinstance(e, dict)]
            
            results_data = signal.get('signal_results', [])
            result = results_data[0] if isinstance(results_data, list) and results_data else None
            
            return {
                'id': signal.get('id'),
                'symbol': signal.get('symbol'),
                'timeframe': signal.get('timeframe'),
                'system_type': signal.get('system_type'),
                'action': signal.get('action_normalized'),
                'confidence': _cap_confidence(signal.get('confidence')),
                'entry_price': signal.get('entry_price'),
                'stop_loss': signal.get('stop_loss'),
                'take_profit': signal.get('take_profit'),
                'leverage': signal.get('leverage'),
                'risk_reward': signal.get('risk_reward'),
                'current_price_at_signal': signal.get('current_price'),
                'candle_timestamp': signal.get('candle_timestamp'),
                'created_at': signal.get('created_at'),
                'closed_at': signal.get('closed_at'),
                'status': signal.get('status'),
                'strategies': strategies,
                'indicators_snapshot': signal.get('indicators_snapshot', {}),
                'context': signal.get('context', {}),
                'result': result
            }
        except Exception as e:
            logger.error(f"Error obteniendo detalle: {e}")
            return None


# Instancia global
analytics_service = AnalyticsService()
