import { API_ENDPOINTS } from './constants.js';
import { settingsManager } from './settings.js';

let currentUser = null;

function loadCSSFile(url) {
    try {
        const links = document.getElementsByTagName('link');
        for (let i = 0; i < links.length; i++) {
            if (links[i].href.includes(url)) {
                return;
            }
        }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.type = 'text/css';
        link.href = url;
        document.head.appendChild(link);
    } catch (_) { /* noop */ }
}

function updateAuthButton() {
    const btn = document.getElementById('auth-btn');
    if (!btn) return;
    if (currentUser && currentUser.username) {
        btn.textContent = '👤';
        btn.title = `Account: ${currentUser.username}`;
    } else {
        btn.textContent = '👤';
        btn.title = 'Login / Registrieren';
    }
}

async function refreshAuthState() {
    try {
        const resp = await fetch(`${API_ENDPOINTS.AUTH_ME}?nocache=1`, {
            credentials: 'same-origin'
        });
        if (!resp.ok) {
            currentUser = null;
        } else {
            const data = await resp.json();
            if (data && data.authenticated && data.user) {
                currentUser = data.user;
            } else {
                currentUser = null;
            }
        }
    } catch (_) {
        currentUser = null;
    }
    updateAuthButton();
}

function closeAuthDialog() {
    const overlay = document.querySelector('.auth-dialog-overlay');
    if (overlay) overlay.remove();
}

async function performLogout() {
    try {
        const resp = await fetch(API_ENDPOINTS.AUTH_LOGOUT, {
            method: 'POST',
            credentials: 'same-origin'
        });
        if (resp.ok) {
            currentUser = null;
            updateAuthButton();
            closeAuthDialog();
            try {
                if (settingsManager) {
                    settingsManager.authenticatedUserId = null;
                }
            } catch (_) { /* noop */ }
        }
    } catch (e) {
        console.error('Logout failed:', e);
    }
}

function showError(message) {
    const el = document.getElementById('auth-error');
    if (!el) return;
    el.textContent = message || '';
}

async function performLogin() {
    const idInput = document.getElementById('auth-login-identifier');
    const pwInput = document.getElementById('auth-login-password');
    if (!idInput || !pwInput) return;
    const identifier = idInput.value.trim();
    const password = pwInput.value;
    if (!identifier || !password) {
        showError('Bitte Benutzername/E-Mail und Passwort eingeben.');
        return;
    }
    showError('');
    try {
        const resp = await fetch(API_ENDPOINTS.AUTH_LOGIN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ identifier, password })
        });
        if (!resp.ok) {
            showError('Login fehlgeschlagen. Bitte prüfen Sie Ihre Eingaben.');
            return;
        }
        const data = await resp.json();
        if (data && data.user) {
            currentUser = data.user;
            updateAuthButton();
            closeAuthDialog();
            try {
                if (settingsManager && typeof settingsManager.loadUserSettingsFromServer === 'function') {
                    await settingsManager.loadUserSettingsFromServer();
                }
            } catch (e) {
                console.error('Error refreshing settings after login:', e);
            }
            try {
                window.location.reload();
            } catch (_) { /* noop */ }
        }
    } catch (e) {
        console.error('Login failed:', e);
        showError('Login fehlgeschlagen (Netzwerkfehler).');
    }
}

async function performRegister() {
    const emailInput = document.getElementById('auth-register-email');
    const userInput = document.getElementById('auth-register-username');
    const pwInput = document.getElementById('auth-register-password');
    if (!emailInput || !userInput || !pwInput) return;
    const email = emailInput.value.trim();
    const username = userInput.value.trim();
    const password = pwInput.value;
    if (!email || !username || !password) {
        showError('Bitte E-Mail, Benutzername und Passwort eingeben.');
        return;
    }
    showError('');
    try {
        const resp = await fetch(API_ENDPOINTS.AUTH_REGISTER, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ email, username, password })
        });
        if (!resp.ok) {
            showError('Registrierung fehlgeschlagen. E-Mail oder Benutzername bereits vergeben?');
            return;
        }
        const data = await resp.json();
        if (data && data.user) {
            currentUser = data.user;
            updateAuthButton();
            closeAuthDialog();
            try {
                if (settingsManager && typeof settingsManager.loadUserSettingsFromServer === 'function') {
                    await settingsManager.loadUserSettingsFromServer();
                }
            } catch (e) {
                console.error('Error refreshing settings after registration:', e);
            }
            try {
                window.location.reload();
            } catch (_) { /* noop */ }
        }
    } catch (e) {
        console.error('Registration failed:', e);
        showError('Registrierung fehlgeschlagen (Netzwerkfehler).');
    }
}

