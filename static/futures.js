// futures.js - Solo se carga en la página /futures
// SOBREESCRIBE las funciones de script.js que consultan spot para que consulten
// solo los endpoints /api/futures/* con los símbolos y timeframes de futuros.
// También añade el panel del ReviewTrader y adapta la correlación.

console.log(`🚀 futures.js cargado - modo ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futuros'} activo`);

const DERIV_API_BASE = window.DERIV_API_BASE || (window.IS_MULTI_ASSET_PAGE ? '/api/multiasset' : '/api/futures');
const DERIV_MARKET_LABEL = window.IS_MULTI_ASSET_PAGE ? 'derivados Multi-Activo' : 'Futures';
function futDisplaySymbol(symbol, explicitName = '') {
    const key = String(symbol || '').toUpperCase();
    return explicitName || window.PAGE_CONFIG?.symbols?.[key] || key.replace('-', '/');
}
function _derivPageSymbols(rows) {
    const allowed = new Set(Object.keys(window.PAGE_CONFIG?.symbols || {}));
    return (Array.isArray(rows) ? rows : []).filter(row => allowed.size === 0 || allowed.has(String(row?.symbol || '').toUpperCase().replace('/', '-')));
}


// ============================================================================
// CONTROL DE CARGA DE SEÑALES FUTUROS
// Evita peticiones simultáneas al mismo caché pesado.
// ============================================================================
window._futuresSignalsState = {
    activeLoading: false,
    previousLoading: false,
    activeTimer: null,
    previousTimer: null
};
// Helper global: nunca mostrar confianza > 100% (defensa contra datos viejos).
function fmtConfidence(c) {
    const n = Number(c) || 0;
    const capped = Math.max(0, Math.min(100, n));
    return capped.toFixed(0);
}
window.fmtConfidence = fmtConfidence;


// ============================================================================
// UTILIDADES
// ============================================================================

