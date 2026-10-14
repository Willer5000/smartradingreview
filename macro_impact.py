"""C41 · Diagnóstico causal verificable de noticias por clase de activo.

Nunca produce señales, órdenes, objetivos de precio o recomendaciones de
apalancamiento.  Una noticia con resultado desconocido = PRECAUCION, no LONG.
El análisis independiente de la IA se publica por separado y NO es autoridad
para el motor de trading.
"""
from __future__ import annotations
import re
from typing import Dict, List

MARKETS = {
    'ENERGIA_PETROLEO': 'Energía · WTI/CL',
    'ENERGIA_GAS': 'Energía · NATGAS',
    'EEUU_SP500': 'EE.UU. · S&P 500/SPY',
    'EEUU_NASDAQ': 'EE.UU. · Nasdaq/QQQ',
    'CHINA_STAR50': 'China · STAR 50/KSTR',
    'METALES_COBRE': 'Minerales · cobre',
    'METALES_PLATA': 'Minerales · plata/XAG',
    'SPOT_BTC': 'Spot · BTC',
    'SPOT_PAXG': 'Spot · oro/PAXG',
    'SPOT_USDT': 'Spot · USDT',
    'FUTURES_CRIPTO': 'Futuros · BTC/ETH/SOL/XRP/ADA',
}
LABELS = {'BENEFICIA','PERJUDICA','PRECAUCION','NEUTRAL','INCIERTO'}


def _has(t, *parts):
    return any(re.search(r'(?<!\w)' + re.escape(x) + r'(?!\w)', t) for x in parts)


def _scenario(title: str, category_codes: set) -> str:
    t = re.sub(r'\s+', ' ', (title or '').casefold())
    # Negations/rumours are not confirmed shocks. Headlines are not full articles.
    if _has(t, 'rumor', 'rumour', 'unconfirmed', 'desmentido', 'sin confirmar', 'denies', 'false report'):
        return 'UNVERIFIED'
    if _has(t, 'stablecoin depeg', 'usdt depeg', 'tether loses peg', 'tether depeg', 'usdt pierde paridad'):
        return 'STABLECOIN_STRESS'
    if _has(t, 'exchange hack', 'exchange hacked', 'exchange insolvency', 'exchange bankrupt',
            'hackeo de exchange', 'quiebra de exchange', 'exchange suspends withdrawals'):
        return 'EXCHANGE_STRESS'
    if _has(t, 'bitcoin etf approved', 'bitcoin etf approval', 'spot etf approved', 'etf bitcoin aprobado'):
        return 'CRYPTO_POSITIVE'
    if _has(t, 'crypto ban', 'bitcoin banned', 'prohibición de bitcoin', 'crypto crackdown'):
        return 'CRYPTO_NEGATIVE'
    if _has(t, 'rate hike', 'raises rates', 'hikes rates', 'hawkish', 'sube tasas', 'alza de tasas',
            'inflation accelerates', 'inflation hotter', 'cpi hotter', 'inflación acelera', 'cpi above expectations'):
        return 'HAWKISH_OR_HOT'
    if _has(t, 'rate cut', 'cuts rates', 'dovish', 'baja tasas', 'recorte de tasas',
            'inflation cools', 'cpi below expectations', 'inflación se modera'):
        return 'DOVISH_OR_COOL'
    if _has(t, 'china stimulus', 'chinese stimulus', 'china boosts spending', 'estímulo chino',
            'china stimulus package'):
        return 'CHINA_STIMULUS'
    if _has(t, 'china slowdown', 'china recession', 'chinese demand falls', 'china pmi contracts',
            'desaceleración china'):
        return 'CHINA_SLOWDOWN'
    if _has(t, 'oil supply disruption', 'oil supply cut', 'opec cuts', 'oil output cut',
            'hormuz closed', 'strait of hormuz blocked', 'pipeline attacked', 'refinery attacked',
            'interrupción de suministro de petróleo', 'recorte de producción de petróleo'):
        return 'OIL_SUPPLY_CUT'
    if _has(t, 'opec increases output', 'oil supply increases', 'oil oversupply', 'oil output rises',
            'aumento de producción de petróleo', 'sobreoferta de petróleo'):
        return 'OIL_SUPPLY_RISE'
    if _has(t, 'gas supply disruption', 'lng terminal shutdown', 'lng export ban',
            'gas pipeline attacked', 'corte de suministro de gas'):
        return 'GAS_SUPPLY_CUT'
    if _has(t, 'trade war escalates', 'new tariffs on china', 'tariffs on china',
            'aranceles a china', 'china export restrictions'):
        return 'TRADE_ESCALATION'
    if _has(t, 'ceasefire agreed', 'peace agreement signed', 'alto el fuego acordado',
            'acuerdo de paz firmado'):
        return 'GEOPOLITICAL_EASING'
    if _has(t, 'war escalates', 'military strikes', 'missile strikes', 'military invasion',
            'escalada militar', 'ataque con misiles', 'guerra se intensifica'):
        return 'GEOPOLITICAL_ESCALATION'
    if _has(t, 'copper mine strike', 'copper mine shutdown', 'copper supply disruption',
            'huelga minera de cobre'):
        return 'COPPER_SUPPLY_CUT'
    if _has(t, 'copper demand rises', 'copper demand surges', 'demanda de cobre aumenta'):
        return 'COPPER_DEMAND_RISE'
    # Calendar announces timing only, not the reading, outcome or surprise.
    if category_codes & {'MONETARY_POLICY', 'INFLATION', 'LABOR', 'US_DATA'}:
        return 'MACRO_DATA_UNRESOLVED'
    if category_codes & {'GEOPOLITICAL', 'MARKET_STRESS', 'TRADE_POLICY'}:
        return 'RISK_EVENT_UNRESOLVED'
    if category_codes & {'ENERGY_INFLATION'}:
        return 'ENERGY_UNRESOLVED'
    if category_codes & {'CRYPTO_POLICY', 'CRYPTO_LEGISLATION'}:
        return 'CRYPTO_UNRESOLVED'
    return 'GENERAL_UNRESOLVED'


