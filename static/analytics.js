// analytics.js - Lógica de la página /analytics
// Consume /api/analytics/* y /api/review/logs

console.log('Análisis del sistema cargado');

function uiHumanLabel(value) {
    const raw = String(value ?? '');
    const exact = {
        'SHADOW_ONLY': 'En evaluación · no afecta operaciones',
        'C4_STRATEGY_REGISTRY_V2': 'Registro de estrategias actual',
        'Q7_STRATEGY_LAB_SHADOW_V1': 'Laboratorio de estrategias actual',
        '36W_V2_NORMALIZED': 'Motor de calidad actual',
        'HARD_SAFETY': 'Descartada por seguridad',
        'PRE_GATE_REJECTION': 'Descartada antes de publicación',
        'CAUTIOUS_SHADOW': 'Configuración prudente en evaluación'
    };
    if (exact[raw]) return exact[raw];
    if (/^[A-Z]?\d+[A-Z][A-Z0-9_.-]*$/.test(raw) || /^Q\d[A-Z0-9_.-]*$/i.test(raw)) return 'Motor actual';
    return raw.replace(/_/g, ' ');
}

const PLOTLY_LAYOUT_BASE = {
    paper_bgcolor: '#0d1726',
    plot_bgcolor: '#0d1726',
    font: { family: '-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif', size: 11, color: '#e7edf5' },
    margin: { l: 60, r: 30, t: 30, b: 60 }
};

const PLOTLY_CONFIG = {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d']
};


// ============================================================================
// UTILIDADES
// ============================================================================

function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) { console.log('[TOAST]', msg); return; }
    
    const colors = { info: 'bg-info', success: 'bg-success', danger: 'bg-danger', warning: 'bg-warning' };
    const bg = colors[type] || 'bg-secondary';
    
    const id = 'toast-' + Date.now();
    const html = `
        <div id="${id}" class="toast text-white ${bg}" role="alert">
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
    const el = document.getElementById(id);
    new bootstrap.Toast(el, { delay: 3500 }).show();
    el.addEventListener('hidden.bs.toast', () => el.remove());
}

function getFilters() {
    return {
        symbol: document.getElementById('f-symbol').value,
        timeframe: document.getElementById('f-timeframe').value,
        system_type: document.getElementById('f-system').value,
        action: document.getElementById('f-action').value,
        days_back: document.getElementById('f-days').value
    };
}

function buildQueryString(filters) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
        if (v) params.append(k, v);
    });
    return params.toString();
}

function formatPct(val, decimals = 2) {
    if (val === null || val === undefined) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(decimals)}%`;
}