function futShowToast(msg, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(msg, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${msg}`);
    }
}

function futFormatPct(val, decimals = 2) {
    if (val === null || val === undefined) return '--';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${Number(val).toFixed(decimals)}%`;
}

function futFormatPrice(price, symbol) {
    if (price === null || price === undefined) return '--';
    const decimals = (symbol && (symbol.includes('XRP') || symbol.includes('ADA'))) ? 4 : 2;
    return '$' + Number(price).toFixed(decimals);
}

function futFormatDuration(seconds) {
    if (!seconds || seconds <= 0) return '--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function futEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}


// ============================================================================
// RC9.8.2 — VISIBILIDAD PERSONAL DE SEÑALES GUARDADAS
// ============================================================================
//
// La señal de mercado es global. El acto de guardarla es personal.
// Por eso NO se modifica /previous, /active ni el lifecycle compartido.
// Sólo se oculta, para el usuario autenticado actual, una Confirmada/Vigente
// que ese mismo usuario ya guardó. Otro usuario sigue viendo la señal global.
//
// Al borrar (soft delete) la señal guardada, /api/saved_signals deja de
// devolverla y la señal reaparece automáticamente en el carril global que aún
// corresponda, siempre que siga confirmada/vigente.
// ============================================================================
window._userSavedSignalRefs = {
    sourceIds: new Set(),
    fingerprints: new Set(),
    loadedAt: 0,
    loadingPromise: null,
    userKey: null
};

// ============================================================================
// RC10.2 FINAL — enlace profundo a señal Futures / señal guardada
// ============================================================================
window.applyFuturesSignalDeepLink = function applyFuturesSignalDeepLink() {
    try {
        const params = new URLSearchParams(window.location.search || '');
        const savedId = String(params.get('saved_signal_id') || '').trim();
        if (savedId && typeof window.openSavedSignalDetail === 'function') {
            setTimeout(() => window.openSavedSignalDetail(savedId), 50);
            return true;
        }
        const signalId = String(params.get('signal_id') || '').trim();
        if (!signalId) return false;
        const safe = (window.CSS && CSS.escape) ? CSS.escape(signalId) : signalId.replace(/['"\\]/g, '');
        const node = document.querySelector(`[data-signal-id="${safe}"]`);
        if (!node) return false;
        node.scrollIntoView({behavior: 'smooth', block: 'center'});
        node.classList.add('border-info');
        setTimeout(() => node.classList.remove('border-info'), 6000);
        if (typeof node.click === 'function') node.click();
        return true;
    } catch (err) {
        console.debug('Deep link Futures no aplicado:', err);
        return false;
    }
};

function _currentSavedSignalUserKey() {
    const user = typeof window.getSmartTradingUser === 'function'
        ? window.getSmartTradingUser()
        : (
            typeof window.getAuthenticatedUser === 'function'
                ? window.getAuthenticatedUser()
                : null
        );
    return String(user || '').trim();
}

function _savedSignalFingerprint(signal) {
    if (!signal || typeof signal !== 'object') return '';
    const symbol = String(signal.symbol || '').trim().toUpperCase();
    const timeframe = String(signal.timeframe || '').trim();
    const action = String(signal.action || signal.decision || '').trim().toUpperCase();
    const candle = String(
        signal.source_candle_timestamp
        || signal.candle_timestamp
        || signal.previous_candle_timestamp
        || ''
    ).trim();
    if (!symbol || !timeframe || !action || !candle) return '';
    return `${symbol}|${timeframe}|${action}|${candle}`;
}

function _replaceUserSavedSignalRefs(rows) {
    const sourceIds = new Set();
    const fingerprints = new Set();
    (Array.isArray(rows) ? rows : []).forEach(row => {
        const sourceId = String(row?.source_signal_id || '').trim();
        if (sourceId) sourceIds.add(sourceId);
        const fingerprint = _savedSignalFingerprint(row);
        if (fingerprint) fingerprints.add(fingerprint);
    });
    window._userSavedSignalRefs.sourceIds = sourceIds;
    window._userSavedSignalRefs.fingerprints = fingerprints;
    window._userSavedSignalRefs.loadedAt = Date.now();
}

window.refreshUserSavedSignalRefs = async function(force = false) {
    const state = window._userSavedSignalRefs;
    const currentUserKey = _currentSavedSignalUserKey();

    // RC9.8.2: nunca reutilizar el índice visual de Willer para Danilo (o viceversa)
    // si la sesión cambia sin recargar la pestaña.
    if (state.userKey !== currentUserKey) {
        state.sourceIds = new Set();
        state.fingerprints = new Set();
        state.loadedAt = 0;
        state.loadingPromise = null;
        state.userKey = currentUserKey;
    }

    const fresh = state.loadedAt > 0 && (Date.now() - state.loadedAt) < 30000;
    if (!force && fresh) return state;
    if (state.loadingPromise) return state.loadingPromise;

    state.loadingPromise = (async () => {
        try {
            const response = await fetch('/api/saved_signals?limit=500', {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            });
            if (response.status === 401) {
                _replaceUserSavedSignalRefs([]);
                return state;
            }
            const json = await response.json();
            if (!response.ok || !json.success) {
                throw new Error(json.error || `HTTP ${response.status}`);
            }
            // El endpoint ya filtra por _authenticated_user() y excluye deleted.
            _replaceUserSavedSignalRefs(_derivPageSymbols(json.signals || []));
            state.userKey = currentUserKey;
        } catch (error) {
            // Fallo de esta capa visual nunca debe ocultar señales globales.
            console.warn('⚠️ RC9.8.2: no se pudo cargar índice personal guardado:', error);
        } finally {
            state.loadingPromise = null;
        }
        return state;
    })();

    return state.loadingPromise;
};

function _isSignalSavedByCurrentUser(signal) {
    const state = window._userSavedSignalRefs;
    const sourceId = String(signal?.signal_id || signal?.source_signal_id || '').trim();
    if (sourceId && state.sourceIds.has(sourceId)) return true;
    const fingerprint = _savedSignalFingerprint(signal);
    return Boolean(fingerprint && state.fingerprints.has(fingerprint));
}

window.refreshSignalLanesAfterSavedChange = async function() {
    await window.refreshUserSavedSignalRefs(true);
    // Cada función conserva su propio lock; no tocamos caches/lifecycle globales.
    if (typeof window.updateActiveSignals === 'function') {
        window.updateActiveSignals();
    }
    if (typeof window.updatePreviousSignals === 'function') {
        window.updatePreviousSignals();
    }
};

function futPublicAnalysisRole(name, index) {
    const key = String(name || '').toLowerCase();
    if (key.includes('técnico') || key.includes('tecnico')) return 'Tendencia e indicadores';
    if (key.includes('chart')) return 'Estructura y patrones';
    if (key.includes('ballena')) return 'Volumen anómalo y reacción';
    if (key.includes('macro')) return 'Contexto macro';
    if (key.includes('pullback')) return 'Retrocesos y timing';
    if (key.includes('smart')) return 'Liquidez y zona de entrada';
    if (key.includes('escépt') || key.includes('escept')) return 'Control de calidad';
    if (key.includes('multi')) return 'Contexto multitemporal';
    if (key.includes('liquid')) return 'Riesgo de liquidaciones';
    if (key.includes('revisión') || key.includes('revision')) return 'Evidencia estadística';
    return `Criterio técnico ${Number(index || 0) + 1}`;
}

function futPublicAuditText(value) {
    return String(value || '')
        .replace(/Escéptico/gi, 'control de calidad')
        .replace(/Trader de Revisión/gi, 'evidencia estadística')
        .replace(/Smart Money/gi, 'liquidez y entrada')
        .replace(/comité/gi, 'conjunto de evidencias')
        .replace(/veto/gi, 'objeción')
        .replace(/réplica/gi, 'confirmación alternativa');
}

function futRenderDecisionAudit(audit) {
    if (!audit || audit.schema_version !== 'DECISION_AUDIT_V1') {
        return '';
    }

    const trace = audit.moderator_trace || {};
    const input = audit.input_snapshot || {};
    const contract = audit.data_contract || {};
    const votes = Array.isArray(audit.votes) ? audit.votes : [];

    const numberText = (value, decimals = 2) => {
        const number = Number(value);
        return Number.isFinite(number) ? number.toFixed(decimals) : '--';
    };
    const dispositionMeta = {
        APOYO_FINAL: ['success', 'COINCIDE'],
        APOYO_AL_VETO: ['warning text-dark', 'OBJECIÓN DE CONTROL'],
        OPOSICION_DIRECCIONAL: ['warning text-dark', 'LECTURA CONTRARIA'],
        CAUTELA_ESPERAR: ['info text-dark', 'PIDE ESPERAR'],
        CAUTELA_NO_OPERAR: ['secondary', 'PIDE NO OPERAR'],
        ABSTENCION: ['secondary', 'SIN SEÑAL'],
        ERROR_CONTROLADO: ['secondary', 'NO DISPONIBLE']
    };

    let votesHtml = '';
    votes.forEach((vote, voteIndex) => {
        const disposition = String(vote.disposition || 'ABSTENCION');
        const meta = dispositionMeta[disposition]
            || dispositionMeta.ABSTENCION;
        const originalAction = String(vote.original_action || 'NO_OPERAR');
        const normalizedAction = String(
            vote.normalized_action || originalAction
        );
        const actionText = originalAction === normalizedAction
            ? futEscapeHtml(normalizedAction)
            : `${futEscapeHtml(originalAction)} → ${futEscapeHtml(normalizedAction)}`;
        const counted = vote.counted_confidence;
        const countedText = counted === null || counted === undefined
            ? 'sin aporte direccional'
            : `aporte ${numberText(counted, 1)}%`;
        const reasons = Array.isArray(vote.reasons) ? vote.reasons : [];
        const strategies = Array.isArray(vote.strategies) ? vote.strategies : [];
        const explanation = reasons[0]
            || (strategies.length > 0 ? strategies.join(', ') : 'Sin razón declarada');

        votesHtml += `
            <div class="border-top border-secondary py-2">
                <div class="d-flex flex-wrap justify-content-between gap-1">
                    <strong>${futEscapeHtml(futPublicAnalysisRole(vote.trader, voteIndex))}</strong>
                    <span class="badge bg-${meta[0]}">${meta[1]}</span>
                </div>
                <div class="small text-light mt-1">
                    Lectura: <strong>${actionText}</strong> ·
                    confianza ${numberText(vote.original_confidence, 1)}%
                </div>
                <div class="small text-muted">
                    ${numberText(vote.original_confidence, 1)}%
                    · contexto ${numberText(vote.regime_multiplier, 2)}
                    · evidencia ${numberText(vote.review_multiplier, 2)}
                    · aporte final ${numberText(vote.weighted_confidence, 1)}%
                    · ${countedText}
                </div>
                <div class="small text-secondary mt-1">
                    ${futEscapeHtml(futPublicAuditText(explanation))}
                </div>
            </div>
        `;
    });

    const provider = futEscapeHtml(contract.provider || 'pendiente del wrapper');
    const candleTimestamp = futEscapeHtml(
        contract.source_candle_timestamp
        || input.analysis_candle_timestamp
        || '--'
    );
    const synthetic = contract.is_synthetic;
    const syntheticText = synthetic === false
        ? 'datos reales (no sintéticos)'
        : (synthetic === true ? 'datos sintéticos' : 'origen aún no declarado');
    const finalReasons = Array.isArray(trace.final_reasons)
        ? trace.final_reasons
        : [];

    return `
        <details class="mt-2 border border-secondary rounded p-2"
                 onclick="event.stopPropagation();">
            <summary class="text-info" style="cursor:pointer;">
                🔎 Cómo se evaluó la señal · ${votes.length} criterios
            </summary>
            <div class="small mt-2">
                <div>
                    <strong>Datos recibidos:</strong> ${provider} ·
                    ${futEscapeHtml(syntheticText)} · vela ${candleTimestamp}
                </div>
                <div class="text-muted">
                    Régimen ${futEscapeHtml(input.market_regime || 'DESCONOCIDO')}
                    (${numberText(input.market_regime_confidence, 1)}%) ·
                    ADX ${numberText(input.adx, 1)} ·
                    ATR ${numberText(input.atr_pct, 2)}% ·
                    volumen ${numberText(input.volume_ratio, 2)}x
                </div>
                <div class="mt-2">
                    <strong>Resultado del análisis:</strong>
                    resultado ${futEscapeHtml(trace.final_action || 'NO_OPERAR')}
                    (${numberText(trace.final_confidence, 1)}%) · evaluación completada
                </div>
                ${finalReasons.length > 0 ? `
                    <div class="text-light mt-1">
                        ${futEscapeHtml(futPublicAuditText(finalReasons.join(' · ')))}
                    </div>
                ` : ''}
                <div class="text-secondary mt-1">
                    Detalle de sólo lectura: muestra las evidencias que participaron en la decisión.
                </div>
                <div class="mt-2">${votesHtml}</div>
            </div>
        </details>
    `;
}
// ============================================================================
// COMMIT 36M — GUARDADO MANUAL DE ANALYSIS_ONLY CLASIFICADO POR RIESGO
// ============================================================================

window._manualAnalysisCandidates = (
    window._manualAnalysisCandidates
    || {}
);


// RC9.7.12 — resolver una sola recomendación de apalancamiento para el
// seguimiento manual. El lifecycle/backend es la fuente primaria. Como defensa
// durante la ventana de migración posterior al deploy, sólo se acepta el
// leverage del análisis actual si símbolo, TF y geometría Entry/SL/TP coinciden.
function futResolveManualCanonicalLeverage(candidate) {
    const fallback = Number(candidate?.leverage || 1);
    const current = window.currentAnalysis || null;
    const levels = current?.levels || null;

    if (!candidate || !current || !levels) {
        return Number.isFinite(fallback) && fallback > 0 ? Math.round(fallback) : 1;
    }

    const normalizeSymbol = value => String(value || '').toUpperCase().replace('/', '-');
    const sameSymbol = normalizeSymbol(candidate.symbol) === normalizeSymbol(current.symbol || window.currentSymbol);
    const sameTimeframe = String(candidate.timeframe || '').toLowerCase() === String(current.timeframe || window.currentInterval || '').toLowerCase();

    const sameLevel = (a, b) => {
        const x = Number(a);
        const y = Number(b);
        if (!(x > 0) || !(y > 0)) return false;
        const tolerance = Math.max(1e-9, Math.abs(y) * 1e-6);
        return Math.abs(x - y) <= tolerance;
    };

    const sameGeometry = (
        sameLevel(candidate.entry, levels.entry)
        && sameLevel(candidate.stop_loss, levels.stop_loss)
        && sameLevel(candidate.take_profit, levels.take_profit)
    );

    const liveLeverage = Number(levels.leverage || 0);
    if (sameSymbol && sameTimeframe && sameGeometry && Number.isFinite(liveLeverage) && liveLeverage > 0) {
        return Math.round(liveLeverage);
    }

    return Number.isFinite(fallback) && fallback > 0 ? Math.round(fallback) : 1;
}

window.openManualAnalysisSave = function(
    manualKey,
    alreadyInPosition = false
) {
    const candidate = (
        window._manualAnalysisCandidates[
            manualKey
        ]
    );

    if (!candidate) {
        futShowToast(
            'El análisis ya no está disponible. Actualiza la lista.',
            'warning'
        );
        return;
    }

    if (
        candidate.manual_save_allowed
        !== true
    ) {
        futShowToast(
            candidate.manual_risk_reason
            || 'Este análisis no puede guardarse como operación.',
            'warning'
        );
        return;
    }

    const riskClass = String(
        candidate.manual_risk_class
        || ''
    ).toUpperCase();

    const confirmationText = (
        riskClass === 'MEDIUM'
            ? (
                'RIESGO MEDIO: esta hipótesis superó el Safety mínimo, '
                + 'pero NO superó la publicación Premium.\n\n'
                + 'Guardarla no significa que el sistema la recomiende. '
                + '¿Deseas seguirla manualmente?'
            )
            : (
                'RIESGO ALTO: esta hipótesis NO supera el Safety mínimo '
                + 'operativo; sólo está en la banda BAJA 55–64.9.\n\n'
                + 'No es una señal oficial. ¿Deseas guardarla como '
                + 'seguimiento manual experimental?'
            )
    );

    if (!window.confirm(confirmationText)) {
        return;
    }

    const canonicalLeverage = futResolveManualCanonicalLeverage(candidate);

    const sig = {
        symbol:
            candidate.symbol,

        timeframe:
            candidate.timeframe,

        action:
            candidate.action,

        confidence:
            candidate.confidence,

        entry:
            candidate.entry,

        stop_loss:
            candidate.stop_loss,

        take_profit:
            candidate.take_profit,

        leverage:
            canonicalLeverage,

        leverage_policy_version:
            candidate.leverage_policy_version || null,

        leverage_policy_mode:
            candidate.leverage_policy_mode || null,

        risk_allocation_fraction:
            candidate.risk_allocation_fraction ?? null,

        suggested_size:
            candidate.suggested_size ?? null,

        risk_reward:
            candidate.risk_reward,

        candle_timestamp:
            candidate.source_candle_timestamp,

        source_signal_id:
            candidate.signal_id,

        execution_origin:
            'USER_MANUAL_ANALYSIS',

        source_context:
            candidate.source_context
            || 'CURRENT_ANALYSIS_ONLY',

        manual_risk_class:
            riskClass,

        manual_save_allowed:
            true,

        manual_override_ack:
            true,

        manual_risk_reason:
            candidate.manual_risk_reason,

        execution_safety:
            candidate.execution_safety,

        execution_safety_minimum:
            candidate.execution_safety_minimum,

        source_valid_until:
            candidate.valid_until || null,

        valid_until:
            candidate.valid_until || null,

        lifecycle_status:
            candidate.lifecycle_status || null,

        entry_touched:
            Boolean(candidate.entry_touched)
    };

    // En un override manual NO generamos niveles artificiales.
    if (
        !(Number(sig.entry) > 0)
        || !(Number(sig.stop_loss) > 0)
        || !(Number(sig.take_profit) > 0)
    ) {
        futShowToast(
            'El análisis no conserva Entry/SL/TP válidos; no puede guardarse.',
            'warning'
        );
        return;
    }

    window.openSaveSignalModal(
        sig,
        Boolean(
            alreadyInPosition
            || candidate.entry_touched
            || candidate.lifecycle_status === 'entry_touched'
        )
    );
};
function futRenderAnalysisDiagnostics(json, context) {
    // RC9.7.6 — en las listas de señales sólo interesan otras hipótesis
    // LONG/SHORT de riesgo MEDIO/ALTO. NO_OPERAR / ESPERAR / PRECAUCIÓN y
    // errores de datos siguen disponibles para aprendizaje interno, pero no
    // ocupan espacio en una lista que el usuario interpreta como oportunidad.
    const candidateKey = context === 'vigent'
        ? 'vigent_other_directional_signals'
        : 'other_directional_signals';

    // Commit 12.4: an explicit empty server list means EMPTY. Do not fall
    // back to analysis_candidates, because that legacy fallback could revive a
    // second signal for the same symbol×timeframe in another UI lane.
    const hasServerCandidateList = Array.isArray(json && json[candidateKey]);
    let candidates = hasServerCandidateList
        ? json[candidateKey]
        : [];

    // Backward compatibility only when the backend truly does not expose the
    // dedicated candidate list (mixed deploy), never when it explicitly sent [].
    if (
        context !== 'vigent'
        && !hasServerCandidateList
        && Array.isArray(json && json.analysis_candidates)
    ) {
        candidates = json.analysis_candidates.filter(candidate => {
            const action = String(candidate.action || '').toUpperCase();
            const classification = String(candidate.classification || '').toUpperCase();
            const riskClass = String(candidate.manual_risk_class || '').toUpperCase();
            return (
                (action === 'LONG' || action === 'SHORT')
                && classification === 'ANALYSIS_ONLY'
                && (riskClass === 'MEDIUM' || riskClass === 'HIGH')
                && candidate.manual_save_allowed === true
            );
        }).map(candidate => ({
            ...candidate,
            // En el análisis actual nunca se ofrece guardado; sólo la vela
            // anterior puede transformarse en seguimiento manual.
            manual_save_allowed: context === 'previous',
            source_context: context === 'previous'
                ? 'PREVIOUS_ANALYSIS_ONLY'
                : 'CURRENT_ANALYSIS_ONLY'
        }));
    }

    // RC9.8.2: una hipótesis ya guardada por ESTE usuario vive sólo en
    // Guardadas para él. No se oculta para otros usuarios.
    candidates = candidates.filter(candidate => !_isSignalSavedByCurrentUser(candidate));

    const title = 'Por qué no aparecen otras señales';

    if (candidates.length === 0) {
        return `
            <details class="mt-2 px-2 pb-2">
                <summary class="text-secondary" style="cursor:pointer;">
                    ${title} (0)
                </summary>
                <div class="small text-muted mt-2">
                    No hubo otras hipótesis LONG/SHORT de riesgo medio o alto en este ciclo.
                </div>
            </details>
        `;
    }

    let rows = '';

    candidates.forEach(candidate => {
        const action = String(candidate.action || '').toUpperCase();
        if (action !== 'LONG' && action !== 'SHORT') return;

        const riskClass = String(candidate.manual_risk_class || '').toUpperCase();
        if (riskClass !== 'MEDIUM' && riskClass !== 'HIGH') return;

        const isLong = action === 'LONG';
        const directionBadge = isLong ? 'success' : 'danger';
        const riskBadge = riskClass === 'MEDIUM'
            ? 'warning text-dark'
            : 'danger';
        const riskLabel = riskClass === 'MEDIUM'
            ? 'RIESGO MEDIO'
            : 'RIESGO ALTO';
        const symbol = futEscapeHtml(String(candidate.symbol || '').replace('-', '/'));
        const timeframe = futEscapeHtml(candidate.timeframe || '--');
        const confidence = fmtConfidence(candidate.confidence);
        const reason = futEscapeHtml(
            candidate.manual_risk_reason
            || candidate.reason
            || 'No superó el filtro final de publicación.'
        );

        let saveHtml = '';
        const canManualSave = (
            (context === 'previous' || context === 'vigent')
            && candidate.manual_save_allowed === true
            && candidate.signal_id
        );

        if (canManualSave) {
            const manualKey = String(candidate.signal_id);
            const sourceContext = context === 'vigent'
                ? 'ACTIVE_ANALYSIS_ONLY'
                : 'PREVIOUS_ANALYSIS_ONLY';

            window._manualAnalysisCandidates[manualKey] = {
                ...candidate,
                source_context: sourceContext
            };

            if (context === 'vigent') {
                const entryTouched = (
                    candidate.entry_touched === true
                    || candidate.lifecycle_status === 'entry_touched'
                );

                saveHtml = entryTouched
                    ? `
                        <div class="mt-2">
                            <button
                                type="button"
                                class="btn btn-sm btn-success"
                                onclick="event.stopPropagation(); window.openManualAnalysisSave('${manualKey}', true);"
                            >
                                ✅ Guardar en operación
                            </button>
                            <div class="small text-muted mt-1">
                                Entry ya fue alcanzado. El guardado queda en seguimiento y Guardian puede actuar desde este punto.
                            </div>
                        </div>
                    `
                    : `
                        <div class="d-flex flex-wrap gap-2 mt-2">
                            <button
                                type="button"
                                class="btn btn-sm ${riskClass === 'MEDIUM' ? 'btn-outline-warning' : 'btn-outline-danger'}"
                                onclick="event.stopPropagation(); window.openManualAnalysisSave('${manualKey}', false);"
                            >
                                ${riskClass === 'MEDIUM' ? '💾 Guardar seguimiento' : '🧪 Guardar experimental'}
                            </button>
                            <button
                                type="button"
                                class="btn btn-sm btn-success"
                                onclick="event.stopPropagation(); window.openManualAnalysisSave('${manualKey}', true);"
                            >
                                ✅ Guardar en operación
                            </button>
                        </div>
                        <div class="small text-muted mt-1">
                            Conserva la vigencia original; guardar no reinicia el reloj pre-Entry.
                        </div>
                    `;
            } else {
                saveHtml = `
                    <div class="mt-2">
                        <button
                            type="button"
                            class="btn btn-sm ${riskClass === 'MEDIUM' ? 'btn-outline-warning' : 'btn-outline-danger'}"
                            onclick="event.stopPropagation(); window.openManualAnalysisSave('${manualKey}', false);"
                        >
                            ${riskClass === 'MEDIUM' ? '💾 Guardar seguimiento' : '🧪 Guardar experimental'}
                        </button>
                        <div class="small text-muted mt-1">
                            Guardado manual: conserva la clasificación de riesgo y no convierte la señal en recomendación oficial.
                        </div>
                    </div>
                `;
            }
        }

        const contextText = context === 'previous'
            ? 'Hipótesis LONG/SHORT del último cierre que no superó el filtro final.'
            : (context === 'vigent'
                ? 'Hipótesis LONG/SHORT de cierres anteriores que todavía conservan vigencia técnica.'
                : 'Hipótesis LONG/SHORT del análisis actual que no superó el filtro final.');

        rows += `
            <div class="border-top border-secondary py-2"
                 style="cursor:pointer;"
                 onclick="window.changeToSignal('${String(candidate.symbol || '').replace(/'/g, "\'")}', '${String(candidate.timeframe || '').replace(/'/g, "\'")}')">
                <div class="d-flex flex-wrap justify-content-between gap-1">
                    <div>
                        <span class="badge bg-${directionBadge} me-1">${action}</span>
                        <strong>${symbol}</strong>
                        <span class="badge bg-dark ms-1">${timeframe}</span>
                    </div>
                    <div>
                        <span class="badge bg-${riskBadge}">${riskLabel}</span>
                        <span class="badge bg-secondary ms-1">${confidence}%</span>
                    </div>
                </div>
                <div class="small text-muted mt-1">${contextText}</div>
                <div class="small text-light mt-1">${reason}</div>
                ${context === 'vigent' ? `
                    <div class="small ${candidate.lifecycle_status === 'entry_touched' ? 'text-info' : 'text-warning'} mt-1">
                        ${candidate.lifecycle_status === 'entry_touched'
                            ? '📍 Entry alcanzado · seguimiento activo'
                            : `⏳ Vigencia restante: <strong>${_formatPreviousSignalValidity(Number(candidate.tiempo_restante || 0))}</strong>`}
                    </div>
                ` : ''}
                ${saveHtml}
            </div>
        `;
    });

    return `
        <details class="mt-2 px-2 pb-2">
            <summary class="text-warning" style="cursor:pointer;">
                ${title} (${candidates.length})
            </summary>
            <div class="mt-2" style="max-height:360px; overflow-y:auto;">
                ${rows}
            </div>
        </details>
    `;
}


// ============================================================================
// PANEL DE REVIEWTRADER (mantenido de la versión anterior)
// ============================================================================

function insertReviewTraderPanel() {
    // RC9.7.17 — estos cuadros eran diagnóstico interno sin valor operativo
    // para el usuario. ReviewTrader/Strategy Bank siguen activos en backend.
    document.getElementById('review-trader-panel-container')?.remove();
    document.getElementById('review-global-panel-container')?.remove();
}


window.refreshReviewPanel = async function() { return null; };


window.loadGlobalStats = async function() { return null; };


// ============================================================================
// SEÑALES VIGENTES: confirmaciones anteriores cuyo ciclo sigue abierto
// ============================================================================
// Solo se ejecuta si estamos en /futures. Usa /api/futures/signals/active
// que retorna SOLO las 5 cripto × 6 TF × LONG/SHORT

window.updateActiveSignals = async function() {

    // futures.js solo se carga en /futures.
    // No dependemos de IS_FUTURES_PAGE para evitar salidas prematuras.
    console.log('🔵 ACTIVE: función llamada');

    // Asegurar que el estado exista aunque otro script
    // lo haya eliminado o reinicializado.
    if (!window._futuresSignalsState) {
        window._futuresSignalsState = {
            activeLoading: false,
            previousLoading: false,
            activeTimer: null,
            previousTimer: null
        };
    }

    const signalsList =
        document.getElementById('active-signals-list');

    const signalsCount =
        document.getElementById('active-signals-count');

    console.log('🔎 ACTIVE estado inicial:', {
        isFuturesPage: window.IS_FUTURES_PAGE,
        state: window._futuresSignalsState,
        hasList: !!signalsList,
        hasCount: !!signalsCount
    });

    if (!signalsList) {
        console.error(
            '❌ ACTIVE: no existe #active-signals-list'
        );
        return;
    }

    // Si ya hay una petición, no crear otra.
    if (window._futuresSignalsState.activeLoading) {
        console.warn(
            '⚠️ ACTIVE: petición anterior marcada como activa.'
        );

        // IMPORTANTE:
        // No nos quedamos bloqueados para siempre.
        // Como no tenemos referencia al fetch anterior,
        // liberamos el estado y permitimos una nueva consulta.
        window._futuresSignalsState.activeLoading = false;
    }

    window._futuresSignalsState.activeLoading = true;

    console.log(
        '🚀 ACTIVE: iniciando consulta...'
    );
    signalsList.innerHTML = `
        <div class="list-group-item bg-dark text-info text-center py-3">
            <div class="spinner-border spinner-border-sm me-2"></div>
            Consultando señales vigentes...
        </div>
    `;

    if (signalsCount) {
        signalsCount.textContent = '...';
        signalsCount.className = 'badge bg-info';
    }

    const startedAt = performance.now();

    try {

        const response = await fetch(
            DERIV_API_BASE + '/signals/active?min_confidence=55&_ts=' + Date.now(),
            {
                method: 'GET',
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            }
        );

        const elapsed = (
            (performance.now() - startedAt) / 1000
        ).toFixed(1);

        console.log(
            `📥 ACTIVE HTTP ${response.status} en ${elapsed}s`
        );

        if (!response.ok) {

            const text = await response.text();

            throw new Error(
                `HTTP ${response.status}: ${text.substring(0, 500)}`
            );
        }

        const json = await response.json();

        console.log('📦 ACTIVE JSON:', json);

        // ------------------------------------------------------------
        // ERROR DEL BACKEND
        // ------------------------------------------------------------
        if (!json.success) {

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-danger text-center py-3">

                    <strong>❌ Error del servidor</strong>

                    <br>

                    <small>
                        ${json.error || 'Error desconocido'}
                    </small>

                </div>
            `;

            if (signalsCount) {
                signalsCount.textContent = 'ERR';
                signalsCount.className = 'badge bg-danger';
            }

            return;
        }

        const allSignals = Array.isArray(json.signals)
            ? json.signals
            : [];

        // RC9.8.2: estado de guardado PERSONAL. No altera la señal global.
        await window.refreshUserSavedSignalRefs(false);
        const signals = allSignals.filter(sig => !_isSignalSavedByCurrentUser(sig));

        const progress = json.progress || {};
        const filterStats =
            json.filter_stats || null;

        // Este endpoint conserva el lifecycle de cierres anteriores.
        // Nunca debe poblar el diagnóstico de Activas, que pertenece al
        // preview INTRABAR de /api/futures/opportunities.
        const vigentDiagnosticsHtml =
            futRenderAnalysisDiagnostics(
                json,
                'vigent'
            );

        // RC9.7.9 FINAL — cada carril tiene su propio "Por qué no aparecen".
        // Aquí sólo MEDIUM/HIGH de cierres anteriores que siguen vigentes.
        const vigentDiagnostics =
            document.getElementById('vigent-signals-diagnostics');
        if (vigentDiagnostics) {
            vigentDiagnostics.innerHTML = vigentDiagnosticsHtml;
        }

        const completed = Number(
            progress.completed || 0
        );

        const total = Number(
            progress.total || 30
        );

        const running = Boolean(
            json.running ||
            json.warming_up
        );

        console.log(
            '📊 ACTIVE:',
            {
                signals: signals.length,
                completed,
                total,
                running
            }
        );

        // ------------------------------------------------------------
        // SERVIDOR TODAVÍA PROCESANDO
        // ------------------------------------------------------------
        if (running) {

            const pct = total > 0
                ? Math.min(
                    100,
                    (completed / total) * 100
                )
                : 0;

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-info text-center py-3">

                    <div class="spinner-border spinner-border-sm me-2"></div>

                    <strong>
                        Analizando ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futuros'}: ${completed}/${total}
                    </strong>

                    <br>

                    <small class="text-muted">
                        ${progress.current || 'Preparando análisis...'}
                    </small>

                    <div class="progress mt-2"
                         style="height: 6px;">

                        <div
                            class="progress-bar bg-info"
                            style="width: ${pct}%;">
                        </div>

                    </div>

                    <small class="d-block mt-2 text-secondary">
                        Resultado recibido del servidor en ${elapsed}s
                    </small>

                </div>
            `;

            if (signalsCount) {
                signalsCount.textContent =
                    `${completed}/${total}`;

                signalsCount.className =
                    'badge bg-info';
            }

            return;
        }

        // ------------------------------------------------------------
        // SERVIDOR TERMINÓ
        // ------------------------------------------------------------
        window.futuresActiveLoaded = true;

        if (signalsCount) {

            signalsCount.textContent =
                String(signals.length);

            signalsCount.className =
                `badge bg-${
                    signals.length > 0
                        ? 'success'
                        : 'secondary'
                }`;
        }

        // ------------------------------------------------------------
        // SIN SEÑALES
        // ------------------------------------------------------------
        if (signals.length === 0) {

            const hiddenInSaved = allSignals.length > 0;
            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-warning text-center py-3">
                    <strong>✅ Análisis de ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futuros'} completado</strong>
                    <br>
                    <small>${hiddenInSaved
                        ? 'Tus señales vigentes de este ciclo ya están en Señales guardadas.'
                        : 'No hay señales vigentes de cierres anteriores en este momento.'}</small>
                </div>
            `;

            return;
        }

        // ------------------------------------------------------------
        // RENDER DE SEÑALES
        // ------------------------------------------------------------
        let html = '';

        signals.forEach(sig => {

            const isLong =
                sig.action === 'LONG';

            const badgeColor =
                isLong
                    ? 'success'
                    : 'danger';

            const icon =
                isLong
                    ? '📈'
                    : '📉';

            const symbolName =
                futDisplaySymbol(sig.symbol, sig.display_name);

            const confidence =
                Number(sig.confidence || 0);

            const leverage =
                Number(sig.leverage || 1);

            const rr =
                Number(sig.risk_reward || 0);

            const roiTp =
                sig.roi_tp == null ? null : Number(sig.roi_tp);

            const roiSl =
                sig.roi_sl == null ? null : Number(sig.roi_sl);
         
            const remainingSeconds =
                Math.max(
                    0,
                    Number(
                        sig.tiempo_restante
                        || 0
                    )
                );
            
            const validityText =
                _formatPreviousSignalValidity(
                    remainingSeconds
                );
            
            let validityHtml = '';
            
            if (sig.lifecycle_status === 'waiting_entry') {
            
                validityHtml = `
                    <div
                        class="
                            small
                            text-warning
                            mt-1
                        "
                    >
                        ⏳ Esperando que el precio toque la entrada · vigente por:
                        <strong>
                            ${validityText}
                        </strong>
                    </div>
                `;
            
            } else if (sig.lifecycle_status === 'entry_touched') {

                validityHtml = `
                    <div class="small text-info mt-1">
                        📍 Entrada alcanzada · seguimiento hasta objetivo, stop o cierre
                    </div>
                `;

            } else if (sig.lifecycle_status === 'expired') {
            
                validityHtml = `
                    <div
                        class="
                            small
                            text-secondary
                            mt-1
                        "
                    >
                        ⌛ Esta señal ya no es vigente.
                    </div>
                `;
            }

            const signalData = _encodeFuturesSignal({
                ...sig,
                source_context: 'ACTIVE_CONFIRMED'
            });

            const saveButtons = sig.lifecycle_status === 'entry_touched'
                ? `
                    <div class="d-flex flex-wrap gap-2 mt-2">
                        <button type="button" class="btn btn-sm btn-success"
                            onclick="window.openSaveActiveSignalFromCard(event, '${signalData}', true)">
                            ✅ Guardar en operación
                        </button>
                    </div>`
                : `
                    <div class="d-flex flex-wrap gap-2 mt-2">
                        <button type="button" class="btn btn-sm btn-outline-success"
                            onclick="window.openSaveActiveSignalFromCard(event, '${signalData}', false)">
                            🔖 Guardar
                        </button>
                        <button type="button" class="btn btn-sm btn-success"
                            onclick="window.openSaveActiveSignalFromCard(event, '${signalData}', true)">
                            ✅ Guardar en operación
                        </button>
                    </div>`;

            html += `
                <div
                    class="list-group-item bg-dark text-white border-secondary"
                    style="cursor:pointer;"
                    onclick="window.changeToSignal(
                        '${sig.symbol}',
                        '${sig.timeframe}'
                    )"
                >

                    <div class="d-flex justify-content-between align-items-center">

                        <div>

                            <span class="badge bg-${badgeColor} me-2">
                                ${icon} ${sig.action}
                            </span>

                            <strong>
                                ${symbolName}
                            </strong>

                            <span class="badge bg-dark ms-1">
                                ${sig.timeframe}
                            </span>

                        </div>

                        <span class="badge bg-warning text-dark">
                            ${Math.max(
                                0,
                                Math.min(
                                    100,
                                    confidence
                                )
                            ).toFixed(0)}%
                        </span>

                    </div>

                    <div
                        class="mt-2 d-flex justify-content-between align-items-center"
                        style="font-size:0.75rem;"
                    >

                        <div>

                            <span class="badge bg-secondary me-1">
                                Apal. ${leverage}x
                            </span>

                            <span class="badge bg-dark">
                                R/R 1:${rr.toFixed(1)}
                            </span>

                        </div>

                        <div>

                            <span class="text-success">
                                TP ${roiTp == null ? '--' : `${roiTp >= 0 ? '+' : ''}${roiTp.toFixed(1)}%`}
                            </span>

                            <span class="mx-1 text-muted">
                                |
                            </span>

                            <span class="text-danger">
                                SL ${roiSl == null ? '--' : `${roiSl.toFixed(1)}%`}
                            </span>

                        </div>

                    </div>

                    ${validityHtml}

                    ${saveButtons}

                    ${futRenderDecisionAudit(sig.decision_audit)}

                </div>
            `;
        });

        signalsList.innerHTML = html;

    } catch (err) {

        console.error(
            '❌ ACTIVE FETCH:',
            err
        );

        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-danger text-center py-3">

                <strong>
                    ❌ No se pudo consultar ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futuros'}
                </strong>

                <br>

                <small>
                    ${err.message || 'Error de conexión'}
                </small>

            </div>
        `;

        if (signalsCount) {

            signalsCount.textContent =
                'ERR';

            signalsCount.className =
                'badge bg-danger';
        }

    } finally {

        window._futuresSignalsState.activeLoading = false;

        console.log(
            '🏁 ACTIVE: request finalizado.'
        );
    }
};


// ============================================================================
// FASE 8.2 — VIGENCIA VISUAL DE SEÑALES DE VELA ANTERIOR
// ============================================================================

function _formatPreviousSignalValidity(seconds) {

    const totalSeconds = Math.max(
        0,
        Number(
            seconds
            || 0
        )
    );

    if (totalSeconds <= 0) {
        return 'vigencia finalizada';
    }

    const days = Math.floor(
        totalSeconds
        / 86400
    );

    const hours = Math.floor(
        (
            totalSeconds
            % 86400
        )
        / 3600
    );

    const minutes = Math.floor(
        (
            totalSeconds
            % 3600
        )
        / 60
    );

    if (days > 0) {

        return (
            `${days}d `
            + `${hours}h`
        );
    }

    if (hours > 0) {

        return (
            `${hours}h `
            + `${minutes}m`
        );
    }

    return `${minutes}m`;
}

function _encodeFuturesSignal(sig) {
    return encodeURIComponent(JSON.stringify(sig)).replace(/'/g, '%27');
}

function _decodeFuturesSignal(encodedSignal) {
    return JSON.parse(decodeURIComponent(encodedSignal));
}

window.openSaveSignalFromCard = function(event, encodedSignal, alreadyInPosition) {
    if (event) event.stopPropagation();
    const sig = _decodeFuturesSignal(encodedSignal);
    if (sig) sig.source_context = 'PREVIOUS_CONFIRMED';
    window.openSaveSignalModal(sig, Boolean(alreadyInPosition));
};

// RC9.7.8 — señales vigentes también son guardables sin reiniciar
// su vigencia original. Si Entry ya fue tocado, se guardan directamente
// como operación en seguimiento para activar Guardian.
window.openSaveActiveSignalFromCard = function(event, encodedSignal, alreadyInPosition) {
    if (event) event.stopPropagation();
    const sig = _decodeFuturesSignal(encodedSignal);
    if (!sig) return;
    sig.source_context = 'ACTIVE_CONFIRMED';
    const inPosition = Boolean(alreadyInPosition || sig.entry_touched || sig.lifecycle_status === 'entry_touched');
    window.openSaveSignalModal(sig, inPosition);
};


// ============================================================================
// SOBREESCRIBIR: updatePreviousSignals (vela ANTERIOR — estática)
// ============================================================================

window.updatePreviousSignals = async function() {

    // futures.js solo se carga en /futures.
    console.log('🟣 PREVIOUS: función llamada');

    if (!window._futuresSignalsState) {
        window._futuresSignalsState = {
            activeLoading: false,
            previousLoading: false,
            activeTimer: null,
            previousTimer: null
        };
    }

    const signalsList =
        document.getElementById(
            'prev-signals-list'
        );

    const signalsCount =
        document.getElementById(
            'prev-signals-count'
        );

    console.log(
        '🔎 PREVIOUS estado inicial:',
        {
            isFuturesPage:
                window.IS_FUTURES_PAGE,

            state:
                window._futuresSignalsState,

            hasList:
                !!signalsList,

            hasCount:
                !!signalsCount
        }
    );

    if (!signalsList) {
        console.error(
            '❌ PREVIOUS: no existe #prev-signals-list'
        );
        return;
    }

    if (
        window._futuresSignalsState
            .previousLoading
    ) {

        console.warn(
            '⚠️ PREVIOUS: petición anterior marcada como activa.'
        );

        // Evitar bloqueo permanente.
        window._futuresSignalsState
            .previousLoading = false;
    }

    window._futuresSignalsState
        .previousLoading = true;

    console.log(
        '🚀 PREVIOUS: iniciando consulta...'
    );

    signalsList.innerHTML = `
        <div class="list-group-item bg-dark text-info text-center py-3">

            <div class="spinner-border spinner-border-sm me-2"></div>

            Consultando último cierre confirmado...

        </div>
    `;

    if (signalsCount) {

        signalsCount.textContent =
            '...';

        signalsCount.className =
            'badge bg-info';
    }

    const startedAt =
        performance.now();

    try {

        const response = await fetch(
            DERIV_API_BASE + '/signals/previous?min_confidence=55&_ts='
            + Date.now(),
            {
                method: 'GET',
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            }
        );

        const elapsed =
            (
                (performance.now() -
                    startedAt) / 1000
            ).toFixed(1);

        console.log(
            `📥 PREVIOUS HTTP ${response.status} en ${elapsed}s`
        );

        if (!response.ok) {

            const text =
                await response.text();

            throw new Error(
                `HTTP ${response.status}: ${text.substring(0, 500)}`
            );
        }

        const json =
            await response.json();

        console.log(
            '📦 PREVIOUS JSON:',
            json
        );

        if (!json.success) {

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-danger text-center py-3">

                    <strong>
                        ❌ Error del servidor
                    </strong>

                    <br>

                    <small>
                        ${json.error || 'Error desconocido'}
                    </small>

                </div>
            `;

            if (signalsCount) {

                signalsCount.textContent =
                    'ERR';

                signalsCount.className =
                    'badge bg-danger';
            }

            return;
        }

        const allSignals =
            Array.isArray(json.signals)
                ? json.signals
                : [];

        // RC9.8.2: ocultar sólo para el usuario que ya la guardó.
        await window.refreshUserSavedSignalRefs(false);
        const signals = allSignals.filter(sig => !_isSignalSavedByCurrentUser(sig));

        const progress =
            json.progress || {};

        const filterStats =
            json.filter_stats || null;

        const diagnosticsHtml =
            futRenderAnalysisDiagnostics(
                json,
                'previous'
            );

        const completed =
            Number(
                progress.completed || 0
            );

        const total =
            Number(
                progress.total || 30
            );

        const running =
            Boolean(
                json.running ||
                json.warming_up
            );

        console.log(
            '📊 PREVIOUS:',
            {
                signals: signals.length,
                completed,
                total,
                running
            }
        );

        // ------------------------------------------------------------
        // SERVIDOR TODAVÍA TRABAJANDO
        // ------------------------------------------------------------
        if (running) {

            const pct =
                total > 0
                    ? Math.min(
                        100,
                        (completed / total) * 100
                    )
                    : 0;

            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-info text-center py-3">

                    <div class="spinner-border spinner-border-sm me-2"></div>

                    <strong>
                        Analizando último cierre:
                        ${completed}/${total}
                    </strong>

                    <br>

                    <small class="text-muted">
                        ${progress.current || 'Preparando análisis...'}
                    </small>

                    <div
                        class="progress mt-2"
                        style="height:6px;"
                    >

                        <div
                            class="progress-bar bg-warning"
                            style="width:${pct}%;">
                        </div>

                    </div>

                    <small
                        class="d-block mt-2 text-secondary"
                    >
                        Respuesta recibida en ${elapsed}s
                    </small>

                </div>
            `;

            if (signalsCount) {

                signalsCount.textContent =
                    `${completed}/${total}`;

                signalsCount.className =
                    'badge bg-info';
            }

            return;
        }

        // ------------------------------------------------------------
        // SERVIDOR TERMINÓ
        // ------------------------------------------------------------
        window.futuresPrevLoaded =
            true;

        if (signalsCount) {
        
            // El contador también es PERSONAL: no incluye señales que este
            // usuario ya movió visualmente a Guardadas.
            const activeCount = signals.filter(
                signal => signal.activa === 1
            ).length;
        
            signalsCount.textContent =
                String(
                    activeCount
                );
        
            signalsCount.className =
                `badge bg-${
                    activeCount > 0
                        ? 'warning'
                        : 'secondary'
                }`;
        
            signalsCount.title =
                `${activeCount} nueva(s) señal(es) confirmada(s) en el último cierre`;
        }

        // ------------------------------------------------------------
        // SIN SEÑALES
        // ------------------------------------------------------------
        if (signals.length === 0) {

            const hiddenInSaved = allSignals.length > 0;
            signalsList.innerHTML = `
                <div class="list-group-item bg-dark text-warning text-center py-3">
                    <strong>✅ Análisis completado</strong>
                    <br>
                    <small>${hiddenInSaved
                        ? 'Tus señales confirmadas de este cierre ya están en Señales guardadas.'
                        : 'No hay nuevas señales confirmadas en el último cierre.'}</small>
                </div>
                ${diagnosticsHtml}
            `;

            return;
        }

        // ------------------------------------------------------------
        // RENDER
        // ------------------------------------------------------------
        let html = '';

        signals.forEach(sig => {

            const isLong =
                sig.action === 'LONG';

            const badgeColor =
                isLong
                    ? 'success'
                    : 'danger';

            const icon =
                isLong
                    ? '📈'
                    : '📉';

            const symbolName =
                futDisplaySymbol(sig.symbol, sig.display_name);

            const confidence =
                Number(sig.confidence || 0);

            const leverage =
                Number(sig.leverage || 1);

            const rr =
                Number(sig.risk_reward || 0);

            const roiTp =
                sig.roi_tp == null ? null : Number(sig.roi_tp);

            const roiSl =
                sig.roi_sl == null ? null : Number(sig.roi_sl);

            let statusBadge =
                '<span class="badge bg-warning text-dark">✅ Nueva confirmada</span>';

            if (sig.lifecycle_status === 'entry_touched') {
                statusBadge =
                    '<span class="badge bg-info text-dark">📍 Entrada alcanzada</span>';
            } else if (
                sig.resultado === 'tp_hit'
            ) {

                statusBadge =
                    '<span class="badge bg-success">✅ TP</span>';

            } else if (
                sig.resultado === 'sl_hit'
            ) {

                statusBadge =
                    '<span class="badge bg-danger">❌ SL</span>';
            }
            else if (
                sig.resultado === 'expired'
            ) {

                statusBadge =
                    '<span class="badge bg-secondary">⌛ Vencida</span>';
            }
            const inactive =
                sig.activa !== 1;

            const opacity =
                inactive
                    ? 'opacity-50'
                    : '';

            const signalData =
                _encodeFuturesSignal(sig);

            const saveButtons = inactive
                ? ''
                : `
                    <div class="d-flex flex-wrap gap-2 mt-2">
                        <button
                            type="button"
                            class="btn btn-sm btn-outline-success"
                            onclick="window.openSaveSignalFromCard(event, '${signalData}', false)"
                            title="Guardar y esperar a que el precio toque Entry"
                        >
                            🔖 Guardar
                        </button>
                        <button
                            type="button"
                            class="btn btn-sm btn-success"
                            onclick="window.openSaveSignalFromCard(event, '${signalData}', true)"
                            title="Ya entré: usar el precio actual como Entry editable"
                        >
                            ✅ Guardar en operación
                        </button>
                    </div>
                `;

            html += `
                <div
                    class="list-group-item bg-dark text-white border-secondary ${opacity}"
                    style="cursor:pointer;"
                    data-signal-id="${String(sig.signal_id || '').replace(/"/g, '&quot;')}"
                    data-signal="${signalData}"
                    onclick="window.showFuturesPrevJustif(_decodeFuturesSignal(this.getAttribute('data-signal')))"
                >

                    <div class="d-flex justify-content-between align-items-center">

                        <div>

                            <span class="badge bg-${badgeColor} me-2">
                                ${icon} ${sig.action}
                            </span>

                            <strong>
                                ${symbolName}
                            </strong>

                            <span class="badge bg-dark ms-1">
                                ${sig.timeframe}
                            </span>

                        </div>

                        <div>
                            ${statusBadge}

                            <span
                                class="badge bg-secondary ms-1"
                            >
                                ${Math.max(
                                    0,
                                    Math.min(
                                        100,
                                        confidence
                                    )
                                ).toFixed(0)}%
                            </span>
                        </div>

                    </div>

                    <div
                        class="mt-2 d-flex justify-content-between"
                        style="font-size:0.72rem;"
                    >

                        <div>

                            <span class="badge bg-dark me-1">
                                Apal. ${leverage}x
                            </span>

                            <span class="badge bg-dark">
                                R/R 1:${rr.toFixed(1)}
                            </span>

                        </div>

                        <div>

                            <span class="text-success">
                                TP ${roiTp == null ? '--' : `${roiTp >= 0 ? '+' : ''}${roiTp.toFixed(1)}%`}
                            </span>

                            <span class="mx-1 text-muted">
                                |
                            </span>

                            <span class="text-danger">
                                SL ${roiSl == null ? '--' : `${roiSl.toFixed(1)}%`}
                            </span>

                        </div>

                    </div>

                    ${saveButtons}

                    ${futRenderDecisionAudit(sig.decision_audit)}

                </div>
            `;
        });

        signalsList.innerHTML = html + diagnosticsHtml;
        window.applyFuturesSignalDeepLink?.();

    } catch (err) {

        console.error(
            '❌ PREVIOUS FETCH:',
            err
        );

        signalsList.innerHTML = `
            <div class="list-group-item bg-dark text-danger text-center py-3">

                <strong>
                    ❌ No se pudo consultar el último cierre confirmado
                </strong>

                <br>

                <small>
                    ${err.message || 'Error de conexión'}
                </small>

            </div>
        `;

        if (signalsCount) {

            signalsCount.textContent =
                'ERR';

            signalsCount.className =
                'badge bg-danger';
        }

    } finally {

        window._futuresSignalsState
            .previousLoading = false;

        console.log(
            '🏁 PREVIOUS: request finalizado.'
        );
    }
};
// ============================================================================
// GUARDAR REFERENCIAS DE LAS FUNCIONES PROPIAS DE FUTUROS
// ============================================================================
// script.js define posteriormente sus propias versiones Spot dentro de
// DOMContentLoaded y puede sobrescribir window.updateActiveSignals y
// window.updatePreviousSignals.
// Guardamos aquí las funciones correctas de Futuros para restaurarlas después.
// ============================================================================

window._futuresUpdateActiveSignals =
    window.updateActiveSignals;

window._futuresUpdatePreviousSignals =
    window.updatePreviousSignals;

// Modal específico de justificación (vela anterior futuros)
window.showFuturesPrevJustif = function(sig) {
    const body = document.getElementById('prev-signal-details');
    if (!body) return;
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-warning"></div></div>';
    
    const modal = new bootstrap.Modal(document.getElementById('prevSignalModal'));
    modal.show();
    
    // Renderizar de inmediato
    setTimeout(() => {
        const symbolName = futDisplaySymbol(sig.symbol, sig.display_name);
        const isLong = sig.action === 'LONG';
        const emoji = isLong ? '📈' : '📉';
        const bgColor = isLong ? 'success' : 'danger';
        
        let estadoHTML;
        if (sig.resultado === 'tp_hit') {
            estadoHTML = `<div class="alert alert-success mt-3"><strong>✅ TP ALCANZADO</strong> - operación exitosa</div>`;
        } else if (sig.resultado === 'sl_hit') {

            estadoHTML = `
                <div class="alert alert-danger mt-3">
                    <strong>❌ SL ALCANZADO</strong>
                    - operación invalidada
                </div>
            `;

        } else if (sig.resultado === 'expired') {

            estadoHTML = `
                <div class="alert alert-secondary mt-3">
                    <strong>⌛ VIGENCIA FINALIZADA</strong>
                    <br>
                    Esta señal pertenecía a la vela anterior y
                    su ventana operativa ya terminó.
                    No persigas el precio; espera una nueva señal.
                </div>
            `;

        } else {
        
            const remainingText =
                _formatPreviousSignalValidity(
                    sig.tiempo_restante
                );
        
            estadoHTML = `
                <div
                    class="
                        alert
                        alert-warning
                        mt-3
                    "
                >
                    <strong>
                        ⏱️ SEÑAL TODAVÍA VIGENTE
                    </strong>
        
                    <br>
        
                    La señal pertenece a la vela anterior
                    y todavía se encuentra dentro de su
                    ventana operativa.
        
                    <br>
        
                    <small>
                        Tiempo restante aproximado:
                        <strong>
                            ${remainingText}
                        </strong>
                    </small>
        
                    <br>
        
                    <small class="text-muted">
                        Si no se activa dentro de esta
                        ventana, no debe perseguirse el
                        precio; debe esperarse una nueva señal.
                    </small>
                </div>
            `;
        }
        
        body.innerHTML = `
            <div>
                <div class="d-flex align-items-center mb-3">
                    <span class="badge bg-${bgColor} p-3 me-3" style="font-size: 1.2rem;">
                        ${emoji} ${sig.action}
                    </span>
                    <div>
                        <span class="badge bg-dark d-block mb-1">${symbolName} · ${sig.timeframe}</span>
                        <span class="badge bg-secondary">Confianza: ${fmtConfidence(sig.confidence)}%</span>
                    </div>
                </div>
                ${estadoHTML}
                <div class="row mt-3 g-2">
                    <div class="col-md-3">
                        <div class="border-start border-3 border-primary ps-2">
                            <small class="text-muted d-block">ENTRADA</small>
                            <strong>${futFormatPrice(sig.entry, sig.symbol)}</strong>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-danger ps-2">
                            <small class="text-muted d-block">STOP LOSS</small>
                            <strong>${futFormatPrice(sig.stop_loss, sig.symbol)}</strong>
                            <div class="small text-danger">${futFormatPct(sig.roi_sl, 1)} ROI</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-success ps-2">
                            <small class="text-muted d-block">TAKE PROFIT</small>
                            <strong>${futFormatPrice(sig.take_profit, sig.symbol)}</strong>
                            <div class="small text-success">${futFormatPct(sig.roi_tp, 1)} ROI</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="border-start border-3 border-warning ps-2">
                            <small class="text-muted d-block">APALANCAMIENTO</small>
                            <strong class="text-warning">${sig.leverage}x</strong>
                            <div class="small">R/R 1:${sig.risk_reward.toFixed(1)}</div>
                        </div>
                    </div>
                </div>
                <div class="mt-3 p-3 bg-dark rounded" style="border-left: 3px solid #FFD700;">
                    <small class="text-muted">
                        <strong>Origen TP:</strong> ${sig.tp_source || '--'}<br>
                        <strong>Origen SL:</strong> ${sig.sl_source || '--'}<br>
                        <strong>Precio actual:</strong> ${futFormatPrice(sig.current_price, sig.symbol)}<br>
                        <strong>Vela evaluada:</strong> ${sig.candle_timestamp || '--'}
                    </small>
                </div>
                <div class="mt-3 text-center">
                    <small class="text-muted">
                        <i class="fas fa-info-circle me-1"></i>
                        Con 10 USDT y ${sig.leverage}x apalancamiento:
                        <strong class="text-success">+${(10 * (sig.roi_tp / 100)).toFixed(2)} USDT</strong> si TP,
                        <strong class="text-danger">${(10 * (sig.roi_sl / 100)).toFixed(2)} USDT</strong> si SL
                    </small>
                </div>
            </div>
        `;
    }, 100);
};


// ============================================================================
// SOBREESCRIBIR: updateCorrelationInfo (vista intra-cripto para futuros)
// ============================================================================

window.updateCorrelationInfo = function(data) {
    if (!window.IS_FUTURES_PAGE) return;

    const tf = document.getElementById('interval-select')?.value || window.currentInterval || '1h';
    const symbol = document.getElementById('symbol-select')?.value || window.currentSymbol || window.PAGE_CONFIG?.defaultSymbol || 'BTC-USDT';
    const requestKey = `${symbol}|${tf}`;
    window.__FUTURES_CONTEXT_REQUEST_KEY__ = requestKey;

    fetch(`${DERIV_API_BASE}/correlation?timeframe=${encodeURIComponent(tf)}&symbol=${encodeURIComponent(symbol)}`, {
        cache: 'no-store'
    })
        .then(r => r.json())
        .then(json => {
            if (!json.success) return;
            const currentSymbol = document.getElementById('symbol-select')?.value || window.currentSymbol || window.PAGE_CONFIG?.defaultSymbol || 'BTC-USDT';
            const currentTf = document.getElementById('interval-select')?.value || window.currentInterval || '1h';
            if (`${currentSymbol}|${currentTf}` !== requestKey) return;
            renderFuturesCorrelation(json);
        })
        .catch(err => console.error(`Error contexto ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futures'}:`, err));
};


function renderFuturesCorrelation(payload) {
    const container = document.getElementById('correlation-info');
    if (!container) return;

    if (window.IS_MULTI_ASSET_PAGE) {
        const rows = Array.isArray(payload?.rankings) ? payload.rankings : [];
        const best = payload?.best_opportunity || {};
        const title = document.getElementById('correlation-panel-title');
        if (title) title.innerHTML = '<i class="fas fa-globe me-2"></i>Oportunidades · Multi-Activo';
        const tfBadge = document.getElementById('correlation-timeframe');
        if (tfBadge) tfBadge.textContent = window.currentInterval || '4h';
        container.innerHTML = `
            <div class="small text-muted mb-2">Prioriza los activos con mejor contexto de mercado para el análisis.</div>
            ${rows.slice(0,7).map((r,i) => `
                <div class="d-flex justify-content-between align-items-center border-bottom border-secondary py-2">
                    <span><strong>${futEscapeHtml(r.display_name || r.symbol || '--')}</strong><br><small>${futEscapeHtml(r.asset_class || '')} · ${futEscapeHtml(r.session || '')}</small></span>
                    <span class="text-end"><span class="badge bg-${i < 2 ? 'success' : 'secondary'}">${Number(r.router_score || 0).toFixed(0)}</span><br><small>${futEscapeHtml(r.bias || '')} · Macro ${futEscapeHtml(r.macro_gate || 'NORMAL')}</small></span>
                </div>`).join('') || '<div class="text-muted">Sin datos suficientes de mercado.</div>'}
            ${best?.display_name ? `<div class="mt-2 text-info">Mejor contexto ahora: <strong>${futEscapeHtml(best.display_name)}</strong>. Esto no obliga a operar; sólo prioriza análisis.</div>` : ''}
        `;
        return;
    }

    const ctx = payload.intermarket_context || {};
    const pairs = payload.pairs || {};
    const selectedSymbol = String(ctx.selected_symbol || window.currentSymbol || window.PAGE_CONFIG?.defaultSymbol || 'BTC-USDT').toUpperCase().replace('/', '-');
    const selected = pairs[selectedSymbol] || {};
    const tf = payload.timeframe || window.currentInterval || '1h';
    const symbolLabel = selectedSymbol.replace('-', '/');

    const title = document.getElementById('correlation-panel-title');
    if (title) {
        title.innerHTML = `<i class="fas fa-network-wired me-2" aria-hidden="true"></i>Contexto de mercado Futures · ${futEscapeHtml(symbolLabel)} ${futEscapeHtml(tf)}`;
    }
    const tfBadge = document.getElementById('correlation-timeframe');
    if (tfBadge) tfBadge.textContent = tf;

    const directionBadge = value => {
        const dir = String(value || '').toLowerCase();
        if (dir === 'bullish') return '<span class="badge bg-success">ALCISTA</span>';
        if (dir === 'bearish') return '<span class="badge bg-danger">BAJISTA</span>';
        return '<span class="badge bg-secondary">NEUTRAL</span>';
    };
    const fmtNum = (value, digits = 2, suffix = '') => {
        const n = Number(value);
        return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : '--';
    };
    const fmtFunding = value => {
        const n = Number(value);
        return Number.isFinite(n) ? `${(n * 100).toFixed(4)}%` : '--';
    };
    const htf = row => {
        if (!row || !row.available) return '<span class="badge bg-secondary">SIN DATO</span>';
        return `${directionBadge(row.direction)} <small class="text-muted">ADX ${fmtNum(row.adx, 1)}</small>`;
    };

    const breadth = ctx.breadth || {};
    const available = Number(breadth.available || 0);
    const bulls = Number(breadth.bullish || 0);
    const bears = Number(breadth.bearish || 0);
    const neutral = Math.max(0, available - bulls - bears);
    const selectedDir = String(selected.direction || 'neutral').toLowerCase();
    const breadthDir = bulls > bears ? 'bullish' : (bears > bulls ? 'bearish' : 'neutral');
    const btc12 = String(ctx.btc_12h?.direction || 'neutral').toLowerCase();
    const btc1d = String(ctx.btc_1d?.direction || 'neutral').toLowerCase();

    let readingClass = 'secondary';
    let reading = 'Contexto mixto o sin tesis direccional actual.';
    if (selectedDir === 'bullish' || selectedDir === 'bearish') {
        const opposite = selectedDir === 'bullish' ? 'bearish' : 'bullish';
        const aligned = [btc12, btc1d, breadthDir].filter(v => v === selectedDir).length;
        const opposed = [btc12, btc1d, breadthDir].filter(v => v === opposite).length;
        if (aligned >= 2 && opposed === 0) {
            readingClass = 'success';
            reading = `Contexto general favorable para la tesis ${selectedDir === 'bullish' ? 'LONG' : 'SHORT'} actual.`;
        } else if (opposed >= 2) {
            readingClass = 'danger';
            reading = `Contexto general adverso a la tesis ${selectedDir === 'bullish' ? 'LONG' : 'SHORT'} actual; exige mayor confirmación.`;
        } else {
            readingClass = 'warning text-dark';
            reading = 'Contexto mixto: hay alineaciones y contradicciones entre BTC HTF y amplitud.';
        }
    }

    const imbalance = Number(ctx.orderbook_imbalance);
    const flow = Number.isFinite(imbalance)
        ? (imbalance > 0.08 ? 'COMPRADOR' : (imbalance < -0.08 ? 'VENDEDOR' : 'NEUTRAL'))
        : 'SIN DATO';
    const flowClass = flow === 'COMPRADOR' ? 'success' : (flow === 'VENDEDOR' ? 'danger' : 'secondary');
    const regime = futEscapeHtml(String(ctx.regime || '--').replaceAll('_', ' '));
    const liquidity = futEscapeHtml(String(ctx.liquidity_band || '--').replaceAll('_', ' '));

    const topLong = (payload.top_long_candidates || [])[0];
    const topShort = (payload.top_short_candidates || [])[0];
    const strengthHtml = (topLong || topShort) ? `
        <div class="small text-muted mt-2">
            Fuerza relativa: ${topLong ? `<span class="text-success">LONG ${futEscapeHtml(topLong.symbol.replace('-', '/'))} · ADX ${fmtNum(topLong.adx, 1)}</span>` : '--'}
            ${topLong && topShort ? ' · ' : ''}
            ${topShort ? `<span class="text-danger">SHORT ${futEscapeHtml(topShort.symbol.replace('-', '/'))} · ADX ${fmtNum(topShort.adx, 1)}</span>` : ''}
        </div>` : '';

    container.innerHTML = `
        <div class="small text-muted mb-2">
            Lectura contextual de <strong>${futEscapeHtml(symbolLabel)} ${futEscapeHtml(tf)}</strong>. No sustituye Entry, SL, TP ni Safety.
        </div>
        <div class="row g-2">
            <div class="col-md-6 col-xl-3">
                <div class="p-2 border border-secondary rounded h-100">
                    <div class="small text-muted">BTC 12H / 1D</div>
                    <div class="mt-1">12H ${htf(ctx.btc_12h)} · 1D ${htf(ctx.btc_1d)}</div>
                </div>
            </div>
            <div class="col-md-6 col-xl-3">
                <div class="p-2 border border-secondary rounded h-100">
                    <div class="small text-muted">Amplitud Futures</div>
                    <div class="mt-1"><span class="text-success">${bulls} alcistas</span> · <span class="text-danger">${bears} bajistas</span> · ${neutral} neutrales</div>
                </div>
            </div>
            <div class="col-md-6 col-xl-3">
                <div class="p-2 border border-secondary rounded h-100">
                    <div class="small text-muted">Derivados ${futEscapeHtml(symbolLabel)}</div>
                    <div class="mt-1">Funding <strong>${fmtFunding(ctx.funding_rate)}</strong> · OI <strong>${fmtNum(ctx.oi_change_pct, 2, '%')}</strong></div>
                </div>
            </div>
            <div class="col-md-6 col-xl-3">
                <div class="p-2 border border-secondary rounded h-100">
                    <div class="small text-muted">Flujo / régimen</div>
                    <div class="mt-1"><span class="badge bg-${flowClass}">${flow}</span> · ${regime}<br><small class="text-muted">Liquidez: ${liquidity}</small></div>
                </div>
            </div>
        </div>
        ${strengthHtml}
        <div class="alert alert-${readingClass} py-2 px-3 mt-2 mb-0 small">
            <strong>Lectura:</strong> ${reading}
        </div>
        <details class="correlation-details mt-2">
            <summary><i class="fas fa-circle-info me-1"></i>Qué significa</summary>
            <div class="small text-muted pt-2">
                BTC 12H/1D aporta el contexto de mercado mayor; amplitud resume cuántos contratos del universo están alcistas o bajistas; funding, interés abierto, order book y liquidez describen el entorno del contrato seleccionado. Esta sección sólo contextualiza la tesis y nunca genera LONG/SHORT por sí sola.
            </div>
        </details>
    `;
}

// ============================================================================
// COMMIT 36L — UI DE PREFERENCIAS DE SCALPING FUTURES
// ============================================================================
//
// Este bloque sólo lee/guarda preferencias del endpoint creado en 36K.
// NO modifica análisis, señales, Safety, Entry, SL, TP ni leverage.
// ============================================================================

window._futuresScalpingPreferencesLoaded = false;


function _futScalpingSetMessage(
    message,
    type = 'secondary'
) {
    const box = document.getElementById(
        'futures-scalping-message'
    );

    if (!box) return;

    box.className = (
        `alert alert-${type} py-2 px-2 small mb-3`
    );

    box.textContent = String(
        message || ''
    );
}


function _futScalpingSetStatus(
    status
) {
    const badge = document.getElementById(
        'futures-scalping-status-badge'
    );

    if (!badge) return;

    if (status === 'ON') {
        badge.textContent = 'ON';
        badge.className = 'badge bg-success';
        return;
    }

    if (status === 'LOGIN') {
        badge.textContent = 'LOGIN';
        badge.className = 'badge bg-secondary';
        return;
    }

    if (status === 'ERROR') {
        badge.textContent = 'ERROR';
        badge.className = 'badge bg-danger';
        return;
    }

    badge.textContent = 'OFF';
    badge.className = 'badge bg-secondary';
}


function _futScalpingApplyPreferences(
    preferences,
    user = null
) {
    const prefs = (
        preferences
        && typeof preferences === 'object'
    )
        ? preferences
        : {};

    const enabled = Boolean(
        prefs.futures_scalping_telegram_enabled
    );

    const enabledInput = document.getElementById(
        'futures-scalping-enabled'
    );

    if (enabledInput) {
        enabledInput.checked = enabled;
    }

    const selectedTimeframes = new Set(
        Array.isArray(
            prefs.futures_scalping_timeframes
        )
            ? prefs.futures_scalping_timeframes
            : []
    );

    document.querySelectorAll(
        '[data-scalping-tf]'
    ).forEach(input => {
        input.checked = selectedTimeframes.has(
            input.value
        );
    });

    const startInput = document.getElementById(
        'futures-scalping-start-time'
    );

    const endInput = document.getElementById(
        'futures-scalping-end-time'
    );

    if (startInput) {
        startInput.value = (
            prefs.futures_scalping_start_time
            || ''
        );
    }

    if (endInput) {
        endInput.value = (
            prefs.futures_scalping_end_time
            || ''
        );
    }

    const selectedDays = new Set(
        (
            Array.isArray(
                prefs.futures_scalping_weekdays
            )
                ? prefs.futures_scalping_weekdays
                : []
        ).map(
            value => Number(value)
        )
    );

    document.querySelectorAll(
        '[data-scalping-day]'
    ).forEach(input => {
        input.checked = selectedDays.has(
            Number(input.value)
        );
    });

    const timezoneInput = document.getElementById(
        'futures-scalping-timezone'
    );

    if (timezoneInput) {
        timezoneInput.value = String(
            prefs.futures_scalping_timezone
            || 'UTC'
        );
    }

    const userLabel = document.getElementById(
        'futures-scalping-user-label'
    );

    if (userLabel) {
        userLabel.textContent = (
            user
            ? String(user)
            : '—'
        );
    }

    _futScalpingSetStatus(
        enabled
            ? 'ON'
            : 'OFF'
    );

    _futScalpingSetMessage(
        enabled
            ? 'Alertas de scalping activadas con tu horario personal.'
            : 'Alertas de scalping desactivadas.',
        enabled
            ? 'success'
            : 'secondary'
    );
}


window.loadFuturesScalpingPreferences = async function(
    options = {}
) {
    if (!window.IS_FUTURES_PAGE) {
        return false;
    }

    const silent = Boolean(
        options.silent
    );

    if (!silent) {
        _futScalpingSetMessage(
            'Cargando preferencias...',
            'info'
        );
    }

    try {
        const response = await fetch(
            '/api/user/futures-scalping-preferences',
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );

        let data = {};

        try {
            data = await response.json();
        } catch (jsonError) {
            data = {};
        }

        if (response.status === 401) {
            window._futuresScalpingPreferencesLoaded = false;

            _futScalpingSetStatus(
                'LOGIN'
            );

            _futScalpingSetMessage(
                'Inicia sesión para configurar tus alertas de scalping.',
                'secondary'
            );

            const userLabel = document.getElementById(
                'futures-scalping-user-label'
            );

            if (userLabel) {
                userLabel.textContent = 'Invitado';
            }

            return false;
        }

        if (
            !response.ok
            || data.success !== true
            || !data.preferences
        ) {
            throw new Error(
                data.error
                || `HTTP ${response.status}`
            );
        }

        _futScalpingApplyPreferences(
            data.preferences,
            data.user
        );

        window._futuresScalpingPreferencesLoaded = true;

        return true;

    } catch (error) {
        console.error(
            '❌ FUTURES SCALPING PREF GET:',
            error
        );

        window._futuresScalpingPreferencesLoaded = false;

        _futScalpingSetStatus(
            'ERROR'
        );

        _futScalpingSetMessage(
            'No se pudieron cargar las preferencias de scalping.',
            'danger'
        );

        return false;
    }
};


function _futScalpingCollectForm() {
    const enabled = Boolean(
        document.getElementById(
            'futures-scalping-enabled'
        )?.checked
    );

    const timeframes = Array.from(
        document.querySelectorAll(
            '[data-scalping-tf]:checked'
        )
    ).map(
        input => input.value
    );

    const weekdays = Array.from(
        document.querySelectorAll(
            '[data-scalping-day]:checked'
        )
    ).map(
        input => Number(input.value)
    ).filter(
        value => (
            Number.isInteger(value)
            && value >= 1
            && value <= 7
        )
    );

    const startTime = (
        document.getElementById(
            'futures-scalping-start-time'
        )?.value
        || null
    );

    const endTime = (
        document.getElementById(
            'futures-scalping-end-time'
        )?.value
        || null
    );

    const timezone = String(
        document.getElementById(
            'futures-scalping-timezone'
        )?.value
        || 'UTC'
    ).trim() || 'UTC';

    return {
        futures_scalping_telegram_enabled:
            enabled,

        futures_scalping_timeframes:
            timeframes,

        futures_scalping_start_time:
            startTime,

        futures_scalping_end_time:
            endTime,

        futures_scalping_weekdays:
            weekdays,

        futures_scalping_timezone:
            timezone
    };
}


function _futScalpingValidateForm(
    payload
) {
    if (
        !payload
        || typeof payload !== 'object'
    ) {
        return 'Configuración inválida.';
    }

    if (
        payload.futures_scalping_telegram_enabled
        !== true
    ) {
        return null;
    }

    if (
        !Array.isArray(
            payload.futures_scalping_timeframes
        )
        || payload.futures_scalping_timeframes.length === 0
    ) {
        return 'Selecciona al menos 5m, 15m o 30m.';
    }

    if (
        !payload.futures_scalping_start_time
        || !payload.futures_scalping_end_time
    ) {
        return 'Define hora inicial y hora final.';
    }

    if (
        !Array.isArray(
            payload.futures_scalping_weekdays
        )
        || payload.futures_scalping_weekdays.length === 0
    ) {
        return 'Selecciona al menos un día de scalping.';
    }

    if (
        !payload.futures_scalping_timezone
    ) {
        return 'Define una zona horaria.';
    }

    return null;
}


window.saveFuturesScalpingPreferences = async function() {
    if (!window.IS_FUTURES_PAGE) {
        return false;
    }

    const payload = (
        _futScalpingCollectForm()
    );

    const validationError = (
        _futScalpingValidateForm(
            payload
        )
    );

    if (validationError) {
        _futScalpingSetMessage(
            validationError,
            'warning'
        );

        futShowToast(
            validationError,
            'warning'
        );

        return false;
    }

    const button = document.getElementById(
        'btn-save-futures-scalping'
    );

    const originalHtml = (
        button
        ? button.innerHTML
        : ''
    );

    if (button) {
        button.disabled = true;
        button.innerHTML = (
            '<span class="spinner-border spinner-border-sm me-1"></span>'
            + 'Guardando...'
        );
    }

    _futScalpingSetMessage(
        'Guardando preferencias...',
        'info'
    );

    try {
        const response = await fetch(
            '/api/user/futures-scalping-preferences',
            {
                method: 'POST',
                credentials: 'same-origin',
                cache: 'no-store',
                headers: {
                    'Content-Type':
                        'application/json'
                },
                body: JSON.stringify(
                    payload
                )
            }
        );

        let data = {};

        try {
            data = await response.json();
        } catch (jsonError) {
            data = {};
        }

        if (response.status === 401) {
            _futScalpingSetStatus(
                'LOGIN'
            );

            _futScalpingSetMessage(
                'Debes iniciar sesión antes de guardar.',
                'warning'
            );

            futShowToast(
                'Debes iniciar sesión para configurar scalping.',
                'warning'
            );

            return false;
        }

        if (
            !response.ok
            || data.success !== true
            || !data.preferences
        ) {
            throw new Error(
                data.error
                || `HTTP ${response.status}`
            );
        }

        _futScalpingApplyPreferences(
            data.preferences,
            data.user
        );

        window._futuresScalpingPreferencesLoaded = true;

        futShowToast(
            data.preferences
                .futures_scalping_telegram_enabled
                ? '⚡ Alertas de scalping activadas.'
                : '🔕 Alertas de scalping desactivadas.',
            'success'
        );

        return true;

    } catch (error) {
        console.error(
            '❌ FUTURES SCALPING PREF POST:',
            error
        );

        _futScalpingSetStatus(
            'ERROR'
        );

        _futScalpingSetMessage(
            (
                'No se pudo guardar: '
                + (
                    error.message
                    || 'error desconocido'
                )
            ),
            'danger'
        );

        futShowToast(
            'No se pudieron guardar las preferencias de scalping.',
            'danger'
        );

        return false;

    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = (
                originalHtml
                || '💾 Guardar'
            );
        }
    }
};


function _futDetectBrowserTimezone() {
    try {
        const timezone = (
            Intl
            .DateTimeFormat()
            .resolvedOptions()
            .timeZone
        );

        if (!timezone) {
            throw new Error(
                'timezone no disponible'
            );
        }

        const input = document.getElementById(
            'futures-scalping-timezone'
        );

        if (input) {
            input.value = timezone;
        }

        _futScalpingSetMessage(
            `Zona detectada: ${timezone}`,
            'info'
        );

        return timezone;

    } catch (error) {
        _futScalpingSetMessage(
            'El navegador no pudo detectar la zona horaria.',
            'warning'
        );

        return null;
    }
}


// ============================================================================
// COMMIT 9.6 — UNIVERSO MULTI-RIESGO + OPPORTUNITY ROUTER
// ============================================================================
window._fut96Universe = null;

function _fut96GroupLabel(group) {
    const remote = window._derivUniverse?.group_labels || {};
    return remote[group] || ({CORE1:'CORE 1 · BTC/ETH/SOL', CORE2:'CORE 2 · XRP/ADA', MEDIUM:'MEDIUM · salida rápida', HIGH:'HIGH · salida muy rápida'})[group] || group;
}

function _fut96ApplyTimeframes(symbol) {
    const select = document.getElementById('interval-select');
    const data = window._fut96Universe;
    if (!select || !data?.groups) return;
    let groupName = null;
    for (const [group, cfg] of Object.entries(data.groups)) {
        if ((cfg.symbols || []).includes(symbol)) { groupName = group; break; }
    }
    if (!groupName) return;
    const allowed = data.groups[groupName].timeframes || [];
    const labels = {'30m':'30 Minutos','1h':'1 Hora','2h':'2 Horas','4h':'4 Horas','12h':'12 Horas','1D':'1 Día'};
    const previous = select.value;
    select.innerHTML = allowed.map(tf => `<option value="${tf}">${labels[tf] || tf}</option>`).join('');
    select.value = allowed.includes(previous) ? previous : (allowed.includes(window.PAGE_CONFIG?.defaultTimeframe) ? window.PAGE_CONFIG.defaultTimeframe : (allowed.includes('1h') ? '1h' : allowed[0]));
    select.dataset.riskClass = groupName;
}

window.loadFuturesUniverse96 = async function() {
    try {
        const response = await fetch(DERIV_API_BASE + '/universe', {cache:'no-store'});
        const data = await response.json();
        if (!data?.success) return false;
        window._fut96Universe = data;
        const select = document.getElementById('symbol-select');
        if (!select) return true;
        const previous = select.value || window.PAGE_CONFIG?.defaultSymbol || 'BTC-USDT';
        let html = '';
        window._derivUniverse = data || {};
        const groupOrder = Array.isArray(data.group_order) && data.group_order.length ? data.group_order : ['CORE1','CORE2','MEDIUM','HIGH'];
        for (const group of groupOrder) {
            const cfg = data.groups[group];
            if (!cfg) continue;
            html += `<optgroup label="${_fut96GroupLabel(group)}">`;
            for (const symbol of (cfg.symbols || [])) {
                const label = data.symbols?.[symbol]?.name || symbol.replace('-', '/');
                html += `<option value="${symbol}">${label}</option>`;
            }
            html += '</optgroup>';
        }
        select.innerHTML = html;
        const all = Object.keys(data.symbols || {});
        select.value = all.includes(previous) ? previous : (window.PAGE_CONFIG?.defaultSymbol || all[0] || 'BTC-USDT');
        _fut96ApplyTimeframes(select.value);
        return true;
    } catch (error) {
        console.warn('FUTURES 9.6 universe:', error);
        return false;
    }
};

function _fut96EnsureOpportunityPanel() {
    // RC9.7.9 — "Señales activas" vuelve a ser una vía separada de
    // navegación hacia el análisis actual. Nunca se mezcla con el lifecycle
    // de confirmadas/vigentes y no ofrece Guardar desde esta lista.
    return document.getElementById('current-active-signals-list');
}

window.loadFuturesOpportunities96 = async function() {
    const panel = _fut96EnsureOpportunityPanel();
    const countEl = document.getElementById('current-active-signals-count');
    if (!panel) return;

    panel.innerHTML = `
        <div class="list-group-item bg-dark text-info text-center py-3">
            <div class="spinner-border spinner-border-sm me-2"></div>
            Buscando señales activas del análisis actual...
        </div>`;

    try {
        const selectedSymbol = String(
            document.getElementById('symbol-select')?.value
            || window.currentSymbol
            || 'BTC-USDT'
        );
        const selectedTimeframe = String(
            document.getElementById('interval-select')?.value
            || window.currentInterval
            || '1h'
        );
        const params = new URLSearchParams({
            limit: '63',
            symbol: selectedSymbol,
            timeframe: selectedTimeframe,
            _ts: String(Date.now())
        });
        const response = await fetch(`${DERIV_API_BASE}/opportunities?${params.toString()}`, {cache:'no-store'});
        const data = await response.json();
        const rows = Array.isArray(data?.opportunities) ? data.opportunities : [];
        const total = Number.isFinite(Number(data?.count)) ? Number(data.count) : rows.length;

        // RC9.7.13 — Activas y su diagnóstico salen de la MISMA vela abierta.
        // Nunca reutilizar el snapshot CLOSED_CANDLE de Confirmadas/Vigentes.
        const currentDiagnostics = document.getElementById('current-active-diagnostics');
        if (currentDiagnostics) {
            currentDiagnostics.innerHTML = futRenderAnalysisDiagnostics(data, 'active');
        }

        if (countEl) {
            countEl.textContent = String(total);
            countEl.className = `badge bg-${total > 0 ? 'success' : 'secondary'}`;
            countEl.title = `${total} señal(es) activa(s) en el análisis actual`;
        }

        if (!rows.length) {
            if (data?.processing_selected) {
                panel.innerHTML = `
                    <div class="list-group-item bg-dark text-muted text-center py-3">
                        <div class="spinner-border spinner-border-sm text-success me-2"></div>
                        Preparando la señal activa de ${selectedSymbol.replace('-', '/')} ${selectedTimeframe}...
                        <br><small>Vigentes y Confirmadas siguen disponibles mientras se calcula.</small>
                    </div>`;
                clearTimeout(window.__rc9717FutActiveRetry);
                window.__rc9717FutActiveRetry = setTimeout(
                    () => window.loadFuturesOpportunities96?.(),
                    6000
                );
                return;
            }
            panel.innerHTML = `
                <div class="list-group-item bg-dark text-muted text-center py-3">
                    <strong>No hay señales activas ejecutables en este momento.</strong>
                    <br>
                    <small>El análisis continúa; no se fuerza una entrada.</small>
                </div>`;
            return;
        }

        panel.innerHTML = rows.map((r) => {
            const action = String(r.action || '').toUpperCase();
            const isLong = action === 'LONG';
            const badge = isLong ? 'success' : 'danger';
            const icon = isLong ? '📈' : '📉';
            const symbol = String(r.symbol || '').replace('-', '/');
            const tf = String(r.timeframe || '--');
            const quality = Number(r.quality_score || 0);
            const rr = Number(r.risk_reward || 0);
            const safety = Number(r.execution_safety || 0);
            const riskClass = String(r.risk_class || '');

            return `
                <button
                    type="button"
                    class="list-group-item list-group-item-action bg-dark text-white border-secondary text-start"
                    onclick="window.changeToSignal('${String(r.symbol || '').replace(/'/g, "\\'")}', '${String(r.timeframe || '').replace(/'/g, "\\'")}')"
                    title="Abrir gráficos, indicadores y recomendación técnica"
                >
                    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
                        <div>
                            <span class="badge bg-${badge} me-2">${icon} ${action}</span>
                            <strong>${symbol}</strong>
                            <span class="badge bg-dark ms-1">${tf}</span>
                        </div>
                        <div>
                            ${riskClass ? `<span class="badge bg-secondary me-1">${riskClass}</span>` : ''}
                            <span class="badge bg-success">Activa</span>
                        </div>
                    </div>
                    <div class="small text-muted mt-2">
                        Calidad ${quality.toFixed(0)}/100 · Seguridad ${safety.toFixed(0)} · R/R 1:${rr.toFixed(2)}
                    </div>
                    <div class="small text-info mt-1">
                        Abrir par/temporalidad → gráficos → indicadores → recomendación técnica
                    </div>
                </button>`;
        }).join('');
    } catch (error) {
        if (countEl) {
            countEl.textContent = 'ERR';
            countEl.className = 'badge bg-danger';
        }
        panel.innerHTML = `
            <div class="list-group-item bg-dark text-muted text-center py-3">
                Señales activas temporalmente no disponibles.
            </div>`;
    }
};

// ============================================================================
// RC9.7.17 — PRIORIDAD VISUAL DE CARRILES FUTURES
// Vigentes > Confirmadas > Activas. Sólo reordena si comparten contenedor.
// ============================================================================
window.prioritizeFuturesSignalLanes = function prioritizeFuturesSignalLanes() {
    try {
        const vigent = document.getElementById('active-signals-list')?.closest('.card');
        const confirmed = document.getElementById('prev-signals-list')?.closest('.card');
        const active = document.getElementById('current-active-signals-list')?.closest('.card');
        if (!vigent || !confirmed || !active) return false;
        const parent = vigent.parentElement;
        if (!parent || confirmed.parentElement !== parent || active.parentElement !== parent) return false;
        parent.insertBefore(vigent, confirmed);
        parent.insertBefore(confirmed, active);
        return true;
    } catch (_) {
        return false;
    }
};

// ============================================================================
// INICIALIZACIÓN
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Commit 9.6 — una sola experiencia Futures. 5m/15m scalping dejó de ser
    // producto operativo; se elimina su formulario y todas las alertas válidas
    // utilizan el mismo monitor de zona de Entry.
    try {
        const scalpingBody = document.getElementById('futures-scalping-settings-body');
        if (scalpingBody) {
            const container = scalpingBody.closest('.accordion-item, .card, .panel, section') || scalpingBody;
            container.remove();
        }
        window.loadFuturesScalpingPreferences = async () => null;
        window.saveFuturesScalpingPreferences = async () => false;
    } catch (e) {
        console.warn('FUTURES 9.6 scalping cleanup:', e);
    }
    const _fut96SymbolSelect = document.getElementById('symbol-select');
    _fut96SymbolSelect?.addEventListener('change', (event) => {
        _fut96ApplyTimeframes(event.target.value);
    }, true);
    setTimeout(() => window.loadFuturesUniverse96(), 150);
    // RC9.8.1 — Activas intrabar: el polling debe ser menor que el TTL más
    // corto del preview para evitar huecos falsos de 0 entre refrescos.
    setInterval(() => {
        if (!document.hidden) window.loadFuturesOpportunities96();
    }, 90000);
    // =========================================================================
    // RESTAURAR LAS FUNCIONES DE FUTUROS
    // =========================================================================
    // script.js registra su propio DOMContentLoaded antes que futures.js y
    // puede sobrescribir temporalmente estas funciones con la versión Spot.
    // Aquí restauramos explícitamente las versiones de Futuros.
    // =========================================================================

    if (
        typeof window._futuresUpdateActiveSignals === 'function'
    ) {
        window.updateActiveSignals =
            window._futuresUpdateActiveSignals;

        console.log(
            '✅ FUTUROS: updateActiveSignals restaurada'
        );
    } else {
        console.error(
            '❌ FUTUROS: no existe _futuresUpdateActiveSignals'
        );
    }

    if (
        typeof window._futuresUpdatePreviousSignals === 'function'
    ) {
        window.updatePreviousSignals =
            window._futuresUpdatePreviousSignals;

        console.log(
            '✅ FUTUROS: updatePreviousSignals restaurada'
        );
    } else {
        console.error(
            '❌ FUTUROS: no existe _futuresUpdatePreviousSignals'
        );
    }
    setTimeout(() => {
        insertReviewTraderPanel();
    }, 800);
    // =====================================================================
    // COMMIT 36L — PREFERENCIAS SCALPING FUTURES
    // =====================================================================

    const scalpingCollapse = document.getElementById(
        'futures-scalping-settings-body'
    );

    if (scalpingCollapse) {
        scalpingCollapse.addEventListener(
            'shown.bs.collapse',
            () => {
                // Releer al abrir: si el usuario inició sesión después
                // de cargar la página, aquí recuperamos sus preferencias.
                window.loadFuturesScalpingPreferences({
                    silent:
                        window._futuresScalpingPreferencesLoaded
                });
            }
        );
    }

    document.getElementById(
        'btn-save-futures-scalping'
    )?.addEventListener(
        'click',
        window.saveFuturesScalpingPreferences
    );

    document.getElementById(
        'btn-refresh-futures-scalping'
    )?.addEventListener(
        'click',
        () => {
            window.loadFuturesScalpingPreferences({
                silent: false
            });
        }
    );

    document.getElementById(
        'btn-detect-futures-scalping-timezone'
    )?.addEventListener(
        'click',
        _futDetectBrowserTimezone
    );

    // Una lectura silenciosa actualiza el badge ON/OFF.
    // Si todavía no hay login, queda LOGIN y se reintenta al abrir el panel.
    setTimeout(
        () => {
            window.loadFuturesScalpingPreferences({
                silent: true
            });
        },
        1800
    );

    
    // ============ INICIALIZAR ANÁLISIS PRINCIPAL DE FUTUROS ============

    // RC9.7.17: paneles internos ReviewTrader/Estrategias Globales retirados
    // del frontend. El aprendizaje backend continúa sin polling visual.
    
    // RC9.7.17 — prioridad operativa: Vigentes > Confirmadas > Activas.
    // updateActiveSignals en Futures es el lifecycle VIGENTE histórico;
    // loadFuturesOpportunities96 es la Activa intrabar de vela abierta.
    setTimeout(() => {
        if (typeof window.updateActiveSignals === 'function') {
            console.log(`🚀 ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futures'}: cargando Vigentes (prioridad 1)`);
            window.updateActiveSignals();
        }
        setTimeout(() => {
            if (typeof window.updatePreviousSignals === 'function') {
                console.log(`📜 ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futures'}: cargando Confirmadas (prioridad 2)`);
                window.updatePreviousSignals();
            }
        }, 500);
        setTimeout(() => {
            console.log(`🟢 ${window.IS_MULTI_ASSET_PAGE ? 'Multi-Activo' : 'Futures'}: cargando Activas (prioridad 3)`);
            window.loadFuturesOpportunities96?.();
        }, 1600);
        setTimeout(() => window.prioritizeFuturesSignalLanes?.(), 2200);
    }, 1200);
    
    // Refrescar señales activas cada 2 min (v15: reduce carga)
    setInterval(() => {
        if (!document.hidden && typeof window.updateActiveSignals === 'function') window.updateActiveSignals();
    }, 300000);
    
    // Refrescar señales anteriores cada 10 min
    setInterval(() => {
        if (!document.hidden && typeof window.updatePreviousSignals === 'function') window.updatePreviousSignals();
    }, 1800000);
    
    // Cargar correlación al inicio
    setTimeout(() => {
        if (typeof window.updateCorrelationInfo === 'function') {
            window.updateCorrelationInfo({});
        }
    }, 1500);
    
    // Refrescar contexto cuando cambia temporalidad O símbolo.
    const refreshFuturesContext = () => {
        setTimeout(() => {
            if (typeof window.updateCorrelationInfo === 'function') {
                window.updateCorrelationInfo({});
            }
            if (typeof window.updateActiveSignals === 'function') {
                window.updateActiveSignals();
            }
            // runCompleteAnalysis() ya disparó el preview del nuevo par/TF;
            // releer Activas después de que termine y reiniciar su reloj.
            setTimeout(() => window.loadFuturesOpportunities96?.(), 5000);
                }, 500);
    };
    document.getElementById('interval-select')?.addEventListener('change', refreshFuturesContext);
    document.getElementById('symbol-select')?.addEventListener('change', refreshFuturesContext);
});


// ============================================================================
// v22.9: SEÑALES GUARDADAS (solo página FUTUROS)
// ============================================================================
// El usuario ve una señal en "Señales de la Vela Anterior" → click → modal
// justificación → botón GUARDAR → modal con inputs → confirmar → señal
// aparece en pestaña "Señales Guardadas" con KPIs propios.
//
// Auto-cierre: el learning_worker cada 30 min evalúa contra precio actual
// y marca entry_touched / tp_hit / sl_hit. Cuando se cierra por TP/SL o
// manualmente, deja de aparecer en la lista de activas.
// ============================================================================

// Referencia global a la señal actualmente mostrada en el modal de justificación
window._currentPrevSignal = null;
// Referencia global a la señal guardada mostrada en el modal detalle
window._currentSavedSignal = null;

// ============ Botón GUARDAR en modal de justificación ============
// Solo visible en la página de FUTUROS. Se hace visible cuando showFuturesPrevJustif se ejecuta.
// ============ Botón GUARDAR en modal de justificación ============
// Solo visible en la página de FUTUROS. Se hace visible cuando showFuturesPrevJustif se ejecuta.
(function _wrapShowPrevJustif() {
    if (!window.IS_FUTURES_PAGE) return;
    const original = window.showFuturesPrevJustif;
    if (typeof original !== 'function') return;

    window.showFuturesPrevJustif = function(sig) {
        // Esta ruta nace exclusivamente de /api/futures/signals/previous.
        // El backend exige esta procedencia para impedir que un análisis actual
        // se guarde accidentalmente como si fuera una señal de vela cerrada.
        if (sig) sig.source_context = 'PREVIOUS_CONFIRMED';
        // Guardar la señal en una variable global PERO también pasarla directamente al botón
        window._currentPrevSignal = sig;
        original(sig);
        
        // Configurar el botón GUARDAR para que pase la señal DIRECTAMENTE
        setTimeout(() => {
            const btn = document.getElementById('btn-save-signal');
            if (btn) {
                btn.style.display = 'inline-block';
                // PASAR sig DIRECTAMENTE - no depender de window._currentPrevSignal
                btn.onclick = function() {
                    window.openSaveSignalModal(sig, false);
                };
            }
        }, 150);
    };
})();

// ============ Abrir modal "Guardar señal" ============
// ============ Abrir modal "Guardar señal" ============
window.openSaveSignalModal = function(sig, alreadyInPosition = false) {
    // Si no recibe parámetro, fallback a la variable global (compatibilidad)
    if (!sig) {
        sig = window._currentPrevSignal;
    }
    
    // Si sigue sin haber señal, intentar usar el análisis actual del panel principal
    if (!sig && window.currentAnalysis && window.currentAnalysis.decision) {
        const d = window.currentAnalysis.decision;
        const l = window.currentAnalysis.levels || {};
        sig = {
            symbol: window.currentAnalysis.symbol || window.currentSymbol,
            timeframe: window.currentAnalysis.timeframe || window.currentInterval,
            action: (d.action === 'SHORT' || d.action === 'VENTA_SPOT') ? 'SHORT' : 'LONG',
            confidence: d.confidence || 0,
            entry: l.entry || window.currentAnalysis.current_price,
            stop_loss: l.stop_loss || 0,
            take_profit: l.take_profit || 0,
            leverage: l.leverage || 1
        };
        console.log('✅ Usando análisis actual como fallback:', sig.symbol, sig.action);
    }
    
    if (!sig) {
        showToast('No hay señal activa ni seleccionada. Esperá a que cargue el análisis o hacé clic en una señal de la vela anterior.', 'warning');
        return;
    }

    window._currentPrevSignal = sig;
    window._saveSignalAlreadyInPosition = Boolean(alreadyInPosition);
    const isManualAnalysis = (
        sig.execution_origin
        === 'USER_MANUAL_ANALYSIS'
    );

    if (
        isManualAnalysis
        && (
            !(Number(sig.entry) > 0)
            || !(Number(sig.stop_loss) > 0)
            || !(Number(sig.take_profit) > 0)
        )
    ) {
        futShowToast(
            'No se puede guardar manualmente: faltan niveles originales válidos.',
            'warning'
        );
        return;
    }

    // Cerrar el modal actual de justificación
    const prevModal = bootstrap.Modal.getInstance(document.getElementById('prevSignalModal'));
    if (prevModal) prevModal.hide();

    // Prefijar inputs con los valores sugeridos por el sistema
    const info = document.getElementById('save-signal-info');
    if (info) {
        const emoji = sig.action === 'LONG' ? '📈' : '📉';
        const badgeClass = sig.action === 'LONG' ? 'success' : 'danger';
        info.innerHTML = `
            <div class="d-flex align-items-center mb-2">
                <span class="badge bg-${badgeClass} p-2 me-3">${emoji} ${sig.action}</span>
                <strong>${futEscapeHtml(futDisplaySymbol(sig.symbol, sig.display_name))}</strong>
                <span class="badge bg-dark ms-2">${sig.timeframe}</span>
                <span class="badge bg-secondary ms-2">Confianza ${Math.round(sig.confidence || 0)}%</span>
            </div>
        `;
    }

    document.getElementById('ss-investment').value = 10;
    const canonicalSaveLeverage = Number(sig.leverage || 1);
    const safeSaveLeverage = Number.isFinite(canonicalSaveLeverage) && canonicalSaveLeverage > 0
        ? Math.round(canonicalSaveLeverage)
        : 1;
    sig.leverage = safeSaveLeverage;
    document.getElementById('ss-leverage').value = safeSaveLeverage;
    document.getElementById('ss-leverage-hint').textContent = `Sugerido por el sistema: ${safeSaveLeverage}x`;
    
    // Fallback: si no hay entry/sl/tp en la señal, usar el precio actual del mercado como base
    const currentPrice = Number(
        sig.current_price
        || sig.live_price
        || window.lastPrices?.[sig.symbol]
        || window.currentAnalysis?.current_price
        || 0
    );
    const defaultEntry = currentPrice > 0 ? currentPrice.toFixed(2) : '';
    const defaultSL = currentPrice > 0 ? (currentPrice * 0.95).toFixed(2) : '';  // 5% abajo
    const defaultTP = currentPrice > 0 ? (currentPrice * 1.10).toFixed(2) : '';  // 10% arriba
    
    document.getElementById('ss-entry').value = alreadyInPosition
        ? (defaultEntry || sig.entry || sig.entry_price || '')
        : (sig.entry || sig.entry_price || defaultEntry);
    document.getElementById('ss-sl').value = sig.stop_loss || defaultSL;
    document.getElementById('ss-tp').value = sig.take_profit || defaultTP;
    document.getElementById('ss-notes').value = '';
    // v22.9.4: fecha/hora de ingreso — default = ahora en zona local del navegador
    document.getElementById('ss-entry-at').value = _nowLocalDatetimeInput();

    const modalElement = document.getElementById('saveSignalModal');
    const modalTitle = modalElement?.querySelector('.modal-title');
    const confirmButton = modalElement?.querySelector('.modal-footer .btn-success');
    if (modalTitle) {
        if (isManualAnalysis) {
            const riskClass = String(
                sig.manual_risk_class
                || ''
            ).toUpperCase();

            modalTitle.innerHTML = (
                riskClass === 'MEDIUM'
                    ? '🟠 Guardar seguimiento manual · Riesgo medio'
                    : '🔴 Guardar seguimiento experimental · Riesgo alto'
            );
        } else {
            modalTitle.innerHTML = alreadyInPosition
                ? '<i class="fas fa-check-circle me-2 text-success"></i>Guardar operación ya iniciada'
                : '<i class="fas fa-bookmark me-2 text-success"></i>Guardar señal y esperar Entry';
        }
    }
    if (confirmButton) {
        confirmButton.innerHTML = alreadyInPosition
            ? '<i class="fas fa-check me-2"></i>Guardar en operación'
            : '<i class="fas fa-check me-2"></i>Guardar señal';
    }

    // Habilitar preview del cálculo
    _updateSaveCalcPreview();
    ['ss-investment', 'ss-leverage', 'ss-entry', 'ss-sl', 'ss-tp'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', _updateSaveCalcPreview);
    });

    const modal = new bootstrap.Modal(document.getElementById('saveSignalModal'));
    modal.show();
};
function _updateSaveCalcPreview() {
    const sig = window._currentPrevSignal;
    if (!sig) return;
    const investment = parseFloat(document.getElementById('ss-investment').value) || 0;
    const leverage = parseInt(document.getElementById('ss-leverage').value) || 1;
    const entry = parseFloat(document.getElementById('ss-entry').value) || 0;
    const sl = parseFloat(document.getElementById('ss-sl').value) || 0;
    const tp = parseFloat(document.getElementById('ss-tp').value) || 0;
    const dir = sig.action === 'LONG' ? 1 : -1;
    
    if (entry <= 0 || sl <= 0 || tp <= 0) {
        document.getElementById('ss-calc-preview').innerHTML = '<span class="text-muted">Completa entry/SL/TP para ver el cálculo.</span>';
        return;
    }
    
    const tpPct = ((tp - entry) / entry) * 100 * leverage * dir;
    const slPct = ((sl - entry) / entry) * 100 * leverage * dir;
    const tpUsdt = investment * (tpPct / 100);
    const slUsdt = investment * (slPct / 100);
    const rr = Math.abs(tpPct / slPct).toFixed(2);
    
    document.getElementById('ss-calc-preview').innerHTML = `
        Si TP: <strong class="text-success">+${tpUsdt.toFixed(2)} USDT (${tpPct.toFixed(2)}%)</strong>
        · Si SL: <strong class="text-danger">${slUsdt.toFixed(2)} USDT (${slPct.toFixed(2)}%)</strong>
        · R/R: <strong>${rr}</strong>
    `;
}

// ============ Confirmar guardar señal ============
// v22.9.4: formatear fecha ISO -> string legible en hora local del navegador
function _fmtLocalDate(iso) {
    if (!iso) return '--';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return String(iso);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (e) {
        return String(iso);
    }
}

// v22.9.4: helper para formato datetime-local (YYYY-MM-DDTHH:mm) en hora local
function _nowLocalDatetimeInput() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// v22.9.4: convertir datetime-local (local naive) a ISO UTC
function _localDatetimeToISO(dtLocal) {
    if (!dtLocal) return null;
    try {
        // datetime-local no lleva zona; JS lo interpreta como hora local del navegador
        const d = new Date(dtLocal);
        if (isNaN(d.getTime())) return null;
        return d.toISOString();
    } catch (e) {
        return null;
    }
}

window.confirmSaveSignal = async function() {
    // Usar la señal que se pasó al abrir el modal (guardada en _currentPrevSignal)
    const sig = window._currentPrevSignal;
    if (!sig) {
        showToast('No hay señal seleccionada', 'warning');
        return;
    }

    // OBTENER USUARIO AUTENTICADO
    const user = (typeof getAuthenticatedUser === 'function' && getAuthenticatedUser()) 
              || (typeof currentUser !== 'undefined' && currentUser) 
              || localStorage.getItem('tgp_session_user') 
              || localStorage.getItem('smarttrading_user') 
              || 'Invitado';
    
    if (user === 'Invitado') {
        showToast('Debes iniciar sesión para guardar señales', 'warning');
        return;
    }

    const investment = parseFloat(document.getElementById('ss-investment').value);
    const leverage = parseInt(document.getElementById('ss-leverage').value);
    const entry = parseFloat(document.getElementById('ss-entry').value);
    const sl = parseFloat(document.getElementById('ss-sl').value);
    const tp = parseFloat(document.getElementById('ss-tp').value);
    const notes = document.getElementById('ss-notes').value || '';
    const entryAtLocal = document.getElementById('ss-entry-at').value;
    const entryAtISO = _localDatetimeToISO(entryAtLocal);

    if (!(investment > 0) || !(leverage > 0) || !(entry > 0) || !(sl > 0) || !(tp > 0)) {
        showToast('Todos los campos deben ser mayores que 0', 'warning');
        return;
    }

    const levelsAreOrdered = sig.action === 'LONG'
        ? (sl < entry && entry < tp)
        : (tp < entry && entry < sl);

    if (!levelsAreOrdered) {
        showToast(
            sig.action === 'LONG'
                ? 'LONG inválido: debe cumplirse SL < Entry < TP'
                : 'SHORT inválido: debe cumplirse TP < Entry < SL',
            'warning'
        );
        return;
    }

    const payload = {
        user_name: user,  // <-- AGREGADO: enviar usuario autenticado
        symbol: sig.symbol,
        timeframe: sig.timeframe,
        action: sig.action,
        confidence: sig.confidence,
        entry, stop_loss: sl, take_profit: tp,
        leverage, investment_usdt: investment,
        original_confidence: sig.confidence,
        original_entry: sig.entry,
        original_stop_loss: sig.stop_loss,
        original_take_profit: sig.take_profit,
        original_leverage: sig.leverage,
        candle_timestamp: sig.candle_timestamp,
        entry_at: entryAtISO,
        already_in_position: Boolean(window._saveSignalAlreadyInPosition),
        execution_origin:
            sig.execution_origin
            || 'SYSTEM_EXECUTABLE',

        risk_class:
            sig.manual_risk_class
            || 'PREMIUM',

        source_context:
            sig.source_context
            || null,

        source_signal_id:
            sig.source_signal_id
            || sig.signal_id
            || null,

        source_valid_until:
            sig.valid_until
            || sig.source_valid_until
            || null,

        manual_override_ack:
            Boolean(
                sig.manual_override_ack
            ),

        system_executable:
            sig.execution_origin
            !== 'USER_MANUAL_ANALYSIS',

        notes,
    };

    console.log('📤 Guardando señal:', payload);

    try {
        const res = await fetch('/api/saved_signals', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });

        // MANEJO DE ERRORES HTTP
        if (!res.ok) {
            const errorText = await res.text();
            console.error('❌ HTTP error:', res.status, errorText);
            showToast('Error ' + res.status + ': ' + (errorText || 'No autorizado'), 'error');
            return;
        }

        const json = await res.json();
        if (json.success) {
            showToast(
                window._saveSignalAlreadyInPosition
                    ? '✅ Operación guardada con Entry ya tocado'
                    : '✅ Señal guardada; el sistema esperará el Entry',
                'success'
            );
            const modal = bootstrap.Modal.getInstance(document.getElementById('saveSignalModal'));
            if (modal) modal.hide();
            await window.updateSavedSignalsList();
            // RC9.8.2: desaparece de Confirmadas/Vigentes sólo para este usuario.
            await window.refreshSignalLanesAfterSavedChange();
        } else {
            showToast('Error: ' + (json.error || 'no se pudo guardar'), 'danger');
        }
    } catch (e) {
        console.error('❌ Fetch error:', e);
        showToast('Error de red: ' + e.message, 'danger');
    }
};
// ============================================================================
// FASE 7G.1 — HISTORIAL CERRADO MINIMIZADO
// ============================================================================