# Scenario: market impact - conditional directional hypotheses, not orders.
_SCENARIOS = {
    'OIL_SUPPLY_CUT': ({'ENERGIA_PETROLEO':'BENEFICIA', 'EEUU_SP500':'PERJUDICA', 'EEUU_NASDAQ':'PRECAUCION',
                        'CHINA_STAR50':'PERJUDICA', 'METALES_COBRE':'PRECAUCION', 'SPOT_PAXG':'PRECAUCION',
                        'FUTURES_CRIPTO':'PRECAUCION'}, 'Oferta de crudo potencialmente menor; riesgo de inflación y costes de energía.'),
    'OIL_SUPPLY_RISE': ({'ENERGIA_PETROLEO':'PERJUDICA', 'EEUU_SP500':'PRECAUCION', 'CHINA_STAR50':'PRECAUCION'},
                        'Oferta de crudo potencialmente mayor; la demanda y el dólar pueden compensar.'),
    'GAS_SUPPLY_CUT': ({'ENERGIA_GAS':'BENEFICIA','EEUU_SP500':'PRECAUCION','CHINA_STAR50':'PRECAUCION'},
                       'Riesgo de menor oferta de gas; depende de región, inventarios y clima.'),
    'CHINA_STIMULUS': ({'CHINA_STAR50':'BENEFICIA','METALES_COBRE':'BENEFICIA', 'EEUU_SP500':'PRECAUCION'},
                       'Estímulo chino potencialmente favorable para demanda industrial; verificar magnitud.'),
    'CHINA_SLOWDOWN': ({'CHINA_STAR50':'PERJUDICA','METALES_COBRE':'PERJUDICA','ENERGIA_PETROLEO':'PRECAUCION'},
                       'Menor actividad china presiona actividad industrial y demanda de materias primas.'),
    'HAWKISH_OR_HOT': ({'EEUU_SP500':'PERJUDICA','EEUU_NASDAQ':'PERJUDICA','CHINA_STAR50':'PRECAUCION',
                        'METALES_PLATA':'PRECAUCION','SPOT_BTC':'PERJUDICA','SPOT_PAXG':'PRECAUCION',
                        'SPOT_USDT':'PRECAUCION','FUTURES_CRIPTO':'PRECAUCION'},
                        'Mayor expectativa de tipos/rendimientos: posible presión en activos de riesgo; oro también depende de tipos reales.'),
    'DOVISH_OR_COOL': ({'EEUU_SP500':'BENEFICIA','EEUU_NASDAQ':'BENEFICIA','SPOT_BTC':'BENEFICIA',
                        'METALES_PLATA':'PRECAUCION','SPOT_PAXG':'PRECAUCION','FUTURES_CRIPTO':'PRECAUCION'},
                        'Menores tipos esperados pueden favorecer riesgo; confirmar sorpresa, crecimiento y reacción del dólar.'),
    'TRADE_ESCALATION': ({'CHINA_STAR50':'PERJUDICA','EEUU_SP500':'PRECAUCION','EEUU_NASDAQ':'PRECAUCION',
                         'METALES_COBRE':'PRECAUCION','ENERGIA_PETROLEO':'PRECAUCION', 'FUTURES_CRIPTO':'PRECAUCION'},
                        'Aranceles/restricciones elevan incertidumbre comercial; impacto depende de contramedidas.'),
    'GEOPOLITICAL_ESCALATION': ({'ENERGIA_PETROLEO':'PRECAUCION','ENERGIA_GAS':'PRECAUCION',
                                'EEUU_SP500':'PRECAUCION','CHINA_STAR50':'PRECAUCION','SPOT_PAXG':'PRECAUCION',
                                'SPOT_BTC':'PRECAUCION','FUTURES_CRIPTO':'PRECAUCION'},
                               'Escalada eleva riesgo y volatilidad; no asumir subida de crudo/oro sin interrupción verificable.'),
    'GEOPOLITICAL_EASING': ({'ENERGIA_PETROLEO':'PRECAUCION','SPOT_PAXG':'PRECAUCION','EEUU_SP500':'PRECAUCION'},
                            'Distensión geopolítica reduce una prima de riesgo posible; reacción no garantizada.'),
    'COPPER_SUPPLY_CUT': ({'METALES_COBRE':'BENEFICIA','CHINA_STAR50':'PRECAUCION'},
                          'Una restricción de oferta puede elevar precio del cobre; verificar inventarios y duración.'),
    'COPPER_DEMAND_RISE': ({'METALES_COBRE':'BENEFICIA','CHINA_STAR50':'PRECAUCION'},
                           'Mayor demanda física favorece al cobre sólo si no existe oferta compensatoria.'),
    'EXCHANGE_STRESS': ({'SPOT_BTC':'PERJUDICA','FUTURES_CRIPTO':'PRECAUCION','SPOT_USDT':'PRECAUCION'},
                        'Riesgo de contraparte, retiros y liquidez del exchange; no equiparar con quiebra de toda la industria.'),
    'STABLECOIN_STRESS': ({'SPOT_USDT':'PERJUDICA','SPOT_BTC':'PRECAUCION','SPOT_PAXG':'PRECAUCION',
                          'FUTURES_CRIPTO':'PRECAUCION'},
                         'Pérdida de paridad amenaza la unidad de cuenta USDT; pares cotizados en USDT pueden distorsionarse.'),
    'CRYPTO_POSITIVE': ({'SPOT_BTC':'BENEFICIA','FUTURES_CRIPTO':'PRECAUCION','SPOT_USDT':'NEUTRAL'},
                        'Catalizador específico de cripto; reacción puede estar descontada por el mercado.'),
    'CRYPTO_NEGATIVE': ({'SPOT_BTC':'PERJUDICA','FUTURES_CRIPTO':'PRECAUCION','SPOT_USDT':'PRECAUCION'},
                        'Restricción cripto puede presionar liquidez y sentimiento; verificar jurisdicción.'),
    'RISK_EVENT_UNRESOLVED': ({'ENERGIA_PETROLEO':'PRECAUCION','ENERGIA_GAS':'PRECAUCION',
                               'EEUU_SP500':'PRECAUCION','EEUU_NASDAQ':'PRECAUCION','CHINA_STAR50':'PRECAUCION',
                               'METALES_COBRE':'PRECAUCION','METALES_PLATA':'PRECAUCION','SPOT_BTC':'PRECAUCION',
                               'SPOT_PAXG':'PRECAUCION','FUTURES_CRIPTO':'PRECAUCION'},
                               'Shock geopolítico/financiero: riesgo de volatilidad; sin causalidad suficiente para una dirección.'),
    'ENERGY_UNRESOLVED': ({'ENERGIA_PETROLEO':'PRECAUCION','ENERGIA_GAS':'PRECAUCION',
                           'CHINA_STAR50':'PRECAUCION','EEUU_SP500':'PRECAUCION'},
                           'Noticia energética con efecto aún no determinado sobre oferta, demanda y precios.'),
    'CRYPTO_UNRESOLVED': ({'SPOT_BTC':'PRECAUCION','SPOT_USDT':'PRECAUCION',
                           'FUTURES_CRIPTO':'PRECAUCION'},
                           'Evento cripto sin dirección verificable; revisar liquidez, contraparte y noticias confirmadas.'),
    'MACRO_DATA_UNRESOLVED': ({'EEUU_SP500':'PRECAUCION','EEUU_NASDAQ':'PRECAUCION',
                               'SPOT_BTC':'PRECAUCION','SPOT_PAXG':'PRECAUCION',
                               'FUTURES_CRIPTO':'PRECAUCION'},
                              'Dato de política monetaria/actividad sin resultado o sorpresa verificada.'),
}


