"""
macro_context.py
================
V1.1/J Macro Context + CEX Flow Radar para TraderMacro.

Objetivo:
- leer fuentes públicas/gratuitas de forma acotada;
- clasificar riesgo/contexto macro sin convertir titulares en órdenes;
- exponer un snapshot liviano para frontend, Telegram y TraderMacro;
- mantener UTC internamente y mostrar hora Argentina en UI;
- fallar abierto: si una fuente externa cae, trading sigue funcionando.

Fuentes iniciales sin API key:
- GDELT DOC 2.0 (titulares recientes en español);
- calendario BLS en iCalendar;
- calendario oficial FOMC de la Reserva Federal.

IMPORTANTE: esta versión es CONTEXT_ONLY. No cambia Safety, Entry, SL, TP,
leverage, pesos del comité ni Publication Gate.
"""

from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger("MACRO_CONTEXT")

MACRO_CONTEXT_ENABLED = str(os.getenv("MACRO_CONTEXT_ENABLED", "true")).strip().lower() in {
    "1", "true", "yes", "on", "si", "sí"
}
MACRO_NEWS_CACHE_SECONDS = max(300, min(3600, int(os.getenv("MACRO_NEWS_CACHE_SECONDS", "900"))))
MACRO_CALENDAR_CACHE_SECONDS = max(1800, min(43200, int(os.getenv("MACRO_CALENDAR_CACHE_SECONDS", "21600"))))
MACRO_NEWS_MAX_ARTICLES = max(5, min(24, int(os.getenv("MACRO_NEWS_MAX_ARTICLES", "12"))))
MACRO_HEADLINE_MAX_AGE_HOURS = max(6, min(48, int(os.getenv("MACRO_HEADLINE_MAX_AGE_HOURS", "24"))))
MACRO_HTTP_TIMEOUT = max(3, min(15, int(os.getenv("MACRO_HTTP_TIMEOUT", "7"))))

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

UTC = timezone.utc
try:
    DISPLAY_TZ_NAME = str(os.getenv("MACRO_DISPLAY_TIMEZONE", "America/Argentina/Buenos_Aires")).strip()
    DISPLAY_TZ = ZoneInfo(DISPLAY_TZ_NAME)
except Exception:
    DISPLAY_TZ_NAME = "America/Argentina/Buenos_Aires"
    DISPLAY_TZ = ZoneInfo(DISPLAY_TZ_NAME)
NY_TZ = ZoneInfo("America/New_York")

_LOCK = threading.Lock()
_DB_HYDRATED = False
_CACHE: Dict[str, object] = {
    "news_fetched_at": 0.0,
    "calendar_fetched_at": 0.0,
    "news": [],
    "calendar": [],
    "errors": [],
    "news_last_success_utc": None,
}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str):
        if data and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        # GDELT commonly emits YYYYMMDDTHHMMSSZ.
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _stable_id(*parts: object) -> str:
    payload = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:20]