function _closedSavedSignalsHistoryShell() {

    return `
        <details
            class="mt-2 border border-secondary rounded"
            ontoggle="window.loadClosedSavedSignalsHistory(this)"
        >
            <summary
                class="p-2 text-muted"
                style="cursor: pointer;"
            >
                📁 Historial cerrado
                <small>
                    (TP / SL / cierre manual / expiradas)
                </small>
            </summary>

            <div
                class="list-group list-group-flush"
                data-closed-history-list
            >
                <div
                    class="list-group-item bg-dark text-muted text-center"
                >
                    Abre esta sección para cargar
                    las operaciones cerradas.
                </div>
            </div>
        </details>
    `;
}


window.loadClosedSavedSignalsHistory =
async function(detailsEl) {

    if (
        !detailsEl
        || !detailsEl.open
    ) {
        return;
    }

    if (
        detailsEl.dataset.loaded
        === '1'
    ) {
        return;
    }

    const container =
        detailsEl.querySelector(
            '[data-closed-history-list]'
        );

    if (!container) {
        return;
    }

    detailsEl.dataset.loaded =
        '1';

    container.innerHTML = `
        <div
            class="list-group-item bg-dark text-info text-center"
        >
            <div
                class="spinner-border spinner-border-sm me-2"
            ></div>
            Cargando historial...
        </div>
    `;

    try {

        const response =
            await fetch(
                (
                    '/api/saved_signals'
                    + '?status='
                    + 'tp_hit,sl_hit,closed_manual,expired'
                    + '&limit=50'
                ),
                {
                    method:
                        'GET',

                    credentials:
                        'same-origin',

                    cache:
                        'no-store'
                }
            );

        const json =
            await response.json();

        if (
            !response.ok
            || !json.success
        ) {

            throw new Error(
                json.error
                || `HTTP ${response.status}`
            );
        }

        const closed =
            Array.isArray(
                json.signals
            )
                ? json.signals
                : [];

        if (
            closed.length === 0
        ) {

            container.innerHTML = `
                <div
                    class="list-group-item bg-dark text-muted text-center"
                >
                    No hay operaciones cerradas.
                </div>
            `;

            return;
        }

        let html = '';

        closed.forEach(
            s => {

                const emoji =
                    s.action === 'LONG'
                        ? '📈'
                        : '📉';

                const badgeClass =
                    s.action === 'LONG'
                        ? 'success'
                        : 'danger';

                const expiryMessage =
                    s.status === 'expired'
                        ? `
                            <div
                                class="
                                    small
                                    text-secondary
                                    mt-2
                                "
                            >
                                ⌛ Esta señal ya no es vigente:
                                no alcanzó su Entry dentro de
                                la ventana permitida.
                
                                <br>
                
                                <strong>
                                    Recomendación:
                                </strong>
                                no persigas el precio;
                                espera una nueva señal válida.
                            </div>
                        `
                        : '';                
                
                html += `
                    <a
                        href="#"
                        class="
                            list-group-item
                            list-group-item-action
                            bg-dark
                            text-white
                        "
                        onclick="
                            event.preventDefault();
                            window.openSavedSignalDetail(
                                '${s.id}'
                            );
                        "
                    >
                        <div
                            class="
                                d-flex
                                justify-content-between
                                align-items-center
                                flex-wrap
                            "
                        >
                            <div>
                                <span
                                    class="
                                        badge
                                        bg-${badgeClass}
                                        me-2
                                    "
                                >
                                    ${emoji}
                                    ${s.action}
                                </span>

                                <strong>
                                    ${
                                        (
                                            s.symbol
                                            || ''
                                        )
                                        .replace(
                                            '-',
                                            '/'
                                        )
                                    }
                                </strong>

                                <span
                                    class="
                                        badge
                                        bg-dark
                                        ms-1
                                    "
                                >
                                    ${s.timeframe}
                                </span>
                            </div>

                            <div
                                class="text-end"
                            >
                                ${
                                    _statusBadge(
                                        s.status,
                                        s.entry_touched
                                    )
                                }

                                ${
                                    _formatPnl(
                                        s
                                    )
                                }
                            </div>
                        </div>

                        ${expiryMessage}

                    </a>
                `;
            }
        );

        container.innerHTML =
            html;

    } catch (error) {

        detailsEl.dataset.loaded =
            '0';

        container.innerHTML = `
            <div
                class="list-group-item bg-dark text-danger"
            >
                Error cargando historial:
                ${error.message}
            </div>
        `;
    }
};


