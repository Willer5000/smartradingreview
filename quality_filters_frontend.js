/* Commit 23 — 10Q parallel quality frontend overlay.
 * Loaded before futures.js by the backend runtime hook.
 * It enriches the diagnostic candidates with the exact quality-filter authority
 * without changing trading decisions in the browser.
 */
(function () {
    'use strict';

    const VERSION = 'COMMIT23-10Q-FRONTEND-1';
    const FILTER_NAMES = {
        Q1: 'Coherencia direccional',
        Q2: 'Estructura / SMC',
        Q3: 'Alineación multitemporal',
        Q4: 'Estrategia / contexto',
        Q5: 'Flujo / volumen',
        Q6: 'Entrada / alcanzabilidad',
        Q7: 'Salida / geometría',
        Q8: 'Régimen / volatilidad',
        Q9: 'Evidencia / validación',
        Q10: 'Safety de ejecución'
    };

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = String(value ?? '');
        return div.innerHTML;
    }

    function traceOf(candidate) {
        return candidate?.quality_filter_trace
            || candidate?.parallel_quality_filters
            || {};
    }

    function qualitySummary(candidate) {
        const trace = traceOf(candidate);
        const scores = trace.filter_scores || {};
        const passed = new Set((trace.passed_filters || []).map(String));
        const selected = String(
            trace.selected_filter
            || candidate?.quality_filter_authority
            || 'NONE'
        ).toUpperCase();
        const selectedScore = Number(
            trace.selected_filter_score
            ?? candidate?.quality_filter_score
            ?? 0
        );
        const selectedName = String(
            trace.selected_filter_name
            || candidate?.quality_filter_name
            || FILTER_NAMES[selected]
            || ''
        );
        const confirmed = Boolean(
            trace.confirmed_one_of_ten
            ?? candidate?.quality_filter_confirmed
        );

        const chips = [];
        for (let i = 1; i <= 10; i += 1) {
            const key = `Q${i}`;
            const value = Number(scores[key]);
            if (!Number.isFinite(value)) continue;
            chips.push(
                `<span class="badge ${passed.has(key) ? 'bg-success' : 'bg-secondary'} me-1 mb-1">${key} ${value.toFixed(0)}${passed.has(key) ? ' ✓' : ''}</span>`
            );
        }

        if (!chips.length && !selectedName) return '';

        const status = confirmed
            ? '✅ CONFIRMADA POR CALIDAD'
            : '⚪ NO CONFIRMADA POR LOS 10 FILTROS';

        return `<div class="mt-2 p-2 rounded border border-secondary bg-black bg-opacity-25 small" style="line-height:1.35;">
            <div><strong>${escapeHtml(status)}</strong> · <span class="text-info">${escapeHtml(selected)} ${escapeHtml(selectedName)}</span> · <strong>${Number.isFinite(selectedScore) ? selectedScore.toFixed(1) : '0.0'}/100</strong></div>
            <div class="mt-1">${chips.join('')}</div>
            ${trace.legacy_publication_blockers?.length ? `<div class="text-muted mt-1">Gate legado: ${escapeHtml(trace.legacy_publication_blockers.join(', '))}. Q10 no es un segundo veto cuando un filtro paralelo ya confirmó y los guards universales pasan.</div>` : ''}
        </div>`;
    }

    function enrichCandidate(candidate) {
        if (!candidate || typeof candidate !== 'object') return candidate;
        const trace = traceOf(candidate);
        if (!trace || Object.keys(trace).length === 0) return candidate;

        const out = { ...candidate };
        const selected = String(
            trace.selected_filter || candidate.quality_filter_authority || 'NONE'
        ).toUpperCase();
        const score = Number(trace.selected_filter_score ?? candidate.quality_filter_score ?? 0);
        const name = String(trace.selected_filter_name || candidate.quality_filter_name || FILTER_NAMES[selected] || '');
        const passed = Array.isArray(trace.passed_filters) ? trace.passed_filters : [];
        const confirmed = Boolean(trace.confirmed_one_of_ten ?? candidate.quality_filter_confirmed);

        out.quality_filter_frontend_label = `${selected} · ${name} · ${Number.isFinite(score) ? score.toFixed(1) : '0.0'}/100`;
        out.quality_filter_frontend_passed = passed;
        out.quality_filter_frontend_confirmed = confirmed;

        const originalReason = String(out.manual_risk_reason || out.reason || '').trim();
        const compact = confirmed
            ? `Filtro de calidad: ${selected} (${name}) ${score.toFixed(1)}/100 · pasa 1+ de los 10 filtros.`
            : `Filtros de calidad: mejor ${selected} (${name}) ${score.toFixed(1)}/100 · no hay un filtro ≥75.`;
        out.manual_risk_reason = originalReason && !originalReason.includes(compact)
            ? `${originalReason} · ${compact}`
            : (originalReason || compact);
        return out;
    }

    function dedupeCandidates(list) {
        const map = new Map();
        for (const raw of Array.isArray(list) ? list : []) {
            const c = enrichCandidate(raw);
            if (!c || typeof c !== 'object') continue;
            const action = String(c.diagnostic_action || c.action || '').toUpperCase();
            if (!['LONG', 'SHORT'].includes(action)) continue;
            const key = `${c.symbol || ''}|${c.timeframe || ''}`;
            const score = Number(c.quality_filter_score ?? c.diagnostic_quality ?? c.confidence ?? 0);
            const prior = map.get(key);
            const priorScore = Number(prior?.quality_filter_score ?? prior?.diagnostic_quality ?? prior?.confidence ?? -1);
            if (!prior || score > priorScore) map.set(key, { ...c, action });
        }
        return [...map.values()];
    }

    function enrichSignalCards() {
        const containers = [
            document.getElementById('current-active-signals-list'),
            document.getElementById('prev-signals-list'),
            document.getElementById('active-signals-list')
        ].filter(Boolean);

        for (const container of containers) {
            const cards = container.querySelectorAll('[data-signal]');
            for (const card of cards) {
                if (card.dataset.commit23FilterShown === '1') continue;
                const raw = card.getAttribute('data-signal');
                if (!raw) continue;
                try {
                    const decode = window._decodeFuturesSignal;
                    const sig = typeof decode === 'function' ? decode(raw) : null;
                    const trace = traceOf(sig);
                    if (!trace || !trace.selected_filter) continue;
                    const selected = String(trace.selected_filter).toUpperCase();
                    const score = Number(trace.selected_filter_score || 0);
                    const name = String(trace.selected_filter_name || FILTER_NAMES[selected] || '');
                    const badge = document.createElement('div');
                    badge.className = 'small mt-1';
                    badge.innerHTML = `<span class="badge bg-info text-dark">Filtro ${escapeHtml(selected)} · ${escapeHtml(name)} · ${Number.isFinite(score) ? score.toFixed(0) : '0'}/100</span>`;
                    card.querySelector('strong')?.closest('div')?.appendChild(badge);
                    card.dataset.commit23FilterShown = '1';
                } catch (_) {
                    // Frontend-only enhancement; never block the original card.
                }
            }
        }
    }

    function wrapFetch() {
        if (window.__commit23QualityFetchWrapped) return;
        const originalFetch = window.fetch;
        if (typeof originalFetch !== 'function') return;

        window.fetch = async function (input, init) {
            const response = await originalFetch.call(this, input, init);
            try {
                const url = typeof input === 'string' ? input : (input?.url || '');
                if (!/\/api\/(futures|multiasset)\//i.test(url)) return response;
                if (!/signals\/(active|previous)|opportunities|analy/i.test(url)) return response;

                const clone = response.clone();
                const json = await clone.json();
                let changed = false;
                for (const key of ['other_directional_signals', 'vigent_other_directional_signals', 'analysis_candidates']) {
                    if (Array.isArray(json?.[key])) {
                        json[key] = dedupeCandidates(json[key]);
                        changed = true;
                    }
                }
                if (!changed) return response;

                const headers = new Headers(response.headers);
                headers.set('content-type', 'application/json; charset=utf-8');
                return new Response(JSON.stringify(json), {
                    status: response.status,
                    statusText: response.statusText,
                    headers
                });
            } catch (_) {
                return response;
            }
        };
        window.__commit23QualityFetchWrapped = true;
    }

    function installObserver() {
        const observer = new MutationObserver(() => enrichSignalCards());
        observer.observe(document.body, { childList: true, subtree: true });
        setInterval(enrichSignalCards, 2500);
    }

    // Expose the same compact renderer for any future UI component that wants
    // to show the ten-filter membership without duplicating policy logic.
    window.renderCommit23QualityFilterSummary = qualitySummary;
    window.COMMIT23_QUALITY_FRONTEND_VERSION = VERSION;

    wrapFetch();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installObserver, { once: true });
    } else {
        installObserver();
    }
})();
