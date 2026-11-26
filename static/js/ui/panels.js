// The object list (left column, or bottom sheet on phones) and the detail
// panel (right column, or a sheet over the list).
import { PLANETS } from '../constants.js';
import { t } from '../i18n.js';
import { listSymbol } from '../skyGrid.js';
import { el } from './dom.js';
import { displayName, fmtClock, fmtDegrees, fmtNumber } from './format.js';

const byMagnitude = (a, b) => (Number.isFinite(a.magnitude) ? a.magnitude : 99) - (Number.isFinite(b.magnitude) ? b.magnitude : 99);

export class ObjectList {
    /**
     * @param {HTMLElement} root  the list panel
     * @param {object} opts  onPick(body), onFilters()
     */
    constructor(root, opts) {
        this.root = root;
        this.opts = opts;
        this.bodies = {};
        this.filters = null;
        this.selectedName = null;
        this.titleEl = el('h2', { class: 'panel-title', id: 'list-title' });
        this.filterBtn = el('button', { type: 'button', class: 'icon-btn', onclick: () => opts.onFilters() }, '⚙');
        this.grip = el('button', { type: 'button', class: 'sheet-grip', 'aria-controls': root.id, onclick: () => this.cycleSheet() });
        this.body = el('div', { class: 'panel-body' });
        root.replaceChildren(this.grip, el('header', { class: 'panel-head' }, this.titleEl, this.filterBtn), this.body);
        root.dataset.sheet = 'peek';
    }

    /** Phones: peek -> half -> full -> peek. */
    cycleSheet() {
        const order = ['peek', 'half', 'full'];
        const next = order[(order.indexOf(this.root.dataset.sheet) + 1) % order.length];
        this.setSheet(next);
    }

    setSheet(state) {
        this.root.dataset.sheet = state;
        this.grip.setAttribute('aria-expanded', String(state !== 'peek'));
    }

    update({ bodies = this.bodies, filters = this.filters, selectedName = this.selectedName } = {}) {
        this.bodies = bodies;
        this.filters = filters;
        this.selectedName = selectedName;
        this.render();
    }

    render() {
        const all = Object.values(this.bodies || {});
        const byName = new Map(all.map((b) => [String(b.name).toLowerCase(), b]));
        const main = ['sun', 'moon', ...PLANETS].map((n) => byName.get(n)).filter(Boolean);
        const asteroids = all.filter((b) => b.type === 'asteroid' && b.altitude > 0).sort(byMagnitude);
        const comets = all.filter((b) => b.type === 'comet' && b.altitude > 0).sort(byMagnitude);
        const up = main.filter((b) => b.altitude > 0).length + asteroids.length + comets.length;

        this.titleEl.textContent = `${t('visible_objects')} (${up})`;
        this.filterBtn.title = t('magnitude_filters');
        this.filterBtn.setAttribute('aria-label', t('magnitude_filters'));
        this.grip.setAttribute('aria-label', t('toggle_list'));

        if (!all.length) {
            this.body.replaceChildren(el('p', { class: 'muted' }, t('loading')));
            return;
        }
        const section = (title, rows, empty) => el('section', { class: 'list-section' },
            el('h3', { class: 'list-heading' }, title),
            rows.length ? el('ul', { class: 'object-list' }, rows) : el('p', { class: 'muted' }, empty));

        const aMax = this.filters?.asteroidMaxMagnitude;
        const cMax = this.filters?.cometMaxMagnitude;
        this.body.replaceChildren(
            section(t('sun_moon_planets'), main.map((b) => this._row(b, fmtDegrees(b.altitude, 0))), t('no_data')),
            section(aMax != null ? `${t('asteroids')} ≤ ${fmtNumber(aMax)}` : t('asteroids'),
                asteroids.map((b) => this._row(b, fmtNumber(b.magnitude))), t('none_above_horizon')),
            section(cMax != null ? `${t('comets')} ≤ ${fmtNumber(cMax)}` : t('comets'),
                comets.map((b) => this._row(b, fmtNumber(b.magnitude))), t('none_above_horizon')));
    }

