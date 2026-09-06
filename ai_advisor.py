# ai_advisor.py
# ============================================================================
# COMMIT 36R
# AI ADVISOR / ASISTENTE PERSONAL / AI LEARNING SHADOW
# ============================================================================

import os
import json
import hashlib
import logging

from datetime import (
    datetime,
    timezone,
    timedelta
)

import requests


logger = logging.getLogger(
    "AI_ADVISOR"
)


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

AI_ENABLED = (
    os.getenv(
        "AI_ADVISOR_ENABLED",
        "false"
    )
    .lower()
    in (
        "1",
        "true",
        "yes",
        "si",
        "sí"
    )
)


AI_PROVIDER = (
    os.getenv(
        "AI_ADVISOR_PROVIDER",
        "GROQ"
    )
    .strip()
    .upper()
)


AI_MODEL = (
    os.getenv(
        "AI_ADVISOR_MODEL",
        "openai/gpt-oss-20b"
    )
    .strip()
)


AI_TIMEOUT = max(
    3,
    min(
        30,
        int(
            os.getenv(
                "AI_ADVISOR_TIMEOUT_SECONDS",
                "10"
            )
        )
    )
)


AI_MAX_CONTEXT = max(
    6000,
    min(
        24000,
        int(
            os.getenv(
                "AI_ADVISOR_MAX_CONTEXT_CHARS",
                "14000"
            )
        )
    )
)


LIMIT_MANUAL_HOUR = max(
    1,
    int(
        os.getenv(
            "AI_MANUAL_HOURLY_LIMIT",
            "3"
        )
    )
)


LIMIT_MANUAL_DAY = max(
    1,
    int(
        os.getenv(
            "AI_MANUAL_DAILY_LIMIT",
            "12"
        )
    )
)


LIMIT_AUTO_DAY = max(
    1,
    int(
        os.getenv(
            "AI_AUTOMATIC_DAILY_LIMIT",
            "30"
        )
    )
)


LIMIT_LEARNING_DAY = max(
    1,
    int(
        os.getenv(
            "AI_LEARNING_DAILY_LIMIT",
            "6"
        )
    )
)


LIMIT_GLOBAL_DAY = max(
    1,
    int(
        os.getenv(
            "AI_GLOBAL_DAILY_LIMIT",
            "60"
        )
    )
)


GROQ_URL = (
    "https://api.groq.com/"
    "openai/v1/chat/completions"
)


# ============================================================================
# DOMINIO PERMITIDO PARA EL CHAT
# ============================================================================

TRADING_TERMS = (
    "trading",
    "trade",
    "spot",
    "future",
    "futures",
    "btc",
    "bitcoin",
    "eth",
    "sol",
    "xrp",
    "ada",
    "paxg",
    "señal",
    "senal",
    "long",
    "short",
    "entry",
    "entrada",
    "stop",
    "sl",
    "tp",
    "take profit",
    "riesgo",
    "margen",
    "leverage",
    "apalanc",
    "portfolio",
    "portafolio",
    "guardian",
    "guardián",
    "mercado",
    "rotación",
    "rotacion",
    "liquidez",
    "safety",
    "expectancy",
    "rentabilidad",
    "winrate",
    "win rate",
    "r/r",
    "rr",
    "smart money",
    "sweep",
    "mss",
    "displacement",
    "poi",
    "indicador",
    "tendencia",
    "volatilidad",
    "reviewtrader",
    "smartradingreview",
    "operación",
    "operacion",
    "oportunidad"
)


# ============================================================================
# RESPUESTA ESTRUCTURADA OBLIGATORIA
# ============================================================================

AI_SCHEMA = {
    "name":
        "smartradingreview_advice",

    "strict":
        True,

    "schema": {

        "type":
            "object",

        "additionalProperties":
            False,

        "properties": {

            "verdict": {
                "type":
                    "string",

                "enum": [
                    "SUPPORT",
                    "CAUTION",
                    "DISAGREE",
                    "NO_EDGE",
                    "INFO"
                ]
            },

            "confidence": {
                "type":
                    "integer",

                "minimum":
                    0,

                "maximum":
                    100
            },

            "headline": {
                "type":
                    "string"
            },

            "advice": {
                "type":
                    "string"
            },

            "why": {
                "type":
                    "array",

                "items": {
                    "type":
                        "string"
                },

                "maxItems":
                    5
            },

            "risks": {
                "type":
                    "array",

                "items": {
                    "type":
                        "string"
                },

                "maxItems":
                    5
            },

            "what_to_watch": {
                "type":
                    "array",

                "items": {
                    "type":
                        "string"
                },

                "maxItems":
                    5
            },

            "learning_hypotheses": {
                "type":
                    "array",

                "items": {
                    "type":
                        "string"
                },

                "maxItems":
                    5
            },

            "system_alignment": {
                "type":
                    "string"
            },

            "personal_risk_note": {
                "type":
                    "string"
            },

            "portfolio_note": {
                "type":
                    "string"
            },

            "authority": {
                "type":
                    "string",

                "enum": [
                    "ADVISORY_ONLY"
                ]
            }
        },

        "required": [
            "verdict",
            "confidence",
            "headline",
            "advice",
            "why",
            "risks",
            "what_to_watch",
            "learning_hypotheses",
            "system_alignment",
            "personal_risk_note",
            "portfolio_note",
            "authority"
        ]
    }
}