def evaluate_macro_impacts(rows: List[Dict], limit: int = 6) -> Dict:
    """Return explainable sector impacts using only dated, known headlines/events."""
    evidence = []
    for row in rows[:max(1, min(limit, 12))]:
        if not isinstance(row, dict) or not row.get('id'):
            continue
        is_event = str(row.get('kind') or '').upper() == 'SCHEDULED_EVENT'
        cats = {str(x.get('code') or '') for x in (row.get('categories') or []) if isinstance(x, dict)}
        scenario = ('MACRO_DATA_UNRESOLVED' if is_event else _scenario(str(row.get('title_es') or ''), cats))
        mapping, note = _SCENARIOS.get(scenario, ({}, 'No existe dirección verificable con este titular aislado; vigilar contexto técnico.'))
        if is_event:
            note = 'Evento programado: aún no hay resultado/sorpresa; sólo precaución de volatilidad.'
        affected = {}
        for key in MARKETS:
            impact = mapping.get(key, 'PRECAUCION' if is_event and key in {
                'EEUU_SP500', 'EEUU_NASDAQ', 'SPOT_BTC', 'SPOT_PAXG', 'FUTURES_CRIPTO'} else 'INCIERTO')
            affected[key] = {'impact': impact, 'why': note[:220], 'confidence': 65 if impact in {'BENEFICIA','PERJUDICA'} else 30}
        evidence.append({'id': row['id'], 'title': str(row.get('title_es') or '')[:200], 'source':row.get('source'),
                         'url':row.get('url'), 'scenario':scenario, 'impacts':affected,
                         'published_at':row.get('published_at'), 'scheduled_at':row.get('scheduled_at')})
    # Aggregate cautiously: opposing impacts never forced into a directional vote.
    aggregate = {}
    for key, label in MARKETS.items():
        pos = [e for e in evidence if e['impacts'][key]['impact'] == 'BENEFICIA']
        neg = [e for e in evidence if e['impacts'][key]['impact'] == 'PERJUDICA']
        caution = [e for e in evidence if e['impacts'][key]['impact'] == 'PRECAUCION']
        if pos and neg:
            result, why, confidence = 'PRECAUCION', 'Impactos fundamentales opuestos; no hay consenso de dirección.', 25
        elif pos:
            result, why, confidence = 'BENEFICIA', pos[0]['impacts'][key]['why'], 60
        elif neg:
            result, why, confidence = 'PERJUDICA', neg[0]['impacts'][key]['why'], 60
        elif caution:
            result, why, confidence = 'PRECAUCION', caution[0]['impacts'][key]['why'], 30
        else:
            result, why, confidence = 'INCIERTO', 'Sin evidencia suficiente de impacto específico.', 0
        ev = (pos + neg + caution)[:3]
        # C41 live caution: a single syndicated GDELT headline is traceable but
        # NOT an officially corroborated fact. Don't let it modify Spot votes.
        corroborated = len({str(e.get('source') or '') for e in (pos+neg)}) >= 2
        official = any(any(tag in str(e.get('source') or '') for tag in
                           ('Federal Reserve', 'BLS', 'CFTC', 'SEC RSS', 'EIA Energy'))
                       for e in (pos+neg))
        if result in ('BENEFICIA','PERJUDICA'):
            confidence = 75 if official else 65 if corroborated else 40
        aggregate[key] = {'label':label, 'impact':result,'confidence':confidence,'why':why,
                          'evidence_ids':[x['id'] for x in ev]}
    return {'authority':'ADVISORY_ONLY', 'method':'RULES_EXPLAINABLE_C41',
            'markets':aggregate, 'evidence':evidence[:max(1,min(limit,12))],
            'disclaimer':'Hipótesis condicionales, no órdenes ni predicción de precios.'}
