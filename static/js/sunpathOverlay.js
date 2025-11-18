import { API_ENDPOINTS } from './constants.js';
import { t, getCurrentLanguage } from './i18n.js';
import { settingsManager } from './settings.js';

const SUNPATH_CACHE = new Map();

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
            this.data = SUNPATH_CACHE.get(key);
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
                year: String(year),
                nocache: '1'
            });
            const resp = await fetch(`${API_ENDPOINTS.SUNPATH}?${params.toString()}`);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const json = await resp.json();
            this.data = json;
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

        const formatTime = (iso) => {
            if (!iso) return '—';
            try {
                const d = new Date(iso);
                if (isNaN(d.getTime())) return '—';
                return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
            } catch (_) {
                return '—';
            }
        };

        const sunrise = formatTime(point.sunrise);
        const sunset = formatTime(point.sunset);
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

        const formatInterval = (startIso, endIso) => {
            if (!startIso || !endIso) return '—';
            try {
                const s = new Date(startIso);
                const e = new Date(endIso);
                if (isNaN(s.getTime()) || isNaN(e.getTime())) return '—';
                const sStr = s.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
                const eStr = e.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
                return `${sStr}–${eStr}`;
            } catch (_) {
                return '—';
            }
        };

        const astro = formatInterval(point.astronomical_twilight_start, point.astronomical_twilight_end);
        const naut = formatInterval(point.nautical_twilight_start, point.nautical_twilight_end);
        const civil = formatInterval(point.civil_twilight_start, point.civil_twilight_end);

        const labelAstro = t('astronomical_twilight');
        const labelNaut = t('nautical_twilight');
        const labelCivil = t('civil_twilight');

        let html = `${labelDate}: ${dateStr}<br>${labelSunrise}: ${sunrise}<br>${labelSunset}: ${sunset}<br>${labelLength}: ${dayLen}`;
        if (astro !== '—') {
            html += `<br>${labelAstro}: ${astro}`;
        }
        if (naut !== '—') {
            html += `<br>${labelNaut}: ${naut}`;
        }
        if (civil !== '—') {
            html += `<br>${labelCivil}: ${civil}`;
        }

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
        const step = days > 1 ? innerWidth / (days - 1) : innerWidth;

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
                year: String(year),
                nocache: '1'
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