# ============================================================================
# HELPERS
# ============================================================================

def _db():

    try:

        from supabase_client import (
            supabase_db
        )

        return supabase_db

    except Exception:

        return None


def _now():

    return datetime.now(
        timezone.utc
    )


# ============================================================================
# CUOTAS
# ============================================================================

def _count_usage(
    since_iso,
    user_name=None,
    usage_type=None
):

    db = _db()

    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return -1

    try:

        def _op():

            q = (
                db.client
                .table(
                    "ai_usage_events"
                )
                .select(
                    "id",
                    count="exact"
                )
                .gte(
                    "created_at",
                    since_iso
                )
                .limit(
                    1
                )
            )


            if user_name:

                q = q.eq(
                    "user_name",
                    str(
                        user_name
                    )
                )


            if usage_type:

                q = q.eq(
                    "usage_type",
                    str(
                        usage_type
                    ).upper()
                )


            return q.execute()


        result = db._with_retry(
            _op
        )


        return int(
            result.count
            if result.count
            is not None
            else 0
        )


    except Exception as e:

        logger.warning(
            "AI quota count: %s",
            e
        )

        return -1


def get_ai_quota_status(
    user_name
):

    now = _now()


    hour = (
        now
        - timedelta(
            hours=1
        )
    ).isoformat()


    day = (
        now
        - timedelta(
            hours=24
        )
    ).isoformat()


    values = {

        "mh":
            _count_usage(
                hour,
                user_name,
                "MANUAL"
            ),

        "md":
            _count_usage(
                day,
                user_name,
                "MANUAL"
            ),

        "ad":
            _count_usage(
                day,
                None,
                "AUTO"
            ),

        "ld":
            _count_usage(
                day,
                None,
                "LEARNING"
            ),

        "gd":
            _count_usage(
                day
            )
    }


    def item(
        used,
        limit
    ):

        used = max(
            0,
            used
        )

        return {
            "used":
                used,

            "limit":
                limit,

            "remaining":
                max(
                    0,
                    limit - used
                )
        }


    return {

        "enabled":
            AI_ENABLED,

        "provider":
            AI_PROVIDER,

        "model":
            AI_MODEL,

        # Ventanas móviles:
        # "última hora" y "últimas 24 horas".
        "window":
            "ROLLING",

        "manual_hourly":
            item(
                values["mh"],
                LIMIT_MANUAL_HOUR
            ),

        "manual_daily":
            item(
                values["md"],
                LIMIT_MANUAL_DAY
            ),

        "automatic_daily":
            item(
                values["ad"],
                LIMIT_AUTO_DAY
            ),

        "learning_daily":
            item(
                values["ld"],
                LIMIT_LEARNING_DAY
            ),

        "global_daily":
            item(
                values["gd"],
                LIMIT_GLOBAL_DAY
            ),

        "quota_storage_ok":
            all(
                value >= 0
                for value
                in values.values()
            )
    }


def _quota_allowed(
    user_name,
    usage_type
):

    quota = (
        get_ai_quota_status(
            user_name
        )
    )


    # Si Supabase falla,
    # protegemos presupuesto IA.
    if not quota[
        "quota_storage_ok"
    ]:

        return (
            False,
            (
                "No se pudo verificar "
                "la cuota persistente."
            ),
            quota
        )


    if (
        quota[
            "global_daily"
        ][
            "remaining"
        ]
        <= 0
    ):

        return (
            False,
            (
                "Se alcanzó el límite "
                "diario global de IA."
            ),
            quota
        )


    usage_type = str(
        usage_type
    ).upper()


    if usage_type == "MANUAL":

        if (
            quota[
                "manual_hourly"
            ][
                "remaining"
            ]
            <= 0
        ):

            return (
                False,
                (
                    "Ya usaste tus "
                    "3 preguntas disponibles "
                    "en la última hora."
                ),
                quota
            )


        if (
            quota[
                "manual_daily"
            ][
                "remaining"
            ]
            <= 0
        ):

            return (
                False,
                (
                    "Se alcanzó tu límite "
                    "diario de preguntas IA."
                ),
                quota
            )


    elif (
        usage_type
        == "AUTO"
    ):

        if (
            quota[
                "automatic_daily"
            ][
                "remaining"
            ]
            <= 0
        ):

            return (
                False,
                (
                    "Se alcanzó el límite "
                    "diario de consejos "
                    "automáticos."
                ),
                quota
            )


    elif (
        usage_type
        == "LEARNING"
    ):

        if (
            quota[
                "learning_daily"
            ][
                "remaining"
            ]
            <= 0
        ):

            return (
                False,
                (
                    "Se alcanzó el límite "
                    "diario de aprendizaje IA."
                ),
                quota
            )


    else:

        return (
            False,
            "Tipo de uso IA inválido.",
            quota
        )


    return (
        True,
        None,
        quota
    )


