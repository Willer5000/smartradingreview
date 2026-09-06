/* static/ai_assistant.js */
/* COMMIT 36R/36S — IA AISLADA DEL FRONTEND PRINCIPAL */

console.log(
    '🤖 AI Assistant JS 20260906-FIX3 cargado'
);

// ============================================================================
// COMMIT 36R
// ASISTENTE IA — SPOT + FUTURES
// ============================================================================

(function initAITradingAssistant() {

    const AUTO_REFRESH_MS =
        10 * 60 * 1000;


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


    function listHtml(
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

                <div class="small fw-bold ${css}">
                    ${esc(title)}
                </div>

                <ul class="small mb-1 ps-3">

                    ${
                        values
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


    // ========================================================================
    // CREAR VENTANA
    // ========================================================================

    function mount() {

        if (
            document.getElementById(
                'ai-trading-assistant-card'
            )
        ) {

            return true;
        }


        const card =
            document.createElement(
                'div'
            );


        card.id =
            'ai-trading-assistant-card';


        card.className =
            (
                'card bg-dark '
                + 'border-info mb-3'
            );


        // ================================================================
        // COMMIT 36R UX
        // La IA es una capa de apoyo.
        //
        // Debe verse claramente, pero NO competir visualmente con:
        // - Recomendación del Sistema;
        // - Guardian;
        // - gráficos.
        // ================================================================

        card.style.fontSize =
            '0.88rem';

        card.style.borderWidth =
            '1px';

        card.style.opacity =
            '0.96';


        card.innerHTML = `

            <div
                class="card-header bg-info bg-opacity-25 d-flex justify-content-between align-items-center py-1 px-2"
                style="min-height: 0;"
            >

                <strong
                    class="text-info mb-0"
                    style="
                        font-size: 0.84rem;
                        line-height: 1.1;
                        font-weight: 600;
                    "
                >
                    🧠 Asistente IA
                </strong>


                <div
                    class="d-flex align-items-center gap-1"
                    style="font-size: 0.68rem;"
                >

                    <span
                        id="ai-assistant-market"
                        class="badge bg-dark py-1 px-2"
                    >
                        ${market()}
                    </span>

                    <span
                        id="ai-assistant-quota"
                        class="badge bg-secondary py-1 px-2"
                    >
                        3/h
                    </span>

                </div>

            </div>


            <div
                class="card-body py-2 px-3"
                style="font-size: 0.84rem;"
            >

                <div
                    id="ai-assistant-state"
                    class="text-muted mb-1"
                    style="
                        font-size: 0.70rem;
                        line-height: 1.15;
                    "
                >
                    Preparando contexto...
                </div>


                <div
                    id="ai-assistant-answer"
                    class="border border-secondary rounded p-2 mb-2"
                    style="
                        font-size: 0.82rem;
                        line-height: 1.35;
                        background: rgba(255,255,255,0.015);
                    "
                >

                    <div class="text-muted small">
                        Inicia sesión y espera el primer
                        análisis del mercado.
                    </div>

                </div>


                <label
                    for="ai-assistant-question"
                    class="form-label small text-muted"
                >
                    Pregunta sobre señales, mercado,
                    oportunidades, riesgo, Guardian
                    o portafolio
                </label>


                <textarea
                    id="ai-assistant-question"
                    class="form-control form-control-sm bg-dark text-light border-secondary"
                    rows="2"
                    maxlength="800"
                    placeholder="Ej.: ¿Cuál de las señales actuales merece más atención según mi riesgo?"
                ></textarea>


                <div class="d-flex gap-2 mt-2">

                    <button
                        id="ai-assistant-ask"
                        type="button"
                        class="btn btn-sm btn-info flex-fill"
                    >
                        Preguntar
                    </button>


                    <button
                        id="ai-assistant-refresh"
                        type="button"
                        class="btn btn-sm btn-outline-info"
                    >
                        ↻ Consejo
                    </button>

                </div>


                <div class="small text-muted mt-2">

                    Máx. 3 preguntas por hora.

                    La IA aconseja y aprende;
                    no modifica Safety, votos,
                    Entry, SL, TP, leverage ni
                    Guardian automáticamente.

                </div>

            </div>
        `;


        // ================================================================
        // UBICACIÓN
        // ================================================================

        // ================================================================
        // UBICACIÓN 36R UX
        // ================================================================
        //
        // SPOT:
        //     Recomendación
        //     ↓
        //     Guardian TGP
        //     ↓
        //     Asistente IA
        //     ↓
        //     gráficos
        //
        // FUTURES:
        //     Recomendación
        //     ↓
        //     Asistente IA
        //     ↓
        //     resto del análisis
        //
        // El Asistente deja de vivir en la barra lateral.
        // ================================================================

        const anchor =
            window.IS_FUTURES_PAGE

                ? document.getElementById(
                    'recommendation-card'
                )

                : document.getElementById(
                    'tgp-banner'
                );


        if (
            anchor
            && anchor.parentNode
        ) {

            anchor.insertAdjacentElement(
                'afterend',
                card
            );

        } else {

            // ============================================================
            // FALLBACK
            //
            // Nunca volver al sidebar.
            // La IA debe permanecer en contenido principal.
            // ============================================================

            const mainContent =
                document.querySelector(
                    '.col-lg-7'
                );


            if (!mainContent) {

                console.warn(
                    '⚠️ Asistente IA: '
                    + 'no se encontró el contenido principal.'
                );

                return false;
            }


            mainContent.prepend(
                card
            );
        }


        document
            .getElementById(
                'ai-assistant-ask'
            )
            ?.addEventListener(
                'click',
                ask
            );


        document
            .getElementById(
                'ai-assistant-refresh'
            )
            ?.addEventListener(
                'click',
                () => loadAuto(
                    true
                )
            );


        return true;
    }


    // ========================================================================
    // CUOTA
    // ========================================================================

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


        const daily =
            quota.manual_daily
            || {};


        el.textContent =
            (
                `${hourly.remaining ?? '--'}`
                + `/`
                + `${hourly.limit ?? 3}`
                + ' esta hora · '
                + `${daily.remaining ?? '--'}`
                + ' hoy'
            );
    }


    // ========================================================================
    // RENDER RESPUESTA
    // ========================================================================

    function render(
        result,
        label = 'Consejo IA'
    ) {

        const state =
            document.getElementById(
                'ai-assistant-state'
            );


        const answer =
            document.getElementById(
                'ai-assistant-answer'
            );


        if (!answer) {

            return;
        }


        updateQuota(
            result?.quota
        );


        if (
            !result
            || result.success
            !== true
        ) {

            if (state) {

                state.textContent =
                    '';
            }


            const reason =
                (
                    result?.reason
                    || result?.error
                    || (
                        'IA temporalmente '
                        + 'no disponible.'
                    )
                );


            answer.innerHTML =
                (
                    '<div class="small text-warning">'
                    + esc(
                        reason
                    )
                    + '</div>'
                );


            return;
        }


        const data =
            result.data
            || {};


        const verdict =
            String(
                data.verdict
                || 'INFO'
            ).toUpperCase();


        // ================================================================
        // Traducción visual.
        //
        // El valor interno permanece en inglés porque forma parte
        // del contrato backend / estadísticas 36R-36S.
        // ================================================================

        const verdictLabel = {

            SUPPORT:
                'APOYA',

            CAUTION:
                'PRECAUCIÓN',

            DISAGREE:
                'DISCREPA',

            NO_EDGE:
                'SIN VENTAJA',

            INFO:
                'INFORMACIÓN'

        }[
            verdict
        ] || 'INFORMACIÓN';


        if (state) {

            const resolved =
                result.resolved_context
                || {};


            const shownMarket =
                resolved.market
                || market();


            const shownSymbol =
                resolved.symbol
                || symbol();


            const shownTimeframe =
                resolved.timeframe
                || timeframe();


            state.textContent =
                (
                    'Contexto · '
                    + `${shownMarket} · `
                    + `${
                        String(
                            shownSymbol
                        ).replace(
                            '-',
                            '/'
                        )
                    } · `
                    + `${shownTimeframe}`
                    + (
                        result.cached
                            ? ' · caché'
                            : ''
                    )
                );
        }


        answer.innerHTML = `

            <div
                class="d-flex flex-wrap justify-content-between gap-2 align-items-center"
            >

                <strong>
                    ${esc(
                        data.headline
                        || 'Consejo del asistente'
                    )}
                </strong>


                <span class="badge bg-${badge}">

                    ${esc(verdictLabel)}

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


            <div class="mt-2">
                ${esc(
                    data.advice
                    || ''
                )}
            </div>


            ${
                listHtml(
                    'Por qué',
                    data.why
                )
            }


            ${
                listHtml(
                    'Riesgos',
                    data.risks,
                    'text-warning'
                )
            }


            ${
                listHtml(
                    'Qué vigilar',
                    data.what_to_watch,
                    'text-info'
                )
            }


            ${
                listHtml(
                    'Hipótesis para mejorar el sistema',
                    data.learning_hypotheses,
                    'text-success'
                )
            }


            ${
                data.personal_risk_note

                    ? `
                        <div class="small mt-2">

                            <strong>
                                Tu riesgo:
                            </strong>

                            ${esc(
                                data.personal_risk_note
                            )}

                        </div>
                    `

                    : ''
            }


            ${
                data.portfolio_note

                    ? `
                        <div class="small mt-1">

                            <strong>
                                Tu portafolio:
                            </strong>

                            ${esc(
                                data.portfolio_note
                            )}

                        </div>
                    `

                    : ''
            }


            <div
                class="small text-muted border-top border-secondary mt-2 pt-2"
            >

                ${esc(
                    data.system_alignment
                    || ''
                )}

                <br>

                Autoridad:
                ADVISORY_ONLY

            </div>
        `;
    }

    // ========================================================================
    // COMMIT 36R-FIX3
    // LECTOR SEGURO DE RESPUESTAS API
    // ========================================================================
    //
    // Antes se hacía directamente response.json().
    //
    // Si Render respondía con HTML de un 502/503,
    // perdíamos el error real y sólo veíamos:
    //
    // "No se pudo consultar el Asistente IA."
    //
    // Ahora veremos el problema verdadero.
    // ========================================================================

    async function readApiJson(
        response
    ) {

        const text =
            await response.text();


        let json = null;


        try {

            json = (
                text
                    ? JSON.parse(
                        text
                    )
                    : {}
            );


        } catch (parseError) {

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
                    + 'el servidor no devolvió JSON'
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
    // CONSEJO AUTOMÁTICO
    // ========================================================================

    async function loadAuto(
        force = false
    ) {

        if (!mount()) {

            return;
        }


        if (
            !isLoggedIn
            || !currentUser
        ) {

            return;
        }


        const answer =
            document.getElementById(
                'ai-assistant-answer'
            );


        if (
            force
            && answer
        ) {

            answer.innerHTML =
                (
                    '<div class="small text-info">'
                    + '🧠 Analizando contexto actual...'
                    + '</div>'
                );
        }


        try {

            const params =
                new URLSearchParams({

                    market:
                        market(),

                    symbol:
                        symbol(),

                    timeframe:
                        timeframe()
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


            render(
                json,
                'Consejo automático'
            );


        } catch (error) {

            console.error(
                '❌ AI Advisor automático:',
                error
            );


            render({

                success:
                    false,

                reason:
                    (
                        error?.message
                        || (
                            'No se pudo consultar '
                            + 'el Asistente IA.'
                        )
                    )
            });
        }
    }


    // ========================================================================
    // PREGUNTA MANUAL
    // ========================================================================

    async function ask() {

        if (
            !isLoggedIn
            || !currentUser
        ) {

            render({

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


        const question =
            String(
                input?.value
                || ''
            ).trim();


        if (!question) {

            return;
        }


        const button =
            document.getElementById(
                'ai-assistant-ask'
            );


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


            render(
                json,
                'Respuesta a tu pregunta'
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
                '❌ AI Assistant pregunta:',
                error
            );


            render({

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

            if (button) {

                button.disabled =
                    false;
            }
        }
    }


    // ========================================================================
    // INICIALIZACIÓN
    // ========================================================================

    document.addEventListener(
        'DOMContentLoaded',
        () => {

            // Esperar autenticación + caches.

            setTimeout(
                () => {

                    if (!mount()) {

                        return;
                    }


                    loadAuto(
                        false
                    );

                },
                7000
            );


            // Si el usuario cambia símbolo o TF,
            // revisamos el nuevo contexto.

            document
                .getElementById(
                    'symbol-select'
                )
                ?.addEventListener(
                    'change',
                    () => {

                        setTimeout(
                            () => loadAuto(
                                false
                            ),
                            2500
                        );
                    }
                );


            document
                .getElementById(
                    'interval-select'
                )
                ?.addEventListener(
                    'change',
                    () => {

                        setTimeout(
                            () => loadAuto(
                                false
                            ),
                            2500
                        );
                    }
                );


            // La llamada real suele salir de caché.
            // No implica una llamada Groq cada 10 minutos.

            setInterval(
                () => loadAuto(
                    false
                ),
                AUTO_REFRESH_MS
            );
        }
    );

})();
