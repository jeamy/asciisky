// Location dialog: place search (Nominatim), elevation (Open-Meteo) and
// manual coordinates.  Search results are third-party text and go in as text
// nodes only (S3).
import { API_ENDPOINTS, DEFAULT_LOCATION } from './constants.js';
import { t } from './i18n.js';
import { el } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';

const MAX_RESULTS = 5;

async function fetchElevation(lat, lon, signal) {
    try {
        const params = new URLSearchParams({ latitude: String(lat), longitude: String(lon) });
        const resp = await fetch(`${API_ENDPOINTS.ELEVATION}?${params}`, { signal });
        if (!resp.ok) return null;
        const value = (await resp.json())?.elevation?.[0];
        return Number.isFinite(value) ? Math.round(value) : null;
    } catch (_) {
        return null;
    }
}

export class LocationDialog {
    /** @param {(loc: {latitude, longitude, elevation, name}) => void} onApply */
    constructor(onApply) {
        this.onApply = onApply;
        this.dialog = new AppDialog('location-dialog');
        this.dialog.onClose = () => this._abort();
        this._controller = null;
    }

    _abort() {
        this._controller?.abort();
        this._controller = null;
    }

    _signal() {
        this._abort();
        this._controller = new AbortController();
        return this._controller.signal;
    }

    open(current) {
        const loc = current || DEFAULT_LOCATION;
        this.dialog.setTitle(t('location_settings'));

        this.searchInput = el('input', { type: 'search', id: 'loc-search', autocomplete: 'off', placeholder: t('search_location'), 'aria-label': t('search_location') });
        const searchForm = el('form', { class: 'field-row', role: 'search' },
            this.searchInput,
            el('button', { type: 'submit', class: 'btn' }, t('search')));
        searchForm.addEventListener('submit', (e) => { e.preventDefault(); this._search(); });
        this.results = el('ul', { class: 'result-list', 'aria-label': t('search_results') });
        this.searchStatus = statusLine();

        this.latInput = el('input', { type: 'number', id: 'loc-lat', step: 'any', min: -90, max: 90, required: true, value: loc.latitude });
        this.lonInput = el('input', { type: 'number', id: 'loc-lon', step: 'any', min: -180, max: 180, required: true, value: loc.longitude });
        this.elevInput = el('input', { type: 'number', id: 'loc-elev', step: '1', value: Number.isFinite(loc.elevation) ? loc.elevation : '' });
        this.nameInput = el('input', { type: 'text', id: 'loc-name', maxlength: 80, value: loc.name || '' });
        this.formStatus = statusLine();
        const form = el('form', { class: 'form-grid' },
            el('label', { for: 'loc-lat' }, t('latitude')), this.latInput,
            el('label', { for: 'loc-lon' }, t('longitude')), this.lonInput,
            el('label', { for: 'loc-elev' }, t('elevation')), this.elevInput,
            el('label', { for: 'loc-name' }, t('location_name')), this.nameInput,
            el('div', { class: 'form-actions' },
                el('button', { type: 'button', class: 'btn', onclick: () => this._fillElevation() }, t('fetch_elevation')),
                el('button', { type: 'submit', class: 'btn btn-primary' }, t('apply'))),
            this.formStatus);
        form.addEventListener('submit', (e) => { e.preventDefault(); this._apply(); });

        this.dialog.setBody(
            el('p', { class: 'dialog-hint' }, `${t('current_location')}: ${loc.name || '—'} (${Number(loc.latitude).toFixed(4)}, ${Number(loc.longitude).toFixed(4)})`),
            el('h3', {}, t('search')), searchForm, this.searchStatus, this.results,
            el('h3', {}, t('manual_coordinates')), form);
        this.dialog.open();
        this.searchInput.focus();
    }

    async _search() {
        const q = this.searchInput.value.trim();
        if (!q) return;
        const signal = this._signal();
        this.results.replaceChildren();
        this.searchStatus.textContent = `${t('searching')}…`;
        try {
            const params = new URLSearchParams({ format: 'json', q, limit: String(MAX_RESULTS) });
            const resp = await fetch(`${API_ENDPOINTS.GEOCODE}?${params}`, { signal, headers: { Accept: 'application/json' } });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (signal.aborted) return;
            const list = Array.isArray(data) ? data.slice(0, MAX_RESULTS) : [];
            this.searchStatus.textContent = list.length ? '' : t('no_results_found');
            this.results.replaceChildren(...list.map((r) => this._resultItem(r)));
        } catch (error) {
            if (error?.name === 'AbortError') return;
            console.error('Location search failed:', error);
            this.searchStatus.textContent = t('search_error');
        }
    }

    _resultItem(result) {
        const lat = Number.parseFloat(result.lat);
        const lon = Number.parseFloat(result.lon);
        const title = String(result.display_name || '');
        const button = el('button', { type: 'button', class: 'result-item' },
            el('span', { class: 'result-name' }, title),
            el('span', { class: 'result-coords' }, `${lat.toFixed(4)}, ${lon.toFixed(4)}`));
        button.addEventListener('click', () => this._pick({ lat, lon, name: title.split(',')[0].trim() }));
        return el('li', {}, button);
    }

    /** A result fills the form; its elevation is fetched once, then it is applied (L29). */
    async _pick({ lat, lon, name }) {
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        this.latInput.value = lat;
        this.lonInput.value = lon;
        this.nameInput.value = name;
        this.elevInput.value = '';
        this.formStatus.textContent = t('fetching_elevation');
        const signal = this._signal();
        const elevation = await fetchElevation(lat, lon, signal);
        if (signal.aborted || !this.dialog.isOpen) return;
        this.elevInput.value = elevation ?? '';
        this.formStatus.textContent = elevation == null ? t('elevation_not_available') : '';
        this._apply();
    }

    async _fillElevation() {
        const lat = Number.parseFloat(this.latInput.value);
        const lon = Number.parseFloat(this.lonInput.value);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
            this.formStatus.textContent = t('invalid_coordinates');
            return;
        }
        this.formStatus.textContent = t('fetching_elevation');
        const signal = this._signal();
        const elevation = await fetchElevation(lat, lon, signal);
        if (signal.aborted || !this.dialog.isOpen) return;
        if (elevation == null) {
            this.formStatus.textContent = t('elevation_not_available');
        } else {
            this.elevInput.value = elevation;
            this.formStatus.textContent = '';
        }
    }

    _apply() {
        const lat = Number.parseFloat(this.latInput.value);
        const lon = Number.parseFloat(this.lonInput.value);
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            this.formStatus.textContent = t('invalid_coordinates');
            return;
        }
        const elev = Number.parseFloat(this.elevInput.value);
        const name = this.nameInput.value.trim() || t('custom_location');
        this.dialog.close();
        this.onApply({ latitude: lat, longitude: lon, elevation: Number.isFinite(elev) ? elev : 0, name });
    }
}