// ============ Refrescar lista y KPIs ============
window.updateSavedSignalsList = async function() {
    if (!window.IS_FUTURES_PAGE) return;

    if (
        typeof window.isSmartTradingAuthenticated === 'function'
        && !window.isSmartTradingAuthenticated()
    ) {
        console.log(
            '🔒 Futuros: señales guardadas requieren sesión.'
        );

        const card =
            document.getElementById('saved-signals-card');

        if (card) {
            card.style.display = 'none';
        }

        return;
    }

    const card = document.getElementById('saved-signals-card');
    const list = document.getElementById('saved-signals-list');
    if (!card || !list) return;
    
    // Mostrar la card en futuros
    card.style.display = 'block';
    
    try {
        const user =
            typeof window.getSmartTradingUser === 'function'
                ? window.getSmartTradingUser()
                : null;

        if (!user) {
            console.log(
                '🔒 Futuros: usuario no disponible.'
            );
            return;
        }

        // KPIs propios
        const kRes = await fetch(
            '/api/saved_signals/kpis',
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );
        const kJson = await kRes.json();
        if (kJson.success) {
            const k = kJson.data || {};
            const wrEl = document.getElementById('ss-kpi-winrate');
            const pnlEl = document.getElementById('ss-kpi-pnl');
            const cntEl = document.getElementById('ss-kpi-count');
            if (wrEl) {
                wrEl.textContent = `WR: ${(k.win_rate || 0).toFixed(1)}%`;
                let cls = 'bg-secondary';
                if (k.total >= 5) {
                    cls = k.win_rate >= 55 ? 'bg-success' : (k.win_rate >= 40 ? 'bg-warning text-dark' : 'bg-danger');
                }
                wrEl.className = 'badge ' + cls;
            }
            if (pnlEl) {
                const sign = (k.pnl_total_usdt || 0) >= 0 ? '+' : '';
                pnlEl.textContent = `PnL: ${sign}${(k.pnl_total_usdt || 0).toFixed(2)} USDT`;
                let cls = 'bg-secondary';
                if (k.total >= 5) {
                    cls = k.pnl_total_usdt > 0 ? 'bg-success' : (k.pnl_total_usdt < 0 ? 'bg-danger' : 'bg-warning text-dark');
                }
                pnlEl.className = 'badge ' + cls;
            }
            if (cntEl) {
                cntEl.textContent = `${k.total || 0} cerradas / ${k.active || 0} activas`;
            }
        }
        
        // Lista de todas (activas + cerradas recientes)
        // =============================================================
        // FASE 7G.1
        // =============================================================
        // La pantalla principal sólo necesita señales abiertas.
        //
        // Historial cerrado se carga únicamente cuando el
        // usuario despliega la sección correspondiente.
        // =============================================================

        const lRes = await fetch(
            (
                '/api/saved_signals'
                + '?status=active,entry_touched'
                + '&limit=100'
            ),
            {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store'
            }
        );
        const lJson = await lRes.json();
        if (!lJson.success) {
            list.innerHTML = `<div class="list-group-item bg-dark text-warning">Error: ${lJson.error || 'desconocido'}</div>`;
            return;
        }
        
        const signals = _derivPageSymbols(lJson.signals || []);
        if (signals.length === 0) {

            list.innerHTML = `
                <div
                    class="
                        list-group-item
                        bg-dark
                        text-muted
                        text-center
                        py-3
                    "
                >
                    <i
                        class="
                            fas
                            fa-check-circle
                            me-1
                        "
                    ></i>

                    No tienes señales abiertas
                    ni esperando Entry.
                </div>

                ${_closedSavedSignalsHistoryShell()}
            `;

            return;
        }
        // =============================================================
        // FUTURES POSITION GUARDIAN
        // =============================================================
        // Una sola petición para todas las posiciones abiertas.
        // El backend agrupa por símbolo + timeframe.
        // =============================================================
        
        let guardianBySignal = {};
        
        try {
            const gRes = await fetch(
                DERIV_API_BASE + '/position-guardian?user='
                + encodeURIComponent(user)
                + '&_ts='
                + Date.now(),
                {
                    cache: 'no-store'
                }
            );
        
            const gJson = await gRes.json();
        
            if (gJson.success) {
        
                (gJson.positions || []).forEach(
                    p => {
                        guardianBySignal[
                            p.signal_id
                        ] = p.guardian || {};
                    }
                );
            }
        
        } catch (guardianError) {
        
            console.warn(
                '⚠️ Futures Guardian no disponible:',
                guardianError
            );
        }        
        let html = '';
        signals.forEach(s => {
        
            const emoji =
                s.action === 'LONG'
                    ? '📈'
                    : '📉';
            const bgColor =
                s.action === 'LONG'
                    ? 'success'
                    : 'danger';        
            const statusBadge =
                _statusBadge(
                    s.status,
                    s.entry_touched
                );
        
            const pnlDisplay =
                _formatPnl(s);
        
            const guardian =
                guardianBySignal[
                    s.id
                ] || {};
        
            let guardianHtml = '';
            // =========================================================
            // COMMIT 29 — GESTIÓN DINÁMICA DEL FUTURES GUARDIAN
            // =========================================================
            //
            // Retrocompatible:
            //
            // - Si el backend nuevo entrega management_action,
            //   podemos mostrar PROTECT / EXTEND.
            //
            // - Si no existe management_action, el código antiguo
            //   continúa funcionando exactamente igual.
            //
            // IMPORTANTE:
            // Esto sólo muestra recomendaciones.
            // No modifica la posición, SL ni TP.
            // =========================================================

            const managementAction = String(
                guardian.management_action || ''
            ).toUpperCase();

            const guardianNumberOrNull = value => {

                if (
                    value === null
                    || value === undefined
                    || value === ''
                ) {
                    return null;
                }

                const number = Number(
                    value
                );

                return Number.isFinite(
                    number
                )
                    ? number
                    : null;
            };

            const originalGuardianSl =
                guardianNumberOrNull(
                    guardian.original_stop_loss
                )
                ?? guardianNumberOrNull(
                    s.stop_loss
                );

            const suggestedGuardianSl =
                guardianNumberOrNull(
                    guardian.suggested_stop_loss
                );

            const originalGuardianTp =
                guardianNumberOrNull(
                    guardian.original_take_profit
                )
                ?? guardianNumberOrNull(
                    s.take_profit
                );

            const suggestedGuardianTp =
                guardianNumberOrNull(
                    guardian.suggested_take_profit
                );

            const guardianProgressR =
                guardianNumberOrNull(
                    guardian.progress_r
                );

            const guardianTpProgress =
                guardianNumberOrNull(
                    guardian.tp_progress_ratio
                );

            const managementReason =
                guardian.management_reason
                || guardian.reason
                || '';

            const guardianProtects = (
                managementAction === 'PROTECT'
                || managementAction
                    === 'PROTECT_AND_EXTEND'
            );

            const guardianExtends = (
                managementAction === 'EXTEND'
                || managementAction
                    === 'PROTECT_AND_EXTEND'
            );        
            if (
                guardian.action
            ) {
                // =====================================================
                // PROTECT / EXTEND
                // =====================================================

                if (
                    guardianProtects
                    || guardianExtends
                ) {

                    let managementLabel =
                        'GESTIONAR';

                    let managementBadge =
                        'primary';

                    let managementIcon =
                        '🛡️';

                    if (
                        guardianProtects
                        && guardianExtends
                    ) {

                        managementLabel =
                            'PROTEGER + EXTENDER';

                        managementBadge =
                            'info text-dark';

                        managementIcon =
                            '🛡️🎯';

                    } else if (
                        guardianProtects
                    ) {

                        managementLabel =
                            'PROTEGER';

                        managementBadge =
                            'primary';

                        managementIcon =
                            '🛡️';

                    } else if (
                        guardianExtends
                    ) {

                        managementLabel =
                            'EXTENDER OBJETIVO';

                        managementBadge =
                            'success';

                        managementIcon =
                            '🎯';
                    }

                    // =============================================
                    // BLOQUE DE PROTECCIÓN DEL SL
                    // =============================================

                    let protectHtml = '';

                    if (
                        guardianProtects
                    ) {

                        protectHtml = `
                            <div
                                class="
                                    mt-2
                                    p-2
                                    rounded
                                    bg-dark
                                "
                                style="
                                    border-left:
                                    3px solid #3A8BFF;
                                "
                            >
                                <div
                                    class="
                                        small
                                        text-info
                                        mb-1
                                    "
                                >
                                    <strong>
                                        🛡️ Protección del riesgo
                                    </strong>
                                </div>

                                ${
                                    originalGuardianSl
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-muted
                                                    "
                                                >
                                                    SL original
                                                </span>

                                                <strong>
                                                    ${
                                                        futFormatPrice(
                                                            originalGuardianSl,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : ''
                                }

                                ${
                                    suggestedGuardianSl
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                    mt-1
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-info
                                                    "
                                                >
                                                    SL sugerido
                                                </span>

                                                <strong
                                                    class="
                                                        text-info
                                                    "
                                                >
                                                    ${
                                                        futFormatPrice(
                                                            suggestedGuardianSl,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : `
                                            <div
                                                class="
                                                    small
                                                    text-muted
                                                "
                                            >
                                                Nuevo SL todavía
                                                no disponible.
                                            </div>
                                        `
                                }

                                <div
                                    class="
                                        small
                                        text-muted
                                        mt-1
                                    "
                                >
                                    El Guardian sólo puede
                                    reducir el riesgo original;
                                    nunca ampliarlo.
                                </div>
                            </div>
                        `;
                    }

                    // =============================================
                    // BLOQUE DE EXTENSIÓN DEL TP
                    // =============================================

                    let extendHtml = '';

                    if (
                        guardianExtends
                    ) {

                        extendHtml = `
                            <div
                                class="
                                    mt-2
                                    p-2
                                    rounded
                                    bg-dark
                                "
                                style="
                                    border-left:
                                    3px solid #00C076;
                                "
                            >
                                <div
                                    class="
                                        small
                                        text-success
                                        mb-1
                                    "
                                >
                                    <strong>
                                        🎯 Extensión estructural
                                    </strong>
                                </div>

                                ${
                                    originalGuardianTp
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-muted
                                                    "
                                                >
                                                    TP original
                                                </span>

                                                <strong>
                                                    ${
                                                        futFormatPrice(
                                                            originalGuardianTp,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : ''
                                }

                                ${
                                    suggestedGuardianTp
                                    !== null
                                        ? `
                                            <div
                                                class="
                                                    d-flex
                                                    justify-content-between
                                                    small
                                                    mt-1
                                                "
                                            >
                                                <span
                                                    class="
                                                        text-success
                                                    "
                                                >
                                                    TP sugerido
                                                </span>

                                                <strong
                                                    class="
                                                        text-success
                                                    "
                                                >
                                                    ${
                                                        futFormatPrice(
                                                            suggestedGuardianTp,
                                                            s.symbol
                                                        )
                                                    }
                                                </strong>
                                            </div>
                                        `
                                        : `
                                            <div
                                                class="
                                                    small
                                                    text-muted
                                                "
                                            >
                                                Nuevo TP todavía
                                                no disponible.
                                            </div>
                                        `
                                }

                                <div
                                    class="
                                        small
                                        text-muted
                                        mt-1
                                    "
                                >
                                    El objetivo sólo se extiende
                                    cuando existe una referencia
                                    estructural posterior.
                                </div>
                            </div>
                        `;
                    }

                    // =============================================
                    // PROGRESO DE LA POSICIÓN
                    // =============================================

                    let progressHtml = '';

                    if (
                        guardianProgressR !== null
                        || guardianTpProgress !== null
                    ) {

                        progressHtml = `
                            <div
                                class="
                                    d-flex
                                    flex-wrap
                                    gap-2
                                    mt-2
                                "
                            >

                                ${
                                    guardianProgressR
                                    !== null
                                        ? `
                                            <span
                                                class="
                                                    badge
                                                    bg-dark
                                                    border
                                                    border-secondary
                                                "
                                            >
                                                Progreso:
                                                ${
                                                    guardianProgressR
                                                    >= 0
                                                        ? '+'
                                                        : ''
                                                }${
                                                    guardianProgressR
                                                        .toFixed(
                                                            2
                                                        )
                                                }R
                                            </span>
                                        `
                                        : ''
                                }

                                ${
                                    guardianTpProgress
                                    !== null
                                        ? `
                                            <span
                                                class="
                                                    badge
                                                    bg-dark
                                                    border
                                                    border-secondary
                                                "
                                            >
                                                TP recorrido:
                                                ${
                                                    Math.max(
                                                        0,
                                                        guardianTpProgress
                                                        * 100
                                                    ).toFixed(
                                                        0
                                                    )
                                                }%
                                            </span>
                                        `
                                        : ''
                                }

                            </div>
                        `;
                    }

                    guardianHtml = `
                        <div
                            class="
                                mt-2
                                p-2
                                border
                                border-info
                                rounded
                            "
                        >

                            <div
                                class="
                                    d-flex
                                    flex-wrap
                                    justify-content-between
                                    align-items-center
                                    gap-1
                                "
                            >

                                <span
                                    class="
                                        badge
                                        bg-${managementBadge}
                                    "
                                >
                                    ${managementIcon}
                                    Guardian:
                                    ${managementLabel}
                                </span>

                                <span
                                    class="
                                        badge
                                        bg-dark
                                    "
                                >
                                    Deterioro:
                                    ${
                                        Number(
                                            guardian
                                                .deterioration_score
                                            || 0
                                        ).toFixed(
                                            0
                                        )
                                    }/100
                                </span>

                            </div>

                            ${progressHtml}

                            ${protectHtml}

                            ${extendHtml}

                            ${
                                managementReason
                                    ? `
                                        <div
                                            class="
                                                small
                                                text-light
                                                mt-2
                                            "
                                        >
                                            ${
                                                futEscapeHtml(
                                                    managementReason
                                                )
                                            }
                                        </div>
                                    `
                                    : ''
                            }

                            <div
                                class="
                                    small
                                    text-warning
                                    mt-2
                                "
                            >
                                ⚠️ Recomendación del Guardian.
                                No modifica automáticamente
                                la orden en el exchange.
                            </div>

                        </div>
                    `;

                } else if (
                    guardian.action
                    === 'WAIT_ENTRY'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2">
                            <span class="badge bg-info">
                                🛡️ Guardian: ESPERANDO ENTRY
                            </span>
                
                            <div class="small text-info mt-1">
                                ${guardian.reason || ''}
                            </div>
                        </div>
                    `;
                
                } else if (
                    guardian.action
                    === 'EXIT'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2 p-2 border border-danger rounded">
                
                            <div class="mb-2">
                                <span class="badge bg-danger">
                                    🛡️ Guardian: SALIR
                                </span>
                
                                <span class="badge bg-dark ms-1">
                                    Deterioro:
                                    ${Number(
                                        guardian.deterioration_score || 0
                                    ).toFixed(0)}/100
                                </span>
                            </div>
                
                            <div class="small text-light">
                
                                <div class="mb-1">
                                    ⏱️ <strong>Tiempo:</strong>
                                    ${Number(
                                        guardian.elapsed_minutes || 0
                                    ).toFixed(0)} min
                                </div>
                
                                <div class="mb-1">
                                    📈 <strong>MFE:</strong>
                                    +${Number(
                                        guardian.mfe_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📉 <strong>MAE:</strong>
                                    -${Number(
                                        guardian.mae_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Avance favorable:</strong>
                                    ${Number(
                                        guardian.favorable_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    ⚠️ <strong>Movimiento adverso:</strong>
                                    ${Number(
                                        guardian.adverse_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Distancia restante a TP:</strong>
                                    ${Number(
                                        guardian.remaining_to_tp_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🛡️ <strong>Distancia al SL:</strong>
                                    ${Number(
                                        guardian.sl_distance_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>Objetivo total:</strong>
                                    ${Number(
                                        guardian.tp_distance_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    ⚡ <strong>Apalancamiento:</strong>
                                    ${Number(
                                        guardian.leverage || 0
                                    ).toFixed(0)}x
                                </div>
                
                                <div class="mt-2 text-danger">
                                    ${guardian.reason || ''}
                                </div>
                
                            </div>
                        </div>
                    `;
                
                } else if (
                    guardian.action
                    === 'REDUCE'
                ) {
                
                    guardianHtml = `
                        <div class="mt-2">
                            <span class="badge bg-warning text-dark">
                                🛡️ Guardian: REDUCIR / PROTEGER
                            </span>
                            <div class="small text-warning mt-1">
                                ${guardian.reason || ''}
                            </div>
                        </div>
                    `;
                
                } else {
                
                    guardianHtml = `
                        <div class="mt-2 p-2 border border-success rounded">
                
                            <div class="mb-2">
                                <span class="badge bg-success">
                                    🛡️ Guardian: MANTENER
                                </span>
                            </div>
                
                            <div class="small text-light">
                
                                <div class="mb-1">
                                    ⏱️ <strong>Tiempo:</strong>
                                    ${Number(
                                        guardian.elapsed_minutes || 0
                                    ).toFixed(0)} min
                                </div>
                
                                <div class="mb-1">
                                    📈 <strong>MFE:</strong>
                                    +${Number(
                                        guardian.mfe_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📉 <strong>MAE:</strong>
                                    -${Number(
                                        guardian.mae_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    🎯 <strong>TP restante:</strong>
                                    ${Number(
                                        guardian.remaining_to_tp_pct || 0
                                    ).toFixed(3)}%
                                </div>
                
                                <div class="mb-1">
                                    📊 <strong>Deterioro:</strong>
                                    ${Number(
                                        guardian.deterioration_score || 0
                                    ).toFixed(0)}/100
                                </div>
                
                            </div>
                        </div>
                    `;
                }
            }
            
            html += `
                <a href="#" class="list-group-item list-group-item-action bg-dark text-white"
                   onclick="event.preventDefault(); window.openSavedSignalDetail('${s.id}')">
                    <div class="d-flex justify-content-between align-items-center flex-wrap">
                        <div>
                            <span class="badge bg-${bgColor} me-2">${emoji} ${s.action}</span>
                            <strong>${(s.symbol || '').replace('-', '/')}</strong>
                            <span class="badge bg-dark ms-1">${s.timeframe}</span>
                            <span class="badge bg-secondary ms-1">${s.leverage}x</span>
                            <span class="text-muted ms-2 small">$${s.investment_usdt} USDT</span>
                        </div>
                        <div class="text-end">
                            ${statusBadge}
                            ${pnlDisplay}
                        </div>
                    </div>
                    ${guardianHtml}
                </a>
            `;
        });
        list.innerHTML =
            html
            + _closedSavedSignalsHistoryShell();
    } catch (e) {
        list.innerHTML = `<div class="list-group-item bg-dark text-danger">Error: ${e.message}</div>`;
    }
};