    _row(body, value) {
        const below = !(body.altitude > 0);
        const btn = el('button', {
            type: 'button', class: `object-row${below ? ' below' : ''}`,
            'aria-pressed': String(body.name === this.selectedName),
            title: below ? t('below_horizon') : null,
        },
        el('span', { class: 'obj-symbol', 'aria-hidden': 'true' }, listSymbol(body)),
        el('span', { class: 'obj-name' }, displayName(body.name)),
        el('span', { class: 'obj-value' }, value));
        btn.addEventListener('click', () => this.opts.onPick(body));
        return el('li', {}, btn);
    }
}

export class DetailPanel {
    /**
     * @param {HTMLElement} root
     * @param {object} opts  onClose(), onPick(hit)
     */
    constructor(root, opts) {
        this.root = root;
        this.opts = opts;
        this.closeBtn = el('button', { type: 'button', class: 'icon-btn', onclick: () => opts.onClose() }, '×');
        this.titleEl = el('h2', { class: 'panel-title', id: 'detail-title' });
        this.body = el('div', { class: 'panel-body' });
        root.replaceChildren(el('header', { class: 'panel-head' }, this.titleEl, this.closeBtn), this.body);
        root.setAttribute('aria-labelledby', 'detail-title');
        this.hide();
    }

    hide() {
        this.root.hidden = true;
        document.body.classList.remove('has-detail');
    }

    _show() {
        this.closeBtn.setAttribute('aria-label', t('close_label'));
        this.closeBtn.title = t('close_label');
        this.root.hidden = false;
        document.body.classList.add('has-detail');
    }

    /** Several objects under the pointer: let the user pick one. */
    showChoice(hits) {
        this.titleEl.textContent = t('multiple_objects_found');
        this.body.replaceChildren(el('ul', { class: 'object-list' }, hits.map((hit) => {
            const obj = hit.obj;
            const btn = el('button', { type: 'button', class: 'object-row' },
                el('span', { class: 'obj-symbol', 'aria-hidden': 'true' }, hit.kind === 'messier' ? '✧' : listSymbol(obj)),
                el('span', { class: 'obj-name' }, hit.kind === 'messier' ? messierTitle(obj) : displayName(obj.name)),
                el('span', { class: 'obj-value' }, fmtDegrees(obj.altitude, 0)));
            btn.addEventListener('click', () => this.opts.onPick(hit));
            return el('li', {}, btn);
        })));
        this._show();
    }

    /** One object; ``kind`` is 'body' or 'messier'. */
    showObject(kind, obj, timeZone) {
        const isMessier = kind === 'messier';
        this.titleEl.replaceChildren(
            el('span', { class: 'obj-symbol', 'aria-hidden': 'true' }, isMessier ? '✧' : listSymbol(obj)), ' ',
            isMessier ? messierTitle(obj) : displayName(obj.name));
        const rows = [
            [t('altitude'), fmtDegrees(obj.altitude)],
            [t('azimuth'), fmtDegrees(obj.azimuth)],
        ];
        if (!isMessier && Number.isFinite(obj.distance)) rows.push([t('distance'), `${fmtNumber(obj.distance, 3)} ${t('au')}`]);
        if (obj.rise_time) rows.push([t('rise_time'), fmtClock(obj.rise_time, timeZone)]);
        if (obj.transit_time) rows.push([t('transit_time'), fmtClock(obj.transit_time, timeZone)]);
        if (obj.set_time) rows.push([t('set_time'), fmtClock(obj.set_time, timeZone)]);
        if (typeof obj.phase === 'number') {
            rows.push([t('phase'), `${fmtNumber(obj.phase * 100)} %${obj.phase_name ? ` · ${t(obj.phase_name)}` : ''}`]);
        }
        if (Number.isFinite(obj.magnitude)) rows.push([t('magnitude'), fmtNumber(obj.magnitude)]);
        if (isMessier && obj.type) rows.push([t('object_type'), String(obj.type)]);
        if (isMessier && obj.constellation) rows.push([t('constellation'), t(obj.constellation)]);
        if (!(obj.altitude > 0)) rows.push(['', t('below_horizon')]);
        this.body.replaceChildren(el('dl', { class: 'detail-list' }, rows.map(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])));
        this._show();
    }
}

function messierTitle(obj) {
    const id = obj.id || '';
    const name = obj.name && obj.name !== id ? ` ${obj.name}` : '';
    return `${id}${name}`.trim() || 'Messier';
}
