// =============================================================================
// shared.js — Utilitarias compartidas, configuración y estado global
// =============================================================================

'use strict';

// =============================================================================
// 1. COMPONENTE: CustomSelect
// =============================================================================

class CustomSelect {
    constructor(el, options = {}) {
        if (!el || el.tagName !== 'SELECT') return;
        this.select = el;
        this.options = options;
        this._build();
        this._bind();
    }

    get value() { return this._hiddenInput.value; }
    set value(val) { this._setValue(val); }

    _build() {
        this.select.style.display = 'none';

        this.wrapper = document.createElement('div');
        this.wrapper.className = 'custom-select';

        this.trigger = document.createElement('button');
        this.trigger.type = 'button';
        this.trigger.className = 'custom-select-trigger';
        this.trigger.setAttribute('aria-haspopup', 'listbox');
        this.trigger.setAttribute('aria-expanded', 'false');
        if (this.select.disabled) this.trigger.disabled = true;

        this.valueEl = document.createElement('span');
        this.valueEl.className = 'custom-select-value';

        this.arrowEl = document.createElement('i');
        this.arrowEl.className = 'fa-solid fa-chevron-down custom-select-arrow';

        this.trigger.appendChild(this.valueEl);
        this.trigger.appendChild(this.arrowEl);

        this.menu = document.createElement('div');
        this.menu.className = 'custom-select-menu';
        this.menu.setAttribute('role', 'listbox');

        this._hiddenInput = document.createElement('input');
        this._hiddenInput.type = 'hidden';
        this._hiddenInput.name = this.select.name || '';
        this.select.removeAttribute('name');

        this._items = [];
        this._populateItems();

        const parent = this.select.parentNode;
        parent.insertBefore(this.wrapper, this.select);
        this.wrapper.appendChild(this.trigger);
        this.wrapper.appendChild(this.menu);
        this.wrapper.appendChild(this._hiddenInput);
    }

    _populateItems() {
        this.menu.innerHTML = '';
        this._items = [];
        Array.from(this.select.options).forEach((opt, i) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'custom-select-item';
            item.setAttribute('data-select-item', ''); // Atributo desacoplado para JS
            item.textContent = opt.text;
            item.dataset.value = opt.value;
            item.dataset.index = i;
            item.setAttribute('role', 'option');
            if (opt.selected) {
                item.classList.add('selected');
                this.valueEl.textContent = opt.text;
                this._hiddenInput.value = opt.value;
            }
            if (opt.disabled) item.disabled = true;
            this.menu.appendChild(item);
            this._items.push(item);
        });
    }

    _bind() {
        this.trigger.addEventListener('click', (e) => {
            if (this.select.disabled) return;
            e.stopPropagation();
            this.toggle();
        });

        // Delegación de eventos en el menú — cubre también elementos repoblados dinámicamente
        this.menu.addEventListener('click', (e) => {
            const item = e.target.closest('[data-select-item], .custom-select-item');
            if (!item || item.disabled) return;
            e.stopPropagation();
            this._selectItem(item);
            this.select.dispatchEvent(new Event('change', { bubbles: true }));
            this.close();
        });
    }

    _selectItem(item) {
        this._items.forEach(el => el.classList.remove('selected'));
        item.classList.add('selected');
        this.valueEl.textContent = item.textContent;
        this._hiddenInput.value = item.dataset.value;
        this.select.value = item.dataset.value;
        if (this.options.onChange) this.options.onChange(item.dataset.value, item.textContent);
    }

    _setValue(val) {
        const item = this._items.find(el => el.dataset.value === String(val));
        if (item) this._selectItem(item);
    }

    open() {
        if (this.menu.classList.contains('open')) return;
        this.menu.classList.add('open');
        this.trigger.classList.add('open');
        this.trigger.setAttribute('aria-expanded', 'true');
        const selected = this._items.find(el => el.classList.contains('selected'));
        if (selected) { selected.scrollIntoView({ block: 'nearest' }); selected.focus(); }
    }

    close() {
        this.menu.classList.remove('open');
        this.trigger.classList.remove('open');
        this.trigger.setAttribute('aria-expanded', 'false');
    }

    toggle() {
        this.menu.classList.contains('open') ? this.close() : this.open();
    }

    updateOptions(options) {
        this.select.innerHTML = '';
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.value;
            o.text = opt.text;
            if (opt.selected) o.selected = true;
            this.select.appendChild(o);
        });
        this._populateItems();
    }

    static init(selector = '[data-custom-select], .custom-select-init') {
        document.querySelectorAll(selector).forEach(el => {
            if (!el._customSelect) el._customSelect = new CustomSelect(el);
        });
    }
}

