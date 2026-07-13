// =============================================================================
// script.js — Dispatcher principal de inicialización por página
// =============================================================================
// shared.js, forms.js, y el JS específico de cada página se cargan por separado.
// Este archivo solo orquesta la inicialización según la página activa.

'use strict';

(function (window, document) {

    window.addEventListener('DOMContentLoaded', () => {
        const IS_ADMIN = window.IS_ADMIN === true;

        // --- Página de límites ---
        if (window.IS_LIMITS_PAGE) {
            showState('stateLoading');
            if (typeof window.AppLimitsInit === 'function') window.AppLimitsInit();
            if (IS_ADMIN && typeof window.AppLimitsSetupEvents === 'function') window.AppLimitsSetupEvents();
            setupBuildingSelector();
            setupUnsavedChangesGuard();
            return;
        }

        // --- Página de umbrales ---
        if (window.IS_THRESHOLDS_PAGE) {
            showState('stateLoading');
            if (typeof window.AppThresholdsInit === 'function') window.AppThresholdsInit();
            if (IS_ADMIN && typeof window.AppThresholdsSetupEvents === 'function') window.AppThresholdsSetupEvents();
            setupBuildingSelector();
            setupUnsavedChangesGuard();
            return;
        }

        // --- Página de monitoreo ---
        const isMonitoringPage = document.getElementById('activeMonitoring') !== null;

        if (isMonitoringPage) {
            if (typeof window.AppMonitoringInit === 'function') window.AppMonitoringInit();
            if (IS_ADMIN && typeof window.AppMonitoringSetupEvents === 'function') window.AppMonitoringSetupEvents();
            setupBuildingSelector();
            return;
        }

        // --- Página de historial (SSE live history) ---
        if (document.getElementById('live-history-list')) {
            const badgeCountEl = document.getElementById('historyBadgeCount');
            if (badgeCountEl) unreadHistoryCount = parseInt(badgeCountEl.textContent, 10) || 0;
            if (typeof initLiveHistory === 'function') initLiveHistory();
            if (EDIFICIO_ID && typeof connectSSE === 'function') connectSSE();
        }
    });

})(window, document);