def _normalize_title(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()[:280]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    t = text.lower()
    return any(term in t for term in terms)


_CATEGORY_RULES: List[Tuple[str, str, Tuple[str, ...], int]] = [
    ("MONETARY_POLICY", "Política monetaria", (
        "federal reserve", "fomc", "fed ", "banco central", "tasas de interés",
        "interest rate", "rate cut", "rate hike", "powell", "liquidez monetaria",
    ), 22),
    ("INFLATION", "Inflación", (
        "inflación", "inflation", "cpi", "ipc", "pce", "precios al consumidor",
        "producer price", "ppi",
    ), 20),
    ("LABOR", "Empleo", (
        "empleo", "employment", "nóminas", "nonfarm", "payroll", "desempleo",
        "unemployment", "jolts", "job openings",
    ), 16),
    ("GEOPOLITICAL", "Geopolítica", (
        "guerra", "war ", "ataque", "attack", "misil", "missile", "iran", "israel",
        "ukraine", "ucrania", "russia", "rusia", "china", "taiwan", "sanciones",
        "sanctions", "conflicto", "geopol",
    ), 20),
    ("CRYPTO_POLICY", "Regulación cripto", (
        "bitcoin", "criptomon", "crypto", "sec ", "etf", "regulación", "regulation",
        "stablecoin", "exchange", "reserva de bitcoin",
    ), 12),
    ("MARKET_STRESS", "Estrés financiero", (
        "bank run", "corrida bancaria", "default", "impago", "liquidity crisis",
        "crisis de liquidez", "quiebra", "bankruptcy", "emergency", "emergencia",
        "debt ceiling", "techo de deuda",
    ), 30),
    ("TRADE_POLICY", "Comercio y aranceles", (
        "tariff", "arancel", "trade war", "guerra comercial", "export ban",
        "prohibición de export", "import ban",
    ), 18),
    ("GOLD", "Oro y refugio", (
        "gold", "oro ", "bullion", "safe haven", "refugio",
    ), 10),
]

_CRITICAL_TERMS = (
    "emergency rate", "reunión de emergencia", "bank run", "corrida bancaria",
    "default", "impago soberano", "ataque nuclear", "nuclear attack",
    "exchange hack", "hackeo de exchange", "capital controls", "controles de capital",
)
_HIGH_TERMS = (
    "fomc", "federal reserve", "cpi", "inflación", "inflation", "nonfarm", "payroll",
    "sanctions", "sanciones", "tariff", "arancel", "war", "guerra", "sec bitcoin",
)


def classify_macro_headline(title: str, source: str = "") -> Dict:
    """Clasificación heurística. Contexto solamente, nunca señal de trading."""
    clean = _normalize_title(title)
    lower = clean.lower()
    categories = []
    score = 18

    for code, label, terms, points in _CATEGORY_RULES:
        if _contains_any(lower, terms):
            categories.append({"code": code, "label_es": label})
            score += points

    if _contains_any(lower, _CRITICAL_TERMS):
        score = max(score, 90)
    elif _contains_any(lower, _HIGH_TERMS):
        score = max(score, 68)

    # Frases que suelen señalar sorpresa/cambio; elevan riesgo, no dirección.
    if _contains_any(lower, (
        "sorpresa", "unexpected", "inesperad", "sharply", "brusc", "emergency",
        "urgente", "breaking", "última hora", "record", "récord",
    )):
        score += 10

    score = max(0, min(100, score))
    if score >= 88:
        level = "CRITICAL"
    elif score >= 65:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    # Direccionalidad intencionalmente conservadora.
    risk_bias = "NEUTRAL"
    if _contains_any(lower, ("risk-off", "aversión al riesgo", "safe haven", "refugio")):
        risk_bias = "RISK_OFF"
    elif _contains_any(lower, ("risk-on", "apetito por riesgo")):
        risk_bias = "RISK_ON"

    category_codes = {item["code"] for item in categories}
    if category_codes & {"GEOPOLITICAL", "MARKET_STRESS", "GOLD"}:
        opportunity_note = "Vigilar refugio en oro/PAXG y confirmar con PAXG/BTC; no asumir dirección por titular."
    elif category_codes & {"MONETARY_POLICY", "INFLATION", "LABOR"}:
        opportunity_note = "Vigilar reacción posterior de BTC, oro y volatilidad; el evento no define dirección por sí solo."
    elif "CRYPTO_POLICY" in category_codes:
        opportunity_note = "Vigilar reacción de BTC y liquidez; regulación/noticia no equivale automáticamente a LONG o SHORT."
    else:
        opportunity_note = "Contexto para vigilancia; sin oportunidad direccional confirmada."

    return {
        "risk_score": score,
        "risk_level": level,
        "threat_level": level,
        "categories": categories or [{"code": "GENERAL_MACRO", "label_es": "Contexto macro"}],
        "risk_bias": risk_bias,
        "opportunity_level": "WATCH" if level in {"HIGH", "CRITICAL"} else "NONE",
        "opportunity_note_es": opportunity_note,
        "futures_posture": "CAUTION" if level in {"HIGH", "CRITICAL"} else "NORMAL",
        "method": "RULE_BASED_CONTEXT_ONLY",
        "source": str(source or ""),
    }


def _fetch_gdelt_news() -> List[Dict]:
    # GDELT permite consultar noticias globales sin API key. Limitamos a fuentes
    # en español para que el cintillo sea comprensible sin gastar LLM/traducción.
    query = (
        '(bitcoin OR criptomonedas OR "Federal Reserve" OR FOMC OR inflación OR CPI '
        'OR "tasas de interés" OR oro OR sanciones OR aranceles OR guerra OR "crisis bancaria") '
        'sourcelang:spanish'
    )
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": MACRO_NEWS_MAX_ARTICLES,
        "timespan": "12h",
        "sort": "datedesc",
        "format": "json",
    }
    response = requests.get(
        GDELT_DOC_URL,
        params=params,
        timeout=MACRO_HTTP_TIMEOUT,
        headers={"User-Agent": "CryptoTraderAnalystPro/1.0 macro-context"},
    )
    response.raise_for_status()
    payload = response.json() if response.content else {}
    articles = payload.get("articles") or []

    rows: List[Dict] = []
    seen = set()
    for article in articles:
        title = _normalize_title(article.get("title"))
        url = str(article.get("url") or "").strip()
        if not title or not url:
            continue
        key = re.sub(r"\W+", "", title.lower())[:160]
        if key in seen:
            continue
        seen.add(key)
        published = _safe_dt(article.get("seendate") or article.get("date"))
        source = str(article.get("domain") or article.get("sourcecountry") or "GDELT").strip()
        classification = classify_macro_headline(title, source)
        rows.append({
            "id": _stable_id(title, url),
            "kind": "HEADLINE",
            "title_es": title,
            "source": source or "GDELT",
            "url": url,
            "published_at": _iso_utc(published) if published else None,
            **classification,
        })

    rows.sort(key=lambda item: (item.get("risk_score", 0), item.get("published_at") or ""), reverse=True)
    return rows[:MACRO_NEWS_MAX_ARTICLES]


