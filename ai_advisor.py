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
            "10"
        )
    )
)


# Límite diario por usuario.
#
# 10/h es el techo horario, pero mantenemos un
# presupuesto diario razonable para proteger
# el servicio gratuito y evitar abuso accidental.
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
# COMMIT 36S.2C
# GEMINI — LEARNING / RESEARCH SHADOW
# ============================================================================

GEMINI_LEARNING_ENABLED = (
    os.getenv(
        "GEMINI_LEARNING_ENABLED",
        "true"
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


def _resolve_ai_route(
    usage_type,
    context_type
):
    """
    Decide qué proveedor hace cada trabajo.

    GROQ:
        - Chat
        - Consejo
        - Futures Critic
        - Guardian

    GEMINI:
        - Learning / Research agregado

    Gemini nunca recibe autoridad operacional aquí.
    """

    usage_type = str(
        usage_type
        or ""
    ).upper()

    context_type = str(
        context_type
        or ""
    ).upper()

    if (
        usage_type == "LEARNING"
        and context_type == "LEARNING"
        and GEMINI_LEARNING_ENABLED
        and os.getenv(
            "GEMINI_API_KEY",
            ""
        ).strip()
    ):
        return (
            "GEMINI",
            GEMINI_LEARNING_MODEL
        )

    return (
        AI_PROVIDER,
        AI_MODEL
    )


def _gemini_learning_safe_context(
    context
):
    """
    El Learning de Gemini recibe contexto del SISTEMA,
    no información financiera personal innecesaria.

    Elimina cantidades monetarias exactas si aparecieran
    accidentalmente dentro del snapshot agregado.
    """

    sensitive_key_fragments = (
        "equity",
        "balance",
        "amount",
        "quantity",
        "investment_usdt",
        "margin_usdt",
        "pnl_usdt",
        "portfolio_value"
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
                    in sensitive_key_fragments
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


    # ================================================================
    # CONSEJO HORARIO
    # ================================================================
    #
    # Para HOURLY_MARKET_ADVICE el contrato real es:
    #
    #     1 usuario
    #     + 1 mercado
    #     + 1 hora
    #     = máximo 1 llamada real a Groq.
    #
    # _cache_get() ya filtra por usuario y context_type.
    #
    # Por eso aquí NO incluimos el contexto dinámico en el hash.
    # Si cambian señales/KPIs durante la misma hora, una recarga
    # del navegador reutiliza el consejo ya generado.
    #
    # Al cambiar hour_bucket, se genera automáticamente uno nuevo.
    # ================================================================

    if (
        normalized_context_type
        == "HOURLY_MARKET_ADVICE"
    ):

        hour_bucket = ""

        if isinstance(
            context,
            dict
        ):

            hour_bucket = str(
                context.get(
                    "hour_bucket"
                )
                or ""
            ).strip()


        raw = json.dumps(

            {
                "context_type":
                    normalized_context_type,

                "market":
                    str(
                        market
                        or ""
                    ).strip().upper(),

                "hour_bucket":
                    hour_bucket
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
    # Para señales, Guardian, Learning y chat seguimos usando
    # fingerprint contextual.
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
10. por qué merece ser probada.

Para FUTURES prioriza como fuentes de mejora:

- calidad Entry SMC;
- Liquidity -> Sweep -> MSS -> Displacement -> POI;
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

def _normalize_strategy_proposals(
    value
):
    """
    Convierte propuestas libres del LLM en hipótesis Shadow
    auditables.

    IMPORTANTE:
    una propuesta NO es una estrategia productiva.
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
                "market",
                "FUTURES"
            )
            or "FUTURES"
        ).upper()

        if market not in (
            "SPOT",
            "FUTURES",
            "BOTH"
        ):
            market = "FUTURES"

        try:
            min_samples = int(
                item.get(
                    "min_samples",
                    25
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

            "regime":
                _ai_clean_text(
                    item.get(
                        "regime"
                    ),
                    "ANY",
                    240
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
        _gemini_learning_safe_context(
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
      "why_test": ""
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
                "temperature":
                    0.15,

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
        "GEMINI"
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


    try:

        if (
            selected_provider
            == "GEMINI"
        ):
            advice, usage = (
                _call_gemini_learning(
                    context,
                    question
                )
            )

        else:
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