// Inicializador global para CustomSelect
document.addEventListener('DOMContentLoaded', () => CustomSelect.init());


// =============================================================================
// 2. UTILIDADES GLOBALES: initFormState
// =============================================================================

function initFormState(form, isEditing) {
    if (!form) return;
    const submitBtn = form.querySelector('button[type=submit]');
    if (!submitBtn) return;

    submitBtn.disabled = true;

    const initialValues = {};
    form.querySelectorAll('input[name], select[name]').forEach(el => {
        initialValues[el.name] = el.value;
    });

    const setBtn = (disabled) => { submitBtn.disabled = disabled; };

    const checkState = () => {
        const hasErrors = form.querySelectorAll('[aria-invalid="true"], .input-error-state').length > 0;
        let shouldEnable;
        if (isEditing) {
            const hasChanges = Array.from(form.querySelectorAll('input[name], select[name]'))
                .some(el => el.value !== (initialValues[el.name] || ''));
            shouldEnable = hasChanges && !hasErrors;
        } else {
            const allFilled = Array.from(form.querySelectorAll('input[required], select[required]'))
                .every(el => el.value.trim() !== '');
            shouldEnable = allFilled && !hasErrors;
        }
        setBtn(!shouldEnable);
    };

    setTimeout(checkState, 0);

    // Delegación de eventos en el contenedor padre (form) para evitar N listeners
    form.addEventListener('input', () => setTimeout(checkState, 0));
    form.addEventListener('change', () => setTimeout(checkState, 0));
    form.addEventListener('focusout', () => setTimeout(checkState, 0)); // focusout burbujea a diferencia de blur

    return checkState;
}


// =============================================================================
// 3. UTILIDADES GLOBALES: Modal, Toast, csrfFetch, Dropdowns
// =============================================================================

function showCustomModal({ title, message, type = 'info', showCancel = false }) {
    return new Promise((resolve) => {
        const ICON_MAP = {
            success: '<i class="fa-solid fa-circle-check custom-modal-icon custom-modal-icon-success"></i>',
            error: '<i class="fa-solid fa-circle-xmark custom-modal-icon custom-modal-icon-error"></i>',
        };
        const iconHtml = ICON_MAP[type] || '<i class="fa-solid fa-triangle-exclamation custom-modal-icon custom-modal-icon-warn"></i>';

        const backdrop = document.createElement('div');
        backdrop.className = 'custom-modal-backdrop';

        const container = document.createElement('div');
        container.className = 'custom-modal-container';
        container.innerHTML = `
                <div class="custom-modal-header">
                    ${iconHtml}
                    <span class="custom-modal-title">${title}</span>
                </div>
                <div class="custom-modal-body">${message}</div>
                <div class="custom-modal-actions">
                    ${showCancel ? '<button id="customModalCancelBtn" class="btn btn-secondary">Cancelar</button>' : ''}
                    <button id="customModalConfirmBtn" class="btn btn-primary">Aceptar</button>
                </div>
            `;

        backdrop.appendChild(container);
        document.body.appendChild(backdrop);
        setTimeout(() => backdrop.classList.add('active'), 10);

        const cleanUp = (value) => {
            backdrop.classList.remove('active');
            setTimeout(() => { backdrop.remove(); resolve(value); }, 150);
        };

        container.querySelector('#customModalConfirmBtn').addEventListener('click', () => cleanUp(true));
        if (showCancel) {
            container.querySelector('#customModalCancelBtn').addEventListener('click', () => cleanUp(false));
        }
    });
}

const showAlert = (message, type = 'info') => {
    const TITLE_MAP = { error: 'Error', success: 'Éxito', warn: 'Advertencia', warning: 'Advertencia' };
    return showCustomModal({ title: TITLE_MAP[type] || 'Notificación', message, type, showCancel: false });
};

const showConfirm = (message) =>
    showCustomModal({ title: 'Confirmar', message, type: 'confirm', showCancel: true });