def _unfold_ics(text: str) -> List[str]:
    output: List[str] = []
    for raw in str(text or "").replace("\r\n", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and output:
            output[-1] += raw[1:]
        else:
            output.append(raw)
    return output


def _parse_ics_dt(raw_key: str, raw_value: str) -> Optional[datetime]:
    tz_name = "America/New_York"
    match = re.search(r"TZID=([^;:]+)", raw_key)
    if match:
        tz_name = match.group(1).strip()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = NY_TZ

    value = raw_value.strip()
    if value.endswith("Z"):
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            return None

    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=tz).astimezone(UTC)
        except ValueError:
            continue
    return None


def _spanish_bls_title(summary: str) -> Tuple[str, str, int]:
    lower = summary.lower()
    mapping = [
        (("consumer price", "cpi"), "IPC / inflación de EE.UU.", "INFLATION", 88),
        (("employment situation", "employment"), "Informe de empleo de EE.UU.", "LABOR", 88),
        (("producer price", "ppi"), "Precios al productor de EE.UU.", "INFLATION", 75),
        (("job openings", "jolts"), "Vacantes laborales JOLTS", "LABOR", 62),
        (("employment cost",), "Coste del empleo de EE.UU.", "LABOR", 60),
        (("import and export",), "Precios de importación/exportación de EE.UU.", "INFLATION", 52),
        (("productivity",), "Productividad y costes de EE.UU.", "LABOR", 48),
    ]
    for terms, label, category, score in mapping:
        if any(term in lower for term in terms):
            return label, category, score
    return summary.strip()[:120], "US_DATA", 35


def _fetch_bls_calendar(now: Optional[datetime] = None) -> List[Dict]:
    now = (now or _utc_now()).astimezone(UTC)
    response = requests.get(
        BLS_ICS_URL,
        timeout=MACRO_HTTP_TIMEOUT,
        headers={"User-Agent": "CryptoTraderAnalystPro/1.0 macro-context"},
    )
    response.raise_for_status()
    lines = _unfold_ics(response.text)
    events: List[Dict] = []
    current: Dict[str, str] = {}

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            summary = current.get("SUMMARY", "")
            dt_key = next((key for key in current if key.startswith("DTSTART")), None)
            dt = _parse_ics_dt(dt_key or "", current.get(dt_key, "")) if dt_key else None
            if dt and now - timedelta(hours=2) <= dt <= now + timedelta(days=8):
                label, category, score = _spanish_bls_title(summary)
                if score >= 45:  # sólo eventos con impacto plausible
                    events.append({
                        "id": _stable_id("BLS", summary, _iso_utc(dt)),
                        "kind": "SCHEDULED_EVENT",
                        "title_es": label,
                        "source": "BLS",
                        "url": "https://www.bls.gov/schedule/",
                        "scheduled_at": _iso_utc(dt),
                        "risk_score": score,
                        "risk_level": "HIGH" if score >= 70 else "MEDIUM",
                        "categories": [{"code": category, "label_es": label}],
                        "risk_bias": "NEUTRAL",
                        "threat_level": "HIGH" if score >= 70 else "MEDIUM",
                        "opportunity_level": "WATCH",
                        "opportunity_note_es": "Esperar el dato y confirmar reacción de BTC/oro antes de inferir dirección.",
                        "futures_posture": "CAUTION",
                        "time_precision": "EXACT",
                        "method": "OFFICIAL_CALENDAR_CONTEXT_ONLY",
                    })
            current = {}
            continue
        if ":" in line and current is not None:
            key, value = line.split(":", 1)
            if key.startswith("DTSTART"):
                current[key] = value
            elif key in {"SUMMARY", "DESCRIPTION", "URL"}:
                current[key] = value.replace("\\,", ",").replace("\\n", " ")

    return events


