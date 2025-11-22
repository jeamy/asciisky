import { API_ENDPOINTS } from './constants.js';

function showAdminError(message) {
    const el = document.getElementById('admin-error');
    if (!el) return;
    el.textContent = message || '';
}

async function fetchUsers() {
    try {
        const resp = await fetch(`${API_ENDPOINTS.ADMIN_USERS}?limit=200`, {
            credentials: 'same-origin'
        });
        if (resp.status === 401 || resp.status === 403) {
            window.location.href = '/';
            return [];
        }
        if (!resp.ok) {
            showAdminError('Fehler beim Laden der Benutzer.');
            return [];
        }
        const data = await resp.json();
        return data && Array.isArray(data.users) ? data.users : [];
    } catch (e) {
        console.error('Failed to load users:', e);
        showAdminError('Netzwerkfehler beim Laden der Benutzer.');
        return [];
    }
}

async function patchUser(userId, payload) {
    try {
        const resp = await fetch(`${API_ENDPOINTS.ADMIN_USERS}/${userId}`, {
            method: 'PATCH',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (resp.status === 401 || resp.status === 403) {
            window.location.href = '/';
            return null;
        }
        if (!resp.ok) {
            showAdminError('Fehler beim Aktualisieren des Benutzers.');
            return null;
        }
        const data = await resp.json();
        return data && data.user ? data.user : null;
    } catch (e) {
        console.error('Failed to update user:', e);
        showAdminError('Netzwerkfehler beim Aktualisieren des Benutzers.');
        return null;
    }
}

async function deleteUser(userId) {
    try {
        const resp = await fetch(`${API_ENDPOINTS.ADMIN_USERS}/${userId}`, {
            method: 'DELETE',
            credentials: 'same-origin'
        });
        if (resp.status === 401 || resp.status === 403) {
            window.location.href = '/';
            return null;
        }
        if (!resp.ok) {
            showAdminError('Fehler beim endgültigen Löschen des Benutzers.');
            return false;
        }
        const data = await resp.json();
        return !!(data && data.deleted);
    } catch (e) {
        console.error('Failed to delete user:', e);
        showAdminError('Netzwerkfehler beim endgültigen Löschen des Benutzers.');
        return false;
    }
}

function renderUsers(users) {
    const tbody = document.getElementById('admin-users-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    users.forEach((u) => {
        const tr = document.createElement('tr');

        const tdId = document.createElement('td');
        tdId.textContent = String(u.id);
        tr.appendChild(tdId);

        const tdUser = document.createElement('td');
        tdUser.textContent = u.username;
        tr.appendChild(tdUser);

        const tdEmail = document.createElement('td');
        tdEmail.textContent = u.email;
        tr.appendChild(tdEmail);

        const tdRole = document.createElement('td');
        tdRole.textContent = u.is_admin ? 'Admin' : 'User';
        tr.appendChild(tdRole);

        const tdStatus = document.createElement('td');
        tdStatus.textContent = u.is_active ? 'aktiv' : 'inaktiv';
        tr.appendChild(tdStatus);

        const tdActions = document.createElement('td');

        const btnToggleAdmin = document.createElement('button');
        btnToggleAdmin.textContent = u.is_admin ? 'Admin entziehen' : 'Admin vergeben';
        btnToggleAdmin.className = 'admin-action-btn';
        btnToggleAdmin.addEventListener('click', async () => {
            showAdminError('');
            const updated = await patchUser(u.id, { is_admin: !u.is_admin });
            if (updated) {
                await loadAndRenderUsers();
            }
        });
        tdActions.appendChild(btnToggleAdmin);

        const btnPassword = document.createElement('button');
        btnPassword.textContent = 'Passwort setzen';
        btnPassword.className = 'admin-action-btn';
        btnPassword.addEventListener('click', async () => {
            showAdminError('');
            const pw = window.prompt(`Neues Passwort für ${u.username}:`);
            if (!pw) return;
            if (pw.length < 6) {
                showAdminError('Passwort zu kurz (mind. 6 Zeichen).');
                return;
            }
            const updated = await patchUser(u.id, { password: pw });
            if (updated) {
                await loadAndRenderUsers();
            }
        });
        tdActions.appendChild(btnPassword);

        const btnActive = document.createElement('button');
        btnActive.textContent = u.is_active ? 'Inaktiv setzen' : 'Reaktivieren';
        btnActive.className = 'admin-action-btn';
        btnActive.addEventListener('click', async () => {
            showAdminError('');
            const payload = { is_active: !u.is_active };
            const updated = await patchUser(u.id, payload);
            if (updated) {
                await loadAndRenderUsers();
            }
        });
        tdActions.appendChild(btnActive);

        const btnDelete = document.createElement('button');
        btnDelete.textContent = 'Benutzer entfernen';
        btnDelete.className = 'admin-action-btn';
        btnDelete.addEventListener('click', async () => {
            showAdminError('');
            const ok = window.confirm(`Benutzer ${u.username} wirklich endgültig löschen? Diese Aktion kann nicht rückgängig gemacht werden.`);
            if (!ok) return;
            const deleted = await deleteUser(u.id);
            if (deleted) {
                await loadAndRenderUsers();
            }
        });
        tdActions.appendChild(btnDelete);

        tr.appendChild(tdActions);
        tbody.appendChild(tr);
    });
}

async function loadAndRenderUsers() {
    showAdminError('');
    const users = await fetchUsers();
    renderUsers(users);
}

document.addEventListener('DOMContentLoaded', () => {
    loadAndRenderUsers();
});
