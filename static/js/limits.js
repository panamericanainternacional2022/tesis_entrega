// =============================================================================
// limits.js — Lógica específica de la página de límites de sensores
// =============================================================================

(function (window, document) {
    'use strict';

    // References globals from shared.js: EDIFICIO_ID, API, _SENSOR_RANGES,
    // _BOMBA_VARS, _ELEVADOR_VARS, _LIMITS_EXCLUDE_VARS,
    // currentThresholds, _originalLimits, _limitsDirtyKeys

    function renderLimitsPanel(ranges) {
        const bombaVars = _BOMBA_VARS.filter(k => ranges[k] && !_LIMITS_EXCLUDE_VARS.includes(k));
        const elevadorVars = _ELEVADOR_VARS.filter(k => ranges[k] && !_LIMITS_EXCLUDE_VARS.includes(k));

        function buildLimitCard(k, r) {
            const div = document.createElement('div');
            div.className = 'thresh-card';
            const name = getVariableName(k);
            const unit = getUnit(k);
            const defaultMin = r[0];
            const maxBound = r[1];
            const hardCap = (window._SENSOR_ABSOLUTE_RANGES && window._SENSOR_ABSOLUTE_RANGES[k]) ? window._SENSOR_ABSOLUTE_RANGES[k][1] : 999999.0;
            const maxVal = r[1];
            const thresh = currentThresholds[k];
            let refText = '';
            if (thresh) {
                const isLower = thresh.direction === 'lower';
                const maxThresh = isLower ? thresh.high : thresh.critic;
                if (maxThresh !== undefined) {
                    const label = isLower ? 'Alto' : (thresh.direction === 'range' ? 'Lím. crítico sup.' : 'Crítico');
                    refText = `${label}: ${maxThresh}${unit ? ' ' + unit : ''}`;
                }
            }
            const headerHtml = `<div class="thresh-card-header">
                <span class="thresh-label">${name}${unit ? ` (${unit})` : ''}</span>
                ${refText ? `<span class="thresh-hint">${refText}</span>` : ''}
            </div>`;
            div.innerHTML = headerHtml + `
                <div class="thresh-grid-2">
                    <div class="form-group">
                        <label class="form-label">Límite mínimo</label>
                        <input type="number" step="any" value="${r[0]}" class="form-input" disabled>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Límite máximo</label>
                        <input type="number" step="any" min="${(defaultMin + 0.01).toFixed(2)}" max="${hardCap}" data-var="${k}" data-level="max" value="${maxVal}" class="form-input">
                    </div>
                </div>
                <div class="error-msg"></div>`;
            return div;
        }

        function buildLimitSection(containerId, vars) {
            const panel = document.getElementById(containerId);
            if (!panel) return;
            const section = panel.closest('section');
            if (vars.length === 0) {
                if (section) section.style.display = 'none';
                panel.innerHTML = '';
                return;
            }
            if (section) section.style.display = '';
            panel.innerHTML = '';
            vars.forEach(k => panel.appendChild(buildLimitCard(k, ranges[k])));
        }

        buildLimitSection('limitsBombaPanel', bombaVars);
        buildLimitSection('limitsElevadorPanel', elevadorVars);
        _originalLimits = JSON.parse(JSON.stringify(ranges));
        _limitsDirtyKeys.clear();
        updateLimitsDirtyBadge();
        validateLimitInputs('bomba');
        validateLimitInputs('elevador');
    }

    function validateLimitInputs(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
        const btn = document.getElementById(bomba ? 'saveLimitsBombaBtn' : 'saveLimitsElevadorBtn');
        let hasError = false, hasChanges = false;

        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const v = inp.dataset.var;
                if (!v) return;
                const val = parseFloat(inp.value);
                inp.classList.remove('input-error-state');
                inp.removeAttribute('aria-invalid');
                const errorMsgEl = inp.closest('.thresh-card')?.querySelector('.error-msg');
                if (errorMsgEl) { errorMsgEl.textContent = ''; errorMsgEl.style.visibility = 'hidden'; }

                const showError = (text) => {
                    hasError = true;
                    inp.classList.add('input-error-state');
                    inp.setAttribute('aria-invalid', 'true');
                    if (errorMsgEl) { errorMsgEl.textContent = text; errorMsgEl.style.visibility = 'visible'; }
                };

                if (isNaN(val)) return showError('Introduzca un número válido.');
                const defaultMin = _originalLimits[v]?.[0];
                if (defaultMin === undefined) return showError('Variable sin rango configurado.');
                if (val <= defaultMin) return showError(`Debe ser mayor que el mínimo (${defaultMin}).`);
                const absMax = (window._SENSOR_ABSOLUTE_RANGES && window._SENSOR_ABSOLUTE_RANGES[v]) ? window._SENSOR_ABSOLUTE_RANGES[v][1] : 999999.0;
                if (val > absMax) return showError(`No puede exceder el límite físico (${absMax}).`);
                const thresh = currentThresholds[v];
                if (thresh) {
                    const isLower = thresh.direction === 'lower';
                    const maxThresh = isLower ? thresh.high : thresh.critic;
                    const maxThreshLabel = isLower ? 'alto' : (thresh.direction === 'range' ? 'crítico sup.' : 'crítico');
                    if (maxThresh !== undefined && val < maxThresh) {
                        const unitStr = getUnit(v) ? ` ${getUnit(v)}` : '';
                        return showError(`No puede ser menor al umbral ${maxThreshLabel} (${maxThresh}${unitStr}).`);
                    }
                }
                if (_originalLimits[v] && val !== _originalLimits[v][1]) hasChanges = true;
            });
        });

        if (btn) btn.disabled = hasError || !hasChanges;
        updateLimitsDirtyState(scope);
    }

    async function saveLimits(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
        const newLimits = { edificio_id: EDIFICIO_ID };
        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const varName = inp.dataset.var;
                if (varName) {
                    newLimits[varName] = parseFloat(inp.value);
                }
            });
        });
        try {
            const resp = await csrfFetch(API.limitsUpdate, { method: 'POST', body: JSON.stringify(newLimits) });
            const res = await resp.json();
            if (res.status === 'ok') {
                _SENSOR_RANGES = res.sensor_ranges;
                renderLimitsPanel(res.sensor_ranges);
            } else {
                showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
            }
        } catch (_) {
            showToast('Error de conexión. Inténtelo de nuevo.', 'error');
        }
    }

    function updateLimitsDirtyState(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
        const panelVars = bomba ? _BOMBA_VARS : _ELEVADOR_VARS;
        const panelKeys = new Set();
        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const varKey = inp.dataset.var;
                if (!varKey) return;
                const orig = _originalLimits[varKey]?.[1];
                const val = parseFloat(inp.value);
                if (orig !== undefined && val !== orig) {
                    inp.classList.add('is-dirty');
                    inp.title = `Valor original: ${orig}${getUnit(varKey) ? ' ' + getUnit(varKey) : ''}`;
                    panelKeys.add(varKey);
                } else {
                    inp.classList.remove('is-dirty');
                    inp.title = '';
                }
            });
        });
        for (const k of panelVars) {
            if (!_LIMITS_EXCLUDE_VARS.includes(k)) {
                if (panelKeys.has(k)) _limitsDirtyKeys.add(k);
                else _limitsDirtyKeys.delete(k);
            }
        }
        updateLimitsDirtyBadge();
    }

    function updateLimitsDirtyBadge() {
        const badge = document.getElementById('globalLimitsDirtyBadge');
        const divider = document.getElementById('globalLimitsDirtyDivider');
        const resetBtn = document.getElementById('resetAllLimitsBtn');
        const totalDirty = _limitsDirtyKeys.size;
        if (badge && divider) {
            if (!totalDirty) {
                badge.classList.add('d-none');
                divider.classList.add('d-none');
            } else {
                badge.classList.remove('d-none');
                divider.classList.remove('d-none');
                badge.textContent = `${totalDirty} sensor(es) modificado(s)`;
            }
        }
        if (resetBtn) resetBtn.disabled = !totalDirty;
    }

    function resetPanelLimits(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['limitsBombaPanel'] : ['limitsElevadorPanel'];
        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const varKey = inp.dataset.var;
                if (!varKey) return;
                const orig = _originalLimits[varKey]?.[1];
                if (orig !== undefined) inp.value = orig;
            });
        });
        validateLimitInputs(scope);
    }

    async function resetAllLimits() {
        if (!await showConfirm('¿Estás seguro de que deseas restablecer todos los límites a sus valores originales?')) return;
        resetPanelLimits('bomba');
        resetPanelLimits('elevador');
    }

    // Public init function called by the dispatcher
    window.AppLimitsInit = function initLimitsPage() {
        (async function() {
            try {
                hideAllStates();
                const resp = await fetch(API.thresholds(EDIFICIO_ID));
                if (resp.ok) {
                    const raw = await resp.json();
                    delete raw.status;
                    currentThresholds = raw;
                }
                renderLimitsPanel(_SENSOR_RANGES);
            } catch (_) { showState('stateOffline'); }
        })();
    };

    function _truncateNumberInput(inp) {
        var str = inp.value;
        var parts = str.split('.');
        if (parts[0] && parts[0].replace('-', '').length > 10) {
            inp.value = str.slice(0, -1);
            return true;
        }
        if (parts[1] && parts[1].length > 4) {
            inp.value = parts[0] + '.' + parts[1].slice(0, 4);
            return true;
        }
        return false;
    }

    // Admin event setup for limits
    window.AppLimitsSetupEvents = function setupLimitsAdminEvents() {
        const saveLimitsBombaBtn = document.getElementById('saveLimitsBombaBtn');
        const limitsBombaPanel = document.getElementById('limitsBombaPanel');
        const saveLimitsElevadorBtn = document.getElementById('saveLimitsElevadorBtn');
        const limitsElevadorPanel = document.getElementById('limitsElevadorPanel');
        if (saveLimitsBombaBtn) saveLimitsBombaBtn.addEventListener('click', () => saveLimits('bomba'));
        if (limitsBombaPanel) limitsBombaPanel.addEventListener('input', function (e) { _truncateNumberInput(e.target); validateLimitInputs('bomba'); });
        if (saveLimitsElevadorBtn) saveLimitsElevadorBtn.addEventListener('click', () => saveLimits('elevador'));
        if (limitsElevadorPanel) limitsElevadorPanel.addEventListener('input', function (e) { _truncateNumberInput(e.target); validateLimitInputs('elevador'); });
        const resetAllLimitsBtn = document.getElementById('resetAllLimitsBtn');
        if (resetAllLimitsBtn) resetAllLimitsBtn.addEventListener('click', resetAllLimits);
    };

})(window, document);
