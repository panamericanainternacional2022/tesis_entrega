// =============================================================================
// forms.js - Validación genérica de formularios (delegación en document)
// =============================================================================

(function (window, document) {
    'use strict';

    function initFormValidation() {
        const REGEX = {
            soloLetras: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$/,
            soloLetrasNumeros: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9\s]+$/,
            soloDigitos: /^\d*$/,
            rif: /^J\d{7,9}\d$/,
            cedula: /^[VE]\d{6,14}$/,
            email: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$/,
            password: /(?=.*[a-zA-Z])(?=.*\d)/,
            direccion: /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s,\.#\-\/()]*$/,
        };

        const KEYPRESS_CONFIG = {
            'solo-letras': { regex: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]$/, useUpper: false, allowDelete: false },
            'solo-letras-numeros': { regex: /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9\s]$/, useUpper: false, allowDelete: false },
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

        const validarSoloLetrasNumeros = (input) => {
            const valor = input.value;
            const maximo = input.maxLength > 0 ? input.maxLength : 100;
            const minimo = 3;
            if (valor && !REGEX.soloLetrasNumeros.test(valor)) {
                input.value = valor.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑüÜ0-9\s]/g, '');
                mostrarError(input, 'Este campo solo acepta letras, números y espacios.');
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

        const _abortControllers = {};

        const _fetchWithCancel = (input, url) => {
            const key = input.name || input.id;
            if (_abortControllers[key]) _abortControllers[key].abort();
            const ac = new AbortController();
            _abortControllers[key] = ac;
            return fetch(url, { signal: ac.signal })
                .then(r => r.json())
                .then(data => {
                    if (data.exists) mostrarError(input, 'Este RIF ya está registrado en otro edificio.');
                    else limpiarError(input);
                    toggleSubmit(input.form);
                }).catch(() => { });
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
                _fetchWithCancel(input, `${checkUrl}?rif=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`);
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarCedula = (input) => {
            let valor = input.value.toUpperCase().replace(/[^VE\d.\-]/g, '');
            if (input.value !== valor) input.value = valor;
            const cleaned = valor.replace(/[.\-\s]/g, '');
            if (valor && !REGEX.cedula.test(cleaned)) {
                mostrarError(input, 'Formato: V o E + 6-14 dígitos. Ej: V-12345678');
            } else if (valor) {
                limpiarError(input);
                const excludeId = input.getAttribute('data-exclude-id') || '';
                const checkUrl = input.getAttribute('data-url') || '/api/check-cedula/';
                _fetchWithCancel(input, `${checkUrl}?cedula=${encodeURIComponent(valor)}&exclude_id=${encodeURIComponent(excludeId)}`);
            } else { limpiarError(input); }
            toggleSubmit(input.form);
        };

        const validarUsername = (input) => {
            const valor = input.value;
            const valido = /^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]+$/;
            if (valor && !valido.test(valor)) { input.value = valor.replace(/[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]/g, ''); mostrarError(input, 'Solo se permiten letras y números, sin espacios.'); }
            else if (valor && valor.length < 4) mostrarError(input, 'El nombre de usuario debe tener al menos 4 caracteres.');
            else if (valor && valor.length > 20) { input.value = valor.slice(0, 20); mostrarError(input, 'Máximo 20 caracteres.'); }
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarLoginPassword = (input) => {
            const valor = input.value;
            if (valor && valor.length > 128) { input.value = valor.slice(0, 128); mostrarError(input, 'Máximo 128 caracteres.'); }
            else limpiarError(input);
            toggleSubmit(input.form);
        };

        const validarEmail = (input) => {
            const valor = input.value;
            if (valor && valor.length > 75) { input.value = valor.slice(0, 75); mostrarError(input, 'Máximo 75 caracteres.'); toggleSubmit(input.form); return; }
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
            if (valor && valor.length < 8) mostrarError(input, 'La contraseña debe tener al menos 8 caracteres.');
            else if (valor && valor.length > 128) { input.value = valor.slice(0, 128); mostrarError(input, 'Máximo 128 caracteres.'); }
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
            'solo-letras-numeros': validarSoloLetrasNumeros,
            'solo-numeros': validarSoloNumeros,
            'rif': validarRIF,
            'cedula': validarCedula,
            'email': validarEmail,
            'password': validarPassword,
            'login-password': validarLoginPassword,
            'confirm-password': validarConfirmPassword,
            'username': validarUsername,
            'cantidad-pisos': validarCantidadPisos,
            'direccion': validarDireccion,
        };

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

        document.addEventListener('focusout', (e) => {
            const input = e.target.closest('input[data-validate]');
            if (input) {
                const tipo = input.getAttribute('data-validate');
                const validator = VALIDATORS[tipo];
                if (validator) validator(input);
            }
        });

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

        document.querySelectorAll('form').forEach((form) => {
            form.querySelectorAll('input[data-validate], select[data-validate]').forEach((input) => {
                if (input.classList.contains('input-error-state') || !input.value) return;
                input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
            });
            toggleSubmit(form);
        });
    }

    document.addEventListener('DOMContentLoaded', initFormValidation);

})(window, document);
