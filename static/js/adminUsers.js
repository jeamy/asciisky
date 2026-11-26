// User administration (/admin).  Passwords are entered in a dialog with a
// password field, never in window.prompt (S8); all names go in as text.
import { API_ENDPOINTS, THEMES } from './constants.js';
import { el } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';

const DETAIL_TEXT = {
    'You cannot remove your own admin access': 'Die eigenen Admin-Rechte können nicht entzogen werden.',
    'The last active admin cannot be removed': 'Der letzte aktive Admin kann nicht entfernt, deaktiviert oder herabgestuft werden.',
    'Password too short': 'Passwort zu kurz (mindestens 6 Zeichen).',
};

function showError(message) {
    document.getElementById('admin-error').textContent = message || '';
}

async function request(method, path = '', body = undefined) {
    const resp = await fetch(`${API_ENDPOINTS.ADMIN_USERS}${path}`, {
        method,
        credentials: 'same-origin',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
    });
    if (resp.status === 401 || resp.status === 403) {
        window.location.href = '/';
        return null;
    }
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
        const detail = typeof data?.detail === 'string' ? data.detail : '';
        throw new Error(DETAIL_TEXT[detail] || detail || `HTTP ${resp.status}`);
    }
    return data;
}

async function run(action) {
    showError('');
    try {
        await action();
        await load();
    } catch (error) {
        console.error(error);
        showError(error.message || 'Netzwerkfehler.');
    }
}

let passwordDialog = null;

function askPassword(user) {
    if (!passwordDialog) passwordDialog = new AppDialog('password-dialog');
    passwordDialog.setTitle(`Neues Passwort für ${user.username}`);
    const input = el('input', { type: 'password', id: 'new-password', autocomplete: 'new-password', minlength: 6, required: true });
    const status = statusLine();
    const form = el('form', { class: 'form-grid' },
        el('label', { for: 'new-password' }, 'Passwort'), input,
        el('div', { class: 'form-actions' },
            el('button', { type: 'button', class: 'btn', onclick: () => passwordDialog.close() }, 'Abbrechen'),
            el('button', { type: 'submit', class: 'btn btn-primary' }, 'Setzen')),
        status);
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (input.value.length < 6) {
            status.textContent = DETAIL_TEXT['Password too short'];
            return;
        }
        try {
            await request('PATCH', `/${user.id}`, { password: input.value });
            passwordDialog.close();
            await load();
        } catch (error) {
            status.textContent = error.message;
        }
    });
    passwordDialog.setBody(form);
    passwordDialog.open();
    input.focus();
}

function render(users) {
    const rows = users.map((u) => el('tr', {},
        el('td', {}, String(u.id)),
        el('td', {}, u.username),
        el('td', {}, u.email),
        el('td', {}, u.is_admin ? 'Admin' : 'Benutzer'),
        el('td', {}, u.is_active ? 'aktiv' : 'inaktiv'),
        el('td', {}, el('div', { class: 'admin-actions' },
            el('button', { type: 'button', class: 'btn btn-small', onclick: () => run(() => request('PATCH', `/${u.id}`, { is_admin: !u.is_admin })) },
                u.is_admin ? 'Admin entziehen' : 'Admin vergeben'),
            el('button', { type: 'button', class: 'btn btn-small', onclick: () => { showError(''); askPassword(u); } }, 'Passwort setzen'),
            el('button', { type: 'button', class: 'btn btn-small', onclick: () => run(() => request('PATCH', `/${u.id}`, { is_active: !u.is_active })) },
                u.is_active ? 'Deaktivieren' : 'Reaktivieren'),
            el('button', {
                type: 'button', class: 'btn btn-small',
                onclick: () => {
                    if (!window.confirm(`Benutzer ${u.username} endgültig löschen? Das kann nicht rückgängig gemacht werden.`)) return;
                    run(() => request('DELETE', `/${u.id}`));
                },
            }, 'Löschen')))));
    document.getElementById('admin-users-body').replaceChildren(...rows);
}

async function load() {
    const data = await request('GET', '?limit=200');
    if (data) render(Array.isArray(data.users) ? data.users : []);
}

// The admin page follows the theme chosen on the main page.
try {
    const s = JSON.parse(localStorage.getItem('asciisky_settings') || 'null');
    if (s && THEMES.includes(s.theme)) document.documentElement.dataset.theme = s.theme;
} catch (_) { /* storage unavailable */ }

document.addEventListener('DOMContentLoaded', () => {
    load().catch((error) => showError(`Fehler beim Laden der Benutzer: ${error.message}`));
});
