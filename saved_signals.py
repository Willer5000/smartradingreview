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
    
    Retorna: dict con la fila creada + id, o None si falló.
    """
    db = _get_db()
    if db is None:
        logger.warning("create_saved_signal: Supabase no disponible")
        return None
    
    try:
        action = str(data.get('action', '')).upper()
        if action not in ('LONG', 'SHORT'):
            logger.warning(f"create_saved_signal: acción inválida {action}")
            return None
        
        entry = float(data.get('entry', 0))
        stop_loss = float(data.get('stop_loss', 0))
        take_profit = float(data.get('take_profit', 0))
        leverage = int(data.get('leverage', 1) or 1)
        investment = float(data.get('investment_usdt', 10))
        
        if entry <= 0 or stop_loss <= 0 or take_profit <= 0:
            logger.warning("create_saved_signal: entry/SL/TP inválidos")
            return None
        
        payload = {
            'symbol': str(data.get('symbol', '')),
            'timeframe': str(data.get('timeframe', '')),
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
            'candle_timestamp': data.get('candle_timestamp'),
            'status': 'active',
            'entry_touched': False,
            'notes': str(data.get('notes', '') or '')[:500],
        }
        
        def _op():
            return db.client.table('saved_signals').insert(payload).execute()
        r = db._with_retry(_op)
        
        if r and r.data:
            return r.data[0]
        return None
    except Exception as e:
        logger.error(f"create_saved_signal: {e}")
        return None


def list_saved_signals(status_filter: Optional[List[str]] = None,
                        limit: int = 200) -> List[Dict]:
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
            pnl = {'pct': 0.0, 'usdt': 0.0}
        
        updates = {
            'status': 'closed_manual',
            'closed_at': datetime.utcnow().isoformat(),
            'closed_price': float(current_price),
            'pnl_pct': pnl['pct'],
            'pnl_usdt': pnl['usdt'],
            'close_reason': 'manual',
            'updated_at': datetime.utcnow().isoformat(),
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
        return {'checked': 0, 'entry_touched': 0, 'tp_hit': 0, 'sl_hit': 0}
    
    stats = {'checked': 0, 'entry_touched': 0, 'tp_hit': 0, 'sl_hit': 0, 'errors': 0}
    
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
                
                # Filtrar velas POSTERIORES al created_at de la señal
                import pandas as pd
                created_ts = pd.Timestamp(sig.get('created_at')).tz_convert('UTC') \
                    if pd.Timestamp(sig.get('created_at')).tz else pd.Timestamp(sig.get('created_at'), tz='UTC')
                df_time = pd.to_datetime(df['time'], utc=True) if df['time'].dtype != 'datetime64[ns, UTC]' else df['time']
                df_after = df[df_time > created_ts]
                
                if len(df_after) == 0:
                    # No hay velas nuevas aún
                    continue
                
                # 1. Verificar si tocó entry (si aún no está tocado)
                if not already_touched:
                    for _, row in df_after.iterrows():
                        if _check_entry_touched(entry, float(row['high']), float(row['low']), action):
                            db.client.table('saved_signals').update({
                                'entry_touched': True,
                                'entry_touched_at': datetime.utcnow().isoformat(),
                                'entry_touched_price': entry,
                                'status': 'entry_touched',
                                'updated_at': datetime.utcnow().isoformat(),
                            }).eq('id', sig['id']).execute()
                            already_touched = True
                            stats['entry_touched'] += 1
                            logger.info(f"Entry tocado: {symbol} {tf} {action} @ {entry}")
                            break
                
                # 2. Verificar TP/SL (solo si entry ya se tocó)
                if not already_touched:
                    continue
                
                for _, row in df_after.iterrows():
                    high = float(row['high'])
                    low = float(row['low'])
                    
                    if action == 'LONG':
                        # LONG: SL abajo, TP arriba
                        if low <= sl:
                            # SL golpeado
                            pnl = _calc_pnl(entry, sl, leverage, investment, action)
                            db.client.table('saved_signals').update({
                                'status': 'sl_hit',
                                'closed_at': datetime.utcnow().isoformat(),
                                'closed_price': sl,
                                'pnl_pct': pnl['pct'],
                                'pnl_usdt': pnl['usdt'],
                                'close_reason': 'sl_hit',
                                'updated_at': datetime.utcnow().isoformat(),
                            }).eq('id', sig['id']).execute()
                            stats['sl_hit'] += 1
                            logger.info(f"SL golpeado: {symbol} {tf} LONG @ {sl} ({pnl['pct']:.2f}%)")
                            break
                        elif high >= tp:
                            pnl = _calc_pnl(entry, tp, leverage, investment, action)
                            db.client.table('saved_signals').update({
                                'status': 'tp_hit',
                                'closed_at': datetime.utcnow().isoformat(),
                                'closed_price': tp,
                                'pnl_pct': pnl['pct'],
                                'pnl_usdt': pnl['usdt'],
                                'close_reason': 'tp_hit',
                                'updated_at': datetime.utcnow().isoformat(),
                            }).eq('id', sig['id']).execute()
                            stats['tp_hit'] += 1
                            logger.info(f"TP golpeado: {symbol} {tf} LONG @ {tp} ({pnl['pct']:+.2f}%)")
                            break
                    else:  # SHORT
                        # SHORT: SL arriba, TP abajo
                        if high >= sl:
                            pnl = _calc_pnl(entry, sl, leverage, investment, action)
                            db.client.table('saved_signals').update({
                                'status': 'sl_hit',
                                'closed_at': datetime.utcnow().isoformat(),
                                'closed_price': sl,
                                'pnl_pct': pnl['pct'],
                                'pnl_usdt': pnl['usdt'],
                                'close_reason': 'sl_hit',
                                'updated_at': datetime.utcnow().isoformat(),
                            }).eq('id', sig['id']).execute()
                            stats['sl_hit'] += 1
                            logger.info(f"SL golpeado: {symbol} {tf} SHORT @ {sl} ({pnl['pct']:.2f}%)")
                            break
                        elif low <= tp:
                            pnl = _calc_pnl(entry, tp, leverage, investment, action)
                            db.client.table('saved_signals').update({
                                'status': 'tp_hit',
                                'closed_at': datetime.utcnow().isoformat(),
                                'closed_price': tp,
                                'pnl_pct': pnl['pct'],
                                'pnl_usdt': pnl['usdt'],
                                'close_reason': 'tp_hit',
                                'updated_at': datetime.utcnow().isoformat(),
                            }).eq('id', sig['id']).execute()
                            stats['tp_hit'] += 1
                            logger.info(f"TP golpeado: {symbol} {tf} SHORT @ {tp} ({pnl['pct']:+.2f}%)")
                            break
            except Exception as e:
                stats['errors'] += 1
                logger.error(f"evaluate_saved_signals: error en {sig.get('id')}: {e}")
        
        return stats
    except Exception as e:
        logger.error(f"evaluate_saved_signals: {e}")
        return stats


# ============================================================================
# ESTADÍSTICAS (KPIs propios de la pestaña de señales guardadas)
# ============================================================================

def get_saved_signals_kpis() -> Dict:
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
            return (db.client.table('saved_signals')
                    .select('pnl_pct, pnl_usdt, entry_touched, status')
                    .in_('status', ['tp_hit', 'sl_hit', 'closed_manual'])
                    .eq('entry_touched', True)
                    .execute())
        r_closed = db._with_retry(_op_closed)
        closed = r_closed.data if r_closed and r_closed.data else []
        
        # Activas (no cuentan para winrate pero sí para 'activas')
        def _op_active():
            return (db.client.table('saved_signals')
                    .select('id', count='exact')
                    .in_('status', ['active', 'entry_touched'])
                    .limit(1)
                    .execute())
        r_active = db._with_retry(_op_active)
        active_count = r_active.count if hasattr(r_active, 'count') and r_active.count is not None else 0
        
        wins = sum(1 for s in closed if float(s.get('pnl_pct') or 0) > 0)
        losses = sum(1 for s in closed if float(s.get('pnl_pct') or 0) < 0)
        total = len(closed)
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        pnl_total_pct = sum(float(s.get('pnl_pct') or 0) for s in closed)
        pnl_total_usdt = sum(float(s.get('pnl_usdt') or 0) for s in closed)
        
        return {
            'total': total,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'pnl_total_pct': round(pnl_total_pct, 3),
            'pnl_total_usdt': round(pnl_total_usdt, 3),
            'active': int(active_count),
        }
    except Exception as e:
        logger.error(f"get_saved_signals_kpis: {e}")
        return {'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
                'pnl_total_pct': 0.0, 'pnl_total_usdt': 0.0, 'active': 0}