def _record_usage(
    user_name,
    usage_type,
    context_type,
    market,
    status,
    usage=None
):

    db = _db()

    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return


    usage = usage or {}


    payload = {

        "user_name":
            str(
                user_name
            )[:120],

        "usage_type":
            str(
                usage_type
            ).upper()[:30],

        "context_type":
            str(
                context_type
            ).upper()[:40],

        "market":
            str(
                market
            ).upper()[:20],

        "provider":
            AI_PROVIDER,

        "model":
            AI_MODEL[:120],

        "status":
            str(
                status
            ).upper()[:30],

        "input_tokens":
            int(
                usage.get(
                    "prompt_tokens",
                    0
                )
                or 0
            ),

        "output_tokens":
            int(
                usage.get(
                    "completion_tokens",
                    0
                )
                or 0
            ),

        "total_tokens":
            int(
                usage.get(
                    "total_tokens",
                    0
                )
                or 0
            ),

        "created_at":
            _now()
            .isoformat()
    }


    try:

        db._with_retry(
            lambda: (
                db.client
                .table(
                    "ai_usage_events"
                )
                .insert(
                    payload
                )
                .execute()
            )
        )


    except Exception as e:

        logger.warning(
            "AI usage insert: %s",
            e
        )


# ============================================================================
# RESTRICCIÓN DEL CHAT
# ============================================================================

def is_trading_question(
    question
):

    text = str(
        question
        or ""
    ).strip().lower()


    return (
        len(
            text
        ) >= 3

        and any(
            term in text
            for term
            in TRADING_TERMS
        )
    )


# ============================================================================
# CACHÉ
# ============================================================================

def _fingerprint(
    context,
    context_type,
    event_type,
    market,
    question
):

    raw = json.dumps(

        {
            "context":
                context,

            "context_type":
                context_type,

            "event_type":
                event_type,

            "market":
                market,

            "question":
                str(
                    question
                    or ""
                ).strip()
        },

        ensure_ascii=False,

        sort_keys=True,

        separators=(
            ",",
            ":"
        ),

        default=str
    )


    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


def _cache_get(
    user_name,
    context_type,
    fingerprint
):

    db = _db()


    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return None


    try:

        result = db._with_retry(

            lambda: (

                db.client

                .table(
                    "ai_advisor_observations"
                )

                .select(
                    "id,response_json"
                )

                .eq(
                    "user_name",
                    str(
                        user_name
                    )
                )

                .eq(
                    "context_type",
                    str(
                        context_type
                    ).upper()
                )

                .eq(
                    "input_fingerprint",
                    fingerprint
                )

                .limit(
                    1
                )

                .execute()
            )
        )


        if (
            result
            and result.data
        ):

            data = dict(
                result.data[0]
                .get(
                    "response_json"
                )
                or {}
            )


            data[
                "observation_id"
            ] = (
                result.data[0]
                .get(
                    "id"
                )
            )


            return data


    except Exception as e:

        logger.warning(
            "AI cache: %s",
            e
        )


    return None


# ============================================================================
# MENTALIDAD DEL AI TRADER
# ============================================================================

def _system_prompt():

    return """
Eres el AI Advisor de SmartradingReview.

Piensas como un trader experto que domina ESTE sistema.

POLÍTICA:
- ASERTIVO PERO CAUTO.
- PRECAVIDO PERO NO TÍMIDO.
- RENTABLE.

Prioriza EXPECTANCY NETA POSITIVA y preservación de capital.
Win Rate es importante, pero es secundario a rentabilidad neta,
R, costes, drawdown y riesgo.

Respeta:
Liquidity -> Sweep -> MSS -> Displacement -> POI -> Entry.

No inventes:
- datos;
- precios;
- indicadores;
- fills;
- costes;
- resultados;
- niveles.

Distingue:
- observado;
- estimado;
- desconocido.

No sobrevalores muestras pequeñas.

Puedes discrepar del comité, Guardian o ReviewTrader si la
evidencia presentada lo justifica. No seas complaciente.

SPOT:
protege acumulación y rotación BTC/PAXG/USDT.
Evita sobrerroración y pérdida innecesaria de reservas.

FUTURES:
prioriza expectancy/R, riesgo monetario, costes y supervivencia.

Margen NO equivale a pérdida aceptada al Stop Loss.

Tu función fundamental es detectar patrones e HIPÓTESIS
COMPROBABLES que puedan mejorar Win Rate y, sobre todo,
RENTABILIDAD NETA.

También aconsejas al usuario en lenguaje claro y personalizado.

Tu autoridad es ADVISORY_ONLY.

Nunca puedes saltarte:
- Safety;
- Publication Gate.

Nunca puedes modificar automáticamente:
- votos;
- pesos;
- Entry;
- Stop Loss;
- Take Profit;
- leverage;
- Guardian.
""".strip()