function formatDate(iso) {
    if (!iso) return '--';
    try {
        return new Date(iso).toLocaleString('es-BO', { 
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    } catch(e) { return iso; }
}

// ============================================================================
// QUALITY ENGINE Q5D — ANALYTICS V2
// ============================================================================
//
// Presenta:
//
//     SPOT V2
//     FUTURES OFICIAL V2
//     FUTURES SHADOW
//
// y relaciona:
//
//     Safety -> WR / PnL / Expectancy R.
//
// Este código es exclusivamente de visualización.
// NO modifica trading.
// ============================================================================


function q5SetText(id, value) {

    const el = document.getElementById(id);

    if (!el) {
        return;
    }

    el.textContent = (
        value === null
        || value === undefined
        || value === ''
    )
        ? '--'
        : String(value);
}


function q5FiniteNumber(value) {

    if (
        value === null
        || value === undefined
        || value === ''
    ) {
        return null;
    }

    const number = Number(value);

    return Number.isFinite(number)
        ? number
        : null;
}


function q5FormatUnsignedPct(
    value,
    decimals = 1
) {

    const number = q5FiniteNumber(
        value
    );

    if (number === null) {
        return '--';
    }

    return (
        number.toFixed(decimals)
        + '%'
    );
}


function q5FormatSignedPct(
    value,
    decimals = 2
) {

    const number = q5FiniteNumber(
        value
    );

    if (number === null) {
        return '--';
    }

    const sign = (
        number > 0
        ? '+'
        : ''
    );

    return (
        sign
        + number.toFixed(decimals)
        + '%'
    );
}


function q5FormatSignedR(
    value,
    decimals = 3
) {

    const number = q5FiniteNumber(
        value
    );

    if (number === null) {
        return '--';
    }

    const sign = (
        number > 0
        ? '+'
        : ''
    );

    return (
        sign
        + number.toFixed(decimals)
        + 'R'
    );
}


function q5FormatNumber(
    value,
    decimals = 2
) {

    const number = q5FiniteNumber(
        value
    );

    if (number === null) {
        return '--';
    }

    return number.toFixed(
        decimals
    );
}


function q5SetPerformanceColor(
    id,
    value
) {

    const el = document.getElementById(id);

    if (!el) {
        return;
    }

    const number = q5FiniteNumber(
        value
    );

    el.classList.remove(
        'text-success',
        'text-danger',
        'text-warning'
    );

    if (number === null) {
        return;
    }

    if (number > 0) {

        el.classList.add(
            'text-success'
        );

    } else if (number < 0) {

        el.classList.add(
            'text-danger'
        );

    } else {

        el.classList.add(
            'text-warning'
        );
    }
}


function q5RenderCohort(
    prefix,
    data,
    options = {}
) {

    const d = (
        data
        && typeof data === 'object'
    )
        ? data
        : {};

    const resolved = Number(
        d.resolved
        || 0
    );

    const total = Number(
        d.total_directional
        || 0
    );

    q5SetText(
        `q5-${prefix}-n`,
        `N ${total.toLocaleString()}`
    );

    q5SetText(
        `q5-${prefix}-resolved`,
        resolved.toLocaleString()
    );

    // ================================================================
    // ECONOMÍA
    // ================================================================
    //
    // Con cero resultados resueltos NO mostramos "0%".
    //
    // 0% podría interpretarse incorrectamente como una medición real.
    // ================================================================

    if (resolved > 0) {

        q5SetText(
            `q5-${prefix}-wr`,
            q5FormatUnsignedPct(
                d.win_rate,
                1
            )
        );

        q5SetText(
            `q5-${prefix}-pnl`,
            q5FormatSignedPct(
                d.pnl_total_pct,
                2
            )
        );

        q5SetText(
            `q5-${prefix}-exp`,
            q5FormatSignedR(
                d.expectancy_r,
                3
            )
        );

        q5SetText(
            `q5-${prefix}-pf`,
            q5FormatNumber(
                d.profit_factor,
                2
            )
        );

        q5SetPerformanceColor(
            `q5-${prefix}-pnl`,
            d.pnl_total_pct
        );

        q5SetPerformanceColor(
            `q5-${prefix}-exp`,
            d.expectancy_r
        );

    } else {

        q5SetText(
            `q5-${prefix}-wr`,
            '--'
        );

        q5SetText(
            `q5-${prefix}-pnl`,
            '--'
        );

        q5SetText(
            `q5-${prefix}-exp`,
            '--'
        );

        q5SetText(
            `q5-${prefix}-pf`,
            '--'
        );
    }

    // ================================================================
    // CALIDAD
    // ================================================================
    //
    // Estas medias sí pueden existir aunque aún no haya TP/SL.
    // ================================================================

    q5SetText(
        `q5-${prefix}-safety`,
        q5FormatNumber(
            d.avg_safety,
            1
        )
    );

    q5SetText(
        `q5-${prefix}-entry`,
        q5FormatNumber(
            d.avg_entry_quality,
            1
        )
    );

    q5SetText(
        `q5-${prefix}-sl`,
        q5FormatNumber(
            d.avg_sl_quality,
            1
        )
    );

    q5SetText(
        `q5-${prefix}-tp`,
        q5FormatNumber(
            d.avg_tp_quality,
            1
        )
    );

    if (options.shadow) {

        q5SetText(
            'q5-q2-shadow',
            Number(
                d.q2_refined
                || 0
            ).toLocaleString()
        );
    }
}


function q5RenderSafetyTable(
    tbodyId,
    bands
) {

    const tbody = document.getElementById(
        tbodyId
    );

    if (!tbody) {
        return;
    }

    const safeBands = (
        bands
        && typeof bands === 'object'
    )
        ? bands
        : {};

    const order = [
        '<65',
        '65-69',
        '70-74',
        '>=75',
        'SIN_DATO'
    ];

    let html = '';

    order.forEach(
        label => {

            const row = (
                safeBands[label]
                || {}
            );

            const total = Number(
                row.total_directional
                || 0
            );

            const resolved = Number(
                row.resolved
                || 0
            );

            const wr = (
                resolved > 0
            )
                ? q5FormatUnsignedPct(
                    row.win_rate,
                    1
                )
                : '--';

            const pnl = (
                resolved > 0
            )
                ? q5FormatSignedPct(
                    row.pnl_total_pct,
                    2
                )
                : '--';

            const expectancy = (
                resolved > 0
            )
                ? q5FormatSignedR(
                    row.expectancy_r,
                    3
                )
                : '--';

            const pf = (
                resolved > 0
            )
                ? q5FormatNumber(
                    row.profit_factor,
                    2
                )
                : '--';

            const pnlNumber = q5FiniteNumber(
                row.pnl_total_pct
            );

            let performanceClass = '';

            if (
                resolved > 0
                && pnlNumber !== null
            ) {

                if (pnlNumber > 0) {

                    performanceClass = (
                        'text-success'
                    );

                } else if (pnlNumber < 0) {

                    performanceClass = (
                        'text-danger'
                    );

                } else {

                    performanceClass = (
                        'text-warning'
                    );
                }
            }

            html += `
                <tr>
                    <td><strong>${label}</strong></td>
                    <td>${total}</td>
                    <td class="text-success">${Number(row.tp_hit || 0)}</td>
                    <td class="text-danger">${Number(row.sl_hit || 0)}</td>
                    <td>${wr}</td>
                    <td class="${performanceClass}">${pnl}</td>
                    <td>${expectancy}</td>
                    <td>${pf}</td>
                </tr>
            `;
        }
    );

    tbody.innerHTML = html;
}

// ============================================================================
// Q7E — ADAPTIVE INTRADAY STRATEGY LAB / UI SHADOW
// ============================================================================
//
// Visualización únicamente.
//
// No recalcula estrategias y no modifica trading.
// Recibe Q7 desde el mismo /api/analytics/quality-v2.
// ============================================================================

function q7EvidenceText(value) {

    const status = String(
        value
        || 'INSUFFICIENT_EVIDENCE'
    ).toUpperCase();

    const labels = {
        INSUFFICIENT_EVIDENCE:
            'Muestra insuficiente',

        PRELIMINARY:
            'Preliminar',

        ELIGIBLE_FOR_HUMAN_REVIEW:
            'Muestra ≥25 · revisar'
    };

    return (
        labels[status]
        || status
    );
}


function q7EntryText(row) {

    const known = Number(
        row.entry_activation_known
        || 0
    );

    if (known <= 0) {
        return '--';
    }

    const activated = Number(
        row.entry_activated
        || 0
    );

    const rate = q5FiniteNumber(
        row.entry_activation_rate
    );

    return (
        `${activated}/${known}`
        + (
            rate === null
                ? ''
                : ` (${rate.toFixed(1)}%)`
        )
    );
}


function q7PushMetricRows(
    output,
    category,
    source,
    predicate = null
) {

    if (
        !source
        || typeof source !== 'object'
    ) {
        return;
    }

    Object.entries(
        source
    ).forEach(
        ([name, row]) => {

            if (
                !row
                || typeof row !== 'object'
            ) {
                return;
            }

            const total = Number(
                row.total_directional
                || 0
            );

            if (total <= 0) {
                return;
            }

            if (
                typeof predicate === 'function'
                && !predicate(
                    name,
                    row
                )
            ) {
                return;
            }

            output.push({
                category,
                name,
                row
            });
        }
    );
}


function q7FriendlyGroup(value) {
    const raw = String(value || '');
    const upper = raw.toUpperCase();
    const profile = upper.split('|')[0];
    const alignment = upper.split('|')[1];
    const profileLabels = { FAST: 'Perfil rápido', BALANCED: 'Perfil equilibrado', STRUCTURAL: 'Perfil estructural' };
    const alignmentLabels = { ALIGNED: 'alineado', NEUTRAL: 'neutral', CONFLICT: 'en conflicto' };
    if (profileLabels[profile] && alignmentLabels[alignment]) return `${profileLabels[profile]} · ${alignmentLabels[alignment]}`;
    const exact = {
        VWAP_RANGE_REVERSION_LONG: 'Reversión VWAP alcista',
        VWAP_RANGE_REVERSION_SHORT: 'Reversión VWAP bajista',
        ACCEPTED_LONG_RETEST: 'Retesteo alcista confirmado',
        ACCEPTED_SHORT_RETEST: 'Retesteo bajista confirmado',
        BREAKOUT_PENDING_RETEST: 'Ruptura pendiente de retesteo',
        BREAKDOWN_PENDING_RETEST: 'Ruptura bajista pendiente de retesteo'
    };
    return exact[upper] || uiHumanLabel(raw);
}

function q7FriendlyCategory(value) {
    const raw = String(value || '').toUpperCase();
    return ({ CONTROL: 'Referencia', RSI: 'RSI', VWAP: 'VWAP', RETEST: 'Ruptura y retesteo' })[raw] || uiHumanLabel(value);
}

function q7BuildRows(cohort) {

    const source = (
        cohort
        && typeof cohort === 'object'
    )
        ? cohort
        : {};

    const rows = [];

    const control = (
        source.control
        && typeof source.control === 'object'
    )
        ? source.control
        : {};

    if (
        Number(
            control.total_directional
            || 0
        ) > 0
    ) {

        rows.push({
            category:
                'CONTROL',

            name:
                'Todas las observaciones de estrategias adaptativas',

            row:
                control
        });
    }

    // RSI: perfil × alineación con la señal del sistema.
    q7PushMetricRows(
        rows,
        'RSI',
        source.profile_alignment
    );

    // VWAP: mostrar sólo hipótesis reales de reversión.
    q7PushMetricRows(
        rows,
        'VWAP',
        source.vwap_states,
        name => String(
            name
        ).includes(
            'VWAP_RANGE_REVERSION'
        )
    );

    // Breakout/Retest: aceptación o ruptura pendiente de retest.
    q7PushMetricRows(
        rows,
        'RETEST',
        source.breakout_retest_states,
        name => {

            const state = String(
                name
            ).toUpperCase();

            return (
                state.includes(
                    'ACCEPTED_'
                )
                || state.includes(
                    'PENDING_RETEST'
                )
            );
        }
    );

    return rows;
}


function q7RenderTable(
    tbodyId,
    cohort
) {

    const tbody = document.getElementById(
        tbodyId
    );

    if (!tbody) {
        return;
    }

    const rows = q7BuildRows(
        cohort
    );

    if (!rows.length) {

        tbody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-muted py-3">
                    Sin observaciones de estrategias adaptativas en esta cohorte.
                </td>
            </tr>
        `;

        return;
    }

    let html = '';

    rows.forEach(
        item => {

            const row = item.row;

            const total = Number(
                row.total_directional
                || 0
            );

            const resolved = Number(
                row.resolved
                || 0
            );

            const wr = (
                resolved > 0
            )
                ? q5FormatUnsignedPct(
                    row.win_rate,
                    1
                )
                : '--';

            const pnl = (
                resolved > 0
            )
                ? q5FormatSignedPct(
                    row.pnl_total_pct,
                    2
                )
                : '--';

            const expectancy = (
                resolved > 0
            )
                ? q5FormatSignedR(
                    row.expectancy_r,
                    3
                )
                : '--';

            const pf = (
                resolved > 0
            )
                ? q5FormatNumber(
                    row.profit_factor,
                    2
                )
                : '--';

            const expectancyNumber = q5FiniteNumber(
                row.expectancy_r
            );

            let performanceClass = '';

            if (
                resolved > 0
                && expectancyNumber !== null
            ) {

                if (expectancyNumber > 0) {
                    performanceClass = 'text-success';
                } else if (expectancyNumber < 0) {
                    performanceClass = 'text-danger';
                } else {
                    performanceClass = 'text-warning';
                }
            }

            html += `
                <tr>
                    <td class="text-nowrap">${q7FriendlyCategory(item.category)}</td>
                    <td><strong>${q7FriendlyGroup(item.name)}</strong></td>
                    <td>${total}</td>
                    <td>${q7EntryText(row)}</td>
                    <td class="text-success">${Number(row.tp_hit || 0)}</td>
                    <td class="text-danger">${Number(row.sl_hit || 0)}</td>
                    <td>${wr}</td>
                    <td>${pnl}</td>
                    <td class="${performanceClass}">${expectancy}</td>
                    <td>
                        ${pf}
                        <div class="small text-muted">
                            ${q7EvidenceText(row.evidence_status)}
                        </div>
                    </td>
                </tr>
            `;
        }
    );

    tbody.innerHTML = html;
}


function q7RenderStrategyLab(q7) {

    const data = (
        q7
        && typeof q7 === 'object'
    )
        ? q7
        : {};

    const official = (
        data.official
        && typeof data.official === 'object'
    )
        ? data.official
        : {};

    const shadow = (
        data.shadow
        && typeof data.shadow === 'object'
    )
        ? data.shadow
        : {};

    const officialObservations = Number(
        official.observations
        || 0
    );

    const shadowObservations = Number(
        shadow.observations
        || 0
    );

    const excluded = Number(
        data.excluded
        || 0
    );

    q5SetText(
        'q7-mode',
        uiHumanLabel(data.mode || 'En evaluación · no afecta operaciones')
    );

    q5SetText(
        'q7-summary',
        (
            `Oficial: ${officialObservations.toLocaleString()} observaciones · `
            + `En evaluación: ${shadowObservations.toLocaleString()} · `
            + `Excluidas por integridad: ${excluded.toLocaleString()}`
        )
    );

    q7RenderTable(
        'q7-official-body',
        official
    );

    q7RenderTable(
        'q7-shadow-body',
        shadow
    );

    const statusEl = document.getElementById(
        'q7-status'
    );

    if (!statusEl) {
        return;
    }

    statusEl.className = (
        'small text-warning mb-3'
    );

    if (
        officialObservations === 0
        && shadowObservations === 0
    ) {

        statusEl.textContent = (
            'Aún no existen resultados suficientes de las estrategias en evaluación. '
            + 'observaciones suficientes para una comparación estable.'
        );

        return;
    }

    statusEl.textContent = (
        'Las estrategias adaptativas continúan en evaluación y no afectan operaciones. '
        + 'Las tablas comparan el momento de entrada y los resultados; '
        + 'ningún resultado cambia seguridad, entrada, stop, objetivo, votos o publicación.'
    );
}


// ============================================================================
// COMMIT 6 — OBSERVATORIO DE APRENDIZAJE
// ============================================================================

function loPct(value, decimals = 1) {
    const n = q5FiniteNumber(value);
    return n === null ? '--' : `${n.toFixed(decimals)}%`;
}

function loR(value, decimals = 2) {
    const n = q5FiniteNumber(value);
    return n === null ? '--' : `${n.toFixed(decimals)}R`;
}

function loHumanReason(value) {
    const raw = String(value || '');
    if (!raw) return 'Sin detalle adicional.';
    if (raw === 'COHORTE_INCOMPLETA') return 'La lectura completa de la cohorte todavía no está demostrada.';
    if (raw === 'PNL_NETO_REALIZADO_AUN_NO_VERIFICABLE') return 'Comisión, slippage y funding realizados todavía no están atribuidos de forma uniforme.';
    if (/^FUTURES_\d+_DE_25_RESUELTAS$/.test(raw)) {
        const n = raw.match(/^FUTURES_(\d+)_/)[1];
        return `Futures oficial: ${n}/25 resultados mínimos para calibración.`;
    }
    if (/^SPOT_\d+_DE_25_RESUELTAS$/.test(raw)) {
        const n = raw.match(/^SPOT_(\d+)_/)[1];
        return `Spot: ${n}/25 resultados mínimos para calibración.`;
    }
    if (/^INSUFFICIENT_EVIDENCE_/i.test(raw)) return 'Muestra insuficiente para cambiar producción.';
    if (raw === 'ROBUST_NEGATIVE_EXECUTION_EVIDENCE') return 'La evidencia disponible sólo autoriza protección, no mayor riesgo.';
    if (raw === 'ROBUST_POSITIVE_EXECUTION_EVIDENCE') return 'Existe evidencia positiva preliminar bajo guardrails.';
    if (raw === 'BLOCKED_PENDING_COMPLETE_NET_EVIDENCE' || raw === 'POSITIVE_AUTHORITY_BLOCKED_PENDING_COMPLETE_NET_EVIDENCE') return 'La promoción positiva y el aumento de leverage siguen bloqueados hasta completar cohorte y costes netos.';
    if (raw === 'EVIDENCE_GATE_CLOSED') return 'La optimización positiva sigue bloqueada hasta que la evidencia completa sea suficiente.';
    if (raw === 'EVIDENCE_GATE_OPEN') return 'La evidencia completa permite optimización de calidad bajo límites de riesgo.';
    if (raw === 'coverage_complete') return 'La lectura completa de la ventana estadística todavía no está demostrada.';
    if (raw === 'sample_ok') return 'Aún faltan resultados Futures oficiales para habilitar optimización automática.';
    if (raw === 'validation_sample_ok') return 'Aún falta muestra suficiente en la ventana temporal de validación.';
    if (raw === 'gross_expectancy_ok') return 'La expectancy oficial todavía no demuestra ventaja suficiente.';
    if (raw === 'profit_factor_ok') return 'El Profit Factor oficial todavía no supera el mínimo de gobernanza.';
    if (raw === 'modeled_net_coverage_ok' || raw === 'model_complete_net_coverage_ok') return 'Aún falta completar la economía modelada de suficientes operaciones, incluido el funding observado.';
    if (raw === 'modeled_net_expectancy_ok' || raw === 'model_complete_net_expectancy_ok') return 'La expectancy neta modelada todavía no demuestra ventaja suficiente.';
    if (raw === 'validation_net_expectancy_ok') return 'La ventaja neta modelada no se mantiene todavía fuera de la ventana de descubrimiento.';
    if (raw === 'validation_profit_factor_ok') return 'El Profit Factor de validación todavía no confirma la ventaja.';
    if (raw === 'realized_net_coverage_ok') return 'Aún falta cobertura económica completa suficiente para habilitar optimización.';
    if (raw === 'realized_net_expectancy_ok') return 'La evidencia neta después de costes todavía no demuestra ventaja positiva.';
    if (raw === 'validation_realized_net_expectancy_ok') return 'La ventaja neta todavía no se confirma fuera de la ventana de descubrimiento.';
    if (raw === 'validation_realized_net_profit_factor_ok') return 'El Profit Factor neto de validación todavía no confirma la ventaja.';
    if (raw === 'risk_sample_ok') return 'El escalado requiere al menos 50 resultados Futures oficiales.';
    if (raw === 'risk_validation_sample_ok') return 'El escalado requiere al menos 15 resultados en validación temporal.';
    if (raw === 'risk_net_coverage_ok') return 'El escalado espera economía neta modelada completa en al menos 95% de resultados.';
    if (raw === 'risk_net_expectancy_ok') return 'La expectancy neta modelada aún no alcanza el margen exigido para escalar riesgo.';
    if (raw === 'risk_net_profit_factor_ok') return 'El Profit Factor neto modelado aún no alcanza el mínimo exigido para escalar riesgo.';
    if (raw === 'risk_validation_expectancy_ok') return 'La ventaja neta todavía no es suficientemente fuerte en validación temporal.';
    if (raw === 'risk_validation_pf_ok') return 'El Profit Factor de validación todavía no es suficiente para escalar riesgo.';
    if (raw === 'risk_recent_health_ok') return 'Los resultados netos recientes no permiten aumentar exposición.';
    if (raw === 'risk_mae_ok') return 'La excursión adversa media todavía es demasiado alta para aumentar exposición.';
    if (raw === 'risk_failure_streak_ok') return 'La racha reciente de pérdidas bloquea cualquier aumento de exposición.';
    if (raw === 'quality_gate_open') return 'La optimización de calidad todavía no ha superado todos sus controles.';
    if (raw === 'STALE_GOVERNANCE_STATE') return 'La última comprobación de gobernanza está desactualizada; la autoridad positiva se cerró por seguridad.';
    if (raw === 'recent_health_ok') return 'Los resultados recientes muestran deterioro y bloquean promoción positiva.';
    if (raw === 'failure_streak_ok') return 'Existe una racha de pérdidas demasiado larga para habilitar promoción positiva.';
    return uiHumanLabel(raw);
}

function traderEvidenceLabel(value) {
    const state = String(value || '').toUpperCase();
    if (state === 'PROMISING') return 'Prometedor';
    if (state === 'DEGRADED') return 'Débil';
    if (state === 'OBSERVE') return 'Observar';
    return 'Muestra insuficiente';
}

function traderRelationLabel(value) {
    const relation = String(value || '').toUpperCase();
    if (relation === 'SUPPORT') return 'Apoya';
    if (relation === 'OPPOSE') return 'Veta / contradice';
    return 'Neutral';
}

function traderRegimeLabel(value) {
    const regime = String(value || '').toUpperCase();
    const labels = {
        ALL: 'Todos', UNKNOWN: 'Sin clasificar', TREND_DOWN: 'Tendencia bajista',
        TREND_UP: 'Tendencia alcista', TRANSITION: 'Transición', BALANCE: 'Equilibrado',
        VOLATILITY_SHOCK: 'Alta volatilidad', RANGING: 'Lateral'
    };
    return labels[regime] || uiHumanLabel(regime || '--');
}

function selfCalibrationStateLabel(value) {
    const state = String(value || 'OBSERVE').toUpperCase();
    const labels = {
        OBSERVE: 'Observación', PROTECT: 'Protección', CANARY: 'Prueba controlada', ACTIVE: 'Activo'
    };
    return labels[state] || uiHumanLabel(state);
}

function selfCalibrationEvidenceLabel(value) {
    const state = String(value || '').toUpperCase();
    if (state === 'ACTIVE_READY' || state === 'ACTIVE') return 'Activo / robusto';
    if (state === 'CANARY_READY' || state === 'CANARY') return 'Prueba controlada';
    if (state === 'PROTECT') return 'Protección';
    if (state === 'REVIEWABLE') return 'Revisable';
    if (state === 'PROMISING') return 'Prometedor';
    if (state === 'DEGRADED') return 'Débil';
    return 'Observación';
}

function renderSelfCalibrationV1(data) {
    const selfCal = data?.self_calibration_v1
        || data?.learning_observatory_v1?.self_calibration
        || {};
    const summary = selfCal?.summary || {};
    const state = String(selfCal?.state || 'OBSERVE').toUpperCase();
    const badge = document.getElementById('sc-state');
    if (badge) {
        const cls = state === 'ACTIVE' ? 'bg-success'
            : state === 'CANARY' ? 'bg-primary'
            : state === 'PROTECT' ? 'bg-warning text-dark' : 'bg-secondary';
        badge.className = `badge ${cls}`;
        badge.textContent = selfCalibrationStateLabel(state);
    }
    q5SetText('sc-active', Number(summary.active_adjustments || 0).toLocaleString());
    q5SetText('sc-canary', Number(summary.canary_adjustments || 0).toLocaleString());
    q5SetText('sc-protect', Number(summary.protective_adjustments || 0).toLocaleString());
    q5SetText('sc-economics', summary.economics_ready ? 'Sí' : 'No');

    const intel = data?.trader_intelligence_v2?.scorecard_v1
        || data?.trader_intelligence_v1
        || {};
    const traderRows = (Array.isArray(intel.rows) ? intel.rows : [])
        .filter(row => row && row.relation === 'SUPPORT'
            && Number(row.resolved || 0) >= 3
            && row.judgement_expectancy_r !== null
            && row.judgement_expectancy_r !== undefined)
        .sort((a, b) => Number(b.judgement_expectancy_r || -999) - Number(a.judgement_expectancy_r || -999))
        .slice(0, 6);

    const traderBody = document.getElementById('sc-top-traders');
    if (traderBody) {
        traderBody.innerHTML = traderRows.length ? traderRows.map(row => `<tr>
            <td><strong>${uiHumanLabel(row.trader || '--')}</strong></td>
            <td>${String(row.market || '--').toUpperCase()}</td>
            <td>${uiHumanLabel(row.direction || '--')}</td>
            <td>${Number(row.resolved || 0).toLocaleString()}</td>
            <td>${loR(row.judgement_expectancy_r, 3)}</td>
            <td>${traderEvidenceLabel(row.evidence_state)}</td>
        </tr>`).join('') : '<tr><td colspan="6" class="text-center text-muted py-2">Aún no hay muestra suficiente para un TOP estable.</td></tr>';
    }

    const bars = document.getElementById('sc-trader-bars');
    if (bars) {
        bars.innerHTML = traderRows.length ? traderRows.map(row => {
            const exp = Number(row.judgement_expectancy_r || 0);
            const width = Math.max(4, Math.min(100, 50 + exp * 22));
            return `<div class="mb-2">
                <div class="d-flex justify-content-between small"><span>${uiHumanLabel(row.trader || '--')}</span><span>${loR(exp, 2)}</span></div>
                <div class="progress" style="height:6px"><div class="progress-bar" role="progressbar" style="width:${width}%" aria-valuenow="${width}" aria-valuemin="0" aria-valuemax="100"></div></div>
            </div>`;
        }).join('') : '<div class="small text-muted">Esperando más resultados.</div>';
    }

    const strategyScopes = [
        ['Spot', data?.strategy_attribution_v2?.spot],
        ['Futures', data?.strategy_attribution_v2?.futures_official],
        ['Futures · evaluación', data?.strategy_attribution_v2?.futures_shadow]
    ];
    const strategies = [];
    strategyScopes.forEach(([scope, block]) => {
        (Array.isArray(block?.rows) ? block.rows : []).forEach(row => {
            if (!row || !row.strategy) return;
            const resolved = Number(row.resolved || 0);
            const exp = row.expectancy_r;
            if (resolved < 2 || exp === null || exp === undefined) return;
            strategies.push({...row, _scope: scope});
        });
    });
    strategies.sort((a, b) => Number(b.expectancy_r || -999) - Number(a.expectancy_r || -999));
    const strategyBody = document.getElementById('sc-top-strategies');
    if (strategyBody) {
        const rows = strategies.slice(0, 7);
        strategyBody.innerHTML = rows.length ? rows.map(row => `<tr>
            <td>${uiHumanLabel(row.strategy)}</td>
            <td>${row._scope}</td>
            <td>${Number(row.resolved || 0).toLocaleString()}</td>
            <td>${row.win_rate_pct === null || row.win_rate_pct === undefined ? '--' : loPct(row.win_rate_pct)}</td>
            <td>${loR(row.expectancy_r, 3)}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted py-2">Aún no hay atribución suficiente.</td></tr>';
    }

    const executionRows = (Array.isArray(data?.execution_challenger_lab_v1?.rows)
        ? data.execution_challenger_lab_v1.rows : [])
        .filter(row => row && String(row.candidate || '').toUpperCase() !== 'BASELINE')
        .sort((a, b) => Number(b.validation_net_expectancy_r ?? -999) - Number(a.validation_net_expectancy_r ?? -999))
        .slice(0, 6);
    const executionBody = document.getElementById('sc-execution-candidates');
    if (executionBody) {
        executionBody.innerHTML = executionRows.length ? executionRows.map(row => `<tr>
            <td>${uiHumanLabel(row.candidate || '--')}</td>
            <td>${Number(row.resolved || 0).toLocaleString()}</td>
            <td>${row.net_expectancy_r === null || row.net_expectancy_r === undefined ? '--' : loR(row.net_expectancy_r, 3)}</td>
            <td>${row.validation_net_expectancy_r === null || row.validation_net_expectancy_r === undefined ? '--' : loR(row.validation_net_expectancy_r, 3)}</td>
            <td>${selfCalibrationEvidenceLabel(row.evidence_state)}</td>
        </tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted py-2">Los resultados nuevos empezarán a llenar esta tabla automáticamente.</td></tr>';
    }

    const note = document.getElementById('sc-note');
    if (note) {
        const updated = selfCal?.updated_at ? new Date(selfCal.updated_at).toLocaleString() : '--';
        note.textContent = summary.economics_ready
            ? `Última recalibración: ${updated}. Los ajustes positivos siguen sujetos a validación temporal y rollback automático.`
            : `Última recalibración: ${updated}. Aún no hay cobertura económica suficiente para habilitar ajustes positivos; las protecciones por evidencia negativa sí pueden actuar.`;
    }
}

function renderLearningObservatory(data) {
    const observatory = data?.learning_observatory_v1 || {};
    const forensics = observatory?.execution_forensics?.futures_official
        || data?.execution_forensics_v2?.futures_official
        || {};
    const attribution = observatory?.strategy_attribution?.futures_official
        || data?.strategy_attribution_v2?.futures_official
        || {};
    const traderIntel = observatory?.trader_intelligence
        || data?.trader_intelligence_v1
        || {};
    const integrity = observatory?.learning_integrity
        || data?.learning_integrity_v1
        || {};

    q5SetText('lo-forensics-n', Number(forensics.n_with_forensics || 0).toLocaleString());
    q5SetText('lo-entry-reach', loPct(forensics.entry_reach_rate_pct));
    q5SetText('lo-defensibility', loPct(forensics.entry_defensibility_proxy_pct));
    q5SetText('lo-direct-stop', loPct(forensics.direct_stop_rate_pct));
    q5SetText('lo-mfe', loR(forensics.avg_mfe_r));
    q5SetText('lo-mae', loR(forensics.avg_mae_r));
    q5SetText('lo-tight-stop', loPct(forensics.stop_tight_suspect_rate_pct));
    q5SetText('lo-post-stop-tp', loPct(forensics.post_stop_tp_rate_pct));

    const gate = document.getElementById('learning-observatory-gate');
    if (gate) {
        const ready = Boolean(observatory.calibration_allowed);
        gate.className = `badge ${ready ? 'bg-success' : 'bg-secondary'}`;
        gate.textContent = ready ? 'Calibración habilitada' : 'Recopilando evidencia';
    }

    const reasons = Array.isArray(observatory.block_reasons) ? observatory.block_reasons : [];
    q5SetText(
        'lo-block-reasons',
        reasons.length
            ? reasons.map(loHumanReason).join(' · ')
            : 'Sin bloqueos de observabilidad reportados.'
    );

    const body = document.getElementById('lo-attribution-body');
    if (body) {
        const rows = Array.isArray(attribution.rows) ? attribution.rows.slice(0, 8) : [];
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-2">Aún no hay suficiente atribución oficial.</td></tr>';
        } else {
            body.innerHTML = rows.map(row => {
                const relation = String(row.relation_to_final || '').toUpperCase();
                const relationText = relation === 'SUPPORT' ? 'Apoya' : relation === 'OPPOSE' ? 'Contradice' : 'Neutral';
                const wr = row.win_rate_pct === null || row.win_rate_pct === undefined ? '--' : loPct(row.win_rate_pct);
                const exp = row.expectancy_r === null || row.expectancy_r === undefined ? '--' : loR(row.expectancy_r, 3);
                return `<tr>
                    <td>${uiHumanLabel(row.trader || '--')}</td>
                    <td>${uiHumanLabel(row.strategy || '--')}</td>
                    <td>${relationText}</td>
                    <td>${Number(row.n || 0).toLocaleString()}</td>
                    <td>${Number(row.resolved || 0).toLocaleString()}</td>
                    <td>${wr}</td>
                    <td>${exp}</td>
                </tr>`;
            }).join('');
        }
    }

    const scoreBody = document.getElementById('lo-trader-scorecard-body');
    if (scoreBody) {
        const rows = Array.isArray(traderIntel.rows)
            ? traderIntel.rows.filter(row => row.dimensionality !== 'REGIME' || Number(row.resolved || 0) > 0).slice(0, 14)
            : [];
        if (!rows.length) {
            scoreBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-2">Aún no hay outcomes suficientes para perfilar especialistas.</td></tr>';
        } else {
            scoreBody.innerHTML = rows.map(row => {
                const exp = row.judgement_expectancy_r === null || row.judgement_expectancy_r === undefined
                    ? '--' : loR(row.judgement_expectancy_r, 3);
                const confidence = row.avg_confidence_pct === null || row.avg_confidence_pct === undefined
                    ? '--' : loPct(row.avg_confidence_pct);
                const state = traderEvidenceLabel(row.evidence_state);
                const cls = String(row.evidence_state || '').toUpperCase() === 'PROMISING' ? 'text-success'
                    : String(row.evidence_state || '').toUpperCase() === 'DEGRADED' ? 'text-danger' : 'text-muted';
                return `<tr>
                    <td><strong>${uiHumanLabel(row.trader || '--')}</strong></td>
                    <td>${String(row.market || '--').toUpperCase()}</td>
                    <td>${row.timeframe === 'ALL' ? 'Todas' : uiHumanLabel(row.timeframe || '--')}</td>
                    <td>${uiHumanLabel(row.direction || '--')}</td>
                    <td>${traderRegimeLabel(row.regime)}</td>
                    <td>${traderRelationLabel(row.relation)}</td>
                    <td>${Number(row.resolved || 0).toLocaleString()}</td>
                    <td>${exp}</td>
                    <td>${confidence}</td>
                    <td class="${cls}">${state}</td>
                </tr>`;
            }).join('');
        }
    }

    const redundancyEl = document.getElementById('lo-trader-redundancy');
    if (redundancyEl) {
        const pairs = Array.isArray(traderIntel.pairwise_redundancy) ? traderIntel.pairwise_redundancy : [];
        const top = pairs.find(row => Number(row.co_signal_n || 0) >= 3);
        redundancyEl.textContent = top
            ? `Redundancia observada: ${uiHumanLabel(top.trader_a)} y ${uiHumanLabel(top.trader_b)} coincidieron en ${Number(top.co_signal_n)} señales; misma dirección ${loPct(top.same_side_pct)}. Es diagnóstico, no modifica pesos.`
            : 'Todavía no hay suficiente co-ocurrencia para medir redundancia entre traders.';
    }

    const integrityEl = document.getElementById('lo-learning-integrity');
    if (integrityEl) {
        const scopes = integrity.scopes || {};
        const spotScope = scopes.spot_current || {};
        const futScope = scopes.futures_official_current || {};
        const comparison = integrity.governance_comparison || {};
        const matchText = comparison.same_scope_match === true ? 'coincide con gobernanza'
            : comparison.same_scope_match === false ? 'snapshot distinto o desactualizado'
            : 'esperando primer refresh de gobernanza';
        integrityEl.textContent = `Motor actual: Spot ${Number(spotScope.n || 0)} señales / ${Number(spotScope.resolved || 0)} resueltas; Futures ${Number(futScope.n || 0)} / ${Number(futScope.resolved || 0)}. Analytics ↔ gobernanza: ${matchText}. El PDF de aprendizaje puede usar una cohorte Q6 más amplia y por eso no necesita tener el mismo N.`;
        q5SetText('lo-governance-cohort-match', comparison.same_scope_match === true ? 'Coherente' : comparison.same_scope_match === false ? 'Revisar snapshot' : 'Esperando refresh');
    }
}

// ============================================================================
// COMMIT 7 — DESCUBRIMIENTO DE EDGE
// ============================================================================

function edgeStateLabel(state) {
    const value = String(state || '').toUpperCase();
    if (value === 'RESEARCH_PRIORITY') return 'Prioridad de investigación';
    if (value === 'PROMISING_NEEDS_VALIDATION') return 'Prometedora · falta validar';
    if (value === 'LOW_PRIORITY_RESEARCH') return 'Baja prioridad';
    return 'Observación';
}

function edgeFriendlyText(value) {
    return String(value || '--')
        .replaceAll('Trend Down', 'Tendencia bajista')
        .replaceAll('Trend Up', 'Tendencia alcista')
        .replaceAll('Balance', 'Mercado equilibrado')
        .replaceAll('Transition', 'Transición')
        .replaceAll('Volatility Shock', 'Choque de volatilidad')
        .replaceAll('Fast|Aligned', 'Perfil rápido · alineado')
        .replaceAll('Fast|Conflict', 'Perfil rápido · en conflicto')
        .replaceAll('Balanced|Aligned', 'Perfil equilibrado · alineado')
        .replaceAll('Balanced|Conflict', 'Perfil equilibrado · en conflicto')
        .replaceAll('Aligned', 'Alineado')
        .replaceAll('Conflict', 'En conflicto')
        .replaceAll('Vwap Range Reversion Short', 'Reversión VWAP bajista')
        .replaceAll('Vwap Range Reversion Long', 'Reversión VWAP alcista')
        .replaceAll('Accepted Short Retest', 'Retesteo bajista confirmado')
        .replaceAll('Accepted Long Retest', 'Retesteo alcista confirmado')
        .replaceAll('Breakdown Pending Retest', 'Ruptura bajista pendiente de retesteo')
        .replaceAll('Breakout Pending Retest', 'Ruptura alcista pendiente de retesteo');
}

function renderEdgeDiscovery(data) {
    const edge = data?.edge_discovery_v1 || {};
    const futures = edge?.futures_shadow || {};
    const baseline = futures?.baseline || {};
    const priority = Array.isArray(futures.priority) ? futures.priority : [];
    const watch = Array.isArray(futures.watch) ? futures.watch : [];
    const low = Array.isArray(futures.low_priority) ? futures.low_priority : [];
    const failure = edge?.early_failure_watch || {};

    q5SetText('edge-baseline-exp', loR(baseline.expectancy_r, 3));
    q5SetText('edge-resolved', Number(futures.resolved || 0).toLocaleString());
    q5SetText('edge-priority-count', Number(priority.length || 0).toLocaleString());
    q5SetText(
        'edge-failure-watch',
        failure.alert ? `${Number(failure.consecutive_sl || 0)} SL seguidos` : 'Sin alerta'
    );

    const note = document.getElementById('edge-discovery-note');
    if (note) {
        const cutoff = futures.cutoff ? formatDate(futures.cutoff) : null;
        note.textContent = cutoff
            ? `Sólo investigación. Corte temporal Descubrimiento/Validación: ${cutoff}. Ninguna hipótesis cambia señales, Safety, niveles o leverage.`
            : 'Sólo investigación. Aún no existe muestra suficiente para una separación temporal estable.';
    }

    const mainRows = [...priority, ...watch].slice(0, 10);
    const body = document.getElementById('edge-priority-body');
    if (body) {
        if (!mainRows.length) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-2">Aún no hay una hipótesis con muestra suficiente.</td></tr>';
        } else {
            body.innerHTML = mainRows.map(row => {
                const total = row.total || {};
                const validation = row.validation || {};
                const lift = q5FiniteNumber(row.lift_vs_baseline_r);
                const liftText = lift === null ? '--' : `${lift >= 0 ? '+' : ''}${lift.toFixed(3)}R`;
                const pf = q5FiniteNumber(total.profit_factor);
                const cls = String(row.state || '').toUpperCase() === 'RESEARCH_PRIORITY' ? 'text-success'
                    : String(row.state || '').toUpperCase() === 'PROMISING_NEEDS_VALIDATION' ? 'text-warning' : '';
                return `<tr>
                    <td><strong>${edgeFriendlyText(row.label || '--')}</strong></td>
                    <td>${Number(total.resolved || 0).toLocaleString()}</td>
                    <td>${loR(total.expectancy_r, 3)}</td>
                    <td>${Number(validation.resolved || 0) > 0 ? loR(validation.expectancy_r, 3) : '--'}</td>
                    <td>${pf === null ? '--' : pf.toFixed(2)}</td>
                    <td>${liftText}</td>
                    <td class="${cls}">${edgeStateLabel(row.state)}</td>
                </tr>`;
            }).join('');
        }
    }

    const lowBody = document.getElementById('edge-low-body');
    if (lowBody) {
        const rows = low.slice(0, 8);
        lowBody.innerHTML = rows.length ? rows.map(row => {
            const total = row.total || {};
            const validation = row.validation || {};
            return `<tr>
                <td>${edgeFriendlyText(row.label || '--')}</td>
                <td>${Number(total.resolved || 0).toLocaleString()}</td>
                <td>${loR(total.expectancy_r, 3)}</td>
                <td>${Number(validation.resolved || 0) > 0 ? loR(validation.expectancy_r, 3) : '--'}</td>
                <td class="text-muted">${edgeStateLabel(row.state)}</td>
            </tr>`;
        }).join('') : '<tr><td colspan="5" class="text-center text-muted py-2">Sin hipótesis de baja prioridad con muestra suficiente.</td></tr>';
    }
}

async function refreshLearningGovernanceNow() {
    const button = document.getElementById('lo-refresh-governance');
    if (button) {
        button.disabled = true;
        button.textContent = 'Actualizando...';
    }
    try {
        const response = await fetch('/api/review/governance/refresh', { method: 'POST' });
        const payload = await response.json();
        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'No se pudo actualizar la gobernanza.');
        }
        showToast('Gobernanza actualizada con la evidencia persistida.', 'success');
        await Promise.all([loadQualityV2(), loadLearningGovernanceStatus()]);
    } catch (error) {
        showToast(error.message || 'Error actualizando gobernanza.', 'danger');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Actualizar';
        }
    }
}

async function runLearningScientistTest() {
    const button = document.getElementById('lo-test-learning');
    if (button) {
        button.disabled = true;
        button.textContent = 'Probando...';
    }
    try {
        const response = await fetch('/api/ai/learning/test', { method: 'POST' });
        const payload = await response.json();
        if (!response.ok || !payload.success) {
            const reason = payload?.result?.reason || payload?.error || 'El proveedor no completó la prueba.';
            throw new Error(reason);
        }
        showToast('El científico de aprendizaje respondió y dejó actividad persistida.', 'success');
        await loadLearningGovernanceStatus();
    } catch (error) {
        showToast(error.message || 'Error probando el científico de aprendizaje.', 'danger');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = 'Probar ahora';
        }
    }
}

async function loadLearningGovernanceStatus() {
    const requests = [
        fetch('/api/review/autopilot/status').then(async response => ({ kind: 'autopilot', response, json: await response.json() })),
        fetch('/api/ai/gemini-activity').then(async response => ({ kind: 'gemini', response, json: await response.json() }))
    ];

    const results = await Promise.allSettled(requests);
    results.forEach(item => {
        if (item.status !== 'fulfilled') return;
        const { kind, response, json } = item.value;
        if (!response.ok || !json) return;

        if (kind === 'autopilot' && json.success) {
            const status = json.autopilot || {};
            const profiles = Array.isArray(status.profiles) ? status.profiles : [];
            const profile = profiles.find(row => row.symbol === '*' && row.timeframe === '*') || profiles[0] || {};
            const state = String(profile.state || 'OBSERVE').toUpperCase();
            const config = profile.config || {};
            const evidence = profile.evidence || {};
            const governance = status.promotion_governance || {};
            const positiveAuthority = Boolean(governance.quality_optimization_allowed);
            const strategyVeto = Boolean(governance.strategy_veto_authority_allowed);
            const strategies = Array.isArray(status.strategies) ? status.strategies : [];
            const activeStrategies = strategies.filter(row => String(row.state || '').toUpperCase() === 'ACTIVE').length;
            const productionAuthority = state === 'PROTECT' || (state === 'ACTIVE' && positiveAuthority);
            q5SetText('lo-autopilot-state', state === 'PROTECT' ? 'Protección' : state === 'ACTIVE' ? 'Perfil de calidad validado' : 'Observación');
            q5SetText('lo-autopilot-authority', productionAuthority ? 'Habilitada bajo evidencia' : 'Bloqueada');
            q5SetText('lo-strategy-veto-authority', strategyVeto ? `${activeStrategies} activas · veto solamente` : 'Bloqueado');
            q5SetText('lo-leverage-growth', governance.risk_growth_allowed ? 'Habilitado por edge neto' : 'Bloqueado');

            const coverage = governance.coverage || {};
            const gEvidence = governance.evidence || {};
            const total = gEvidence.total || {};
            const validation = gEvidence.validation_30 || {};
            const streak = Number(gEvidence.consecutive_sl || 0);
            q5SetText('lo-governance-coverage', coverage.complete ? 'Completa' : 'Incompleta');
            q5SetText('lo-governance-sample', `${Number(total.resolved || 0)}/25`);
            q5SetText('lo-governance-validation', `${Number(validation.resolved || 0)}/10`);
            const modelCoverage = Number(total.model_complete_net_coverage_pct ?? total.modeled_net_coverage_pct ?? 0);
            const modelExp = total.model_complete_net_expectancy_r ?? total.modeled_net_expectancy_r;
            const modelPf = total.model_complete_net_profit_factor ?? total.modeled_net_profit_factor;
            const fundingCoverage = Number(total.funding_observed_coverage_pct || 0);
            q5SetText('lo-economics-coverage', `${modelCoverage.toFixed(0)}% de resultados`);
            q5SetText('lo-governance-net-exp', modelExp === null || modelExp === undefined ? '--' : loR(modelExp, 3));
            q5SetText('lo-governance-net-pf', modelPf === null || modelPf === undefined ? '--' : Number(modelPf).toFixed(2));
            q5SetText('lo-funding-coverage', `${fundingCoverage.toFixed(0)}% de resultados`);
            const realizedCoverage = Number(total.realized_net_coverage_pct || 0);
            q5SetText('lo-governance-realized-net', realizedCoverage > 0 ? `${realizedCoverage.toFixed(0)}% con datos reales` : 'No disponibles · sin ejecución del exchange');
            q5SetText('lo-governance-sl-streak', streak > 0 ? `${streak} consecutivos` : 'Sin racha activa');
            q5SetText('lo-leverage-mode', governance.risk_growth_allowed ? 'Presupuesto de riesgo adaptativo' : 'Estática · mínima viable');

            const reasons = Array.isArray(governance.block_reasons) ? governance.block_reasons : [];
            const riskReasons = Array.isArray(governance.risk_block_reasons) ? governance.risk_block_reasons : [];
            const visibleReasons = [...new Set([...reasons, ...riskReasons])];
            const governanceReason = visibleReasons.length
                ? visibleReasons.slice(0, 6).map(loHumanReason).join(' · ')
                : (evidence.reason || 'EVIDENCE_GATE_OPEN');
            q5SetText('lo-autopilot-reason', governanceReason);
            const gateBadge = document.getElementById('learning-observatory-gate');
            if (gateBadge) {
                gateBadge.className = `badge ${positiveAuthority ? 'bg-success' : 'bg-secondary'}`;
                gateBadge.textContent = positiveAuthority ? 'Optimización de calidad habilitada' : 'Recopilando evidencia';
            }
        }

        if (kind === 'gemini' && json.success) {
            const data = json.data || {};
            const state = String(data.state || 'WAITING_FIRST_RUN');
            q5SetText('lo-gemini-state', state === 'SUCCESS' || state === 'READY' || state === 'WORKING' ? 'Activo' : uiHumanLabel(state));
            q5SetText('lo-learning-provider', data.provider_label || uiHumanLabel(data.provider || '--'));
            const last = data.last_run;
            const lastText = last && typeof last === 'object'
                ? (last.created_at || last.timestamp || last.at || '--')
                : (last || '--');
            q5SetText('lo-gemini-last', lastText === '--' ? '--' : formatDate(lastText));
            const scheduler = data.scheduler && typeof data.scheduler === 'object' ? data.scheduler : {};
            const schedulerAt = scheduler.last_attempt_at || '--';
            q5SetText('lo-gemini-scheduler-last', schedulerAt === '--' ? '--' : formatDate(schedulerAt));
            q5SetText('lo-gemini-scheduler-state', uiHumanLabel(scheduler.status || 'UNKNOWN'));
            q5SetText('lo-gemini-fallback', data.fallback_active ? 'Sí' : 'No');
            const schedulerDetail = schedulerAt !== '--'
                ? ` Scheduler: ${uiHumanLabel(scheduler.status || 'UNKNOWN')}.`
                : '';
            q5SetText('lo-gemini-reason', (data.reason ? uiHumanLabel(data.reason) : 'Actividad leída sin realizar llamadas adicionales.') + schedulerDetail);
        }
    });
}


function renderExecutionIntelligenceV2(data) {
    const root = data?.execution_intelligence_v2 || {};
    const shadow = root?.shadow || {};
    const micro = shadow?.microstructure_alignment || {};
    const uncertainty = shadow?.uncertainty_buckets || {};
    const research = shadow?.research_universe || {};
    const wick = root?.wick_resilience?.shadow || {};

    const fmtR = value => {
        const n = Number(value);
        if (!Number.isFinite(n)) return '--';
        return `${n >= 0 ? '+' : ''}${n.toFixed(3)}R`;
    };
    const fmtPct = value => {
        const n = Number(value);
        return Number.isFinite(n) ? `${n.toFixed(1)}%` : '--';
    };
    const fmtN = value => Number(value || 0).toLocaleString();

    q5SetText('c15-micro-aligned-exp', fmtR(micro?.ALIGNED?.expectancy_r));
    q5SetText('c15-uncertainty-low-exp', fmtR(uncertainty?.LOW?.expectancy_r));
    q5SetText(
        'c15-wick-outs',
        `${fmtN(wick?.wick_outs)}${Number.isFinite(Number(wick?.wick_out_rate_pct)) ? ` · ${fmtPct(wick.wick_out_rate_pct)}` : ''}`
    );
    const researchN = Number(research?.['LINK-USDT']?.n || 0) + Number(research?.['BNB-USDT']?.n || 0);
    q5SetText('c15-research-universe', fmtN(researchN));

    const renderRows = (targetId, groups, order, labels) => {
        const body = document.getElementById(targetId);
        if (!body) return;
        body.innerHTML = order.map(key => {
            const item = groups?.[key] || {};
            return `<tr>
                <td>${labels[key] || key}</td>
                <td>${fmtN(item.n)}</td>
                <td>${fmtN(item.resolved)}</td>
                <td>${fmtPct(item.win_rate)}</td>
                <td>${fmtR(item.expectancy_r)}</td>
            </tr>`;
        }).join('');
    };

    renderRows(
        'c15-micro-table', micro,
        ['ALIGNED', 'NEUTRAL', 'CONFLICT'],
        {ALIGNED: 'Alineado', NEUTRAL: 'Neutral', CONFLICT: 'En conflicto'}
    );
    renderRows(
        'c15-uncertainty-table', uncertainty,
        ['LOW', 'MEDIUM', 'HIGH'],
        {LOW: 'Baja', MEDIUM: 'Media', HIGH: 'Alta'}
    );
}

async function loadQualityV2() {

    const statusEl = document.getElementById(
        'q5-v2-status'
    );

    if (statusEl) {

        statusEl.className = (
            'small text-muted mb-3'
        );

        statusEl.textContent = (
            'Cargando rendimiento actual...'
        );
    }

    try {

        const qs = buildQueryString(
            getFilters()
        );

        const response = await fetch(
            '/api/analytics/quality-v2?'
            + qs
        );

        // ============================================================
        // PARSEO ROBUSTO
        // ============================================================
        //
        // Si Render devuelve HTML 502/504 no dejamos caer todo
        // analytics.js con "Unexpected token <".
        // ============================================================

        const rawText = await response.text();

        let json;

        try {

            json = JSON.parse(
                rawText
            );

        } catch (parseError) {

            throw new Error(
                `Respuesta no JSON de Q5 V2 `
                + `(HTTP ${response.status})`
            );
        }

        if (
            !response.ok
            || !json.success
        ) {

            throw new Error(
                json.error
                || `HTTP ${response.status}`
            );
        }

        // Hotfix 16.4: Analytics puede ceder el único slot pesado al trading.
        // Eso no es un error. Conservamos la UI y reintentamos automáticamente.
        if (json.deferred && !json.data) {
            if (statusEl) {
                statusEl.className = 'small text-info mb-3';
                statusEl.textContent = json.note || 'Analytics preparando snapshot sin bloquear el trading...';
            }
            clearTimeout(window.__qualityV2DeferredRetry);
            const retryMs = Math.max(10000, Number(json.retry_after_seconds || 15) * 1000);
            window.__qualityV2DeferredRetry = setTimeout(() => loadQualityV2(), retryMs);
            return;
        }

        clearTimeout(window.__qualityV2DeferredRetry);

        const data = (
            json.data
            || {}
        );

        const spot = (
            data.spot
            || {}
        );

        const futures = (
            data.futures
            || {}
        );

        const shadow = (
            data.futures_shadow
            || {}
        );

        const q7 = (
            data.q7_strategy_lab
            || {}
        );
        
        // ============================================================
        // VERSIONADO
        // ============================================================

        q5SetText(
            'q5-v2-version',
            'Motor de calidad actual'
        );

        // ============================================================
        // TRES COHORTES
        // ============================================================

        q5RenderCohort(
            'spot',
            spot
        );

        q5RenderCohort(
            'futures',
            futures
        );

        q5RenderCohort(
            'shadow',
            shadow,
            {
                shadow:
                    true
            }
        );

        // ============================================================
        // SAFETY -> PERFORMANCE
        // ============================================================

        q5RenderSafetyTable(
            'q5-safety-spot',
            spot.safety_bands
        );

        q5RenderSafetyTable(
            'q5-safety-futures',
            futures.safety_bands
        );

        // ============================================================
        // Q2
        // ============================================================

        q5SetText(
            'q5-q2-official',
            Number(
                futures.q2_refined
                || 0
            ).toLocaleString()
        );

        // ============================================================
        // Q3 MICROESTRUCTURA SHADOW
        // ============================================================

        const q3 = (
            shadow.q3_alignment
            && typeof shadow.q3_alignment
            === 'object'
        )
            ? shadow.q3_alignment
            : {};

        q5SetText(
            'q5-q3-aligned',
            Number(
                q3.ALIGNED
                || 0
            ).toLocaleString()
        );

        q5SetText(
            'q5-q3-neutral',
            Number(
                q3.NEUTRAL
                || 0
            ).toLocaleString()
        );

        q5SetText(
            'q5-q3-conflict',
            Number(
                q3.CONFLICT
                || 0
            ).toLocaleString()
        );

        // Commit 15F — Order Flow / incertidumbre / wick resilience.
        renderExecutionIntelligenceV2(data);

        // ============================================================
        // Q7 STRATEGY LAB
        // ============================================================

        q7RenderStrategyLab(
            q7
        );

        // Observabilidad y autocalibración V1.0.
        renderLearningObservatory(data);
        renderSelfCalibrationV1(data);

        // Hipótesis de edge, siempre research-only.
        renderEdgeDiscovery(data);

        
        // ============================================================
        // COBERTURA
        // ============================================================

        const coverage = (
            data.coverage
            || {}
        );

        q5SetText(
            'q5-coverage',
            (
                'Cobertura V2 · '
                + `Total direccionales: ${
                    Number(
                        coverage.v2_directional_total
                        || 0
                    ).toLocaleString()
                } · `
                + `Spot: ${
                    Number(
                        coverage.spot_v2
                        || 0
                    ).toLocaleString()
                } · `
                + `Futures oficial: ${
                    Number(
                        coverage.futures_official_v2
                        || 0
                    ).toLocaleString()
                } · `
                + `Futures en evaluación: ${
                    Number(
                        coverage.futures_shadow_v2
                        || 0
                    ).toLocaleString()
                }`
            )
        );

        // ============================================================
        // ESTADO
        // ============================================================

        if (statusEl) {

            statusEl.className = coverage.complete === true
                ? 'small text-success mb-3'
                : 'small text-warning mb-3';

            statusEl.textContent = (
                (coverage.complete === true
                    ? '✅ Lectura V2 completa. '
                    : '⚠️ Lectura parcial: no calibrar con esta muestra. ')
                + 'PnL bruto observado; costes no descontados. '
                + 'Spot sin procedencia y Legacy excluidos.'
            );
        }

    } catch (error) {

        console.error(
            'Error Q5 Analytics V2:',
            error
        );

        if (statusEl) {

            statusEl.className = (
                'small text-danger mb-3'
            );

            statusEl.textContent = (
                '❌ No se pudo cargar Analytics V2: '
                + error.message
            );
        }

        const spotBody = document.getElementById(
            'q5-safety-spot'
        );

        const futuresBody = document.getElementById(
            'q5-safety-futures'
        );

        if (spotBody) {

            spotBody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center text-danger">
                        Analytics V2 no disponible
                    </td>
                </tr>
            `;
        }

        if (futuresBody) {

            futuresBody.innerHTML = `
                <tr>
                    <td colspan="8" class="text-center text-danger">
                        Analytics V2 no disponible
                    </td>
                </tr>
            `;
        }
        const q7OfficialBody = document.getElementById(
            'q7-official-body'
        );

        const q7ShadowBody = document.getElementById(
            'q7-shadow-body'
        );

        [
            q7OfficialBody,
            q7ShadowBody
        ].forEach(
            body => {

                if (!body) {
                    return;
                }

                body.innerHTML = `
                    <tr>
                        <td colspan="10" class="text-center text-danger">
                            Análisis de estrategias adaptativas no disponible
                        </td>
                    </tr>
                `;
            }
        );
    }
}

// ============================================================================
// 1. KPIs GLOBALES
// ============================================================================

async function loadSummary() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/summary?' + qs);
        const json = await res.json();
        
        if (!json.success) { console.error('Error summary:', json.error); return; }
        
        const d = json.data;
        
        // ============ KPIs BÁSICOS ============
        document.getElementById('kpi-total').textContent = d.total_signals.toLocaleString();
        document.getElementById('kpi-resolved').textContent = `Resueltas: ${d.resolved.toLocaleString()}`;
        document.getElementById('kpi-winrate').textContent = d.win_rate + '%';
        document.getElementById('kpi-tps').textContent = d.tp_hit;
        document.getElementById('kpi-sls').textContent = d.sl_hit;
        document.getElementById('kpi-expectancy').textContent = (d.expectancy > 0 ? '+' : '') + d.expectancy;
        document.getElementById('kpi-avgwin').textContent = formatPct(d.avg_win_pct, 2);
        document.getElementById('kpi-strategies').textContent = d.unique_strategies;
        document.getElementById('kpi-days').textContent = d.days_back;
        
        // Colorear expectancy según sea positivo o negativo
        const expEl = document.getElementById('kpi-expectancy');
        expEl.style.color = d.expectancy > 0 ? '#00C076' : d.expectancy < 0 ? '#FF5B5B' : '#FFD700';
        
        // ============ KPIs ECONÓMICOS (nuevos v13) ============
        const pnlTotal = d.pnl_total_pct || 0;
        const pnlTotalEl = document.getElementById('kpi-pnl-total');
        if (pnlTotalEl) {
            pnlTotalEl.textContent = (pnlTotal >= 0 ? '+' : '') + pnlTotal.toFixed(2) + '%';
            pnlTotalEl.style.color = pnlTotal > 0 ? '#00C076' : pnlTotal < 0 ? '#FF5B5B' : '#FFD700';
        }
        
        const roi = d.roi_1000usd_estimated || 0;
        const roiEl = document.getElementById('kpi-roi');
        if (roiEl) {
            const usdFinal = 1000 * (1 + roi / 100);
            roiEl.textContent = (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%';
            roiEl.title = `Capital final: $${usdFinal.toFixed(2)}`;
            roiEl.style.color = roi > 0 ? '#00C076' : roi < 0 ? '#FF5B5B' : '#FFD700';
        }
        
        const pf = d.profit_factor || 0;
        const pfEl = document.getElementById('kpi-profit-factor');
        if (pfEl) {
            pfEl.textContent = pf.toFixed(2);
            pfEl.style.color = pf >= 1.5 ? '#00C076' : pf >= 1.0 ? '#FFD700' : '#FF5B5B';
        }
        
        const bestTrade = d.best_trade_pct || 0;
        const worstTrade = d.worst_trade_pct || 0;
        const bestEl = document.getElementById('kpi-best-trade');
        const worstEl = document.getElementById('kpi-worst-trade');
        if (bestEl) bestEl.textContent = (bestTrade >= 0 ? '+' : '') + bestTrade.toFixed(2) + '%';
        if (worstEl) worstEl.textContent = worstTrade.toFixed(2) + '%';
        
        const maxWinsEl = document.getElementById('kpi-max-wins');
        const maxLossesEl = document.getElementById('kpi-max-losses');
        if (maxWinsEl) maxWinsEl.textContent = d.max_consecutive_wins || 0;
        if (maxLossesEl) maxLossesEl.textContent = d.max_consecutive_losses || 0;
        
    } catch (err) {
        console.error('Error loadSummary:', err);
    }
}


// ============================================================================
// 2. RANKING DE ESTRATEGIAS
// ============================================================================

async function loadStrategiesRanking() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/strategies?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.length === 0) {
            Plotly.newPlot('chart-strategies', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos suficientes', font: { size: 14 } },
                height: 500
            });
            return;
        }
        
        const data = json.data;
        // Invertimos para que el top quede arriba en la barra horizontal
        data.reverse();
        
        const trace = {
            type: 'bar',
            orientation: 'h',
            x: data.map(d => d.win_rate),
            y: data.map(d => d.strategy),
            marker: {
                color: data.map(d => d.win_rate >= 60 ? '#00C076' : d.win_rate >= 45 ? '#FFD700' : '#FF5B5B')
            },
            text: data.map(d => `${d.win_rate}% (${d.wins}/${d.wins + d.losses})`),
            textposition: 'outside',
            hovertemplate: '<b>%{y}</b><br>Win Rate: %{x}%<br>Total: %{customdata}<extra></extra>',
            customdata: data.map(d => d.total)
        };
        
        const layout = {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Win Rate (%)', range: [0, 110], gridcolor: 'rgba(255,255,255,0.1)' },
            yaxis: { automargin: true, tickfont: { size: 10 } },
            margin: { l: 250, r: 60, t: 30, b: 40 },
            height: Math.max(500, data.length * 25)
        };
        
        // Línea vertical en 50%
        layout.shapes = [{
            type: 'line', x0: 50, x1: 50, y0: -0.5, y1: data.length - 0.5,
            line: { color: 'rgba(255,255,255,0.3)', dash: 'dash', width: 1 }
        }];
        
        Plotly.newPlot('chart-strategies', [trace], layout, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error strategies:', err);
    }
}


