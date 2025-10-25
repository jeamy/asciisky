import { API_ENDPOINTS, CONFIG, ASCII_ART, ASTRO_CONSTANTS, MOON_PHASE_SYMBOLS } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';
import { ZodiacRenderer } from './zodiacRenderer.js';

export class SkyRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.sky = [];
        this.celestialData = null;
        this.selectedObject = null;
        this.skyManager = null; // Wird später gesetzt
        // Dedup for background precompute triggers (per loc/time/kinds)
        this._precomputeRequests = new Set();
        
        // Horizontale Verschiebung aus den Einstellungen laden
        this.horizontalShift = settingsManager.getHorizontalShift(); 
        console.log(`Loaded horizontal shift: ${this.horizontalShift}°`);
        
        // Lade gespeicherte Standortdaten
        this.location = settingsManager.getLocation();
        
        console.log(`Loaded location settings: lat=${this.location.latitude}, lon=${this.location.longitude}, elevation=${this.location.elevation}`);

        // Update-Race-Guard: Token/Zähler für laufende Updates
        this._updateCounter = 0;     // monotoner Zähler
        this._activeUpdate = 0;      // aktuell gültiger Token
        
        // Zoom-State und Originalauflösung merken (für 1x/2x Umschaltung)
        this.isZoomed = false;
        this.originalSkyConfig = {
            width: CONFIG.SKY_WIDTH,
            height: CONFIG.SKY_HEIGHT,
            horizonRow: CONFIG.HORIZON_ROW
        };
        // Unterstützte Zoomstufen (Faktoren)
        this.zoomLevels = [1, 2, 4];
        this.zoomIndex = 0; // Start: 1×, bleibt bei mobilen Geräten immer 0
        
        // Pan-Funktionalität für gezoomte Ansicht
        this.verticalOffset = 0; // Vertikale Verschiebung in Pixeln
        this.isDragging = false;
        this.lastMouseY = 0;

        this.initSky();
        this.setupEventListeners();
        
        // Initialize zodiac renderer if enabled
        if (CONFIG.CONSTELLATIONS?.ENABLE_CONSTELLATION_LAYER) {
            this.zodiacRenderer = new ZodiacRenderer(this);
        }
        
        // Manuell update aufrufen, um die Daten zu laden und anzuzeigen
        this.update();
    }

    initSky() {
        // Initialize empty sky
        this.sky = Array(CONFIG.SKY_HEIGHT).fill().map(() => 
            Array(CONFIG.SKY_WIDTH).fill(' ')
        );
        this.drawHorizon();
        // Don't call render() here to avoid recursion
    }
    
    // Methode zum Verschieben des Horizonts nach links
    shiftHorizonLeft() {
        // Verschiebe um 5 Grad nach links
        this.horizontalShift -= 5;
        
        // Speichere die aktuelle Verschiebung
        settingsManager.setHorizontalShift(this.horizontalShift);
        
        // Aktualisiere die Anzeige
        this.render();
        // Halte Sternbild-SVG synchron (im nächsten Frame nach Layout)
        if (this.zodiacRenderer && this.zodiacRenderer.visible) {
            try { requestAnimationFrame(() => { try { this.zodiacRenderer.updatePositions(); } catch (_) { /* noop */ } }); } catch (_) { /* noop */ }
        }
    }
    
    // Methode zum Verschieben des Horizonts nach rechts
    shiftHorizonRight() {
        // Verschiebe um 5 Grad nach rechts
        this.horizontalShift += 5;
        
        // Speichere die aktuelle Verschiebung
        settingsManager.setHorizontalShift(this.horizontalShift);
        
        // Aktualisiere die Anzeige
        this.render();
        // Halte Sternbild-SVG synchron (im nächsten Frame nach Layout)
        if (this.zodiacRenderer && this.zodiacRenderer.visible) {
            try { requestAnimationFrame(() => { try { this.zodiacRenderer.updatePositions(); } catch (_) { /* noop */ } }); } catch (_) { /* noop */ }
        }
    }

    drawHorizon() {
        const horizonRow = CONFIG.HORIZON_ROW;
        const width = CONFIG.SKY_WIDTH;
        const height = CONFIG.SKY_HEIGHT;
        
        // Draw horizon line deutlicher
        for (let col = 1; col < width - 1; col++) {
            this.sky[horizonRow][col] = ASCII_ART.HORIZON;
        }
        
        // Add corners
        this.sky[horizonRow][0] = ASCII_ART.HORIZON_START;
        this.sky[horizonRow][width - 1] = ASCII_ART.HORIZON_END;
        
        // Keine Beschriftung für den Horizont
        
        // Add cardinal directions along the horizon (dehnen: nur 3 gleichzeitig anzeigen)
        // Azimut-Mapping: 0°=Nord, 90°=Ost, 180°=Süd, 270°=West
        const dirDefs = [
            { dir: 'N', azimuth: 0 },
            { dir: 'O', azimuth: 90 },
            { dir: 'S', azimuth: 180 },
            { dir: 'W', azimuth: 270 }
        ];
        
        // Bestimme die Richtung, die aktuell "aus dem Blick" liegt: die mit effektivem Azimut am nächsten zu 0°
        // Standard (horizontalShift=0): N ist am nächsten zu 0° => O,S,W bleiben sichtbar
        const withEffective = dirDefs.map(p => {
            let eff = p.azimuth - this.horizontalShift;
            while (eff < 0) eff += 360;
            while (eff >= 360) eff -= 360;
            const distToZero = Math.min(eff, 360 - eff); // Abstand zu 0° entlang des Kreises
            return { ...p, effectiveAzimuth: eff, distToZero };
        });
        
        // Verstecke genau eine Richtung: die mit minimalem Abstand zu 0°
        withEffective.sort((a, b) => a.distToZero - b.distToZero);
        const hidden = withEffective[0].dir;
        const visible = withEffective.filter(p => p.dir !== hidden);
        
        // Platziere die drei sichtbaren Richtungen anhand ihres absoluten (verschobenen) Azimuts,
        // damit sie sich bei Klick auf die Pfeile sichtbar bewegen
        const inner = width - 2;
        const vis = visible.map(p => ({ dir: p.dir, eff: p.effectiveAzimuth }));

        const placeDir = (dir, col) => {
            if (col < 0 || col >= width) return;
            if (dir === 'N') this.sky[horizonRow][col] = t('north');
            else if (dir === 'O') this.sky[horizonRow][col] = t('east');
            else if (dir === 'S') this.sky[horizonRow][col] = t('south');
            else if (dir === 'W') this.sky[horizonRow][col] = t('west');
        };

        // Absolute Abbildung auf Breite (0..360 -> 1..inner+1)
        vis.forEach(v => {
            const col = Math.round((v.eff / 360) * inner) + 1;
            placeDir(v.dir, col);
        });
        
        // Füge Höhenmarkierungen hinzu (alle 30 Grad)
        const altitudeMarks = [90, 60, 30, 0, -30, -60, -90];
        altitudeMarks.forEach(alt => {
            const normalizedAlt = (alt - CONFIG.MIN_ALTITUDE) / (CONFIG.MAX_ALTITUDE - CONFIG.MIN_ALTITUDE);
            const row = Math.round((1 - normalizedAlt) * (height - 1));
            
            if (row >= 0 && row < height && row !== horizonRow) {
                // Markiere die Höhe am linken Rand
                this.sky[row][0] = alt > 0 ? '+' : alt < 0 ? '-' : '0';
                
                // Füge die Höhenzahl hinzu
                const altStr = Math.abs(alt).toString();
                for (let i = 0; i < altStr.length && i + 1 < width; i++) {
                    this.sky[row][i + 1] = altStr[i];
                }
            }
        });

        // Listen for fullscreen changes
        document.addEventListener('fullscreenchange', () => {
            if (!document.fullscreenElement && this.isFullscreen) {
                if (this.exitFullscreen && typeof this.exitFullscreen === 'function') {
                    this.exitFullscreen();
                } else {
                    // Gracefully reset flag if no fullscreen API available in this branch
                    this.isFullscreen = false;
                }
            }
        });

    }

    // Converts altitude/azimuth into integer grid coordinates (row, col)
    // This projection is used by both ASCII rendering and SVG overlays
    altAzToGridPosition(altitude, azimuth) {
        const horizonRow = CONFIG.HORIZON_ROW;
        const height = CONFIG.SKY_HEIGHT;
        const width = CONFIG.SKY_WIDTH;

        // Vertical mapping: above the horizon goes from horizonRow up to 0
        let row;
        if (altitude >= 0) {
            row = Math.round(horizonRow - (altitude / 90 * horizonRow));
        } else {
            row = Math.round(horizonRow + (Math.abs(altitude) / 90 * (height - horizonRow - 1)));
        }

        // Horizontal mapping with the current horizontalShift applied
        let effectiveAzimuth = azimuth - this.horizontalShift;
        while (effectiveAzimuth < 0) effectiveAzimuth += 360;
        while (effectiveAzimuth >= 360) effectiveAzimuth -= 360;
        let col = Math.round((effectiveAzimuth / 360) * (width - 2)) + 1;

        // Clamp to bounds to avoid dropping stars at the edges due to rounding
        if (row < 0 || row >= height || col < 0 || col >= width) {
            // console.debug('[proj] clamp needed', { row, col, width, height, altitude, azimuth, effectiveAzimuth });
        }
        row = Math.max(0, Math.min(height - 1, row));
        col = Math.max(0, Math.min(width - 1, col));
        return { row, col };
    }

    updateCelestialData(data) {
        this.celestialData = data;
        this.render();
    }

    render() {

        // Initialisiere den Himmel neu (zeichnet den Horizont und die Himmelsrichtungen)
        this.initSky();

        // Zeichne Himmelsobjekte nur, wenn Daten vorhanden sind
        if (this.celestialData && this.celestialData.bodies) {
            Object.values(this.celestialData.bodies).forEach(body => {
                this.drawCelestialObject(body);
            });
        }

        // Convert 2D array to string and display
        const skyText = this.sky.map(row => row.join('')).join('\n');

        // Erstelle ein temporäres div für den Himmelstext
        const skyTextDiv = document.createElement('div');
        skyTextDiv.className = 'sky-text';
        skyTextDiv.textContent = skyText;

        // Speichere die vorhandenen Navigationspfeile
        const existingArrows = document.getElementById('navigation-arrows');

        // Rette das SVG-Layer vor dem Leeren
        const svgLayer = document.getElementById('constellation-layer');
        
        // Entferne alte object-count-displays vor dem Leeren
        const oldCounts = document.querySelectorAll('#object-count-display');
        oldCounts.forEach(count => count.remove());
        
        // Leere den Container
        this.container.innerHTML = '';

        // Füge den Himmelstext hinzu
        this.container.appendChild(skyTextDiv);
        
        // Füge das SVG-Layer wieder hinzu, falls es existierte
        if (svgLayer) {
            this.container.appendChild(svgLayer);
        }

        // Füge Objektanzahl-Display hinzu
        this.addObjectCountDisplay();

        // Füge immer neue Navigationspfeile hinzu
        this.addNavigationArrows();

        // Stelle sicher, dass der Zoom-Button nach jedem Rendern vorhanden ist
        this.createZoomButton();

        // Aktualisiere Label-Overlay für helle Kleinplaneten nach dem Layout-Pass
        // requestAnimationFrame stellt sicher, dass getBoundingClientRect() valide Größen liefert
        requestAnimationFrame(() => {
            this.renderLabels();
            // Update cursor style and apply vertical offset for pan functionality
            this.updateCursorStyle();
            this.applyVerticalOffset();
            // Re-setup pan events since DOM element was recreated
            this.setupPanEvents();
            // Reproject constellation overlay to match the new layout and horizon shift
            if (this.zodiacRenderer && this.zodiacRenderer.visible) {
                this.zodiacRenderer.updatePositions();
            }
        });
    }

    // No-op fullscreen helpers for master branch (no fullscreen feature enabled)
    createFullscreenButton() { /* noop: fullscreen not available in master */ }
    updateFullscreenButton() { /* noop */ }

    // Zoom-Schalter (1x/2x Auflösung), physische Größe bleibt dank adjustSkyScale gleich
    createZoomButton() {
        try {
            // Entferne bestehenden Button
            const existing = this.container.querySelector('#zoom-toggle');
            if (existing) existing.remove();

            // Zoom-Button nur auf Desktop-Geräten anzeigen
            if (this.isMobileDevice()) {
                return;
            }

            const btn = document.createElement('button');
            btn.id = 'zoom-toggle';
            btn.className = 'zoom-button';
            btn.type = 'button';
            const factor = (this.zoomLevels && this.zoomLevels[this.zoomIndex]) ? this.zoomLevels[this.zoomIndex] : 1;
            const nextIndex = (this.zoomIndex + 1) % this.zoomLevels.length;
            const nextFactor = this.zoomLevels[nextIndex];
            btn.title = `Zoom ${nextFactor}×`;
            btn.textContent = `${nextFactor}×`;
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleZoom();
            });
            this.container.appendChild(btn);
        } catch (_) { /* noop */ }
    }

    toggleZoom() {
        try {
            // Zoom nur auf Desktop-Geräten erlauben
            if (this.isMobileDevice()) {
                return;
            }
            
            // Zyklisch auf nächste Zoomstufe schalten
            this.zoomIndex = (this.zoomIndex + 1) % this.zoomLevels.length;
            const factor = this.zoomLevels[this.zoomIndex] || 1;
            
            // Reset vertical offset when switching zoom levels
            this.verticalOffset = 0;
            
            // Skalierte Rastergröße setzen (physische Größe bleibt dank adjustSkyScale konstant)
            CONFIG.SKY_WIDTH = Math.max(1, Math.round(this.originalSkyConfig.width * factor));
            CONFIG.SKY_HEIGHT = Math.max(1, Math.round(this.originalSkyConfig.height * factor));
            CONFIG.HORIZON_ROW = Math.floor(CONFIG.SKY_HEIGHT * 0.5);
            
            // Update cursor style based on zoom level
            this.updateCursorStyle();
            
            // Raster neu aufbauen und rendern
            this.initSky();
            this.render();
        } catch (e) {
            console.error('Error toggling zoom:', e);
        }
    }

    isMobileDevice() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || 
               window.innerWidth <= 768;
    }

    updateCursorStyle() {
        const skyEl = this.container.querySelector('.sky-text');
        if (skyEl) {
            const factor = this.zoomLevels[this.zoomIndex] || 1;
            if (factor > 1 && !this.isMobileDevice()) {
                skyEl.style.cursor = 'grab';
            } else {
                skyEl.style.cursor = 'default';
            }
        }
    }

    addNavigationArrows() {
        // Füge Navigationspfeile hinzu
        // Entferne zuerst alle vorhandenen Navigationspfeile
        const existingArrows = document.getElementById('navigation-arrows');
        if (existingArrows) {
            existingArrows.remove();
        }
        
        // Erstelle neue Navigationspfeile
        const arrowsDiv = document.createElement('div');
        arrowsDiv.id = 'navigation-arrows';
        arrowsDiv.className = 'navigation-arrows';
        
        // Positioniere die Pfeile vertikal auf Höhe der Horizontlinie
        const horizonRow = CONFIG.HORIZON_ROW;
        const totalRows = CONFIG.SKY_HEIGHT - 1;
        const horizonYPercent = (horizonRow / totalRows) * 100;
        // Setze CSS-Variable, Styling verbleibt in externer CSS
        arrowsDiv.style.setProperty('--horizon-top', `${horizonYPercent}%`);
        
        // Linker Pfeil (rechts neben West)
        const leftArrow = document.createElement('button');
        leftArrow.id = 'nav-left';
        leftArrow.className = 'nav-arrow nav-arrow-left';
        leftArrow.title = t('shift_left');
        leftArrow.innerHTML = '&#9665;';
        leftArrow.addEventListener('click', (e) => { e.stopPropagation(); this.shiftHorizonLeft(); });
        
        // Rechter Pfeil (links neben Ost)
        const rightArrow = document.createElement('button');
        rightArrow.id = 'nav-right';
        rightArrow.className = 'nav-arrow nav-arrow-right';
        rightArrow.title = t('shift_right');
        rightArrow.innerHTML = '&#9655;';
        rightArrow.addEventListener('click', (e) => { e.stopPropagation(); this.shiftHorizonRight(); });
        
        arrowsDiv.appendChild(leftArrow);
        arrowsDiv.appendChild(rightArrow);
        this.container.appendChild(arrowsDiv);
    }

    async addObjectCountDisplay() {
        // Entferne alle vorhandenen Count-Displays (auch Duplikate)
        const existingCounts = document.querySelectorAll('#object-count-display, .object-count-display');
        existingCounts.forEach(count => count.remove());

        // Zähle sichtbare Asteroiden und Kometen
        let asteroidCount = 0;
        let cometCount = 0;

        if (this.celestialData && this.celestialData.bodies) {
            Object.values(this.celestialData.bodies).forEach(body => {
                if (body.altitude > 0) { // Nur sichtbare Objekte über dem Horizont
                    if (body.type === 'asteroid') {
                        asteroidCount++;
                    } else if (body.type === 'comet') {
                        cometCount++;
                    }
                }
            });
        }

        // Hole Magnitude-Werte aus der Filters-API (benutzerdefinierte Einstellungen)
        let asteroidMag = 10.0; // Fallback
        let cometMag = 14.0;    // Fallback
        
        try {
            const response = await fetch(`${API_ENDPOINTS.FILTERS_GET}?nocache=1`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.filters) {
                    asteroidMag = data.filters.asteroidMaxMagnitude || 10.0;
                    cometMag = data.filters.cometMaxMagnitude || 14.0;
                }
            }
        } catch (error) {
            console.warn('Could not fetch magnitude filters:', error);
        }

        // Erstelle Count-Display
        const countDiv = document.createElement('div');
        countDiv.id = 'object-count-display';
        countDiv.className = 'object-count-display';
        
        countDiv.innerHTML = `
            <div class="count-item">${t('asteroids_up_to_mag')} ${asteroidMag}: ${asteroidCount}</div>
            <div class="count-item">${t('comets_up_to_mag')} ${cometMag}: ${cometCount}</div>
        `;

        this.container.appendChild(countDiv);
    }

    // Stellt sicher, dass eine Ebene für Labels existiert und gibt sie zurück
    ensureLabelsLayer() {
        let layer = this.container.querySelector('#labels-layer');
        if (!layer) {
            layer = document.createElement('div');
            layer.id = 'labels-layer';
            layer.className = 'labels-layer';
            this.container.appendChild(layer);
        }
        return layer;
    }

    // Rendert kleine Labels für helle Kleinplaneten und Kometen (mag < Threshold)
    renderLabels() {
        try {
            if (!this.celestialData) return;
            const enableAsteroidLabels = !!CONFIG.LABELS?.ENABLE_BRIGHT_MINOR_PLANET_LABELS;
            const enableCometLabels = !!CONFIG.LABELS?.ENABLE_BRIGHT_COMET_LABELS;
            if (!enableAsteroidLabels && !enableCometLabels) return;
            const layer = this.ensureLabelsLayer();
            // Layer leeren
            layer.innerHTML = '';

            // Verwende die tatsächliche Größe und Position des Sky-Textes, nicht des Containers
            const containerRect = this.container.getBoundingClientRect();
            const textEl = this.container.querySelector('.sky-text');
            if (!textEl) {
                console.warn('[labels] sky-text element not found; skip labels');
                return;
            }
            const textRect = textEl.getBoundingClientRect();
            // Berücksichtige Scroll-Offsets des Containers, da overflow:auto aktiv ist
            const offsetX = (textRect.left - containerRect.left) + this.container.scrollLeft;
            const offsetY = (textRect.top  - containerRect.top)  + this.container.scrollTop;
            const colWidth = textRect.width / CONFIG.SKY_WIDTH;
            const rowHeight = textRect.height / CONFIG.SKY_HEIGHT;

            const asteroidThreshold = (CONFIG.LABELS && CONFIG.LABELS.BRIGHT_MINOR_PLANET_MAG_THRESHOLD != null)
                ? CONFIG.LABELS.BRIGHT_MINOR_PLANET_MAG_THRESHOLD : 9.0;
            const cometThreshold = (CONFIG.LABELS && CONFIG.LABELS.BRIGHT_COMET_MAG_THRESHOLD != null)
                ? CONFIG.LABELS.BRIGHT_COMET_MAG_THRESHOLD : 9.0;

            let renderedCount = 0;
            for (const obj of Object.values(this.celestialData.bodies)) {
                // Prüfe Objekt-Typ und Magnitude
                const isAsteroid = (obj.type && obj.type === 'asteroid') || /asteroid/i.test(String(obj.name || ''));
                const isComet = (obj.type && obj.type === 'comet');
                if (typeof obj.magnitude !== 'number') continue;

                let eligible = false;
                if (enableAsteroidLabels && isAsteroid && obj.magnitude < asteroidThreshold) eligible = true;
                if (enableCometLabels && isComet && obj.magnitude < cometThreshold) eligible = true;
                if (!eligible) continue;

                // Position muss bereits berechnet sein
                let row = (obj.displayRow !== undefined) ? obj.displayRow : null;
                let col = (obj.displayCol !== undefined) ? obj.displayCol : null;
                // Fallback falls Position nicht gesetzt wurde
                if (row === null || col === null) {
                    const horizonRow = CONFIG.HORIZON_ROW;
                    const height = CONFIG.SKY_HEIGHT;
                    const width = CONFIG.SKY_WIDTH;
                    if (obj.altitude >= 0) {
                        row = Math.round(horizonRow - (obj.altitude / 90 * horizonRow));
                    } else {
                        row = Math.round(horizonRow + (Math.abs(obj.altitude) / 90 * (height - horizonRow - 1)));
                    }
                    let effectiveAzimuth = obj.azimuth - this.horizontalShift;
                    while (effectiveAzimuth < 0) effectiveAzimuth += 360;
                    while (effectiveAzimuth >= 360) effectiveAzimuth -= 360;
                    col = Math.round((effectiveAzimuth / 360) * (width - 2)) + 1;
                }
                if (row === null || col === null) continue;

                // Pixelposition relativ zum Container, ausgerichtet auf die Textfläche
                const xRaw = offsetX + (col + 0.5) * colWidth;
                const yRaw = offsetY + (row - 0.6) * rowHeight; // leicht oberhalb des Symbols
                const x = Math.max(offsetX, Math.min(offsetX + textRect.width, xRaw));
                const y = Math.max(offsetY, Math.min(offsetY + textRect.height, yRaw));

                // Label erzeugen
                const label = document.createElement('div');
                label.className = 'object-label';
                const displayName = this.getLocalizedDisplayName(obj.name);
                label.textContent = `${displayName} ${obj.magnitude.toFixed(1)} m`;
                label.style.left = `${x}px`;
                label.style.top = `${y}px`;
                layer.appendChild(label);
                renderedCount++;
            }
        } catch (e) {
            console.error('Error rendering labels:', e);
        }
    }

    // Zeige/Verberge einen lokalisierten Ladeindikator außerhalb des Sky-Containers
    showLoading(messageKey = 'loading') {
        try {
            const el = document.getElementById('loading-indicator');
            if (el) {
                const textSpan = el.querySelector('.text');
                if (textSpan) textSpan.textContent = t(messageKey);
                el.hidden = false;
            }
        } catch (_) { /* noop */ }
    }

    hideLoading() {
        try {
            const el = document.getElementById('loading-indicator');
            if (el) {
                el.hidden = true;
            }
        } catch (_) { /* noop */ }
    }

    // Hängt den optionalen Simulationszeit-Parameter (?time=ISO) an eine URL an
    appendTimeParam(url) {
        try {
            const iso = settingsManager.getSimulatedTimeISO && settingsManager.getSimulatedTimeISO();
            if (iso) {
                const sep = url.includes('?') ? '&' : '?';
                return `${url}${sep}time=${encodeURIComponent(iso)}`;
            }
            return url;
        } catch (_) {
            return url;
        }
    }

    // Legacy function - disabled after RabbitMQ migration
    async checkCacheAvailability(location) {
        // RabbitMQ handles caching automatically
        return null;
    }

    // Legacy function - disabled after RabbitMQ migration
    async triggerPrecomputeWindowIfNeeded(location, timeISO, kinds, locKey) {
        // RabbitMQ triggers precompute automatically on cache miss
        return;
    }

    // Prüft, ob ein Update-Token noch aktiv ist (verhindert Out-of-Order-Merges)
    isActiveUpdate(token) {
        return token === this._activeUpdate;
    }

    drawCelestialObject(obj) {
        // Wenn das Objekt unter dem Horizont ist und wir sie nicht anzeigen sollen, nichts tun
        if (obj.altitude < 0 && !CONFIG.SHOW_BELOW_HORIZON) {
            return;
        }
        
        const horizonRow = CONFIG.HORIZON_ROW;
        const height = CONFIG.SKY_HEIGHT;
        const width = CONFIG.SKY_WIDTH;
        
        // Berechne die Zeile basierend auf der Höhe (-90° bis 90°)
        // Für Objekte über dem Horizont: 0 bis horizonRow
        // Für Objekte unter dem Horizont: horizonRow bis height-1
        let row;
        if (obj.altitude >= 0) {
            // Über dem Horizont (0° bis 90°)
            row = Math.round(horizonRow - (obj.altitude / 90 * horizonRow));
        } else {
            // Unter dem Horizont (0° bis -90°)
            row = Math.round(horizonRow + (Math.abs(obj.altitude) / 90 * (height - horizonRow - 1)));
        }
        
        // Berechne die Spalte basierend auf dem Azimut (0° bis 360°) mit horizontaler Verschiebung
        // Azimut: 0° = Nord, 90° = Ost, 180° = Süd, 270° = West
        // Nutze den vollen Bereich 0°–360° über die gesamte Breite
        
        // Berechne den effektiven Azimut mit Verschiebung
        let effectiveAzimuth = obj.azimuth - this.horizontalShift;
        
        // Normalisiere den Azimut auf den Bereich 0-360
        while (effectiveAzimuth < 0) effectiveAzimuth += 360;
        while (effectiveAzimuth >= 360) effectiveAzimuth -= 360;
        
        // Berechne die Spalte basierend auf dem normalisierten Azimut
        const col = Math.round((effectiveAzimuth / 360) * (width - 2)) + 1;
        
        // Speichere die Position des Objekts für spätere Verwendung
        obj.displayRow = row;
        obj.displayCol = col;
        
        // Nur zeichnen, wenn innerhalb der Grenzen
        if (row >= 0 && row < height && col >= 0 && col < width) {
            // Prüfe, ob dies das ausgewählte Objekt ist
            const isSelected = this.selectedObject && this.selectedObject.name === obj.name;
            
            // Prüfe, ob an dieser Position bereits ein Objekt gezeichnet wurde
            const existingContent = this.sky[row][col];
            const isOccupied = existingContent !== ' ' && 
                              existingContent !== ASCII_ART.HORIZON && 
                              existingContent !== 'N' && 
                              existingContent !== 'S' && 
                              existingContent !== 'O' && 
                              existingContent !== 'W';
            
            
            // Wähle Symbol basierend auf Auswahl und Überlappung
            let symbol;
            if (isSelected) {
                symbol = ASCII_ART.SELECTED_OBJECT;
            } else if (isOccupied) {
                // Wenn bereits ein Objekt an dieser Position ist, prüfe Priorität
                const backendSymbol = obj.symbol && String(obj.symbol).trim() !== '' ? obj.symbol : null;
                const isAsteroid = obj.type === 'asteroid' || backendSymbol === '⚸';
                // Prüfe ob existierendes Symbol ein wichtiges Objekt ist (Planeten oder Mondphasen)
                const moonPhaseSymbols = Object.values(MOON_PHASE_SYMBOLS);
                const existingIsMoon = moonPhaseSymbols.includes(existingContent);
                const existingIsImportant = existingIsMoon || existingContent === '♄' || existingContent === '♆' || existingContent === '♅' || existingContent === '♃' || existingContent === '♂' || existingContent === '♀' || existingContent === '☿' || existingContent === ASCII_ART.SELECTED_OBJECT;
                const existingIsAsteroid = existingContent === '⚸';

                if (isAsteroid) {
                    // Asteroiden immer mit ihrem Glyphen rendern, auch bei Überlappung
                    symbol = backendSymbol || '⚸';
                    obj.isOverlapping = true;
                } else if (existingIsImportant || existingIsAsteroid) {
                    // Wichtiges Objekt oder bereits ein Asteroid an dieser Position: nicht überschreiben
                    return;
                } else {
                    // Generischer Überlappungsfall für Nicht-Asteroiden
                    symbol = '*';
                    obj.isOverlapping = true;
                }
            } else {
                // Bevorzuge Symbol vom Backend; fallback auf lokale Symboltabelle
                const backendSymbol = obj.symbol && String(obj.symbol).trim() !== '' ? obj.symbol : null;
                
                // Spezialbehandlung für Mond: Wähle Symbol basierend auf Phase
                if (obj.name && obj.name.toLowerCase() === 'moon' && obj.phase_name && MOON_PHASE_SYMBOLS[obj.phase_name]) {
                    symbol = MOON_PHASE_SYMBOLS[obj.phase_name];
                }
                // Prüfe zuerst auf Backend-Symbol, dann auf Typ, dann auf Namen
                else if (backendSymbol) {
                    symbol = backendSymbol;
                } else if (obj.type && CONFIG.OBJECT_SYMBOLS[obj.type.toLowerCase()]) {
                    // Verwende Symbol basierend auf dem Typ (asteroid oder comet)
                    symbol = CONFIG.OBJECT_SYMBOLS[obj.type.toLowerCase()];
                } else if (CONFIG.OBJECT_SYMBOLS[obj.name.toLowerCase()]) {
                    symbol = CONFIG.OBJECT_SYMBOLS[obj.name.toLowerCase()];
                } else {
                    symbol = '★'; // Fallback auf Stern-Symbol
                }
               
            }
            
            this.sky[row][col] = symbol;
            
            // Füge Label und Höheninformation hinzu, wenn ausgewählt
            if (isSelected) {
                // Formatiere die Höhe mit der konfigurierten Genauigkeit
                const altitudeStr = obj.altitude.toFixed(CONFIG.ALTITUDE_PRECISION);
                const displayName = this.getLocalizedDisplayName(obj.name);
                const label = `${displayName} (${altitudeStr}°)`;
                const startCol = Math.max(0, col - Math.floor(label.length / 2));
                
                // Stelle sicher, dass das Label nicht außerhalb des sichtbaren Bereichs liegt
                const labelRow = Math.min(row + 1, height - 1);
                
                for (let i = 0; i < label.length && startCol + i < width; i++) {
                    this.sky[labelRow][startCol + i] = label[i] || ' ';
                }
            }
        }
    }

    // Hilfsfunktion: Entfernt numerische Bezeichnungen wie "(4) Vesta" -> "Vesta" und lokalisiert
    getLocalizedDisplayName(name) {
        try {
            if (!name) return '';
            let s = String(name).trim();

            // 1) Entferne doppelte Namenssegmente, die mit einem Bullet getrennt sind, z.B. "(4) Vesta • (4) Vesta"
            if (s.includes('•')) {
                const parts = s.split('•')
                    .map(p => p.trim())
                    .filter(Boolean);
                // Wähle den längsten Teil (meist ohne führende/abschließende Artefakte)
                if (parts.length > 0) {
                    parts.sort((a, b) => b.length - a.length);
                    s = parts[0];
                }
            }

            // 2) Entferne führende nummerische Bezeichnungen
            //    a) "(4) Vesta" -> "Vesta"
            s = s.replace(/^\(\s*\d+\s*\)\s*/, '');
            //    b) "4 Vesta" oder "0004 Vesta" -> "Vesta"
            s = s.replace(/^\d+\s+/, '');

            // 3) Falls der Name exakt doppelt vorkommt (mit Leerzeichen), reduziere auf einmal
            //    Beispiel: "Vesta Vesta" -> "Vesta"
            s = s.replace(/^(.+?)\s+\1$/, '$1');

            // 4) Mehrfache Whitespaces bereinigen
            s = s.replace(/\s+/g, ' ').trim();

            // 5) Versuche Übersetzung mit Original-Schreibweise und Kleinbuchstaben
            //    Das Backend sendet Planetennamen in Kleinbuchstaben (mercury, venus, etc.)
            const translated = t(s) || t(s.toLowerCase());
            return translated !== s && translated !== s.toLowerCase() ? translated : s;
        } catch (_) {
            return String(name);
        }
    }

    // Normalisiert Roh-Namen zu einem stabilen Dedup-Key (ohne Lokalisierung)
    normalizeNameKey(name) {
        try {
            if (!name) return '';
            let s = String(name).trim();

            if (s.includes('•')) {
                const parts = s.split('•').map(p => p.trim()).filter(Boolean);
                if (parts.length > 0) {
                    parts.sort((a, b) => b.length - a.length);
                    s = parts[0];
                }
            }

            s = s.replace(/^\(\s*\d+\s*\)\s*/, '');
            s = s.replace(/^\d+\s+/, '');
            s = s.replace(/^(.+?)\s+\1$/, '$1');
            s = s.replace(/\s+/g, ' ').trim();

            return s.toLowerCase();
        } catch (_) {
            return String(name).toLowerCase();
        }
    }

    selectObject(objectName, showDialog = false) {
        console.log(`Selecting object: ${objectName}`);
        if (this.celestialData?.bodies[objectName]) {
            this.selectedObject = this.celestialData.bodies[objectName];
            
            // Highlight the object in the list
            const listItems = document.querySelectorAll('#objectList li');
            listItems.forEach(item => {
                if (item.dataset.name === objectName) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }
            });
            
            // Highlight the object in the sky
            this.render();
            
            // Nur Dialog anzeigen, wenn showDialog true ist
            if (showDialog) {
                this.showObjectDialog(this.selectedObject);
            }
            return true;
        }
        console.log(`Object ${objectName} not found in celestial data`);
        return false;
    }
    
    highlightObject(objectName) {
        // Setze das ausgewählte Objekt, ohne einen Dialog anzuzeigen
        this.selectObject(objectName, false);
    }
    
    removeDialog() {
        const dialog = document.getElementById('object-dialog');
        if (dialog) dialog.remove();
    }
    
    // Positioniert einen Dialog je nach Bildschirmgröße
    positionDialog(dialog) {
        const isMobile = window.innerWidth <= 768;
        const skyRect = this.container.getBoundingClientRect();
        
        if (!isMobile) {
            // Desktop: Neben der Himmelsansicht
            dialog.style.top = `${skyRect.top}px`;
            dialog.style.left = `${skyRect.right + 10}px`; // 10px Abstand zur rechten Kante
            // Entferne mobile-spezifische Styles
            dialog.style.transform = '';
        }
        // Mobile: Overlay wird durch CSS positioniert
    }

    clearSelection() {
        this.removeDialog();
        this.selectedObject = null;
        // Nutze den normalen Renderpfad, damit auch die Pfeile erhalten bleiben
        this.render();
    }

    setupEventListeners() {
        // Handle click on the sky to select objects
        this.container.addEventListener('click', (e) => {
            // If a drag just finished, suppress the immediate click to avoid mis-selection
            if (this._suppressNextClick) {
                this._suppressNextClick = false;
                return;
            }
            console.log('Click event detected on sky container');
            const skyEl = this.container.querySelector('.sky-text');
            const rect = skyEl ? skyEl.getBoundingClientRect() : this.container.getBoundingClientRect();

            // If we have a sky element and click is outside of it, ignore to avoid wrong mapping
            if (skyEl) {
                const within = e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
                if (!within) {
                    return;
                }
            }

            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            // Convert click coordinates to grid position based on actual text box size
            const colWidth = rect.width / CONFIG.SKY_WIDTH;
            const rowHeight = rect.height / CONFIG.SKY_HEIGHT;

            const col = Math.floor(x / colWidth);
            const row = Math.floor(y / rowHeight);

            console.log(`Click at position: row=${row}, col=${col}`);
            console.log(`Sky content at position: ${this.sky[row]?.[col]}`);

            // Prüfe, ob der Klick auf ein überlappendes Symbol (*) erfolgte
            const isOverlappingSymbol = this.sky[row]?.[col] === '*';

            // Direkter Zugriff auf die Himmelskörper und Prüfung der Nähe zum Klick
            if (this.celestialData) {
                // Sammle alle Objekte in der Nähe des Klicks
                const nearbyObjects = [];
                const maxDistance = isOverlappingSymbol ? 0.5 : 5; // Kleinere Distanz für überlappende Objekte

                // Prüfe, ob der Klick im Menübereich war
                const isMenuClick = document.getElementById('object-list')?.contains(e.target);
                if (isMenuClick) {
                    console.log('Click detected in menu area, not showing dialog');
                    return; // Beende die Funktion, wenn im Menü geklickt wurde
                }

                for (const [name, obj] of Object.entries(this.celestialData.bodies)) {
                    // Berücksichtige Sichtbarkeit basierend auf Höhe und Konfiguration
                    if (CONFIG.SHOW_BELOW_HORIZON || obj.altitude >= 0) {
                        // Verwende die gespeicherte Position, wenn vorhanden
                        const objRow = obj.displayRow !== undefined ? obj.displayRow :
                            (obj.altitude >= 0) ?
                                Math.round(CONFIG.HORIZON_ROW - (obj.altitude / 90 * CONFIG.HORIZON_ROW)) :
                                Math.round(CONFIG.HORIZON_ROW + (Math.abs(obj.altitude) / 90 * (CONFIG.SKY_HEIGHT - CONFIG.HORIZON_ROW - 1)));

                        let effectiveAzimuth = obj.azimuth - this.horizontalShift;

                        // Normalisiere den Azimut auf den Bereich 0-360
                        while (effectiveAzimuth < 0) effectiveAzimuth += 360;
                        while (effectiveAzimuth >= 360) effectiveAzimuth -= 360;

                        const objCol = obj.displayCol !== undefined ? obj.displayCol :
                            Math.round((effectiveAzimuth / 360) * (CONFIG.SKY_WIDTH - 2)) + 1;

                        // Berechne Distanz zum Klick
                        const distance = Math.sqrt(Math.pow(row - objRow, 2) + Math.pow(col - objCol, 2));
                        console.log(`Distance to ${name}: ${distance} (at row=${objRow}, col=${objCol})`);

                        // Bei überlappenden Objekten oder wenn die Distanz klein genug ist
                        if (distance <= maxDistance ||
                            (isOverlappingSymbol && objRow === row && objCol === col)) {
                            nearbyObjects.push({
                                name,
                                obj,
                                distance
                            });
                        }
                    }
                }

                // Sortiere nach Distanz
                nearbyObjects.sort((a, b) => a.distance - b.distance);

                // Entferne Duplikate (gleicher Objektname, nach Normalisierung), behalte den nächsten Eintrag
                const seenNames = new Set();
                const uniqueNearby = [];
                for (const item of nearbyObjects) {
                    const rawName = item.obj && item.obj.name ? item.obj.name : item.name;
                    const key = this.normalizeNameKey(rawName);
                    if (!seenNames.has(key)) {
                        seenNames.add(key);
                        uniqueNearby.push(item);
                    }
                }

                if (uniqueNearby.length > 0) {
                    console.log(`Found ${uniqueNearby.length} nearby objects:`,
                        uniqueNearby.map(item => item.name).join(', '));

                    if (uniqueNearby.length === 1) {
                        // Nur ein Objekt gefunden
                        this.selectObject(uniqueNearby[0].name, true);
                    } else {
                        // Mehrere Objekte gefunden - zeige Dialog mit allen Objekten
                        this.showMultiObjectDialog(uniqueNearby.map(item => item.obj));
                    }
                    return;
                }
            }

            // Wenn kein Objekt in der Nähe gefunden wurde
            console.log('No object near click position, clearing selection');
            this.clearSelection();
        });

        // Pan functionality for zoomed view
        this.setupPanEvents();

        // Touch events for sky navigation
        this.setupTouchEvents();

        // Keyboard controls for horizon panning
        this.setupKeyboardControls();
    }

    // Keyboard navigation: ArrowLeft/ArrowRight pan the horizon in 5° steps
    setupKeyboardControls() {
        // Bind once per instance
        if (this._keyboardSetup) return;
        this._keyboardSetup = true;

        document.addEventListener('keydown', (e) => {
            try {
                // Ignore when focused on text inputs or editable elements
                const tag = (document.activeElement && document.activeElement.tagName) ? document.activeElement.tagName.toLowerCase() : '';
                const isEditable = document.activeElement && (document.activeElement.isContentEditable || tag === 'input' || tag === 'textarea' || tag === 'select');
                if (isEditable) return;

                // Ignore when modifier keys are pressed to avoid clashes
                if (e.altKey || e.ctrlKey || e.metaKey) return;

                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    this.shiftHorizonLeft();
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    this.shiftHorizonRight();
                }
            } catch (_) { /* noop */ }
        });
    }

    setupPanEvents() {
        const skyEl = this.container.querySelector('.sky-text');
        if (!skyEl) return;

        // Throttle-Mechanismus für flüssigeres Rendering
        this._horizDragPending = false;
        this._horizDragScheduled = false;
        this._horizDragDirection = 0; // -1=links, 0=keine, 1=rechts
        
        // Hilfsfunktion für throttled horizon shift
        const throttledHorizonShift = () => {
            if (!this._horizDragPending) return;
            
            // Führe den anstehenden Shift aus
            if (this._horizDragDirection < 0) {
                this.shiftHorizonLeft();
            } else if (this._horizDragDirection > 0) {
                this.shiftHorizonRight();
            }
            
            // Markiere als erledigt
            this._horizDragPending = false;
            this._horizDragScheduled = false;
        };

        // Pan nur auf Desktop-Geräten aktivieren
        if (this.isMobileDevice()) {
            return;
        }

        // Mouse events for panning
        skyEl.addEventListener('mousedown', (e) => {
            // Start dragging always (vertical pan only when zoomed, horizontal pan always)
            this.isDragging = true;
            this.lastMouseY = e.clientY;
            this.lastMouseX = e.clientX;
            this._dragStartX = e.clientX;
            this._dragStartY = e.clientY;
            this._didDrag = false;
            // Accumulator for horizontal drag in pixels -> convert to 5° steps
            this._horizDragAccumPx = 0;
            // Reset throttling state
            this._horizDragPending = false;
            this._horizDragScheduled = false;
            this._horizDragDirection = 0;
            skyEl.style.cursor = 'grabbing';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;

            const factor = this.zoomLevels[this.zoomIndex] || 1;

            // Vertical drag only when zoomed
            if (factor > 1) {
                const deltaY = e.clientY - this.lastMouseY;
                this.verticalOffset += deltaY;
                
                // Limit vertical offset to reasonable bounds
                const maxOffset = CONFIG.SKY_HEIGHT * 10; // Allow scrolling beyond visible area
                this.verticalOffset = Math.max(-maxOffset, Math.min(maxOffset, this.verticalOffset));
                
                this.lastMouseY = e.clientY;
            }

            // Horizontal drag -> pan horizon in 5° steps (same as arrow buttons), always active
            {
                const deltaX = e.clientX - this.lastMouseX;
                this._horizDragAccumPx += deltaX;
                this.lastMouseX = e.clientX;
                // Mark as drag if movement exceeds small threshold
                if (!this._didDrag) {
                    const totalDx = Math.abs(e.clientX - (this._dragStartX || e.clientX));
                    const totalDy = Math.abs(e.clientY - (this._dragStartY || e.clientY));
                    if (totalDx > 3 || totalDy > 3) this._didDrag = true;
                }

                // Convert pixels to degrees based on current sky element width
                const rect = skyEl.getBoundingClientRect();
                const stepPx = rect.width * (5 / 360); // 5° step size in pixels
                if (stepPx > 0) {
                    // Apply as many 5° steps as accumulated, but throttle to animation frames
                    while (Math.abs(this._horizDragAccumPx) >= stepPx) {
                        // Bestimme die Richtung für den nächsten Shift
                        const direction = this._horizDragAccumPx > 0 ? -1 : 1; // -1=links, 1=rechts
                        
                        // Reduziere den Akkumulator
                        if (this._horizDragAccumPx > 0) {
                            this._horizDragAccumPx -= stepPx;
                        } else {
                            this._horizDragAccumPx += stepPx;
                        }
                        
                        // Merke die letzte Richtung und markiere als anstehend
                        this._horizDragDirection = direction;
                        this._horizDragPending = true;
                        
                        // Schedule nur einmal pro Frame
                        if (!this._horizDragScheduled) {
                            this._horizDragScheduled = true;
                            requestAnimationFrame(throttledHorizonShift);
                        }
                    }
                }
            }

            this.applyVerticalOffset();
            e.preventDefault();
        });

        document.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                const skyEl = this.container.querySelector('.sky-text');
                if (skyEl) {
                    const factor = this.zoomLevels[this.zoomIndex] || 1;
                    skyEl.style.cursor = factor > 1 ? 'grab' : 'default';
                }
                // Reset horizontal accumulator
                this._horizDragAccumPx = 0;
                // Clear any pending drag operations
                this._horizDragPending = false;
                this._horizDragScheduled = false;
                this._horizDragDirection = 0;
                // Prevent click selection immediately after a drag
                if (this._didDrag) {
                    this._suppressNextClick = true;
                    // Reset flag shortly after to only suppress the immediate click
                    setTimeout(() => { this._suppressNextClick = false; }, 50);
                }
            }
        });

        // Prevent context menu on right click during pan
        skyEl.addEventListener('contextmenu', (e) => {
            const factor = this.zoomLevels[this.zoomIndex] || 1;
            if (factor > 1) {
                e.preventDefault();
            }
        });
    }

    applyVerticalOffset() {
        const skyEl = this.container.querySelector('.sky-text');
        if (skyEl) {
            skyEl.style.transform = `translateY(${this.verticalOffset}px)`;
        }
        
        // Auch die Labels verschieben
        const labelsLayer = this.container.querySelector('.labels-layer');
        if (labelsLayer) {
            labelsLayer.style.transform = `translateY(${this.verticalOffset}px)`;
        }
        
        // Auch die Sternbilder-SVG-Layer verschieben
        const constellationLayer = this.container.querySelector('#constellation-layer');
        if (constellationLayer) {
            constellationLayer.style.transform = `translateY(${this.verticalOffset}px)`;
        }
    }

    setupTouchEvents() {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchStartTime = 0;
        const minSwipeDistance = 50; // Minimum distance for a swipe in pixels
        const maxTapDuration = 300; // Maximum duration for a tap in milliseconds

        this.container.addEventListener('touchstart', (e) => {
            // Store the initial touch position and time
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = Date.now();
        }, { passive: true });

        this.container.addEventListener('touchend', (e) => {
            // Calculate touch duration
            const touchDuration = Date.now() - touchStartTime;
            
            // Get the final touch position
            const touchEndX = e.changedTouches[0].clientX;
            const touchEndY = e.changedTouches[0].clientY;
            
            // Calculate the horizontal distance moved
            const touchDistanceX = touchEndX - touchStartX;
            
            // If it's a short tap (not a swipe), let the click handler take care of it
            if (touchDuration < maxTapDuration && Math.abs(touchDistanceX) < minSwipeDistance) {
                return;
            }
            
            // If it's a horizontal swipe with enough distance
            if (Math.abs(touchDistanceX) >= minSwipeDistance) {
                // Prevent the default behavior (page scrolling)
                e.preventDefault();
                
                if (touchDistanceX > 0) {
                    // Swipe right -> shift horizon left
                    this.shiftHorizonLeft();
                } else {
                    // Swipe left -> shift horizon right
                    this.shiftHorizonRight();
                }
            }
        });

        // Prevent default on touchmove to avoid page scrolling while swiping
        this.container.addEventListener('touchmove', (e) => {
            const touchCurrentX = e.touches[0].clientX;
            const touchDistanceX = touchCurrentX - touchStartX;
            
            // If it seems like a horizontal swipe, prevent default scrolling
            if (Math.abs(touchDistanceX) > Math.abs(e.touches[0].clientY - touchStartY)) {
                e.preventDefault();
            }
        }, { passive: false });
    }

    // Formatiert einen Zeitstring im ISO-Format in das Format HH:MM
    formatTimeString(timeString) {
        try {
            // Wenn es ein ISO-Zeitstring ist
            if (timeString && timeString.includes('T')) {
                const date = new Date(timeString);
                // Lokale Zeit im Format HH:MM
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
            }
            // Wenn es bereits ein formatierter String ist, gib ihn unverändert zurück
            return timeString;
        } catch (e) {
            console.error('Error formatting time:', e);
            return timeString; // Fallback zum ursprünglichen String
        }
    }

    // Baut ein sauber lokalisiertes Zeitlabel (fügt 'Uhr' nur einmal hinzu und trimmt Leerzeichen)
    buildTimeLabel(timeValue) {
        try {
            if (!timeValue) return '';
            const s = this.formatTimeString(timeValue);
            if (!s) return '';
            const needsSuffix = !/[A-Za-zÀ-ÖØ-öø-ÿ]/.test(s);
            return (needsSuffix ? `${s} ${t('hour')}` : s).trim();
        } catch (_) {
            return String(timeValue);
        }
    }

    buildObjectInfoLines(obj) {
        if (!obj) return [];
        const displayName = this.getLocalizedDisplayName(obj.name);
        const info = [
            `${obj.symbol || ''} ${displayName}`.trim(),
            `${t('altitude')}: ${obj.altitude?.toFixed ? obj.altitude.toFixed(1) : obj.altitude}°`,
            `${t('azimuth')}: ${obj.azimuth?.toFixed ? obj.azimuth.toFixed(1) : obj.azimuth}°`,
            `${t('distance')}: ${obj.distance?.toFixed ? obj.distance.toFixed(3) : obj.distance} ${t('au')}`
        ];

        if (obj.rise_time) {
            const label = this.buildTimeLabel(obj.rise_time);
            info.push(`${t('rise_time')}: ${label}`);
        }

        if (obj.transit_time) {
            const label = this.buildTimeLabel(obj.transit_time);
            info.push(`${t('transit_time')}: ${label}`);
        }

        if (obj.set_time) {
            const label = this.buildTimeLabel(obj.set_time);
            info.push(`${t('set_time')}: ${label}`);
        }

        if (obj.phase !== undefined) {
            const phaseName = obj.phase_name ? t(obj.phase_name) : '';
            const phaseValue = (typeof obj.phase === 'number') ? (obj.phase * 100).toFixed(1) : obj.phase;
            info.push(`${t('phase')}: ${phaseValue}% ${phaseName}`.trim());
        }

        if (obj.magnitude !== undefined) {
            const mag = obj.magnitude?.toFixed ? obj.magnitude.toFixed(1) : obj.magnitude;
            info.push(`${t('magnitude')}: ${mag}`);
        }

        return info;
    }

    refreshDialogIfVisible() {
        try {
            if (!this.selectedObject) return;
            const dialog = document.getElementById('object-dialog');
            if (!dialog) return;
            const content = dialog.querySelector('#dialog-content') || dialog.querySelector('.object-data');
            if (!content) return;
            const fresh = (this.celestialData && this.celestialData.bodies) ? this.celestialData.bodies[this.selectedObject.name] : null;
            if (fresh) {
                this.selectedObject = fresh;
            }
            const info = this.buildObjectInfoLines(this.selectedObject);
            content.innerHTML = info.join('\n');
            this.render();
        } catch (error) {
            console.error('Error refreshing object dialog:', error);
        }
    }

    showObjectDialog(obj) {
        console.log('Showing dialog for:', obj.name, obj);
        
        try {
            // Entferne vorhandenen Dialog, falls vorhanden
            const existingDialog = document.getElementById('object-dialog');
            if (existingDialog) {
                existingDialog.remove();
            }
            
            // Stelle sicher, dass die Dialog-Styles geladen sind
            if (!document.querySelector('link[href="/static/css/dialogStyles.css"]')) {
                const linkElem = document.createElement('link');
                linkElem.rel = 'stylesheet';
                linkElem.href = '/static/css/dialogStyles.css';
                document.head.appendChild(linkElem);
            }
            
            // Dialog-Inhalt erstellen
            const info = this.buildObjectInfoLines(obj);
            // Erstelle den Dialog
            const dialog = document.createElement('div');
            dialog.id = 'object-dialog';
            dialog.innerHTML = `
                <button id="dialog-close">${t('close')}</button>
                <div id="dialog-content">${info.join('\n')}</div>
            `;
            
            // Füge den Dialog zum Body hinzu
            document.body.appendChild(dialog);
            
            // Positioniere den Dialog je nach Bildschirmgröße
            const isMobile = window.innerWidth <= 768;
            const skyRect = this.container.getBoundingClientRect();
            
            if (!isMobile) {
                // Desktop: Neben der Himmelsansicht
                dialog.style.top = `${skyRect.top}px`;
                dialog.style.left = `${skyRect.right + 10}px`;
            }
            
            // Close-Button-Event hinzufügen
            document.getElementById('dialog-close').addEventListener('click', () => {
                this.clearSelection();
            });
        } catch (error) {
            console.error('Error showing object info:', error);
        }
    }
    
    showMultiObjectDialog(objects) {
        if (!objects || objects.length === 0) return;
        
        try {
            // Entferne vorherige Dialoge
            this.removeDialog();
            
            // Entferne doppelte Einträge nach normalisiertem Namen
            const seen = new Set();
            const uniqueObjects = [];
            for (const o of objects) {
                const key = this.normalizeNameKey(o && o.name ? o.name : '');
                if (key && !seen.has(key)) {
                    seen.add(key);
                    uniqueObjects.push(o);
                }
            }

            // Erstelle einen neuen Dialog
            const dialog = document.createElement('div');
            dialog.className = 'object-dialog multi-object-dialog';
            dialog.id = 'object-dialog';
            
            // Dialog-Header mit Titel und Close-Button
            let dialogContent = `<div class="dialog-header"><h3>${t('multiple_objects_found')}</h3><button id="dialog-close">${t('close')}</button></div>`;
            
            // Füge Liste der Objekte hinzu
            dialogContent += '<div class="object-list">';
            uniqueObjects.forEach((obj, index) => {
                const displayName = this.getLocalizedDisplayName(obj.name);
                dialogContent += `<div class="object-list-item" data-object-name="${obj.name}">${obj.symbol || ''} ${displayName}</div>`;
            });
            dialogContent += '</div>';
            
            // Füge Trennlinie hinzu
            dialogContent += '<hr class="dialog-divider">';
            
            // Füge Datenbereich hinzu
            dialogContent += '<div class="object-data"></div>';
            
            dialog.innerHTML = dialogContent;
            
            // Füge den Dialog zum Body hinzu
            document.body.appendChild(dialog);
            
            // Positioniere den Dialog je nach Bildschirmgröße
            const isMobile = window.innerWidth <= 768;
            const skyRect = this.container.getBoundingClientRect();
            
            if (!isMobile) {
                // Desktop: Neben der Himmelsansicht
                dialog.style.top = `${skyRect.top}px`;
                dialog.style.left = `${skyRect.right + 10}px`;
            }
            
            // Lade die externen Styles für den Dialog
            const linkElem = document.createElement('link');
            linkElem.rel = 'stylesheet';
            linkElem.href = '/static/css/dialogStyles.css';
            document.head.appendChild(linkElem);
            
            // Event-Listener für den Close-Button
            const closeButton = dialog.querySelector('#dialog-close');
            closeButton.addEventListener('click', () => {
                this.clearSelection();
            });
            
            // Event-Listener für die Objektliste
            const listItems = dialog.querySelectorAll('.object-list-item');
            const dataContainer = dialog.querySelector('.object-data');
            
            // Funktion zum Anzeigen der Objektdaten
            const showObjectData = (objectName) => {
                // Finde das ausgewählte Objekt
                const selectedObject = uniqueObjects.find(obj => obj.name === objectName);
                if (!selectedObject) return;
                
                // Erstelle Informationstext
                const displayName = this.getLocalizedDisplayName(selectedObject.name);
                const info = this.buildObjectInfoLines(selectedObject);
                // Aktualisiere den Datenbereich
                dataContainer.innerHTML = info.join('\n');
                
                // Setze das ausgewählte Objekt für die Labelanzeige
                this.selectedObject = selectedObject;
                
                // Hebe das entsprechende Objekt im Himmel hervor und zeige das Label an
                this.render(); // Neu rendern, um das Label anzuzeigen
                
                // Markiere das ausgewählte Element in der Liste
                listItems.forEach(item => {
                    if (item.getAttribute('data-object-name') === objectName) {
                        item.classList.add('active');
                    } else {
                        item.classList.remove('active');
                    }
                });
            };
            
            // Füge Event-Listener zu den Listeneinträgen hinzu
            listItems.forEach(item => {
                item.addEventListener('click', () => {
                    const objectName = item.getAttribute('data-object-name');
                    showObjectData(objectName);
                });
            });
            
            // Zeige das erste Objekt standardmäßig an
            if (uniqueObjects.length > 0) {
                showObjectData(uniqueObjects[0].name);
            }
        } catch (error) {
            console.error('Error showing multi-object dialog:', error);
        }
    }

    // Methode zum Setzen der Magnitude-Filter wurde entfernt
    
    // Methode zum Laden von Asteroiden
    async loadAsteroids(token) {
        try {
            // Erstelle die URL mit Standortparametern
            let url = `${API_ENDPOINTS.ASTEROIDS}?nocache=1`;
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += `&lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
            }
            
            url = this.appendTimeParam(url);
            const response = await fetch(url, { cache: 'no-store' });
            if (!response.ok) {
                throw new Error(`HTTP error loading asteroids! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`Loaded ${data.bodies ? Object.keys(data.bodies).length : 0} asteroids`);
            
            // Falls dieses Update veraltet ist, breche ab
            if (!this.isActiveUpdate(token)) return;

            // Füge die Asteroiden zu den Himmelsdaten hinzu
            if (data && data.bodies && this.celestialData && this.celestialData.bodies) {
                this.celestialData.bodies = { ...this.celestialData.bodies, ...data.bodies };
                if (this.selectedObject && this.selectedObject.name && data.bodies[this.selectedObject.name]) {
                    this.selectedObject = data.bodies[this.selectedObject.name];
                    this.refreshDialogIfVisible();
                }
            }
        } catch (error) {
            console.error('Error loading asteroids:', error);
        }
    }
    
    // Methode zum Laden von Kometen
    async loadComets(token) {
        try {
            // Erstelle die URL mit Standortparametern
            let url = `${API_ENDPOINTS.COMETS}?nocache=1`;
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += `?lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
            }
            
            url = this.appendTimeParam(url);
            const response = await fetch(url, { cache: 'no-store' });
            if (!response.ok) {
                throw new Error(`HTTP error loading comets! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`Loaded ${data.bodies ? Object.keys(data.bodies).length : 0} comets`);
            
            // Falls dieses Update veraltet ist, breche ab
            if (!this.isActiveUpdate(token)) return;

            // Füge die Kometen zu den Himmelsdaten hinzu
            if (data && data.bodies && this.celestialData && this.celestialData.bodies) {
                this.celestialData.bodies = { ...this.celestialData.bodies, ...data.bodies };
                if (this.selectedObject && this.selectedObject.name && data.bodies[this.selectedObject.name]) {
                    this.selectedObject = data.bodies[this.selectedObject.name];
                    this.refreshDialogIfVisible();
                }
            }
        } catch (error) {
            console.error('Error loading comets:', error);
        }
    }

    startAutoUpdate() {
        this.update();
        this.updateInterval = setInterval(() => this.update(), CONFIG.UPDATE_INTERVAL_MS);
    }

    stopAutoUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
    }
    
    // Lade Himmelsdaten und aktualisiere die Anzeige (deprecated – nutzt update())
    async updateSkyData() {
        // Vereinheitlichte Update-Logik verwenden, damit Renderpfad konsistent bleibt
        return this.update();
    }

    // Methode zum Aktualisieren der Himmelsdaten
    async update() {
        try {
            // Verhindere mehrfache parallele Updates
            if (this._updateRunning) {
                console.log('Update already in progress, skipping...');
                return;
            }
            this._updateRunning = true;
            
            console.log('Updating sky data...');
            // Zeige allgemeinen Ladeindikator früh, um langsame Starts (z.B. MPCORB-Download) zu signalisieren
            this.showLoading('loading');
            // Neuer Update-Token: nur die neueste Update-Runde darf Daten anwenden
            const token = ++this._updateCounter;
            this._activeUpdate = token;
            
            // Hole die aktuellen Standortdaten
            const location = settingsManager.getLocation();
            // Halte Instanz-Location synchron, da Hilfsloader (Asteroiden/Kometen) darauf zugreifen
            this.location = location;
            
            // Lade die Basisdaten (Sonne, Mond, Planeten)
            {
                let url = `${API_ENDPOINTS.SKY}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}&nocache=1`;
                url = this.appendTimeParam(url);
                const response = await fetch(url, { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error(`HTTP error loading sky data! status: ${response.status}`);
                }
                const data = await response.json();
                // Abbrechen, wenn veraltetes Update
                if (!this.isActiveUpdate(token)) return;
                this.celestialData = data;
                if (this.selectedObject && this.selectedObject.name && data.bodies && data.bodies[this.selectedObject.name]) {
                    this.selectedObject = data.bodies[this.selectedObject.name];
                }
                // Rendere sofort die Himmelskörper (Planeten etc.), um First Paint zu beschleunigen
                this.render();
                this.refreshDialogIfVisible();
                // Aktualisiere die Visible Objects Liste sofort mit Planeten
                try {
                    const { updateVisibleObjectsList } = await import('./visibleObjectsList.js');
                    updateVisibleObjectsList(this.celestialData);
                } catch (e) {
                    console.error('Error updating visible objects list (first paint):', e);
                }
                // Verberge den allgemeinen Ladeindikator bereits nach dem ersten Paint
                // (Asteroiden/Kometen werden ggf. separat nachgeladen oder im Hintergrund vorbereitet)
                this.hideLoading();
            }
            
            // Prüfe Cache-Verfügbarkeit und lade nur, was bereits vorliegt; fehlendes im Hintergrund anstoßen
            const avail = await this.checkCacheAvailability(this.location);
            const availableAsteroids = !!(avail && avail.available && avail.available.asteroids);
            const availableComets = !!(avail && avail.available && avail.available.comets);
            const timeISO = (avail && avail.time) ? avail.time : (settingsManager.getSimulatedTimeISO && settingsManager.getSimulatedTimeISO());
            const locKey = (avail && avail.location && avail.location.loc_key) ? avail.location.loc_key : undefined;

            // Entferne alte Asteroiden/Kometen-Einträge BEVOR neue geladen werden
            // (verhindert Duplikate bei parallel laufenden Updates)
            if (this.celestialData && this.celestialData.bodies) {
                const cleanBodies = {};
                for (const [key, value] of Object.entries(this.celestialData.bodies)) {
                    // Behalte nur Planeten, Sonne, Mond - entferne Asteroiden und Kometen
                    if (!key.startsWith('bright_asteroid_') && !key.startsWith('comet_')) {
                        cleanBodies[key] = value;
                    }
                }
                this.celestialData.bodies = cleanBodies;
            }

            const tasks = [];
            // ALWAYS load asteroids and comets, regardless of cache status
            // They should be visible at all times like planets
            tasks.push(this.loadAsteroids(token));
            tasks.push(this.loadComets(token));
            
            // Load zodiac constellations if enabled
            if (this.zodiacRenderer) {
                tasks.push(this.loadZodiacData(token, this.location, timeISO));
            }

            // If cache is missing, trigger background precompute for future
            const missing = [];
            if (!availableAsteroids) missing.push('asteroids');
            if (!availableComets) missing.push('comets');
            if (missing.length > 0) {
                console.log(`Cache missing for: ${missing.join(', ')} - triggering background computation`);
                this.triggerPrecomputeWindowIfNeeded(this.location, timeISO, missing, locKey);
            }

            // Warte optional auf geladene Zusatzdaten und rendere erneut
            if (tasks.length > 0) {
                await Promise.all(tasks);
                if (this.isActiveUpdate(token)) {
                    this.render();
                    this.refreshDialogIfVisible();
                }
            }
            
            // Aktualisiere die Visible Objects Liste
            try {
                const { updateVisibleObjectsList } = await import('./visibleObjectsList.js');
                updateVisibleObjectsList(this.celestialData);
            } catch (e) {
                console.error('Error updating visible objects list:', e);
            }
            
            // Aktualisiere die Anzeige
            // Hinweis: Erste Render erfolgte bereits nach den Celestial-Daten
            
        } catch (error) {
            console.error('Error updating sky data:', error);
            this.container.textContent = t('error_loading');
        } finally {
            // Verstecke den Ladeindikator am Ende des gesamten Update-Zyklus
            this.hideLoading();
            // Erlaube neue Updates
            this._updateRunning = false;
        }
    }
    
    async loadZodiacData(token, location, timeISO) {
        try {
            if (this.zodiacRenderer) {
                await this.zodiacRenderer.fetchZodiacData(location, timeISO);
                if (this.isActiveUpdate(token)) {
                    this.zodiacRenderer.updatePositions();
                }
            }
        } catch (error) {
            console.error('Error loading zodiac data:', error);
        }
    }
}