def _fetch_fomc_calendar(now: Optional[datetime] = None) -> List[Dict]:
    now = (now or _utc_now()).astimezone(UTC)
    response = requests.get(
        FOMC_CALENDAR_URL,
        timeout=MACRO_HTTP_TIMEOUT,
        headers={"User-Agent": "CryptoTraderAnalystPro/1.0 macro-context"},
    )
    response.raise_for_status()
    parser = _TextExtractor()
    parser.feed(response.text)
    text = re.sub(r"\s+", " ", parser.text())
    year = now.astimezone(NY_TZ).year
    month_names = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }

    # Acotar al bloque del año actual para evitar duplicados históricos.
    marker = f"{year} FOMC Meetings"
    next_marker = f"{year + 1} FOMC Meetings"
    start = text.find(marker)
    if start >= 0:
        end = text.find(next_marker, start + len(marker))
        section = text[start:end if end >= 0 else None]
    else:
        section = text

    events: List[Dict] = []
    month_pattern = "|".join(month_names)
    for match in re.finditer(rf"\b({month_pattern})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\*?", section):
        month_name, first_day, second_day = match.groups()
        try:
            start_local = datetime(year, month_names[month_name], int(first_day), 0, 0, tzinfo=NY_TZ)
            end_local = datetime(year, month_names[month_name], int(second_day), 23, 59, tzinfo=NY_TZ)
        except ValueError:
            continue
        start_utc = start_local.astimezone(UTC)
        end_utc = end_local.astimezone(UTC)
        if now - timedelta(days=1) <= end_utc <= now + timedelta(days=10):
            label = f"Reunión FOMC · {first_day}-{second_day} {month_name}"
            events.append({
                "id": _stable_id("FOMC", year, month_name, first_day, second_day),
                "kind": "SCHEDULED_EVENT",
                "title_es": label,
                "source": "Federal Reserve",
                "url": FOMC_CALENDAR_URL,
                "scheduled_at": _iso_utc(start_utc),
                "scheduled_end_at": _iso_utc(end_utc),
                "risk_score": 90,
                "risk_level": "CRITICAL",
                "categories": [{"code": "MONETARY_POLICY", "label_es": "Política monetaria"}],
                "risk_bias": "NEUTRAL",
                "threat_level": "CRITICAL",
                "opportunity_level": "WATCH",
                "opportunity_note_es": "Riesgo de volatilidad por política monetaria; confirmar reacción antes de sesgo BTC/oro.",
                "futures_posture": "CAUTION",
                "time_precision": "DATE_ONLY",
                "method": "OFFICIAL_CALENDAR_CONTEXT_ONLY",
            })
    return events


def _hydrate_cache_from_db_once() -> None:
    """Restore only still-relevant compact macro rows after a Render restart.

    The DB is the durable store; RAM holds a very small hot window. Failure is
    harmless because public sources can repopulate it.
    """
    global _DB_HYDRATED
    if _DB_HYDRATED:
        return
    _DB_HYDRATED = True
    try:
        from runtime_persistence import load_active_macro_events
        rows = load_active_macro_events(limit=60) or []
    except Exception:
        rows = []
    if not rows:
        return
    news = [r for r in rows if str(r.get("kind") or "").upper() == "HEADLINE"][:MACRO_NEWS_MAX_ARTICLES]
    events = [r for r in rows if str(r.get("kind") or "").upper() == "SCHEDULED_EVENT"][:16]
    with _LOCK:
        if news and not _CACHE.get("news"):
            _CACHE["news"] = news
        if events and not _CACHE.get("calendar"):
            _CACHE["calendar"] = events


