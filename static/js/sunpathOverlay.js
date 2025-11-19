import { API_ENDPOINTS } from './constants.js';
import { t, getCurrentLanguage } from './i18n.js';
import { settingsManager } from './settings.js';

const SUNPATH_CACHE = new Map();
const SUNPATH_FETCH_MAX_RETRIES = 6;
const SUNPATH_FETCH_BASE_DELAY_MS = 1200;
const SUNPATH_FETCH_MAX_DELAY_MS = 6000;

function pad2(value) {
    return String(value).padStart(2, '0');
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseIsoLocalTime(iso) {
    if (typeof iso !== 'string') return null;
    const tIndex = iso.indexOf('T');
    if (tIndex === -1) return null;
    const timeSection = iso.slice(tIndex + 1);
    const match = timeSection.match(/^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?/);
    if (!match) return null;

    const hour = Number(match[1]);
    const minute = Number(match[2]);
    const second = match[3] ? Number(match[3]) : 0;
    const fractional = match[4] ? Number(`0.${match[4]}`) : 0;
    const totalSeconds = hour * 3600 + minute * 60 + second + fractional;

    return {
        hour,
        minute,
        second,
        decimalHour: totalSeconds / 3600,
        formatted: `${pad2(hour)}:${pad2(minute)}`
    };
}

function formatIsoLocalTime(iso) {
    const parts = parseIsoLocalTime(iso);
    return parts ? parts.formatted : '—';
}

function formatIsoInterval(startIso, endIso) {
    const start = parseIsoLocalTime(startIso);
    const end = parseIsoLocalTime(endIso);
    if (!start || !end) {
        return '—';
    }
    // Handle intervals that run up to local midnight of the next day.
    // In the serialized data these end times appear as 00:00 of the
    // following calendar day, which would look odd as "22:50–00:00".
    // For display purposes, treat such cases as "24:00".
    let endLabel = end.formatted;
    if (end.decimalHour === 0 && start.decimalHour > 0) {
        endLabel = '24:00';
    }
    return `${start.formatted}–${endLabel}`;
}

function formatIsoIntervals(periods, fallbackStart, fallbackEnd) {
    const usePeriods = Array.isArray(periods) && periods.length > 0
        ? periods
        : (fallbackStart && fallbackEnd ? [{ start: fallbackStart, end: fallbackEnd }] : []);

    if (!usePeriods.length) {
        return '—';
    }

    // For high latitudes it is common that the same twilight type appears
    // shortly after midnight and again late in the evening (e.g. 00:00–00:41
    // and 22:49–24:00). For display purposes it is more intuitive to treat
    // this as a single interval spanning midnight (22:49–00:41).
    let displayPeriods = usePeriods;
    if (usePeriods.length === 2) {
        const s0 = parseIsoLocalTime(usePeriods[0].start);
        const e0 = parseIsoLocalTime(usePeriods[0].end);
        const s1 = parseIsoLocalTime(usePeriods[1].start);
        const e1 = parseIsoLocalTime(usePeriods[1].end);
        if (s0 && e0 && s1 && e1) {
            const early = s0.decimalHour <= 3 && e0.decimalHour <= 3;
            const late = s1.decimalHour >= 21 && e1.decimalHour >= 21;
            if (early && late) {
                displayPeriods = [{ start: usePeriods[1].start, end: usePeriods[0].end }];
            }
        }
    }

    const parts = displayPeriods
        .map((period) => formatIsoInterval(period.start, period.end))
        .filter((p) => p !== '—');
    return parts.length ? parts.join(', ') : '—';
}

function normalizeTwilightPeriods(periods, fallbackStart, fallbackEnd) {
    const arr = Array.isArray(periods) ? periods.filter((p) => p && p.start && p.end) : [];
    if (arr.length > 0) {
        return arr;
    }
    if (fallbackStart && fallbackEnd) {
        return [{ start: fallbackStart, end: fallbackEnd }];
    }
    return [];
}

function getDecimalHourFromIso(iso) {
    const parts = parseIsoLocalTime(iso);
    return parts ? parts.decimalHour : null;
}

function makeCacheKey(location, year) {
    if (!location) return '';
    const lat = typeof location.latitude === 'number' ? location.latitude : location.lat;
    const lon = typeof location.longitude === 'number' ? location.longitude : location.lon;
    if (typeof lat !== 'number' || typeof lon !== 'number') return '';
    return `${lat.toFixed(4)}_${lon.toFixed(4)}_${year}`;
}

function showLoadingIndicator(messageKey = 'loading') {
    try {
        const el = document.getElementById('loading-indicator');
        if (el) {
            const textSpan = el.querySelector('.text');
            if (textSpan) {
                textSpan.textContent = t(messageKey);
            }
            el.hidden = false;
        }
    } catch (_) { /* noop */ }
}

function hideLoadingIndicator() {
    try {
        const el = document.getElementById('loading-indicator');
        if (el) {
            el.hidden = true;
        }
    } catch (_) { /* noop */ }
}

export class SunpathOverlay {
    constructor(container) {
        this.container = container || document.body;
        this.root = null;
        this.titleEl = null;
        this.svg = null;
        this.data = null;
        this.visible = false;
        this.currentKey = null;
        this.tooltip = null;
        this.locationTimezone = 'UTC';
    }

    ensureSvg() {
        if (
            this.root &&
            this.root.parentElement === document.body &&
            this.svg &&
            this.svg.parentElement === this.root &&
            this.titleEl &&
            this.root.contains(this.titleEl)
        ) {
            return this.svg;
        }

        let root = this.root;
        if (!root || root.parentElement !== document.body || root.id !== 'sunpath-overlay' || root.tagName.toLowerCase() !== 'div') {
            root = document.getElementById('sunpath-overlay');
            if (root && root.tagName.toLowerCase() !== 'div') {
                if (root.parentElement) {
                    root.parentElement.removeChild(root);
                }
                root = null;
            }
            if (!root) {
                root = document.createElement('div');
                root.id = 'sunpath-overlay';
                root.className = 'sunpath-overlay';
                document.body.appendChild(root);
            }
            this.root = root;
        }

        let title = this.titleEl;
        if (!title || !this.root.contains(title)) {
            title = this.root.querySelector('.sunpath-title');
            if (!title) {
                title = document.createElement('div');
                title.className = 'sunpath-title';
                this.root.insertBefore(title, this.root.firstChild);
            }
            this.titleEl = title;
        }

        let svg = this.svg;
        if (!svg || svg.parentElement !== this.root || svg.tagName.toLowerCase() !== 'svg') {
            svg = this.root.querySelector('svg');
            if (!svg) {
                svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                svg.classList.add('sunpath-svg');
                if (this.titleEl && this.titleEl.nextSibling) {
                    this.root.insertBefore(svg, this.titleEl.nextSibling);
                } else {
                    this.root.appendChild(svg);
                }
            }
            this.svg = svg;
        }

        return this.svg;
    }

    ensureTooltip() {
        if (this.tooltip && document.body.contains(this.tooltip)) {
            return this.tooltip;
        }
        const existing = document.querySelector('.sunpath-tooltip');
        if (existing) {
            this.tooltip = existing;
            return this.tooltip;
        }
        const div = document.createElement('div');
        div.className = 'sunpath-tooltip';
        div.style.display = 'none';
        document.body.appendChild(div);
        this.tooltip = div;
        return div;
    }

    hideTooltip() {
        if (this.tooltip) {
            this.tooltip.style.display = 'none';
        }
    }

    hide() {
        this.visible = false;
        if (this.root) {
            this.root.style.display = 'none';
        }
        this.hideTooltip();
    }

    async toggleForCurrentLocation() {
        const loc = settingsManager.getLocation();
        if (!loc) return;
        const now = new Date();
        const year = now.getFullYear();
        const key = makeCacheKey(loc, year);
        const willShow = !this.visible;
        if (willShow) {
            showLoadingIndicator('loading');
        }
        try {
            if (!this.data || this.currentKey !== key) {
                await this.fetchData(loc, year);
                this.currentKey = key;
            }
            // Wenn keine gültigen Daten vorliegen, Overlay verborgen halten
            if (!this.data || !Array.isArray(this.data.points) || this.data.points.length === 0) {
                this.visible = false;
                this.hide();
                return;
            }
            this.visible = willShow;
            if (this.visible) {
                this.render();
                if (this.root) {
                    this.root.style.display = 'block';
                }
            } else {
                this.hide();
            }
        } finally {
            if (willShow) {
                hideLoadingIndicator();
            }
        }
    }

    async fetchData(location, year) {
        const key = makeCacheKey(location, year);
        if (key && SUNPATH_CACHE.has(key)) {
            const cached = SUNPATH_CACHE.get(key);
            this.data = cached;
            this.locationTimezone = (cached && cached.location && cached.location.timezone) || 'UTC';
            return;
        }
        try {
            const lat = typeof location.latitude === 'number' ? location.latitude : location.lat;
            const lon = typeof location.longitude === 'number' ? location.longitude : location.lon;
            const elev = typeof location.elevation === 'number' ? location.elevation : (location.elevation || 0);
            const params = new URLSearchParams({
                lat: String(lat),
                lon: String(lon),
                elevation: String(elev || 0),
                year: String(year)
            });
            const resp = await fetch(`${API_ENDPOINTS.SUNPATH}?${params.toString()}`);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const json = await resp.json();
            this.data = json;
            this.locationTimezone = (json && json.location && json.location.timezone) || 'UTC';
            if (key) {
                SUNPATH_CACHE.set(key, json);
            }
        } catch (e) {
            console.error('Failed to fetch sunpath data:', e);
            this.data = null;
        }
    }

    showTooltipForPoint(point, evt) {
        if (!point) return;
        const tooltip = this.ensureTooltip();

        const lang = typeof getCurrentLanguage === 'function' ? getCurrentLanguage() : 'de';
        const locale = lang === 'en' ? 'en-US' : 'de-DE';

        let dateStr = point.date;
        try {
            const d = new Date(point.date);
            if (!isNaN(d.getTime())) {
                dateStr = d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit' });
            }
        } catch (_) { /* noop */ }

        const sunrise = formatIsoLocalTime(point.sunrise);
        const sunset = formatIsoLocalTime(point.sunset);
        let dayLen = '—';
        if (typeof point.day_length_hours === 'number') {
            const totalMinutes = Math.round(point.day_length_hours * 60);
            const hours = Math.floor(totalMinutes / 60);
            const minutes = totalMinutes % 60;
            dayLen = `${hours} h ${minutes.toString().padStart(2, '0')} min`;
        }

        const labelDate = t('date');
        const labelSunrise = t('rise_time');
        const labelSunset = t('set_time');
        const labelLength = t('day_length') || 'Tageslänge';

        const astro = formatIsoIntervals(
            point.astronomical_twilight_periods,
            point.astronomical_twilight_start,
            point.astronomical_twilight_end
        );
        const naut = formatIsoIntervals(
            point.nautical_twilight_periods,
            point.nautical_twilight_start,
            point.nautical_twilight_end
        );
        const civil = formatIsoIntervals(
            point.civil_twilight_periods,
            point.civil_twilight_start,
            point.civil_twilight_end
        );

        const labelAstro = t('astronomical_twilight');
        const labelNaut = t('nautical_twilight');
        const labelCivil = t('civil_twilight');

        let html = `${labelDate}: ${dateStr}<br>${labelSunrise}: ${sunrise}<br>${labelSunset}: ${sunset}<br>${labelLength}: ${dayLen}`;
        html += `<br>${labelAstro}: ${astro}`;
        html += `<br>${labelNaut}: ${naut}`;
        html += `<br>${labelCivil}: ${civil}`;

        tooltip.innerHTML = html;

        const pageX = evt.pageX || (evt.clientX + window.scrollX);
        const pageY = evt.pageY || (evt.clientY + window.scrollY);
        const offsetX = 12;
        const offsetY = 12;
        tooltip.style.left = `${pageX + offsetX}px`;
        tooltip.style.top = `${pageY + offsetY}px`;
        tooltip.style.display = 'block';
    }

    render() {
        if (!this.data || !Array.isArray(this.data.points)) return;
        const svg = this.ensureSvg();
        this.ensureTooltip();
        if (this.root) {
            this.root.style.display = 'block';
        }

        let monthLocale = 'de-DE';
        const lang = typeof getCurrentLanguage === 'function' ? getCurrentLanguage() : 'de';
        if (lang === 'en') {
            monthLocale = 'en-US';
        }

        const viewportWidth = Math.max(
            document.documentElement ? document.documentElement.clientWidth : 0,
            window.innerWidth || 0
        );
        const viewportHeight = Math.max(
            document.documentElement ? document.documentElement.clientHeight : 0,
            window.innerHeight || 0
        );

        const width = Math.max(300, Math.round((viewportWidth || 800) * 0.8));
        const height = Math.max(200, Math.round((viewportHeight || 600) * 0.45));

        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.setAttribute('width', String(width));
        svg.setAttribute('height', String(height));

        if (this.titleEl) {
            const year = this.data.year;
            this.titleEl.textContent = `${t('sunpath_title')} ${year}`;
        }

        while (svg.firstChild) svg.removeChild(svg.firstChild);

        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        bg.setAttribute('x', '0');
        bg.setAttribute('y', '0');
        bg.setAttribute('width', String(width));
        bg.setAttribute('height', String(height));
        bg.setAttribute('class', 'sunpath-bg');
        svg.appendChild(bg);

        const margin = { left: 40, right: 10, top: 20, bottom: 20 };
        const innerWidth = Math.max(1, width - margin.left - margin.right);
        const innerHeight = Math.max(1, height - margin.top - margin.bottom);

        const points = this.data.points;
        const days = points.length || 1;
        const step = days > 1 ? innerWidth / (days - 1) : innerWidth;
        const xForIndex = (i) => margin.left + (innerWidth * (days === 1 ? 0.5 : i / (days - 1)));
        const yForHour = (h) => {
            const v = Math.min(24, Math.max(0, h));
            return margin.top + innerHeight * (1 - v / 24);
        };

        const axis = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        axis.setAttribute('class', 'sunpath-axis');

        const yAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        yAxis.setAttribute('x1', String(margin.left));
        yAxis.setAttribute('x2', String(margin.left));
        yAxis.setAttribute('y1', String(margin.top));
        yAxis.setAttribute('y2', String(margin.top + innerHeight));
        axis.appendChild(yAxis);

        const xAxis = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        xAxis.setAttribute('x1', String(margin.left));
        xAxis.setAttribute('x2', String(margin.left + innerWidth));
        xAxis.setAttribute('y1', String(margin.top + innerHeight));
        xAxis.setAttribute('y2', String(margin.top + innerHeight));
        axis.appendChild(xAxis);

        [0, 6, 12, 18, 24].forEach((h) => {
            const y = yForHour(h);
            const tick = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            tick.setAttribute('x1', String(margin.left - 4));
            tick.setAttribute('x2', String(margin.left));
            tick.setAttribute('y1', String(y));
            tick.setAttribute('y2', String(y));
            axis.appendChild(tick);

            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', String(margin.left - 6));
            label.setAttribute('y', String(y + 4));
            label.setAttribute('text-anchor', 'end');
            label.textContent = String(h);
            axis.appendChild(label);
        });

        svg.appendChild(axis);

        // Twilight bands (astronomical, nautical, civil) as background rectangles per day
        const twilightGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        twilightGroup.setAttribute('class', 'sunpath-twilight');
        svg.appendChild(twilightGroup);

        const addTwilightRects = (periods, fallbackStart, fallbackEnd, xLeft, width, cssClass) => {
            const ranges = normalizeTwilightPeriods(periods, fallbackStart, fallbackEnd);
            ranges.forEach((period) => {
                let startH = getDecimalHourFromIso(period.start);
                let endH = getDecimalHourFromIso(period.end);
                if (startH === null || endH === null) {
                    return;
                }

                // Intervals that end at local midnight of the *next* day are
                // serialized as 00:00 for that end time. Interpreting this
                // literally would draw a rectangle from late evening down to
                // 0:00 across almost the entire 0–24h range. For visualization
                // we instead treat such cases as running up to 24:00.
                if (endH === 0 && startH > 0) {
                    endH = 24;
                }

                const yStart = yForHour(startH);
                const yEnd = yForHour(endH);
                const y = Math.min(yStart, yEnd);
                const h = Math.abs(yEnd - yStart);
                if (h <= 0.5) return;

                const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                r.setAttribute('x', String(xLeft));
                r.setAttribute('y', String(y));
                r.setAttribute('width', String(width));
                r.setAttribute('height', String(h));
                r.setAttribute('class', cssClass);
                twilightGroup.appendChild(r);
            });
        };

        for (let i = 0; i < days; i++) {
            const pt = points[i];
            const xCenter = xForIndex(i);
            let xLeft = i === 0 ? margin.left : xCenter - step / 2;
            let xRight = i === days - 1 ? margin.left + innerWidth : xCenter + step / 2;
            if (xRight <= xLeft) {
                xRight = xLeft + 1;
            }
            const w = xRight - xLeft;

            addTwilightRects(
                pt.astronomical_twilight_periods,
                pt.astronomical_twilight_start,
                pt.astronomical_twilight_end,
                xLeft,
                w,
                'sunpath-twilight-astronomical'
            );
            addTwilightRects(
                pt.nautical_twilight_periods,
                pt.nautical_twilight_start,
                pt.nautical_twilight_end,
                xLeft,
                w,
                'sunpath-twilight-nautical'
            );
            addTwilightRects(
                pt.civil_twilight_periods,
                pt.civil_twilight_start,
                pt.civil_twilight_end,
                xLeft,
                w,
                'sunpath-twilight-civil'
            );
        }

        const monthGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        monthGroup.setAttribute('class', 'sunpath-months');
        svg.appendChild(monthGroup);

        let lastMonth = null;
        for (let i = 0; i < days; i++) {
            const pt = points[i];
            if (!pt || !pt.date) {
                continue;
            }
            const d = new Date(pt.date);
            if (isNaN(d.getTime())) {
                continue;
            }
            const day = d.getDate();
            const month = d.getMonth();
            if (day !== 1 || month === lastMonth) {
                continue;
            }
            lastMonth = month;

            const x = xForIndex(i);

            const vLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            vLine.setAttribute('x1', String(x));
            vLine.setAttribute('x2', String(x));
            vLine.setAttribute('y1', String(margin.top));
            vLine.setAttribute('y2', String(margin.top + innerHeight));
            vLine.setAttribute('class', 'sunpath-month-line');
            monthGroup.appendChild(vLine);

            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', String(x));
            label.setAttribute('y', String(margin.top + innerHeight + 12));
            label.setAttribute('text-anchor', 'middle');
            label.setAttribute('class', 'sunpath-month-label');
            label.textContent = d.toLocaleDateString(monthLocale, { month: 'short' });
            monthGroup.appendChild(label);
        }

        const buildPath = (key) => {
            let d = '';
            let started = false;
            const n = points.length;
            for (let i = 0; i < n; i++) {
                const v = points[i][key];
                if (typeof v !== 'number') {
                    started = false;
                    continue;
                }
                const x = xForIndex(i);
                const y = yForHour(v);
                if (!started) {
                    d += `M ${x.toFixed(2)} ${y.toFixed(2)} `;
                    started = true;
                } else {
                    d += `L ${x.toFixed(2)} ${y.toFixed(2)} `;
                }
            }
            return d.trim();
        };

        const sunrisePathData = buildPath('sunrise_hours');
        const sunsetPathData = buildPath('sunset_hours');

        if (sunrisePathData) {
            const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            p.setAttribute('d', sunrisePathData);
            p.setAttribute('class', 'sunpath sunrise');
            svg.appendChild(p);
        }
        if (sunsetPathData) {
            const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            p.setAttribute('d', sunsetPathData);
            p.setAttribute('class', 'sunpath sunset');
            svg.appendChild(p);
        }

        const hoverLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        hoverLine.setAttribute('class', 'sunpath-hover-line');
        hoverLine.setAttribute('y1', String(margin.top));
        hoverLine.setAttribute('y2', String(margin.top + innerHeight));
        hoverLine.style.display = 'none';
        svg.appendChild(hoverLine);

        const showHoverLine = (x) => {
            hoverLine.setAttribute('x1', String(x));
            hoverLine.setAttribute('x2', String(x));
            hoverLine.style.display = 'block';
        };

        const hideHoverLine = () => {
            hoverLine.style.display = 'none';
        };

        const hitGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        hitGroup.setAttribute('class', 'sunpath-hitareas');

        for (let i = 0; i < days; i++) {
            const pt = points[i];
            if (typeof pt.sunrise_hours !== 'number' && typeof pt.sunset_hours !== 'number') {
                continue;
            }
            const xCenter = xForIndex(i);
            let xLeft = i === 0 ? margin.left : xCenter - step / 2;
            let xRight = i === days - 1 ? margin.left + innerWidth : xCenter + step / 2;
            if (xRight <= xLeft) {
                xRight = xLeft + 1;
            }

            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', String(xLeft));
            rect.setAttribute('y', String(margin.top));
            rect.setAttribute('width', String(xRight - xLeft));
            rect.setAttribute('height', String(innerHeight));
            rect.setAttribute('fill', 'transparent');
            rect.setAttribute('pointer-events', 'all');

            rect.addEventListener('mousemove', (evt) => {
                this.showTooltipForPoint(pt, evt);
                showHoverLine(xCenter);
            });
            rect.addEventListener('mouseleave', () => {
                this.hideTooltip();
                hideHoverLine();
            });

            hitGroup.appendChild(rect);
        }

        svg.appendChild(hitGroup);
    }

    static async preloadForCurrentLocation() {
        try {
            const loc = settingsManager.getLocation();
            if (!loc) return;
            const now = new Date();
            const year = now.getFullYear();
            const key = makeCacheKey(loc, year);
            if (key && SUNPATH_CACHE.has(key)) {
                return;
            }

            const lat = typeof loc.latitude === 'number' ? loc.latitude : loc.lat;
            const lon = typeof loc.longitude === 'number' ? loc.longitude : loc.lon;
            const elev = typeof loc.elevation === 'number' ? loc.elevation : (loc.elevation || 0);
            const params = new URLSearchParams({
                lat: String(lat),
                lon: String(lon),
                elevation: String(elev || 0),
                year: String(year)
            });
            const resp = await fetch(`${API_ENDPOINTS.SUNPATH}?${params.toString()}`);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const json = await resp.json();
            if (key) {
                SUNPATH_CACHE.set(key, json);
            }
        } catch (e) {
            console.error('Failed to preload sunpath data:', e);
        }
    }
}

