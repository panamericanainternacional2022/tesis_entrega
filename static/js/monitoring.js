// =============================================================================
// monitoring.js — Lógica específica de la página de monitoreo en vivo
// =============================================================================

(function (window, document) {
    'use strict';

    // These variables reference globals defined in shared.js:
    // EDIFICIO_ID, API, IS_ADMIN, _BOMBA_VARS, _ELEVADOR_VARS
    // _RISK, _currentFaults, currentThresholds
    // currentPumpOn, currentElevOn, currentReadings
    // _elevTargetFloor, _pumpDemand, _faultInjectedAt
    // chart1, chart2, sseSource, monitorConnectionTimeout, unreadHistoryCount
    // CHART_PUMP_VARS, CHART_ELEV_VARS

    let _persistCounter = 0;
    const _PERSIST_INTERVAL = 30;

    function updateCards(data) {
        const bombaContainer = document.getElementById('bombaCards');
        const elevadorContainer = document.getElementById('elevadorCards');
        if (!bombaContainer || !elevadorContainer) return;

        for (const [k, v] of Object.entries(data)) {
            const ri = getRiskClass(k, v);
            const displayValue = translateSensorValue(k, v) ?? `${formatNumeric(v, k)} ${getUnit(k)}`;

            let card = document.getElementById(`sensor-card-${k}`);
            if (!card) {
                card = document.createElement('div');
                card.id = `sensor-card-${k}`;
                card.className = 'sensor-card';
                const badgeHtml = `<span class="badge ${ri.badge}">${ri.label}</span>`;

                if (k === 'elev_position') {
                    const showTarget = _elevTargetFloor !== undefined && _elevTargetFloor !== 0;
                    const targetHtml = showTarget
                        ? `<span class="sensor-card-target">→ ${translateSensorValue('elev_position', _elevTargetFloor) || _elevTargetFloor}</span>`
                        : '';
                    card.innerHTML = `
                        <div class="sensor-card-name" data-sensor-name>${getVariableName(k)}</div>
                        <div class="sensor-card-value" data-sensor-value>${displayValue}</div>
                        <div class="sensor-card-footer" data-sensor-footer>
                            ${badgeHtml}
                            ${targetHtml}
                        </div>
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
                    const targetEl = card.querySelector('.sensor-card-target');
                    const showTarget = _elevTargetFloor !== undefined && _elevTargetFloor !== 0;
                    if (targetEl) {
                        if (showTarget) {
                            targetEl.textContent = `→ ${translateSensorValue('elev_position', _elevTargetFloor) || _elevTargetFloor}`;
                        } else {
                            targetEl.remove();
                        }
                    } else if (showTarget) {
                        const footerEl = card.querySelector('.sensor-card-footer');
                        if (footerEl) {
                            const tgt = document.createElement('span');
                            tgt.className = 'sensor-card-target';
                            tgt.textContent = `→ ${translateSensorValue('elev_position', _elevTargetFloor) || _elevTargetFloor}`;
                            footerEl.appendChild(tgt);
                        }
                    }
                }

                const footerEl = card.querySelector('[data-sensor-footer], .sensor-card-footer');
                if (footerEl) {
                    const badgeEl = footerEl.querySelector('.badge');
                    if (badgeEl) { badgeEl.className = `badge ${ri.badge}`; badgeEl.textContent = ri.label; }
                    else footerEl.innerHTML = `<span class="badge ${ri.badge}">${ri.label}</span>`;
                }
            }
        }
    }

    // ─────────────── DAILY CHART CONFIG ───────────────

    var LINE_PALETTE = [
        '#2563eb', '#dc2626', '#16a34a', '#d97706',
        '#7c3aed', '#0891b2', '#c026d3', '#ea580c',
    ];

    var BRUTAL_FONT = { family: "'DM Sans', system-ui", size: 11, weight: '500' };
    var BRUTAL_FONT_SM = { family: "'DM Sans', system-ui", size: 10 };

    var _brutalTooltip = {
        enabled: true,
        backgroundColor: '#0a0a0a',
        titleColor: '#ffffff',
        bodyColor: '#ffffff',
        titleFont: { family: "'DM Sans', system-ui", size: 12, weight: '700' },
        bodyFont: { family: "'DM Sans', system-ui", size: 11 },
        padding: { top: 10, bottom: 10, left: 14, right: 14 },
        borderColor: '#0a0a0a',
        borderWidth: 3,
        cornerRadius: 0,
        displayColors: true,
        boxWidth: 10,
        boxHeight: 10,
        boxPadding: 6,
        usePointStyle: false,
    };

    // ─── Plugin: borde brutalista alrededor del canvas ───
    var brutalBorderPlugin = {
        id: 'brutalBorder',
        beforeDraw: function (chart) {
            var ctx = chart.ctx;
            var xAxis = chart.scales.x;
            var yAxis = chart.scales.y;
            if (!xAxis || !yAxis) return;
            var area = chart.chartArea;
            if (!area) return;
            ctx.save();
            ctx.strokeStyle = '#0a0a0a';
            ctx.lineWidth = 3;
            ctx.strokeRect(area.left, area.top, area.right - area.left, area.bottom - area.top);
            ctx.restore();
        }
    };

    function _formatDayLabel(dayStr) {
        if (!dayStr) return '';
        var parts = dayStr.split('-');
        return parts[2] + '/' + parts[1];
    }

    function initCharts() {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js no disponible. Gráficos desactivados.');
            return;
        }
        var canvas1 = document.getElementById('chart1');
        var canvas2 = document.getElementById('chart2');
        if (!canvas1 || !canvas2) {
            console.warn('Canvas para gráficos no encontrados. Omisión de inicialización.');
            return;
        }

        Chart.register(brutalBorderPlugin);

        var chartDefaults = {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 8, right: 12, bottom: 16, left: 4 } },
            plugins: {
                legend: {
                    display: true,
                    position: 'bottom',
                    labels: {
                        font: BRUTAL_FONT_SM,
                        usePointStyle: true,
                        pointStyle: 'rectRounded',
                        padding: 20,
                        color: '#0a0a0a',
                        boxWidth: 14,
                        boxHeight: 14,
                    },
                },
                tooltip: _brutalTooltip,
            },
            scales: {
                x: {
                    type: 'category',
                    border: { color: '#0a0a0a', width: 2 },
                    ticks: {
                        font: BRUTAL_FONT_SM,
                        maxRotation: 0,
                        color: '#5e5e5e',
                        padding: 6,
                    },
                    grid: { display: false },
                },
                y: {
                    type: 'linear',
                    beginAtZero: true,
                    border: { color: '#0a0a0a', width: 2 },
                    ticks: {
                        font: BRUTAL_FONT_SM,
                        color: '#5e5e5e',
                        padding: 8,
                    },
                    grid: {
                        color: 'rgba(10, 10, 10, 0.08)',
                        lineWidth: 1,
                        drawTicks: false,
                    },
                },
            },
            animation: false,
        };

        function _legendCursorHandler(isLeave) {
            return function (e, legendItem, legend) {
                legend.chart.canvas.style.cursor = isLeave ? 'default' : 'pointer';
            };
        }

        var opts1 = JSON.parse(JSON.stringify(chartDefaults));
        opts1.plugins.legend.onHover = _legendCursorHandler(false);
        opts1.plugins.legend.onLeave = _legendCursorHandler(true);
        opts1.scales.y.afterFit = function (scale) { scale.width = 65; };
        chart1 = new Chart(canvas1.getContext('2d'), {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: opts1,
        });

        var opts2 = JSON.parse(JSON.stringify(chartDefaults));
        opts2.plugins.legend.onHover = _legendCursorHandler(false);
        opts2.plugins.legend.onLeave = _legendCursorHandler(true);
        opts2.scales.y.afterFit = function (scale) { scale.width = 65; };
        chart2 = new Chart(canvas2.getContext('2d'), {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: opts2,
        });
    }

    function _buildDailyDatasets(variables, varData) {
        var datasets = [];
        variables.forEach(function (v, i) {
            var color = LINE_PALETTE[i % LINE_PALETTE.length];
            var info = varData[v];
            if (!info) return;

            datasets.push({
                label: getVariableName(v) + ' (' + getUnit(v) + ')',
                data: info.avg,
                borderColor: color,
                backgroundColor: color,
                borderWidth: 3,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: '#ffffff',
                pointBorderColor: color,
                pointBorderWidth: 2,
                pointHoverBackgroundColor: color,
                pointHoverBorderColor: '#0a0a0a',
                pointHoverBorderWidth: 2,
                tension: 0.3,
                fill: false,
                variable: v,
            });
        });
        return datasets;
    }

    function renderDailyCharts(data) {
        if (!chart1 && !chart2) return;
        var labels = (data.labels || []).map(_formatDayLabel);

        if (chart1 && data.pump) {
            var pumpVars = Object.keys(data.pump);
            chart1.data.labels = labels;
            chart1.data.datasets = _buildDailyDatasets(pumpVars, data.pump);
            chart1.update('none');
        }

        if (chart2 && data.elevator) {
            var elevVars = Object.keys(data.elevator);
            chart2.data.labels = labels;
            chart2.data.datasets = _buildDailyDatasets(elevVars, data.elevator);
            chart2.update('none');
        }
    }

    function fetchDailyData() {
        if (!EDIFICIO_ID) return;
        fetch('/api/sensors/daily/' + EDIFICIO_ID + '/?days=7')
            .then(function (r) { return r.json(); })
            .then(function (data) { renderDailyCharts(data); })
            .catch(function () {});
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
        const pumpOff = ctrl ? !ctrl._pumpOn : false;
        const elevOff = ctrl ? !ctrl._elevOn : false;
        _csSetDisabled(document.getElementById('simFaultPump'), !hasPump || simDisabled || pumpOff);
        _csSetDisabled(document.getElementById('simFaultElevator'), !hasElev || simDisabled || elevOff);
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
        if (data.elev_target_floor !== undefined) _elevTargetFloor = data.elev_target_floor;
        if (data.pump_demand !== undefined) _pumpDemand = data.pump_demand;
        if (data.fault_injected_at) _faultInjectedAt = data.fault_injected_at;
        hideAllStates();

        const simPaused = data.sim_paused === true;
        const isFirstLoad = Object.keys(currentReadings).length === 0;

        if (IS_ADMIN && window.SimulationController && data.sim_paused !== undefined) {
            SimulationController.syncFromPayload(data);
        }

        if (!simPaused && data.sim_speed) {
            _persistCounter += data.sim_speed;
            if (_persistCounter >= _PERSIST_INTERVAL) {
                _persistCounter = 0;
                fetchDailyData();
            }
        }

        if (simPaused && !isFirstLoad) return;

        if (data.current) { currentReadings = data.current; updateCards(data.current); }

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

    }

    function updateSummaryValues(data) {
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setVal('summaryPumpStatus', data.pump_on ? 'Encendida' : 'Apagada');
        setVal('summaryElevatorStatus', data.elevator_on ? 'Encendido' : 'Apagado');
    }

    function renderStatsTable(entries, containerId, firstColLabel) {
        var div = document.getElementById(containerId);
        if (!div) return;
        if (!entries.length) { div.innerHTML = ''; return; }
        var rows = entries.map(function (entry) {
            var k = entry[0], v = entry[1];
            var std = v.std != null ? formatNumeric(v.std, k) : '-';
            return '<tr><td>' + getVariableName(k) + '</td>'
                + '<td>' + formatNumeric(v.avg, k) + '</td>'
                + '<td>' + formatNumeric(v.min, k) + '</td>'
                + '<td>' + formatNumeric(v.max, k) + '</td>'
                + '<td>' + std + '</td></tr>';
        }).join('');
        div.innerHTML =
            '<section class="chart-panel">' +
                '<div class="form-section-header">' +
                    '<h2 class="form-page-title form-section-title">' + firstColLabel + '</h2>' +
                '</div>' +
                '<div class="table-wrapper">' +
                '<table class="report-table stats-table">' +
                '<thead><tr>' +
                '<th>Variable</th>' +
                '<th>Prom.</th><th>Mín.</th><th>Máx.</th><th>Desv. Est.</th>' +
                '</tr></thead>' +
                '<tbody>' + rows + '</tbody>' +
                '</table></div>' +
            '</section>';
    }

    function updateStats(stats) {
        var entries = stats && Object.keys(stats).length ? Object.entries(stats) : [];
        renderStatsTable(entries.filter(function (e) { return _BOMBA_VARS.includes(e[0]); }), 'statsBombaPanel', 'Estadísticas de la bomba');
        renderStatsTable(entries.filter(function (e) { return _ELEVADOR_VARS.includes(e[0]); }), 'statsElevadorPanel', 'Estadísticas del elevador');
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
                currentPumpOn = data.pump_on;
                currentElevOn = data.elevator_on;
                updateEquipmentPowerBtns(data.pump_on, data.elevator_on);
                updateSummaryValues({pump_on: currentPumpOn, elevator_on: currentElevOn});
                if (data.faults) {
                    _currentFaults = data.faults;
                }
                var ctrl = window.SimulationController;
                if (ctrl) {
                    ctrl._pumpOn = data.pump_on;
                    ctrl._elevOn = data.elevator_on;
                    ctrl._activePumpFault = (data.faults && data.faults.pump) || '';
                    ctrl._activeElevFault = (data.faults && data.faults.elevator) || '';
                    if (window._csSetValue) window._csSetValue(document.getElementById('simFaultPump'), ctrl._activePumpFault);
                    if (window._csSetValue) window._csSetValue(document.getElementById('simFaultElevator'), ctrl._activeElevFault);
                    ctrl._updateControlStates();
                    ctrl._updateFaultUI();
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

    const _faultTypeToDisplay = (faultType) => {
        const name = (window._CONFIG && window._CONFIG.fault_names_es && window._CONFIG.fault_names_es[faultType]);
        return name || faultType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    };

    function addLiveHistoryEvent(data) {
        const container = document.getElementById('live-history-list');
        if (!container) return;

        let ul = container.querySelector('.hist-list');
        if (!ul) {
            container.querySelectorAll('.no-history').forEach(function (el) { el.remove(); });
            ul = document.createElement('ul'); ul.className = 'hist-list'; container.appendChild(ul);
        }

        const li = document.createElement('li');
        li.className = 'hist-item';

        var _riskUpper = (data.risk || '').toUpperCase();
        var BADGE_MAP = { 'CRÍTICO': 'sensor-critical', 'ALTO': 'sensor-high', 'NORMAL': 'sensor-normal' };
        var badgeClass = BADGE_MAP[_riskUpper] || 'sensor-normal';

        if (data.fault_type) {
            li.setAttribute('data-fault-type', data.fault_type);
            const faultName = data.fault_name || _faultTypeToDisplay(data.fault_type);
            const varsList = (data.variables || []).map(v => {
                const varName = typeof v === 'string' ? v : (v.display_name || getVariableName(v.variable));
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
                const filters = {};
                const edi = document.getElementById('hidden-edificio')?.value;
                const sev = document.getElementById('hidden-severidad')?.value;
                const vrb = document.getElementById('hidden-variable')?.value;
                const fdesde = document.getElementById('hidden-fecha-desde')?.value;
                const fhasta = document.getElementById('hidden-fecha-hasta')?.value;
                const per = document.getElementById('periodoSelect')?.value;

                if (edi) filters.edificio = edi;
                if (sev) filters.severidad = sev;
                if (vrb) filters.variable = vrb;
                if (fdesde) filters.fecha_desde = fdesde;
                if (fhasta) filters.fecha_hasta = fhasta;
                if (per) filters.periodo = per;

                let scopeMsg = 'todos tus registros';
                const buildingName = window.SELECTED_EDIFICIO_NOMBRE;
                if (buildingName) {
                    scopeMsg = `tus registros del edificio "${buildingName}"`;
                }
                if (sev || vrb || fdesde) {
                    scopeMsg += ' con los filtros actuales';
                }
                if (!await showConfirm(`¿Estás seguro de que deseas limpiar ${scopeMsg}?`)) return;
                try {
                    const resp = await csrfFetch(API.clearHistory, {
                        method: 'POST',
                        body: JSON.stringify(filters),
                    });
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
                const data = resp.ok ? await resp.json().catch(function () { return {}; }) : {};
                if (data.status === 'ok' || resp.ok) {
                    const li = btn.closest('.hist-item');
                    const faultType = li ? li.getAttribute('data-fault-type') : null;
                    // Mark ALL history items with the same fault_type as resolved
                    if (faultType) {
                        var escaped = faultType.replace(/"/g, '\\"');
                        document.querySelectorAll('#live-history-list .hist-item[data-fault-type="' + escaped + '"]').forEach(function (item) {
                            item.classList.remove('risk-high', 'risk-crit');
                            item.classList.add('risk-resolved');
                            var badge = item.querySelector('.risk-icon');
                            if (badge) {
                                badge.classList.remove('risk-high', 'risk-crit');
                                badge.classList.add('risk-resolved');
                                badge.innerHTML = '<i class="fa-solid fa-circle-check" aria-hidden="true"></i> Resuelta';
                            }
                            var rBtn = item.querySelector('.hist-resolve-btn');
                            if (rBtn) rBtn.remove();
                        });
                    } else if (li) {
                        li.classList.remove('risk-high', 'risk-crit');
                        li.classList.add('risk-resolved');
                        var badge = li.querySelector('.risk-icon');
                        if (badge) {
                            badge.classList.remove('risk-high', 'risk-crit');
                            badge.classList.add('risk-resolved');
                            badge.innerHTML = '<i class="fa-solid fa-circle-check" aria-hidden="true"></i> Resuelta';
                        }
                        btn.remove();
                    }
                    unreadHistoryCount = Math.max(0, unreadHistoryCount - 1);
                    setHistoryBadge(unreadHistoryCount);
                    // Sync simulation state if server returned updated faults
                    if (data.faults) {
                        _currentFaults = data.faults;
                        var ctrl = window.SimulationController;
                        if (ctrl) {
                            ctrl._activePumpFault = data.faults.pump || '';
                            ctrl._activeElevFault = data.faults.elevator || '';
                            if (window._csSetValue) {
                                window._csSetValue(document.getElementById('simFaultPump'), ctrl._activePumpFault);
                                window._csSetValue(document.getElementById('simFaultElevator'), ctrl._activeElevFault);
                            }
                            ctrl._updateControlStates();
                            ctrl._updateFaultUI();
                        }
                        if (typeof window.updateCards === 'function') {
                            window.updateCards(currentReadings);
                        }
                    }
                }
            } catch (_) { btn.disabled = false; }
        });
    }

    // Expose to window for SimulationController (in monitoring_dashboard.html inline script)
    window.fetchInitialData = fetchInitialData_monitoring;
    window.initLiveHistory = initLiveHistory;
    window.connectSSE = connectSSE;
    window.addLiveHistoryEvent = addLiveHistoryEvent;
    window.updateEquipmentPowerBtns = updateEquipmentPowerBtns;
    window.updateCards = updateCards;

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
        showState('stateLoading');
        initCharts();
        fetchDailyData();

        var _origClear = window.clearCurrentReadings || function () {};
        window.clearCurrentReadings = function () {
            _persistCounter = 0;
            _origClear();
            [chart1, chart2].forEach(function (c) {
                if (!c) return;
                c.data.labels = [];
                c.data.datasets = [];
                c.update('none');
            });
            fetchDailyData();
        };

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