function _statusBadge(status, entryTouched) {
    if (status === 'active') return '<span class="badge bg-info">⏳ Esperando entry</span>';
    if (status === 'entry_touched') return '<span class="badge bg-primary">🎯 En operación</span>';
    if (status === 'tp_hit') return '<span class="badge bg-success">✅ TP</span>';
    if (status === 'sl_hit') return '<span class="badge bg-danger">❌ SL</span>';
    if (status === 'expired') {
        return '<span class="badge bg-secondary">⌛ Expirada sin Entry</span>';
    }
    if (status === 'closed_manual') {
        return entryTouched ? '<span class="badge bg-warning text-dark">🔒 Cerrada</span>'
                             : '<span class="badge bg-secondary">🔒 Cerrada (sin entry)</span>';
    }
    return `<span class="badge bg-secondary">${status}</span>`;
}

function _formatPnl(s) {
    if (s.status === 'active' || s.status === 'entry_touched') return '';
    if (!s.entry_touched) {
        return '<div class="small text-muted">Sin operación</div>';
    }
    const pct = parseFloat(s.pnl_pct || 0);
    const usdt = parseFloat(s.pnl_usdt || 0);
    const cls = pct >= 0 ? 'text-success' : 'text-danger';
    const sign = pct >= 0 ? '+' : '';
    return `<div class="small ${cls}"><strong>${sign}${usdt.toFixed(2)} USDT</strong> (${sign}${pct.toFixed(2)}%)</div>`;
}