// ============================================================================
// 3. HEATMAP símbolo × timeframe
// ============================================================================

async function loadHeatmap() {
    try {
        const f = getFilters();
        const qs = buildQueryString({ system_type: f.system_type, action: f.action, days_back: f.days_back });
        const res = await fetch('/api/analytics/heatmap?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.symbols.length === 0) {
            Plotly.newPlot('chart-heatmap', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos suficientes', font: { size: 14 } },
                height: 400
            });
            return;
        }
        
        const d = json.data;
        
        // Texto de hover: win_rate + tamaño muestra
        const text = d.win_rates.map((row, i) => 
            row.map((val, j) => val !== null ? `${val}%<br>(${d.sample_sizes[i][j]} señales)` : 'Sin datos')
        );
        
        const trace = {
            type: 'heatmap',
            x: d.timeframes,
            y: d.symbols,
            z: d.win_rates,
            text: text,
            texttemplate: '%{z}%',
            textfont: { color: 'white', size: 11 },
            hoverinfo: 'text',
            colorscale: [
                [0, '#FF5B5B'], [0.4, '#FFD700'], [0.6, '#90EE90'], [1, '#00C076']
            ],
            zmin: 0, zmax: 100,
            colorbar: { title: 'WR %', tickfont: { color: 'white' } }
        };
        
        Plotly.newPlot('chart-heatmap', [trace], {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Timeframe' },
            yaxis: { title: 'Símbolo' },
            height: 400
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error heatmap:', err);
    }
}


// ============================================================================
// 4. TIMELINE
// ============================================================================

async function loadTimeline() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/timeline?bucket=week&' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.dates.length === 0) {
            Plotly.newPlot('chart-timeline', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos', font: { size: 14 } },
                height: 400
            });
            return;
        }
        
        const d = json.data;
        
        const traceWR = {
            x: d.dates,
            y: d.win_rates,
            type: 'scatter', mode: 'lines+markers',
            name: 'Win Rate (%)',
            line: { color: '#00C076', width: 2 },
            marker: { size: 8 },
            hovertemplate: '<b>%{x}</b><br>WR: %{y}%<br>Muestras: %{customdata}<extra></extra>',
            customdata: d.sample_sizes,
            yaxis: 'y'
        };
        
        const traceSamples = {
            x: d.dates,
            y: d.sample_sizes,
            type: 'bar',
            name: 'Cantidad señales',
            marker: { color: 'rgba(58, 139, 255, 0.3)' },
            yaxis: 'y2'
        };
        
        Plotly.newPlot('chart-timeline', [traceSamples, traceWR], {
            ...PLOTLY_LAYOUT_BASE,
            xaxis: { title: 'Semana' },
            yaxis: { title: 'Win Rate (%)', range: [0, 100], gridcolor: 'rgba(255,255,255,0.1)' },
            yaxis2: { title: 'Señales', overlaying: 'y', side: 'right', gridcolor: 'rgba(255,255,255,0)' },
            height: 400,
            legend: { orientation: 'h', y: -0.15 },
            shapes: [{
                type: 'line', xref: 'paper',
                x0: 0, x1: 1, y0: 50, y1: 50,
                line: { color: 'rgba(255,255,255,0.3)', dash: 'dash', width: 1 }
            }]
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error timeline:', err);
    }
}


