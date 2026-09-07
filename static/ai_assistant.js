/* static/ai_assistant.js */
/* COMMIT 36R UX4 — CONSEJO HORARIO + CHAT MINIMIZADO */

console.log(
    '🤖 AI Assistant JS 20260906-UX5 cargado'
);

(function initAITradingAssistant() {

    'use strict';


    let lastAdviceHourKey =
        null;

    let adviceLoading =
        false;

    let chatLoading =
        false;


    function esc(value) {

        return String(
            value ?? ''
        )
            .replace(
                /&/g,
                '&amp;'
            )
            .replace(
                /</g,
                '&lt;'
            )
            .replace(
                />/g,
                '&gt;'
            )
            .replace(
                /"/g,
                '&quot;'
            )
            .replace(
                /'/g,
                '&#039;'
            );
    }


    function market() {

        return window.IS_FUTURES_PAGE
            ? 'FUTURES'
            : 'SPOT';
    }


    function symbol() {

        return (

            window.currentSymbol

            || document
                .getElementById(
                    'symbol-select'
                )
                ?.value

            || 'BTC-USDT'
        );
    }


    function timeframe() {

        return (

            window.currentInterval

            || document
                .getElementById(
                    'interval-select'
                )
                ?.value

            || (
                window.IS_FUTURES_PAGE
                    ? '1h'
                    : '1D'
            )
        );
    }


    function loggedIn() {

        if (
            typeof isLoggedIn
            !== 'undefined'
        ) {

            return Boolean(
                isLoggedIn
            );
        }


        return Boolean(
            window.isLoggedIn
        );
    }


    function currentHourKey() {

        const now =
            new Date();

        const halfHour =
            now.getMinutes() < 30
                ? '00'
                : '30';

        return [

            market(),

            now.getFullYear(),

            String(
                now.getMonth() + 1
            ).padStart(
                2,
                '0'
            ),

            String(
                now.getDate()
            ).padStart(
                2,
                '0'
            ),

            String(
                now.getHours()
            ).padStart(
                2,
                '0'
            ),

            halfHour

        ].join(
            '|'
        );
    }


    function verdictMeta(
        verdictRaw
    ) {

        const verdict =
            String(
                verdictRaw
                || 'INFO'
            ).toUpperCase();


        const map = {

            SUPPORT: {
                label:
                    'APOYA',

                css:
                    'success'
            },

            CAUTION: {
                label:
                    'PRECAUCIÓN',

                css:
                    'warning text-dark'
            },

            DISAGREE: {
                label:
                    'DISCREPA',

                css:
                    'danger'
            },

            NO_EDGE: {
                label:
                    'SIN VENTAJA',

                css:
                    'secondary'
            },

            INFO: {
                label:
                    'INFORMACIÓN',

                css:
                    'info text-dark'
            }
        };


        return (
            map[
                verdict
            ]
            || map.INFO
        );
    }


    function compactList(
        title,
        values,
        css = 'text-light'
    ) {

        if (
            !Array.isArray(
                values
            )
            || values.length === 0
        ) {

            return '';
        }


        return `
            <div class="mt-2">

                <div
                    class="fw-semibold ${css}"
                    style="font-size: 0.76rem;"
                >
                    ${esc(title)}
                </div>

                <ul
                    class="mb-0 ps-3"
                    style="
                        font-size: 0.76rem;
                        line-height: 1.3;
                    "
                >
                    ${
                        values
                            .slice(
                                0,
                                4
                            )
                            .map(
                                item =>
                                    `<li>${esc(item)}</li>`
                            )
                            .join('')
                    }
                </ul>

            </div>
        `;
    }


    function getAnchor() {

        return window.IS_FUTURES_PAGE

            ? document.getElementById(
                'recommendation-card'
            )

            : document.getElementById(
                'tgp-banner'
            );
    }


    // ========================================================================
    // CREAR LAS DOS VENTANAS
    // ========================================================================

    function mount() {

        if (
            document.getElementById(
                'ai-hourly-advice-card'
            )
            &&
            document.getElementById(
                'ai-trading-assistant-card'
            )
        ) {

            return true;
        }


        const anchor =
            getAnchor();


        if (
            !anchor
            || !anchor.parentNode
        ) {

            console.warn(
                '⚠️ IA: no se encontró '
                + 'el ancla principal.'
            );

            return false;
        }


        // ================================================================
        // CONSEJO IA
        // ================================================================

        const adviceCard =
            document.createElement(
                'div'
            );


        adviceCard.id =
            'ai-hourly-advice-card';


        adviceCard.className =
            (
                'card bg-dark '
                + 'border-info mb-3'
            );


        adviceCard.style.fontSize =
            '0.82rem';


        adviceCard.innerHTML = `

            <div
                id="ai-advice-toggle"
                class="card-header bg-info bg-opacity-10 d-flex justify-content-between align-items-center py-1 px-2"
                role="button"
                tabindex="0"
                aria-expanded="false"
                style="
                    cursor: pointer;
                    min-height: 0;
                "
            >

                <strong
                    class="text-info"
                    style="
                        font-size: 0.84rem;
                        line-height: 1.1;
                    "
                >
                    🧠 Consejo IA
                </strong>


                <div
                    class="d-flex align-items-center gap-2"
                >

                    <span
                        class="badge bg-dark"
                        style="font-size: 0.64rem;"
                    >
                        ${market()}
                    </span>


                    <span
                        id="ai-advice-hour"
                        class="text-muted"
                        style="font-size: 0.66rem;"
                    >
                        --:--
                    </span>


                    <i
                        id="ai-advice-chevron"
                        class="fas fa-chevron-down text-muted"
                        style="font-size: 0.68rem;"
                    ></i>

                </div>

            </div>


            <div
                id="ai-advice-body"
                class="card-body py-2 px-2"
                style="
                    display: none;
                    font-size: 0.80rem;
                    line-height: 1.35;
                "
            >

                <div
                    id="ai-hourly-advice-state"
                    class="text-muted"
                    style="font-size: 0.68rem;"
                >
                    Preparando evaluación horaria
                    del sistema...
                </div>


                <div
                    id="ai-hourly-advice-answer"
                    class="mt-1"
                >

                    <span class="text-muted">
                        El consejo se genera
                        automáticamente cada 30 minutos.
                    </span>

                </div>

            </div>
        `;

        // ================================================================
        // CHAT IA
        // ================================================================

        const chatCard =
            document.createElement(
                'div'
            );


        chatCard.id =
            'ai-trading-assistant-card';


        chatCard.className =
            (
                'card bg-dark '
                + 'border-secondary mb-3'
            );


        chatCard.style.fontSize =
            '0.80rem';


        chatCard.innerHTML = `

            <div
                id="ai-chat-toggle"
                class="card-header d-flex justify-content-between align-items-center py-1 px-2"
                role="button"
                tabindex="0"
                aria-expanded="false"
                style="
                    cursor: pointer;
                    min-height: 0;
                "
            >

                <div
                    class="d-flex align-items-center gap-2"
                >

                    <strong
                        class="text-light"
                        style="
                            font-size: 0.82rem;
                            line-height: 1.1;
                        "
                    >
                        💬 Asistente IA
                    </strong>


                    <span
                        id="ai-assistant-quota"
                        class="badge bg-secondary"
                        style="font-size: 0.62rem;"
                    >
                        10/h
                    </span>

                </div>


                <i
                    id="ai-chat-chevron"
                    class="fas fa-chevron-down text-muted"
                    style="font-size: 0.68rem;"
                ></i>

            </div>


            <div
                id="ai-chat-body"
                class="card-body py-2 px-2"
                style="
                    display: none;
                    font-size: 0.80rem;
                "
            >

                <div
                    id="ai-chat-answer"
                    class="mb-2"
                    style="display: none;"
                ></div>


                <div
                    class="input-group input-group-sm align-items-end"
                >

                    <textarea
                        id="ai-assistant-question"
                        class="form-control bg-dark text-light border-secondary"
                        rows="1"
                        maxlength="800"
                        placeholder="Pregunta sobre señales, riesgo, Guardian, portafolio u oportunidades..."
                        style="
                            resize: none;
                            min-height: 34px;
                            max-height: 88px;
                            font-size: 0.78rem;
                        "
                    ></textarea>


                    <button
                        id="ai-assistant-ask"
                        type="button"
                        class="btn btn-outline-info"
                        title="Enviar"
                        aria-label="Enviar pregunta"
                        style="
                            width: 38px;
                            min-width: 38px;
                            height: 34px;
                            padding: 0;
                        "
                    >
                        <i
                            class="fas fa-arrow-right"
                        ></i>
                    </button>

                </div>


                <div
                    class="text-muted mt-1"
                    style="font-size: 0.66rem;"
                >
                    Máx. 3 preguntas por hora.
                    Enter envía · Shift+Enter agrega una línea.
                </div>

            </div>
        `;


        // ================================================================
        // UBICACIÓN
        // ================================================================
        //
        // SPOT:
        // Guardian -> Consejo -> Chat -> gráficos
        //
        // FUTURES:
        // Recomendación -> Consejo -> Chat
        // ================================================================

        anchor.insertAdjacentElement(
            'afterend',
            adviceCard
        );


        adviceCard.insertAdjacentElement(
            'afterend',
            chatCard
        );

        const adviceToggle =
            document.getElementById(
                'ai-advice-toggle'
            );


        adviceToggle?.addEventListener(
            'click',
            () => toggleAdvice()
        );


        adviceToggle?.addEventListener(
            'keydown',
            event => {

                if (
                    event.key === 'Enter'
                    || event.key === ' '
                ) {

                    event.preventDefault();

                    toggleAdvice();
                }
            }
        );
        
        const toggle =
            document.getElementById(
                'ai-chat-toggle'
            );


        const input =
            document.getElementById(
                'ai-assistant-question'
            );


        const send =
            document.getElementById(
                'ai-assistant-ask'
            );


        toggle?.addEventListener(
            'click',
            () => toggleChat()
        );


        toggle?.addEventListener(
            'keydown',
            event => {

                if (
                    event.key === 'Enter'
                    || event.key === ' '
                ) {

                    event.preventDefault();

                    toggleChat();
                }
            }
        );


        send?.addEventListener(
            'click',
            ask
        );


        input?.addEventListener(
            'keydown',
            event => {

                if (
                    event.key === 'Enter'
                    && !event.shiftKey
                ) {

                    event.preventDefault();

                    ask();
                }
            }
        );


        return true;
    }


    // ========================================================================
    // MINIMIZAR / ABRIR CHAT
    // ========================================================================
    function toggleAdvice(
        forceOpen = null
    ) {

        const body =
            document.getElementById(
                'ai-advice-body'
            );


        const toggle =
            document.getElementById(
                'ai-advice-toggle'
            );


        const chevron =
            document.getElementById(
                'ai-advice-chevron'
            );


        if (!body) {

            return;
        }


        const currentlyOpen =
            body.style.display
            !== 'none';


        const shouldOpen =
            forceOpen === null

                ? !currentlyOpen

                : Boolean(
                    forceOpen
                );


        body.style.display =
            shouldOpen

                ? 'block'

                : 'none';


        toggle?.setAttribute(
            'aria-expanded',

            shouldOpen
                ? 'true'
                : 'false'
        );


        if (chevron) {

            chevron.className =

                shouldOpen

                    ? (
                        'fas fa-chevron-up '
                        + 'text-muted'
                    )

                    : (
                        'fas fa-chevron-down '
                        + 'text-muted'
                    );
        }
    }
    
    function toggleChat(
        forceOpen = null
    ) {

        const body =
            document.getElementById(
                'ai-chat-body'
            );


        const toggle =
            document.getElementById(
                'ai-chat-toggle'
            );


        const chevron =
            document.getElementById(
                'ai-chat-chevron'
            );


        if (!body) {

            return;
        }


        const currentlyOpen =
            body.style.display !== 'none';


        const shouldOpen =
            forceOpen === null

                ? !currentlyOpen

                : Boolean(
                    forceOpen
                );


        body.style.display =
            shouldOpen
                ? 'block'
                : 'none';


        toggle?.setAttribute(
            'aria-expanded',
            shouldOpen
                ? 'true'
                : 'false'
        );


        if (chevron) {

            chevron.className =
                shouldOpen

                    ? (
                        'fas fa-chevron-up '
                        + 'text-muted'
                    )

                    : (
                        'fas fa-chevron-down '
                        + 'text-muted'
                    );
        }


        if (shouldOpen) {

            setTimeout(
                () =>
                    document
                        .getElementById(
                            'ai-assistant-question'
                        )
                        ?.focus(),
                50
            );
        }
    }


    function updateQuota(
        quota
    ) {

        const el =
            document.getElementById(
                'ai-assistant-quota'
            );


        if (
            !el
            || !quota
        ) {

            return;
        }


        const hourly =
            quota.manual_hourly
            || {};


        el.textContent =
            (
                `${hourly.remaining ?? '--'}`
                + '/'
                + `${hourly.limit ?? 10}`
            );


        el.title =
            (
                'Preguntas disponibles '
                + 'esta hora'
            );
    }


    // ========================================================================
    // API
    // ========================================================================

    async function readApiJson(
        response
    ) {

        const text =
            await response.text();


        let json;


        try {

            json = text

                ? JSON.parse(
                    text
                )

                : {};


        } catch (error) {

            const preview =
                String(
                    text
                    || ''
                )
                    .replace(
                        /\s+/g,
                        ' '
                    )
                    .trim()
                    .slice(
                        0,
                        160
                    );


            throw new Error(
                (
                    `HTTP ${response.status}: `
                    + 'respuesta no JSON'
                    + (
                        preview
                            ? ` · ${preview}`
                            : ''
                    )
                )
            );
        }


        if (!response.ok) {

            throw new Error(
                (
                    json?.reason
                    || json?.error
                    || `HTTP ${response.status}`
                )
            );
        }


        return json;
    }


    // ========================================================================
    // DIBUJAR CONSEJO
    // ========================================================================

    function renderHourlyAdvice(
        result
    ) {

        const state =
            document.getElementById(
                'ai-hourly-advice-state'
            );


        const answer =
            document.getElementById(
                'ai-hourly-advice-answer'
            );


        const hour =
            document.getElementById(
                'ai-advice-hour'
            );


        if (!answer) {

            return;
        }


        updateQuota(
            result?.quota
        );


        if (
            !result
            || result.success !== true
        ) {

            if (state) {

                state.textContent =
                    'Consejo horario no disponible';
            }


            answer.innerHTML =
                (
                    '<div class="text-warning">'
                    + esc(
                        result?.reason
                        || result?.error
                        || (
                            'La IA no pudo evaluar '
                            + 'el contexto actual.'
                        )
                    )
                    + '</div>'
                );


            return;
        }


        const data =
            result.data
            || {};


        const meta =
            verdictMeta(
                data.verdict
            );


        const resolved =
            result.resolved_context
            || {};


        if (state) {

            const focus =
                resolved.focus_symbol

                    ? (
                        ' · foco '
                        + String(
                            resolved.focus_symbol
                        ).replace(
                            '-',
                            '/'
                        )
                        + (
                            resolved.focus_timeframe
                                ? ` ${resolved.focus_timeframe}`
                                : ''
                        )
                    )

                    : '';


            state.textContent =
                (
                    'Evaluación 30 min · '
                    + (
                        resolved.market
                        || market()
                    )
                    + focus
                    + (
                        result.cached
                            ? ' · caché 30 min'
                            : ''
                    )
                );
        }


        if (hour) {

            const generated =
                resolved.generated_at

                    ? new Date(
                        resolved.generated_at
                    )

                    : new Date();


            hour.textContent =
                generated.toLocaleTimeString(
                    [],
                    {
                        hour:
                            '2-digit',

                        minute:
                            '2-digit'
                    }
                );
        }


        answer.innerHTML = `

            <div
                class="d-flex flex-wrap justify-content-between align-items-center gap-2"
            >

                <strong
                    style="font-size: 0.82rem;"
                >
                    ${
                        esc(
                            data.headline
                            || 'Evaluación del mercado'
                        )
                    }
                </strong>


                <span
                    class="badge bg-${meta.css}"
                    style="font-size: 0.64rem;"
                >
                    ${esc(meta.label)}
                    ·
                    ${
                        Number(
                            data.confidence
                            || 0
                        ).toFixed(
                            0
                        )
                    }%
                </span>

            </div>


            <div class="mt-1">
                ${esc(
                    data.advice
                    || ''
                )}
            </div>


            ${
                compactList(
                    'Evidencia destacada',
                    data.why
                )
            }


            ${
                compactList(
                    'Riesgo / protección',
                    data.risks,
                    'text-warning'
                )
            }


            ${
                compactList(
                    'Qué vigilar',
                    data.what_to_watch,
                    'text-info'
                )
            }


            ${
                data.personal_risk_note

                    ? `
                        <div class="mt-2">
                            <strong>
                                Riesgo personal:
                            </strong>
                            ${
                                esc(
                                    data.personal_risk_note
                                )
                            }
                        </div>
                    `

                    : ''
            }


            ${
                data.portfolio_note

                    ? `
                        <div class="mt-1">
                            <strong>
                                Portafolio:
                            </strong>
                            ${
                                esc(
                                    data.portfolio_note
                                )
                            }
                        </div>
                    `

                    : ''
            }
        `;
    }


    // ========================================================================
    // DIBUJAR RESPUESTA CHAT
    // ========================================================================

    function renderChat(
        result
    ) {

        const answer =
            document.getElementById(
                'ai-chat-answer'
            );


        if (!answer) {

            return;
        }


        updateQuota(
            result?.quota
        );


        answer.style.display =
            'block';


        if (
            !result
            || result.success !== true
        ) {

            answer.innerHTML =
                (
                    '<div class="text-warning">'
                    + esc(
                        result?.reason
                        || result?.error
                        || (
                            'No se pudo responder '
                            + 'la pregunta.'
                        )
                    )
                    + '</div>'
                );


            return;
        }


        const data =
            result.data
            || {};


        const meta =
            verdictMeta(
                data.verdict
            );


        const resolved =
            result.resolved_context
            || {};


        const contextText = [

            resolved.market,

            resolved.symbol

                ? String(
                    resolved.symbol
                ).replace(
                    '-',
                    '/'
                )

                : null,

            resolved.timeframe

        ]
            .filter(
                Boolean
            )
            .join(
                ' · '
            );


        answer.innerHTML = `

            ${
                contextText

                    ? `
                        <div
                            class="text-muted mb-1"
                            style="font-size: 0.66rem;"
                        >
                            Contexto:
                            ${esc(contextText)}
                        </div>
                    `

                    : ''
            }


            <div
                class="d-flex justify-content-between align-items-center gap-2"
            >

                <strong
                    style="font-size: 0.80rem;"
                >
                    ${
                        esc(
                            data.headline
                            || 'Respuesta'
                        )
                    }
                </strong>


                <span
                    class="badge bg-${meta.css}"
                    style="font-size: 0.62rem;"
                >
                    ${esc(meta.label)}
                </span>

            </div>


            <div class="mt-1">
                ${esc(
                    data.advice
                    || ''
                )}
            </div>


            ${
                compactList(
                    'Por qué',
                    data.why
                )
            }


            ${
                compactList(
                    'Riesgos',
                    data.risks,
                    'text-warning'
                )
            }


            ${
                compactList(
                    'Qué vigilar',
                    data.what_to_watch,
                    'text-info'
                )
            }
        `;
    }


    // ========================================================================
    // CONSEJO AUTOMÁTICO
    // ========================================================================

    async function loadHourlyAdvice() {

        if (
            !mount()
            || adviceLoading
            || !loggedIn()
        ) {

            return;
        }


        const hourKey =
            currentHourKey();


        if (
            lastAdviceHourKey
            === hourKey
        ) {

            return;
        }


        adviceLoading =
            true;


        const answer =
            document.getElementById(
                'ai-hourly-advice-answer'
            );


        if (answer) {

            answer.innerHTML =
                (
                    '<span class="text-info">'
                    + '🧠 Evaluando señales, mercado, '
                    + 'riesgo y portafolio...'
                    + '</span>'
                );
        }


        try {

            const params =
                new URLSearchParams({

                    market:
                        market()
                });


            const response =
                await fetch(

                    (
                        '/api/ai/advice?'
                        + params.toString()
                    ),

                    {
                        credentials:
                            'same-origin',

                        cache:
                            'no-store'
                    }
                );


            const json =
                await readApiJson(
                    response
                );


            renderHourlyAdvice(
                json
            );


            if (json.success) {

                lastAdviceHourKey =
                    hourKey;
            }


        } catch (error) {

            console.error(
                '❌ Consejo IA horario:',
                error
            );


            renderHourlyAdvice({

                success:
                    false,

                reason:
                    (
                        error?.message
                        || (
                            'No se pudo generar '
                            + 'el consejo horario.'
                        )
                    )
            });


        } finally {

            adviceLoading =
                false;
        }
    }


    // ========================================================================
    // CHAT MANUAL
    // ========================================================================

    async function ask() {

        if (
            !mount()
            || chatLoading
        ) {

            return;
        }


        toggleChat(
            true
        );


        if (!loggedIn()) {

            renderChat({

                success:
                    false,

                reason:
                    (
                        'Debes iniciar sesión '
                        + 'para preguntar a la IA.'
                    )
            });


            return;
        }


        const input =
            document.getElementById(
                'ai-assistant-question'
            );


        const button =
            document.getElementById(
                'ai-assistant-ask'
            );


        const question =
            String(
                input?.value
                || ''
            ).trim();


        if (!question) {

            return;
        }


        chatLoading =
            true;


        if (button) {

            button.disabled =
                true;
        }


        try {

            const response =
                await fetch(

                    '/api/ai/ask',

                    {
                        method:
                            'POST',

                        credentials:
                            'same-origin',

                        headers: {
                            'Content-Type':
                                'application/json'
                        },

                        body:
                            JSON.stringify({

                                question:
                                    question,

                                market:
                                    market(),

                                symbol:
                                    symbol(),

                                timeframe:
                                    timeframe()
                            })
                    }
                );


            const json =
                await readApiJson(
                    response
                );


            renderChat(
                json
            );


            if (
                json.success
                && input
            ) {

                input.value =
                    '';
            }


        } catch (error) {

            console.error(
                '❌ Asistente IA pregunta:',
                error
            );


            renderChat({

                success:
                    false,

                reason:
                    (
                        error?.message
                        || (
                            'No se pudo enviar '
                            + 'la pregunta.'
                        )
                    )
            });


        } finally {

            chatLoading =
                false;


            if (button) {

                button.disabled =
                    false;
            }
        }
    }


    // ========================================================================
    // INICIO
    // ========================================================================

    document.addEventListener(
        'DOMContentLoaded',
        () => {

            // Esperar login + caches.
            setTimeout(
                () => {

                    if (mount()) {

                        loadHourlyAdvice();
                    }
                },
                7000
            );


            // Revisa una vez por minuto si cambió el bloque de 30 min.
            // NO llama a la IA otra vez dentro del mismo bloque.

            setInterval(
                () => {

                    if (
                        currentHourKey()
                        !== lastAdviceHourKey
                    ) {

                        loadHourlyAdvice();
                    }
                },
                60 * 1000
            );


            // Si el equipo estuvo suspendido,
            // comprobar al volver a la pestaña.

            document.addEventListener(
                'visibilitychange',
                () => {

                    if (
                        !document.hidden
                        &&
                        currentHourKey()
                        !== lastAdviceHourKey
                    ) {

                        loadHourlyAdvice();
                    }
                }
            );
        }
    );

})();