// ============================================================================
// RC9.7.16 — FICHA DE SEÑAL ORIENTADA AL USUARIO
// ============================================================================
// El backend conserva IDs, familias, fuentes y atribuciones internas para
// ReviewTrader. Esta capa SOLO traduce esa evidencia a lenguaje de trading
// entendible para el usuario. No altera señales, scores ni aprendizaje.
// ============================================================================
function _futUserStrategyLabel(family, action) {
    const key = String(family || '').trim().toUpperCase();
    const direction = String(action || '').toUpperCase() === 'SHORT' ? 'bajista' : 'alcista';
    const labels = {
        'BREAKOUT_RETEST': `Ruptura y retesteo ${direction}`,
        'STRUCTURE_RETEST': `Retesteo de estructura ${direction}`,
        'TREND_PULLBACK': `Retroceso dentro de tendencia ${direction}`,
        'SWEEP_REVERSAL': `Reversión tras barrido de liquidez ${direction}`,
        'MEAN_REVERSION': `Retorno hacia zona de valor ${direction}`,
        'TREND_BREAK': `Ruptura de tendencia ${direction}`,
        'ROTATION': 'Rotación de activos',
    };
    return labels[key] || `Configuración técnica ${direction}`;
}

function _futScoreDescriptor(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '';
    if (n >= 85) return 'Muy alta';
    if (n >= 70) return 'Alta';
    if (n >= 55) return 'Media';
    return 'Baja';
}