// ============================================================================
// 5. DISTRIBUCIÓN DE PnL
// ============================================================================

async function loadPnLDistribution() {
    try {
        const qs = buildQueryString(getFilters());
        const res = await fetch('/api/analytics/pnl_distribution?' + qs);
        const json = await res.json();
        
        if (!json.success || !json.data || json.data.total === 0) {
            Plotly.newPlot('chart-pnl', [], {
                ...PLOTLY_LAYOUT_BASE,
                title: { text: 'Sin datos', font: { size: 14 } },
                height: 350
            });
            return;
        }
        
        const d = json.data;
        
        const trace = {
            type: 'bar',
            x: d.labels,
            y: d.counts,
            marker: { color: d.colors },
            text: d.counts,
            textposition: 'outside',
            hovertemplate: '<b>%{x}</b><br>Señales: %{y}<extra></extra>'
        };
        
        Plotly.newPlot('chart-pnl', [trace], {
            ...PLOTLY_LAYOUT_BASE,
            title: { 
                text: `Total: ${d.total} señales · Positivas: ${d.positive} · Negativas: ${d.negative} · Media: ${formatPct(d.mean, 2)}`,
                font: { size: 12 }
            },
            xaxis: { title: 'Rango de PnL' },
            yaxis: { title: 'Cantidad', gridcolor: 'rgba(255,255,255,0.1)' },
            height: 350
        }, PLOTLY_CONFIG);
        
    } catch (err) {
        console.error('Error pnl:', err);
    }
}


