// Sign-in, registration and sign-out.  Names go in as text (S2); signing out
// forgets this browser's copy of the user's settings (S7).
import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';
import { el } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';

let currentUser = null;
let dialog = null;
let onChange = null;

export function getCurrentUser() {
    return currentUser;
}

export async function refreshAuthState() {
    try {
        const resp = await fetch(API_ENDPOINTS.AUTH_ME, { credentials: 'same-origin' });
        const data = resp.ok ? await resp.json() : null;
        currentUser = data?.authenticated && data.user ? data.user : null;
    } catch (_) {
        currentUser = null;
    }
    onChange?.(currentUser);
    return currentUser;
}

async function post(url, body) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await resp.json(); } catch (_) { /* empty body */ }
    return { ok: resp.ok, status: resp.status, data };
}

function field(id, label, type, autocomplete) {
    const input = el('input', { id, type, autocomplete, required: true });
    return { input, nodes: [el('label', { for: id }, label), input] };
}

function renderSignedIn() {
    const status = statusLine();
    const logout = el('button', { type: 'button', class: 'btn btn-primary' }, t('logout'));
    logout.addEventListener('click', async () => {
        try {
            const r = await post(API_ENDPOINTS.AUTH_LOGOUT);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            currentUser = null;
            settingsManager.resetLocal();
            dialog.close();
            window.location.reload();
        } catch (error) {
            console.error('Logout failed:', error);
            status.textContent = t('network_error');
        }
    });
    const actions = [logout];
    if (currentUser.is_admin) actions.push(el('a', { class: 'btn', href: '/admin' }, t('user_admin')));
    dialog.setBody(
        el('p', {}, t('signed_in_as'), ' ', el('strong', {}, currentUser.username)),
        el('div', { class: 'form-actions' }, actions),
        status);
}

function renderSignedOut(tab = 'login') {
    const status = statusLine();
    const tabs = el('div', { class: 'segmented', role: 'tablist' },
        ['login', 'register'].map((name) => el('button', {
            type: 'button', role: 'tab', class: 'seg-btn', 'aria-selected': String(name === tab),
            onclick: () => renderSignedOut(name),
        }, t(name === 'login' ? 'login' : 'register'))));

    let form;
    if (tab === 'login') {
        const id = field('auth-identifier', t('username_or_email'), 'text', 'username');
        const pw = field('auth-password', t('password'), 'password', 'current-password');
        form = el('form', { class: 'form-grid' }, id.nodes, pw.nodes,
            el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'btn btn-primary' }, t('login'))),
            status);
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            status.textContent = '';
            try {
                const r = await post(API_ENDPOINTS.AUTH_LOGIN, { identifier: id.input.value.trim(), password: pw.input.value });
                if (r.status === 429) { status.textContent = t('too_many_attempts'); return; }
                if (!r.ok || !r.data?.user) { status.textContent = t('login_failed'); return; }
                // The account's settings replace whatever this browser had.
                settingsManager.resetLocal();
                window.location.reload();
            } catch (error) {
                console.error('Login failed:', error);
                status.textContent = t('network_error');
            }
        });
        setTimeout(() => id.input.focus(), 0);
    } else {
        const user = field('auth-username', t('username'), 'text', 'username');
        user.input.setAttribute('minlength', '3');
        user.input.setAttribute('maxlength', '40');
        const pw = field('auth-new-password', t('password'), 'password', 'new-password');
        pw.input.setAttribute('minlength', '6');
        form = el('form', { class: 'form-grid' }, user.nodes, pw.nodes,
            el('p', { class: 'dialog-hint form-wide' }, t('register_hint')),
            el('div', { class: 'form-actions' }, el('button', { type: 'submit', class: 'btn btn-primary' }, t('register'))),
            status);
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            status.textContent = '';
            // The API wants an e-mail address; registration here asks only for a name.
            const email = `user+${Date.now().toString(36)}${Math.random().toString(36).slice(2)}@example.com`;
            try {
                const r = await post(API_ENDPOINTS.AUTH_REGISTER, { email, username: user.input.value.trim(), password: pw.input.value });
                if (r.status === 429) { status.textContent = t('too_many_attempts'); return; }
                if (!r.ok || !r.data?.user) {
                    status.textContent = typeof r.data?.detail === 'string' && r.status === 400 ? t('register_failed_name') : t('register_failed');
                    return;
                }
                // The new account starts with this browser's current settings.
                settingsManager.authenticatedUserId = r.data.user.id;
                await settingsManager.saveUserSettingsToServer();
                window.location.reload();
            } catch (error) {
                console.error('Registration failed:', error);
                status.textContent = t('network_error');
            }
        });
        setTimeout(() => user.input.focus(), 0);
    }
    dialog.setBody(tabs, form);
}

export function openAuthDialog() {
    if (!dialog) dialog = new AppDialog('auth-dialog');
    dialog.setTitle(currentUser ? t('account') : t('login_register'));
    if (currentUser) renderSignedIn();
    else renderSignedOut();
    dialog.open();
}

/** @param {(user|null) => void} changed  called whenever the signed-in user is known */
export async function initAuth(changed) {
    onChange = changed;
    return refreshAuthState();
}
