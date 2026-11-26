// Brightness limits for asteroids and comets.  The workers cache small bodies
// down to magnitude 20, so a new limit applies at once (no recomputation).
import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { el } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';
import { fmtNumber } from './ui/format.js';

export const DEFAULT_FILTERS = { asteroidMaxMagnitude: 10, cometMaxMagnitude: 14 };

export async function fetchFilters() {
    try {
        const resp = await fetch(API_ENDPOINTS.FILTERS, { credentials: 'same-origin' });
        const data = resp.ok ? await resp.json() : null;
        if (data?.success && data.filters) return { ...DEFAULT_FILTERS, ...data.filters };
    } catch (error) {
        console.warn('Could not load magnitude filters:', error);
    }
    return { ...DEFAULT_FILTERS };
}

export class MagnitudeFilterDialog {
    /** @param {(filters) => void} onApplied */
    constructor(onApplied) {
        this.onApplied = onApplied;
        this.dialog = new AppDialog('filter-dialog');
    }

    /** Built on every open, so a language change shows (L28). */
    async open() {
        this.dialog.setTitle(t('magnitude_filters'));
        const status = statusLine();
        status.textContent = t('loading');
        this.dialog.setBody(status);
        this.dialog.open();
        const filters = await fetchFilters();

        const slider = (id, label, value) => {
            const out = el('output', { for: id }, fmtNumber(value));
            const input = el('input', { type: 'range', id, min: 10, max: 20, step: 0.5, value });
            input.addEventListener('input', () => { out.textContent = fmtNumber(Number(input.value)); });
            return { input, row: el('div', { class: 'slider-row' }, el('label', { for: id }, label), input, out) };
        };
        const ast = slider('filter-asteroids', t('asteroid_magnitude_label'), filters.asteroidMaxMagnitude);
        const com = slider('filter-comets', t('comet_magnitude_label'), filters.cometMaxMagnitude);
        const form = el('form', { class: 'filter-form' },
            el('p', { class: 'dialog-hint' }, t('magnitude_filter_info')),
            ast.row, com.row,
            el('div', { class: 'form-actions' },
                el('button', { type: 'button', class: 'btn', onclick: () => this.dialog.close() }, t('cancel')),
                el('button', { type: 'submit', class: 'btn btn-primary' }, t('apply'))),
            status);
        status.textContent = '';
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const next = {
                asteroidMaxMagnitude: Number(ast.input.value),
                cometMaxMagnitude: Number(com.input.value),
            };
            try {
                const resp = await fetch(API_ENDPOINTS.FILTERS, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify(next),
                });
                const data = resp.ok ? await resp.json() : null;
                if (!data?.success) throw new Error(`HTTP ${resp.status}`);
                this.dialog.close();
                this.onApplied?.({ ...next, ...(data.filters || {}) });
            } catch (error) {
                console.error('Applying filters failed:', error);
                status.textContent = t('error_applying_filters');
            }
        });
        this.dialog.setBody(form);
    }
}