// ============================================================================
// 6. TABLAS: MEJORES Y PEORES OPERACIONES
// ============================================================================

async function loadTopOperations(mode = 'best') {
    try {
        const qs = buildQueryString({ ...getFilters(), mode, top_n: 10 });
        const res = await fetch('/api/analytics/top_operations?' + qs);
        const json = await res.json();
        
        const tbodyId = mode === 'best' ? 'tbody-best' : 'tbody-worst';
        const tbody = document.getElementById(tbodyId);
        
        if (!json.success || !json.data || json.data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">Sin datos</td></tr>';
            return;
        }
        
        let html = '';
        json.data.forEach(op => {
            const pnlClass = op.pnl_pct >= 0 ? 'status-tp' : 'status-sl';
            const actionColor = op.action === 'LONG' ? 'success' : 'danger';
            html += `
                <tr onclick="window.showOperationDetail('${op.id}')">
                    <td><small>${op.symbol.replace('-', '/')}</small></td>
                    <td><small>${op.timeframe}</small></td>
                    <td><span class="badge bg-${actionColor}">${op.action}</span></td>
                    <td class="${pnlClass}">${formatPct(op.pnl_pct)}</td>
                    <td><small>${formatDate(op.created_at)}</small></td>
                    <td><i class="fas fa-search-plus text-info"></i></td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        
    } catch (err) {
        console.error('Error top ops:', err);
    }
}


// ============================================================================
// 7. DETALLE DE OPERACIÓN (modal)
// ============================================================================

window.showOperationDetail = async function(signalId) {
    const body = document.getElementById('opDetailBody');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div></div>';
    
    const modal = new bootstrap.Modal(document.getElementById('opDetailModal'));
    modal.show();
    
    try {
        const res = await fetch(`/api/analytics/operation_detail/${signalId}`);
        const json = await res.json();
        
        if (!json.success) {
            body.innerHTML = `<div class="alert alert-danger">${json.error || 'Error'}</div>`;
            return;
        }
        
        const op = json.data;
        const result = op.result || {};
        const statusColor = {
            'tp_hit': 'success', 'sl_hit': 'danger', 'expired': 'warning', 'pending': 'secondary'
        }[op.status] || 'secondary';
        
        const strategiesHTML = (op.strategies || []).map(s => 
            `<span class="badge bg-secondary me-1 mb-1">${s}</span>`
        ).join('');
        
        // Indicadores snapshot destacados
        const snapshot = op.indicators_snapshot || {};
        const context = op.context || {};
        
        body.innerHTML = `
            <div class="row g-3">
                <!-- Info principal -->
                <div class="col-md-6">
                    <div class="card bg-dark border-secondary">
                        <div class="card-header">
                            <strong>${op.symbol.replace('-', '/')} · ${op.timeframe}</strong>
                            <span class="badge bg-${op.action === 'LONG' ? 'success' : 'danger'} ms-2">${op.action}</span>
                            <span class="badge bg-${statusColor} ms-1">${op.status}</span>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-6"><small class="text-muted">Sistema:</small><br>${op.system_type}</div>
                                <div class="col-6"><small class="text-muted">Confianza:</small><br><strong>${op.confidence}%</strong></div>
                            </div>
                            <hr class="my-2">
                            <div class="row small">
                                <div class="col-6">
                                    <div class="text-muted">Entry:</div>
                                    <strong>${op.entry_price}</strong>
                                </div>
                                <div class="col-6">
                                    <div class="text-muted">Exit:</div>
                                    <strong>${result.exit_price || '--'}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Stop Loss:</div>
                                    <strong class="text-danger">${op.stop_loss}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Take Profit:</div>
                                    <strong class="text-success">${op.take_profit}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">R/R:</div>
                                    <strong>1:${op.risk_reward}</strong>
                                </div>
                                <div class="col-6 mt-2">
                                    <div class="text-muted">Leverage:</div>
                                    <strong>${op.leverage}x</strong>
                                </div>
                                <div class="col-12 mt-3 text-center">
                                    <div class="text-muted">PnL final</div>
                                    <strong class="h4 ${(result.pnl_pct || 0) >= 0 ? 'text-success' : 'text-danger'}">
                                        ${formatPct(result.pnl_pct, 2)}
                                    </strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Indicadores + Estrategias -->
                <div class="col-md-6">
                    <div class="card bg-dark border-info mb-2">
                        <div class="card-header"><strong>🎯 Estrategias detectadas</strong></div>
                        <div class="card-body">${strategiesHTML || '<em class="text-muted">Ninguna</em>'}</div>
                    </div>
                    
                    <div class="card bg-dark border-secondary">
                        <div class="card-header"><strong>📊 Snapshot de indicadores</strong></div>
                        <div class="card-body small">
                            <div class="row">
                                <div class="col-6">ADX: <strong>${(snapshot.adx || 0).toFixed(1)}</strong></div>
                                <div class="col-6">RSI: <strong>${(snapshot.rsi || 0).toFixed(1)}</strong></div>
                                <div class="col-6">MACD: <strong>${(snapshot.macd_hist || 0).toFixed(2)}</strong></div>
                                <div class="col-6">MFI: <strong>${(snapshot.mfi || 0).toFixed(1)}</strong></div>
                                <div class="col-6">ATR%: <strong>${(snapshot.atr_pct || 0).toFixed(2)}</strong></div>
                                <div class="col-6">Vol ratio: <strong>${(snapshot.volume_ratio || 1).toFixed(2)}</strong></div>
                                <div class="col-6">Trend: <strong>${snapshot.trend_direction || '--'}</strong></div>
                                <div class="col-6">FTM: <strong>${snapshot.ftm_state || '--'}</strong></div>
                            </div>
                            <hr class="my-2">
                            <div class="row">
                                <div class="col-6">🐋 Whale buy: <strong>${snapshot.whale_buy ? 'sí' : 'no'}</strong></div>
                                <div class="col-6">🐋 Whale sell: <strong>${snapshot.whale_sell ? 'sí' : 'no'}</strong></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card bg-dark border-primary mt-2">
                        <div class="card-header"><strong>🌐 Contexto</strong></div>
                        <div class="card-body small">
                            <div>Sesión: <strong>${context.session || '--'}</strong> | Día: <strong>${context.day_type || '--'}</strong></div>
                            ${context.fear_greed ? `<div>Fear & Greed: <strong>${context.fear_greed}</strong> (${context.sentiment_bias || 'neutral'})</div>` : ''}
                            ${context.rotation_signal ? `<div>Rotación: <strong>${context.rotation_signal}</strong></div>` : ''}
                        </div>
                    </div>
                </div>
                
                <!-- Timestamps -->
                <div class="col-12">
                    <div class="card bg-dark border-secondary">
                        <div class="card-body small">
                            <div class="row">
                                <div class="col-md-4">🕐 <strong>Señal creada:</strong> ${formatDate(op.created_at)}</div>
                                <div class="col-md-4">🕒 <strong>Vela evaluada:</strong> ${formatDate(op.candle_timestamp)}</div>
                                <div class="col-md-4">🕓 <strong>Cerrada:</strong> ${formatDate(op.closed_at)}</div>
                            </div>
                            ${result.candles_to_result ? `<div class="mt-2">⏱️ Tardó <strong>${result.candles_to_result}</strong> velas en resolverse</div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
    } catch (err) {
        console.error('Error detail:', err);
        body.innerHTML = `<div class="alert alert-danger">Error: ${err.message}</div>`;
    }
};


// ============================================================================
// 8. LOGS DEL REVIEWTRADER
// ============================================================================

window.loadLogs = async function() {
    const container = document.getElementById('logs-container');
    container.innerHTML = '<div class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm text-info"></div> Cargando logs...</div>';
    
    try {
        const res = await fetch('/api/review/logs?limit=30');
        
        // v22.6: manejar caso de HTML de error (502/504 del gunicorn).
        // Antes: res.json() lanzaba "Unexpected token '<'" y todo caía sin
        // mensaje claro. Ahora: leer como texto primero y validar.
        const text = await res.text();
        let json;
        try {
            json = JSON.parse(text);
        } catch (parseErr) {
            container.innerHTML = `
                <div class="alert alert-warning py-3">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    El servidor respondió con un error (status ${res.status}). Es probable que estuviera saturado. Recarga la página en unos segundos.
                </div>
            `;
            console.error('loadLogs: respuesta no-JSON', text.slice(0, 200));
            return;
        }
        
        if (!json.success || !json.logs || json.logs.length === 0) {
            const errMsg = json.error ? ` (${json.error})` : '';
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-info-circle me-1"></i>
                    Aún no hay logs${errMsg}. Ejecuta el ReviewTrader manualmente o espera al ciclo diario (20:00 Bolivia).
                </div>
            `;
            return;
        }
        
        let html = '';
        json.logs.forEach(log => {
            const statusClass = log.status === 'failed' ? 'log-error' : log.status === 'partial' ? 'log-partial' : '';
            const statusIcon = log.status === 'success' ? '✅' : log.status === 'partial' ? '⚠️' : '❌';
            const triggerIcon = log.trigger_source === 'scheduler' ? '⏰' : '👤';
            
            const errorsHTML = (log.errors && log.errors.length > 0) 
                ? `<div class="mt-2 text-danger small">❌ Errores: ${log.errors.join(' · ')}</div>`
                : '';
            
            const storage = log.storage_stats || {};
            const totalRows = Object.values(storage).reduce((a, b) => a + (b > 0 ? b : 0), 0);
            
            html += `
                <div class="log-entry ${statusClass}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <strong>${statusIcon} ${formatDate(log.run_started_at)}</strong>
                            <span class="badge bg-secondary ms-2">${triggerIcon} ${log.trigger_source}</span>
                            <span class="badge bg-dark ms-1">${log.duration_seconds}s</span>
                        </div>
                        <small class="text-muted">${log.status.toUpperCase()}</small>
                    </div>
                    <div class="mt-2 small">
                        <span class="me-3">📊 Evaluadas: <strong>${log.signals_evaluated}</strong></span>
                        <span class="me-3 text-success">✅ TP: <strong>${log.tp_hits}</strong></span>
                        <span class="me-3 text-danger">❌ SL: <strong>${log.sl_hits}</strong></span>
                        <span class="me-3 text-warning">⏰ Exp: <strong>${log.expired}</strong></span>
                        <span class="me-3 text-info">💡 Oport. perdidas: <strong>${log.missed_opportunities_found}</strong></span>
                    </div>
                    <div class="mt-1 small text-muted">
                        📈 Stats: ${log.stats_specific_updated} específicas · ${log.stats_general_updated} generales
                        · 🧹 TTL: ${log.ttl_deleted} borradas · Compresión: ${log.low_sample_deleted}
                        · 💾 Total BD: ${totalRows} filas
                    </div>
                    ${log.notes ? `<div class="mt-1 small">📝 ${log.notes}</div>` : ''}
                    ${errorsHTML}
                </div>
            `;
        });
        
        container.innerHTML = html;
        
    } catch (err) {
        console.error('Error logs:', err);
        container.innerHTML = `<div class="alert alert-danger">Error cargando logs: ${err.message}</div>`;
    }
};


// ============================================================================
// EJECUTAR REVIEWTRADER MANUALMENTE
// ============================================================================

window.runReviewManually = async function() {
    if (!confirm('¿Ejecutar el ciclo completo del ReviewTrader?\n\nEsto puede tardar 1-2 minutos.')) return;
    
    showToast('🎓 Ejecutando ReviewTrader... esto tardará 1-2 minutos.', 'info');
    
    try {
        const res = await fetch('/api/review/run_now', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Key': 'crypto_trader_analyst_2025'
            }
        });
        
        const json = await res.json();
        
        if (!json.success) {
            showToast('Error: ' + (json.error || 'desconocido'), 'danger');
            return;
        }
        
        const r = json.results || {};
        const ev = r.evaluated || {};
        showToast(
            `✅ ReviewTrader completo: ${ev.tp_hit || 0} TP, ${ev.sl_hit || 0} SL, ${r.missed || 0} oportunidades.`,
            'success'
        );
        
        // Refrescar todos los datos
        window.loadAllAnalytics();
        window.loadLogs();
        
    } catch (err) {
        showToast('Error de conexión: ' + err.message, 'danger');
    }
};