# ============================================================================
# GROQ
# ============================================================================

def _call_groq(
    context,
    question=None
):

    key = (
        os.getenv(
            "GROQ_API_KEY",
            ""
        )
        .strip()
    )


    if not key:

        raise RuntimeError(
            (
                "GROQ_API_KEY no está "
                "configurada en Render."
            )
        )


    context_text = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        default=str
    )


    if (
        len(
            context_text
        )
        > AI_MAX_CONTEXT
    ):

        context_text = (
            context_text[
                :AI_MAX_CONTEXT
            ]
            + "\n...[CONTEXTO RECORTADO]"
        )


    prompt = (
        "CONTEXTO DEL SISTEMA:\n"
        f"{context_text}"
    )


    if question:

        prompt += (
            "\n\nPREGUNTA DEL USUARIO:\n"
            + str(
                question
            ).strip()[:800]
        )


    response = requests.post(

        GROQ_URL,

        headers={
            "Authorization":
                f"Bearer {key}",

            "Content-Type":
                "application/json"
        },

        json={

            "model":
                AI_MODEL,

            "messages": [

                {
                    "role":
                        "system",

                    "content":
                        _system_prompt()
                },

                {
                    "role":
                        "user",

                    "content":
                        prompt
                }
            ],

            "temperature":
                0.2,

            "max_completion_tokens":
                900,

            "reasoning_effort":
                "low",

            "response_format": {

                "type":
                    "json_schema",

                "json_schema":
                    AI_SCHEMA
            }
        },

        timeout=
            AI_TIMEOUT
    )


    if (
        response.status_code
        != 200
    ):

        raise RuntimeError(
            (
                f"Groq HTTP "
                f"{response.status_code}: "
                f"{response.text[:160]}"
            )
        )


    raw = response.json()


    choices = (
        raw.get(
            "choices"
        )
        or []
    )


    if not choices:

        raise RuntimeError(
            "Groq no devolvió respuesta."
        )


    advice = json.loads(
        choices[0][
            "message"
        ][
            "content"
        ]
    )


    # ================================================================
    # GUARDRAILS DUROS
    # ================================================================

    advice.update({

        "authority":
            "ADVISORY_ONLY",

        "affect_decision":
            False,

        "affect_safety":
            False,

        "affect_levels":
            False,

        "affect_leverage":
            False,

        "affect_weights":
            False
    })


    return (
        advice,
        raw.get(
            "usage"
        )
        or {}
    )


# ============================================================================
# PERSISTENCIA
# ============================================================================

def _persist(
    user_name,
    usage_type,
    context_type,
    event_type,
    market,
    fingerprint,
    advice,
    context,
    symbol=None,
    timeframe=None,
    related_saved_signal_id=None,
    source_signal_id=None,
    question=None
):

    db = _db()


    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return None


    system_action = (

        context.get(
            "system_action"
        )

        or (
            context.get(
                "selected_signal"
            )
            or {}
        ).get(
            "action"
        )

        or (
            context.get(
                "guardian"
            )
            or {}
        ).get(
            "action"
        )

        or ""
    )


    payload = {

        "user_name":
            str(
                user_name
            )[:120],

        "usage_type":
            str(
                usage_type
            ).upper()[:30],

        "context_type":
            str(
                context_type
            ).upper()[:40],

        "event_type":
            str(
                event_type
                or ""
            )[:80],

        "market":
            str(
                market
            ).upper()[:20],

        "symbol":
            (
                str(
                    symbol
                    or ""
                )[:40]
                or None
            ),

        "timeframe":
            (
                str(
                    timeframe
                    or ""
                )[:20]
                or None
            ),

        "related_saved_signal_id":
            (
                related_saved_signal_id
                or None
            ),

        "source_signal_id":
            (
                str(
                    source_signal_id
                    or ""
                )[:160]
                or None
            ),

        "input_fingerprint":
            fingerprint,

        "provider":
            AI_PROVIDER,

        "model":
            AI_MODEL[:120],

        "system_action":
            (
                str(
                    system_action
                )[:40]
                or None
            ),

        "ai_verdict":
            str(
                advice.get(
                    "verdict",
                    "INFO"
                )
            )[:30],

        "ai_confidence":
            int(
                advice.get(
                    "confidence",
                    0
                )
                or 0
            ),

        "response_json":
            advice,

        "context_snapshot":
            context,

        "assistant_question":
            (
                str(
                    question
                    or ""
                )[:800]
                or None
            ),

        "authority":
            "ADVISORY_ONLY",

        "affect_decision":
            False,

        "affect_safety":
            False,

        "affect_levels":
            False,

        "affect_leverage":
            False,

        "affect_weights":
            False,

        "outcome_status":
            (
                "PENDING"
                if related_saved_signal_id
                else "NOT_LINKED"
            ),

        "created_at":
            _now()
            .isoformat(),

        "updated_at":
            _now()
            .isoformat()
    }


    try:

        result = db._with_retry(

            lambda: (

                db.client

                .table(
                    "ai_advisor_observations"
                )

                .insert(
                    payload
                )

                .execute()
            )
        )


        if (
            result
            and result.data
        ):

            return (
                result.data[0]
                .get(
                    "id"
                )
            )


    except Exception as e:

        logger.warning(
            "AI observation insert: %s",
            e
        )


    return None


