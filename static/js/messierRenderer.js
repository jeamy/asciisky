import { API_ENDPOINTS, CONFIG } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';

export class MessierRenderer {
    constructor(skyRenderer) {
        this.skyRenderer = skyRenderer;
        this.objects = [];
        this.detailsCache = new Map();
        this.lastDataTimeISO = null;
        this.visible = true;
        this.svgLayer = null;
        this.toggleButton = null;
        // restore visibility from settings if present
        try {
            const opts = settingsManager?.settings?.options;
            if (opts && typeof opts.showMessier === 'boolean') {
                this.visible = !!opts.showMessier;
            }
        } catch (_) { /* noop */ }
        this.initSVGLayer();
    }

    initSVGLayer() {
        const container = this.skyRenderer.container;
        if (!container) return;

        // Remove existing SVG layer if any
        const existing = document.getElementById('messier-layer');
        if (existing) existing.remove();

        this.loadCSS();

        this.svgLayer = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svgLayer.id = 'messier-layer';
        this.svgLayer.setAttribute('class', this.visible ? 'visible' : '');
        // ensure it sits at same stacking context as constellations
        this.svgLayer.style.position = 'absolute';
        this.svgLayer.style.top = '0';
        this.svgLayer.style.left = '0';
        this.svgLayer.style.width = '100%';
        this.svgLayer.style.height = '100%';
        this.svgLayer.style.pointerEvents = 'none';
        container.appendChild(this.svgLayer);
    }

    loadCSS() {
        const cssId = 'messier-css';
        if (!document.getElementById(cssId)) {
            const head = document.getElementsByTagName('head')[0];
            const link = document.createElement('link');
            link.id = cssId;
            link.rel = 'stylesheet';
            link.type = 'text/css';
            link.href = '/static/css/messier.css';
            head.appendChild(link);
        }
    }

    buildQueryParams(location, timeISO = null) {
        const params = new URLSearchParams({
            lat: location.latitude,
            lon: location.longitude,
            elevation: location.elevation || 0
        });
        if (timeISO) params.append('time', timeISO);
        return params;
    }

    buildDetailsCacheKey(objectId, location, timeISO = null) {
        const resolvedTimeISO = timeISO || this.lastDataTimeISO || '';
        return [
            objectId || '',
            location?.latitude ?? '',
            location?.longitude ?? '',
            location?.elevation ?? 0,
            resolvedTimeISO
        ].join('|');
    }