// ============================================================================
// CARGAR TODO
// ============================================================================

window.loadAllAnalytics = async function() {

    showToast(
        '🔄 Actualizando estadísticas...',
        'info'
    );

    // HOTFIX 14.6: no lanzar 9 lecturas estadísticas simultáneas.
    // En Render Free, cada respuesta puede materializar cientos/miles de filas
    // y los picos concurrentes eran capaces de superar 512 MB. El usuario ve
    // la misma información, pero se carga secuencialmente y cede el event loop
    // entre paneles.
    const tasks = [
        () => loadQualityV2(),
        () => loadLearningGovernanceStatus(),
        () => loadResearchFederationAnalytics(),
        () => loadSummary(),
        () => loadStrategiesRanking(),
        () => loadHeatmap(),
        () => loadTimeline(),
        () => loadPnLDistribution(),
        () => loadTopOperations('best'),
        () => loadTopOperations('worst')
    ];
    for (const task of tasks) {
        try {
            await task();
        } catch (err) {
            console.warn('Analytics parcial:', err);
        }
        await new Promise(resolve => setTimeout(resolve, 80));
    }

    showToast(
        '✅ Estadísticas actualizadas',
        'success'
    );
};

// ============================================================================
// INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('📈 Página Analytics inicializada');
    
    // Carga inicial
    window.loadAllAnalytics();
    window.loadLogs();

    const governanceButton = document.getElementById('lo-refresh-governance');
    if (governanceButton) governanceButton.addEventListener('click', refreshLearningGovernanceNow);
    const learningButton = document.getElementById('lo-test-learning');
    if (learningButton) learningButton.addEventListener('click', runLearningScientistTest);
    const researchButton = document.getElementById('rf-analytics-refresh');
    if (researchButton) researchButton.addEventListener('click', loadResearchFederationAnalytics);

    
    // ================================================================
    // AUTO-REFRESH LEGACY
    // ================================================================
    //
    // Mantiene exactamente la frecuencia existente.
    // ================================================================

    setInterval(
        () => {

            loadSummary();

            window.loadLogs();

        },
        300000
    );


    // ================================================================
    // QUALITY ENGINE Q5
    // ================================================================
    //
    // Q5 lee context JSON de la cohorte nueva.
    //
    // No tiene sentido ejecutarlo cada minuto ni cada 5 minutos.
    //
    // El learning worker ya trabaja en ciclos de aproximadamente
    // 15 minutos y este intervalo protege los 512 MB de Render.
    // ================================================================

    setInterval(
        () => {

            loadQualityV2();

        },
        900000
    );

});