function _futScoreForUser(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '--';
    return `${n.toFixed(1)}/100 · ${_futScoreDescriptor(n)}`;
}

function _futUserThesisLabel(direction, quality) {
    const raw = String(direction || '').trim().toUpperCase();
    const side = raw === 'BEARISH' || raw === 'SHORT' ? 'Bajista'
        : raw === 'BULLISH' || raw === 'LONG' ? 'Alcista'
        : 'Mixto';
    const q = Number(quality);
    if (!Number.isFinite(q)) return side;
    const strength = q >= 85 ? 'muy favorable' : q >= 70 ? 'favorable' : q >= 55 ? 'moderado' : 'débil';
    return `${side} · contexto ${strength}`;
}

function _futUserMtfLabel(value) {
    const key = String(value || '').trim().toUpperCase();
    const labels = {
        'SUPPORTIVE': 'Favorable',
        'ALIGNED': 'Muy favorable',
        'STRONGLY_ALIGNED': 'Muy favorable',
        'CONFIRMED': 'Favorable',
        'MIXED': 'Mixta',
        'NEUTRAL': 'Neutral',
        'OPPOSED': 'Desfavorable',
        'CONFLICTING': 'Mixta / con conflicto',
        'INCOMPLETE': 'Parcial',
    };
    return labels[key] || (key ? 'Disponible' : '--');
}

function _futUserRegimeLabel(value) {
    const key = String(value || '').trim().toUpperCase();
    const labels = {
        'TRENDING_BULL': 'Tendencia alcista',
        'TREND_UP': 'Tendencia alcista',
        'BULLISH': 'Tendencia alcista',
        'TRENDING_BEAR': 'Tendencia bajista',
        'TREND_DOWN': 'Tendencia bajista',
        'BEARISH': 'Tendencia bajista',
        'RANGING': 'Mercado lateral',
        'RANGE': 'Mercado lateral',
        'TRANSITION': 'Transición',
        'HIGH_VOLATILITY': 'Alta volatilidad',
        'LOW_VOLATILITY': 'Baja volatilidad',
    };
    return labels[key] || '';
}

function _futUserPatternEvidence(code) {
    const key = String(code || '').trim().toUpperCase();
    const labels = {
        'BAND_WALK_ALCISTA': 'Bandas de Bollinger mostraron continuidad alcista.',
        'BAND_WALK_BAJISTA': 'Bandas de Bollinger mostraron continuidad bajista.',
        'HCH_INVERTIDO': 'Se detectó un Hombro-Cabeza-Hombro invertido.',
        'HCH': 'Se detectó un Hombro-Cabeza-Hombro bajista.',
        'DOBLE_SUELO': 'Se detectó un doble suelo como zona de reacción alcista.',
        'DOBLE_TECHO': 'Se detectó un doble techo como zona de reacción bajista.',
        'PULLBACK_ALCISTA': 'El precio mostraba un retroceso dentro de una estructura alcista.',
        'PULLBACK_BAJISTA': 'El precio mostraba un rebote dentro de una estructura bajista.',
        'LIQUIDITY_SWEEP_ALCISTA': 'Se observó un barrido de liquidez con reacción alcista.',
        'LIQUIDITY_SWEEP_BAJISTA': 'Se observó un barrido de liquidez con reacción bajista.',
    };
    return labels[key] || '';
}

function _futUserMotive(raw, action) {
    const text = String(raw || '').trim();
    if (!text) return '';

    // Los IDs de playbook son internos. La estrategia amigable ya se muestra arriba.
    if (/^Playbook seleccionado:/i.test(text)) return '';

    const mtfMatch = text.match(/^Alineación multitemporal:\s*(.+?)\.?$/i);
    if (mtfMatch) {
        const label = _futUserMtfLabel(mtfMatch[1]);
        return label === '--' ? '' : `Los marcos temporales mostraban una alineación ${label.toLowerCase()} con la señal.`;
    }

    const thesisMatch = text.match(/^Calidad de tesis al confirmar:\s*([0-9.]+)/i);
    if (thesisMatch) {
        const n = Number(thesisMatch[1]);
        if (Number.isFinite(n)) {
            const direction = String(action || '').toUpperCase() === 'SHORT' ? 'bajista' : 'alcista';
            return `El contexto ${direction} al confirmar obtuvo ${n.toFixed(1)}/100 de calidad técnica.`;
        }
    }

    // Nunca mostrar nombres de traders internos. Sólo traducir la evidencia técnica.
    const supportMatch = text.match(/apoyó\s+con\s+([A-Z0-9_\-]+)/i);
    if (supportMatch) return _futUserPatternEvidence(supportMatch[1]);

    return '';
}


function _futUserReviewState(value) {
    const key = String(value || '').trim().toUpperCase();
    const labels = {
        'ENTRY_DEFENDED_TO_TARGET': 'Entry bien defendido hasta el objetivo',
        'ENTRY_TIMING_SUSPECTED': 'Timing de entrada mejorable',
        'FAST_ADVERSE_MOVE': 'Movimiento adverso rápido tras el Entry',
        'MANAGEMENT_OR_STOP_REVIEW': 'Conviene revisar gestión o ubicación del SL',
        'MARGINAL_RR_GEOMETRY': 'Relación riesgo/beneficio ajustada',
        'WEAK_RR_GEOMETRY': 'Relación riesgo/beneficio desfavorable',
        'GUARDIAN_HELPFUL': 'La gestión protegió valor',
        'GUARDIAN_HARMFUL': 'La gestión recortó parte del resultado',
        'MIXED_NO_CHANGE': 'Resultado mixto; sin ajuste',
        'POSITIVE_ECONOMIC_OUTCOME': 'Resultado económico positivo',
        'PROTECTED_STOP_WIN': 'Ganancia protegida mediante Stop Loss',
        'BREAKEVEN': 'Cierre cercano a equilibrio',
        'WIN': 'Ganadora',
        'LOSS': 'Perdedora',
        'UNFLAGGED': 'Sin observaciones relevantes',
        'UNKNOWN': 'Sin diagnóstico suficiente',
        'UNRESOLVED': 'Aún sin resolver',
        'PENDING_OR_NEUTRAL': 'Pendiente / neutral',
        'SUPPORTED': 'Respaldado por la evidencia',
        'WEAK': 'Evidencia débil',
        'MARGINAL': 'Evidencia marginal',
    };
    return labels[key] || (key ? key.toLowerCase().replaceAll('_', ' ') : '--');
}

function _futUserLearningAuthority(value) {
    const key = String(value || '').trim().toUpperCase();
    const labels = {
        'OBSERVE_ONLY': 'Solo observación',
        'BOUNDED_CALIBRATION': 'Calibración limitada',
        'BOUNDED_CONTINUITY': 'Evidencia favorable limitada',
        'REQUIRE_MORE_CONFIRMATION': 'Exige más confirmación',
    };
    return labels[key] || (key ? 'En evaluación' : 'Solo observación');
}

function _futIndicatorEvidence(indicators, action) {
    const i = indicators && typeof indicators === 'object' ? indicators : {};
    const side = String(action || '').toUpperCase();
    const out = [];
    const num = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
    };

    const adx = num(i.adx);
    if (adx !== null) {
        const label = adx >= 25 ? 'tendencia con fuerza' : adx >= 20 ? 'fuerza de tendencia moderada' : 'tendencia débil';
        out.push(`ADX ${adx.toFixed(1)}: ${label}.`);
    }

    const plusDi = num(i.plus_di);
    const minusDi = num(i.minus_di);
    if (plusDi !== null && minusDi !== null) {
        if (plusDi > minusDi) {
            out.push(`DMI: presión compradora superior (+DI ${plusDi.toFixed(1)} vs -DI ${minusDi.toFixed(1)}).`);
        } else if (minusDi > plusDi) {
            out.push(`DMI: presión vendedora superior (-DI ${minusDi.toFixed(1)} vs +DI ${plusDi.toFixed(1)}).`);
        }
    }

    const rsi = num(i.rsi);
    if (rsi !== null) {
        let note = 'zona neutral';
        if (rsi >= 70) note = side === 'LONG' ? 'momentum alto, pero precio exigido' : 'zona alta favorable a vigilar para rechazo';
        else if (rsi <= 30) note = side === 'SHORT' ? 'momentum bajista alto, pero precio exigido' : 'zona deprimida favorable a vigilar para reacción';
        else if (rsi >= 55) note = 'impulso comprador';
        else if (rsi <= 45) note = 'impulso vendedor';
        out.push(`RSI ${rsi.toFixed(1)}: ${note}.`);
    }

    const macd = num(i.macd_hist);
    if (macd !== null) {
        const aligned = (side === 'LONG' && macd > 0) || (side === 'SHORT' && macd < 0);
        out.push(`MACD: histograma ${macd.toFixed(4)}${aligned ? ', acompañaba la dirección.' : ', no acompañaba plenamente la dirección.'}`);
    }

    const vol = num(i.volume_ratio);
    if (vol !== null) {
        const label = vol >= 1.2 ? 'participación superior al promedio' : vol >= 0.8 ? 'volumen cercano al promedio' : 'participación inferior al promedio';
        out.push(`Volumen ${vol.toFixed(2)}× el promedio: ${label}.`);
    }

    const atr = num(i.atr_pct);
    if (atr !== null) {
        out.push(`Volatilidad observada (ATR): ${atr.toFixed(2)}%. Se utilizó para calibrar distancia, tolerancia y riesgo del Entry.`);
    }
    return out;
}