def _persist_macro_cache_best_effort() -> None:
    try:
        from runtime_persistence import persist_macro_events
        with _LOCK:
            news = list(_CACHE.get("news") or [])[:MACRO_NEWS_MAX_ARTICLES]
            calendar_rows = list(_CACHE.get("calendar") or [])[:16]
        persist_macro_events(news, calendar_rows)
    except Exception as exc:
        logger.warning("Macro persistence unavailable: %s", exc)


def _refresh_news_if_needed(force: bool = False) -> None:
    now_monotonic = time.monotonic()
    with _LOCK:
        last = float(_CACHE.get("news_fetched_at") or 0.0)
        if not force and now_monotonic - last < MACRO_NEWS_CACHE_SECONDS:
            return
    errors = []
    rows: List[Dict] = []
    try:
        rows = _fetch_gdelt_news()
    except Exception as exc:
        errors.append(f"GDELT: {type(exc).__name__}: {str(exc)[:120]}")
        logger.warning("Macro GDELT no disponible: %s", exc)
    with _LOCK:
        if rows:
            _CACHE["news"] = rows[:MACRO_NEWS_MAX_ARTICLES]
            _CACHE["news_last_success_utc"] = _iso_utc(_utc_now())
        _CACHE["news_fetched_at"] = now_monotonic
        _CACHE["errors"] = (list(_CACHE.get("errors") or []) + errors)[-8:]
    if rows:
        _persist_macro_cache_best_effort()


def _refresh_calendar_if_needed(force: bool = False) -> None:
    now_monotonic = time.monotonic()
    with _LOCK:
        last = float(_CACHE.get("calendar_fetched_at") or 0.0)
        if not force and now_monotonic - last < MACRO_CALENDAR_CACHE_SECONDS:
            return
    errors = []
    events: List[Dict] = []
    for name, fetcher in (("BLS", _fetch_bls_calendar), ("FOMC", _fetch_fomc_calendar)):
        try:
            events.extend(fetcher())
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
            logger.warning("Macro calendar %s no disponible: %s", name, exc)
    # unique
    unique = {row["id"]: row for row in events if row.get("id")}
    events = sorted(unique.values(), key=lambda row: row.get("scheduled_at") or "")
    with _LOCK:
        if events:
            _CACHE["calendar"] = events[:16]
        _CACHE["calendar_fetched_at"] = now_monotonic
        _CACHE["errors"] = (list(_CACHE.get("errors") or []) + errors)[-8:]
    if events:
        _persist_macro_cache_best_effort()


def refresh_macro_context(force: bool = False) -> Dict:
    _hydrate_cache_from_db_once()
    if not MACRO_CONTEXT_ENABLED:
        return get_macro_context_snapshot(fetch_if_stale=False)
    _refresh_news_if_needed(force=force)
    _refresh_calendar_if_needed(force=force)
    return get_macro_context_snapshot(fetch_if_stale=False)


def _event_hours_until(event: Dict, now: datetime) -> Optional[float]:
    dt = _safe_dt(event.get("scheduled_at"))
    if not dt:
        return None
    return (dt - now).total_seconds() / 3600.0


def _format_event_ticker(event: Dict, now: datetime) -> str:
    dt = _safe_dt(event.get("scheduled_at"))
    if not dt:
        return str(event.get("title_es") or "Evento macro")
    local = dt.astimezone(DISPLAY_TZ)
    hours = (dt - now).total_seconds() / 3600.0
    when = "hoy" if local.date() == now.astimezone(DISPLAY_TZ).date() else "mañana" if local.date() == (now.astimezone(DISPLAY_TZ).date() + timedelta(days=1)) else local.strftime("%d/%m")
    # Para eventos FOMC de día completo no inventamos una hora de decisión.
    if str(event.get("source")) == "Federal Reserve":
        return f"{event.get('title_es')} · {when} · riesgo macro alto"
    return f"{event.get('title_es')} · {when} {local.strftime('%H:%M')} local · riesgo {str(event.get('risk_level') or '').lower()}"


