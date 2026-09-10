(() => {

    'use strict';


    // ========================================================================
    // COMMIT 36Y — GEMINI TICKER AISLADO
    // ========================================================================
    //
    // REGLA DE SEGURIDAD:
    //
    // Este archivo NO conoce:
    //
    // - mount()
    // - loadHourlyAdvice()
    // - Chat IA
    // - Spot
    // - Futures
    //
    // Si este archivo falla por completo,
    // Consejo IA y Asistente IA siguen funcionando.
    // ========================================================================


    let loading =
        false;

    let items =
        [];

    let currentIndex =
        0;

    let rotationTimer =
        null;


    function tickerElement() {

        return document.getElementById(
            'gemini-activity-ticker'
        );
    }


    function messageElement() {

        return document.getElementById(
            'gemini-activity-message'
        );
    }


    function metaElement() {

        return document.getElementById(
            'gemini-activity-meta'
        );
    }


    function hideTicker() {

        const ticker =
            tickerElement();


        if (!ticker) {

            return;
        }


        ticker.classList.add(
            'd-none'
        );
    }


    function showTicker() {

        const ticker =
            tickerElement();


        if (!ticker) {

            return;
        }


        ticker.classList.remove(
            'd-none'
        );
    }


    function renderCurrentItem() {

        const element =
            messageElement();


        if (
            !element
            ||
            !items.length
        ) {

            return;
        }


        const text =
            String(
                items[
                    currentIndex
                    %
                    items.length
                ]
                || ''
            ).trim();


        if (!text) {

            return;
        }


        element.textContent =
            text;
    }


    function startRotation() {

        if (rotationTimer) {

            clearInterval(
                rotationTimer
            );

            rotationTimer =
                null;
        }


        currentIndex =
            0;


        renderCurrentItem();


        if (
            items.length
            <= 1
        ) {

            return;
        }


        rotationTimer =
            setInterval(
                () => {

                    currentIndex = (
                        currentIndex
                        + 1
                    )
                    %
                    items.length;


                    renderCurrentItem();
                },
                9000
            );
    }


    function stateLabel(
        value
    ) {

        const state =
            String(
                value
                || ''
            ).toUpperCase();


        const labels = {

            WORKING:
                'activo',

            WAITING_FIRST_RUN:
                'esperando ciclo',

            ERROR_FALLBACK:
                'fallback Groq',

            NOT_CONFIGURED:
                'sin configurar',

            DISABLED:
                'deshabilitado',

            DB_UNAVAILABLE:
                'sin historial',

            STATUS_ERROR:
                'estado no disponible'
        };


        return (
            labels[
                state
            ]
            ||
            state.toLowerCase()
            ||
            'sin estado'
        );
    }


    async function loadActivity() {

        if (loading) {

            return;
        }


        // Si el HTML no contiene el cintillo,
        // terminamos sin tocar absolutamente nada.

        if (!tickerElement()) {

            return;
        }


        loading =
            true;


        try {

            const response =
                await fetch(
                    '/api/ai/gemini-activity',
                    {
                        method:
                            'GET',

                        cache:
                            'no-store',

                        credentials:
                            'same-origin'
                    }
                );


            // Usuario todavía no autenticado.
            //
            // No mostramos nada y tampoco generamos error.

            if (
                response.status
                === 401
            ) {

                hideTicker();

                return;
            }


            if (!response.ok) {

                hideTicker();

                return;
            }


            const payload =
                await response.json();


            const data = (
                payload
                &&
                payload.data
                &&
                typeof payload.data
                === 'object'
            )
                ? payload.data
                : {};


            const rawItems =
                Array.isArray(
                    data.ticker_items
                )
                    ? data.ticker_items
                    : [];


            items =
                rawItems
                .map(
                    value =>
                        String(
                            value
                            || ''
                        ).trim()
                )
                .filter(
                    Boolean
                )
                .slice(
                    0,
                    4
                );


            if (!items.length) {

                // No inventamos actividad.
                //
                // Si el backend todavía no tiene información,
                // simplemente ocultamos el cintillo.

                hideTicker();

                return;
            }


            const meta =
                metaElement();


            if (meta) {

                const lastRun = (
                    data.last_run
                    &&
                    typeof data.last_run
                    === 'object'
                )
                    ? data.last_run
                    : {};


                const model =
                    String(
                        data.provider_label
                        ||
                        data.model
                        ||
                        lastRun.model
                        ||
                        'Aprendizaje IA'
                    );


                meta.textContent =
                    (
                        model
                        + ' · '
                        + stateLabel(
                            data.state
                        )
                    );
            }


            showTicker();

            startRotation();

        }

        catch (error) {

            // ================================================================
            // FAIL-SILENT
            // ================================================================
            //
            // El cintillo es puramente informativo.
            //
            // NO propagamos el error.
            // NO tocamos otros módulos.
            // ================================================================

            hideTicker();

            console.debug(
                'Ticker de aprendizaje IA no disponible:',
                error
            );

        }

        finally {

            loading =
                false;
        }
    }


    function start() {

        // Primer intento después de que login/UI
        // hayan tenido tiempo de inicializar.

        setTimeout(
            loadActivity,
            10000
        );


        // Segundo intento si el usuario estaba
        // terminando de iniciar sesión.

        setTimeout(
            loadActivity,
            30000
        );


        // Refrescar sólo el estado persistido.
        //
        // NO llama directamente al proveedor IA.

        setInterval(
            loadActivity,
            5 * 60 * 1000
        );
    }


    if (
        document.readyState
        === 'loading'
    ) {

        document.addEventListener(
            'DOMContentLoaded',
            start,
            {
                once:
                    true
            }
        );

    } else {

        start();
    }

})();