// Toast: un único listener delegado para todos los botones de cierre del Toast
document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-toast-close], .toast-item .btn-icon');
    if (!btn) return;
    const toast = btn.closest('[data-toast], .toast-item');
    if (!toast) return;
    toast.style.transform = 'translateX(120%)';
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 350);
});

const showToast = (message, type = 'info') => {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const hasClose = type !== 'success';
    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type}${hasClose ? ' has-close' : ''}`;
    toast.setAttribute('data-toast', '');
    toast.innerHTML = `
            ${hasClose ? '<button type="button" class="btn btn-icon toast-close" data-toast-close><i class="fa-solid fa-xmark"></i></button>' : ''}
            <div class="toast-body-content">${message}</div>
        `;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.style.transform = 'translateX(0)'; toast.style.opacity = '1'; });
    setTimeout(() => {
        toast.style.transform = 'translateX(120%)';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 350);
    }, 5000);
};

// --- CSRF Fetch ---
function getCookie(name) {
    const found = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(`${name}=`));
    return found ? decodeURIComponent(found.slice(name.length + 1)) : null;
}

function csrfFetch(url, opts = {}) {
    let token = getCookie('csrftoken');
    if (!token && window.CSRF_TOKEN) token = window.CSRF_TOKEN;
    const headers = { 'X-CSRFToken': token, ...opts.headers };
    if (opts.body && !headers['Content-Type'] && !headers['content-type']) {
        headers['Content-Type'] = 'application/json';
    }
    opts.headers = headers;
    opts.credentials = 'same-origin';
    return fetch(url, opts);
}

// --- Dropdowns: delegación de eventos unificada ---
const closeAllDropdowns = () => {
    document.querySelectorAll('[data-dropdown-menu].open, .dropdown-menu.open').forEach(menu => {
        menu.classList.remove('open');
        const trigger = menu.previousElementSibling;
        if (trigger) trigger.classList.remove('open');
        menu.style.position = '';
        menu.style.top = '';
        menu.style.left = '';
        menu.style.right = '';
        menu.style.bottom = '';
    });
};

const initDropdowns = () => {
    document.addEventListener('click', (e) => {
        const trigger = e.target.closest('[data-dropdown-trigger], .actions-dropdown .btn-icon');
        if (trigger) {
            if (trigger.disabled) return;
            e.stopPropagation();
            const menu = trigger.nextElementSibling;
            if (!menu) return;
            const isOpen = menu.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) {
                menu.classList.add('open');
                trigger.classList.add('open');
                if (trigger.closest('.table-wrapper')) {
                    const rect = trigger.getBoundingClientRect();
                    const menuWidth = menu.offsetWidth || 180;
                    let left = rect.right - menuWidth;
                    if (left < 8) left = 8;
                    menu.style.position = 'fixed';
                    menu.style.top = (rect.bottom + 4) + 'px';
                    menu.style.left = left + 'px';
                    menu.style.right = 'auto';
                    menu.style.bottom = 'auto';
                }
            }
        } else {
            closeAllDropdowns();
        }
    });
    document.addEventListener('scroll', closeAllDropdowns, { passive: true });
};

// Delegación de eventos para confirmaciones de borrado
const initConfirmDelete = () => {
    document.addEventListener('click', (e) => {
        const link = e.target.closest('[data-confirm-delete], .js-btn-confirm-delete');
        if (!link) return;
        e.preventDefault();
        showCustomModal({
            title: 'Confirmar',
            message: link.getAttribute('data-confirm'),
            type: 'confirm',
            showCancel: true,
        }).then(confirmed => {
            if (!confirmed) return;
            if (link.tagName === 'FORM') {
                link.submit();
            } else {
                window.location.href = link.getAttribute('href');
            }
        });
    });
};

// Delegación para auto-envío de formularios
function initAutoSubmit() {
    document.addEventListener('change', (e) => {
        const el = e.target.closest('[data-auto-submit], .js-auto-submit');
        if (el && el.form) {
            el.form.submit();
        }
    });
}

// SSE en vivo para actualizar badge del sidebar
function initLiveBadge() {
    var sidebarBadge = document.getElementById('historyBadgeSidebar');
    if (!sidebarBadge) return;

    var isHistoryPage = !!document.getElementById('live-history-list');
    var newEventsBtn = isHistoryPage ? document.getElementById('newEventsBtn') : null;
    var SSE_URL = '/history/api/sse/count/';
    var lastCount = parseInt(sidebarBadge.textContent, 10) || 0;
    var sseSource = null;
    var pollInterval = null;

    // Botón "Recargar eventos" recarga la página
    if (newEventsBtn) {
        newEventsBtn.addEventListener('click', function () {
            location.reload();
        });
    }

    function applyCount(count) {
        // Actualizar sidebar badge
        if (count > 0) {
            sidebarBadge.textContent = count;
            sidebarBadge.classList.add('visible');
        } else {
            sidebarBadge.textContent = '';
            sidebarBadge.classList.remove('visible');
        }

        // Pulse cuando sube el conteo
        if (lastCount >= 0 && count > lastCount && count > 0) {
            sidebarBadge.classList.remove('badge-pulse');
            void sidebarBadge.offsetWidth;
            sidebarBadge.classList.add('badge-pulse');
            setTimeout(function () { sidebarBadge.classList.remove('badge-pulse'); }, 2000);

            // Habilitar botón de nuevos eventos y filtro en history page
            if (newEventsBtn) {
                newEventsBtn.disabled = false;
            }
            var filterBtn = document.getElementById('openFilterPanel');
            if (filterBtn) filterBtn.disabled = false;
        }

        lastCount = count;
    }

    async function pollCount() {
        try {
            var resp = await fetch('/history/api/count/', { credentials: 'same-origin' });
            if (!resp.ok) return;
            var data = await resp.json();
            applyCount(data.count || 0);
        } catch (_) { }
    }

    if (typeof EventSource !== 'undefined') {
        sseSource = new EventSource(SSE_URL);
        sseSource.addEventListener('count-update', function (e) {
            try {
                var data = JSON.parse(e.data);
                applyCount(data.count || 0);
            } catch (_) { }
        });
        sseSource.onerror = function () {
            if (!pollInterval) {
                pollInterval = setInterval(pollCount, 5000);
            }
        };
        sseSource.onopen = function () {
            if (pollInterval) {
                clearInterval(pollInterval);
                pollInterval = null;
            }
        };
        window.addEventListener('beforeunload', function () {
            if (sseSource) sseSource.close();
        });
    } else {
        pollCount();
        pollInterval = setInterval(pollCount, 5000);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initDropdowns();
    initConfirmDelete();
    initAutoSubmit();
});


// =============================================================================
// 4. CONFIGURACIÓN DEL MÓDULO DE MONITOREO
// =============================================================================

const API = {
    thresholdsUpdate: '/api/thresholds/update/',
    limitsUpdate: '/api/sensor-limits/update/',
    clearHistory: '/history/clear/',
    resolveAlert: (id) => `/history/${id}/resolve/`,
    simStatus: (id) => `/api/sim/${id}/status/`,
    simPause: (id) => `/api/sim/${id}/pause/`,
    simReset: (id) => `/api/sim/${id}/reset/`,
    simInjectFault: (id) => `/api/sim/${id}/inject-fault/`,
    simClearFault: (id) => `/api/sim/${id}/clear-fault/`,
    simSetSpeed: (id) => `/api/sim/${id}/set-speed/`,
    simTogglePump: (id) => `/api/sim/${id}/toggle-pump/`,
    simToggleElevator: (id) => `/api/sim/${id}/toggle-elevator/`,
    status: (id) => id ? `/api/status/?edificio_id=${id}` : '/api/status/',
    thresholds: (id) => `/api/thresholds/?edificio_id=${id}`,
    sensorLimits: (id) => `/api/sensor-limits/?edificio_id=${id}`,
};

const _CONFIG = (() => {
    const el = document.getElementById('appConfig');
    return el ? JSON.parse(el.textContent) : {};
})();

const IS_ADMIN = window.IS_ADMIN === true;
const _VAR_NAMES = _CONFIG.var_names || {};
const _UNITS = _CONFIG.units || {};
const _BOMBA_VARS = _CONFIG.pump_vars || [];
const _ELEVADOR_VARS = _CONFIG.elevator_vars || [];
const _RISK = _CONFIG.risk_labels || {};
const _LIMITS_EXCLUDE_VARS = _CONFIG.limits_exclude_vars || [];
const _ENUM_VARS = _CONFIG.enum_vars || [];
const _VALUE_DISPLAY = _CONFIG.value_display_es || {};
let _SENSOR_RANGES = _CONFIG.sensor_ranges || {};

let _currentFaults = {};
const _FAULT_FORCED_RISK = {
    "door_blocked|elev_door_status": true,
    "pos_sensor_fail|elev_door_status": true,
};

const CHART_PUMP_VARS = _BOMBA_VARS.filter(v => v !== 'pump_tank_level');
const CHART_ELEV_VARS = _ELEVADOR_VARS.filter(
    v => v !== 'elev_position' && v !== 'elev_door_status'
);

let EDIFICIO_ID = _CONFIG.edificio_id || window.SELECTED_EDIFICIO_ID || 0;
let SSE_URL = EDIFICIO_ID ? `/sse/${EDIFICIO_ID}/` : null;

// --- Estado mutable del módulo (encapsulado en IIFE) ---
let sseSource = null;
let monitorConnectionTimeout = null;
let currentThresholds = {};
let _originalThresholds = {};
let _dirtySensorKeys = new Set();
let _limitsDirtyKeys = new Set();
let _unsavedGuardDisabled = false;
let currentReadings = {};
window.clearCurrentReadings = function () { currentReadings = {}; };
let currentPumpOn = false;
let currentElevOn = false;
let _elevTargetFloor = 0;
let _pumpDemand = 15.0;
let _faultInjectedAt = {};
let chart1, chart2;
let unreadHistoryCount = 0;
let _originalLimits = {};
function _hasUnsavedChanges() {
    return _dirtySensorKeys.size > 0 || _limitsDirtyKeys.size > 0;
}


// =============================================================================
// 5. FUNCIONES UTILITARIAS / LÓGICA DE NEGOCIO
// =============================================================================

const _htmlEscapeDiv = document.createElement('div');
const safeText = (value) => {
    if (value === null || value === undefined) return '-';
    _htmlEscapeDiv.textContent = String(value);
    return _htmlEscapeDiv.innerHTML;
};

function formatNumeric(value, variable) {
    if (typeof value !== 'number') return safeText(value);
    if (variable === 'elev_load') return Math.round(value).toString();
    return value.toFixed(2);
}

const getVariableName = (variable) =>
    _VAR_NAMES[variable] || variable.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

const getUnit = (variable) => _UNITS[variable] || '';

function translateSensorValue(variable, value) {
    if (variable === 'elev_position') {
        const floor = Math.round(Number(value));
        const posRange = _SENSOR_RANGES['elev_position'];
        const maxFloor = posRange ? posRange[1] : null;
        if (floor === 0) return 'PB';
        if (maxFloor !== null && floor === maxFloor) return 'PH';
        return `Piso ${floor}`;
    }
    if (_VALUE_DISPLAY[variable]) {
        const tr = _VALUE_DISPLAY[variable][String(value)];
        if (tr !== undefined) return tr;
    }
    if (typeof value === 'boolean') return value ? 'Sí' : 'No';
    return null;
}

function getRiskClass(varName, value) {
    for (const faultType of Object.values(_currentFaults)) {
        if (_FAULT_FORCED_RISK[`${faultType}|${varName}`]) {
            return { badge: 'badge-crit', label: _RISK.critico };
        }
    }
    if (_ENUM_VARS.includes(varName)) {
        return { badge: 'badge-normal', label: _RISK.normal };
    }

    const cfg = currentThresholds[varName];
    if (!cfg) return { badge: 'badge-normal', label: _RISK.normal };

    const numVal = Number(value);

    if (cfg.direction === 'range') {
        // cfg.high   = límite INFERIOR del rango normal (ej: 210 V, 20% tank)
        // cfg.critic = límite SUPERIOR del rango normal (ej: 230 V, 85% tank)
        // cfg.crit_low / cfg.crit_high = límites críticos externos
        const lo = cfg.high;
        const hi = cfg.critic;
        const critLo = cfg.crit_low;
        const critHi = cfg.crit_high;
        if (critLo !== undefined && numVal < critLo) return { badge: 'badge-crit', label: _RISK.critico };
        if (critHi !== undefined && numVal > critHi) return { badge: 'badge-crit', label: _RISK.critico };
        if (numVal >= lo && numVal <= hi) return { badge: 'badge-normal', label: _RISK.normal };
        return { badge: 'badge-high', label: _RISK.alto };
    }

    // direction === 'higher': cfg.high = umbral Normal→Alto, cfg.critic = umbral Alto→Crítico
    if (numVal > cfg.critic) return { badge: 'badge-crit', label: _RISK.critico };
    if (numVal > cfg.high) return { badge: 'badge-high', label: _RISK.alto };
    return { badge: 'badge-normal', label: _RISK.normal };
}

const getCSSVar = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '';


// =============================================================================
// 6. UI state functions
// =============================================================================

const STATE_IDS = ['stateLoading', 'stateOffline', 'stateNoEquipment', 'stateNoBuildings'];

function showState(stateId) {
    STATE_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = id === stateId ? '' : 'none';
    });
    const card = document.getElementById('stateCard');
    if (card) card.style.display = 'block';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'none';
}

function hideAllStates() {
    STATE_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const card = document.getElementById('stateCard');
    if (card) card.style.display = 'none';
    const active = document.getElementById('activeMonitoring');
    if (active) active.style.display = 'block';
}

function renderConnectionStatus(isConnected) {
    if (monitorConnectionTimeout) { clearTimeout(monitorConnectionTimeout); monitorConnectionTimeout = null; }
    if (isConnected) hideAllStates();
    else showState('stateOffline');
}

function updateEquipmentVisibility(equipTypes) {
    const et = equipTypes || [];
    const hasPump = et.includes('bomba');
    const hasElev = et.includes('elevador');

    if (!hasPump && !hasElev && EDIFICIO_ID) { showState('stateNoEquipment'); return false; }

    const toggle = (ids, show) =>
        ids.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = show ? '' : 'none'; });

    toggle(['bombaSection', 'chartPumpPanel', 'statsBombaPanel'], hasPump);
    toggle(['elevadorSection', 'chartElevatorPanel', 'statsElevadorPanel'], hasElev);
    return true;
}

const _csSelect = (el) => el?._customSelect ?? null;
const _csSetValue = (el, val) => { const cs = _csSelect(el); if (cs) cs.value = String(val); else if (el) el.value = val; };
const _csSetDisabled = (el, disabled) => { const cs = _csSelect(el); if (cs?.trigger) cs.trigger.disabled = disabled; if (el) el.disabled = disabled; };
const _csSyncOptions = (el) => { const cs = _csSelect(el); if (cs) cs.updateOptions(Array.from(el.options).map(o => ({ value: o.value, text: o.text }))); };

window._csSetValue = _csSetValue;
window._csSetDisabled = _csSetDisabled;
window.getVariableName = getVariableName;
window.getUnit = getUnit;
window.getRiskClass = getRiskClass;
window.setEquipmentState = (pumpOn, elevOn) => {
    currentPumpOn = pumpOn;
    currentElevOn = elevOn;
    if (typeof updateEquipmentPowerBtns === 'function') {
        updateEquipmentPowerBtns(pumpOn, elevOn);
    }
};
Object.defineProperty(window, '_SENSOR_RANGES', { get: function () { return _SENSOR_RANGES; }, configurable: true });

function setHistoryBadge(count) {
    var badge = document.getElementById('historyBadgeSidebar');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = count;
        badge.classList.add('visible');
    } else {
        badge.textContent = '';
        badge.classList.remove('visible');
    }
    var btn = document.getElementById('newEventsBtn');
    if (btn) btn.disabled = count <= 0;
}


// =============================================================================
// setupBuildingSelector
// =============================================================================

function setupBuildingSelector() {
    const sel = document.getElementById('buildingSelect');
    if (!sel) return;
    sel.addEventListener('change', async function () {
        const newId = parseInt(this.value);
        if (!newId || newId === EDIFICIO_ID) return;
        if (_hasUnsavedChanges()) {
            const confirmed = await showConfirm('Tienes cambios sin guardar. ¿Cambiar de edificio?');
            if (!confirmed) {
                this.value = EDIFICIO_ID;
                return;
            }
        }
        _unsavedGuardDisabled = true;
        window.location.href = `?edificio_id=${newId}`;
    });
}

function setupUnsavedChangesGuard() {
    const sidebar = document.querySelector('[data-sidebar], .sidebar');
    if (sidebar) {
        sidebar.addEventListener('click', (e) => {
            const link = e.target.closest('[data-sidebar-link], a.sidebar-link');
            if (!link || !_hasUnsavedChanges()) return;
            const href = link.getAttribute('href');
            if (!href || href === '#') return;
            e.preventDefault();
            showConfirm('Tienes cambios sin guardar. ¿Salir de la página?')
                .then(confirmed => {
                    if (confirmed) {
                        _unsavedGuardDisabled = true;
                        window.location.href = href;
                    }
                });
        });
    }
}


// =============================================================================
// 13. PREVENCIÓN DE FUGAS DE MEMORIA Y CICLO DE VIDA
// =============================================================================

const cleanUpResources = () => {
    if (sseSource) {
        sseSource.close();
        sseSource = null;
    }
    if (monitorConnectionTimeout) {
        clearTimeout(monitorConnectionTimeout);
        monitorConnectionTimeout = null;
    }
};

// Liberar memoria al ocultar/descargar la página
window.addEventListener('pagehide', cleanUpResources);

window.addEventListener('beforeunload', (e) => {
    if (_unsavedGuardDisabled) {
        cleanUpResources();
        return;
    }
    if (_hasUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = '';
    } else {
        cleanUpResources();
    }
});

// Cierre único delegando clicks fuera de los selectores customizados
document.addEventListener('click', (e) => {
    document.querySelectorAll('.custom-select-menu.open').forEach(menu => {
        const wrapper = menu.closest('.custom-select');
        if (wrapper && !wrapper.contains(e.target)) {
            const selectEl = wrapper.nextElementSibling;
            const cs = selectEl?._customSelect;
            if (cs) cs.close();
        }
    });
});

// Teclado único delegando en el CustomSelect actualmente abierto
document.addEventListener('keydown', (e) => {
    const openMenu = document.querySelector('.custom-select-menu.open');
    if (!openMenu) return;
    const selectEl = openMenu.closest('.custom-select')?.nextElementSibling;
    const cs = selectEl?._customSelect;
    if (!cs) return;

    const currentIndex = cs._items.findIndex(el => el.classList.contains('selected'));
    let newIndex = currentIndex;

    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            newIndex = Math.min(currentIndex + 1, cs._items.length - 1);
            while (newIndex < cs._items.length - 1 && cs._items[newIndex].disabled) newIndex++;
            break;
        case 'ArrowUp':
            e.preventDefault();
            newIndex = Math.max(currentIndex - 1, 0);
            while (newIndex > 0 && cs._items[newIndex].disabled) newIndex--;
            break;
        case 'Enter':
            e.preventDefault();
            if (currentIndex >= 0 && !cs._items[currentIndex].disabled) {
                cs._selectItem(cs._items[currentIndex]);
                cs.select.dispatchEvent(new Event('change', { bubbles: true }));
                cs.close();
            }
            return;
        case 'Escape':
            e.preventDefault();
            cs.close();
            return;
        default:
            return;
    }

    if (newIndex !== currentIndex && cs._items[newIndex]) {
        cs._items[newIndex].focus();
        cs._items.forEach(el => el.classList.remove('selected'));
        cs._items[newIndex].classList.add('selected');
        cs.valueEl.textContent = cs._items[newIndex].textContent;
        cs._hiddenInput.value = cs._items[newIndex].dataset.value;
        cs._items[newIndex].scrollIntoView({ block: 'nearest' });
    }
});


// =============================================================================
// 16. EXPOSICIÓN DE APIs PÚBLICAS
// =============================================================================

window.CustomSelect = CustomSelect;
window.initFormState = initFormState;
window.showCustomModal = showCustomModal;
window.showAlert = showAlert;
window.showConfirm = showConfirm;
window.showToast = showToast;
window.csrfFetch = csrfFetch;
window.closeAllDropdowns = closeAllDropdowns;
window.initDropdowns = initDropdowns;
window.initConfirmDelete = initConfirmDelete;

// Config y estado global (accesible por limits.js, thresholds.js, monitoring.js, script.js)
window._CONFIG = _CONFIG;
window._DIRTY_SENSOR_KEYS = _dirtySensorKeys;
window._LIMITS_DIRTY_KEYS = _limitsDirtyKeys;
window.showState = showState;
window.hideAllStates = hideAllStates;
window.initLiveBadge = initLiveBadge;
