// =============================================================================
// APLICACIÓN: Monitoreo y Administración - Refactorización de Rendimiento
// =============================================================================

(function (window, document) {
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

    // Polling ligero para actualizar el badge de historial en el sidebar
    function initSidebarPolling() {
        const badgeEl = document.getElementById('historyBadgeSidebar');
        if (!badgeEl) return;

        // El dashboard tiene su propio SSE que ya actualiza el badge en tiempo real.
        const isDashboard = !!document.getElementById('activeMonitoring');
        if (isDashboard) return;

        const POLL_INTERVAL_MS = 30000;   // 30 segundos
        const COUNT_URL = '/history/api/count/';

        function applyCount(count) {
            if (count > 0) {
                badgeEl.textContent = count;
                badgeEl.classList.add('visible');
            } else {
                badgeEl.textContent = '';
                badgeEl.classList.remove('visible');
            }
        }

        async function pollCount() {
            try {
                const resp = await fetch(COUNT_URL, { credentials: 'same-origin' });
                if (!resp.ok) return;
                const data = await resp.json();
                applyCount(data.count || 0);
            } catch (_) { /* silent */ }
        }

        pollCount();
        setInterval(pollCount, POLL_INTERVAL_MS);
    }

    document.addEventListener('DOMContentLoaded', () => {
        initDropdowns();
        initConfirmDelete();
        initAutoSubmit();
        initSidebarPolling();
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
    const _NO_RISK_VARS = _CONFIG.no_risk_vars || [];
    const _LIMITS_EXCLUDE_VARS = _CONFIG.limits_exclude_vars || [];
    const _BOOLEAN_VARS = _CONFIG.boolean_vars || [];
    const _ENUM_VARS = _CONFIG.enum_vars || [];
    const _ENUM_RISK_VALUES = _CONFIG.enum_risk_values || {};
    const _VALUE_DISPLAY = _CONFIG.value_display_es || {};
    let _SENSOR_RANGES = _CONFIG.sensor_ranges || {};

    let _currentFaults = {};
    const _FAULT_FORCED_RISK = {
        "door_blocked|elev_door_status":    true,
        "pos_sensor_fail|elev_door_status": true,
    };

    const CHART_PUMP_VARS = _BOMBA_VARS.filter(v => v !== 'tank_level');
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
    let _lastPosition = null;
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
        if (_BOOLEAN_VARS.includes(varName)) {
            const crit = !!value;
            return { badge: `badge-${crit ? 'crit' : 'normal'}`, label: crit ? _RISK.critico : _RISK.normal };
        }
        if (_ENUM_VARS.includes(varName)) {
            const risky = _ENUM_RISK_VALUES[varName] || [];
            const crit = risky.includes(String(value).toLowerCase());
            return { badge: `badge-${crit ? 'crit' : 'normal'}`, label: crit ? _RISK.critico : _RISK.normal };
        }
        if (_NO_RISK_VARS.includes(varName)) {
            return { badge: 'badge-normal', label: _RISK.normal };
        }

        const cfg = currentThresholds[varName];
        if (!cfg) return { badge: 'badge-normal', label: _RISK.normal };

        const numVal = Number(value);

        if (cfg.direction === 'range') {
            // cfg.high   = límite INFERIOR del rango normal (ej: 210 V, 20% tank)
            // cfg.critic = límite SUPERIOR del rango normal (ej: 230 V, 85% tank)
            // cfg.crit_low / cfg.crit_high = límites críticos externos
            const lo     = cfg.high;
            const hi     = cfg.critic;
            const critLo = cfg.crit_low;
            const critHi = cfg.crit_high;
            if (critLo !== undefined && numVal < critLo) return { badge: 'badge-crit', label: _RISK.critico };
            if (critHi !== undefined && numVal > critHi) return { badge: 'badge-crit', label: _RISK.critico };
            if (numVal >= lo && numVal <= hi) return { badge: 'badge-normal', label: _RISK.normal };
            return { badge: 'badge-high', label: _RISK.alto };
        }

        // direction === 'higher': cfg.high = umbral Normal→Alto, cfg.critic = umbral Alto→Crítico
        if (numVal > cfg.critic) return { badge: 'badge-crit', label: _RISK.critico };
        if (numVal > cfg.high)   return { badge: 'badge-high', label: _RISK.alto };
        return { badge: 'badge-normal', label: _RISK.normal };
    }

    const getCSSVar = (name) =>
        getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '';


    function _getMovementState(variable, value) {
        if (variable !== 'elev_position') return null;
        if (typeof value !== 'number') return null;

        if (!currentElevOn) {
            _lastPosition = value;
            return { cls: 'inactivo', icon: 'fa-power-off', label: 'Inactivo' };
        }

        if (_lastPosition === null) {
            _lastPosition = value;
            return null;
        }

        const diff = value - _lastPosition;
        _lastPosition = value;

        const isAtFloor = Math.abs(value - Math.round(value)) < 0.05;

        if (Math.abs(diff) < 0.01) {
            if (!isAtFloor) {
                return { cls: 'entre-pisos', icon: 'fa-triangle-exclamation', label: 'Entre pisos' };
            }
            return { cls: 'parado', icon: 'fa-pause', label: 'Parado' };
        }
        if (diff > 0) {
            return { cls: 'subiendo', icon: 'fa-arrow-up', label: 'Subiendo' };
        }
        return { cls: 'bajando', icon: 'fa-arrow-down', label: 'Bajando' };
    }

    // =============================================================================
    // 6. RENDERIZADO DE UI: Tarjetas, Gráficos, Estados
    // =============================================================================

    function updateCards(data) {
        const bombaContainer = document.getElementById('bombaCards');
        const elevadorContainer = document.getElementById('elevadorCards');
        if (!bombaContainer || !elevadorContainer) return;

        for (const [k, v] of Object.entries(data)) {
            const ri = getRiskClass(k, v);
            const displayValue = translateSensorValue(k, v) ?? `${formatNumeric(v, k)} ${getUnit(k)}`;
            const isNoRisk = _NO_RISK_VARS.includes(k);

            let card = document.getElementById(`sensor-card-${k}`);
            if (!card) {
                card = document.createElement('div');
                card.id = `sensor-card-${k}`;
                card.className = 'sensor-card';
                const badgeHtml = isNoRisk ? '' : `<span class="badge ${ri.badge}">${ri.label}</span>`;

                if (k === 'elev_position') {
                    const movementInfo = _getMovementState(k, v);
                    const movementHtml = movementInfo
                        ? `<span class="sensor-card-movement ${movementInfo.cls}"><i class="fa-solid ${movementInfo.icon}"></i> ${movementInfo.label}</span>`
                        : '';
                    card.innerHTML = `
                        <div class="sensor-card-header">
                            <div class="sensor-card-name" data-sensor-name>${getVariableName(k)}</div>
                            ${movementHtml}
                        </div>
                        <div class="sensor-card-value" data-sensor-value>${displayValue}</div>
                        <div class="sensor-card-footer" data-sensor-footer>${badgeHtml}</div>
                    `;
                } else {
                    card.innerHTML = `
                        <div class="sensor-card-name" data-sensor-name>${getVariableName(k)}</div>
                        <div class="sensor-card-value" data-sensor-value>${displayValue}</div>
                        <div class="sensor-card-footer" data-sensor-footer>${badgeHtml}</div>
                    `;
                }

                if (_BOMBA_VARS.includes(k)) bombaContainer.appendChild(card);
                else if (_ELEVADOR_VARS.includes(k)) elevadorContainer.appendChild(card);
            } else {
                card.className = 'sensor-card';
                const valEl = card.querySelector('[data-sensor-value], .sensor-card-value');
                if (valEl && valEl.textContent !== displayValue) valEl.textContent = displayValue;

                if (k === 'elev_position') {
                    const movementInfo = _getMovementState(k, v);
                    const movEl = card.querySelector('.sensor-card-movement');
                    if (movementInfo) {
                        if (movEl) {
                            movEl.className = `sensor-card-movement ${movementInfo.cls}`;
                            movEl.innerHTML = `<i class="fa-solid ${movementInfo.icon}"></i> ${movementInfo.label}`;
                        } else {
                            const headerEl = card.querySelector('.sensor-card-header');
                            if (headerEl) {
                                const mov = document.createElement('span');
                                mov.className = `sensor-card-movement ${movementInfo.cls}`;
                                mov.innerHTML = `<i class="fa-solid ${movementInfo.icon}"></i> ${movementInfo.label}`;
                                headerEl.appendChild(mov);
                            }
                        }
                    } else if (movEl) {
                        movEl.remove();
                    }
                }

                const footerEl = card.querySelector('[data-sensor-footer], .sensor-card-footer');
                if (footerEl) {
                    const badgeEl = footerEl.querySelector('.badge');
                    if (!isNoRisk) {
                        if (badgeEl) { badgeEl.className = `badge ${ri.badge}`; badgeEl.textContent = ri.label; }
                        else footerEl.innerHTML = `<span class="badge ${ri.badge}">${ri.label}</span>`;
                    } else if (badgeEl) {
                        badgeEl.remove();
                    }
                }
            }
        }
    }

    function initCharts() {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js no disponible. Gráficos desactivados.');
            return;
        }
        const canvas1 = document.getElementById('chart1');
        const canvas2 = document.getElementById('chart2');
        if (!canvas1 || !canvas2) {
            console.warn('Canvas para gráficos no encontrados. Omisión de inicialización.');
            return;
        }

        const chartDefaults = {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const dataset = ctx.chart.data.datasets[ctx.datasetIndex];
                            const variable = dataset.variables ? dataset.variables[ctx.dataIndex] : null;
                            const formatted = variable
                                ? formatNumeric(ctx.raw, variable)
                                : (typeof ctx.raw === 'number' ? ctx.raw.toFixed(2) : ctx.raw);
                            return `${ctx.label}: ${formatted}`;
                        },
                    },
                },
            },
            scales: {
                x: { ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
                y: { beginAtZero: true, ticks: { font: { family: "'DM Sans', system-ui", size: 10 } } },
            },
        };

        const inkColor = getCSSVar('--color-ink') || '#0a0a0a';

        chart1 = new Chart(canvas1.getContext('2d'), {
            type: 'bar',
            data: {
                labels: CHART_PUMP_VARS.map(v => `${getVariableName(v)} (${getUnit(v)})`),
                datasets: [{
                    variables: CHART_PUMP_VARS,
                    backgroundColor: inkColor,
                    borderColor: inkColor,
                    borderWidth: 1,
                    data: new Array(CHART_PUMP_VARS.length).fill(0),
                }],
            },
            options: chartDefaults,
        });

        chart2 = new Chart(canvas2.getContext('2d'), {
            type: 'bar',
            data: {
                labels: CHART_ELEV_VARS.map(v => `${getVariableName(v)} (${getUnit(v)})`),
                datasets: [{
                    variables: CHART_ELEV_VARS,
                    backgroundColor: inkColor,
                    borderColor: inkColor,
                    borderWidth: 1,
                    data: new Array(CHART_ELEV_VARS.length).fill(0),
                }],
            },
            options: chartDefaults,
        });
    }

    function updateCharts(history) {
        if (typeof Chart === 'undefined' || !chart1 || !history?.length) return;

        const getLatestReading = (v) => history.filter(item => item.variable === v).pop();
        const getLatest = (v) => { const r = getLatestReading(v); return r ? r.value : 0; };
        const getSensorColor = (v) => {
            const r = getLatestReading(v);
            if (!r) return getCSSVar('--color-ink') || '#0a0a0a';
            if (r.risk === _RISK.critico) return getCSSVar('--state-critical') || '#dc2626';
            if (r.risk === _RISK.alto) return getCSSVar('--state-high') || '#c2410c';
            return getCSSVar('--state-normal') || '#16a34a';
        };

        const applyToChart = (chartInst, vars) => {
            chartInst.data.datasets[0].data = vars.map(getLatest);
            chartInst.data.datasets[0].backgroundColor = vars.map(getSensorColor);
            chartInst.data.datasets[0].borderColor = chartInst.data.datasets[0].backgroundColor;
            chartInst.update();
        };

        if (chart1) applyToChart(chart1, CHART_PUMP_VARS);
        if (chart2) applyToChart(chart2, CHART_ELEV_VARS);
    }

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
    window._csSelect = _csSelect;
    window._csSyncOptions = _csSyncOptions;
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

    function updateFaultWarnings() {
        if (!IS_ADMIN) return;
        const pumpEl = document.getElementById('faultWarningPump');
        const elevEl = document.getElementById('faultWarningElevator');
        const pumpFault = document.getElementById('simFaultPump')?.value;
        const elevFault = document.getElementById('simFaultElevator')?.value;
        const simCtrl = window.SimulationController;
        const pumpOn = currentPumpOn || (simCtrl && simCtrl._pumpOn);
        const elevOn = currentElevOn || (simCtrl && simCtrl._elevOn);

        if (pumpEl) {
            if (pumpFault && !pumpOn) {
                pumpEl.textContent = 'Se activará al encender el equipo';
                pumpEl.style.display = 'block';
            } else {
                pumpEl.style.display = 'none';
            }
        }
        if (elevEl) {
            if (elevFault && !elevOn) {
                elevEl.textContent = 'Se activará al encender el equipo';
                elevEl.style.display = 'block';
            } else {
                elevEl.style.display = 'none';
            }
        }
    }

    function updateAdminControlsByEquipment(equipTypes) {
        if (!IS_ADMIN) return;
        const et = equipTypes || [];
        const hasPump = et.includes('bomba');
        const hasElev = et.includes('elevador');

        const ctrl = window.SimulationController;
        const simStarted = ctrl ? ctrl.simStarted : false;
        const simPaused = ctrl ? ctrl.simPaused : true;
        const simDisabled = !simStarted || simPaused;
        _csSetDisabled(document.getElementById('simFaultPump'), !hasPump || simDisabled);
        _csSetDisabled(document.getElementById('simFaultElevator'), !hasElev || simDisabled);

        updateFaultWarnings();

    }

    function setHistoryBadge(count) {
        const pageBadge = document.getElementById('historyBadgeCount');
        if (!pageBadge) return;
        if (count > 0) { pageBadge.textContent = count; pageBadge.style.display = 'inline-flex'; pageBadge.hidden = false; }
        else { pageBadge.textContent = ''; pageBadge.style.display = 'none'; pageBadge.hidden = true; }
    }


    // =============================================================================
    // 7. CONEXIÓN SSE Y PROCESAMIENTO DE DATOS
    // =============================================================================

    function connectSSE() {
        if (sseSource) sseSource.close();
        const isMonitoring = document.getElementById('activeMonitoring') !== null;

        if (!SSE_URL || typeof EventSource === 'undefined') {
            if (isMonitoring) fetchInitialData();
            return;
        }

        sseSource = new EventSource(SSE_URL);

        sseSource.onopen = () => { if (isMonitoring) renderConnectionStatus(true); };

        sseSource.onerror = () => {
            if (isMonitoring && !monitorConnectionTimeout) {
                monitorConnectionTimeout = setTimeout(() => {
                    showState('stateOffline');
                    monitorConnectionTimeout = null;
                }, 15000);
            }
        };

        sseSource.onmessage = (event) => {
            try { applyPayload(JSON.parse(event.data)); } catch (_) { }
        };

        sseSource.addEventListener('history-event', (event) => {
            try { addLiveHistoryEvent(JSON.parse(event.data)); } catch (_) { }
        });

        if (isMonitoring) fetchInitialData();
    }

    function _countUnreadAlerts(alertLog) {
        return (alertLog || []).filter(a => a.risk !== _RISK.normal).length;
    }

    function applyPayload(data) {
        if (data.thresholds) currentThresholds = data.thresholds;
        if (data.sim_faults) _currentFaults = data.sim_faults;
        if (data.pump_on !== undefined) {
            currentPumpOn = data.pump_on;
            currentElevOn = data.elevator_on === true;
            updateEquipmentPowerBtns(data.pump_on, data.elevator_on);
        }
        hideAllStates();

        const simPaused = data.sim_paused === true;
        const isFirstLoad = Object.keys(currentReadings).length === 0;

        if (IS_ADMIN && window.SimulationController && data.sim_paused !== undefined) {
            SimulationController.syncFromPayload(data);
        }

        if (simPaused && !isFirstLoad) return;

        if (data.current) { currentReadings = data.current; updateCards(data.current); }
        if (data.history) updateCharts(data.history);

        const lastUpd = document.getElementById('lastUpdate');
        if (lastUpd) {
            lastUpd.innerText = data.sim_started ? new Date().toLocaleTimeString() : '--:--:--';
        }

        const hasEquipment = updateEquipmentVisibility(data.equipment_types);
        if (IS_ADMIN) updateAdminControlsByEquipment(data.equipment_types);
        if (data.current && hasEquipment) updateSummaryValues(data);
        if (data.stats) {
            updateStats(data.stats);
        }

        const isHistoryPage = !!document.getElementById('live-history-list');
        if (!isHistoryPage) {
            const totalAlerts = _countUnreadAlerts(data.alert_log);
            unreadHistoryCount = totalAlerts;
            setHistoryBadge(totalAlerts);
        }
    }

    function updateSummaryValues(data) {
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setVal('summaryPumpStatus', data.pump_on ? 'Encendida' : 'Apagada');
        setVal('summaryElevatorStatus', data.elevator_on ? 'Encendido' : 'Apagado');
    }


    // =============================================================================
    // 8. ESTADÍSTICAS
    // =============================================================================

    function renderStatsTable(entries, containerId, firstColLabel) {
        const div = document.getElementById(containerId);
        if (!div) return;
        if (!entries.length) { div.innerHTML = ''; return; }
        const rows = entries.map(([k, v]) =>
            `<tr><td>${getVariableName(k)}</td><td>${formatNumeric(v.avg, k)}</td><td>${formatNumeric(v.min, k)}</td><td>${formatNumeric(v.max, k)}</td></tr>`
        ).join('');
        div.innerHTML = `
            <div class="table-wrapper">
                <table class="report-table">
                    <thead><tr>
                        <th>${firstColLabel}</th>
                        <th>Prom.</th><th>Mín.</th><th>Máx.</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
    }

    function updateStats(stats) {
        const entries = stats && Object.keys(stats).length ? Object.entries(stats) : [];
        renderStatsTable(entries.filter(([k]) => _BOMBA_VARS.includes(k)), 'statsBombaPanel', 'Estadísticas de la bomba');
        renderStatsTable(entries.filter(([k]) => _ELEVADOR_VARS.includes(k)), 'statsElevadorPanel', 'Estadísticas del elevador');
    }


    // =============================================================================
    // 9. UMBRALES Y LÍMITES DE SENSORES
    // =============================================================================

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
        const bombaVars = _BOMBA_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k) && !_THRESHOLDS_HIDDEN_VARS.includes(k));
        const elevadorVars = _ELEVADOR_VARS.filter(k => th[k] && !_NO_RISK_VARS.includes(k) && !_THRESHOLDS_HIDDEN_VARS.includes(k));

        function buildCard(k, cfg) {
            const div = document.createElement('div');
            div.className = 'thresh-card';
            const name = getVariableName(k);
            const unit = getUnit(k);
            const bounds = _SENSOR_RANGES[k];
            const boundsText = bounds ? `Límite: ${bounds[0]} – ${bounds[1]}${unit ? ' ' + unit : ''}` : '';
            const DIR_BADGE = {
                higher: '<span class="thresh-dir-badge" style="color:var(--state-critical);" title="Mayor es peor"><i class="fa-solid fa-arrow-up" aria-hidden="true"></i> Mayor es peor</span>',
                lower: '<span class="thresh-dir-badge" style="color:var(--state-critical);" title="Menor es peor"><i class="fa-solid fa-arrow-down" aria-hidden="true"></i> Menor es peor</span>',
            };
            const dirBadge = DIR_BADGE[cfg.direction] || '<span class="thresh-dir-badge" style="color:var(--state-info);" title="Rango válido"><i class="fa-solid fa-arrows-left-right" aria-hidden="true"></i> Rango válido</span>';
            const headerHtml = `<div class="thresh-card-header">
                <span class="thresh-label">${name}${unit ? ` (${unit})` : ''}</span>
                ${dirBadge}
            </div>`;

            if (cfg.direction === 'range') {
                div.innerHTML = headerHtml + `
                    <div class="thresh-grid-2">
                        <div class="form-group"><label class="form-label">Mínimo aceptable</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                        <div class="form-group"><label class="form-label">Máximo aceptable</label><input type="number" step="any" data-var="${k}" data-level="critic" value="${cfg.critic}" class="form-input"></div>
                    </div>
                    <div class="error-msg"></div>
                    <input type="hidden" data-var="${k}" data-level="direction" value="range">
                    <div class="thresh-card-footer"><span>${boundsText}</span></div>`;
            } else {
                div.innerHTML = headerHtml + `
                    <div class="thresh-grid-2">
                        <div class="form-group"><label class="form-label">Alto</label><input type="number" step="any" data-var="${k}" data-level="high" value="${cfg.high}" class="form-input"></div>
                        <div class="form-group"><label class="form-label">Crítico</label><input type="number" step="any" data-var="${k}" data-level="critic" value="${cfg.critic}" class="form-input"></div>
                    </div>
                    <div class="error-msg"></div>
                    <input type="hidden" data-var="${k}" data-level="direction" value="${cfg.direction}">
                    <div class="thresh-card-footer"><span>${boundsText}</span></div>`;
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

    function renderLimitsPanel(ranges) {
        const bombaVars = _BOMBA_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k) && !_LIMITS_EXCLUDE_VARS.includes(k));
        const elevadorVars = _ELEVADOR_VARS.filter(k => ranges[k] && !_NO_RISK_VARS.includes(k) && !_LIMITS_EXCLUDE_VARS.includes(k));

        function buildLimitCard(k, r) {
            const div = document.createElement('div');
            div.className = 'thresh-card';
            const name = getVariableName(k);
            const unit = getUnit(k);
            const maxVal = r[1];
            const thresh = currentThresholds[k];
            let refText = '';
            if (thresh?.high !== undefined) {
                const label = thresh.direction === 'range' ? 'Máximo aceptable' : 'Crítico';
                refText = `${label}: ${thresh.high}${unit ? ' ' + unit : ''}`;
            }
            const headerHtml = `<div class="thresh-card-header">
                <span class="thresh-label">${name}${unit ? ` (${unit})` : ''}</span>
                ${refText ? `<span class="thresh-hint">${refText}</span>` : ''}
            </div>`;
            div.innerHTML = headerHtml + `
                <div class="form-group">
                    <input type="number" step="any" data-var="${k}" data-level="max" value="${maxVal}" class="form-input">
                    <div class="error-msg"></div>
                </div>`;
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
                const val = parseFloat(inp.value);
                inp.classList.remove('input-error-state');
                inp.removeAttribute('aria-invalid');
                const errorMsgEl = inp.closest('.form-group')?.querySelector('.error-msg');
                if (errorMsgEl) { errorMsgEl.textContent = ''; errorMsgEl.style.visibility = 'hidden'; }

                const showError = (text) => {
                    hasError = true;
                    inp.classList.add('input-error-state');
                    inp.setAttribute('aria-invalid', 'true');
                    if (errorMsgEl) { errorMsgEl.textContent = text; errorMsgEl.style.visibility = 'visible'; }
                };

                if (isNaN(val)) return showError('Introduzca un número válido.');
                const defaultMin = _originalLimits[v]?.[0] ?? 0;
                if (val <= defaultMin) return showError(`Debe ser mayor que el mínimo (${defaultMin}).`);
                const thresh = currentThresholds[v];
                if (thresh?.high !== undefined && val < thresh.high) {
                    const label = thresh.direction === 'range' ? 'máximo aceptable' : 'crítico';
                    const unitStr = getUnit(v) ? ` ${getUnit(v)}` : '';
                    return showError(`No puede ser menor al umbral ${label} (${thresh.high}${unitStr}).`);
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
                newLimits[inp.dataset.var] = parseFloat(inp.value);
            });
        });
        try {
            const resp = await csrfFetch(API.limitsUpdate, { method: 'POST', body: JSON.stringify(newLimits) });
            const res = await resp.json();
            if (res.status === 'ok') {
                _CONFIG.sensor_ranges = res.sensor_ranges;
                _SENSOR_RANGES = res.sensor_ranges;
                currentThresholds = res.thresholds || currentThresholds;
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
        const resetBtn = document.getElementById('resetAllLimitsBtn');
        const totalDirty = _limitsDirtyKeys.size;
        if (badge) {
            if (!totalDirty) {
                badge.classList.add('d-none');
            } else {
                badge.classList.remove('d-none');
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
        if (!await showConfirm('¿Restablecer todos los límites a sus valores originales (último guardado)?')) return;
        resetPanelLimits('bomba');
        resetPanelLimits('elevador');
    }


    // =============================================================================
    // 10. CONTROLES MANUALES DE ADMIN
    // =============================================================================

    const setSimMessage = (msg, type) =>
        showToast(msg, type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');

    function updateEquipmentPowerBtns(pumpOn, elevOn) {
        const pumpBtn = document.getElementById('togglePumpBtn');
        const elevBtn = document.getElementById('toggleElevatorBtn');
        if (pumpBtn && pumpOn !== undefined) {
            pumpBtn.classList.toggle('btn-critical', pumpOn === true);
            pumpBtn.classList.toggle('btn-secondary', pumpOn !== true);
            pumpBtn.title = pumpOn ? 'Apagar la bomba de agua' : 'Encender la bomba de agua';
            const pumpSpan = pumpBtn.querySelector('span');
            if (pumpSpan) pumpSpan.textContent = pumpOn ? 'Apagar' : 'Encender';
        }
        if (elevBtn && elevOn !== undefined) {
            elevBtn.classList.toggle('btn-critical', elevOn === true);
            elevBtn.classList.toggle('btn-secondary', elevOn !== true);
            elevBtn.title = elevOn ? 'Apagar el elevador' : 'Encender el elevador';
            const elevSpan = elevBtn.querySelector('span');
            if (elevSpan) elevSpan.textContent = elevOn ? 'Apagar' : 'Encender';
        }
        updateFaultWarnings();
    }

    async function toggleEquipmentPower(device) {
        if (!EDIFICIO_ID) return;
        const url = device === 'pump'
            ? API.simTogglePump(EDIFICIO_ID)
            : API.simToggleElevator(EDIFICIO_ID);
        try {
            const resp = await csrfFetch(url, { method: 'POST', body: '{}' });
            const data = await resp.json();
            if (data.status === 'ok') {
                if (device === 'pump') {
                    currentPumpOn = data.pump_on;
                    updateEquipmentPowerBtns(data.pump_on, undefined);
                } else {
                    currentElevOn = data.elevator_on;
                    updateEquipmentPowerBtns(undefined, data.elevator_on);
                }
            } else {
                setSimMessage(data.message || 'Error al cambiar el estado del equipo.', 'error');
            }
        } catch (_) {
            setSimMessage('Error de conexión al cambiar el equipo.', 'error');
        }
    }


    // =============================================================================
    // 11. HISTORIAL EN VIVO
    // =============================================================================

    function _parseTimestamp(ts) {
        if (!ts) return '';
        const d = new Date(ts.replace(' ', 'T') + 'Z');
        return isNaN(d.getTime()) ? ts : d.toLocaleString();
    }

    function addLiveHistoryEvent(data) {
        const container = document.getElementById('live-history-list');
        if (!container) return;
        document.getElementById('live-no-history')?.remove();

        let ul = container.querySelector('.hist-list');
        if (!ul) { ul = document.createElement('ul'); ul.className = 'hist-list'; container.appendChild(ul); }

        const li = document.createElement('li');
        li.className = 'hist-item';

        const BADGE_MAP = { 'CRÍTICO': 'sensor-critical', 'ALTO': 'sensor-high', 'NORMAL': 'sensor-normal' };
        const badgeClass = BADGE_MAP[data.risk] || 'sensor-normal';

        if (data.fault_type) {
            const faultName = data.fault_name || data.fault_type;
            const varsList = (data.variables || []).map(v => {
                const varName = typeof v === 'string' ? v : (v.display_name || v.variable);
                const varValue = typeof v === 'string' ? '' : (v.value != null ? ` ${v.value}${v.unit ? ' ' + v.unit : ''}` : '');
                const varRisk = typeof v === 'string' ? '' : v.risk;
                const riskSpan = varRisk ? ` <span class="compound-var-risk">(${safeText(varRisk)})</span>` : '';
                return `<li class="compound-var-item"><strong>${safeText(varName)}</strong>${varValue}${riskSpan}</li>`;
            }).join('');

            li.innerHTML = `
                <div class="hist-body">
                    <div class="flex-wrap mb-1">
                        <span class="sensor-badge ${badgeClass}">${safeText(data.risk)}</span>
                        <span class="value-bold">${safeText(faultName)}</span>
                    </div>
                    <p class="hist-meta-text compound-action">${safeText(data.message)}</p>
                    <ul class="compound-vars-list">
                        ${varsList}
                    </ul>
                    <div class="hist-meta" style="margin-top:8px;">
                        <span><i class="fa-solid fa-clock"></i> ${_parseTimestamp(data.timestamp)}</span>
                    </div>
                </div>`;
        } else {
            const valueStr = String(data.value);
            const unit = getUnit(data.variable);
            const SKIP_VALUES = new Set(['true', 'True', 'false', 'False', 'undefined', 'null']);
            const showValueBox = !SKIP_VALUES.has(valueStr) && valueStr.trim() !== '';
            const valueHtml = showValueBox
                ? `<span class="code-badge">${formatNumeric(data.value, data.variable)}${unit ? ' ' + unit : ''}</span>`
                : '';

            li.innerHTML = `
                <div class="hist-body">
                    <div class="flex-wrap mb-1">
                        <span class="sensor-badge ${badgeClass}">${safeText(data.risk)}</span>
                        ${valueHtml}
                        <span class="value-bold">${safeText(getVariableName(data.variable))}</span>
                    </div>
                    <p class="hist-meta-text">${safeText(data.message)}</p>
                    <div class="hist-meta" style="margin-top:8px;">
                        <span><i class="fa-solid fa-clock"></i> ${_parseTimestamp(data.timestamp)}</span>
                    </div>
                </div>`;
        }

        ul.prepend(li);
        unreadHistoryCount++;
        setHistoryBadge(unreadHistoryCount);
    }

    // =============================================================================
    // 12. MANEJADORES DE EVENTOS
    // =============================================================================

    function initLiveHistory() {
        const clearBtn = document.getElementById('clearDbHistoryBtn');
        if (clearBtn) {
            clearBtn.addEventListener('click', async () => {
                if (!await showConfirm('¿Estás seguro de que deseas limpiar todo el historial?')) return;
                try {
                    const resp = await csrfFetch(API.clearHistory, { method: 'POST' });
                    if (resp.ok) { window.location.href = window.location.pathname; }
                    else throw new Error('Error al limpiar');
                } catch (_) { await showAlert('No se pudo limpiar el historial.', 'error'); }
            });
        }

        document.getElementById('live-history-list')?.addEventListener('click', async (e) => {
            const btn = e.target.closest('.hist-resolve-btn');
            if (!btn) return;
            const recordId = btn.dataset.recordId;
            if (!recordId) return;
            btn.disabled = true;
            try {
                const resp = await csrfFetch(API.resolveAlert(recordId), { method: 'POST' });
                if (resp.ok) {
                    const li = btn.closest('.hist-item');
                    if (li) {
                        li.classList.remove('risk-high', 'risk-crit');
                        li.classList.add('risk-resolved');
                        const badge = li.querySelector('.risk-icon');
                        if (badge) {
                            badge.classList.remove('risk-high', 'risk-crit');
                            badge.classList.add('risk-resolved');
                            badge.innerHTML = '<i class="fa-solid fa-circle-check" aria-hidden="true"></i> Resuelta';
                        }
                    }
                    btn.remove();
                }
            } catch (_) { btn.disabled = false; }
        });
    }

    async function fetchInitialData() {
        if (window.IS_LIMITS_PAGE) {
            try {
                const resp = await fetch(API.sensorLimits(EDIFICIO_ID));
                if (!resp.ok) throw new Error(resp.statusText);
                const data = await resp.json();
                hideAllStates();
                currentThresholds = data.thresholds || {};
                renderLimitsPanel(data.limits || {});
            } catch (_) { showState('stateOffline'); }
            return;
        }

        if (window.IS_THRESHOLDS_PAGE) {
            try {
                const resp = await fetch(API.thresholds(EDIFICIO_ID));
                if (!resp.ok) throw new Error(resp.statusText);
                const raw = await resp.json();
                delete raw.status;
                currentThresholds = raw;
                hideAllStates();
                renderThresholdsPanel(currentThresholds);
            } catch (_) { showState('stateOffline'); }
            return;
        }

        try {
            const resp = await fetch(API.status(EDIFICIO_ID));
            if (!resp.ok) throw new Error(resp.statusText);
            const data = await resp.json();
            applyPayload(data);
            if (IS_ADMIN && data.thresholds) renderThresholdsPanel(data.thresholds);
        } catch (_) {
            if (IS_ADMIN) {
                ['statsBombaPanel', 'statsElevadorPanel'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.innerHTML = '<span class="text-secondary text-sm">Sin datos de telemetría para este edificio.</span>';
                });
            }
        }
    }

    function setupAdminEvents() {
        const togglePumpBtn = document.getElementById('togglePumpBtn');
        const toggleElevBtn = document.getElementById('toggleElevatorBtn');

        if (togglePumpBtn) togglePumpBtn.addEventListener('click', () => toggleEquipmentPower('pump'));
        if (toggleElevBtn) toggleElevBtn.addEventListener('click', () => toggleEquipmentPower('elevator'));

        // Panel de umbrales
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

        // Panel de límites
        const saveLimitsBombaBtn = document.getElementById('saveLimitsBombaBtn');
        const limitsBombaPanel = document.getElementById('limitsBombaPanel');
        const saveLimitsElevadorBtn = document.getElementById('saveLimitsElevadorBtn');
        const limitsElevadorPanel = document.getElementById('limitsElevadorPanel');
        if (saveLimitsBombaBtn) saveLimitsBombaBtn.addEventListener('click', () => saveLimits('bomba'));
        if (limitsBombaPanel) limitsBombaPanel.addEventListener('input', () => validateLimitInputs('bomba'));
        if (saveLimitsElevadorBtn) saveLimitsElevadorBtn.addEventListener('click', () => saveLimits('elevador'));
        if (limitsElevadorPanel) limitsElevadorPanel.addEventListener('input', () => validateLimitInputs('elevador'));

        const resetAllLimitsBtn = document.getElementById('resetAllLimitsBtn');
        if (resetAllLimitsBtn) resetAllLimitsBtn.addEventListener('click', resetAllLimits);
    }

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
    // 14. INICIALIZACIÓN PRINCIPAL
    // =============================================================================

    window.addEventListener('DOMContentLoaded', () => {
        if (window.IS_LIMITS_PAGE) {
            showState('stateLoading');
            fetchInitialData();
            if (IS_ADMIN) setupAdminEvents();
            setupBuildingSelector();
            setupUnsavedChangesGuard();
            return;
        }

        if (window.IS_THRESHOLDS_PAGE) {
            showState('stateLoading');
            fetchInitialData();
            if (IS_ADMIN) setupAdminEvents();
            setupBuildingSelector();
            setupUnsavedChangesGuard();
            return;
        }

        const isMonitoringPage = document.getElementById('activeMonitoring') !== null;

        if (!isMonitoringPage) {
            if (document.getElementById('live-history-list')) {
                const badgeCountEl = document.getElementById('historyBadgeCount');
                if (badgeCountEl) unreadHistoryCount = parseInt(badgeCountEl.textContent, 10) || 0;
                initLiveHistory();
                if (EDIFICIO_ID) connectSSE();
            }

            return;
        }

        setHistoryBadge(0);
        showState('stateLoading');
        initCharts();

        monitorConnectionTimeout = setTimeout(() => {
            showState('stateOffline');
            monitorConnectionTimeout = null;
        }, 15000);

        connectSSE();
        if (IS_ADMIN) setupAdminEvents();
        setupBuildingSelector();
    });


    // =============================================================================
    // 15. VALIDACIÓN DE FORMULARIOS: Delegación de eventos total en document
    // =============================================================================

    function initFormValidation() {
        const REGEX = {
            soloLetras: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]*$/,
            soloDigitos: /^\d*$/,
            rif: /^J\d{7,9}\d$/,
            cedula: /^[VE]\d{6,9}$/,
            email: /^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$/,
            password: /(?=.*[a-zA-Z])(?=.*\d)/,
            direccion: /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s,\.#\-\/()]*$/,
        };

        const KEYPRESS_CONFIG = {
            'solo-letras': { regex: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]$/, useUpper: false, allowDelete: false },
            'solo-numeros': { regex: /^\d$/, useUpper: false, allowDelete: true },
            'username': { regex: /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]$/, useUpper: false, allowDelete: false },
            'email': { regex: /^[a-zA-Z0-9.@]$/, useUpper: false, allowDelete: false },
            'rif': { regex: /^[J\d\-]$/, useUpper: true, allowDelete: false },
            'cedula': { regex: /^[VE\d.\-]$/, useUpper: true, allowDelete: false },
            'cantidad-pisos': { regex: /^\d$/, useUpper: false, allowDelete: true },
            'direccion': { regex: /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s,\.#\-\/()]$/, useUpper: false, allowDelete: false },
        };

        const mostrarError = (input, mensaje) => {
            const grupo = input.closest('[data-form-group], .form-group') || input.parentElement;
            let errEl = grupo.querySelector('[data-error-message], .error-msg');
            if (!errEl) {
                errEl = document.createElement('div');
                errEl.className = 'error-msg';
                errEl.setAttribute('data-error-message', '');
                grupo.appendChild(errEl);
            }
            errEl.textContent = mensaje;
            errEl.style.visibility = 'visible';
            input.classList.add('input-error-state');
            input.setAttribute('aria-invalid', 'true');
        };

        const limpiarError = (input) => {
            const grupo = input.closest('[data-form-group], .form-group') || input.parentElement;
            const errEl = grupo.querySelector('[data-error-message], .error-msg');
            if (errEl) { errEl.textContent = ''; errEl.style.visibility = 'hidden'; }
            input.classList.remove('input-error-state');
            input.removeAttribute('aria-invalid');
        };

        const tieneErrores = (form) => {
            if (form.querySelectorAll('[aria-invalid="true"], .input-error-state').length > 0) return true;
            return Array.from(form.querySelectorAll('input[required], select[required]'))
                .some(el => !el.value || el.value.trim() === '');
        };

        const toggleSubmit = (form) => {
            const btn = form.querySelector('button[type="submit"]');
            if (btn) btn.disabled = tieneErrores(form);
        };

        const validarSoloLetras = (input) => {
            const valor = input.value;
            const maximo = input.maxLength > 0 ? input.maxLength : 999;
            const minimo = input.id === 'nombreEdificio' ? 3 : 2;
            if (valor && !REGEX.soloLetras.test(valor)) {
                input.value = valor.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]/g, '');
                mostrarError(input, 'Este campo solo acepta letras y espacios.');
            } else if (valor.length > maximo) {
                input.value = valor.slice(0, maximo); mostrarError(input, `Máximo ${maximo} caracteres.`);
            } else if (valor.length > 0 && valor.length < minimo) {
                mostrarError(input, `El campo debe tener al menos ${minimo} caracteres.`);
            } else if (valor.length > 0 && valor.trim().length === 0) {
                mostrarError(input, 'Completa este campo correctamente.');
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarSoloNumeros = (input) => {
            const valor = input.value;
            const maximo = input.maxLength > 0 ? input.maxLength : 999;
            const minimo = input.id === 'cedula' ? 6 : 1;
            if (valor && !REGEX.soloDigitos.test(valor)) {
                input.value = valor.replace(/\D/g, ''); mostrarError(input, 'Este campo solo acepta números.');
            } else if (valor.length > maximo) {
                input.value = valor.slice(0, maximo); mostrarError(input, `Máximo ${maximo} dígitos.`);
            } else if (valor.length > 0 && valor.length < minimo) {
                mostrarError(input, `La cédula debe tener al menos ${minimo} dígitos.`);
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarRIF = (input) => {
            let valor = input.value.toUpperCase().replace(/[^J\d\-]/g, '');
            if (input.value !== valor) input.value = valor;
            const cleaned = valor.replace(/[.\-\s]/g, '');
            if (valor && !REGEX.rif.test(cleaned)) {
                mostrarError(input, 'Formato: J + 7-9 dígitos + dígito control. Ej: J-12345678-0');
            } else if (valor) {
                limpiarError(input);
                const excludeId = input.getAttribute('data-exclude-id') || '';
                const checkUrl = input.getAttribute('data-url') || '/api/check-rif/';
                fetch(`${checkUrl}?rif=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.exists) mostrarError(input, 'Este RIF ya está registrado en otro edificio.');
                        else limpiarError(input);
                        toggleSubmit(input.form);
                    }).catch(() => { });
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarCedula = (input) => {
            let valor = input.value.toUpperCase().replace(/[^VE\d.\-]/g, '');
            if (input.value !== valor) input.value = valor;
            const cleaned = valor.replace(/[.\-\s]/g, '');
            if (valor && !REGEX.cedula.test(cleaned)) {
                mostrarError(input, 'Formato: V o E + 6-9 dígitos. Ej: V-12345678');
            } else if (valor) {
                limpiarError(input);
                const excludeId = input.getAttribute('data-exclude-id') || '';
                const checkUrl = input.getAttribute('data-url') || '/api/check-cedula/';
                fetch(`${checkUrl}?cedula=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.exists) mostrarError(input, 'Esta cédula ya está registrada por otro usuario.');
                        else limpiarError(input);
                        toggleSubmit(input.form);
                    }).catch(() => { });
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarUsername = (input) => {
            const valor = input.value;
            const valido = /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+$/;
            if (valor && !valido.test(valor)) { input.value = valor.replace(/[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]/g, ''); mostrarError(input, 'Solo se permiten letras y números, sin espacios.'); }
            else if (valor && valor.length < 4) mostrarError(input, 'El nombre de usuario debe tener al menos 4 caracteres.');
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarEmail = (input) => {
            const valor = input.value;
            if (valor && valor.includes('@') && valor.split('@')[0].length > 30) {
                mostrarError(input, 'Máximo 30 caracteres antes del @.'); toggleSubmit(input.form); return;
            }
            if (valor && valor.length < 6) mostrarError(input, 'El correo debe tener al menos 6 caracteres.');
            else if (valor && !REGEX.email.test(valor)) mostrarError(input, 'Ingresa un correo electrónico válido.');
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarPassword = (input) => {
            const valor = input.value;
            if (valor && valor.length < 6) mostrarError(input, 'La contraseña debe tener al menos 6 caracteres.');
            else if (valor && !REGEX.password.test(valor)) mostrarError(input, 'Debe contener letras y números.');
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarConfirmPassword = (input) => {
            const passField = input.form.querySelector('#password') || input.form.querySelector('#new_password') || input.form.querySelector('#current_password');
            if (input.value && input.value !== passField?.value) mostrarError(input, 'Las contraseñas no coinciden.');
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarCantidadPisos = (input) => {
            const valor = input.value;
            const MAX_FLOORS = 150;
            if (valor && !/^\d+$/.test(valor)) {
                mostrarError(input, 'La cantidad de pisos debe ser un número entero.');
            } else if (valor) {
                const num = parseInt(valor, 10);
                if (num === 0) {
                    mostrarError(input, 'La cantidad de pisos debe ser mayor a 0.');
                } else if (num > MAX_FLOORS) {
                    mostrarError(input, `La cantidad de pisos no puede exceder ${MAX_FLOORS}.`);
                } else {
                    const elevatorInput = input.form?.querySelector('input[name="con_elevador"]');
                    if (elevatorInput && elevatorInput.value === 'true' && num <= 1) {
                        mostrarError(input, 'Un edificio de 1 piso no puede tener elevador.');
                    } else {
                        limpiarError(input);
                    }
                }
            } else {
                limpiarError(input);
            }
            toggleSubmit(input.form);
        };

        const validarDireccion = (input) => {
            const valor = input.value;
            const maximo = input.maxLength > 0 ? input.maxLength : 100;
            const minimo = 8;
            if (valor && !REGEX.direccion.test(valor)) {
                input.value = valor.replace(/[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s,\.#\-/()]/g, '');
                mostrarError(input, 'La dirección contiene caracteres no válidos.');
            } else if (valor.length > maximo) {
                input.value = valor.slice(0, maximo); mostrarError(input, `Máximo ${maximo} caracteres.`);
            } else if (valor.length > 0 && valor.length < minimo) {
                mostrarError(input, `La dirección debe tener al menos ${minimo} caracteres.`);
            } else if (valor.length > 0 && valor.trim().length === 0) {
                mostrarError(input, 'Completa este campo correctamente.');
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const VALIDATORS = {
            'solo-letras': validarSoloLetras,
            'solo-numeros': validarSoloNumeros,
            'rif': validarRIF,
            'cedula': validarCedula,
            'email': validarEmail,
            'password': validarPassword,
            'confirm-password': validarConfirmPassword,
            'username': validarUsername,
            'cantidad-pisos': validarCantidadPisos,
            'direccion': validarDireccion,
        };

        // --- Registro de Listeners Delegados en document ---

        // Delegación de entrada (input)
        document.addEventListener('input', (e) => {
            const input = e.target.closest('input[data-validate]');
            if (input) {
                const tipo = input.getAttribute('data-validate');
                const validator = VALIDATORS[tipo];
                if (!validator) return;
                validator(input);
                if (tipo === 'password') {
                    const confirmField = input.form?.querySelector('[data-validate="confirm-password"]');
                    if (confirmField?.value) validarConfirmPassword(confirmField);
                }
            }
        });

        // Delegación de teclado (keypress)
        document.addEventListener('keypress', (e) => {
            const input = e.target.closest('input[data-validate]');
            if (input) {
                const tipo = input.getAttribute('data-validate');
                const cfg = KEYPRESS_CONFIG[tipo];
                if (!cfg) return;
                const key = cfg.useUpper ? e.key.toUpperCase() : e.key;
                const allowed = cfg.regex.test(key) || e.key === 'Backspace' || e.key === 'Tab' || (cfg.allowDelete && e.key === 'Delete');
                if (!allowed) e.preventDefault();
            }
        });

        // Delegación de foco saliente (focusout) para forzar validación en blur
        document.addEventListener('focusout', (e) => {
            const input = e.target.closest('input[data-validate]');
            if (input) {
                const tipo = input.getAttribute('data-validate');
                const validator = VALIDATORS[tipo];
                if (validator) validator(input);
            }
        });

        // Delegación para elementos <select>
        const handleSelectChange = (select) => {
            if (select.value) limpiarError(select);
            else if (select.required) mostrarError(select, 'Este campo es obligatorio.');
            if (select.form) toggleSubmit(select.form);
        };

        document.addEventListener('change', (e) => {
            const select = e.target.closest('select');
            if (select) handleSelectChange(select);
        });

        document.addEventListener('input', (e) => {
            const select = e.target.closest('select');
            if (select) handleSelectChange(select);
        });

        // Delegación de envío de formulario (submit)
        document.addEventListener('submit', (e) => {
            const form = e.target.closest('form');
            if (form) {
                let hasErrors = false;
                form.querySelectorAll('input[required], select[required]').forEach((input) => {
                    if (!input.value || input.value.trim() === '') {
                        mostrarError(input, 'Este campo es obligatorio.'); hasErrors = true;
                    }
                });
                if (hasErrors || tieneErrores(form)) {
                    e.preventDefault();
                    toggleSubmit(form);
                    const firstError = form.querySelector('.input-error-state, [aria-invalid="true"]');
                    if (firstError) {
                        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        firstError.focus();
                    }
                }
            }
        });

        // --- Inicialización al cargar el formulario ---
        document.querySelectorAll('form').forEach((form) => {
            form.querySelectorAll('input[data-validate], select[data-validate]').forEach((input) => {
                if (input.classList.contains('input-error-state') || !input.value) return;
                input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
            });
            toggleSubmit(form);
        });
    }

    document.addEventListener('DOMContentLoaded', initFormValidation);


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
    window.updateFaultWarnings = updateFaultWarnings;
    window.fetchInitialData = fetchInitialData;

})(window, document);
