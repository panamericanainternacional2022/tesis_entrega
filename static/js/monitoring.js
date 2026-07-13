// =============================================================================
// monitoring.js — Lógica específica de la página de monitoreo en vivo
// =============================================================================

(function (window, document) {
    'use strict';

    // These variables reference globals defined in shared.js:
    // EDIFICIO_ID, API, IS_ADMIN, _BOMBA_VARS, _ELEVADOR_VARS, _NO_RISK_VARS
    // _RISK, _currentFaults, _FAULT_FORCED_RISK, currentThresholds
    // currentPumpOn, currentElevOn, currentReadings, _lastPosition
    // chart1, chart2, sseSource, monitorConnectionTimeout, unreadHistoryCount
    // CHART_PUMP_VARS, CHART_ELEV_VARS

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

    function connectSSE() {
        if (sseSource) sseSource.close();

        if (!SSE_URL || typeof EventSource === 'undefined') {
            fetchInitialData_monitoring();
            return;
        }

        sseSource = new EventSource(SSE_URL);

        sseSource.onopen = () => { renderConnectionStatus(true); };

        sseSource.onerror = () => {
            if (!monitorConnectionTimeout) {
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

        fetchInitialData_monitoring();
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

    // Admin manual controls
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

    // Live history
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

    // Expose to window for SimulationController (in monitoring_dashboard.html inline script)
    window.updateFaultWarnings = updateFaultWarnings;
    window.fetchInitialData = fetchInitialData_monitoring;
    window.initLiveHistory = initLiveHistory;
    window.connectSSE = connectSSE;
    window.updateEquipmentPowerBtns = updateEquipmentPowerBtns;

    function fetchInitialData_monitoring() {
        // This is the monitoring-specific fetchInitialData (lines 1719-1733)
        // For monitoring page: fetch API.status() and apply
        (async function() {
            try {
                const resp = await fetch(API.status(EDIFICIO_ID));
                if (!resp.ok) throw new Error(resp.statusText);
                const data = await resp.json();
                applyPayload(data);
                if (IS_ADMIN && data.thresholds && typeof renderThresholdsPanel === 'function') renderThresholdsPanel(data.thresholds);
            } catch (_) {
                if (IS_ADMIN) {
                    ['statsBombaPanel', 'statsElevadorPanel'].forEach(id => {
                        const el = document.getElementById(id);
                        if (el) el.innerHTML = '<span class="text-secondary text-sm">Sin datos de telemetría para este edificio.</span>';
                    });
                }
            }
        })();
    }

    // Public init function called by the dispatcher in script.js
    window.AppMonitoringInit = function initMonitoringPage() {
        setHistoryBadge(0);
        showState('stateLoading');
        initCharts();
        
        monitorConnectionTimeout = setTimeout(() => {
            showState('stateOffline');
            monitorConnectionTimeout = null;
        }, 15000);
        
        connectSSE();

        // Admin manual controls (from setupAdminEvents)
        const togglePumpBtn = document.getElementById('togglePumpBtn');
        const toggleElevBtn = document.getElementById('toggleElevatorBtn');
        if (togglePumpBtn) togglePumpBtn.addEventListener('click', () => toggleEquipmentPower('pump'));
        if (toggleElevBtn) toggleElevBtn.addEventListener('click', () => toggleEquipmentPower('elevator'));
    };

})(window, document);