# ============================================================================
# PUNTO ÚNICO DE ENTRADA
# ============================================================================

def run_ai_advisor(
    user_name,
    usage_type,
    context_type,
    event_type,
    market,
    context,
    symbol=None,
    timeframe=None,
    related_saved_signal_id=None,
    source_signal_id=None,
    question=None
):

    if not AI_ENABLED:

        return {
            "success":
                False,

            "reason":
                "AI_ADVISOR_ENABLED=false",

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


    if (
        AI_PROVIDER
        != "GROQ"
    ):

        return {
            "success":
                False,

            "reason":
                (
                    "Proveedor no soportado: "
                    f"{AI_PROVIDER}"
                ),

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


    usage_type = str(
        usage_type
    ).upper()


    context_type = str(
        context_type
    ).upper()


    market = str(
        market
    ).upper()


    # Preguntas ajenas a trading:
    # se rechazan SIN gastar llamada.
    if (
        usage_type
        == "MANUAL"

        and not is_trading_question(
            question
        )
    ):

        return {

            "success":
                False,

            "reason":
                (
                    "Este asistente sólo responde "
                    "sobre SmartradingReview, mercado, "
                    "señales, riesgo, portafolio y "
                    "gestión de trading."
                ),

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


    fingerprint = _fingerprint(
        context,
        context_type,
        event_type,
        market,
        question
    )


    # ================================================================
    # CACHÉ ANTES DE CUOTA
    # ================================================================

    cached = _cache_get(
        user_name,
        context_type,
        fingerprint
    )


    if cached:

        return {

            "success":
                True,

            "cached":
                True,

            "data":
                cached,

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


    allowed, reason, quota = (
        _quota_allowed(
            user_name,
            usage_type
        )
    )


    if not allowed:

        return {

            "success":
                False,

            "quota_limited":
                True,

            "reason":
                reason,

            "quota":
                quota
        }


    try:

        advice, usage = (
            _call_groq(
                context,
                question
            )
        )


        _record_usage(
            user_name,
            usage_type,
            context_type,
            market,
            "SUCCESS",
            usage
        )


        advice[
            "observation_id"
        ] = _persist(

            user_name,
            usage_type,
            context_type,
            event_type,
            market,
            fingerprint,
            advice,
            context,
            symbol,
            timeframe,
            related_saved_signal_id,
            source_signal_id,
            question
        )


        return {

            "success":
                True,

            "cached":
                False,

            "data":
                advice,

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


    except Exception as e:

        logger.warning(
            "AI call: %s",
            e
        )


        _record_usage(
            user_name,
            usage_type,
            context_type,
            market,
            "ERROR",
            {}
        )


        return {

            "success":
                False,

            "reason":
                str(
                    e
                )[:220],

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }


# ============================================================================
# 36R.7 — EVALUAR LA PROPIA IA
# ============================================================================

def settle_ai_outcomes(
    limit=100
):

    stats = {
        "pending":
            0,

        "settled":
            0,

        "errors":
            0
    }


    db = _db()


    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return stats


    try:

        result = db._with_retry(

            lambda: (

                db.client

                .table(
                    "ai_advisor_observations"
                )

                .select(
                    "id,related_saved_signal_id"
                )

                .eq(
                    "outcome_status",
                    "PENDING"
                )

                .order(
                    "created_at",
                    desc=False
                )

                .limit(
                    max(
                        1,
                        min(
                            int(
                                limit
                            ),
                            500
                        )
                    )
                )

                .execute()
            )
        )


        rows = (
            result.data

            if (
                result
                and result.data
            )

            else []
        )


        stats[
            "pending"
        ] = len(
            rows
        )


        from saved_signals import (
            get_saved_signal
        )


        for row in rows:

            try:

                signal = (
                    get_saved_signal(
                        row.get(
                            "related_saved_signal_id"
                        )
                    )
                )


                if not signal:

                    continue


                status = str(
                    signal.get(
                        "status",
                        ""
                    )
                ).lower()


                if status not in (
                    "tp_hit",
                    "sl_hit",
                    "closed_manual"
                ):

                    continue


                outcome_r = None

                source = None


                # Preferimos neto 36O.
                for (
                    field,
                    label
                ) in (

                    (
                        "estimated_net_r",
                        "ESTIMATED_NET_R_36O"
                    ),

                    (
                        "gross_r",
                        "GROSS_R"
                    ),

                    (
                        "actual_close_r",
                        "ACTUAL_CLOSE_R"
                    )
                ):

                    try:

                        if (
                            signal.get(
                                field
                            )
                            is not None
                        ):

                            outcome_r = float(
                                signal[
                                    field
                                ]
                            )

                            source = label

                            break


                    except (
                        TypeError,
                        ValueError
                    ):

                        pass


                pnl = signal.get(
                    "estimated_net_pnl_usdt",
                    signal.get(
                        "pnl_usdt"
                    )
                )


                try:

                    pnl = (
                        float(
                            pnl
                        )
                        if pnl
                        is not None
                        else None
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    pnl = None


                updates = {

                    "outcome_status":
                        (
                            "SETTLED"
                            if outcome_r
                            is not None
                            else "SETTLED_NO_R"
                        ),

                    "outcome_r":
                        outcome_r,

                    "outcome_pnl_usdt":
                        pnl,

                    "outcome_win":
                        (
                            bool(
                                outcome_r > 0
                            )
                            if outcome_r
                            is not None
                            else None
                        ),

                    "outcome_source":
                        source,

                    "settled_at":
                        _now()
                        .isoformat(),

                    "updated_at":
                        _now()
                        .isoformat()
                }


                db._with_retry(

                    lambda: (

                        db.client

                        .table(
                            "ai_advisor_observations"
                        )

                        .update(
                            updates
                        )

                        .eq(
                            "id",
                            row[
                                "id"
                            ]
                        )

                        .execute()
                    )
                )


                stats[
                    "settled"
                ] += 1


            except Exception as row_error:

                stats[
                    "errors"
                ] += 1


                logger.warning(
                    "AI outcome row: %s",
                    row_error
                )


    except Exception as e:

        stats[
            "errors"
        ] += 1


        logger.warning(
            "AI outcomes: %s",
            e
        )


    return stats


def get_ai_performance_summary(
    user_name=None
):

    empty = {

        "mode":
            "SHADOW_ONLY",

        "authority":
            "NONE",

        "settled_total":
            0,

        "coverage_note":
            (
                "Sólo observaciones ligadas "
                "a Saved Futures cerradas."
            ),

        "by_verdict":
            {}
    }


    db = _db()


    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return empty


    try:

        def _op():

            q = (

                db.client

                .table(
                    "ai_advisor_observations"
                )

                .select(
                    (
                        "ai_verdict,"
                        "outcome_r,"
                        "outcome_win,"
                        "outcome_source"
                    )
                )

                .eq(
                    "outcome_status",
                    "SETTLED"
                )
            )


            if user_name:

                q = q.eq(
                    "user_name",
                    str(
                        user_name
                    )
                )


            return q.execute()


        result = db._with_retry(
            _op
        )


        buckets = {}


        for row in (
            result.data
            if (
                result
                and result.data
            )
            else []
        ):

            try:

                r_value = float(
                    row.get(
                        "outcome_r"
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                continue


            verdict = str(
                row.get(
                    "ai_verdict",
                    "INFO"
                )
            ).upper()


            bucket = buckets.setdefault(

                verdict,

                {
                    "sample":
                        0,

                    "wins":
                        0,

                    "sum_r":
                        0.0,

                    "sources":
                        {}
                }
            )


            bucket[
                "sample"
            ] += 1


            bucket[
                "sum_r"
            ] += r_value


            if bool(
                row.get(
                    "outcome_win"
                )
            ):

                bucket[
                    "wins"
                ] += 1


            source = str(
                row.get(
                    "outcome_source",
                    "UNKNOWN"
                )
            )


            bucket[
                "sources"
            ][
                source
            ] = (

                bucket[
                    "sources"
                ].get(
                    source,
                    0
                )

                + 1
            )


        final = {}


        for (
            verdict,
            bucket
        ) in buckets.items():

            sample = bucket[
                "sample"
            ]


            final[
                verdict
            ] = {

                "sample":
                    sample,

                "win_rate":
                    (
                        round(
                            (
                                bucket[
                                    "wins"
                                ]
                                / sample
                                * 100
                            ),
                            2
                        )
                        if sample
                        else 0.0
                    ),

                "avg_outcome_r":
                    (
                        round(
                            (
                                bucket[
                                    "sum_r"
                                ]
                                / sample
                            ),
                            4
                        )
                        if sample
                        else None
                    ),

                "sources":
                    bucket[
                        "sources"
                    ]
            }


        return {

            **empty,

            "settled_total":
                sum(
                    item[
                        "sample"
                    ]
                    for item
                    in final.values()
                ),

            "by_verdict":
                final
        }


    except Exception as e:

        logger.warning(
            "AI performance: %s",
            e
        )


        return empty
# ============================================================================
# COMMIT 36S.1 — AI CONTROL LAYER
# ============================================================================

AI_CONTROL_ENABLED = (
    os.getenv(
        "AI_CONTROL_ENABLED",
        "false"
    )
    .strip()
    .lower()
    in (
        "1",
        "true",
        "yes",
        "si",
        "sí"
    )
)


AI_CONTROL_MIN_CONFIDENCE = max(
    50,
    min(
        100,
        int(
            os.getenv(
                "AI_CONTROL_MIN_CONFIDENCE",
                "80"
            )
        )
    )
)


AI_CONTROL_MODE = (
    os.getenv(
        "AI_CONTROL_MODE",
        "CAUTIOUS_OVERLAY"
    )
    .strip()
    .upper()
)


def evaluate_ai_control(
    ai_result,
    context_type,
    original_action,
    original_publication_status=None
):
    """
    Autoridad 36S.1, deliberadamente limitada.

    SIGNAL:
        una IA con DISAGREE fuerte puede bloquear
        una señal ya EXECUTABLE_SIGNAL.

    GUARDIAN:
        EXTEND -> HOLD
        PROTECT_AND_EXTEND -> PROTECT

    Nunca:
        - promociona señales rechazadas;
        - cancela PROTECT;
        - cancela REDUCE;
        - cancela EXIT.
    """

    context_type = str(
        context_type
        or ""
    ).upper()

    original_action = str(
        original_action
        or ""
    ).upper()

    publication = str(
        original_publication_status
        or ""
    ).upper()


    control = {

        "enabled":
            AI_CONTROL_ENABLED,

        "mode":
            AI_CONTROL_MODE,

        "applied":
            False,

        "control_action":
            "NO_CHANGE",

        "original_action":
            original_action,

        "final_action":
            original_action,

        "original_publication_status":
            publication
            or None,

        "final_publication_status":
            publication
            or None,

        "ai_verdict":
            None,

        "ai_confidence":
            None,

        "minimum_confidence":
            AI_CONTROL_MIN_CONFIDENCE,

        "reason":
            None,

        "observation_id":
            None,
    }


    if not AI_CONTROL_ENABLED:

        control[
            "reason"
        ] = "AI_CONTROL_DISABLED"

        return control


    if (
        not isinstance(
            ai_result,
            dict
        )
        or not ai_result.get(
            "success"
        )
    ):

        control[
            "reason"
        ] = (
            "AI_UNAVAILABLE_OR_FAILED"
        )

        return control


    data = (
        ai_result.get(
            "data"
        )
        or {}
    )


    verdict = str(
        data.get(
            "verdict"
        )
        or ""
    ).upper()


    try:

        confidence = int(
            float(
                data.get(
                    "confidence"
                )
                or 0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        confidence = 0


    control[
        "ai_verdict"
    ] = verdict

    control[
        "ai_confidence"
    ] = confidence

    control[
        "observation_id"
    ] = data.get(
        "observation_id"
    )


    control[
        "reason"
    ] = str(
        data.get(
            "headline"
        )
        or data.get(
            "advice"
        )
        or ""
    )[:500]


    # ================================================================
    # Sólo una discrepancia FUERTE recibe autoridad.
    # ================================================================

    if (
        verdict
        != "DISAGREE"

        or confidence
        < AI_CONTROL_MIN_CONFIDENCE
    ):

        return control


    # ================================================================
    # SEÑALES
    # ================================================================

    if (
        context_type
        == "SIGNAL"
    ):

        if (
            original_action
            in (
                "LONG",
                "SHORT",
                "COMPRA_SPOT",
                "VENTA_SPOT",
            )

            and publication
            == "EXECUTABLE_SIGNAL"
        ):

            control.update({

                "applied":
                    True,

                "control_action":
                    "BLOCK_SIGNAL",

                # La dirección se conserva para auditoría.
                "final_action":
                    original_action,

                "final_publication_status":
                    "AI_BLOCKED",
            })


        return control


    # ================================================================
    # GUARDIAN
    # ================================================================

    if (
        context_type
        == "GUARDIAN"
    ):

        # EXTEND aumenta exposición temporal.
        # IA puede vetarlo.

        if (
            original_action
            == "EXTEND"
        ):

            control.update({

                "applied":
                    True,

                "control_action":
                    "BLOCK_EXTEND",

                "final_action":
                    "HOLD",
            })


        # Conservamos la parte protectora,
        # eliminamos solamente la extensión.

        elif (
            original_action
            == "PROTECT_AND_EXTEND"
        ):

            control.update({

                "applied":
                    True,

                "control_action":
                    "STRIP_EXTEND",

                "final_action":
                    "PROTECT",
            })


    return control


def record_ai_control_event(
    *,
    dedup_key,
    context_type,
    market,
    symbol,
    timeframe,
    control,
    related_saved_signal_id=None,
    source_signal_id=None,
    source_candle_timestamp=None
):
    """
    Guarda la decisión 36S.

    Un fallo aquí NO rompe producción.
    """

    if not isinstance(
        control,
        dict
    ):

        return False


    db = _db()


    if (
        db is None

        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return False


    payload = {

        "dedup_key":
            str(
                dedup_key
            )[:240],

        "context_type":
            str(
                context_type
            ).upper()[:30],

        "market":
            str(
                market
            ).upper()[:20],

        "symbol":
            str(
                symbol
                or ""
            )[:40]
            or None,

        "timeframe":
            str(
                timeframe
                or ""
            )[:20]
            or None,

        "related_saved_signal_id":
            related_saved_signal_id
            or None,

        "source_signal_id":
            str(
                source_signal_id
                or ""
            )[:160]
            or None,

        "source_candle_timestamp":
            str(
                source_candle_timestamp
                or ""
            )[:80]
            or None,

        "ai_observation_id":
            control.get(
                "observation_id"
            ),

        "original_action":
            control.get(
                "original_action"
            ),

        "original_publication_status":
            control.get(
                "original_publication_status"
            ),

        "ai_verdict":
            control.get(
                "ai_verdict"
            ),

        "ai_confidence":
            control.get(
                "ai_confidence"
            ),

        "minimum_confidence":
            control.get(
                "minimum_confidence"
            ),

        "control_action":
            control.get(
                "control_action",
                "NO_CHANGE"
            ),

        "final_action":
            control.get(
                "final_action"
            ),

        "final_publication_status":
            control.get(
                "final_publication_status"
            ),

        "applied":
            bool(
                control.get(
                    "applied"
                )
            ),

        "reason":
            str(
                control.get(
                    "reason"
                )
                or ""
            )[:1000],

        "updated_at":
            _now()
            .isoformat(),
    }


    try:

        db._with_retry(

            lambda: (

                db.client

                .table(
                    "ai_control_events"
                )

                .upsert(
                    payload,
                    on_conflict=
                        "dedup_key"
                )

                .execute()
            )
        )


        return True


    except Exception as e:

        logger.warning(
            "AI control event: %s",
            e
        )


        return False


def get_ai_control_event(
    dedup_key
):
    """
    Recupera una decisión 36S ya tomada.

    Esto es MUY importante:

    una misma vela/evento NO puede recibir una decisión
    diferente de la IA cinco minutos después.
    """

    db = _db()


    if (
        db is None

        or not getattr(
            db,
            "enabled",
            False
        )
    ):

        return None


    try:

        result = db._with_retry(

            lambda: (

                db.client

                .table(
                    "ai_control_events"
                )

                .select(
                    (
                        "applied,"
                        "control_action,"
                        "original_action,"
                        "final_action,"
                        "original_publication_status,"
                        "final_publication_status,"
                        "ai_verdict,"
                        "ai_confidence,"
                        "minimum_confidence,"
                        "reason,"
                        "ai_observation_id"
                    )
                )

                .eq(
                    "dedup_key",
                    str(
                        dedup_key
                    )
                )

                .limit(
                    1
                )

                .execute()
            )
        )


        if (
            not result
            or not result.data
        ):

            return None


        row = dict(
            result.data[0]
        )


        return {

            "enabled":
                True,

            "mode":
                AI_CONTROL_MODE,

            "applied":
                bool(
                    row.get(
                        "applied"
                    )
                ),

            "control_action":
                row.get(
                    "control_action"
                )
                or "NO_CHANGE",

            "original_action":
                row.get(
                    "original_action"
                ),

            "final_action":
                row.get(
                    "final_action"
                ),

            "original_publication_status":
                row.get(
                    "original_publication_status"
                ),

            "final_publication_status":
                row.get(
                    "final_publication_status"
                ),

            "ai_verdict":
                row.get(
                    "ai_verdict"
                ),

            "ai_confidence":
                row.get(
                    "ai_confidence"
                ),

            "minimum_confidence":
                row.get(
                    "minimum_confidence"
                ),

            "reason":
                row.get(
                    "reason"
                ),

            "observation_id":
                row.get(
                    "ai_observation_id"
                ),

            "reused_control":
                True,
        }


    except Exception as e:

        logger.warning(
            "AI control read: %s",
            e
        )

        return None
