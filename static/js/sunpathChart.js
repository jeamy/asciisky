// Yearly sunrise, transit and sunset curve with twilight bands, in a dialog.
import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { el, svgEl } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';
import { locale } from './ui/format.js';

const SUNPATH_SCHEMA_VERSION = 6; // SUNPATH_VERSION in api/computation.py
const cache = new Map();

const pad2 = (v) => String(v).padStart(2, '0');

/** 'YYYY-MM-DD' as a local calendar date (new Date('YYYY-MM-DD') would be UTC, L30). */
function parseDay(text) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(text || ''));
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

/** Clock time of a local ISO string, without converting time zones. */
function isoClock(iso) {
    const m = /T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(String(iso || ''));
    if (!m) return null;
    const hours = Number(m[1]) + Number(m[2]) / 60 + Number(m[3] || 0) / 3600;
    return { hours, text: `${m[1]}:${m[2]}` };
}

function hoursText(h) {
    if (!Number.isFinite(h)) return '—';
    const v = ((h % 24) + 24) % 24;
    const hh = Math.floor(v);
    return `${pad2(hh)}:${pad2(Math.floor((v - hh) * 60))}`;
}

function periods(list, start, end) {
    const arr = Array.isArray(list) ? list.filter((p) => p && p.start && p.end) : [];
    if (arr.length) return arr;
    return start && end ? [{ start, end }] : [];
}

/** Interval hours; an end at the next day's midnight counts as 24:00. */
function periodHours(p) {
    const s = isoClock(p.start);
    const e = isoClock(p.end);
    if (!s || !e) return null;
    let end = e.hours;
    if (end === 0 && s.hours > 0) end = 24;
    return [s.hours, end];
}

function intervalsText(list, start, end) {
    let ps = periods(list, start, end);
    // Two pieces around midnight read as one interval (22:49–00:41).
    if (ps.length === 2) {
        const a = periodHours(ps[0]);
        const b = periodHours(ps[1]);
        if (a && b && a[1] <= 3 && b[0] >= 21) ps = [{ start: ps[1].start, end: ps[0].end }];
    }
    const parts = ps.map((p) => {
        const s = isoClock(p.start);
        const e = isoClock(p.end);
        if (!s || !e) return null;
        const endText = e.hours === 0 && s.hours > 0 && ps.length > 1 ? '24:00' : e.text;
        return `${s.text}–${endText}`;
    }).filter(Boolean);
    return parts.length ? parts.join(', ') : '—';
}

export class SunpathChart {
    constructor() {
        this.dialog = new AppDialog('sunpath-dialog', 'dialog-wide');
        this.status = statusLine();
        this.chart = el('div', { class: 'sunpath-chart' });
        this.tip = el('div', { class: 'sunpath-tip', hidden: true });
        // Touch: the values go into a box above the chart, where the finger
        // and the hand do not cover them; it keeps the last day touched.
        this.dock = el('div', { class: 'sunpath-dock', 'aria-live': 'polite' });
        this.dock.hidden = !matchMedia('(pointer: coarse)').matches;
        this.wrap = el('div', { class: 'sunpath-wrap' }, this.dock, this.chart, this.tip);
        this.dialog.setBody(this.status, this.wrap);
        this._loading = null;
        this.data = null;
    }