def _build_alert_candidates(events: List[Dict], news: List[Dict], now: datetime) -> List[Dict]:
    alerts: List[Dict] = []
    for event in events:
        hours = _event_hours_until(event, now)
        if hours is None or hours < 0:
            continue
        window = None
        precision = str(event.get("time_precision") or "EXACT").upper()
        if 23.5 <= hours <= 24.5:
            window = "24H"
        elif precision == "EXACT" and 2.7 <= hours <= 3.3:
            window = "3H"
        elif precision == "EXACT" and 0.35 <= hours <= 0.65:
            window = "30M"
        if window:
            alerts.append({
                "key": f"{event.get('id')}:{window}",
                "level": event.get("risk_level", "HIGH"),
                "text": _format_event_ticker(event, now),
                "source": event.get("source"),
                "url": event.get("url"),
            })

    for item in news[:8]:
        published = _safe_dt(item.get("published_at"))
        age_minutes = ((now - published).total_seconds() / 60.0) if published else 9999
        if item.get("risk_level") == "CRITICAL" and 0 <= age_minutes <= 45:
            alerts.append({
                "key": f"{item.get('id')}:BREAKING",
                "level": "CRITICAL",
                "text": f"Noticia macro crítica · {item.get('title_es')}",
                "source": item.get("source"),
                "url": item.get("url"),
            })
    return alerts


