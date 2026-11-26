// Names and values as the panels show them.
import { t, getCurrentLanguage, hasKey } from '../i18n.js';

/** Catalogue name without number prefix or doubled parts: "(4) Vesta • (4) Vesta" -> "Vesta". */
export function cleanName(name) {
    let s = String(name ?? '').trim();
    if (s.includes('•')) {
        const parts = s.split('•').map((p) => p.trim()).filter(Boolean).sort((a, b) => b.length - a.length);
        if (parts.length) s = parts[0];
    }
    s = s.replace(/^\(\s*\d+\s*\)\s*/, '').replace(/^\d+\s+/, '');
    s = s.replace(/^(.+?)\s+\1$/, '$1').replace(/\s+/g, ' ').trim();
    return s;
}

/** Localized name: planets, Sun and Moon are translated, catalogue names cleaned. */
export function displayName(name) {
    const s = cleanName(name);
    if (hasKey(s)) return t(s);
    if (hasKey(s.toLowerCase())) return t(s.toLowerCase());
    return s;
}

export function locale() {
    return getCurrentLanguage() === 'en' ? 'en-GB' : 'de-AT';
}

export function fmtNumber(value, digits = 1) {
    return Number.isFinite(value)
        ? value.toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits })
        : '—';
}

export function fmtDegrees(value, digits = 1) {
    return Number.isFinite(value) ? `${fmtNumber(value, digits)}°` : '—';
}

/** "HH:MM" or an ISO time as clock time in ``timeZone``, with the language's suffix. */
export function fmtClock(value, timeZone) {
    if (!value) return '—';
    let text = String(value);
    if (text.includes('T')) {
        const d = new Date(text);
        if (!Number.isNaN(d.getTime())) {
            text = d.toLocaleTimeString(locale(), {
                hour: '2-digit', minute: '2-digit', hour12: false, ...(timeZone ? { timeZone } : {}),
            });
        }
    }
    const suffix = t('clock_suffix');
    return suffix ? `${text} ${suffix}` : text;
}

/** Date and time of ``date`` at the observer's place. */
export function fmtDateTime(date, timeZone, { seconds = false, short = false } = {}) {
    const tz = timeZone ? { timeZone } : {};
    const day = date.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', ...(short ? {} : { year: 'numeric' }), ...tz });
    const time = date.toLocaleTimeString(locale(), {
        hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}), hour12: false, ...tz,
    });
    return { day, time };
}

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];

/** Compass point of an azimuth in the current language ("SW", "SO"). */
export function compassPoint(az) {
    const idx = Math.round((((az % 360) + 360) % 360) / 22.5) % 16;
    const point = COMPASS[idx];
    return getCurrentLanguage() === 'de' ? point.replace(/E/g, 'O') : point;
}
