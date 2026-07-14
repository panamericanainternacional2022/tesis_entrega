// =============================================================================
// thresholds.js — Lógica específica de la página de umbrales de sensores
// =============================================================================

(function (window, document) {
    'use strict';

    // References globals from shared.js: EDIFICIO_ID, API, _SENSOR_RANGES,
    // _BOMBA_VARS, _ELEVADOR_VARS, _RISK,
    // currentThresholds, _originalThresholds, _dirtySensorKeys

    function _validateThresholdRange(dir, high, critic) {
        if (isNaN(high) || isNaN(critic)) {
            const errs = [];
            if (isNaN(high)) errs.push('high');
            if (isNaN(critic)) errs.push('critic');
            return { valid: false, errorText: 'Introduzca valores numéricos válidos.', errorInputs: errs };
        }
        if (dir === 'range') {
            if (!(high < critic)) return { valid: false, errorText: 'El mínimo aceptable debe ser menor al máximo aceptable.', errorInputs: ['high', 'critic'] };
        } else if (dir === 'higher') {
            if (high >= critic) return { valid: false, errorText: 'Los valores deben estar ordenados: Alto < Crítico.', errorInputs: ['high', 'critic'] };
        } else if (dir === 'lower') {
            if (high <= critic) return { valid: false, errorText: 'Los valores deben estar ordenados: Alto > Crítico.', errorInputs: ['high', 'critic'] };
        }
        return { valid: true, errorText: '', errorInputs: [] };
    }

    function _validateThresholdBounds(dir, high, critic, bounds, unit) {
        const [minBound, maxBound] = bounds;
        const unitStr = unit ? ` ${unit}` : '';
        const outOfRange = (dir === 'lower')
            ? (high > maxBound && critic < minBound)
            : (high < minBound && critic > maxBound);

        if (outOfRange) return { valid: false, errorText: `Los umbrales deben estar dentro de los límites del sensor (${minBound} - ${maxBound}${unitStr}).`, errorInputs: ['high', 'critic'] };

        if (dir === 'lower') {
            if (high > maxBound) return { valid: false, errorText: `El umbral alto no puede ser mayor al límite.`, errorInputs: ['high'] };
            if (critic < minBound) return { valid: false, errorText: `El umbral crítico no puede ser menor al límite.`, errorInputs: ['critic'] };
        } else if (dir === 'higher') {
            if (high < minBound) return { valid: false, errorText: `El umbral alto no puede ser menor al límite.`, errorInputs: ['high'] };
            if (critic > maxBound) return { valid: false, errorText: `El umbral crítico no puede ser mayor al límite.`, errorInputs: ['critic'] };
        } else {
            if (high < minBound) return { valid: false, errorText: `El mínimo aceptable no puede ser menor al límite.`, errorInputs: ['high'] };
            if (critic > maxBound) return { valid: false, errorText: `El máximo aceptable no puede ser mayor al límite.`, errorInputs: ['critic'] };
        }
        return { valid: true, errorText: '', errorInputs: [] };
    }

    function renderThresholdsPanel(th) {
        const _THRESHOLDS_HIDDEN_VARS = ['elev_position'];
        const bombaVars = _BOMBA_VARS.filter(k => th[k] && !_THRESHOLDS_HIDDEN_VARS.includes(k));
        const elevadorVars = _ELEVADOR_VARS.filter(k => th[k] && !_THRESHOLDS_HIDDEN_VARS.includes(k));

        function buildCard(k, cfg) {
            const div = document.createElement('div');
            div.className = 'thresh-card';
            const name = getVariableName(k);
            const unit = getUnit(k);
            const bounds = _SENSOR_RANGES[k];
            const boundsText = bounds ? `Límite: ${bounds[0]} – ${bounds[1]}${unit ? ' ' + unit : ''}` : '';
            const headerHtml = `<div class="thresh-card-header">
                <span class="thresh-label">${name}${unit ? ` (${unit})` : ''}</span>
                ${boundsText ? `<span class="thresh-bounds-badge">${boundsText}</span>` : ''}
            </div>`;

            if (cfg.direction === 'range') {
                div.innerHTML = headerHtml + `
                    <div class="thresh-grid-2">
                        <div class="form-group"><label class="form-label">Mínimo aceptable</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                        <div class="form-group"><label class="form-label">Máximo aceptable</label><input type="number" step="any" data-var="${k}" data-level="critic" value="${cfg.critic}" class="form-input"></div>
                    </div>
                    <div class="error-msg"></div>
                    <input type="hidden" data-var="${k}" data-level="direction" value="range">`;
            } else {
                div.innerHTML = headerHtml + `
                    <div class="thresh-grid-2">
                        <div class="form-group"><label class="form-label">Alto</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                        <div class="form-group"><label class="form-label">Crítico</label><input type="number" step="any" data-var="${k}" data-level="critic" value="${cfg.critic}" class="form-input"></div>
                    </div>
                    <div class="error-msg"></div>
                    <input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">`;
            }
            return div;
        }

        function buildSection(containerId, vars) {
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
            vars.forEach(k => { const cfg = th[k]; if (cfg) panel.appendChild(buildCard(k, cfg)); });
        }

        buildSection('thresholdsBombaPanel', bombaVars);
        buildSection('thresholdsElevadorPanel', elevadorVars);

        _originalThresholds = JSON.parse(JSON.stringify(th));
        _dirtySensorKeys.clear();
        updateGlobalDirtyBadge();
        validateThresholdInputs('bomba');
        validateThresholdInputs('elevador');
    }

    function updateDirtyState(scope) {
        const bomba = scope === 'bomba';
        const panelId = bomba ? 'thresholdsBombaPanel' : 'thresholdsElevadorPanel';
        const panelVars = bomba ? _BOMBA_VARS : _ELEVADOR_VARS;
        const panel = document.getElementById(panelId);
        if (!panel) return;
        const panelKeys = new Set();
        panel.querySelectorAll('input[type="number"]').forEach(inp => {
            const varKey = inp.dataset.var;
            const lvl = inp.dataset.level;
            if (!varKey || !lvl || lvl === 'direction') return;
            const orig = _originalThresholds[varKey]?.[lvl];
            if (orig !== undefined && parseFloat(inp.value) !== orig) {
                inp.classList.add('is-dirty');
                inp.title = `Valor original: ${orig}${getUnit(varKey) ? ' ' + getUnit(varKey) : ''}`;
                panelKeys.add(varKey);
            } else {
                inp.classList.remove('is-dirty');
                inp.title = '';
            }
        });
        for (const k of panelVars) {
            if (panelKeys.has(k)) _dirtySensorKeys.add(k);
            else _dirtySensorKeys.delete(k);
        }
        updateGlobalDirtyBadge();
    }

    function updateGlobalDirtyBadge() {
        const badge = document.getElementById('globalDirtyBadge');
        const resetBtn = document.getElementById('resetAllThresholdsBtn');
        const saveAllBtn = document.getElementById('saveAllThresholdsBtn');
        const totalDirty = _dirtySensorKeys.size;
        if (badge) {
            if (!totalDirty) {
                badge.classList.add('d-none');
            } else {
                badge.classList.remove('d-none');
                badge.textContent = `${totalDirty} sensor(es) modificado(s)`;
            }
        }
        if (resetBtn) resetBtn.disabled = !totalDirty;
        if (saveAllBtn) saveAllBtn.disabled = totalDirty === 0;
    }

    function validateThresholdInputs(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
        const btn = document.getElementById(bomba ? 'saveThresholdsBombaBtn' : 'saveThresholdsElevadorBtn');
        let hasError = false, hasChanges = false;
        const processed = {};

        const findInp = (v, level) => {
            for (const pid of PANEL_IDS) {
                const el = document.getElementById(pid)?.querySelector(`input[data-var="${v}"][data-level="${level}"]`);
                if (el) return el;
            }
            return null;
        };

        const findErrorMsgEl = (v) => {
            for (const pid of PANEL_IDS) {
                const el = document.getElementById(pid)?.querySelector(`input[data-var="${v}"]`);
                if (el) return el.closest('.thresh-card')?.querySelector('.error-msg') ?? null;
            }
            return null;
        };

        const setInputColors = (inpKeys, inputMap, isErr) =>
            inpKeys.forEach(k => {
                if (inputMap[k]) {
                    inputMap[k].classList.toggle('input-error-state', isErr);
                    if (isErr) inputMap[k].setAttribute('aria-invalid', 'true');
                    else inputMap[k].removeAttribute('aria-invalid');
                }
            });

        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const v = inp.dataset.var;
                if (!v || processed[v]) return;
                processed[v] = true;

                const dirInp = findInp(v, 'direction');
                const highInp = findInp(v, 'high');
                const criticInp = findInp(v, 'critic');
                const inputMap = { high: highInp, critic: criticInp };

                setInputColors(['high', 'critic'], inputMap, false);

                const errorMsgEl = findErrorMsgEl(v);
                if (errorMsgEl) { errorMsgEl.textContent = ''; errorMsgEl.style.visibility = 'hidden'; }

                const dir = dirInp?.value;
                const high = parseFloat(highInp?.value);
                const critic = parseFloat(criticInp?.value);

                let result = _validateThresholdRange(dir, high, critic);
                if (result.valid && _SENSOR_RANGES[v]) {
                    result = _validateThresholdBounds(dir, high, critic, _SENSOR_RANGES[v], getUnit(v));
                }

                if (!result.valid) {
                    hasError = true;
                    setInputColors(result.errorInputs, inputMap, true);
                    if (errorMsgEl && result.errorText) { errorMsgEl.textContent = result.errorText; errorMsgEl.style.visibility = 'visible'; }
                }
            });
        });

        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const varKey = inp.dataset.var;
                const lvl = inp.dataset.level;
                if (!varKey || !lvl || lvl === 'direction') return;
                if (_originalThresholds[varKey]?.[lvl] !== undefined) {
                    if (parseFloat(inp.value) !== _originalThresholds[varKey][lvl]) hasChanges = true;
                }
            });
        });

        if (btn) btn.disabled = hasError || !hasChanges;
        updateDirtyState(scope);
    }

    async function saveThresholds(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
        const newTh = { edificio_id: EDIFICIO_ID };
        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const v = inp.dataset.var, l = inp.dataset.level;
                if (!v || !l) return;
                if (!newTh[v]) newTh[v] = { direction: panel.querySelector(`input[data-var="${v}"][data-level="direction"]`)?.value || 'higher' };
                newTh[v][l] = parseFloat(inp.value);
            });
        });
        try {
            const resp = await csrfFetch(API.thresholdsUpdate, { method: 'POST', body: JSON.stringify(newTh) });
            const res = await resp.json();
            if (res.status === 'ok') {
                currentThresholds = res.thresholds;
                renderThresholdsPanel(res.thresholds);
            } else {
                showToast(`Error al guardar: ${res.message || 'Inténtelo de nuevo.'}`, 'error');
            }
        } catch (_) {
            showToast('Error de conexión. Inténtelo de nuevo.', 'error');
        }
    }

    function resetPanelThresholds(scope) {
        const bomba = scope === 'bomba';
        const PANEL_IDS = bomba ? ['thresholdsBombaPanel'] : ['thresholdsElevadorPanel'];
        PANEL_IDS.forEach(panelId => {
            const panel = document.getElementById(panelId);
            if (!panel) return;
            panel.querySelectorAll('input[type="number"]').forEach(inp => {
                const varKey = inp.dataset.var;
                const lvl = inp.dataset.level;
                if (!varKey || !lvl || lvl === 'direction') return;
                const orig = _originalThresholds[varKey]?.[lvl];
                if (orig !== undefined) inp.value = orig;
            });
        });
        validateThresholdInputs(scope);
    }

    async function resetAllThresholds() {
        if (!await showConfirm('¿Restablecer todos los umbrales a sus valores originales (último guardado)?')) return;
        resetPanelThresholds('bomba');
        resetPanelThresholds('elevador');
    }

    // Public init function called by the dispatcher
    window.AppThresholdsInit = function initThresholdsPage() {
        (async function() {
            try {
                const resp = await fetch(API.thresholds(EDIFICIO_ID));
                if (!resp.ok) throw new Error(resp.statusText);
                const raw = await resp.json();
                delete raw.status;
                currentThresholds = raw;
                hideAllStates();
                renderThresholdsPanel(currentThresholds);
            } catch (_) { showState('stateOffline'); }
        })();
    };

    // Admin event setup for thresholds
    window.AppThresholdsSetupEvents = function setupThresholdsAdminEvents() {
        const saveThreshBombaBtn = document.getElementById('saveThresholdsBombaBtn');
        const threshBombaPanel = document.getElementById('thresholdsBombaPanel');
        const saveThreshElevadorBtn = document.getElementById('saveThresholdsElevadorBtn');
        const threshElevadorPanel = document.getElementById('thresholdsElevadorPanel');
        const resetAllBtn = document.getElementById('resetAllThresholdsBtn');
        if (saveThreshBombaBtn) saveThreshBombaBtn.addEventListener('click', () => saveThresholds('bomba'));
        if (threshBombaPanel) threshBombaPanel.addEventListener('input', () => validateThresholdInputs('bomba'));
        if (saveThreshElevadorBtn) saveThreshElevadorBtn.addEventListener('click', () => saveThresholds('elevador'));
        if (threshElevadorPanel) threshElevadorPanel.addEventListener('input', () => validateThresholdInputs('elevador'));
        if (resetAllBtn) resetAllBtn.addEventListener('click', resetAllThresholds);
    };

})(window, document);