    async fetchMessierData(location, timeISO = null) {
        if (!location || location.latitude === undefined || location.longitude === undefined) return;
        const params = this.buildQueryParams(location, timeISO);

        const resp = await fetch(`${API_ENDPOINTS.MESSIER}?${params.toString()}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        this.objects = data.objects || [];
        this.lastDataTimeISO = timeISO || new Date().toISOString();
        if (this.visible) this.render();
    }

    async fetchMessierDetails(objectId, location, timeISO = null) {
        if (!objectId || !location || location.latitude === undefined || location.longitude === undefined) {
            return null;
        }

        const cacheKey = this.buildDetailsCacheKey(objectId, location, timeISO);
        if (this.detailsCache.has(cacheKey)) {
            return this.detailsCache.get(cacheKey);
        }

        const params = this.buildQueryParams(location, timeISO);
        params.append('object_id', objectId);
        params.append('details', '1');

        const resp = await fetch(`${API_ENDPOINTS.MESSIER}?${params.toString()}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        const data = await resp.json();
        const detail = Array.isArray(data.objects) ? data.objects[0] : null;
        if (detail) {
            this.detailsCache.set(cacheKey, detail);
        }
        return detail;
    }

    toggleVisibility() {
        this.visible = !this.visible;
        if (this.svgLayer) {
            this.svgLayer.classList.toggle('visible', this.visible);
        }
        if (this.toggleButton) {
            this.toggleButton.classList.toggle('active', this.visible);
            this.toggleButton.title = this.visible ? t('hide_messier') : t('show_messier');
        }
        if (this.visible && this.objects.length) {
            this.render();
        }
        try {
            if (settingsManager && typeof settingsManager.setMessierVisible === 'function') {
                settingsManager.setMessierVisible(this.visible);
            }
        } catch (_) { /* noop */ }
        return this.visible;
    }

    updatePositions() {
        this.toggleButton = document.getElementById('messier-toggle');
        const layerInDOM = document.getElementById('messier-layer');
        if (layerInDOM) this.svgLayer = layerInDOM;
        if (!this.svgLayer) this.initSVGLayer();
        if (this.svgLayer) this.svgLayer.classList.toggle('visible', !!this.visible);
        if (this.toggleButton) {
            this.toggleButton.classList.toggle('active', !!this.visible);
            this.toggleButton.title = this.visible ? t('hide_messier') : t('show_messier');
        }
        if (this.visible && this.objects.length) this.render();
    }

    render() {
        if (!this.svgLayer || !this.visible) return;
        const container = this.skyRenderer.container;
        const skyText = container?.querySelector('.sky-text');
        if (!skyText) return;

        const textRect = skyText.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const offsetX = textRect.left - containerRect.left - container.clientLeft + container.scrollLeft;
        const offsetY = textRect.top - containerRect.top - container.clientTop + container.scrollTop;
        const skyWidth = skyText.clientWidth;
        const skyHeight = skyText.clientHeight;

        this.svgLayer.setAttribute('viewBox', `0 0 ${skyWidth} ${skyHeight}`);
        this.svgLayer.style.position = 'absolute';
        this.svgLayer.style.left = `${offsetX}px`;
        this.svgLayer.style.top = `${offsetY}px`;
        this.svgLayer.style.width = `${skyWidth}px`;
        this.svgLayer.style.height = `${skyHeight}px`;
        this.svgLayer.setAttribute('width', `${skyWidth}`);
        this.svgLayer.setAttribute('height', `${skyHeight}`);

        const fragment = document.createDocumentFragment();

        const cellW = skyWidth / CONFIG.SKY_WIDTH;
        const cellH = skyHeight / CONFIG.SKY_HEIGHT;
        const labelThreshold = CONFIG.LABELS?.MESSIER_MAG_THRESHOLD ?? 10;
        const labelsEnabled = CONFIG.LABELS?.ENABLE_MESSIER_LABELS !== false;

        for (const obj of this.objects) {
            const gridPos = this.skyRenderer.altAzToGridPosition(obj.altitude, obj.azimuth);
            if (!gridPos) continue;
            const x = gridPos.col * cellW + (cellW / 2);
            const y = gridPos.row * cellH + (cellH / 2);

            const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            g.setAttribute('class', 'messier-object');
            g.setAttribute('data-id', obj.id);

            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', x);
            circle.setAttribute('cy', y);
            circle.setAttribute('r', 3);
            if (obj.altitude < 0) circle.classList.add('below-horizon');
            g.appendChild(circle);

            const shouldLabel = labelsEnabled && (obj.magnitude == null || obj.magnitude <= labelThreshold);
            if (shouldLabel) {
                const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                label.setAttribute('x', x + 4);
                label.setAttribute('y', y - 4);
                label.textContent = obj.id || obj.name || 'M';
                g.appendChild(label);
            }

            g.addEventListener('click', (e) => {
                e.stopPropagation();
                const data = {
                    ...obj,
                    name: obj.name || obj.id,
                    symbol: obj.symbol || '✦',
                    isMessier: true,
                };
                try {
                    this.skyRenderer.selectedObject = data;
                    this.skyRenderer.showObjectDialog(data);
                    const location = this.skyRenderer.location || settingsManager.getLocation();
                    const timeISO = (settingsManager.getSimulatedTimeISO && settingsManager.getSimulatedTimeISO()) || this.lastDataTimeISO;
                    this.fetchMessierDetails(obj.id, location, timeISO)
                        .then((detail) => {
                            if (!detail) return;
                            Object.assign(obj, detail);
                            const current = this.skyRenderer.selectedObject;
                            if (!current || (current.id !== obj.id && current.name !== data.name)) return;
                            this.skyRenderer.selectedObject = {
                                ...current,
                                ...detail,
                                name: detail.name || current.name,
                                symbol: detail.symbol || current.symbol || '✦',
                                isMessier: true,
                            };
                            this.skyRenderer.refreshDialogIfVisible();
                        })
                        .catch((err) => {
                            console.error(`Failed to load Messier details for ${obj.id}`, err);
                        });
                } catch (err) {
                    console.error('Failed to show Messier dialog', err);
                }
            });

            fragment.appendChild(g);
        }

        this.svgLayer.replaceChildren(fragment);
    }
}