// ============ Modal DETALLE con gráfico Plotly + zonas TP/SL ============
window.openSavedSignalDetail = async function(signalId) {
    const modal = new bootstrap.Modal(document.getElementById('savedSignalDetailModal'));
    modal.show();
    
    const body = document.getElementById('saved-signal-detail-body');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-info"></div><p class="mt-3">Cargando gráfico...</p></div>';
    
    try {
        const res = await fetch(`/api/saved_signals/${signalId}/chart_data`);
        const json = await res.json();
        if (!json.success) {
            body.innerHTML = `<div class="alert alert-warning">${json.error || 'Error cargando datos'}</div>`;
            return;
        }
        
        const sig = json.signal;
        window._currentSavedSignal = sig;
        const c = json.candles;
        const currentPrice = json.current_price;
        
        // Habilitar/deshabilitar botones según estado
        const isOpen = (sig.status === 'active' || sig.status === 'entry_touched');
        document.getElementById('btn-ss-edit').style.display = isOpen ? 'inline-block' : 'none';
        document.getElementById('btn-ss-close-manual').style.display = isOpen ? 'inline-block' : 'none';
        
        // Renderizar body con panel de info + div para el gráfico
        const emoji = sig.action === 'LONG' ? '📈' : '📉';
        const badgeClass = sig.action === 'LONG' ? 'success' : 'danger';
        const statusBadge = _statusBadge(sig.status, sig.entry_touched);
        const pnlDisplay = _formatPnl(sig);

        // RC9.7.14 — configuration + post-trade review are read-only.
        // They are loaded only when this modal is opened, so the main Futures
        // dashboard stays light on Render Free.
        const cfg = json.signal_configuration || {};
        const forensic = json.trade_forensics || {};
        const globalLearning = json.global_execution_learning || {};
        const guardianGlobal = json.guardian_global_learning || {};
        const cfgStrategy = cfg.strategy || {};
        const cfgThesis = cfg.thesis || {};
        const cfgExecution = cfg.execution || {};
        const cfgRegime = cfg.market_regime || {};
        const fmtScore = (value, digits = 1) => {
            const n = Number(value);
            return Number.isFinite(n) ? n.toFixed(digits) : '--';
        };
        // RC9.7.16: la evidencia interna se conserva intacta en `cfg`, pero la UI
        // muestra una ficha para trader común, sin IDs de playbook ni nombres de
        // especialistas internos.
        const strategyLabel = _futUserStrategyLabel(cfgStrategy.family, sig.action);
        const thesisLabel = _futUserThesisLabel(cfgThesis.direction || sig.action, cfgThesis.quality);
        const mtfLabel = _futUserMtfLabel(cfgThesis.mtf_alignment);
        const regimeLabel = _futUserRegimeLabel(cfgRegime.regime);
        const motiveEvidence = (Array.isArray(cfg.motives) ? cfg.motives : [])
            .map(x => _futUserMotive(x, sig.action))
            .filter(Boolean);
        const indicatorEvidence = _futIndicatorEvidence(cfg.key_indicators || {}, sig.action);
        const userEvidence = [...new Set([...motiveEvidence, ...indicatorEvidence])].slice(0, 9);
        const motivesHtml = userEvidence.length
            ? `<ul class="mb-0 ps-3">${userEvidence.map(x => `<li>${futEscapeHtml(x)}</li>`).join('')}</ul>`
            : '<span class="text-muted">No hay evidencia histórica suficiente para ampliar esta ficha.</span>';
        const regimeHtml = regimeLabel
            ? `<div class="col-md-4"><span class="text-muted">Contexto de mercado:</span> <strong>${futEscapeHtml(regimeLabel)}</strong></div>`
            : '';
        const configurationHtml = cfg.available ? `
            <details class="mb-3 p-2 border border-secondary rounded bg-black">
                <summary class="fw-semibold">🧩 Ficha técnica de la señal</summary>
                <div class="row g-2 mt-1 small">
                    <div class="col-md-6"><span class="text-muted">Estrategia:</span> <strong>${futEscapeHtml(strategyLabel)}</strong></div>
                    <div class="col-md-6"><span class="text-muted">Contexto:</span> <strong>${futEscapeHtml(thesisLabel)}</strong></div>
                    <div class="col-md-4"><span class="text-muted">Alineación temporal:</span> <strong>${futEscapeHtml(mtfLabel)}</strong></div>
                    <div class="col-md-4"><span class="text-muted">Seguridad técnica:</span> <strong>${_futScoreForUser(cfgExecution.execution_safety)}</strong></div>
                    ${regimeHtml}
                    <div class="col-md-4"><span class="text-muted">Calidad de entrada:</span> <strong>${_futScoreForUser(cfgExecution.entry_score)}</strong></div>
                    <div class="col-md-4"><span class="text-muted">Zona alcanzable:</span> <strong>${_futScoreForUser(cfgExecution.entry_reachability_score)}</strong></div>
                    <div class="col-md-4"><span class="text-muted">Protección estructural del Entry:</span> <strong>${_futScoreForUser(cfgExecution.entry_defensibility_score)}</strong></div>
                </div>
                <div class="small mt-2"><strong>Evidencias técnicas:</strong>${motivesHtml}</div>
                <div class="small text-muted mt-2">Los puntajes son medidas internas de calidad técnica; no representan una probabilidad garantizada de tocar TP.</div>
            </details>` : '';

        const forensicReasons = Array.isArray(forensic.reasons)
            ? forensic.reasons.slice(0, 6).map(x => `<li>${futEscapeHtml(x)}</li>`).join('')
            : '';
        const closedStatus = ['tp_hit', 'sl_hit', 'closed_manual'].includes(String(sig.status || '').toLowerCase());
        const component = forensic.component_assessment || {};
        const guardianReview = forensic.guardian_review || {};
        const reviewHtml = closedStatus ? `
            <details open class="mb-3 p-2 border border-secondary rounded">
                <summary class="fw-semibold">🔬 Revisión técnica de la operación</summary>
                <div class="small mt-2">
                    ${forensicReasons ? `<ul class="mb-2 ps-3">${forensicReasons}</ul>` : '<span class="text-muted">Sin diagnóstico suficiente.</span>'}
                    <div>Resultado económico: <strong>${futEscapeHtml(_futUserReviewState(forensic.economic_outcome))}</strong> · R real: <strong>${fmtScore(forensic.actual_r, 2)}</strong> · MFE: <strong>${fmtScore(forensic.mfe_r, 2)}R</strong> · MAE: <strong>${fmtScore(forensic.mae_r, 2)}R</strong></div>
                    <div class="mt-1">Entry: <strong>${futEscapeHtml(_futUserReviewState((component.entry || {}).state))}</strong> · Geometría: <strong>${futEscapeHtml(_futUserReviewState((component.geometry || {}).state))}</strong> · Guardian: <strong>${futEscapeHtml(_futUserReviewState((component.guardian || {}).state))}</strong></div>
                    ${guardianReview.evaluated ? `<div class="mt-1">Guardian vs HOLD: <strong>${fmtScore(guardianReview.avg_delta_r, 2)}R</strong> (${Number(guardianReview.evaluated || 0)} evento/s evaluados)</div>` : ''}
                    <div class="mt-1 text-muted">Un trade = una muestra de mercado. Entry, estrategia, SL/TP y Guardian se diagnostican por separado sin multiplicar artificialmente N.</div>
                </div>
            </details>` : '';

        const globalCanonicalN = Number(globalLearning.sample_size || 0);
        const globalObservedN = Number(globalLearning.observed_trade_count_all_users || 0);
        const guardianGlobalN = Number(guardianGlobal.sample_size || 0);
        const globalHtml = (globalCanonicalN > 0 || globalObservedN > 0 || guardianGlobalN > 0) ? `
            <div class="mb-3 p-2 rounded bg-dark small">
                <strong>🌐 Aprendizaje agregado de ejecución</strong><br>
                ${futEscapeHtml(globalLearning.symbol || sig.symbol)} ${futEscapeHtml(globalLearning.timeframe || sig.timeframe)} ${futEscapeHtml(globalLearning.action || sig.action)} ·
                Observaciones=${globalObservedN} · N canónico=${globalCanonicalN}${globalCanonicalN > 0 ? ` · WR ${fmtScore(globalLearning.win_rate)}% · Exp ${fmtScore(globalLearning.expectancy_r, 2)}R` : ''} ·
                <span class="text-muted">${futEscapeHtml(_futUserLearningAuthority(globalLearning.authority))}</span>
                ${guardianGlobalN > 0 ? `<br>Guardian EXIT: N=${guardianGlobalN} · ajuste umbral=${fmtScore(guardianGlobal.exit_threshold_delta, 1)} · ${futEscapeHtml(guardianGlobal.reason || '')}` : ''}
            </div>` : '';
        
        body.innerHTML = `
            <div class="mb-3 d-flex flex-wrap align-items-center gap-2">
                <span class="badge bg-${badgeClass} p-2">${emoji} ${sig.action}</span>
                <strong>${futEscapeHtml(futDisplaySymbol(sig.symbol, sig.display_name))}</strong>
                <span class="badge bg-dark">${sig.timeframe}</span>
                <span class="badge bg-secondary">${sig.leverage}x</span>
                <span class="text-muted">$${sig.investment_usdt} USDT</span>
                ${statusBadge}
                <div class="ms-auto">${pnlDisplay}</div>
            </div>
            <div class="row g-2 mb-3 small">
                <div class="col-md-3"><span class="text-muted">Entry:</span> <strong class="text-primary">${sig.entry}</strong></div>
                <div class="col-md-3"><span class="text-muted">SL:</span> <strong class="text-danger">${sig.stop_loss}</strong></div>
                <div class="col-md-3"><span class="text-muted">TP:</span> <strong class="text-success">${sig.take_profit}</strong></div>
                <div class="col-md-3"><span class="text-muted">Precio actual:</span> <strong>${currentPrice}</strong></div>
            </div>
            <div class="row g-2 mb-3 small">
                <div class="col-md-6"><span class="text-muted">🕒 Ingreso:</span> <strong>${_fmtLocalDate(sig.entry_at || sig.created_at)}</strong></div>
                ${sig.entry_touched_at ? `<div class="col-md-6"><span class="text-muted">🎯 Entry tocado:</span> <strong>${_fmtLocalDate(sig.entry_touched_at)}</strong></div>` : ''}
            </div>
            ${configurationHtml}
            ${reviewHtml}
            ${globalHtml}
            <div id="saved-signal-chart" style="height: 500px;"></div>
            ${sig.notes ? `<div class="mt-3 p-2 bg-black rounded small"><strong>Notas:</strong> ${sig.notes}</div>` : ''}
        `;
        
        // Renderizar el gráfico Plotly
        if (
            c
            && c.time
            && c.time.length > 0
        ) {
        
            _renderSavedSignalChart(
                c,
                sig,
                currentPrice
            );
        
        } else {
        
            document.getElementById(
                'saved-signal-chart'
            ).innerHTML =
                '<div class="alert alert-warning">No hay datos de velas para este par/timeframe</div>';
        }
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
};

function _renderSavedSignalChart(candles, sig, currentPrice) {
    // GUARDAS DEFENSIVAS
    if (!candles || !candles.time || !Array.isArray(candles.time) || candles.time.length === 0) {
        console.warn('⚠️ Datos de velas inválidos:', candles);
        const chartDiv = document.getElementById('saved-signal-chart');
        if (chartDiv) chartDiv.innerHTML = '<div class="alert alert-warning">No hay datos de velas disponibles</div>';
        return;
    }
    if (!candles.open || !candles.high || !candles.low || !candles.close) {
        console.warn('⚠️ Faltan datos OHLC:', candles);
        return;
    }
    if (typeof Plotly === 'undefined' || !Plotly.newPlot) {
        console.warn('⚠️ Plotly no disponible');
        return;
    }

    const times = candles.time;
    const entry = parseFloat(sig.entry);
    const sl = parseFloat(sig.stop_loss);
    const tp = parseFloat(sig.take_profit);
    const isLong = sig.action === 'LONG';

   
    // Rango X: primer a último candle + un poco de margen a la derecha
    const xStart = times[0];
    const xEnd = times[times.length - 1];
    
    const traces = [{
        type: 'candlestick',
        x: times,
        open: candles.open,
        high: candles.high,
        low: candles.low,
        close: candles.close,
        name: 'Precio',
        increasing: {line: {color: '#00C076', width: 1}, fillcolor: '#00C076'},
        decreasing: {line: {color: '#FF5B5B', width: 1}, fillcolor: '#FF5B5B'},
        showlegend: false,
    }];
    
    // Zonas: verde (favorable) y roja (desfavorable) tipo TradingView
    // LONG: entry→TP arriba (verde), entry→SL abajo (rojo)
    // SHORT: entry→TP abajo (verde), entry→SL arriba (rojo)
    const shapes = [
        // Zona de ganancia (verde)
        {
            type: 'rect', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: isLong ? entry : tp,
            y1: isLong ? tp : entry,
            fillcolor: 'rgba(0, 192, 118, 0.15)',
            line: {color: 'rgba(0, 192, 118, 0.5)', width: 1},
            layer: 'below',
        },
        // Zona de pérdida (rojo)
        {
            type: 'rect', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: isLong ? sl : entry,
            y1: isLong ? entry : sl,
            fillcolor: 'rgba(255, 91, 91, 0.15)',
            line: {color: 'rgba(255, 91, 91, 0.5)', width: 1},
            layer: 'below',
        },
        // Línea del entry
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: entry, y1: entry,
            line: {color: '#3A8BFF', width: 2, dash: 'solid'},
        },
        // Línea SL punteada
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: sl, y1: sl,
            line: {color: '#FF5B5B', width: 1.5, dash: 'dash'},
        },
        // Línea TP punteada
        {
            type: 'line', xref: 'x', yref: 'y',
            x0: xStart, x1: xEnd,
            y0: tp, y1: tp,
            line: {color: '#00C076', width: 1.5, dash: 'dash'},
        },
    ];
    
    const annotations = [
        {x: xEnd, y: entry, xref: 'x', yref: 'y', text: `Entry: ${entry}`,
         showarrow: false, xanchor: 'left', font: {color: '#3A8BFF', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#3A8BFF', borderwidth: 1, borderpad: 3},
        {x: xEnd, y: sl, xref: 'x', yref: 'y', text: `SL: ${sl}`,
         showarrow: false, xanchor: 'left', font: {color: '#FF5B5B', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#FF5B5B', borderwidth: 1, borderpad: 3},
        {x: xEnd, y: tp, xref: 'x', yref: 'y', text: `TP: ${tp}`,
         showarrow: false, xanchor: 'left', font: {color: '#00C076', size: 11},
         bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#00C076', borderwidth: 1, borderpad: 3},
    ];
    
    const layout = {
        paper_bgcolor: '#0A0C10',
        plot_bgcolor: '#0A0C10',
        font: {color: 'white', size: 11},
        xaxis: {rangeslider: {visible: false}, gridcolor: 'rgba(255,255,255,0.08)'},
        yaxis: {gridcolor: 'rgba(255,255,255,0.08)', side: 'right'},
        margin: {l: 40, r: 80, t: 20, b: 40},
        shapes,
        annotations,
        hovermode: 'x unified',
    };
    
    Plotly.newPlot('saved-signal-chart', traces, layout,
                   {responsive: true, displayModeBar: false});
}

// ============ Editar señal guardada ============
window.openEditSavedSignal = function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    document.getElementById('edit-ss-investment').value = sig.investment_usdt;
    document.getElementById('edit-ss-leverage').value = sig.leverage;
    document.getElementById('edit-ss-entry').value = sig.entry;
    document.getElementById('edit-ss-sl').value = sig.stop_loss;
    document.getElementById('edit-ss-tp').value = sig.take_profit;
    document.getElementById('edit-ss-notes').value = sig.notes || '';
    // v22.9.4: entry_at editable — convertir ISO UTC de la BD a datetime-local
    const entryAtEl = document.getElementById('edit-ss-entry-at');
    if (entryAtEl) {
        if (sig.entry_at) {
            try {
                const d = new Date(sig.entry_at);
                const pad = n => String(n).padStart(2, '0');
                entryAtEl.value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
            } catch (e) {
                entryAtEl.value = _nowLocalDatetimeInput();
            }
        } else {
            entryAtEl.value = _nowLocalDatetimeInput();
        }
    }
    
    // Cerrar el detalle para evitar solapamiento
    const detailModal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
    if (detailModal) detailModal.hide();
    
    const modal = new bootstrap.Modal(document.getElementById('editSavedSignalModal'));
    modal.show();
};

window.confirmEditSavedSignal = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const entryAtLocal = document.getElementById('edit-ss-entry-at').value;
    const entryAtISO = _localDatetimeToISO(entryAtLocal);
    
    const payload = {
        investment_usdt: parseFloat(document.getElementById('edit-ss-investment').value),
        leverage: parseInt(document.getElementById('edit-ss-leverage').value),
        entry: parseFloat(document.getElementById('edit-ss-entry').value),
        stop_loss: parseFloat(document.getElementById('edit-ss-sl').value),
        take_profit: parseFloat(document.getElementById('edit-ss-tp').value),
        notes: document.getElementById('edit-ss-notes').value || '',
        entry_at: entryAtISO,  // v22.9.4
    };
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });
        const json = await res.json();
        if (json.success) {
            showToast('✅ Señal modificada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('editSavedSignalModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Cerrar señal manualmente ============
window.closeSavedSignalManual = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const confirmed = confirm(
        sig.entry_touched
            ? '¿Cerrar la operación manualmente? Se calcula PnL con el precio actual.'
            : '⚠️ El precio aún no ha tocado el entry. Al cerrar NO cuenta para winrate ni PnL. ¿Continuar?'
    );
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}/close`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({}),  // el backend obtiene precio actual
        });
        const json = await res.json();
        if (json.success) {
            showToast('✅ Señal cerrada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
            if (modal) modal.hide();
            window.updateSavedSignalsList();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Eliminar señal guardada ============
window.deleteSavedSignal = async function() {
    const sig = window._currentSavedSignal;
    if (!sig) return;
    
    const confirmed = confirm('¿Eliminar esta señal permanentemente? Esta acción no se puede deshacer.');
    if (!confirmed) return;
    
    try {
        const res = await fetch(`/api/saved_signals/${sig.id}`, {method: 'DELETE'});
        const json = await res.json();
        if (json.success) {
            showToast('🗑️ Señal eliminada', 'success');
            const modal = bootstrap.Modal.getInstance(document.getElementById('savedSignalDetailModal'));
            if (modal) modal.hide();
            await window.updateSavedSignalsList();
            // RC9.8.2: al eliminar, si la señal global sigue confirmada o
            // vigente vuelve a su carril únicamente para este usuario.
            await window.refreshSignalLanesAfterSavedChange();
        } else {
            showToast('Error: ' + (json.error || ''), 'danger');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'danger');
    }
};

// ============ Auto-refresh de la lista cada 5 min ============
if (window.IS_FUTURES_PAGE) {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => window.updateSavedSignalsList(), 1500);
        setInterval(() => {
            if (!document.hidden) window.updateSavedSignalsList();
        }, 10 * 60 * 1000);
    });
}
// ============================================================================
// RC9.7.1 — PERFIL PERSONAL DE RIESGO FUTURES · FRONTEND RESTAURADO
// ============================================================================
// RC9.7 conservó el endpoint backend pero el JS que enlazaba el panel fue
// retirado accidentalmente. El resultado era un panel visual sin eventos:
// Usuario "—" y botones Guardar/Refrescar inertes incluso con sesión válida.
(function initFuturesRiskProfile97_1() {
    if (!window.IS_FUTURES_PAGE) return;
    if (window.__FUTURES_RISK_PROFILE_97_1_BOUND__) return;
    window.__FUTURES_RISK_PROFILE_97_1_BOUND__ = true;

    const byId = id => document.getElementById(id);
    const nullableNumber = id => {
        const raw = String(byId(id)?.value ?? '').trim();
        if (!raw) return null;
        const n = Number(raw);
        return Number.isFinite(n) ? n : null;
    };

    function renderMessage(text, type = 'secondary') {
        const el = byId('futures-risk-message');
        if (!el) return;
        el.className = `alert alert-${type} py-2 px-2 small mb-3`;
        el.textContent = text;
    }

    function renderProfile(profile = {}, user = null) {
        const mode = String(profile.futures_risk_mode || 'MANUAL').toUpperCase();
        const policy = String(profile.futures_margin_policy || 'FIXED_USDT').toUpperCase();
        if (byId('futures-risk-mode')) byId('futures-risk-mode').value = mode;
        if (byId('futures-margin-policy')) byId('futures-margin-policy').value = policy;
        if (byId('futures-risk-equity')) byId('futures-risk-equity').value = profile.futures_equity_usdt ?? '';
        if (byId('futures-risk-allocation')) byId('futures-risk-allocation').value = profile.futures_max_allocation_pct ?? '';
        if (byId('futures-risk-max-loss')) byId('futures-risk-max-loss').value = profile.futures_max_loss_pct_equity_per_trade ?? '';
        if (byId('futures-risk-preferred-margin')) byId('futures-risk-preferred-margin').value = profile.futures_preferred_margin_usdt ?? '';
        if (byId('futures-risk-max-leverage')) byId('futures-risk-max-leverage').value = profile.futures_personal_max_leverage ?? '';

        const userEl = byId('futures-risk-user-label');
        if (userEl) userEl.textContent = user || '—';

        const badge = byId('futures-risk-status-badge');
        if (badge) {
            badge.textContent = mode === 'PROFILE_ADVISORY' ? 'PERFIL' : 'MANUAL';
            badge.className = `badge ${mode === 'PROFILE_ADVISORY' ? 'bg-info text-dark' : 'bg-secondary'}`;
        }

        if (mode === 'PROFILE_ADVISORY') {
            renderMessage(
                'Perfil personal activo: el sistema puede reducir margen/apalancamiento según tus límites; nunca aumenta el riesgo permitido por el setup.',
                'info'
            );
        } else {
            renderMessage(
                'Modo manual: tú eliges el margen y el apalancamiento. El sistema no ajusta automáticamente el tamaño según tus límites personales.',
                'secondary'
            );
        }
    }

    window.clearFuturesRiskProfileUI = function() {
        renderProfile({futures_risk_mode: 'MANUAL', futures_margin_policy: 'FIXED_USDT'}, null);
        const badge = byId('futures-risk-status-badge');
        if (badge) {
            badge.textContent = 'LOGIN';
            badge.className = 'badge bg-warning text-dark';
        }
        renderMessage(`Inicia sesión para cargar o guardar tu perfil ${DERIV_MARKET_LABEL}.`, 'warning');
    };

    window.loadFuturesRiskProfile = async function({silent = false} = {}) {
        try {
            const response = await fetch('/api/user/futures-risk-profile', {
                method: 'GET',
                credentials: 'same-origin',
                cache: 'no-store',
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}

            if (response.status === 401 || data.authenticated === false) {
                window.clearFuturesRiskProfileUI();
                return false;
            }
            if (!response.ok || data.success !== true) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }

            renderProfile(data.profile || {}, data.user || null);
            if (!silent && typeof window.showToast === 'function') {
                window.showToast(`Perfil ${DERIV_MARKET_LABEL} actualizado`, 'success');
            }
            return true;
        } catch (error) {
            console.error('❌ loadFuturesRiskProfile:', error);
            renderMessage(`No se pudo cargar el perfil ${DERIV_MARKET_LABEL}: ${error.message}`, 'danger');
            return false;
        }
    };

    window.saveFuturesRiskProfile = async function() {
        const button = byId('btn-save-futures-risk');
        if (button) button.disabled = true;
        try {
            const payload = {
                futures_risk_mode: String(byId('futures-risk-mode')?.value || 'MANUAL').toUpperCase(),
                futures_margin_policy: String(byId('futures-margin-policy')?.value || 'FIXED_USDT').toUpperCase(),
                futures_equity_usdt: nullableNumber('futures-risk-equity'),
                futures_max_allocation_pct: nullableNumber('futures-risk-allocation'),
                futures_max_loss_pct_equity_per_trade: nullableNumber('futures-risk-max-loss'),
                futures_preferred_margin_usdt: nullableNumber('futures-risk-preferred-margin'),
                futures_personal_max_leverage: nullableNumber('futures-risk-max-leverage'),
            };

            const response = await fetch('/api/user/futures-risk-profile', {
                method: 'POST',
                credentials: 'same-origin',
                cache: 'no-store',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}

            if (response.status === 401 || data.authenticated === false) {
                window.clearFuturesRiskProfileUI();
                throw new Error(`Debes iniciar sesión antes de guardar el perfil ${DERIV_MARKET_LABEL}.`);
            }
            if (!response.ok || data.success !== true) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }

            renderProfile(data.profile || payload, data.user || null);
            if (typeof window.showToast === 'function') {
                window.showToast(`✅ Perfil de riesgo ${DERIV_MARKET_LABEL} guardado`, 'success');
            }
            return true;
        } catch (error) {
            console.error('❌ saveFuturesRiskProfile:', error);
            renderMessage(error.message || `No se pudo guardar el perfil ${DERIV_MARKET_LABEL}.`, 'danger');
            if (typeof window.showToast === 'function') {
                window.showToast(error.message || `No se pudo guardar el perfil ${DERIV_MARKET_LABEL}`, 'danger');
            }
            return false;
        } finally {
            if (button) button.disabled = false;
        }
    };

    const bind = () => {
        byId('btn-save-futures-risk')?.addEventListener('click', window.saveFuturesRiskProfile);
        byId('btn-refresh-futures-risk')?.addEventListener('click', () => window.loadFuturesRiskProfile({silent: false}));
        byId('futures-risk-mode')?.addEventListener('change', () => {
            const mode = String(byId('futures-risk-mode')?.value || 'MANUAL').toUpperCase();
            const currentUser = byId('futures-risk-user-label')?.textContent?.trim();
            renderProfile({
                futures_risk_mode: mode,
                futures_margin_policy: byId('futures-margin-policy')?.value || 'FIXED_USDT',
                futures_equity_usdt: nullableNumber('futures-risk-equity'),
                futures_max_allocation_pct: nullableNumber('futures-risk-allocation'),
                futures_max_loss_pct_equity_per_trade: nullableNumber('futures-risk-max-loss'),
                futures_preferred_margin_usdt: nullableNumber('futures-risk-preferred-margin'),
                futures_personal_max_leverage: nullableNumber('futures-risk-max-leverage'),
            }, currentUser && currentUser !== '—' ? currentUser : null);
        });
        window.setTimeout(() => window.loadFuturesRiskProfile({silent: true}), 2200);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind, {once: true});
    } else {
        bind();
    }
})();