def get_macro_context_snapshot(fetch_if_stale: bool = True) -> Dict:
    _hydrate_cache_from_db_once()
    if fetch_if_stale and MACRO_CONTEXT_ENABLED:
        _refresh_news_if_needed(force=False)
        _refresh_calendar_if_needed(force=False)

    now = _utc_now()
    with _LOCK:
        news = [dict(item) for item in (_CACHE.get("news") or [])]
        calendar_rows = [dict(item) for item in (_CACHE.get("calendar") or [])]
        errors = list(_CACHE.get("errors") or [])[-4:]
        news_fetched_at = float(_CACHE.get("news_fetched_at") or 0.0)
        calendar_fetched_at = float(_CACHE.get("calendar_fetched_at") or 0.0)
        news_last_success_utc = _CACHE.get("news_last_success_utc")

    upcoming = []
    for event in calendar_rows:
        hours = _event_hours_until(event, now)
        if hours is not None and -2 <= hours <= 24 * 8:
            enriched = dict(event)
            enriched["hours_until"] = round(hours, 2)
            dt = _safe_dt(event.get("scheduled_at"))
            enriched["scheduled_at_argentina"] = dt.astimezone(DISPLAY_TZ).isoformat() if dt else None
            upcoming.append(enriched)
    upcoming.sort(key=lambda row: row.get("hours_until", 99999))

    active_news = []
    for row in news:
        published = _safe_dt(row.get("published_at"))
        # H.2: un titular sin fecha verificable no puede quedarse para siempre
        # en el ticker. Conservamos el cache durable, pero sólo mostramos como
        # noticia ACTIVA filas con timestamp real y dentro de la ventana máxima.
        if not published:
            continue
        age_hours = (now - published).total_seconds() / 3600.0
        if 0 <= age_hours <= float(MACRO_HEADLINE_MAX_AGE_HOURS):
            item = dict(row)
            item["age_hours"] = round(age_hours, 2)
            active_news.append(item)

    # Commit J: current CEX reserve/flow context. It is a volatility/supply
    # pressure input, never proof that an exchange itself bought or sold.
    try:
        from exchange_flow_context import get_exchange_flow_context
        exchange_flow = get_exchange_flow_context(force=False) or {}
    except Exception as exchange_error:
        exchange_flow = {
            "available": False, "state": "UNAVAILABLE",
            "volatility_risk": "UNKNOWN", "error": str(exchange_error)[:160],
        }

    top_score = max(
        [int(row.get("risk_score") or 0) for row in active_news[:10]]
        + [int(row.get("risk_score") or 0) for row in upcoming if 0 <= float(row.get("hours_until") or 9999) <= 24]
        + [0]
    )
    if top_score >= 88:
        risk_level = "CRITICAL"
    elif top_score >= 65:
        risk_level = "HIGH"
    elif top_score >= 40:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    near_high_event = next((
        event for event in upcoming
        if 0 <= float(event.get("hours_until") or 9999) <= 24
        and event.get("risk_level") in {"HIGH", "CRITICAL"}
    ), None)

    futures_posture = "CAUTION" if near_high_event or risk_level in {"HIGH", "CRITICAL"} else "NORMAL"
    if str(exchange_flow.get("volatility_risk") or "").upper() in {"HIGH"}:
        futures_posture = "CAUTION"
    if (
        near_high_event
        and str(near_high_event.get("time_precision") or "EXACT").upper() == "EXACT"
        and 0 <= float(near_high_event.get("hours_until") or 9999) <= 0.75
    ):
        futures_posture = "NO_NEW_TRADES"

    risk_off_count=sum(1 for row in active_news[:10] if str(row.get("risk_bias") or "").upper()=="RISK_OFF")
    risk_on_count=sum(1 for row in active_news[:10] if str(row.get("risk_bias") or "").upper()=="RISK_ON")
    if risk_off_count > risk_on_count and risk_off_count > 0:
        directional_bias="RISK_OFF"
    elif risk_on_count > risk_off_count and risk_on_count > 0:
        directional_bias="RISK_ON"
    else:
        directional_bias="NEUTRAL"

    ticker_items: List[Dict] = []
    for event in upcoming[:4]:
        ticker_items.append({
            "id": event.get("id"),
            "type": "EVENT",
            "level": event.get("risk_level"),
            "text": _format_event_ticker(event, now),
            "url": event.get("url"),
            "source": event.get("source"),
        })
    for row in active_news[:8]:
        category = (row.get("categories") or [{}])[0].get("label_es", "Macro")
        ticker_items.append({
            "id": row.get("id"),
            "type": "NEWS",
            "level": row.get("risk_level"),
            "text": f"{category} · {row.get('title_es')}",
            "url": row.get("url"),
            "source": row.get("source"),
            "age_hours": row.get("age_hours"),
            "published_at": row.get("published_at"),
        })
    if exchange_flow.get("available"):
        d24=float(exchange_flow.get("aggregate_inflow_24h_usd") or 0.0)
        sign="+" if d24>=0 else "-"
        ticker_items.insert(0,{
            "id":"J-CEX-FLOW", "type":"CEX_FLOW",
            "level": exchange_flow.get("volatility_risk") or "LOW",
            "text": f"Flujo CEX 24h · {sign}${abs(d24)/1e6:.0f}M · {exchange_flow.get('label_es')}",
            "url":"https://defillama.com/cexs", "source":"DefiLlama CEX",
        })
    ticker_items = ticker_items[:10]

    return {
        "enabled": MACRO_CONTEXT_ENABLED,
        "mode": "CONTEXT_ONLY",
        "authority": "NONE",
        "trader_macro_reads_context": True,
        "production_change": False,
        "risk_level": risk_level,
        "risk_score": top_score,
        "futures_posture": futures_posture,
        "directional_bias": directional_bias,
        "exchange_flow": exchange_flow,
        "fundamental_signal_context": {
            "scheduled_event_risk": bool(near_high_event),
            "news_bias": directional_bias,
            "cex_flow_state": exchange_flow.get("state"),
            "cex_volatility_risk": exchange_flow.get("volatility_risk"),
            "policy": "CONFIRM_OR_VETO_ONLY_NEVER_CREATE_DIRECTION",
        },
        "upcoming_events": upcoming[:10],
        "headlines": active_news[:12],
        "ticker_items": ticker_items,
        "telegram_alert_candidates": _build_alert_candidates(upcoming, active_news, now),
        "generated_at": _iso_utc(now),
        "display_timezone": DISPLAY_TZ_NAME,
        "sources": ["GDELT", "BLS", "Federal Reserve", "DefiLlama CEX"],
        "news_cache_age_seconds": round(max(0.0, time.monotonic() - news_fetched_at), 1) if news_fetched_at else None,
        "calendar_cache_age_seconds": round(max(0.0, time.monotonic() - calendar_fetched_at), 1) if calendar_fetched_at else None,
        "news_refresh_seconds": MACRO_NEWS_CACHE_SECONDS,
        "calendar_refresh_seconds": MACRO_CALENDAR_CACHE_SECONDS,
        "headline_max_age_hours": MACRO_HEADLINE_MAX_AGE_HOURS,
        "fresh_headlines": len(active_news),
        "freshest_headline_age_hours": (
            min((float(row.get("age_hours")) for row in active_news if row.get("age_hours") is not None), default=None)
        ),
        "news_last_success_utc": news_last_success_utc,
        "errors": errors,
    }
