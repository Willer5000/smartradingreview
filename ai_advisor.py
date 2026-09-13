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

# ============================================================================
# AI QUOTA GUARD — CONTEXTO GROQ COMPACTO
# ============================================================================
#
# Gemini Learning conserva AI_MAX_CONTEXT porque su trabajo es investigar.
#
# Groq Runtime (Chat / Consejo / Guardian / Decision Control) usa un contexto
# más compacto para proteger el Free Tier sin modificar ninguna decisión del
# sistema de trading.
# ============================================================================

GROQ_MAX_CONTEXT = max(
    4000,
    min(
        12000,
        int(
            os.getenv(
                "AI_GROQ_MAX_CONTEXT_CHARS",
                "8000"
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

# Límite diario por usuario.
#
# El Chat IA conserva un máximo de 3 preguntas
# por hora para proteger la cuota gratuita.
#
# El límite diario se controla por separado.
LIMIT_MANUAL_DAY = max(
    1,
    int(
        os.getenv(
            "AI_MANUAL_DAILY_LIMIT",
            "60"
        )
    )
)

LIMIT_HOURLY_ADVICE_DAY = max(
    1,
    int(
        os.getenv(
            "AI_HOURLY_ADVICE_DAILY_LIMIT",
            "96"
        )
    )
)


LIMIT_AUTO_CONTROL_DAY = max(
    1,
    int(
        os.getenv(
            "AI_AUTO_CONTROL_DAILY_LIMIT",
            "60"
        )
    )
)


# Límite agregado informativo.
#
# Ya NO será el gate que mezcle Consejo horario,
# Guardian y Decision Control.
#
# Se conserva por compatibilidad con el endpoint
# de estado y para observar el consumo AUTO total.
LIMIT_AUTO_DAY = max(
    1,
    int(
        os.getenv(
            "AI_AUTOMATIC_DAILY_LIMIT",
            "150"
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


# También se mantiene como métrica agregada.
#
# Las categorías tienen sus propios gates para impedir
# que una actividad agote la cuota de otra.
LIMIT_GLOBAL_DAY = max(
    1,
    int(
        os.getenv(
            "AI_GLOBAL_DAILY_LIMIT",
            "180"
        )
    )
)


GROQ_URL = (
    "https://api.groq.com/"
    "openai/v1/chat/completions"
)
# ============================================================================
# AI QUOTA GUARD — BACKOFF GROQ
# ============================================================================
#
# Si Groq responde 429, respetamos Retry-After y dejamos de enviar nuevas
# llamadas externas durante ese intervalo.
#
# IMPORTANTE:
# - no cambia trading;
# - no cambia Safety;
# - no cambia señales;
# - no cambia Entry / SL / TP;
# - evita una tormenta de reintentos cuando se agota la cuota gratuita.
# ============================================================================

_GROQ_BACKOFF_UNTIL = None
_GROQ_BACKOFF_REASON = ""


def _groq_backoff_remaining_seconds():
    global _GROQ_BACKOFF_UNTIL

    if _GROQ_BACKOFF_UNTIL is None:
        return 0

    now = datetime.now(
        timezone.utc
    )

    if now >= _GROQ_BACKOFF_UNTIL:
        _GROQ_BACKOFF_UNTIL = None
        return 0

    return max(
        1,
        int(
            (
                _GROQ_BACKOFF_UNTIL
                - now
            ).total_seconds()
        )
    )


def _activate_groq_backoff(
    response
):
    global _GROQ_BACKOFF_UNTIL
    global _GROQ_BACKOFF_REASON

    # Si Groq no entrega Retry-After, esperamos 5 minutos
    # como fallback conservador.
    retry_seconds = 300

    try:
        retry_after = (
            response.headers.get(
                "retry-after"
            )
        )

        if retry_after:
            retry_seconds = int(
                float(
                    retry_after
                )
            )

    except (
        TypeError,
        ValueError
    ):
        retry_seconds = 300

    response_text = str(
        getattr(
            response,
            "text",
            ""
        )
        or ""
    )

    is_daily_token_limit = (
        "tokens per day"
        in response_text.lower()
        or "tpd"
        in response_text.lower()
    )

    if is_daily_token_limit:
        # Si por algún motivo Retry-After no llegó,
        # no golpeamos la API cada minuto.
        retry_seconds = max(
            retry_seconds,
            15 * 60
        )

        _GROQ_BACKOFF_REASON = (
            "TPD_DAILY_TOKEN_LIMIT"
        )

    else:
        _GROQ_BACKOFF_REASON = (
            "RATE_LIMIT"
        )

    retry_seconds = max(
        60,
        min(
            6 * 60 * 60,
            retry_seconds + 5
        )
    )

    _GROQ_BACKOFF_UNTIL = (
        datetime.now(
            timezone.utc
        )
        + timedelta(
            seconds=retry_seconds
        )
    )

    return retry_seconds
    
def _learning_key_provider():
    """Commit 10: detect the provider stored in the legacy learning key slot.

    Historical deployments used GEMINI_API_KEY as the learning-scientist slot.
    If that value is a Groq key (gsk_), we route it to Groq instead of sending
    it incorrectly to Google's endpoint.  The variable name is retained only
    for backwards compatibility; Analytics exposes the real provider.
    """
    dedicated_groq = os.getenv("GROQ_LEARNING_API_KEY", "").strip()
    if dedicated_groq:
        return "GROQ_LEARNING", dedicated_groq

    # Legacy slot requested by the current deployment.  A gsk_ value is a
    # Groq key; any other non-empty value is treated as a Gemini key.
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return "NONE", ""
    if key.lower().startswith("gsk_"):
        return "GROQ_LEARNING", key
    return "GEMINI", key


def _learning_provider_label(provider):
    provider = str(provider or "").upper()
    if provider == "GROQ_LEARNING":
        return "Groq · científico de aprendizaje"
    if provider == "GEMINI":
        return "Gemini · científico de aprendizaje"
    if provider == "GROQ":
        return "Groq · proveedor alternativo"
    return "Científico de aprendizaje IA"


def _resolve_ai_route(
    usage_type,
    context_type
):
    """
    Router defensivo 36S.2C.

    Chat / Consejo / Guardian / Decision Control:
        siempre GROQ.

    Learning:
        GEMINI sólo si:
        - existe GEMINI_API_KEY;
        - está habilitado;
        - la función _call_gemini_learning existe realmente.

    Si algo falta, vuelve a Groq.

    Esta función es deliberadamente fail-open para impedir que
    una integración experimental de Gemini rompa la IA operativa.
    """

    usage_type = str(
        usage_type
        or ""
    ).strip().upper()

    context_type = str(
        context_type
        or ""
    ).strip().upper()

    # ================================================================
    # RUNTIME OPERATIVO
    # ================================================================
    #
    # Consejo, Chat, Guardian y Decision Control permanecen
    # exclusivamente en Groq.
    # ================================================================

    if not (
        usage_type == "LEARNING"
        and context_type == "LEARNING"
    ):
        return (
            "GROQ",
            AI_MODEL
        )

    # ================================================================
    # LEARNING
    # ================================================================

    learning_provider, learning_key = _learning_key_provider()

    gemini_enabled = (
        os.getenv(
            "GEMINI_LEARNING_ENABLED",
            "true"
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

    # La función puede estar declarada más abajo en el archivo.
    # En tiempo de ejecución globals() ya podrá verla.
    gemini_function_ready = callable(
        globals().get(
            "_call_gemini_learning"
        )
    )

    if learning_key and gemini_enabled:
        if learning_provider == "GROQ_LEARNING":
            model = (
                os.getenv("GROQ_LEARNING_MODEL", AI_MODEL).strip()
                or AI_MODEL
            )
            return ("GROQ_LEARNING", model)

        if learning_provider == "GEMINI" and gemini_function_ready:
            model = (
                os.getenv(
                    "GEMINI_LEARNING_MODEL",
                    "gemini-3.7-flash"
                )
                .strip()
                or "gemini-3.7-flash"
            )
            return ("GEMINI", model)

    # ================================================================
    # FALLBACK
    # ================================================================

    return (
        "GROQ",
        AI_MODEL
    )
# ============================================================================
# COMMIT 36S.2C
# GEMINI — LEARNING SCIENTIST SHADOW
# ============================================================================

GEMINI_LEARNING_ENABLED = (
    os.getenv(
        "GEMINI_LEARNING_ENABLED",
        "true"
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


GEMINI_LEARNING_MODEL = (
    os.getenv(
        "GEMINI_LEARNING_MODEL",
        "gemini-3.7-flash"
    )
    .strip()
)


GEMINI_LEARNING_TIMEOUT = max(
    5,
    min(
        45,
        int(
            os.getenv(
                "GEMINI_LEARNING_TIMEOUT_SECONDS",
                "20"
            )
        )
    )
)


def _gemini_learning_available():
    """Backward-compatible availability check for the learning scientist.

    Commit 10 accepts either a real Gemini key or a Groq learning key in the
    historical GEMINI_API_KEY slot.  Operational Groq remains independent.
    """
    provider, key = _learning_key_provider()
    return bool(GEMINI_LEARNING_ENABLED and key and provider in {"GEMINI", "GROQ_LEARNING"})


def _gemini_safe_learning_context(
    context
):
    """
    Quita cantidades financieras personales exactas antes
    de enviar un snapshot agregado a Gemini.

    El Learning Scientist necesita estadísticas y porcentajes,
    no balances personales exactos.
    """

    blocked_fragments = (
        "equity",
        "balance",
        "amount",
        "quantity",
        "margin_usdt",
        "investment_usdt",
        "pnl_usdt",
        "portfolio_value",
        "wallet"
    )

    def _clean(
        value
    ):
        if isinstance(
            value,
            dict
        ):
            cleaned = {}

            for key, item in value.items():
                key_text = str(
                    key
                )

                lowered = (
                    key_text
                    .strip()
                    .lower()
                )

                if any(
                    fragment in lowered
                    for fragment
                    in blocked_fragments
                ):
                    continue

                cleaned[
                    key_text
                ] = _clean(
                    item
                )

            return cleaned

        if isinstance(
            value,
            list
        ):
            return [
                _clean(
                    item
                )
                for item
                in value[:100]
            ]

        return value

    return _clean(
        context
        if isinstance(
            context,
            dict
        )
        else {}
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
    usage_type=None,
    context_type=None
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
                .eq(
                    "status",
                    "SUCCESS"
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


            if context_type:

                q = q.eq(
                    "context_type",
                    str(
                        context_type
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


    # ================================================================
    # CUOTAS SEPARADAS
    # ================================================================
    #
    # MANUAL:
    #     por usuario.
    #
    # HOURLY_MARKET_ADVICE:
    #     por usuario.
    #
    # DECISION_CONTROL + GUARDIAN:
    #     presupuesto automático del sistema.
    #
    # LEARNING:
    #     presupuesto independiente.
    #
    # Esto evita que Guardian / Decision Control consuman
    # el presupuesto del consejo horario del usuario.
    # ================================================================

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

        # AUTO total.
        # Sólo para observabilidad / compatibilidad.
        "ad":
            _count_usage(
                day,
                None,
                "AUTO"
            ),

        # Consejo horario PERSONAL.
        "had":
            _count_usage(
                day,
                user_name,
                "AUTO",
                "HOURLY_MARKET_ADVICE"
            ),

        # Controles automáticos Futures.
        "dc":
            _count_usage(
                day,
                None,
                "AUTO",
                "DECISION_CONTROL"
            ),

        # Guardian IA.
        "gu":
            _count_usage(
                day,
                None,
                "AUTO",
                "GUARDIAN"
            ),

        "ld":
            _count_usage(
                day,
                None,
                "LEARNING"
            ),

        # Total general.
        # Se conserva como información de diagnóstico.
        "gd":
            _count_usage(
                day
            )
    }


    if (
        values["dc"] < 0
        or values["gu"] < 0
    ):

        auto_control_used = -1

    else:

        auto_control_used = (
            values["dc"]
            + values["gu"]
        )


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


    storage_values = [
        values["mh"],
        values["md"],
        values["ad"],
        values["had"],
        values["dc"],
        values["gu"],
        values["ld"],
        values["gd"],
    ]


    return {

        "enabled":
            AI_ENABLED,

        "provider":
            AI_PROVIDER,

        "model":
            AI_MODEL,

        # Ventanas móviles:
        # última hora / últimas 24 horas.
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

        # ============================================================
        # CONSEJO HORARIO PERSONAL
        # ============================================================
        "hourly_advice_daily":
            item(
                values["had"],
                LIMIT_HOURLY_ADVICE_DAY
            ),

        # ============================================================
        # CONTROL AUTOMÁTICO DEL SISTEMA
        # ============================================================
        "auto_control_daily":
            item(
                auto_control_used,
                LIMIT_AUTO_CONTROL_DAY
            ),

        # AUTO agregado.
        # Informativo, no mezcla los gates.
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

        # Total agregado para diagnóstico.
        "global_daily":
            item(
                values["gd"],
                LIMIT_GLOBAL_DAY
            ),

        "quota_storage_ok":
            all(
                value >= 0
                for value
                in storage_values
            )
    }

def _quota_allowed(
    user_name,
    usage_type,
    context_type=None
):

    quota = (
        get_ai_quota_status(
            user_name
        )
    )


    # Si Supabase falla, protegemos presupuesto IA.
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


    usage_type = str(
        usage_type
    ).upper()


    context_type = str(
        context_type
        or ""
    ).upper()


    # ================================================================
    # CHAT MANUAL
    # ================================================================

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
                    f"{LIMIT_MANUAL_HOUR} "
                    "preguntas disponibles "
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


    # ================================================================
    # AUTOMÁTICO
    # ================================================================

    elif usage_type == "AUTO":

        # ------------------------------------------------------------
        # CONSEJO HORARIO
        # ------------------------------------------------------------
        #
        # Tiene presupuesto PERSONAL e independiente.
        #
        # Guardian y Decision Control NO pueden agotarlo.
        # ------------------------------------------------------------

        if (
            context_type
            == "HOURLY_MARKET_ADVICE"
        ):

            if (
                quota[
                    "hourly_advice_daily"
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
                        "horarios para este "
                        "usuario."
                    ),
                    quota
                )


        # ------------------------------------------------------------
        # DECISION CONTROL / GUARDIAN
        # ------------------------------------------------------------

        else:

            if (
                quota[
                    "auto_control_daily"
                ][
                    "remaining"
                ]
                <= 0
            ):

                return (
                    False,
                    (
                        "Se alcanzó el límite "
                        "diario de controles "
                        "automáticos de IA."
                    ),
                    quota
                )


    # ================================================================
    # LEARNING
    # ================================================================

    elif usage_type == "LEARNING":

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
    usage=None,
    provider=None,
    model=None
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
            str(
                provider
                or AI_PROVIDER
            ).upper()[:40],

        "model":
            str(
                model
                or AI_MODEL
            )[:120],

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
# COMMIT 36Y
# GEMINI ACTIVITY / WORK REPORT — ZERO EXTRA LLM CALLS
# ============================================================================

def get_gemini_activity_status():
    """
    Estado observable del Learning Scientist Gemini.

    READ-ONLY.

    Esta función NO llama a Gemini.
    Sólo lee ai_usage_events y ai_advisor_observations ya persistidos.

    El cintillo del frontend puede consultarla muchas veces sin gastar
    cuota de Gemini.
    """

    configured_provider, configured_key = _learning_key_provider()
    configured = bool(configured_key)

    result = {
        "mode":
            "WORK_REPORT",

        "provider": configured_provider if configured_provider != "NONE" else None,
        "provider_label": _learning_provider_label(configured_provider),

        "configured":
            configured,

        "enabled":
            bool(
                GEMINI_LEARNING_ENABLED
            ),

        "model":
            (
                (os.getenv("GROQ_LEARNING_MODEL", AI_MODEL).strip() or AI_MODEL)
                if configured_provider == "GROQ_LEARNING"
                else GEMINI_LEARNING_MODEL
            ),

        "state":
            "WAITING_FIRST_RUN",

        "working":
            False,

        "fallback_active":
            False,

        "extra_gemini_calls_for_ticker":
            0,

        # En 36Y Free Tier usamos Opción B:
        # reporte del trabajo real de Gemini.
        "macro_news_enabled":
            False,

        # No existe noticia externa verificable,
        # por lo que TraderMacro permanece intacto.
        "trader_macro_influence":
            False,

        "last_run":
            None,

        # Commit J separates scheduler health from the last successful LLM
        # observation. A stale answer must not make an active watchdog look dead.
        "scheduler": {
            "last_attempt_at": None,
            "status": "UNKNOWN",
            "job_key": None,
        },

        "last_success":
            None,

        "ticker_items":
            [],

        "reason":
            None
    }

    if not configured:
        result[
            "state"
        ] = "NOT_CONFIGURED"

        result[
            "reason"
        ] = "No hay una clave configurada para el científico de aprendizaje."

        result[
            "ticker_items"
        ] = [
            "Científico de aprendizaje · API key no configurada."
        ]

        return result

    if not GEMINI_LEARNING_ENABLED:
        result[
            "state"
        ] = "DISABLED"

        result[
            "reason"
        ] = "GEMINI_LEARNING_ENABLED=false"

        result[
            "ticker_items"
        ] = [
            "Científico de aprendizaje · deshabilitado por configuración."
        ]

        return result

    db = _db()

    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):
        result[
            "state"
        ] = "DB_UNAVAILABLE"

        result[
            "reason"
        ] = (
            "Supabase no disponible "
            "para consultar actividad IA."
        )

        result[
            "ticker_items"
        ] = [
            (
                "Científico de aprendizaje configurado · "
                "estado histórico no disponible."
            )
        ]

        return result

    def _short_text(
        value,
        limit=180
    ):
        text = " ".join(
            str(
                value
                or ""
            ).split()
        )

        if len(
            text
        ) <= limit:
            return text

        return (
            text[
                :max(
                    0,
                    limit - 1
                )
            ].rstrip()
            + "…"
        )

    def _as_dict(
        value
    ):
        if isinstance(
            value,
            dict
        ):
            return value

        if isinstance(
            value,
            str
        ):
            try:
                parsed = json.loads(
                    value
                )

                if isinstance(
                    parsed,
                    dict
                ):
                    return parsed

            except Exception:
                pass

        return {}

    try:

        # ================================================================
        # COMMIT J — SALUD DEL SCHEDULER DEL CIENTÍFICO
        # ================================================================
        # q6_job_runs es la evidencia determinista de que el watchdog está
        # intentando ejecutar el slot, aun si Groq/Gemini falla antes de
        # producir una observación. No realiza llamadas LLM.
        try:
            scheduler_response = db._with_retry(
                lambda: (
                    db.client
                    .table("q6_job_runs")
                    .select("job_key,status,updated_at")
                    .like("job_key", "AI_LEARNING_V2:%")
                    .order("updated_at", desc=True)
                    .limit(1)
                    .execute()
                )
            )
            scheduler_row = (
                dict(scheduler_response.data[0])
                if scheduler_response and scheduler_response.data
                else None
            )
            if scheduler_row:
                result["scheduler"] = {
                    "last_attempt_at": scheduler_row.get("updated_at"),
                    "status": str(scheduler_row.get("status") or "UNKNOWN").upper(),
                    "job_key": scheduler_row.get("job_key"),
                }
        except Exception as scheduler_error:
            result["scheduler"] = {
                "last_attempt_at": None,
                "status": "UNAVAILABLE",
                "job_key": None,
                "error": str(scheduler_error)[:120],
            }

        # ================================================================
        # ÚLTIMO INTENTO GEMINI LEARNING
        # ================================================================

        gemini_usage_response = db._with_retry(
            lambda: (
                db.client
                .table(
                    "ai_usage_events"
                )
                .select(
                    (
                        "provider,model,status,"
                        "usage_type,context_type,"
                        "input_tokens,output_tokens,"
                        "total_tokens,created_at"
                    )
                )
                .eq(
                    "provider",
                    configured_provider
                )
                .eq(
                    "usage_type",
                    "LEARNING"
                )
                .order(
                    "created_at",
                    desc=True
                )
                .limit(
                    1
                )
                .execute()
            )
        )

        gemini_usage = (
            dict(
                gemini_usage_response.data[0]
            )
            if (
                gemini_usage_response
                and gemini_usage_response.data
            )
            else None
        )

        # ================================================================
        # ÚLTIMO LEARNING DE CUALQUIER PROVEEDOR
        # ================================================================
        #
        # Permite saber si Gemini falló y Groq terminó atendiendo
        # el ciclo mediante el fallback.
        # ================================================================

        latest_learning_response = db._with_retry(
            lambda: (
                db.client
                .table(
                    "ai_usage_events"
                )
                .select(
                    (
                        "provider,model,status,"
                        "total_tokens,created_at"
                    )
                )
                .eq(
                    "usage_type",
                    "LEARNING"
                )
                .order(
                    "created_at",
                    desc=True
                )
                .limit(
                    1
                )
                .execute()
            )
        )

        latest_learning_usage = (
            dict(
                latest_learning_response.data[0]
            )
            if (
                latest_learning_response
                and latest_learning_response.data
            )
            else None
        )

        # ================================================================
        # ÚLTIMO TRABAJO REAL PRODUCIDO POR GEMINI
        # ================================================================

        observation_response = db._with_retry(
            lambda: (
                db.client
                .table(
                    "ai_advisor_observations"
                )
                .select(
                    (
                        "provider,model,event_type,"
                        "response_json,created_at"
                    )
                )
                .eq(
                    "provider",
                    configured_provider
                )
                .eq(
                    "context_type",
                    "LEARNING"
                )
                .order(
                    "created_at",
                    desc=True
                )
                .limit(
                    1
                )
                .execute()
            )
        )

        observation = (
            dict(
                observation_response.data[0]
            )
            if (
                observation_response
                and observation_response.data
            )
            else None
        )

        # ================================================================
        # GEMINI CONFIGURADO PERO TODAVÍA SIN EJECUCIÓN
        # ================================================================

        if not gemini_usage:
            result[
                "state"
            ] = "WAITING_FIRST_RUN"

            result[
                "reason"
            ] = (
                "El científico de aprendizaje está configurado pero aún no existe "
                "un evento LEARNING persistido para el proveedor actual."
            )

            if (
                latest_learning_usage
                and str(
                    latest_learning_usage.get(
                        "provider"
                    )
                    or ""
                ).upper()
                == "GROQ"
            ):
                result[
                    "fallback_active"
                ] = True

                result[
                    "ticker_items"
                ] = [
                    (
                        "Científico de aprendizaje configurado · "
                        "el último ciclo fue atendido por el proveedor alternativo."
                    )
                ]

            else:
                result[
                    "ticker_items"
                ] = [
                    (
                        "Científico de aprendizaje configurado · "
                        "esperando el próximo ciclo de aprendizaje."
                    )
                ]

            return result

        usage_status = str(
            gemini_usage.get(
                "status"
            )
            or "UNKNOWN"
        ).upper()

        total_tokens = int(
            gemini_usage.get(
                "total_tokens"
            )
            or 0
        )

        result[
            "last_run"
        ] = {
            "provider":
                configured_provider,

            "model":
                str(
                    gemini_usage.get(
                        "model"
                    )
                    or result.get("model")
                ),

            "status":
                usage_status,

            "created_at":
                gemini_usage.get(
                    "created_at"
                ),

            "input_tokens":
                int(
                    gemini_usage.get(
                        "input_tokens"
                    )
                    or 0
                ),

            "output_tokens":
                int(
                    gemini_usage.get(
                        "output_tokens"
                    )
                    or 0
                ),

            "total_tokens":
                total_tokens
        }

        # ================================================================
        # GEMINI INTENTADO PERO FALLÓ
        # ================================================================

        if usage_status != "SUCCESS":
            result[
                "state"
            ] = "ERROR_FALLBACK"

            result[
                "fallback_active"
            ] = bool(
                latest_learning_usage
                and str(
                    latest_learning_usage.get(
                        "provider"
                    )
                    or ""
                ).upper()
                == "GROQ"
            )

            result[
                "reason"
            ] = (
                "El último intento del científico de aprendizaje no terminó "
                "correctamente; el sistema puede usar un proveedor alternativo."
            )

            result[
                "ticker_items"
            ] = [
                (
                    "Científico de aprendizaje · último intento con error; "
                    "el trading continúa sin depender de la IA."
                )
            ]

            return result

        # ================================================================
        # GEMINI FUNCIONANDO
        # ================================================================

        result[
            "state"
        ] = "WORKING"

        result[
            "working"
        ] = True

        result["last_success"] = dict(result.get("last_run") or {})

        response_json = _as_dict(
            (
                observation
                or {}
            ).get(
                "response_json"
            )
        )

        ticker_items = []

        # ================================================================
        # 1. TITULAR DEL TRABAJO
        # ================================================================

        headline = _short_text(
            response_json.get(
                "headline"
            ),
            170
        )

        if headline:
            ticker_items.append(
                "Aprendizaje IA · "
                + headline
            )

        # ================================================================
        # 2. HIPÓTESIS QUE ESTÁ INVESTIGANDO
        # ================================================================

        hypotheses = response_json.get(
            "learning_hypotheses"
        )

        if isinstance(
            hypotheses,
            list
        ):
            first_hypothesis = next(
                (
                    _short_text(
                        item,
                        175
                    )
                    for item
                    in hypotheses
                    if _short_text(
                        item,
                        175
                    )
                ),
                ""
            )

            if first_hypothesis:
                ticker_items.append(
                    "🔬 Investigación · "
                    + first_hypothesis
                )

        # ================================================================
        # 3. PROPUESTA SHADOW
        # ================================================================

        proposals = response_json.get(
            "strategy_proposals"
        )

        if isinstance(
            proposals,
            list
        ):
            first_proposal = next(
                (
                    item
                    for item
                    in proposals
                    if isinstance(
                        item,
                        dict
                    )
                ),
                None
            )

            if first_proposal:
                proposal_name = _short_text(
                    first_proposal.get(
                        "name"
                    ),
                    70
                )

                proposal_thesis = _short_text(
                    first_proposal.get(
                        "thesis"
                    ),
                    120
                )

                proposal_text = " · ".join(
                    part
                    for part
                    in (
                        proposal_name,
                        proposal_thesis
                    )
                    if part
                )

                if proposal_text:
                    ticker_items.append(
                        "🧪 Shadow proposal · "
                        + proposal_text
                    )

        # ================================================================
        # 4. CONSEJO DE MEJORA
        # ================================================================

        advice_text = _short_text(
            response_json.get(
                "advice"
            ),
            175
        )

        if (
            advice_text
            and len(
                ticker_items
            ) < 3
        ):
            ticker_items.append(
                "📈 Mejora del sistema · "
                + advice_text
            )

        # ================================================================
        # 5. PRUEBA OBJETIVA DE QUE SE EJECUTÓ
        # ================================================================

        created_at = str(
            gemini_usage.get(
                "created_at"
            )
            or ""
        )

        provider_short = (
            "Groq Learning"
            if configured_provider == "GROQ_LEARNING"
            else "Gemini"
        )
        activity_summary = (
            f"✅ {provider_short} activo"
            + (
                f" · {total_tokens} tokens"
                if total_tokens > 0
                else ""
            )
            + (
                (
                    " · "
                    f"{created_at[:16].replace('T', ' ')} UTC"
                )
                if created_at
                else ""
            )
        )

        ticker_items.append(
            activity_summary
        )

        result[
            "ticker_items"
        ] = ticker_items[:4]

        result[
            "reason"
        ] = (
            "El cintillo reutiliza la última respuesta Learning "
            f"persistida; no realiza llamadas adicionales a {provider_short}."
        )

        return result

    except Exception as error:

        logger.warning(
            "Gemini activity status: %s",
            error
        )

        result[
            "state"
        ] = "STATUS_ERROR"

        result[
            "reason"
        ] = str(
            error
        )[:180]

        result[
            "ticker_items"
        ] = [
            (
                "🧠 Gemini Learning configurado · "
                "no se pudo leer su actividad histórica."
            )
        ]

        return result
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

    normalized_context_type = str(
        context_type
        or ""
    ).strip().upper()

    normalized_market = str(
        market
        or ""
    ).strip().upper()

    # ================================================================
    # CONSEJO IA — CADENCIA INTELIGENTE
    # ================================================================
    #
    # SPOT:
    #     máximo una generación nueva cada 2 horas.
    #
    # FUTURES:
    #     si existe una oportunidad/señal activa:
    #         máximo una generación nueva cada 15 minutos.
    #
    #     si no existe oportunidad activa:
    #         máximo una generación nueva cada 60 minutos.
    #
    # Esto protege la cuota gratuita de Groq sin reducir
    # la frecuencia cuando realmente puede existir una operación.
    # ================================================================

    if (
        normalized_context_type
        == "HOURLY_MARKET_ADVICE"
    ):

        safe_context = (
            context
            if isinstance(
                context,
                dict
            )
            else {}
        )

        snapshot = (
            safe_context.get(
                "hourly_market_snapshot"
            )
            or {}
        )

        if not isinstance(
            snapshot,
            dict
        ):
            snapshot = {}

        focus_signal = (
            snapshot.get(
                "focus_signal"
            )
            or {}
        )

        if not isinstance(
            focus_signal,
            dict
        ):
            focus_signal = {}

        focus_action = str(
            focus_signal.get(
                "action"
            )
            or ""
        ).strip().upper()

        try:
            active_signal_count = int(
                snapshot.get(
                    "active_signal_count"
                )
                or 0
            )

        except (
            TypeError,
            ValueError
        ):
            active_signal_count = 0

        futures_actionable = (
            focus_action
            in (
                "LONG",
                "SHORT"
            )
            or active_signal_count > 0
        )

        if normalized_market == "SPOT":

            interval_minutes = 120

        elif normalized_market == "FUTURES":

            interval_minutes = (
                15
                if futures_actionable
                else 60
            )

        else:

            interval_minutes = 60

        now = _now()

        day_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        minutes_today = (
            now.hour * 60
            + now.minute
        )

        bucket_minutes = (
            (
                minutes_today
                // interval_minutes
            )
            * interval_minutes
        )

        bucket_time = (
            day_start
            + timedelta(
                minutes=bucket_minutes
            )
        )

        advice_bucket = (
            bucket_time.strftime(
                "%Y-%m-%dT%H:%MZ"
            )
        )

        raw = json.dumps(
            {
                "context_type":
                    normalized_context_type,

                "market":
                    normalized_market,

                "advice_bucket":
                    advice_bucket,

                "interval_minutes":
                    interval_minutes,

                "futures_actionable":
                    (
                        futures_actionable
                        if normalized_market
                        == "FUTURES"
                        else False
                    )
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":"
            ),
            default=str
        )

    # ================================================================
    # RESTO DE FUNCIONES IA
    # ================================================================
    #
    # Chat, Guardian, Decision Control y Learning continúan usando
    # fingerprint contextual normal.
    # ================================================================

    else:

        raw = json.dumps(
            {
                "context":
                    context,

                "context_type":
                    normalized_context_type,

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
def _groq_runtime_system_prompt():
    """
    Prompt compacto para Groq Runtime.

    Conserva la política y los guardrails importantes,
    pero evita reenviar un prompt enorme en cada Consejo,
    Chat, Guardian o Decision Control.

    Gemini Learning conserva el prompt/contexto amplio.
    """

    return """
Eres el AI Trader Analyst de SmartradingReview.
Responde siempre en español y analiza de forma independiente:
no justifiques una decisión sólo porque el sistema la emitió.

POLÍTICA:
ASERTIVO PERO CAUTO. PRECAVIDO PERO NO TÍMIDO. RENTABLE.
Prioriza expectancy neta positiva, preservación de capital,
calidad riesgo/retorno, drawdown y costes antes que cantidad
de operaciones o Win Rate aislado.

FUTURES:
respeta Liquidity -> Sweep -> MSS -> Displacement -> POI -> Entry.
Comprueba Entry, invalidación, SL, TP, RR, Safety, estructura,
régimen, multitemporalidad, leverage y riesgo monetario.
Si market_intelligence está disponible, actúa como Trader IA de contexto:
interpreta OI, funding, mark/index basis, order book, flujo reciente y
liquidez EN CONJUNTO con el régimen. OI o una pared del libro aislados
no definen dirección; considera crowding, desapalancamiento, absorción y
si el contexto favorece continuación o reversión. Una pared puede desaparecer.
No inventes Entry/SL/TP, no aumentes leverage y no conviertas
NO_OPERAR en LONG/SHORT. Si contradices una señal, explica la evidencia.

SPOT/TGP:
Spot no es Futures. Considera BTC, PAXG y USDT, reservas,
concentración, oportunidad frente a HOLD, coste de rotación,
anti-whipsaw y calidad/frescura del Entry. No recomiendes perseguir
una entrada cuyo recorrido útil ya se consumió.

PERSONALIZACIÓN Y SEGURIDAD:
usa sólo datos presentes en el contexto. Si falta un dato, dilo.
El perfil personal puede reducir riesgo, nunca aumentarlo por encima
del límite técnico. Tu salida es ADVISORY_ONLY y no puede modificar
Safety, niveles, leverage, pesos ni producción.
""".strip()
    
def _system_prompt():

    return """
Eres el AI Trader Analyst de SmartradingReview.

Tu rol NO es repetir ni justificar automáticamente la conclusión
del sistema.

Actúas como un trader profesional independiente, cuantitativo y
discrecional, experto en:

- estructura de mercado;
- liquidez;
- Smart Money;
- Sweep;
- MSS;
- Displacement;
- POI;
- soporte y resistencia;
- RSI;
- ADX / DMI;
- EMAs;
- volumen;
- flujo de dinero;
- Fibonacci;
- análisis multitemporal;
- gestión de riesgo;
- expectancy;
- R;
- drawdown;
- costes;
- Spot;
- Futures perpetual.

============================================================
IDIOMA
============================================================

Responde SIEMPRE en español.

Puedes conservar términos técnicos universales:

LONG
SHORT
Entry
Stop Loss
Take Profit
Safety
Smart Money
Sweep
MSS
Displacement
POI
RR

pero explica su implicación de forma comprensible.

============================================================
POLÍTICA DE SMARTRADINGREVIEW
============================================================

ASERTIVO PERO CAUTO.
PRECAVIDO PERO NO TÍMIDO.
RENTABLE.

El objetivo principal NO es maximizar cantidad de operaciones
ni Win Rate aislado.

Prioridad:

1. expectancy neta positiva;
2. preservación de capital;
3. calidad riesgo/retorno;
4. drawdown;
5. costes;
6. Win Rate;
7. cantidad de operaciones.

============================================================
REGLA ANTI-COMPLACENCIA
============================================================

La recomendación, confidence, Safety, votos o conclusión final
de SmartradingReview NO son evidencia por sí mismos.

Nunca escribas algo equivalente a:

"Estoy de acuerdo porque el sistema recomienda LONG."

Primero debes estudiar los datos técnicos disponibles.

Sólo DESPUÉS debes comparar tu conclusión independiente con
la conclusión del sistema.

Puedes:

- coincidir;
- coincidir con reservas;
- discrepar;
- concluir que no existe ventaja suficiente.

No tienes obligación de coincidir con el Comité.

============================================================
METODOLOGÍA OBLIGATORIA
============================================================

FASE A — ANÁLISIS INDEPENDIENTE

Antes de considerar la conclusión final del sistema, evalúa
todos los datos realmente disponibles.

Cuando existan, considera:

1. régimen de mercado;
2. tendencia multitemporal;
3. estructura;
4. pools de liquidez;
5. Sweep;
6. MSS;
7. Displacement;
8. POI;
9. Entry;
10. invalidación;
11. Stop Loss;
12. Take Profit;
13. RR;
14. Safety y sus componentes;
15. RSI;
16. ADX;
17. DMI;
18. EMAs;
19. volumen;
20. flujo de dinero;
21. Fibonacci;
22. Smart Money;
23. contradicciones entre temporalidades;
24. contradicciones entre indicadores;
25. riesgo agregado;
26. costes cuando estén disponibles;
27. resultados históricos relevantes;
28. ReviewTrader cuando exista muestra suficiente.

No inventes un indicador que no esté presente.

Si falta un dato importante, decláralo como desconocido.

FASE B — TESIS PROPIA

Forma una conclusión propia:

- alcista;
- bajista;
- neutral;
- sin ventaja suficiente.

Determina si el setup parece:

- fuerte;
- aceptable;
- débil;
- contradictorio.

La confianza debe provenir de la calidad y consistencia
de la evidencia recibida.

NO copies automáticamente la confidence del sistema.

FASE C — COMPARACIÓN

Sólo después compara tu tesis con:

- Comité;
- recomendación del sistema;
- Guardian;
- ReviewTrader.

Usa system_alignment para explicar claramente:

- en qué coincides;
- en qué discrepas;
- qué evidencia causa la diferencia.

============================================================
JERARQUÍA SMART MONEY
============================================================

Respeta como prioridad:

Liquidity
-> Sweep
-> MSS
-> Displacement
-> POI
-> Entry

Una señal basada sólo en osciladores no debe superar una
contradicción estructural importante sin evidencia adicional.

============================================================
FUTURES
============================================================

Para Futures:

- prioriza expectancy/R;
- verifica geometría Entry/SL/TP;
- considera Safety;
- considera RR;
- considera leverage y riesgo monetario;
- penaliza contradicciones estructurales;
- no confundas margen con pérdida máxima al SL;
- no inventes funding, fees o slippage.

Nunca:

- conviertas NO_OPERAR en LONG o SHORT;
- inventes Entry;
- inventes SL;
- inventes TP;
- aumentes leverage;
- ignores hard risk caps.

============================================================
SPOT / TGP
============================================================

Spot NO es Futures.

Analiza:

- acumulación BTC;
- protección PAXG;
- liquidez USDT;
- concentración;
- oportunidad de rotación;
- coste de oportunidad;
- riesgo de quedarse sin reservas.

Una VENTA_SPOT no equivale automáticamente a SHORT Futures.
============================================================
PERSONALIZACIÓN OBLIGATORIA
============================================================

Nunca trates a dos usuarios como si fueran iguales.

Si market == SPOT y existe portfolio_percentages:

- considera obligatoriamente BTC_pct;
- considera obligatoriamente PAXG_pct;
- considera obligatoriamente USDT_pct;
- identifica concentración;
- identifica falta o exceso de liquidez;
- evalúa si una rotación aumenta o perjudica el objetivo TGP;
- evita recomendar una operación que deje irresponsablemente
  al usuario sin BTC, PAXG u USDT.

Cuando esos porcentajes estén disponibles, una recomendación
Spot debe mencionar al menos uno de ellos cuando sea relevante.

NO necesitas conocer las cantidades exactas.

Si market == FUTURES y existe personal_risk_profile:

- respeta futures_risk_mode;
- respeta futures_margin_policy;
- considera futures_equity_usdt cuando exista;
- considera futures_max_allocation_pct;
- considera futures_max_loss_pct_equity_per_trade;
- considera futures_preferred_margin_usdt;
- respeta futures_personal_max_leverage.

Nunca recomiendes más leverage o asignación que el máximo
personal configurado.

El perfil personal puede REDUCIR riesgo.
Nunca debe utilizarse para justificar aumentar el riesgo
por encima del límite técnico del sistema.

============================================================
MEJOR OPORTUNIDAD
============================================================

Si el usuario pregunta:

- "¿cuál es la mejor oportunidad?";
- "¿qué operarías?";
- "¿qué señal es mejor?";
- "¿dónde ves más ventaja?";
- o una pregunta equivalente,

NO analices únicamente el símbolo que está visible en pantalla.

Compara todas las señales candidatas disponibles en `signals`.

Debes indicar de forma explícita:

1. símbolo;
2. timeframe;
3. dirección o acción;
4. por qué esa oportunidad supera a las demás;
5. al menos dos métricas o hechos concretos disponibles;
6. riesgo o contradicción principal.

Ejemplos de hechos concretos válidos:

- Safety;
- RR;
- Entry;
- Stop Loss;
- Take Profit;
- confidence;
- estructura;
- votos;
- publication gate;
- exposición del portfolio;
- riesgo personal Futures;
- ReviewTrader.

Si ninguna señal tiene una ventaja convincente:

di claramente:

"Actualmente no encuentro una operación con edge suficiente."

NO inventes una oportunidad solamente porque el usuario
preguntó cuál es la mejor.

============================================================
PROHIBICIÓN DE RESPUESTAS GENÉRICAS
============================================================

No respondas únicamente:

- "gestiona el riesgo";
- "espera confirmación";
- "mantén disciplina";
- "el mercado es volátil";
- "diversifica";
- "usa un Stop Loss".

Una respuesta operativa debe identificar el hecho concreto
que provoca esa recomendación.

Siempre que el contexto lo permita, usa al menos TRES hechos
concretos.

Ejemplo:

"BTC-USDT 1h es actualmente la oportunidad Futures más fuerte:
Safety 81, RR 2.3 y estructura alcista consistente. Sin embargo,
tu leverage personal máximo es 10x, por lo que no considero
apropiado superar ese límite."

Eso es válido.

"BTC parece interesante; gestiona bien tu riesgo."

Eso es inválido.

============================================================
CONSEJO HORARIO
============================================================

Cuando exista hourly_advice_contract:

- analiza el estado ACTUAL;
- busca primero la decisión de mayor impacto;
- usa hechos concretos;
- evita consejos genéricos.

Prioriza:

1. oportunidad concreta;
2. protección concreta;
3. riesgo concreto;
4. exposición agregada;
5. concentración;
6. rotación;
7. NO actuar cuando realmente no exista edge.

why debe contener principalmente EVIDENCIA TÉCNICA,
no la opinión del sistema.

risks debe contener contradicciones o riesgos concretos.

what_to_watch debe indicar qué condición observable podría
cambiar la tesis.

============================================================
Q7 STRATEGY LAB — SHADOW ONLY
============================================================

Si el contexto contiene q7_strategy_lab:

- trátalo como evidencia experimental de TIMING;
- ALIGNED no significa que la estrategia esté validada;
- CONFLICT puede señalar riesgo de timing, pero no invalida
  por sí solo la estructura principal;
- nunca uses Q7 para bajar Safety;
- nunca conviertas Q7 en un voto adicional del comité;
- nunca cambies Entry, SL, TP, leverage o publication por Q7;
- distingue observaciones de resultados resueltos;
- no declares edge con una muestra insuficiente.

Q7 puede contener:

- RSI adaptativo por timeframe;
- VWAP real de reversión en rango;
- Breakout + Retest Acceptance.

Una futura promoción Q7 requiere:

muestra suficiente
→ Expectancy favorable
→ costes
→ walk-forward
→ OOS
→ revisión humana.

Q7 nunca tiene promoción automática positiva.


============================================================
APRENDIZAJE Y DISEÑO DE ESTRATEGIAS
============================================================

learning_hypotheses sólo debe contener hipótesis comprobables.

Ejemplo válido:

"Evaluar si LONG BTC 1h con MSS + displacement y ADX alto
presenta mayor expectancy que la cohorte general."

Ejemplo inválido:

"Usar mejor los indicadores."

No afirmes que un patrón funciona si la muestra no lo demuestra.

Cuando el contexto corresponda a LEARNING puedes además
proponer nuevas estrategias de investigación.

Una estrategia propuesta:

- NO entra automáticamente en producción;
- NO modifica Safety;
- NO modifica Entry/SL/TP actuales;
- NO modifica pesos;
- NO modifica leverage;
- debe comenzar como SHADOW_PROPOSAL.

Una estrategia propuesta debe indicar:

1. mercado: SPOT o FUTURES;
2. tesis;
3. régimen donde debería funcionar;
4. setup técnico;
5. condiciones de entrada observables;
6. invalidación;
7. lógica de target;
8. métrica principal de éxito;
9. cantidad mínima de muestras;
10. por qué merece ser probada;
11. research_filters: filtros ESTRUCTURADOS que Research Federation pueda medir.

research_filters sólo puede usar estas claves cuando exista evidencia para ellas:
market_family, symbol, timeframe, direction, regime, micro_alignment, orderbook_imbalance_band, recent_buy_share_band,
oi_change_band, funding_band, basis_band, liquidity_band,
sl_quality_band, tp_quality_band, defensibility_band, reachability_band,
has_order_block, has_sweep, has_pullback, component.

No inventes un filtro si no aparece en el contexto. Una propuesta sin filtros
medibles puede describirse, pero permanecerá no testeable y no será promovida.

Para FUTURES prioriza como fuentes de mejora:

- calidad Entry SMC;
- Liquidity -> Sweep -> MSS -> Displacement -> POI;
- régimen + posicionamiento (OI/funding/basis) + order flow/liquidez cuando exista;
- distinguir continuación de tendencia vs reversión en balance;
- calidad del Stop Loss;
- calidad/probabilidad del Take Profit;
- régimen;
- temporalidad;
- expectancy R;
- costes.

Para SPOT prioriza:

- acumulación BTC;
- protección PAXG;
- liquidez USDT;
- edge de rotación;
- coste de oportunidad;
- crecimiento/protección del portafolio.

Una nueva estrategia NO debe ser simplemente:

"bajar Safety para tener más señales".

Debe intentar generar setups de MAYOR CALIDAD que alcancen
Safety por mérito propio.

Si no existe evidencia suficiente para proponer una estrategia,
strategy_proposals debe ser [].

Distingue siempre:

- observado;
- estimado;
- hipótesis;
- desconocido.
============================================================
GUARDRAILS
============================================================

Tu autoridad sigue siendo ADVISORY_ONLY.

No puedes modificar directamente:

- decisiones;
- Safety;
- Entry;
- Stop Loss;
- Take Profit;
- leverage;
- pesos;
- Guardian.

Puedes cuestionarlos y explicar por qué.

No muestres razonamiento interno paso a paso.

Entrega únicamente:

- conclusión;
- evidencia concreta;
- riesgos;
- contradicciones;
- hipótesis comprobables;
- comparación objetiva con el sistema.

Tu misión es ayudar a que SmartradingReview sea más rentable
y más inteligente, no hacerlo más complaciente.
""".strip()

# ============================================================================
# GROQ
# ============================================================================
# ============================================================================
# COMMIT 36R-FIX4
# NORMALIZACIÓN LOCAL DE RESPUESTAS IA
# ============================================================================

_AI_ALLOWED_VERDICTS = {
    "SUPPORT",
    "CAUTION",
    "DISAGREE",
    "NO_EDGE",
    "INFO"
}


_AI_VERDICT_ALIASES = {

    "APOYA":
        "SUPPORT",

    "APOYAR":
        "SUPPORT",

    "PRECAUCIÓN":
        "CAUTION",

    "PRECAUCION":
        "CAUTION",

    "CAUTELA":
        "CAUTION",

    "DISCREPA":
        "DISAGREE",

    "DESACUERDO":
        "DISAGREE",

    "SIN VENTAJA":
        "NO_EDGE",

    "SIN EDGE":
        "NO_EDGE",

    "NO HAY VENTAJA":
        "NO_EDGE",

    "INFORMACIÓN":
        "INFO",

    "INFORMACION":
        "INFO"
}


def _ai_clean_text(
    value,
    default="",
    max_len=2400
):

    if value is None:

        return default


    if isinstance(
        value,
        (
            dict,
            list,
            tuple
        )
    ):

        try:

            value = json.dumps(
                value,
                ensure_ascii=False
            )

        except Exception:

            value = str(
                value
            )


    text = str(
        value
    ).strip()


    if not text:

        return default


    return text[
        :max_len
    ]


def _ai_clean_list(
    value,
    max_items=5
):

    if value is None:

        return []


    if isinstance(
        value,
        str
    ):

        value = [
            value
        ]


    if not isinstance(
        value,
        (
            list,
            tuple
        )
    ):

        return []


    cleaned = []


    for item in value:

        text = _ai_clean_text(
            item,
            "",
            800
        )


        if not text:

            continue


        cleaned.append(
            text
        )


        if (
            len(
                cleaned
            )
            >= max_items
        ):

            break


    return cleaned

_RESEARCH_PROPOSAL_FILTERS = {
    "market_family",
    "symbol",
    "timeframe",
    "direction",
    "regime",
    "micro_alignment",
    "sl_quality_band",
    "tp_quality_band",
    "defensibility_band",
    "reachability_band",
    "has_order_block",
    "has_sweep",
    "has_pullback",
    "orderbook_imbalance_band",
    "recent_buy_share_band",
    "oi_change_band",
    "funding_band",
    "basis_band",
    "liquidity_band",
    "component",
}


def _normalize_research_filters(value, market="FUTURES"):
    """Normaliza el contrato que Research Federation puede medir.

    No interpreta lenguaje libre.  Sólo acepta dimensiones que ya existen en
    los snapshots V2; por eso una propuesta IA puede convertirse en hipótesis
    medible sin darle autoridad operativa al LLM.
    """
    raw = value if isinstance(value, dict) else {}
    out = {}

    market_family = str(raw.get("market_family") or "").strip().upper()
    if not market_family and str(market or "").upper() == "FUTURES":
        market_family = "CRYPTO_FUTURES"
    if market_family in {"CRYPTO_FUTURES", "CRYPTO_SPOT", "PAXG_USDT", "PAXG_BTC"}:
        out["market_family"] = market_family

    symbol = str(raw.get("symbol") or "").strip().upper().replace("/", "-")
    if symbol and symbol not in {"ALL", "ANY", "TODOS"}:
        out["symbol"] = symbol[:40]

    timeframe = str(raw.get("timeframe") or "").strip().upper()
    if timeframe in {"5M", "15M", "30M", "1H", "2H", "4H", "12H", "1D", "1W"}:
        out["timeframe"] = timeframe

    direction = str(raw.get("direction") or "").strip().upper()
    if direction in {"LONG", "SHORT"}:
        out["direction"] = direction

    regime = str(raw.get("regime") or "").strip().upper()
    if regime in {"BALANCE", "TREND_UP", "TREND_DOWN", "TRANSITION", "VOLATILITY_SHOCK"}:
        out["regime"] = regime

    micro = str(raw.get("micro_alignment") or "").strip().upper()
    if micro in {"ALIGNED", "NEUTRAL", "CONFLICT"}:
        out["micro_alignment"] = micro

    for key in (
        "sl_quality_band",
        "tp_quality_band",
        "defensibility_band",
        "reachability_band",
    ):
        band = str(raw.get(key) or "").strip().upper()
        if band in {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}:
            out[key] = band

    for key in ("has_order_block", "has_sweep", "has_pullback"):
        flag = str(raw.get(key) or "").strip().upper()
        if flag in {"YES", "NO"}:
            out[key] = flag

    enum_filters = {
        "orderbook_imbalance_band": {"SELL_HEAVY", "BALANCED", "BUY_HEAVY"},
        "recent_buy_share_band": {"SELL_HEAVY", "BALANCED", "BUY_HEAVY"},
        "oi_change_band": {"DELEVERAGING", "STABLE", "BUILDING"},
        "funding_band": {"SHORT_CROWDED", "NEUTRAL", "LONG_CROWDED"},
        "basis_band": {"BACKWARDATION", "NEUTRAL", "CONTANGO"},
        "liquidity_band": {"LOW", "NORMAL", "HIGH"},
    }
    for key, allowed in enum_filters.items():
        value = str(raw.get(key) or "").strip().upper()
        if value in allowed:
            out[key] = value

    component = str(raw.get("component") or "").strip().upper()
    if component:
        # El prefijo forma parte del token real persistido (STRATEGY:, RSI_...).
        out["component"] = component[:180]

    return {k: out[k] for k in _RESEARCH_PROPOSAL_FILTERS if k in out}


def _normalize_strategy_proposals(
    value
):
    """
    Convierte propuestas de la IA en hipótesis Shadow
    estructuradas.

    IMPORTANTE:
    SHADOW_PROPOSAL NO significa estrategia aprobada.
    """

    if not isinstance(
        value,
        list
    ):
        return []

    proposals = []

    for item in value[:3]:
        if not isinstance(
            item,
            dict
        ):
            continue

        market = str(
            item.get(
                "market"
            )
            or "FUTURES"
        ).strip().upper()

        if market not in (
            "SPOT",
            "FUTURES",
            "BOTH"
        ):
            market = "FUTURES"

        try:
            min_samples = int(
                item.get(
                    "min_samples"
                )
                or 25
            )

        except (
            TypeError,
            ValueError
        ):
            min_samples = 25

        min_samples = max(
            10,
            min(
                500,
                min_samples
            )
        )

        proposal = {
            "name":
                _ai_clean_text(
                    item.get(
                        "name"
                    ),
                    "Propuesta IA",
                    160
                ),

            "market":
                market,

            "thesis":
                _ai_clean_text(
                    item.get(
                        "thesis"
                    ),
                    "",
                    1200
                ),

            "regime":
                _ai_clean_text(
                    item.get(
                        "regime"
                    ),
                    "ANY",
                    240
                ),

            "setup":
                _ai_clean_text(
                    item.get(
                        "setup"
                    ),
                    "",
                    1600
                ),

            "entry_conditions":
                _ai_clean_list(
                    item.get(
                        "entry_conditions"
                    ),
                    6
                ),

            "invalidation":
                _ai_clean_text(
                    item.get(
                        "invalidation"
                    ),
                    "",
                    800
                ),

            "target_logic":
                _ai_clean_text(
                    item.get(
                        "target_logic"
                    ),
                    "",
                    800
                ),

            "success_metric":
                _ai_clean_text(
                    item.get(
                        "success_metric"
                    ),
                    "net_expectancy_R",
                    240
                ),

            "min_samples":
                min_samples,

            "why_test":
                _ai_clean_text(
                    item.get(
                        "why_test"
                    ),
                    "",
                    1200
                ),

            "status":
                "SHADOW_PROPOSAL"
        }

        research_filters = _normalize_research_filters(
            item.get("research_filters"),
            market=market
        )
        proposal["research_filters"] = research_filters
        # Testable significa únicamente que existe al menos una condición
        # además de la familia de mercado. No implica edge ni aprobación.
        discriminants = [
            key for key in research_filters
            if key != "market_family"
        ]
        proposal["runtime_testable"] = bool(discriminants)
        proposal_seed = json.dumps(
            {
                "market": market,
                "name": proposal["name"],
                "filters": research_filters,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        proposal["proposal_id"] = (
            "AI_" + hashlib.sha256(proposal_seed.encode("utf-8")).hexdigest()[:16]
        )

        if (
            proposal[
                "thesis"
            ]
            and proposal[
                "entry_conditions"
            ]
        ):
            proposals.append(
                proposal
            )

    return proposals
    
def _normalize_ai_advice(
    payload
):
    """
    Convierte cualquier JSON válido de Groq
    al contrato interno estable de SmartradingReview.

    IMPORTANTE:
    36S nunca recibe directamente el JSON libre
    producido por el modelo.
    """

    if not isinstance(
        payload,
        dict
    ):

        payload = {}


    raw_verdict = str(

        payload.get(
            "verdict",
            "INFO"
        )

        or "INFO"

    ).strip().upper()


    verdict = (
        _AI_VERDICT_ALIASES.get(
            raw_verdict,
            raw_verdict
        )
    )


    if (
        verdict
        not in _AI_ALLOWED_VERDICTS
    ):

        verdict = "INFO"


    try:

        confidence = int(
            round(
                float(
                    payload.get(
                        "confidence",
                        0
                    )
                    or 0
                )
            )
        )

    except (
        TypeError,
        ValueError
    ):

        confidence = 0


    confidence = max(
        0,
        min(
            100,
            confidence
        )
    )


    headline = _ai_clean_text(

        payload.get(
            "headline"
        ),

        "Evaluación del sistema",

        300
    )


    advice = _ai_clean_text(

        payload.get(
            "advice"
        ),

        (
            "No existe información suficiente "
            "para emitir una recomendación "
            "más específica."
        ),

        3000
    )


    normalized = {

        "verdict":
            verdict,

        "confidence":
            confidence,

        "headline":
            headline,

        "advice":
            advice,

        "why":
            _ai_clean_list(
                payload.get(
                    "why"
                ),
                5
            ),

        "risks":
            _ai_clean_list(
                payload.get(
                    "risks"
                ),
                5
            ),

        "what_to_watch":
            _ai_clean_list(
                payload.get(
                    "what_to_watch"
                ),
                5
            ),

        "learning_hypotheses":
            _ai_clean_list(
                payload.get(
                    "learning_hypotheses"
                ),
                5
            ),
        "strategy_proposals":
            _normalize_strategy_proposals(
                payload.get(
                    "strategy_proposals"
                )
            ),
        "system_alignment":
            _ai_clean_text(
                payload.get(
                    "system_alignment"
                ),
                "",
                1200
            ),

        "personal_risk_note":
            _ai_clean_text(
                payload.get(
                    "personal_risk_note"
                ),
                "",
                1200
            ),

        "portfolio_note":
            _ai_clean_text(
                payload.get(
                    "portfolio_note"
                ),
                "",
                1200
            ),

        # ================================================================
        # GUARDRAILS
        # ================================================================

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
    }


    return normalized

def _call_groq(
    context,
    question=None,
    context_type=None,
    api_key_override=None,
    model_override=None
):

    key = str(api_key_override or os.getenv("GROQ_API_KEY", "")).strip()


    if not key:

        raise RuntimeError(
            (
                "No existe una API key Groq válida para esta ruta."
            )
        )
    backoff_remaining = (
        _groq_backoff_remaining_seconds()
    )

    if backoff_remaining > 0:
        raise RuntimeError(
            (
                "Groq está temporalmente en pausa "
                "por límite de cuota. "
                f"Reintento disponible en aproximadamente "
                f"{max(1, backoff_remaining // 60)} min. "
                "No se realizó una nueva llamada externa."
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
        > GROQ_MAX_CONTEXT
    ):

        context_text = (
            context_text[
                :GROQ_MAX_CONTEXT
            ]
            + "\n...[CONTEXTO RECORTADO]"
        )


    # ========================================================================
    # CONTRATO JSON
    # ========================================================================
    #
    # Ya NO usamos JSON Schema del proveedor.
    #
    # Groq garantiza JSON sintácticamente válido.
    # SmartradingReview normaliza y valida localmente.
    # ========================================================================

    output_contract = """
FORMATO TÉCNICO OBLIGATORIO:

Responde EXCLUSIVAMENTE con un objeto JSON válido.
No escribas markdown.
No escribas ```json.
No escribas texto antes ni después del JSON.

Usa esta estructura:

{
  "verdict": "SUPPORT",
  "confidence": 0,
  "headline": "",
  "advice": "",
  "why": [],
  "risks": [],
  "what_to_watch": [],
  "learning_hypotheses": [],
  "strategy_proposals": [],
  "system_alignment": "",
  "personal_risk_note": "",
  "portfolio_note": ""
}

REGLAS:

verdict debe representar una de estas ideas:
SUPPORT, CAUTION, DISAGREE, NO_EDGE o INFO.

confidence debe ser un número de 0 a 100.

why, risks, what_to_watch y learning_hypotheses
deben ser listas de textos.

strategy_proposals debe ser [] salvo que el contexto
corresponda específicamente a LEARNING.

Cuando incluyas strategy_proposals, cada propuesta debe contener además
research_filters con únicamente dimensiones medibles del contexto:
market_family, symbol, timeframe, direction, regime, micro_alignment,
sl_quality_band, tp_quality_band, defensibility_band, reachability_band,
has_order_block, has_sweep, has_pullback o component.

Todos los textos visibles deben estar en español.

Nunca incluyas datos que no estén presentes
en el contexto recibido.
""".strip()


    prompt = (
        "CONTEXTO DEL SISTEMA:\n"
        f"{context_text}"
        "\n\n"
        f"{output_contract}"
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
                (model_override or AI_MODEL),

            "messages": [

                {
                    "role":
                        "system",

                    "content":
                        (
                            _system_prompt()
                            if str(
                                context_type
                                or ""
                            ).strip().upper()
                            == "LEARNING"
                            else _groq_runtime_system_prompt()
                        )
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

            # ============================================================
            # FIX 36R
            #
            # JSON válido sin JSON-Schema remoto rígido.
            #
            # La validación real ocurre después
            # dentro de SmartradingReview.
            # ============================================================

            "response_format": {
                "type":
                    "json_object"
            }
        },

        timeout=
            AI_TIMEOUT
    )


    if (
        response.status_code
        == 429
    ):

        retry_seconds = (
            _activate_groq_backoff(
                response
            )
        )

        raise RuntimeError(
            (
                "Groq alcanzó temporalmente su "
                "límite de cuota. "
                "El sistema activó una pausa automática "
                f"de aproximadamente "
                f"{max(1, retry_seconds // 60)} min "
                "para evitar reintentos innecesarios."
            )
        )

    if (
        response.status_code
        != 200
    ):

        raise RuntimeError(
            (
                f"Groq HTTP "
                f"{response.status_code}: "
                f"{response.text[:200]}"
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


    content = (

        choices[0]
        .get(
            "message",
            {}
        )
        .get(
            "content"
        )

        or ""
    )


    try:

        generated = json.loads(
            content
        )


    except Exception as json_error:

        raise RuntimeError(
            (
                "Groq devolvió JSON "
                "no interpretable: "
                f"{str(json_error)[:120]}"
            )
        )


    advice = (
        _normalize_ai_advice(
            generated
        )
    )


    return (
        advice,
        raw.get(
            "usage"
        )
        or {}
    )
def _call_groq_learning_slot(context, question=None):
    """Use a Groq key stored in the legacy GEMINI_API_KEY learning slot.

    This is intentionally separate from GROQ_API_KEY so a secondary Groq key
    can be dedicated to daily learning without changing operational chat/advice.
    """
    provider, key = _learning_key_provider()
    if provider != "GROQ_LEARNING" or not key:
        raise RuntimeError("La clave del científico de aprendizaje no es una clave Groq.")
    model = os.getenv("GROQ_LEARNING_MODEL", AI_MODEL).strip() or AI_MODEL
    return _call_groq(
        context,
        question=question,
        context_type="LEARNING",
        api_key_override=key,
        model_override=model,
    )


def _call_gemini_learning(
    context,
    question=None
):
    """
    Gemini actúa exclusivamente como Learning Scientist.

    No publica señales.
    No modifica trading.
    No recibe autoridad 36S.
    """

    key = (
        os.getenv(
            "GEMINI_API_KEY",
            ""
        )
        .strip()
    )

    if not key:
        raise RuntimeError(
            (
                "GEMINI_API_KEY no está "
                "configurada en Render."
            )
        )

    safe_context = (
        _gemini_safe_learning_context(
            context
        )
    )

    context_text = json.dumps(
        safe_context,
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

    learning_instruction = """
Actúas como AI Learning Scientist de SmartradingReview.

Tu función es investigar cómo mejorar la CALIDAD,
EXPECTANCY y RENTABILIDAD del sistema.

NO modificas producción.

Analiza críticamente:

- ReviewTrader;
- economía;
- outcomes;
- Guardian Learning;
- Futures Shadow;
- Safety;
- Entry SMC;
- Stop Loss;
- Take Profit;
- Risk/Reward;
- regímenes;
- temporalidades;
- errores recurrentes;
- oportunidades perdidas cuando existan.

No intentes aumentar operaciones simplemente bajando filtros.

Si existe execution_forensics_v2 en el contexto:

- estudia MFE y MAE como diagnóstico retrospectivo, no como certeza futura;
- distingue Entry no alcanzado de Entry alcanzado pero no defendible;
- identifica STOPPED_WITHOUT_PROGRESS frente a stops después de progreso;
- presta atención a stop_was_possibly_tight y a TP alcanzado después del SL;
- formula hipótesis para mejorar Entry/SL/TP sin mover niveles en producción.

Si existe strategy_attribution_v2 en el contexto:

- atribuye resultados al trader + estrategia + dirección que realmente votó;
- separa SUPPORT, OPPOSE y NEUTRAL;
- nunca acredites un TP LONG a una estrategia que votó SHORT;
- usa expectancy R, muestra y Entry Activation; no uses WR aislado;
- trata toda conclusión como evidencia diagnóstica hasta validación posterior.

Si existe q7_strategy_lab en el contexto:

- estudia RSI adaptativo, VWAP de reversión y Breakout-Retest
  exclusivamente como experimentos SHADOW;
- compara Oficial y Shadow por separado;
- compara ALIGNED, NEUTRAL y CONFLICT contra el CONTROL;
- compara perfiles FAST, BALANCED y STRUCTURAL por timeframe;
- prioriza Entry Activation, Expectancy R, Profit Factor y PnL;
- no uses Win Rate aislado como criterio de promoción;
- no declares edge con muestra insuficiente;
- no propongas bajar Safety para favorecer Q7;
- una evidencia positiva sólo puede generar revisión humana;
- nunca promociones automáticamente una estrategia Q7.

Si existe edge_discovery_v1 en el contexto:

- úsalo como mapa de hipótesis falsables, nunca como autoridad operativa;
- compara expectancy de Discovery y Validation por separado;
- exige que una mejora sobreviva fuera de muestra antes de llamarla prometedora;
- presta especial atención a diferencias por régimen, acción y contexto;
- una hipótesis RESEARCH_PRIORITY sigue siendo investigación, no una señal;
- una hipótesis LOW_PRIORITY_RESEARCH puede descartarse de prioridad, pero no reescribas historia;
- usa MFE/MAE y Entry Defensibility para explicar por qué una combinación mejora o empeora;
- nunca aumentes leverage ni bajes Safety por una hipótesis de este laboratorio.

Si existe research_federation_v13 en el contexto:

- úsalo como evidencia externa Research-only;
- distingue Discovery, Holdout temporal y Shadow live;
- NO interpretes PF degenerado ni Val.N pequeño como edge real;
- prioriza hipótesis que sobrevivan Holdout, walk-forward, costes y varios activos;
- usa las temporalidades estratégicas de Spot (4H/12H/1D/1W) sin mezclarlas con scalping;
- si un candidato está SHADOW_READY, sólo significa que merece prueba live Shadow;
- si está REJECTED_OOS, úsalo para evitar repetir esa hipótesis.

Si existe learning_integrity_v1 en el contexto:

- verifica que cada conclusión declare su scope de cohorte;
- no exijas que el PDF de aprendizaje y el dashboard tengan el mismo N si estudian scopes distintos;
- si Analytics y Governance declaran el mismo scope pero sus fingerprints no coinciden, trata la evidencia como stale/incompleta;
- nunca recomiendes recalibrar desde una cohorte truncada.

Si existe trader_intelligence_v1 en el contexto:

- estudia a cada trader por MERCADO, TEMPORALIDAD, DIRECCIÓN y RÉGIMEN;
- distingue SUPPORT de OPPOSE: un buen veto puede aportar aunque no "gane" la operación;
- usa judgement_expectancy_r y calibración de confianza, no WR aislado;
- detecta especialización real y también redundancia entre traders;
- no propongas pesos dinámicos todavía: Commit 10 es diagnóstico;
- formula hipótesis de especialización que luego deban pasar validación temporal.

Busca qué características hacen que una señal SEA MEJOR.

Debes generar hipótesis falsables.

Cuando la evidencia lo justifique puedes proponer como máximo
3 estrategias nuevas SHADOW_PROPOSAL.

Una propuesta NO significa que funciona.

Debe pasar posteriormente por:

SHADOW
-> muestra suficiente
-> expectancy
-> costes
-> walk-forward
-> OOS
-> promoción o descarte.

Nunca inventes:

- resultados;
- fees;
- slippage;
- funding;
- muestras;
- métricas.

Si los datos son insuficientes, dilo claramente.
""".strip()

    output_contract = """
Responde EXCLUSIVAMENTE con un objeto JSON válido.

No escribas markdown.
No escribas texto antes ni después del JSON.

Usa exactamente esta estructura:

{
  "verdict": "INFO",
  "confidence": 0,
  "headline": "",
  "advice": "",
  "why": [],
  "risks": [],
  "what_to_watch": [],
  "learning_hypotheses": [],
  "strategy_proposals": [
    {
      "name": "",
      "market": "FUTURES",
      "thesis": "",
      "setup": "",
      "entry_conditions": [],
      "invalidation": "",
      "target_logic": "",
      "regime": "",
      "success_metric": "net_expectancy_R",
      "min_samples": 25,
      "why_test": "",
      "research_filters": {
        "market_family": "CRYPTO_FUTURES",
        "timeframe": "30M",
        "direction": "SHORT",
        "regime": "TREND_DOWN"
      }
    }
  ],
  "system_alignment": "",
  "personal_risk_note": "",
  "portfolio_note": ""
}

REGLAS:

strategy_proposals puede ser [].

Máximo 3 propuestas.

market sólo puede ser:

SPOT
FUTURES
BOTH

Cada estrategia debe ser comprobable.

El criterio principal de éxito debe ser expectancy neta
y preservación de capital, no Win Rate aislado.
""".strip()

    prompt = (
        "CONTEXTO DE APRENDIZAJE:\n"
        f"{context_text}"
        "\n\n"
        f"{output_contract}"
    )

    if question:
        prompt += (
            "\n\nPREGUNTA:\n"
            + str(
                question
            ).strip()[:800]
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        f"{GEMINI_LEARNING_MODEL}:generateContent"
    )

    response = requests.post(
        url,
        headers={
            "x-goog-api-key":
                key,

            "Content-Type":
                "application/json"
        },
        json={
            "systemInstruction": {
                "parts": [
                    {
                        "text":
                            (
                                _system_prompt()
                                + "\n\n"
                                + learning_instruction
                            )
                    }
                ]
            },

            "contents": [
                {
                    "role":
                        "user",

                    "parts": [
                        {
                            "text":
                                prompt
                        }
                    ]
                }
            ],

            "generationConfig": {
                "maxOutputTokens":
                    1800,

                "responseMimeType":
                    "application/json"
            }
        },
        timeout=
            GEMINI_LEARNING_TIMEOUT
    )

    if (
        response.status_code
        != 200
    ):
        raise RuntimeError(
            (
                f"Gemini HTTP "
                f"{response.status_code}: "
                f"{response.text[:240]}"
            )
        )

    raw = response.json()

    candidates = (
        raw.get(
            "candidates"
        )
        or []
    )

    if not candidates:
        raise RuntimeError(
            "Gemini no devolvió candidatos."
        )

    parts = (
        candidates[0]
        .get(
            "content",
            {}
        )
        .get(
            "parts",
            []
        )
        or []
    )

    content = "".join(
        str(
            part.get(
                "text",
                ""
            )
            or ""
        )
        for part in parts
        if isinstance(
            part,
            dict
        )
    ).strip()

    if not content:
        raise RuntimeError(
            "Gemini no devolvió texto."
        )

    try:
        generated = json.loads(
            content
        )

    except Exception as json_error:
        raise RuntimeError(
            (
                "Gemini devolvió JSON "
                "no interpretable: "
                f"{str(json_error)[:120]}"
            )
        )

    advice = (
        _normalize_ai_advice(
            generated
        )
    )

    usage_raw = (
        raw.get(
            "usageMetadata"
        )
        or {}
    )

    usage = {
        "prompt_tokens":
            int(
                usage_raw.get(
                    "promptTokenCount",
                    0
                )
                or 0
            ),

        "completion_tokens":
            int(
                usage_raw.get(
                    "candidatesTokenCount",
                    0
                )
                or 0
            ),

        "total_tokens":
            int(
                usage_raw.get(
                    "totalTokenCount",
                    0
                )
                or 0
            )
    }

    return (
        advice,
        usage
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
    question=None,
    provider=None,
    model=None
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
            str(
                provider
                or AI_PROVIDER
            ).upper()[:40],

        "model":
            str(
                model
                or AI_MODEL
            )[:120],

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
# HOTFIX 14.6 — RESPALDO LOCAL 24/7
# ============================================================================

def _local_operational_fallback(context, market, question=None, reason=''):
    """Deterministic fail-open summary when the external LLM is rate-limited.

    It never invents a trade and never changes production. The purpose is to
    keep Consejo/Asistente useful 24/7 while being explicit that the LLM is
    temporarily unavailable.
    """
    context = context if isinstance(context, dict) else {}
    market = str(market or 'SPOT').upper()
    selected = context.get('selected_signal') or {}
    signals = context.get('signals') or []
    if not isinstance(selected, dict):
        selected = {}
    if not selected and isinstance(signals, list) and signals and isinstance(signals[0], dict):
        selected = signals[0]

    why = []
    risks = []
    watch = []
    advice_parts = [
        'El proveedor LLM está temporalmente limitado; se muestra un resumen local basado sólo en datos del sistema.'
    ]

    if selected:
        symbol = str(selected.get('symbol') or selected.get('pair') or '').upper()
        tf = str(selected.get('timeframe') or '')
        action = str(selected.get('action') or selected.get('decision') or '').upper()
        confidence = selected.get('confidence')
        if symbol or action:
            line = 'Señal destacada'
            if symbol: line += f' {symbol}'
            if tf: line += f' {tf}'
            if action: line += f' · {action}'
            if confidence is not None:
                try: line += f' · confianza {float(confidence):.0f}%'
                except Exception: pass
            why.append(line)
        for label, key in (('Entry','entry'), ('SL','stop_loss'), ('TP','take_profit')):
            value = selected.get(key)
            if value is not None:
                try: watch.append(f'{label}: {float(value):g}')
                except Exception: pass

    macro = context.get('macro_context') or context.get('macro') or {}
    if isinstance(macro, dict):
        risk = str(macro.get('risk_level') or '').upper()
        posture = str(macro.get('futures_posture') or '').upper()
        if risk:
            why.append(f'Contexto macro: {risk}')
        if posture and posture != 'NORMAL':
            risks.append(f'Postura macro Futures: {posture}')

    saved = context.get('saved_kpis') or {}
    if isinstance(saved, dict):
        open_count = saved.get('active') or saved.get('open') or context.get('open_saved_count')
        if open_count:
            why.append(f'Posiciones/señales guardadas activas: {open_count}')

    if market == 'FUTURES':
        risks.append('Mantener el riesgo definido por Entry–SL y respetar Guardian/Publication Gate.')
        advice_parts.append('No se altera LONG/SHORT, Entry, SL, TP ni leverage en este modo de respaldo.')
    else:
        risks.append('Mantener reservas y evitar rotaciones por una sola lectura de corto plazo.')
        advice_parts.append('Guardian TGP conserva prioridad sobre cualquier comentario del asistente.')

    if question:
        advice_parts.append('Para preguntas interpretativas complejas, reintenta cuando el proveedor externo recupere cuota.')

    payload = _normalize_ai_advice({
        'verdict': 'INFO',
        'confidence': 0,
        'headline': 'Modo local de respaldo',
        'advice': ' '.join(advice_parts),
        'why': why[:5],
        'risks': risks[:5],
        'what_to_watch': watch[:5],
        'learning_hypotheses': [],
        'strategy_proposals': [],
        'system_alignment': 'Fail-open: trading y gobernanza siguen funcionando sin depender del LLM.'
    })
    payload['provider'] = 'LOCAL_RULES'
    payload['degraded_mode'] = True
    payload['provider_reason'] = str(reason or '')[:220]
    return payload


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





    usage_type = str(
        usage_type
    ).upper()


    context_type = str(
        context_type
    ).upper()


    market = str(
        market
    ).upper()
    # ================================================================
    # ROUTER MULTI-PROVIDER 36S.2C
    # ================================================================

    selected_provider, selected_model = (
        _resolve_ai_route(
            usage_type,
            context_type
        )
    )

    if selected_provider not in (
        "GROQ",
        "GEMINI",
        "GROQ_LEARNING"
    ):
        return {
            "success":
                False,

            "reason":
                (
                    "Proveedor no soportado: "
                    f"{selected_provider}"
                ),

            "quota":
                get_ai_quota_status(
                    user_name
                )
        }

    # El proveedor/modelo forma parte de la identidad del
    # aprendizaje para no reutilizar un caché antiguo de Groq
    # cuando ahora corresponde Gemini.
    fingerprint_context = context

    if (
        usage_type == "LEARNING"
        and isinstance(
            context,
            dict
        )
    ):
        fingerprint_context = dict(
            context
        )

        fingerprint_context[
            "_ai_route"
        ] = {
            "provider":
                selected_provider,

            "model":
                selected_model
        }

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
        fingerprint_context,
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
            usage_type,
            context_type
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
    # ====================================================================
    # AI QUOTA GUARD
    # ====================================================================
    #
    # Si ya sabemos que Groq pidió esperar, ni siquiera intentamos
    # otra llamada externa ni persistimos cientos de errores repetidos.
    # ====================================================================

    if (
        selected_provider
        in {"GROQ", "GROQ_LEARNING"}
    ):
        backoff_remaining = (
            _groq_backoff_remaining_seconds()
        )

        if backoff_remaining > 0:
            reason_text = (
                "Groq alcanzó su cuota temporal. "
                "El sistema está esperando automáticamente "
                f"aproximadamente {max(1, backoff_remaining // 60)} min "
                "antes de volver a consultar al proveedor."
            )
            if usage_type in {"AUTO", "MANUAL"} and context_type in {"HOURLY_MARKET_ADVICE", "MANUAL_CHAT"}:
                return {
                    "success": True,
                    "cached": False,
                    "provider_limited": True,
                    "degraded_mode": True,
                    "retry_after_seconds": backoff_remaining,
                    "reason": reason_text,
                    "data": _local_operational_fallback(context, market, question, reason_text),
                    "quota": quota
                }
            return {
                "success": False,
                "provider_limited": True,
                "retry_after_seconds": backoff_remaining,
                "reason": reason_text,
                "quota": quota
            }


    try:

        if selected_provider == "GROQ_LEARNING":
            try:
                logger.info(
                    "AI Learning provider=GROQ_LEARNING model=%s",
                    selected_model
                )
                advice, usage = _call_groq_learning_slot(context)
            except Exception as learning_groq_error:
                logger.warning(
                    "Groq Learning dedicado no disponible: %s. Fallback a GROQ_API_KEY.",
                    learning_groq_error
                )
                _record_usage(
                    user_name, usage_type, context_type, market, "ERROR", {},
                    provider="GROQ_LEARNING", model=selected_model
                )
                selected_provider = "GROQ"
                selected_model = AI_MODEL
                advice, usage = _call_groq(
                    context, question=question, context_type=context_type
                )

        elif (
            selected_provider
            == "GEMINI"
        ):
            try:
                logger.info(
                    "AI Learning provider=GEMINI model=%s",
                    selected_model
                )

                advice, usage = (
                    _call_gemini_learning(
                        context
                    )
                )

            except Exception as gemini_error:
                # ====================================================
                # FAIL-OPEN
                # ====================================================
                # Gemini nunca puede impedir el aprendizaje existente.
                logger.warning(
                    (
                        "Gemini Learning no disponible: %s. "
                        "Fallback a Groq."
                    ),
                    gemini_error
                )

                # ====================================================
                # COMMIT 36Y
                # REGISTRAR EL INTENTO GEMINI FALLIDO
                # ====================================================
                #
                # Esto sirve únicamente para observabilidad.
                #
                # ERROR no cuenta como SUCCESS para las cuotas.
                # Después continúa el fallback normal a Groq.
                # ====================================================

                _record_usage(
                    user_name,
                    usage_type,
                    context_type,
                    market,
                    "ERROR",
                    {},
                    provider=
                        "GEMINI",
                    model=
                        selected_model
                )

                selected_provider = "GROQ"
                selected_model = AI_MODEL

                advice, usage = (
                    _call_groq(
                        context,
                        question,
                        context_type=
                            context_type
                    )
                )

        else:
            advice, usage = (
                _call_groq(
                    context,
                    question,
                    context_type=
                        context_type
                )
            )


        _record_usage(
            user_name,
            usage_type,
            context_type,
            market,
            "SUCCESS",
            usage,
            provider=
                selected_provider,
            model=
                selected_model
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
            question,
            provider=
                selected_provider,
            model=
                selected_model
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
            {},
            provider=
                selected_provider,
            model=
                selected_model
        )


        error_reason = str(e)[:220]
        if usage_type in {"AUTO", "MANUAL"} and context_type in {"HOURLY_MARKET_ADVICE", "MANUAL_CHAT"}:
            return {
                "success": True,
                "cached": False,
                "provider_limited": True,
                "degraded_mode": True,
                "reason": error_reason,
                "data": _local_operational_fallback(context, market, question, error_reason),
                "quota": get_ai_quota_status(user_name)
            }
        return {
            "success": False,
            "reason": error_reason,
            "quota": get_ai_quota_status(user_name)
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
# COMMIT 36S.3
# ADAPTIVE AI TRUST — RESULTADOS REALES
# ============================================================================

AI_TRUST_PRELIMINARY_SAMPLE = max(
    5,
    int(
        os.getenv(
            'AI_TRUST_PRELIMINARY_SAMPLE',
            '10'
        )
    )
)


AI_TRUST_RELIABLE_SAMPLE = max(
    AI_TRUST_PRELIMINARY_SAMPLE,
    int(
        os.getenv(
            'AI_TRUST_RELIABLE_SAMPLE',
            '25'
        )
    )
)


def get_ai_adaptive_trust_summary(
    user_name=None,
    market=None,
    context_type=None
):
    """
    COMMIT 36S.3

    Mide si cada proveedor/modelo de IA está aportando valor
    según outcomes REALES ya liquidados.

    NO usa la confidence declarada por el modelo como medida
    de confianza.

    NO modifica autoridad.
    NO modifica trading.

    Interpretación:

    SUPPORT:
        si la señal original gana, la IA tuvo razón.

    DISAGREE:
        si la señal original pierde, la IA tuvo razón
        al cuestionarla.

    CAUTION / INFO / NO_EDGE:
        se observan, pero no se utilizan para conceder
        autoridad operativa en esta fase.
    """

    empty = {
        'mode':
            'ADAPTIVE_TRUST_SHADOW',

        'authority_changed':
            False,

        'preliminary_sample':
            AI_TRUST_PRELIMINARY_SAMPLE,

        'reliable_sample':
            AI_TRUST_RELIABLE_SAMPLE,

        'settled_total':
            0,

        'actionable_total':
            0,

        'groups':
            {}
    }

    db = _db()

    if (
        db is None
        or not getattr(
            db,
            'enabled',
            False
        )
    ):
        return empty

    try:
        def _op():
            query = (
                db.client
                .table(
                    'ai_advisor_observations'
                )
                .select(
                    (
                        'provider,'
                        'model,'
                        'context_type,'
                        'market,'
                        'ai_verdict,'
                        'outcome_r,'
                        'outcome_win,'
                        'outcome_source'
                    )
                )
                .eq(
                    'outcome_status',
                    'SETTLED'
                )
                .limit(
                    2000
                )
            )

            if user_name:
                query = query.eq(
                    'user_name',
                    str(
                        user_name
                    )
                )

            if market:
                query = query.eq(
                    'market',
                    str(
                        market
                    ).upper()
                )

            if context_type:
                query = query.eq(
                    'context_type',
                    str(
                        context_type
                    ).upper()
                )

            return query.execute()

        response = db._with_retry(
            _op
        )

        rows = (
            response.data
            if (
                response
                and response.data
            )
            else []
        )

        groups = {}

        settled_total = 0
        actionable_total = 0

        for row in rows:
            try:
                outcome_r = float(
                    row.get(
                        'outcome_r'
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            settled_total += 1

            provider = str(
                row.get(
                    'provider'
                )
                or 'UNKNOWN'
            ).upper()

            model = str(
                row.get(
                    'model'
                )
                or 'UNKNOWN'
            )

            row_context = str(
                row.get(
                    'context_type'
                )
                or 'UNKNOWN'
            ).upper()

            row_market = str(
                row.get(
                    'market'
                )
                or 'UNKNOWN'
            ).upper()

            verdict = str(
                row.get(
                    'ai_verdict'
                )
                or 'INFO'
            ).upper()

            group_key = (
                f'{provider}|'
                f'{model}|'
                f'{row_market}|'
                f'{row_context}'
            )

            bucket = groups.setdefault(
                group_key,
                {
                    'provider':
                        provider,

                    'model':
                        model,

                    'market':
                        row_market,

                    'context_type':
                        row_context,

                    'settled':
                        0,

                    'actionable':
                        0,

                    'correct_judgements':
                        0,

                    'decision_value_r_sum':
                        0.0,

                    'support_n':
                        0,

                    'support_system_r_sum':
                        0.0,

                    'disagree_n':
                        0,

                    'disagree_system_r_sum':
                        0.0,

                    'outcome_sources':
                        {}
                }
            )

            bucket[
                'settled'
            ] += 1

            source = str(
                row.get(
                    'outcome_source'
                )
                or 'UNKNOWN'
            )

            bucket[
                'outcome_sources'
            ][
                source
            ] = (
                bucket[
                    'outcome_sources'
                ].get(
                    source,
                    0
                )
                + 1
            )

            # ========================================================
            # VALOR DE LA DECISIÓN DE LA IA
            # ========================================================
            #
            # SUPPORT:
            #     resultado positivo = IA acertó.
            #
            # DISAGREE:
            #     resultado negativo = IA acertó al objetar.
            # ========================================================

            decision_value_r = None

            if verdict == 'SUPPORT':
                decision_value_r = (
                    outcome_r
                )

                bucket[
                    'support_n'
                ] += 1

                bucket[
                    'support_system_r_sum'
                ] += outcome_r

            elif verdict == 'DISAGREE':
                decision_value_r = (
                    -outcome_r
                )

                bucket[
                    'disagree_n'
                ] += 1

                bucket[
                    'disagree_system_r_sum'
                ] += outcome_r

            if decision_value_r is None:
                continue

            actionable_total += 1

            bucket[
                'actionable'
            ] += 1

            bucket[
                'decision_value_r_sum'
            ] += decision_value_r

            if decision_value_r > 0:
                bucket[
                    'correct_judgements'
                ] += 1

        final = {}

        for (
            group_key,
            bucket
        ) in groups.items():

            sample = int(
                bucket[
                    'actionable'
                ]
            )

            avg_value_r = (
                (
                    bucket[
                        'decision_value_r_sum'
                    ]
                    / sample
                )
                if sample
                else None
            )

            judgement_rate = (
                (
                    bucket[
                        'correct_judgements'
                    ]
                    / sample
                    * 100
                )
                if sample
                else None
            )

            # ========================================================
            # ESTADO DE CONFIANZA
            # ========================================================
            #
            # Importante:
            # esto NO cambia autoridad.
            #
            # Sólo entrega un diagnóstico para 36S.4.
            # ========================================================

            if sample < AI_TRUST_PRELIMINARY_SAMPLE:
                trust_state = (
                    'INSUFFICIENT_EVIDENCE'
                )

            elif (
                avg_value_r is None
                or avg_value_r <= 0
            ):
                trust_state = (
                    'DEGRADE_CANDIDATE'
                )

            elif sample < AI_TRUST_RELIABLE_SAMPLE:
                trust_state = (
                    'PROMISING_SHADOW'
                )

            else:
                trust_state = (
                    'LIMITED_AUTHORITY_REVIEW'
                )

            support_n = int(
                bucket[
                    'support_n'
                ]
            )

            disagree_n = int(
                bucket[
                    'disagree_n'
                ]
            )

            final[
                group_key
            ] = {
                'provider':
                    bucket[
                        'provider'
                    ],

                'model':
                    bucket[
                        'model'
                    ],

                'market':
                    bucket[
                        'market'
                    ],

                'context_type':
                    bucket[
                        'context_type'
                    ],

                'settled':
                    bucket[
                        'settled'
                    ],

                'actionable_sample':
                    sample,

                'judgement_accuracy_pct':
                    (
                        round(
                            judgement_rate,
                            2
                        )
                        if judgement_rate
                        is not None
                        else None
                    ),

                'avg_decision_value_r':
                    (
                        round(
                            avg_value_r,
                            4
                        )
                        if avg_value_r
                        is not None
                        else None
                    ),

                # SUPPORT positivo significa:
                # las operaciones que apoyó tendieron a funcionar.
                'support_sample':
                    support_n,

                'support_avg_system_r':
                    (
                        round(
                            (
                                bucket[
                                    'support_system_r_sum'
                                ]
                                / support_n
                            ),
                            4
                        )
                        if support_n
                        else None
                    ),

                # DISAGREE negativo en system_r es BUENO:
                # significa que cuestionó operaciones perdedoras.
                'disagree_sample':
                    disagree_n,

                'disagree_avg_system_r':
                    (
                        round(
                            (
                                bucket[
                                    'disagree_system_r_sum'
                                ]
                                / disagree_n
                            ),
                            4
                        )
                        if disagree_n
                        else None
                    ),

                'trust_state':
                    trust_state,

                'authority_changed':
                    False,

                'outcome_sources':
                    bucket[
                        'outcome_sources'
                    ]
            }

        return {
            **empty,

            'settled_total':
                settled_total,

            'actionable_total':
                actionable_total,

            'groups':
                final
        }

    except Exception as e:
        # ============================================================
        # FAIL-OPEN
        # ============================================================
        #
        # Adaptive Trust jamás puede romper la IA ni el trading.
        # ============================================================

        logger.warning(
            'Adaptive AI Trust: %s',
            e
        )

        return {
            **empty,

            'error':
                str(
                    e
                )[:180]
        }
# ============================================================================
# COMMIT 36S.4
# AI GOVERNANCE / AUTO-DEMOTION
# ============================================================================

AI_GOVERNANCE_ENABLED = (
    os.getenv(
        "AI_GOVERNANCE_ENABLED",
        "true"
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


AI_GOVERNANCE_MIN_ACTIONABLE_SAMPLE = max(
    10,
    int(
        os.getenv(
            "AI_GOVERNANCE_MIN_ACTIONABLE_SAMPLE",
            "25"
        )
    )
)


def get_ai_governance_state(
    market=None,
    context_type=None,
    provider=None,
    model=None
):
    """
    COMMIT 36S.4

    Gobierno de autoridad de la IA basado en resultados.

    PRINCIPIO ASIMÉTRICO:

    - evidencia negativa suficiente:
        puede DEMOTAR automáticamente;

    - evidencia positiva:
        NO promociona automáticamente;
        sólo permite revisión humana/posterior.

    Si 36S.3 no está disponible o falla:
        NO cambia la autoridad existente.

    Esta función no modifica señales, SL, TP, leverage,
    Guardian ni pesos.
    """

    result = {
        "enabled":
            AI_GOVERNANCE_ENABLED,

        "state":
            "INSUFFICIENT_EVIDENCE",

        "authority_action":
            "KEEP_CURRENT",

        "auto_demoted":
            False,

        "promotion_allowed":
            False,

        "promotion_review":
            False,

        "actionable_sample":
            0,

        "avg_decision_value_r":
            None,

        "provider":
            str(
                provider
                or AI_PROVIDER
            ).upper(),

        "model":
            str(
                model
                or AI_MODEL
            ),

        "market":
            (
                str(
                    market
                ).upper()
                if market
                else None
            ),

        "context_type":
            (
                str(
                    context_type
                ).upper()
                if context_type
                else None
            ),

        "reason":
            None
    }

    if not AI_GOVERNANCE_ENABLED:
        result[
            "state"
        ] = "GOVERNANCE_DISABLED"

        result[
            "reason"
        ] = (
            "AI_GOVERNANCE_ENABLED=false"
        )

        return result

    # ================================================================
    # 36S.3 ES LA ÚNICA FUENTE VÁLIDA PARA AUTO-DEMOTION
    # ================================================================
    #
    # No usamos confidence del LLM.
    # No usamos opiniones.
    # No usamos Win Rate aislado.
    #
    # Si 36S.3 aún no existe, Governance queda neutral.
    # ================================================================

    adaptive_fn = globals().get(
        "get_ai_adaptive_trust_summary"
    )

    if not callable(
        adaptive_fn
    ):
        result[
            "state"
        ] = "WAITING_FOR_36S3"

        result[
            "reason"
        ] = (
            "Adaptive Trust 36S.3 "
            "no está disponible."
        )

        return result

    try:
        try:
            trust = adaptive_fn(
                market=
                    market,
                context_type=
                    context_type
            )

        except TypeError:
            # Compatibilidad defensiva si la firma de 36S.3
            # fuera distinta en una versión anterior.
            trust = adaptive_fn()

        if not isinstance(
            trust,
            dict
        ):
            result[
                "state"
            ] = "TRUST_DATA_INVALID"

            result[
                "reason"
            ] = (
                "Adaptive Trust devolvió "
                "un resultado inválido."
            )

            return result

        groups = (
            trust.get(
                "groups"
            )
            or {}
        )

        if not isinstance(
            groups,
            dict
        ):
            groups = {}

        selected_provider = str(
            provider
            or AI_PROVIDER
        ).upper()

        selected_model = str(
            model
            or AI_MODEL
        )

        selected_market = (
            str(
                market
            ).upper()
            if market
            else None
        )

        selected_context = (
            str(
                context_type
            ).upper()
            if context_type
            else None
        )

        matched = []

        # ============================================================
        # NO MEZCLAR MODELOS / MERCADOS / FUNCIONES
        # ============================================================
        #
        # Groq Futures SIGNAL no debe heredar resultados de:
        #
        # - Gemini Learning;
        # - Spot;
        # - Guardian;
        # - otro modelo.
        # ============================================================

        for group in groups.values():
            if not isinstance(
                group,
                dict
            ):
                continue

            group_provider = str(
                group.get(
                    "provider"
                )
                or ""
            ).upper()

            group_model = str(
                group.get(
                    "model"
                )
                or ""
            )

            group_market = str(
                group.get(
                    "market"
                )
                or ""
            ).upper()

            group_context = str(
                group.get(
                    "context_type"
                )
                or ""
            ).upper()

            if (
                group_provider
                and group_provider
                != selected_provider
            ):
                continue

            if (
                group_model
                and selected_model
                and group_model
                != selected_model
            ):
                continue

            if (
                selected_market
                and group_market
                and group_market
                != selected_market
            ):
                continue

            if (
                selected_context
                and group_context
                and group_context
                != selected_context
            ):
                continue

            try:
                sample = int(
                    group.get(
                        "actionable_sample"
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError
            ):
                sample = 0

            try:
                avg_value = (
                    float(
                        group.get(
                            "avg_decision_value_r"
                        )
                    )
                    if group.get(
                        "avg_decision_value_r"
                    )
                    is not None
                    else None
                )

            except (
                TypeError,
                ValueError
            ):
                avg_value = None

            if (
                sample <= 0
                or avg_value is None
            ):
                continue

            matched.append(
                {
                    "sample":
                        sample,

                    "avg_value_r":
                        avg_value
                }
            )

        if not matched:
            result[
                "state"
            ] = "NO_MATCHING_OUTCOMES"

            result[
                "reason"
            ] = (
                "Todavía no existen outcomes "
                "Adaptive Trust suficientes "
                "para este proveedor/modelo/"
                "mercado/contexto."
            )

            return result

        total_sample = sum(
            item[
                "sample"
            ]
            for item
            in matched
        )

        weighted_value_sum = sum(
            (
                item[
                    "avg_value_r"
                ]
                * item[
                    "sample"
                ]
            )
            for item
            in matched
        )

        avg_decision_value_r = (
            weighted_value_sum
            / total_sample
            if total_sample
            else None
        )

        result[
            "actionable_sample"
        ] = total_sample

        result[
            "avg_decision_value_r"
        ] = (
            round(
                avg_decision_value_r,
                4
            )
            if avg_decision_value_r
            is not None
            else None
        )

        # ============================================================
        # MUESTRA INSUFICIENTE
        # ================================================================

        if (
            total_sample
            < AI_GOVERNANCE_MIN_ACTIONABLE_SAMPLE
        ):
            result[
                "state"
            ] = "INSUFFICIENT_EVIDENCE"

            result[
                "reason"
            ] = (
                "Muestra insuficiente: "
                f"{total_sample}/"
                f"{AI_GOVERNANCE_MIN_ACTIONABLE_SAMPLE}."
            )

            return result

        # ============================================================
        # AUTO-DEMOTION
        # ================================================================
        #
        # Si con muestra suficiente la IA aporta valor R NEGATIVO,
        # pierde autoridad de veto.
        #
        # IMPORTANTE:
        #
        # avg = 0 NO activa demotion.
        #
        # Sólo evidencia de degradación real:
        #
        #     avg_decision_value_r < 0
        # ================================================================

        if (
            avg_decision_value_r
            is not None
            and avg_decision_value_r < 0
        ):
            result.update({
                "state":
                    "AUTO_DEMOTED",

                "authority_action":
                    "ADVISORY_ONLY",

                "auto_demoted":
                    True,

                "promotion_allowed":
                    False,

                "promotion_review":
                    False,

                "reason":
                    (
                        "La IA presenta valor de decisión "
                        "R negativo con muestra suficiente."
                    )
            })

            return result

        # ============================================================
        # EVIDENCIA POSITIVA
        # ================================================================
        #
        # Incluso si funciona bien:
        #
        # NO aumentamos automáticamente su autoridad.
        #
        # Sólo mantenemos la autoridad limitada existente y
        # habilitamos revisión futura.
        # ================================================================

        if (
            avg_decision_value_r
            is not None
            and avg_decision_value_r > 0
        ):
            result.update({
                "state":
                    "POSITIVE_EVIDENCE",

                "authority_action":
                    "KEEP_CURRENT_LIMITED",

                "auto_demoted":
                    False,

                "promotion_allowed":
                    False,

                "promotion_review":
                    True,

                "reason":
                    (
                        "La IA aporta valor R positivo, "
                        "pero la promoción requiere "
                        "validación adicional/OOS."
                    )
            })

            return result

        # avg == 0
        result[
            "state"
        ] = "NEUTRAL_EVIDENCE"

        result[
            "reason"
        ] = (
            "La IA no demuestra todavía "
            "aporte ni degradación."
        )

        return result

    except Exception as governance_error:
        # ============================================================
        # FAIL-OPEN
        # ============================================================
        #
        # Un error en Governance no cambia el comportamiento actual
        # del sistema.
        # ============================================================

        logger.warning(
            "AI Governance: %s",
            governance_error
        )

        result[
            "state"
        ] = "GOVERNANCE_ERROR"

        result[
            "reason"
        ] = str(
            governance_error
        )[:180]

        return result


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

        # 36S.4
        # Se completa antes de conceder autoridad.
        "governance":
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
    # ================================================================
    # COMMIT 36S.4
    # GOVERNANCE ANTES DE CONCEDER AUTORIDAD
    # ================================================================

    governance_market = None

    if original_action in (
        "LONG",
        "SHORT"
    ):
        governance_market = (
            "FUTURES"
        )

    elif original_action in (
        "COMPRA_SPOT",
        "VENTA_SPOT"
    ):
        governance_market = (
            "SPOT"
        )

    try:
        governance = (
            get_ai_governance_state(
                market=
                    governance_market,

                context_type=
                    context_type,

                provider=
                    AI_PROVIDER,

                model=
                    AI_MODEL
            )
        )

    except Exception as governance_error:
        # Fail-open.
        governance = {
            "state":
                "GOVERNANCE_ERROR",

            "auto_demoted":
                False,

            "authority_action":
                "KEEP_CURRENT",

            "reason":
                str(
                    governance_error
                )[:180]
        }

    control[
        "governance"
    ] = governance

    # ================================================================
    # AUTO-DEMOTION
    # ================================================================
    #
    # La IA sigue pudiendo:
    #
    # - explicar;
    # - aconsejar;
    # - aprender.
    #
    # Sólo pierde capacidad de MODIFICAR/BLOQUEAR decisiones.
    # ================================================================

    if governance.get(
        "auto_demoted"
    ):
        control[
            "reason"
        ] = (
            "AI_AUTHORITY_AUTO_DEMOTED: "
            + str(
                governance.get(
                    "reason"
                )
                or ""
            )[:380]
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
# ============================================================================
# COMMIT 36T.1
# SPOT / TGP SHADOW EVIDENCE
# ============================================================================

def get_spot_tgp_shadow_evidence(
    user_name,
    limit=1000
):
    """
    COMMIT 36T.1

    Mide qué habría pasado si la IA hubiera bloqueado
    determinadas señales Spot.

    READ-ONLY.

    NO:
    - modifica señales;
    - modifica TGP;
    - modifica Guardian;
    - modifica el portfolio;
    - cambia autoridad IA;
    - escribe en Supabase.

    Esta fase utiliza el PnL bruto de la señal únicamente como
    PROXY diagnóstico.

    36S.2B.2 permanece bloqueado hasta añadir posteriormente:
    - contrafactual real del portfolio;
    - costes de rotación;
    - comparación contra HOLD.
    """

    result = {
        "mode":
            "SPOT_TGP_SHADOW_EVIDENCE",

        "authority_changed":
            False,

        "ready_for_36S2B2_review":
            False,

        "economic_status":
            "GROSS_SIGNAL_PROXY_ONLY",

        "minimums": {
            "resolved_total":
                25,

            "would_block_resolved":
                10,

            "validation_resolved":
                10,

            "validation_would_block":
                3
        },

        "observations":
            0,

        "unique_linked_signals":
            0,

        "resolved_total":
            0,

        "unresolved_total":
            0,

        "invalid_source_ids":
            0,

        "ambiguous_market":
            0,

        "would_block": {
            "resolved":
                0,

            "losses_avoided":
                0,

            "winners_blocked":
                0,

            "neutral":
                0,

            "gross_value_pct_sum":
                0.0,

            "gross_value_pct_avg":
                None
        },

        "calibration_70":
            {},

        "validation_30":
            {},

        "gate": {
            "sample_ok":
                False,

            "block_sample_ok":
                False,

            "validation_ok":
                False,

            "validation_block_sample_ok":
                False,

            "gross_value_positive":
                False,

            "validation_gross_value_positive":
                False,

            "portfolio_counterfactual_verified":
                False,

            "costs_verified":
                False
        },

        "reason":
            None
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
        result[
            "reason"
        ] = "SUPABASE_UNAVAILABLE"

        return result

    user_name = str(
        user_name
        or ""
    ).strip()

    if not user_name:
        result[
            "reason"
        ] = "USER_REQUIRED"

        return result

    try:
        import uuid as _uuid

        safe_limit = max(
            50,
            min(
                int(
                    limit
                    or 1000
                ),
                2000
            )
        )

        # ================================================================
        # 1. OBSERVACIONES IA SPOT
        # ================================================================

        observations_response = (
            db._with_retry(
                lambda: (
                    db.client
                    .table(
                        "ai_advisor_observations"
                    )
                    .select(
                        (
                            "id,"
                            "source_signal_id,"
                            "ai_verdict,"
                            "ai_confidence,"
                            "created_at,"
                            "symbol,"
                            "timeframe"
                        )
                    )
                    .eq(
                        "user_name",
                        user_name
                    )
                    .eq(
                        "market",
                        "SPOT"
                    )
                    .eq(
                        "context_type",
                        "HOURLY_MARKET_ADVICE"
                    )
                    .order(
                        "created_at",
                        desc=False
                    )
                    .limit(
                        safe_limit
                    )
                    .execute()
                )
            )
        )

        observations = (
            observations_response.data
            if (
                observations_response
                and observations_response.data
            )
            else []
        )

        result[
            "observations"
        ] = len(
            observations
        )

        # ================================================================
        # UNA SEÑAL = UNA OBSERVACIÓN
        # ================================================================
        #
        # Conservamos la PRIMERA opinión.
        #
        # Si la IA analiza la misma señal varias veces posteriormente,
        # no puede elegir retroactivamente la opinión que mejor quedó.
        # ================================================================

        first_by_signal = {}

        for row in observations:

            if not isinstance(
                row,
                dict
            ):
                continue

            raw_id = str(
                row.get(
                    "source_signal_id"
                )
                or ""
            ).strip()

            if not raw_id:
                continue

            try:
                canonical_id = str(
                    _uuid.UUID(
                        raw_id
                    )
                )

            except Exception:

                result[
                    "invalid_source_ids"
                ] += 1

                continue

            if (
                canonical_id
                not in first_by_signal
            ):
                first_by_signal[
                    canonical_id
                ] = row

        source_ids = list(
            first_by_signal.keys()
        )

        result[
            "unique_linked_signals"
        ] = len(
            source_ids
        )

        if not source_ids:

            result[
                "reason"
            ] = (
                "NO_LINKED_SPOT_AI_OBSERVATIONS"
            )

            return result

        # ================================================================
        # HELPER DE BATCHES
        # ================================================================

        def _chunks(
            values,
            size=100
        ):

            for start in range(
                0,
                len(values),
                size
            ):

                yield values[
                    start:
                    start + size
                ]

        # ================================================================
        # 2. SEÑALES ORIGINALES
        # ================================================================

        signals_by_id = {}

        for batch in _chunks(
            source_ids
        ):

            response = db._with_retry(
                lambda batch=batch: (
                    db.client
                    .table(
                        "signals"
                    )
                    .select(
                        (
                            "id,"
                            "symbol,"
                            "timeframe,"
                            "system_type,"
                            "action_original,"
                            "status,"
                            "created_at"
                        )
                    )
                    .in_(
                        "id",
                        batch
                    )
                    .execute()
                )
            )

            for row in (
                response.data
                if (
                    response
                    and response.data
                )
                else []
            ):

                if isinstance(
                    row,
                    dict
                ):

                    signals_by_id[
                        str(
                            row.get(
                                "id"
                            )
                        )
                    ] = row

        # ================================================================
        # EXCLUSIVAMENTE SPOT VERIFICADO
        # ================================================================

        result_ids = [

            signal_id

            for (
                signal_id,
                signal
            )
            in signals_by_id.items()

            if str(
                signal.get(
                    "system_type"
                )
                or ""
            ).lower()
            == "spot"
        ]

        # ================================================================
        # 3. RESULTADOS REALES DE REVIEWTRADER
        # ================================================================

        results_by_signal = {}

        for batch in _chunks(
            result_ids
        ):

            response = db._with_retry(
                lambda batch=batch: (
                    db.client
                    .table(
                        "signal_results"
                    )
                    .select(
                        (
                            "signal_id,"
                            "status,"
                            "pnl_pct,"
                            "created_at"
                        )
                    )
                    .in_(
                        "signal_id",
                        batch
                    )
                    .order(
                        "created_at",
                        desc=False
                    )
                    .execute()
                )
            )

            for row in (
                response.data
                if (
                    response
                    and response.data
                )
                else []
            ):

                if not isinstance(
                    row,
                    dict
                ):
                    continue

                sid = str(
                    row.get(
                        "signal_id"
                    )
                    or ""
                )

                if sid:
                    results_by_signal[
                        sid
                    ] = row

        # ================================================================
        # 4. CRUZAR IA VS RESULTADO REAL
        # ================================================================

        evaluated_rows = []

        for (
            signal_id,
            observation
        ) in first_by_signal.items():

            signal = (
                signals_by_id.get(
                    signal_id
                )
            )

            if not signal:

                result[
                    "unresolved_total"
                ] += 1

                continue

            system_type = str(
                signal.get(
                    "system_type"
                )
                or ""
            ).lower()

            # No reinterpretamos filas ambiguas.
            if system_type != "spot":

                result[
                    "ambiguous_market"
                ] += 1

                continue

            action = str(
                signal.get(
                    "action_original"
                )
                or ""
            ).upper()

            if action not in (
                "COMPRA_SPOT",
                "VENTA_SPOT"
            ):
                continue

            signal_result = (
                results_by_signal.get(
                    signal_id
                )
            )

            if not signal_result:

                result[
                    "unresolved_total"
                ] += 1

                continue

            status = str(
                signal_result.get(
                    "status"
                )
                or ""
            ).lower()

            if status not in (
                "tp_hit",
                "sl_hit",
                "expired"
            ):

                result[
                    "unresolved_total"
                ] += 1

                continue

            try:
                pnl_pct = float(
                    signal_result.get(
                        "pnl_pct"
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError
            ):

                result[
                    "unresolved_total"
                ] += 1

                continue

            verdict = str(
                observation.get(
                    "ai_verdict"
                )
                or ""
            ).upper()

            try:
                confidence = int(
                    float(
                        observation.get(
                            "ai_confidence"
                        )
                        or 0
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                confidence = 0

            # ============================================================
            # RECONSTRUCCIÓN DETERMINISTA DEL WOULD_BLOCK
            # ============================================================
            #
            # Es exactamente la regla Shadow:
            #
            # DISAGREE >= 80
            # ============================================================

            would_block = bool(
                verdict == "DISAGREE"
                and confidence >= 80
            )

            # ============================================================
            # VALOR DEL BLOQUEO
            # ============================================================
            #
            # Ejemplo:
            #
            # La operación habría perdido -2%
            # IA habría bloqueado:
            #
            #     valor IA = +2%
            #
            # La operación habría ganado +3%
            # IA habría bloqueado:
            #
            #     valor IA = -3%
            #
            # ============================================================

            block_value_pct = (
                -pnl_pct
                if would_block
                else None
            )

            evaluated_rows.append({

                "signal_id":
                    signal_id,

                "created_at":
                    str(
                        signal.get(
                            "created_at"
                        )
                        or ""
                    ),

                "symbol":
                    signal.get(
                        "symbol"
                    ),

                "timeframe":
                    signal.get(
                        "timeframe"
                    ),

                "action":
                    action,

                "status":
                    status,

                "system_pnl_pct":
                    pnl_pct,

                "ai_verdict":
                    verdict,

                "ai_confidence":
                    confidence,

                "would_block":
                    would_block,

                "block_value_pct":
                    block_value_pct
            })

        evaluated_rows.sort(
            key=lambda row:
                row[
                    "created_at"
                ]
        )

        result[
            "resolved_total"
        ] = len(
            evaluated_rows
        )

        # ================================================================
        # RESUMEN
        # ================================================================

        def _summarize(
            rows
        ):

            blocks = [

                row
                for row in rows

                if row.get(
                    "would_block"
                )
            ]

            values = [

                float(
                    row[
                        "block_value_pct"
                    ]
                )

                for row in blocks

                if row.get(
                    "block_value_pct"
                )
                is not None
            ]

            return {

                "resolved":
                    len(
                        rows
                    ),

                "would_block_resolved":
                    len(
                        blocks
                    ),

                "losses_avoided":
                    sum(
                        1
                        for row in blocks

                        if float(
                            row[
                                "system_pnl_pct"
                            ]
                        ) < 0
                    ),

                "winners_blocked":
                    sum(
                        1
                        for row in blocks

                        if float(
                            row[
                                "system_pnl_pct"
                            ]
                        ) > 0
                    ),

                "neutral":
                    sum(
                        1
                        for row in blocks

                        if float(
                            row[
                                "system_pnl_pct"
                            ]
                        ) == 0
                    ),

                "gross_value_pct_sum":
                    round(
                        sum(
                            values
                        ),
                        4
                    ),

                "gross_value_pct_avg":
                    (
                        round(
                            sum(
                                values
                            )
                            / len(
                                values
                            ),
                            4
                        )

                        if values
                        else None
                    )
            }

        total_summary = (
            _summarize(
                evaluated_rows
            )
        )

        result[
            "would_block"
        ] = {

            "resolved":
                total_summary[
                    "would_block_resolved"
                ],

            "losses_avoided":
                total_summary[
                    "losses_avoided"
                ],

            "winners_blocked":
                total_summary[
                    "winners_blocked"
                ],

            "neutral":
                total_summary[
                    "neutral"
                ],

            "gross_value_pct_sum":
                total_summary[
                    "gross_value_pct_sum"
                ],

            "gross_value_pct_avg":
                total_summary[
                    "gross_value_pct_avg"
                ]
        }

        # ================================================================
        # 70 / 30 WALK-FORWARD SIMPLE
        # ================================================================
        #
        # Primer 70%:
        # calibración / observación.
        #
        # Último 30%:
        # validación posterior.
        # ================================================================

        split_index = int(
            len(
                evaluated_rows
            )
            * 0.70
        )

        calibration_rows = (
            evaluated_rows[
                :split_index
            ]
        )

        validation_rows = (
            evaluated_rows[
                split_index:
            ]
        )

        calibration = (
            _summarize(
                calibration_rows
            )
        )

        validation = (
            _summarize(
                validation_rows
            )
        )

        result[
            "calibration_70"
        ] = calibration

        result[
            "validation_30"
        ] = validation

        # ================================================================
        # 5. GATE DIAGNÓSTICO
        # ================================================================

        minimums = (
            result[
                "minimums"
            ]
        )

        gate = (
            result[
                "gate"
            ]
        )

        gate[
            "sample_ok"
        ] = bool(
            result[
                "resolved_total"
            ]
            >= minimums[
                "resolved_total"
            ]
        )

        gate[
            "block_sample_ok"
        ] = bool(
            total_summary[
                "would_block_resolved"
            ]
            >= minimums[
                "would_block_resolved"
            ]
        )

        gate[
            "validation_ok"
        ] = bool(
            validation[
                "resolved"
            ]
            >= minimums[
                "validation_resolved"
            ]
        )

        gate[
            "validation_block_sample_ok"
        ] = bool(
            validation[
                "would_block_resolved"
            ]
            >= minimums[
                "validation_would_block"
            ]
        )

        gate[
            "gross_value_positive"
        ] = bool(
            total_summary[
                "would_block_resolved"
            ] > 0
            and total_summary[
                "gross_value_pct_sum"
            ] > 0
        )

        gate[
            "validation_gross_value_positive"
        ] = bool(
            validation[
                "would_block_resolved"
            ] > 0
            and validation[
                "gross_value_pct_sum"
            ] > 0
        )

        diagnostic_ready = all((

            gate[
                "sample_ok"
            ],

            gate[
                "block_sample_ok"
            ],

            gate[
                "validation_ok"
            ],

            gate[
                "validation_block_sample_ok"
            ],

            gate[
                "gross_value_positive"
            ],

            gate[
                "validation_gross_value_positive"
            ]
        ))

        # ================================================================
        # IMPORTANTE
        # ================================================================
        #
        # Incluso aunque todos los gates anteriores sean positivos,
        # 36S.2B.2 NO se activa.
        #
        # Esto es solamente la primera evidencia.
        #
        # Falta 36T.2:
        #
        # - portfolio real;
        # - BTC/PAXG/USDT;
        # - comparación contra HOLD;
        # - costes de rotación.
        # ================================================================

        result[
            "ready_for_36S2B2_review"
        ] = False

        if not diagnostic_ready:

            result[
                "reason"
            ] = (
                "COLLECTING_SPOT_SHADOW_OUTCOMES"
            )

        else:

            result[
                "reason"
            ] = (
                "SIGNAL_PROXY_POSITIVE_"
                "WAITING_FOR_36T2_PORTFOLIO_NET"
            )

        return result

    except Exception as error:

        # ================================================================
        # FAIL-OPEN
        # ================================================================
        #
        # Un fallo de estadísticas nunca afecta Spot.
        # ================================================================

        logger.warning(
            "Spot TGP shadow evidence: %s",
            error
        )

        result[
            "reason"
        ] = (
            "EVIDENCE_ERROR: "
            + str(
                error
            )[:180]
        )

        return result
# ============================================================================
# COMMIT 36T
# SPOT / TGP — PORTFOLIO-AWARE SHADOW EVIDENCE
# ============================================================================

def get_spot_tgp_portfolio_evidence(
    user_name,
    limit=1000
):
    """
    COMMIT 36T — EVIDENCIA SPOT/TGP COMPLETA (SHADOW).

    Combina:

    1. resultado direccional de la señal Spot;
    2. primera opinión de la IA;
    3. composición del portfolio que la IA vio;
    4. pisos/techos reales del Guardian TGP;
    5. corte temporal 70/30.

    READ-ONLY.

    Nunca:
    - modifica señales;
    - modifica portfolio;
    - modifica TGP;
    - modifica Guardian;
    - cambia autoridad IA.
    """

    result = {
        "mode":
            "SPOT_TGP_36T_COMPLETE",

        "authority_changed":
            False,

        "ready_for_36S2B2_review":
            False,

        "signal_evidence":
            {},

        "portfolio_policy": {
            "thresholds_pct":
                {},

            "resolved_with_context":
                0,

            "would_block_with_context":
                0,

            "context_coverage_pct":
                None,

            "would_block_context_coverage_pct":
                None,

            "reserve_stress_resolved":
                0,

            "concentration_resolved":
                0,

            "would_block_under_reserve_stress":
                0,

            "would_block_under_concentration":
                0
        },

        "calibration_70":
            {},

        "validation_30":
            {},

        "gate": {
            "signal_sample_ok":
                False,

            "block_sample_ok":
                False,

            "validation_ok":
                False,

            "validation_block_sample_ok":
                False,

            "gross_value_positive":
                False,

            "validation_gross_value_positive":
                False,

            "portfolio_context_coverage_ok":
                False,

            "validation_portfolio_context_ok":
                False,

            "portfolio_counterfactual_verified":
                False,

            "costs_verified":
                False
        },

        "status":
            "COLLECTING_EVIDENCE",

        "reason":
            None
    }

    # ================================================================
    # REUTILIZAR 36T.1
    # ================================================================

    base_fn = globals().get(
        "get_spot_tgp_shadow_evidence"
    )

    if not callable(
        base_fn
    ):
        result[
            "status"
        ] = "WAITING_FOR_36T1"

        result[
            "reason"
        ] = (
            "get_spot_tgp_shadow_evidence "
            "no está disponible."
        )

        return result

    try:
        base = base_fn(
            user_name=user_name,
            limit=limit
        )

    except Exception as base_error:
        result[
            "status"
        ] = "BASE_EVIDENCE_ERROR"

        result[
            "reason"
        ] = str(
            base_error
        )[:180]

        return result

    if not isinstance(
        base,
        dict
    ):
        result[
            "status"
        ] = "BASE_EVIDENCE_INVALID"

        result[
            "reason"
        ] = (
            "36T.1 devolvió evidencia inválida."
        )

        return result

    result[
        "signal_evidence"
    ] = base

    db = _db()

    if (
        db is None
        or not getattr(
            db,
            "enabled",
            False
        )
    ):
        result[
            "status"
        ] = "SUPABASE_UNAVAILABLE"

        result[
            "reason"
        ] = "Supabase no disponible."

        return result

    user_name = str(
        user_name
        or ""
    ).strip()

    if not user_name:
        result[
            "status"
        ] = "USER_REQUIRED"

        result[
            "reason"
        ] = "Usuario requerido."

        return result

    try:
        import uuid as _uuid

        # ================================================================
        # POLÍTICA REAL DEL GUARDIAN
        # ================================================================
        #
        # Valores fallback:
        #
        # BTC  >= 10%
        # PAXG >= 10%
        # USDT >= 5%
        # concentración <= 75%
        #
        # Pero primero intentamos leer los valores REALES del Guardian.
        # ================================================================

        reserve_btc = 10.0
        reserve_paxg = 10.0
        reserve_usdt = 5.0
        max_concentration = 75.0

        try:
            from portfolio_guardian import (
                portfolio_guardian as _pg
            )

            reserves = getattr(
                _pg,
                "MIN_RESERVE_PCTS",
                {}
            ) or {}

            reserve_btc = float(
                reserves.get(
                    "BTC",
                    0.10
                )
            ) * 100.0

            reserve_paxg = float(
                reserves.get(
                    "PAXG",
                    0.10
                )
            ) * 100.0

            reserve_usdt = float(
                reserves.get(
                    "USDT",
                    0.05
                )
            ) * 100.0

            max_concentration = float(
                getattr(
                    _pg,
                    "MAX_CONCENTRATION_PCT",
                    0.75
                )
            ) * 100.0

        except Exception:
            # Fail-open diagnóstico.
            #
            # Estos valores nunca toman decisiones.
            pass

        thresholds = {
            "BTC_min":
                round(
                    reserve_btc,
                    2
                ),

            "PAXG_min":
                round(
                    reserve_paxg,
                    2
                ),

            "USDT_min":
                round(
                    reserve_usdt,
                    2
                ),

            "max_concentration":
                round(
                    max_concentration,
                    2
                )
        }

        result[
            "portfolio_policy"
        ][
            "thresholds_pct"
        ] = thresholds

        safe_limit = max(
            50,
            min(
                int(
                    limit
                    or 1000
                ),
                2000
            )
        )

        # ================================================================
        # OBSERVACIONES SPOT DE LA IA
        # ================================================================

        response = db._with_retry(
            lambda: (
                db.client
                .table(
                    "ai_advisor_observations"
                )
                .select(
                    (
                        "id,"
                        "source_signal_id,"
                        "system_action,"
                        "ai_verdict,"
                        "ai_confidence,"
                        "context_snapshot,"
                        "created_at,"
                        "symbol,"
                        "timeframe"
                    )
                )
                .eq(
                    "user_name",
                    user_name
                )
                .eq(
                    "market",
                    "SPOT"
                )
                .eq(
                    "context_type",
                    "HOURLY_MARKET_ADVICE"
                )
                .order(
                    "created_at",
                    desc=False
                )
                .limit(
                    safe_limit
                )
                .execute()
            )
        )

        observations = (
            response.data
            if (
                response
                and response.data
            )
            else []
        )

        # ================================================================
        # UNA SEÑAL = PRIMERA OPINIÓN IA
        # ================================================================
        #
        # La IA no puede cambiar de opinión después y elegir
        # retrospectivamente la respuesta que quedó mejor.
        # ================================================================

        first_by_signal = {}

        for row in observations:

            if not isinstance(
                row,
                dict
            ):
                continue

            raw_id = str(
                row.get(
                    "source_signal_id"
                )
                or ""
            ).strip()

            if not raw_id:
                continue

            try:
                signal_id = str(
                    _uuid.UUID(
                        raw_id
                    )
                )

            except Exception:
                continue

            if (
                signal_id
                not in first_by_signal
            ):
                first_by_signal[
                    signal_id
                ] = row

        source_ids = list(
            first_by_signal.keys()
        )

        if not source_ids:
            result[
                "status"
            ] = "COLLECTING_EVIDENCE"

            result[
                "reason"
            ] = (
                "Todavía no existen observaciones "
                "Spot IA vinculadas a señales."
            )

            return result

        # ================================================================
        # BATCHES
        # ================================================================

        def _chunks(
            values,
            size=100
        ):

            for start in range(
                0,
                len(values),
                size
            ):

                yield values[
                    start:
                    start + size
                ]

        # ================================================================
        # RESULTADOS REALES DE REVIEWTRADER
        # ================================================================

        results_by_signal = {}

        for batch in _chunks(
            source_ids
        ):

            response = db._with_retry(
                lambda batch=batch: (
                    db.client
                    .table(
                        "signal_results"
                    )
                    .select(
                        (
                            "signal_id,"
                            "status,"
                            "pnl_pct,"
                            "created_at"
                        )
                    )
                    .in_(
                        "signal_id",
                        batch
                    )
                    .order(
                        "created_at",
                        desc=False
                    )
                    .execute()
                )
            )

            for row in (
                response.data
                if (
                    response
                    and response.data
                )
                else []
            ):

                if not isinstance(
                    row,
                    dict
                ):
                    continue

                sid = str(
                    row.get(
                        "signal_id"
                    )
                    or ""
                )

                if sid:
                    results_by_signal[
                        sid
                    ] = row

        # ================================================================
        # HELPERS
        # ================================================================

        def _number(
            value
        ):
            try:
                if value is None:
                    return None

                return float(
                    value
                )

            except (
                TypeError,
                ValueError
            ):
                return None


        def _portfolio_from_context(
            observation
        ):
            """
            Recupera exactamente el portfolio porcentual
            que la IA vio en ese momento.
            """

            context = (
                observation.get(
                    "context_snapshot"
                )
                or {}
            )

            if not isinstance(
                context,
                dict
            ):
                return {}

            portfolio = (
                context.get(
                    "portfolio_percentages"
                )
                or {}
            )

            if not portfolio:

                hourly = (
                    context.get(
                        "hourly_market_snapshot"
                    )
                    or {}
                )

                if isinstance(
                    hourly,
                    dict
                ):
                    portfolio = (
                        hourly.get(
                            "portfolio_percentages"
                        )
                        or {}
                    )

            return (
                portfolio
                if isinstance(
                    portfolio,
                    dict
                )
                else {}
            )


        def _normalize_pct(
            value
        ):
            """
            Normaliza 0..100.

            Tolera también 0..1 por seguridad.
            """

            number = _number(
                value
            )

            if number is None:
                return None

            if (
                0.0
                <= number
                <= 1.0
            ):
                number *= 100.0

            if not (
                0.0
                <= number
                <= 100.0
            ):
                return None

            return number

        # ================================================================
        # CRUCE:
        #
        # IA
        # +
        # RESULTADO REAL
        # +
        # PORTFOLIO DEL MOMENTO
        # ================================================================

        rows = []

        for (
            signal_id,
            observation
        ) in first_by_signal.items():

            signal_result = (
                results_by_signal.get(
                    signal_id
                )
            )

            if not signal_result:
                continue

            status = str(
                signal_result.get(
                    "status"
                )
                or ""
            ).lower()

            if status not in (
                "tp_hit",
                "sl_hit",
                "expired"
            ):
                continue

            try:
                pnl_pct = float(
                    signal_result.get(
                        "pnl_pct"
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            verdict = str(
                observation.get(
                    "ai_verdict"
                )
                or ""
            ).upper()

            try:
                confidence = int(
                    float(
                        observation.get(
                            "ai_confidence"
                        )
                        or 0
                    )
                )

            except (
                TypeError,
                ValueError
            ):
                confidence = 0

            # ============================================================
            # MISMA REGLA 36S.2B.1
            # ============================================================

            would_block = bool(
                verdict == "DISAGREE"
                and confidence >= 80
            )

            portfolio = (
                _portfolio_from_context(
                    observation
                )
            )

            btc_pct = _normalize_pct(
                portfolio.get(
                    "BTC_pct"
                )
            )

            paxg_pct = _normalize_pct(
                portfolio.get(
                    "PAXG_pct"
                )
            )

            usdt_pct = _normalize_pct(
                portfolio.get(
                    "USDT_pct"
                )
            )

            context_available = all(
                value is not None
                for value in (
                    btc_pct,
                    paxg_pct,
                    usdt_pct
                )
            )

            reserve_stress = False
            concentrated = False

            if context_available:

                reserve_stress = bool(
                    btc_pct
                    < reserve_btc

                    or paxg_pct
                    < reserve_paxg

                    or usdt_pct
                    < reserve_usdt
                )

                concentrated = bool(
                    max(
                        btc_pct,
                        paxg_pct,
                        usdt_pct
                    )
                    >= max_concentration
                )

            rows.append({

                "signal_id":
                    signal_id,

                "created_at":
                    str(
                        observation.get(
                            "created_at"
                        )
                        or ""
                    ),

                "system_action":
                    str(
                        observation.get(
                            "system_action"
                        )
                        or ""
                    ).upper(),

                "ai_verdict":
                    verdict,

                "ai_confidence":
                    confidence,

                "would_block":
                    would_block,

                "status":
                    status,

                "system_pnl_pct":
                    pnl_pct,

                # ========================================================
                # CONTRAFACTUAL DIRECCIONAL
                # ========================================================
                #
                # Si la señal perdió -2% y la IA la habría bloqueado:
                #
                # valor del bloqueo = +2%
                #
                # Si ganó +3%:
                #
                # valor del bloqueo = -3%
                # ========================================================

                "block_value_pct":
                    (
                        -pnl_pct
                        if would_block
                        else None
                    ),

                "portfolio_context_available":
                    context_available,

                "BTC_pct":
                    (
                        round(
                            btc_pct,
                            2
                        )
                        if btc_pct is not None
                        else None
                    ),

                "PAXG_pct":
                    (
                        round(
                            paxg_pct,
                            2
                        )
                        if paxg_pct is not None
                        else None
                    ),

                "USDT_pct":
                    (
                        round(
                            usdt_pct,
                            2
                        )
                        if usdt_pct is not None
                        else None
                    ),

                "reserve_stress":
                    reserve_stress,

                "concentrated":
                    concentrated
            })

        rows.sort(
            key=lambda item:
                item[
                    "created_at"
                ]
        )

        # ================================================================
        # RESUMEN
        # ================================================================

        def _summary(
            subset
        ):

            resolved = len(
                subset
            )

            with_context = [

                row
                for row in subset

                if row[
                    "portfolio_context_available"
                ]
            ]

            blocks = [

                row
                for row in subset

                if row[
                    "would_block"
                ]
            ]

            blocks_with_context = [

                row
                for row in blocks

                if row[
                    "portfolio_context_available"
                ]
            ]

            block_values = [

                float(
                    row[
                        "block_value_pct"
                    ]
                )

                for row in blocks

                if row[
                    "block_value_pct"
                ]
                is not None
            ]

            return {
                "resolved":
                    resolved,

                "resolved_with_context":
                    len(
                        with_context
                    ),

                "context_coverage_pct":
                    (
                        round(
                            (
                                len(
                                    with_context
                                )
                                / resolved
                                * 100.0
                            ),
                            2
                        )

                        if resolved
                        else None
                    ),

                "would_block_resolved":
                    len(
                        blocks
                    ),

                "would_block_with_context":
                    len(
                        blocks_with_context
                    ),

                "would_block_context_coverage_pct":
                    (
                        round(
                            (
                                len(
                                    blocks_with_context
                                )
                                / len(
                                    blocks
                                )
                                * 100.0
                            ),
                            2
                        )

                        if blocks
                        else None
                    ),

                "gross_block_value_pct_sum":
                    round(
                        sum(
                            block_values
                        ),
                        4
                    ),

                "reserve_stress_resolved":
                    sum(
                        1
                        for row
                        in with_context

                        if row[
                            "reserve_stress"
                        ]
                    ),

                "concentration_resolved":
                    sum(
                        1
                        for row
                        in with_context

                        if row[
                            "concentrated"
                        ]
                    ),

                "would_block_under_reserve_stress":
                    sum(
                        1
                        for row
                        in blocks_with_context

                        if row[
                            "reserve_stress"
                        ]
                    ),

                "would_block_under_concentration":
                    sum(
                        1
                        for row
                        in blocks_with_context

                        if row[
                            "concentrated"
                        ]
                    )
            }

        total = _summary(
            rows
        )

        # ================================================================
        # WALK-FORWARD 70 / 30
        # ================================================================

        split_index = int(
            len(
                rows
            )
            * 0.70
        )

        calibration_rows = (
            rows[
                :split_index
            ]
        )

        validation_rows = (
            rows[
                split_index:
            ]
        )

        calibration = _summary(
            calibration_rows
        )

        validation = _summary(
            validation_rows
        )

        result[
            "portfolio_policy"
        ].update({

            "resolved_with_context":
                total[
                    "resolved_with_context"
                ],

            "would_block_with_context":
                total[
                    "would_block_with_context"
                ],

            "context_coverage_pct":
                total[
                    "context_coverage_pct"
                ],

            "would_block_context_coverage_pct":
                total[
                    "would_block_context_coverage_pct"
                ],

            "reserve_stress_resolved":
                total[
                    "reserve_stress_resolved"
                ],

            "concentration_resolved":
                total[
                    "concentration_resolved"
                ],

            "would_block_under_reserve_stress":
                total[
                    "would_block_under_reserve_stress"
                ],

            "would_block_under_concentration":
                total[
                    "would_block_under_concentration"
                ]
        })

        result[
            "calibration_70"
        ] = calibration

        result[
            "validation_30"
        ] = validation

        # ================================================================
        # GATE FINAL 36T
        # ================================================================

        base_gate = (
            base.get(
                "gate"
            )
            or {}
        )

        gate = (
            result[
                "gate"
            ]
        )

        gate[
            "signal_sample_ok"
        ] = bool(
            base_gate.get(
                "sample_ok"
            )
        )

        gate[
            "block_sample_ok"
        ] = bool(
            base_gate.get(
                "block_sample_ok"
            )
        )

        gate[
            "validation_ok"
        ] = bool(
            base_gate.get(
                "validation_ok"
            )
        )

        gate[
            "validation_block_sample_ok"
        ] = bool(
            base_gate.get(
                "validation_block_sample_ok"
            )
        )

        gate[
            "gross_value_positive"
        ] = bool(
            base_gate.get(
                "gross_value_positive"
            )
        )

        gate[
            "validation_gross_value_positive"
        ] = bool(
            base_gate.get(
                "validation_gross_value_positive"
            )
        )

        total_coverage = (
            total.get(
                "context_coverage_pct"
            )
        )

        validation_coverage = (
            validation.get(
                "context_coverage_pct"
            )
        )

        # Exigimos que al menos 80% de las observaciones
        # resueltas tengan portfolio conocido.

        gate[
            "portfolio_context_coverage_ok"
        ] = bool(
            total_coverage is not None
            and total_coverage >= 80.0
        )

        gate[
            "validation_portfolio_context_ok"
        ] = bool(
            validation_coverage is not None
            and validation_coverage >= 80.0
        )

        # ================================================================
        # NO INVENTAR CONTRAFACTUAL NI COSTES
        # ================================================================
        #
        # Ya podemos demostrar:
        #
        # - outcome Spot;
        # - valor bruto de WOULD_BLOCK;
        # - composición BTC/PAXG/USDT;
        # - reservas;
        # - concentración;
        # - validación 70/30.
        #
        # Todavía NO sabemos una ejecución TGP real completa ni:
        #
        # - comisión;
        # - spread;
        # - slippage;
        # - coste de rotación.
        #
        # Por eso estos dos gates siguen FALSE.
        # ================================================================

        gate[
            "portfolio_counterfactual_verified"
        ] = False

        gate[
            "costs_verified"
        ] = False

        diagnostic_ready = all((

            gate[
                "signal_sample_ok"
            ],

            gate[
                "block_sample_ok"
            ],

            gate[
                "validation_ok"
            ],

            gate[
                "validation_block_sample_ok"
            ],

            gate[
                "gross_value_positive"
            ],

            gate[
                "validation_gross_value_positive"
            ],

            gate[
                "portfolio_context_coverage_ok"
            ],

            gate[
                "validation_portfolio_context_ok"
            ]
        ))

        # ================================================================
        # ESTADO
        # ================================================================

        if not diagnostic_ready:

            result[
                "status"
            ] = "COLLECTING_EVIDENCE"

            result[
                "reason"
            ] = (
                "36T continúa acumulando outcomes "
                "Spot y contexto de portfolio."
            )

        else:

            result[
                "status"
            ] = (
                "DIAGNOSTIC_READY_"
                "WAITING_NET_COUNTERFACTUAL"
            )

            result[
                "reason"
            ] = (
                "La evidencia direccional y de portfolio "
                "es suficiente para revisión diagnóstica, "
                "pero todavía faltan contrafactual de "
                "ejecución TGP y costes verificables."
            )

        # ================================================================
        # 36S.2B.2 SIGUE BLOQUEADO
        # ================================================================

        result[
            "ready_for_36S2B2_review"
        ] = False

        return result

    except Exception as error:

        # ================================================================
        # FAIL-OPEN ABSOLUTO
        # ================================================================

        logger.warning(
            "36T portfolio evidence: %s",
            error
        )

        result[
            "status"
        ] = "EVIDENCE_ERROR"

        result[
            "reason"
        ] = (
            "36T_ERROR: "
            + str(
                error
            )[:180]
        )

        return result