function openAuthDialog() {
    closeAuthDialog();
    loadCSSFile('./static/css/dialogStyles.css');

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay auth-dialog-overlay';

    const loggedIn = !!(currentUser && currentUser.username);

    if (loggedIn) {
        overlay.innerHTML = `
            <div class="location-dialog auth-dialog">
                <button class="dialog-close" type="button">×</button>
                <h3 class="auth-dialog-title">Account</h3>
                <p>Angemeldet als <strong>${currentUser.username}</strong> (${currentUser.email})</p>
                <div id="auth-error" class="auth-error"></div>
                <button id="auth-logout-btn" type="button" class="sim-time-btn auth-logout-btn">Logout</button>
            </div>
        `;
    } else {
        overlay.innerHTML = `
            <div class="location-dialog auth-dialog">
                <button class="dialog-close" type="button">×</button>
                <h3 class="auth-dialog-title">Login / Registrieren</h3>
                <div class="auth-tabs">
                    <button type="button" id="auth-tab-login" class="sim-time-btn auth-tab-btn">Login</button>
                    <button type="button" id="auth-tab-register" class="sim-time-btn auth-tab-btn">Registrieren</button>
                </div>
                <div id="auth-error" class="auth-error"></div>
                <div id="auth-login-panel" class="auth-panel active">
                    <label class="auth-field-label">
                        Benutzername oder E-Mail<br>
                        <input id="auth-login-identifier" type="text" class="auth-field-input">
                    </label>
                    <label class="auth-field-label">
                        Passwort<br>
                        <input id="auth-login-password" type="password" class="auth-field-input">
                    </label>
                    <button id="auth-login-submit" type="button" class="sim-time-btn auth-primary-btn">Login</button>
                </div>
                <div id="auth-register-panel" class="auth-panel hidden">
                    <label class="auth-field-label">
                        E-Mail<br>
                        <input id="auth-register-email" type="email" class="auth-field-input">
                    </label>
                    <label class="auth-field-label">
                        Benutzername<br>
                        <input id="auth-register-username" type="text" class="auth-field-input">
                    </label>
                    <label class="auth-field-label">
                        Passwort<br>
                        <input id="auth-register-password" type="password" class="auth-field-input">
                    </label>
                    <button id="auth-register-submit" type="button" class="sim-time-btn auth-primary-btn">Registrieren</button>
                </div>
            </div>
        `;
    }

    document.body.appendChild(overlay);

    const closeBtn = overlay.querySelector('.dialog-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => closeAuthDialog());
    }

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeAuthDialog();
        }
    });

    if (loggedIn) {
        const logoutBtn = document.getElementById('auth-logout-btn');
        if (logoutBtn) logoutBtn.addEventListener('click', () => { performLogout(); });
        return;
    }

    const tabLogin = document.getElementById('auth-tab-login');
    const tabRegister = document.getElementById('auth-tab-register');
    const panelLogin = document.getElementById('auth-login-panel');
    const panelRegister = document.getElementById('auth-register-panel');

    if (tabLogin && tabRegister && panelLogin && panelRegister) {
        tabLogin.addEventListener('click', () => {
            panelLogin.classList.add('active');
            panelLogin.classList.remove('hidden');
            panelRegister.classList.remove('active');
            panelRegister.classList.add('hidden');
            showError('');
        });
        tabRegister.addEventListener('click', () => {
            panelLogin.classList.remove('active');
            panelLogin.classList.add('hidden');
            panelRegister.classList.add('active');
            panelRegister.classList.remove('hidden');
            showError('');
        });
    }

    const loginBtn = document.getElementById('auth-login-submit');
    if (loginBtn) loginBtn.addEventListener('click', () => { performLogin(); });

    const regBtn = document.getElementById('auth-register-submit');
    if (regBtn) regBtn.addEventListener('click', () => { performRegister(); });

    // Initial focus: Benutzername/E-Mail im Login-Panel
    try {
        const identifierInput = document.getElementById('auth-login-identifier');
        if (identifierInput && typeof identifierInput.focus === 'function') {
            identifierInput.focus();
            if (typeof identifierInput.select === 'function') {
                identifierInput.select();
            }
        }
    } catch (_) { /* noop */ }
}

function setupAuthButton() {
    const btn = document.getElementById('auth-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
        openAuthDialog();
    });
}

export async function initAuthUI() {
    await refreshAuthState();
    setupAuthButton();
}
