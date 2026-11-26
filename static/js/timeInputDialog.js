// Dialog for a chosen date and time at the observer's place.
import { t } from './i18n.js';
import { settingsManager } from './settings.js';
import { el } from './ui/dom.js';
import { AppDialog, statusLine } from './ui/dialog.js';

const pad2 = (v) => String(v).padStart(2, '0');

function zonedParts(date, timeZone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(date);
    const get = (type) => Number(parts.find((p) => p.type === type)?.value);
    return { year: get('year'), month: get('month'), day: get('day'), hour: get('hour') % 24, minute: get('minute') };
}

/** UTC milliseconds of a wall-clock time in ``timeZone``. */
export function zonedToUtcMillis({ year, month, day, hour, minute }, timeZone) {
    const target = Date.UTC(year, month - 1, day, hour, minute, 0);
    let guess = target;
    for (let i = 0; i < 3; i++) {
        const p = zonedParts(new Date(guess), timeZone);
        const diff = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, 0) - target;
        guess -= diff;
        if (diff === 0) break;
    }
    return guess;
}

export class TimeInputDialog {
    /** @param {(offsetMinutes: number) => void} onChange */
    constructor(onChange) {
        this.onChange = onChange;
        this.dialog = new AppDialog('time-dialog');
    }

    open() {
        const tz = settingsManager.getLocation().timezone || undefined;
        const now = settingsManager.getSkyDate();
        let p;
        try {
            p = tz ? zonedParts(now, tz) : null;
        } catch (_) {
            p = null;
        }
        p = p || { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate(), hour: now.getHours(), minute: now.getMinutes() };

        this.dialog.setTitle(t('custom_time_title'));
        const date = el('input', { type: 'date', id: 'time-date', required: true, value: `${p.year}-${pad2(p.month)}-${pad2(p.day)}` });
        const time = el('input', { type: 'time', id: 'time-time', required: true, value: `${pad2(p.hour)}:${pad2(p.minute)}` });
        const status = statusLine();
        const form = el('form', { class: 'form-grid' },
            el('label', { for: 'time-date' }, t('date')), date,
            el('label', { for: 'time-time' }, t('time')), time,
            el('p', { class: 'dialog-hint form-wide' }, tz ? `${t('time_zone')}: ${tz}` : ''),
            el('div', { class: 'form-actions' },
                el('button', { type: 'button', class: 'btn', onclick: () => this._apply(0) }, t('now')),
                el('button', { type: 'submit', class: 'btn btn-primary' }, t('apply'))),
            status);
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const [y, mo, d] = date.value.split('-').map(Number);
            const [hh, mm] = time.value.split(':').map(Number);
            if (![y, mo, d, hh, mm].every(Number.isFinite)) {
                status.textContent = t('invalid_time_input');
                return;
            }
            const millis = tz
                ? zonedToUtcMillis({ year: y, month: mo, day: d, hour: hh, minute: mm }, tz)
                : new Date(y, mo - 1, d, hh, mm).getTime();
            this._apply(Math.round((millis - Date.now()) / 60000));
        });
        this.dialog.setBody(form);
        this.dialog.open();
        date.focus();
    }

    _apply(offsetMinutes) {
        this.dialog.close();
        this.onChange(offsetMinutes);
    }
}