// ============================================================================
// COMMIT 16 — RESEARCH FEDERATION: Backtest → OOS → Shadow live
// Una sola respuesta compacta. No materializa señales históricas en Render.
// ============================================================================
async function loadResearchFederationAnalytics(){
    const body=document.getElementById('rf-analytics-body');
    if(!body) return;
    try{
        const response=await fetch('/api/research-federation/summary',{cache:'no-store'});
        const data=await response.json();
        if(!response.ok || !data.success) throw new Error(data.error||'Research Federation no disponible');
        const candidates=data.candidates||[], shadow=data.shadow_live||[];
        const coverage=data.coverage||{};
        const profitability=data.profitability_evidence||{};
        const strategic=coverage.strategic_timeframes||{};
        const covEl=document.getElementById('rf-analytics-coverage');
        if(covEl){
            const parts=['4H','12H','1D','1W'].map(tf=>`${tf}: ${Number(strategic[tf]||0)}`);
            const missing=(coverage.missing_strategic_timeframes||[]);
            covEl.className=`small mb-2 ${missing.length?'text-warning':'text-success'}`;
            const causalInfo=data.profitability_evidence||{};
            const causal=`Causal ${Number(causalInfo.coverage_cells||0)}/${Number(causalInfo.coverage_target||18)}`;
            covEl.textContent=`Cobertura estratégica · ${parts.join(' · ')} · ${causal}${missing.length?` · Sin evidencia actual: ${missing.join(', ')}`:''}`;
        }
        const sm=new Map(shadow.map(x=>[x.candidate_key,x]));
        const actionable=candidates.filter(x=>['SHADOW_READY_FAST','SHADOW_READY','VALIDATED_SINGLE_ASSET','VALIDATION_REQUIRED','REJECTED_OOS','OBSERVE'].includes(String(x.stage||'')));
        const fmt=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toFixed(d):'--';
        const pct=v=>Number.isFinite(Number(v))?`${Number(v).toFixed(1)}%`:'--';
        const renderBt=(bucket, emptyLabel='Sin estrategia OOS validada todavía')=>{
            if(!bucket || bucket.state==='NO_EVIDENCE') return `<span class="text-muted">${emptyLabel}</span>`;
            const best=bucket.best||{};
            const state=bucket.state==='VALIDATED_OOS_POSITIVE'?'✅ OOS validado':'🟡 candidato';
            return `${state} · Estrategias validadas ${Number(bucket.validated_strategies||0)} · OOS N ${Number(bucket.oos_n||0)} · Exp. ponderada ${fmt(bucket.oos_exp_r_weighted,3)}R`
                + (best.oos_pf!=null?` · Mejor PF ${fmt(best.oos_pf,2)}`:'')
                + (best.scope?.timeframe?` · Mejor TF ${best.scope.timeframe}`:'');
        };
        const spotBt=document.getElementById('q5-spot-backtest');
        if(spotBt) spotBt.innerHTML=renderBt(profitability.spot);
        const futBt=document.getElementById('q5-futures-backtest');
        if(futBt) futBt.innerHTML=renderBt(profitability.futures_official,'Aún no hay Futures SHADOW_READY causal; no se fuerza rentabilidad.');
        const shadowBt=document.getElementById('q5-shadow-backtest');
        if(shadowBt) shadowBt.innerHTML=renderBt(profitability.futures_evaluation,'Sin challengers causales disponibles.');
        const coverageLabel = profitability.coverage_target ? ` · Causal ${Number(profitability.coverage_cells||0)}/${Number(profitability.coverage_target||18)}` : '';
        body.innerHTML=actionable.slice(0,80).map(x=>{const l=sm.get(x.candidate_key)||{};return `<tr>
          <td><span class="badge bg-secondary">${x.stage||'--'}</span></td>
          <td><b>${x.source_engine||'--'}</b><br><span class="text-muted small">${x.experiment||'--'}</span></td>
          <td>${x.market_family||'--'} · ${x.timeframe||'--'}</td>
          <td>${x.backtest_n??0} / ${pct(x.backtest_wr)} / ${fmt(x.backtest_exp_r,3)}R</td>
          <td>${x.oos_n??0} / ${pct(x.oos_wr)} / ${fmt(x.oos_exp_r,3)}R / ${fmt(x.oos_pf,2)}</td>
          <td>${l.resolved_n??0}/${l.signals_n??0} / ${pct(l.win_rate_pct)} / ${fmt(l.expectancy_r,3)}R / ${fmt(l.profit_factor,2)}</td>
          <td>${fmt(l.avg_safety,1)}</td></tr>`}).join('') || `<tr><td colspan="7" class="text-muted text-center">${data.connected===false?'Research Bridge sin conexión':'Bridge conectado, pero todavía no hay filas visibles para esta cuenta/clave.'}</td></tr>`;
        const stages={}; candidates.forEach(x=>stages[x.stage]=(stages[x.stage]||0)+1);
        const kp=document.getElementById('rf-analytics-kpis');
        if(kp) kp.innerHTML=[['Hallazgos',candidates.length],['Shadow Ready',(stages.SHADOW_READY||0)+(stages.SHADOW_READY_FAST||0)],['Shadow live',shadow.reduce((a,x)=>a+Number(x.signals_n||0),0)],['Rechazados OOS',stages.REJECTED_OOS||0]].map(([k,v])=>`<div class="col-6 col-md-3"><div class="border rounded p-2 h-100"><div class="text-muted small">${k}</div><div class="h5 mb-0">${v}</div></div></div>`).join('');
    }catch(err){body.innerHTML=`<tr><td colspan="7" class="text-warning">${err.message}</td></tr>`;}
}
window.loadResearchFederationAnalytics=loadResearchFederationAnalytics;