    /** Open the chart for ``location`` and the year of ``skyDate``. */
    async open(location, skyDate) {
        const year = skyDate.getFullYear();
        const key = `${location.latitude.toFixed(4)}_${location.longitude.toFixed(4)}_${year}`;
        this.dialog.setTitle(`${t('sunpath_title')} ${year}`);
        this.dialog.open();
        if (this._loading?.key === key) return; // already on its way
        this.chart.replaceChildren();
        this.dock.replaceChildren(el('p', { class: 'sunpath-hint' }, t('sunpath_touch_hint')));
        const cached = cache.get(key);
        if (cached) {
            this.data = cached;
            this.status.textContent = '';
            this.render();
            return;
        }
        this.status.textContent = t('loading_sunpath');
        const job = { key };
        this._loading = job;
        try {
            const params = new URLSearchParams({
                lat: String(location.latitude), lon: String(location.longitude),
                elevation: String(location.elevation ?? 0), year: String(year),
            });
            const resp = await fetch(`${API_ENDPOINTS.SUNPATH}?${params}`, { credentials: 'same-origin' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const json = await resp.json();
            if (!json || !Array.isArray(json.points) || !json.points.length || (json.version || 0) < SUNPATH_SCHEMA_VERSION) {
                throw new Error('no sunpath data');
            }
            cache.set(key, json);
            if (this._loading !== job) return;
            this.data = json;
            this.status.textContent = '';
            if (this.dialog.isOpen) this.render();
        } catch (error) {
            console.error('Failed to load sunpath data:', error);
            if (this._loading === job) this.status.textContent = t('sunpath_error');
        } finally {
            if (this._loading === job) this._loading = null;
        }
    }

    render() {
        const points = this.data?.points || [];
        if (!points.length) return;
        const width = Math.max(300, Math.min(1100, this.chart.clientWidth || 800));
        const height = Math.round(width * 0.55);
        const margin = { left: 36, right: 10, top: 12, bottom: 24 };
        const iw = width - margin.left - margin.right;
        const ih = height - margin.top - margin.bottom;
        const n = points.length;
        const step = n > 1 ? iw / (n - 1) : iw;
        const xAt = (i) => margin.left + (n === 1 ? iw / 2 : (iw * i) / (n - 1));
        const yAt = (h) => margin.top + ih * (1 - clampHour(h) / 24);
        const svg = svgEl('svg', { class: 'sunpath-svg', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': t('sunpath_title') });

        svg.append(svgEl('rect', { x: margin.left, y: margin.top, width: iw, height: ih, class: 'sunpath-bg' }));

        const bands = svgEl('g', { class: 'sunpath-bands' });
        points.forEach((pt, i) => {
            const x = i === 0 ? margin.left : xAt(i) - step / 2;
            const w = Math.max(1, (i === n - 1 ? margin.left + iw : xAt(i) + step / 2) - x);
            for (const [kind, cls] of [['astronomical', 'band-astro'], ['nautical', 'band-naut'], ['civil', 'band-civil']]) {
                for (const p of periods(pt[`${kind}_twilight_periods`], pt[`${kind}_twilight_start`], pt[`${kind}_twilight_end`])) {
                    const hrs = periodHours(p);
                    if (!hrs) continue;
                    const y = yAt(hrs[1]);
                    const h = yAt(hrs[0]) - y;
                    if (h > 0.5) bands.append(svgEl('rect', { x, y, width: w, height: h, class: cls }));
                }
            }
        });
        svg.append(bands);

        const axis = svgEl('g', { class: 'sunpath-axis' });
        for (const h of [0, 6, 12, 18, 24]) {
            const y = yAt(h);
            axis.append(svgEl('line', { x1: margin.left - 4, x2: margin.left + iw, y1: y, y2: y, class: h % 24 ? 'tick' : 'edge' }));
            axis.append(svgEl('text', { x: margin.left - 6, y: y + 4, 'text-anchor': 'end' }, String(h)));
        }
        let lastMonth = -1;
        points.forEach((pt, i) => {
            const d = parseDay(pt.date);
            if (!d || d.getDate() !== 1 || d.getMonth() === lastMonth) return;
            lastMonth = d.getMonth();
            const x = xAt(i);
            axis.append(svgEl('line', { x1: x, x2: x, y1: margin.top, y2: margin.top + ih, class: 'month' }));
            axis.append(svgEl('text', { x, y: margin.top + ih + 16, 'text-anchor': 'middle' },
                d.toLocaleDateString(locale(), { month: 'short' })));
        });
        svg.append(axis);

        for (const [key, cls] of [['sunrise_hours', 'sunrise'], ['transit_hours', 'transit'], ['sunset_hours', 'sunset']]) {
            let d = '';
            let open = false;
            points.forEach((pt, i) => {
                const v = pt[key];
                if (typeof v !== 'number') { open = false; return; }
                d += `${open ? 'L' : 'M'}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)} `;
                open = true;
            });
            if (d) svg.append(svgEl('path', { d: d.trim(), class: `sunpath-curve ${cls}` }));
        }

        const hover = svgEl('line', { y1: margin.top, y2: margin.top + ih, class: 'sunpath-hover', visibility: 'hidden' });
        svg.append(hover);
        // One delegated listener for the whole chart instead of two per day (O21).
        const hit = svgEl('rect', { x: margin.left, y: margin.top, width: iw, height: ih, class: 'sunpath-hit' });
        const show = (evt) => {
            const box = svg.getBoundingClientRect();
            const sx = ((evt.clientX - box.left) / box.width) * width;
            const i = Math.round(((sx - margin.left) / iw) * (n - 1));
            const pt = points[Math.max(0, Math.min(n - 1, i))];
            const x = xAt(Math.max(0, Math.min(n - 1, i)));
            hover.setAttribute('x1', x);
            hover.setAttribute('x2', x);
            hover.setAttribute('visibility', 'visible');
            this._showTip(pt, evt);
        };
        hit.addEventListener('pointermove', show);
        hit.addEventListener('pointerdown', show);
        hit.addEventListener('pointerleave', () => {
            hover.setAttribute('visibility', 'hidden');
            this.tip.hidden = true;
        });
        svg.append(hit);
        this.chart.replaceChildren(svg);
    }

    _showTip(pt, evt) {
        const d = parseDay(pt.date);
        const rise = isoClock(pt.sunrise);
        const set = isoClock(pt.sunset);
        let transit = isoClock(pt.transit)?.text || hoursText(pt.transit_hours);
        if (transit === '—' && rise && set) {
            const end = set.hours <= rise.hours ? set.hours + 24 : set.hours;
            transit = hoursText((rise.hours + end) / 2);
        }
        let length = '—';
        if (typeof pt.day_length_hours === 'number') {
            const min = Math.round(pt.day_length_hours * 60);
            length = `${Math.floor(min / 60)} h ${pad2(min % 60)} min`;
        }
        const rows = [
            [t('date'), d ? d.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit' }) : String(pt.date)],
            [t('rise_time'), rise?.text || '—'],
            [t('transit_time'), transit],
            [t('set_time'), set?.text || '—'],
            [t('day_length'), length],
            [t('astronomical_twilight'), intervalsText(pt.astronomical_twilight_periods, pt.astronomical_twilight_start, pt.astronomical_twilight_end)],
            [t('nautical_twilight'), intervalsText(pt.nautical_twilight_periods, pt.nautical_twilight_start, pt.nautical_twilight_end)],
            [t('civil_twilight'), intervalsText(pt.civil_twilight_periods, pt.civil_twilight_start, pt.civil_twilight_end)],
        ];
        if (evt.pointerType === 'touch' || evt.pointerType === 'pen') {
            this.tip.hidden = true;
            this.dock.hidden = false;
            // The twilight rows (the last three) can hold several intervals: full width.
            this.dock.replaceChildren(el('dl', {}, rows.map(([k, v], i) => el('div', { class: i >= rows.length - 3 ? 'wide' : null },
                el('dt', {}, k), el('dd', {}, v)))));
            return;
        }
        this.tip.replaceChildren(el('dl', {}, rows.map(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])));
        this.tip.hidden = false;
        const frame = this.wrap.getBoundingClientRect();
        const tipBox = this.tip.getBoundingClientRect();
        let left = evt.clientX - frame.left + 14;
        if (left + tipBox.width > frame.width) left = evt.clientX - frame.left - tipBox.width - 14;
        this.tip.style.left = `${Math.max(0, left)}px`;
        this.tip.style.top = `${Math.max(0, evt.clientY - frame.top - tipBox.height - 10)}px`;
    }
}

function clampHour(h) {
    return Math.min(24, Math.max(0, h));
}
