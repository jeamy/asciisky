/**
 * ZodiacRenderer - Renders zodiac constellations as SVG overlay
 */

import { API_ENDPOINTS, CONFIG } from './constants.js';
import { t } from './i18n.js';

export class ZodiacRenderer {
    // Konstanten für Sternbild-Filter
    static MIN_ALTITUDE_DEG = -90;     // Alle Sterne anzeigen, auch weit unter dem Horizont
    static MAX_AZ_SEPARATION_DEG = 180; // Keine Beschränkung der Azimut-Trennung mehr
    static MAX_ALT_SEPARATION_DEG = 180; // Keine Beschränkung der Höhen-Trennung mehr
    static DEBUG_GRID = false;          // Deaktiviert für normale Nutzung
    
    constructor(skyRenderer) {
        this.skyRenderer = skyRenderer;
        this.constellations = [];
        // Default Sichtbarkeit aus Konfiguration übernehmen (standard: aus)
        this.visible = !!(CONFIG.CONSTELLATIONS && CONFIG.CONSTELLATIONS.DEFAULT_VISIBLE === true);
        this.svgLayer = null;
        this.toggleButton = null;
        
        this.initSVGLayer();
        this.createToggleButton();
    }

    /**
     * Initialize SVG layer for constellation rendering
     */
    initSVGLayer() {
        if (!CONFIG.CONSTELLATIONS?.ENABLE_CONSTELLATION_LAYER) return;
        
        const container = this.skyRenderer.container;
        if (!container) return;
        
        // Remove existing SVG layer if any
        const existingSVG = document.getElementById('constellation-layer');
        if (existingSVG) {
            existingSVG.remove();
        }
        
        // Load constellation CSS
        this.loadConstellationCSS();
        
        // Create SVG element
        this.svgLayer = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this.svgLayer.id = 'constellation-layer';
        this.svgLayer.setAttribute('class', this.visible ? 'visible' : '');
        
        container.appendChild(this.svgLayer);
    }
    
    /**
     * Load constellation CSS file
     */
    loadConstellationCSS() {
        const cssId = 'constellation-css';
        if (!document.getElementById(cssId)) {
            const head = document.getElementsByTagName('head')[0];
            const link = document.createElement('link');
            link.id = cssId;
            link.rel = 'stylesheet';
            link.type = 'text/css';
            link.href = '/static/css/constellations.css';
            head.appendChild(link);
        }
    }
    
    /**
     * Create toggle button for constellation visibility
     */
    createToggleButton() {
        // Button wird jetzt in setupObjectList() erstellt, nicht hier
        // Nur eine Referenz auf den existierenden Button holen
        this.toggleButton = document.getElementById('constellation-toggle');
    }

    /**
     * Fetch zodiac constellation data from the API
     * @param {Object} location - Location object with lat, lon, and elevation
     * @param {string} time - ISO time string (optional)
     * @returns {Promise} - Promise that resolves when data is fetched
     */
    async fetchZodiacData(location, time = null) {
        try {
            if (!location || location.latitude === undefined || location.longitude === undefined) {
                console.error('Invalid location data for zodiac:', location);
                return;
            }
            
            const params = new URLSearchParams({
                lat: location.latitude,
                lon: location.longitude,
                elevation: location.elevation || 0
            });
            // Ensure we bypass any previously cached 12-only result
            params.append('nocache', '1');
            
            if (time) {
                params.append('time', time);
            }
            
            const response = await fetch(`${API_ENDPOINTS.ZODIAC}?${params}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.constellations = data.constellations || [];
            console.debug(`[zodiac] fetched ${this.constellations.length} constellations`);
            if (this.constellations.length > 0) {
                const c0 = this.constellations[0];
                console.debug(`[zodiac] sample: ${c0.name} stars=${(c0.stars||[]).length} lines=${(c0.lines||[]).length}`);
            }
            
            // If visible, render immediately
            if (this.visible && this.constellations.length > 0) {
                this.renderSVGConstellations();
            }
            
            // Debug-Funktion optional aufrufbar
            // this.debugConstellations();
            
        } catch (error) {
            console.error('Error fetching zodiac data:', error);
            this.constellations = [];
        }
    }

    /**
     * Cleanup method to remove event listeners
     */
    cleanup() {
        if (this.resizeHandler) {
            window.removeEventListener('resize', this.resizeHandler);
            this.resizeHandler = null;
        }
    }
    
    /**
     * Zeigt alle Sternbilder an, unabhängig von ihrer Position
     */
    showAllConstellations() {
        // Aktiviere Sternbilder falls noch nicht aktiv
        if (!this.visible) {
            this.toggleVisibility();
        }
        
        // Setze MIN_ALTITUDE_DEG auf -90, um alle Sterne zu zeigen
        ZodiacRenderer.MIN_ALTITUDE_DEG = -90;
        
        // Rendere alle Sternbilder neu
        this.renderSVGConstellations();
        
    }
    
    /**
     * Debug-Funktion: Gibt alle Sternbilder und ihre Sterne in der Konsole aus
     */
    debugConstellations() {
        
        // Gruppiere nach Sichtbarkeit
        const visibleStars = {};
        const belowHorizonStars = {};
        
        for (const constellation of this.constellations) {
            const starsAbove = constellation.stars.filter(s => s.altitude >= 0).length;
            const starsBelow = constellation.stars.filter(s => s.altitude < 0).length;
            const totalStars = constellation.stars.length;
            const percentVisible = totalStars > 0 ? (starsAbove / totalStars * 100).toFixed(0) : 0;
            
            
            if (percentVisible >= 50) {
                visibleStars[constellation.name] = { starsAbove, totalStars, percentVisible };
            } else {
                belowHorizonStars[constellation.name] = { starsAbove, totalStars, percentVisible };
            }
        }
        
    }

    /**
     * Render constellations in SVG layer
     */
    renderSVGConstellations() {
        if (!this.svgLayer || !this.constellations || !this.visible) return;
        
        // Clear existing content
        this.svgLayer.innerHTML = '';
        
        const container = this.skyRenderer.container;
        const skyText = container.querySelector('.sky-text');
        if (!skyText) return;
        
        // Use offsetLeft/offsetTop to align inside flex-centered container reliably
        const offsetX = skyText.offsetLeft;
        const offsetY = skyText.offsetTop;
        const skyWidth = skyText.clientWidth;
        const skyHeight = skyText.clientHeight;
        
        // Set SVG dimensions to match sky area
        this.svgLayer.setAttribute('viewBox', `0 0 ${skyWidth} ${skyHeight}`);
        // Set explicit pixel size and position so it exactly matches .sky-text
        this.svgLayer.style.position = 'absolute';
        this.svgLayer.style.left = `${offsetX}px`;
        this.svgLayer.style.top = `${offsetY}px`;
        this.svgLayer.style.width = `${skyWidth}px`;
        this.svgLayer.style.height = `${skyHeight}px`;
        // Also set width/height attributes for SVG coordinate system
        this.svgLayer.setAttribute('width', `${skyWidth}`);
        this.svgLayer.setAttribute('height', `${skyHeight}`);
        
        // Optional: Draw debug grid to visualize cell boundaries
        if (ZodiacRenderer.DEBUG_GRID) {
            this.drawDebugGrid(skyWidth, skyHeight);
        }
        
        // Render all constellations
        console.debug(`[zodiac] render overlay at ${skyWidth}x${skyHeight}`);
        console.debug(`[zodiac] rendering ${this.constellations.length} constellations: ${this.constellations.map(c => c.name).join(', ')}`);
        
        // Sortiere Sternbilder nach Namen für bessere Übersicht
        const sortedConstellations = [...this.constellations].sort((a, b) => a.name.localeCompare(b.name));
        
        for (const constellation of sortedConstellations) {
            console.debug(`[zodiac] rendering constellation: ${constellation.name} (${constellation.name_de})`);
            this.renderSVGConstellation(constellation, 0, 0, skyWidth, skyHeight);
        }
    }
    
    /**
     * Render a single constellation in SVG
     */
    renderSVGConstellation(constellation, offsetX, offsetY, skyWidth, skyHeight) {
        // Zeige alle Sternbilder an, auch wenn alle Sterne unter dem Horizont sind
        // Wir filtern nur nach der absoluten Mindesthöhe
        const constellationVisibleStars = constellation.stars.filter(s => s.altitude > ZodiacRenderer.MIN_ALTITUDE_DEG);
        
        // Nur Debug-Ausgabe, aber keine Filterung mehr
        if (constellationVisibleStars.length === 0) {
            console.debug(`[zodiac] All stars in ${constellation.name} are below minimum altitude`);
        }
        
        // Debug: Zeige die sichtbaren Sterne und ihre IDs
        console.debug(`[zodiac] Visible stars in ${constellation.name}: ${constellationVisibleStars.map(s => s.hip_id).join(', ')}`);
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('class', 'constellation');
        group.setAttribute('data-name', constellation.name);
        
        // RICHTIG: Verwende die exakten Stern-Daten aus der API
        const starPositions = [];
        
        console.debug(`[zodiac] draw ${constellation.name}: stars=${(constellation.stars||[]).length}, lines=${(constellation.lines||[]).length}`);
        // 1. Zeichne alle Sterne des Sternbilds
        for (const star of constellation.stars) {
            // Verwende die exakten Altitude/Azimuth Werte aus der API
            const altitude = star.altitude;
            const azimuth = star.azimuth;
            
            // Konvertiere zu Grid-Position
            const gridPos = this.altAzToGridPosition(altitude, azimuth);
            if (!gridPos) {
                console.warn(`[zodiac] Failed to convert coordinates for star ${star.hip_id}: alt=${altitude.toFixed(2)}°, az=${azimuth.toFixed(2)}°`);
                continue;
            }
            
            // Debug: Zeige Koordinatenumrechnung
            console.debug(`[zodiac] Star ${star.hip_id}: alt=${altitude.toFixed(1)}°, az=${azimuth.toFixed(1)}° -> grid(${gridPos.row}, ${gridPos.col})`);
            
            // Konvertiere zu Pixel-Koordinaten (Zellmitte)
            const cellW = skyWidth / CONFIG.SKY_WIDTH;
            const cellH = skyHeight / CONFIG.SKY_HEIGHT;
            // Exakte Zellmitte für präzise Ausrichtung
            const x = gridPos.col * cellW + (cellW / 2);
            const y = gridPos.row * cellH + (cellH / 2);
            
            // Debug: Zeige Pixel-Koordinaten
            console.debug(`[zodiac] Star ${star.hip_id}: pixel(${x.toFixed(1)}, ${y.toFixed(1)}) cellSize(${cellW.toFixed(1)}, ${cellH.toFixed(1)})`);
            
            // Speichere Position und Winkel für Linien/Filter
            starPositions.push({
                hip_id: star.hip_id,
                x: x,
                y: y,
                magnitude: star.magnitude,
                visible: star.visible,
                azimuth: azimuth,
                altitude: altitude
            });
            
            // Zeichne Stern (auch unsichtbare, aber schwächer)
            const starCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            starCircle.setAttribute('cx', x);
            starCircle.setAttribute('cy', y);
            starCircle.setAttribute('r', this.getStarRadius(star.magnitude));
            
            // Unterschiedliche Darstellung für Sterne über/unter dem Horizont
            if (star.altitude < 0) {
                starCircle.classList.add('below-horizon');
            }
            
            group.appendChild(starCircle);
        }
        
        // 2. Zeichne Verbindungslinien zwischen den Sternen
        // NEOWISE-Ansatz: Strenge Filter für natürlich aussehende Sternbilder
        // 1. Kleine azimutale Trennung (keine Diagonalen quer über die Karte)
        // 2. Nur Sterne über Mindesthöhe verbinden
        // 3. Nicht zu große Höhenunterschiede
        
        // Debug: Zeige alle Linien-Definitionen
        console.debug(`[zodiac] ${constellation.name} (${constellation.name_de}) has ${constellation.lines.length} line definitions:`, 
                     constellation.lines.map(([a, b]) => `${a}-${b}`).join(', '));
        
        // Debug: Zeige alle Sternpositionen für dieses Sternbild
        console.debug(`[zodiac] ${constellation.name} (${constellation.name_de}) star positions:`, 
                     starPositions.map(s => `${s.hip_id}:(${s.x.toFixed(1)},${s.y.toFixed(1)}), alt:${s.altitude.toFixed(1)}`).join(', '));
        
        for (const [star1Id, star2Id] of constellation.lines) {
            const star1 = starPositions.find(s => s.hip_id === star1Id);
            const star2 = starPositions.find(s => s.hip_id === star2Id);
            
            // Beide Sterne müssen vorhanden sein
            if (!star1 || !star2) {
                console.warn(`[zodiac] Missing star in line ${star1Id}-${star2Id}. Available stars: ${starPositions.map(s => s.hip_id).join(', ')}`);
                continue;
            }
            
            // Debug: Zeige die Linie, die gezeichnet wird
            console.debug(`[zodiac] Drawing line ${star1Id}-${star2Id}: (${star1.x.toFixed(1)},${star1.y.toFixed(1)}) -> (${star2.x.toFixed(1)},${star2.y.toFixed(1)})`);

            // Alle Linien zeichnen, auch wenn beide Sterne unter dem Horizont sind
            // Wir filtern nur nach der minimalen Höhe, um extrem tief stehende Sterne auszuschließen
            if (star1.altitude < ZodiacRenderer.MIN_ALTITUDE_DEG || star2.altitude < ZodiacRenderer.MIN_ALTITUDE_DEG) {
                // Nur Debug-Ausgabe, aber keine Filterung mehr
                console.debug(`[zodiac] Line with stars below MIN_ALTITUDE: ${star1.hip_id}-${star2.hip_id}: ${star1.altitude.toFixed(1)}°, ${star2.altitude.toFixed(1)}°`);
            }

            // Keine Filterung nach Azimut oder Höhe mehr
            // Wir zeichnen alle Linien, wie sie in den äquatorialen Koordinaten definiert sind
            // Debug-Information für sehr weit entfernte Sterne
            const dAz = Math.abs(star2.azimuth - star1.azimuth);
            const azSeparation = Math.min(dAz, 360 - dAz);
            const altSeparation = Math.abs(star2.altitude - star1.altitude);
            
            if (azSeparation > 90 || altSeparation > 60) {
                console.debug(`[zodiac] Wide separation in line ${star1.hip_id}-${star2.hip_id}: azimuth=${azSeparation.toFixed(1)}°, altitude=${altSeparation.toFixed(1)}°`);
            }

            // Azimut-Wrap-around behandeln: kürzeste Verbindung wählen
            let x1 = star1.x;
            let y1 = star1.y;
            let x2 = star2.x;
            let y2 = star2.y;

            let dx = x2 - x1;
            // Wenn Differenz größer als die halbe Breite, über 0°/360°-Grenze korrigieren
            if (Math.abs(dx) > (skyWidth / 2)) {
                if (dx > 0) {
                    // Beispiel: x1=10, x2=790 (Breite ~800) -> Verbindung über linke Kante
                    x2 -= skyWidth;
                } else {
                    // Beispiel: x1=790, x2=10 -> Verbindung über rechte Kante
                    x2 += skyWidth;
                }
            }

            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x1);
            line.setAttribute('y1', y1);
            line.setAttribute('x2', x2);
            line.setAttribute('y2', y2);
            
            // Unterschiedliche Darstellung für Linien mit Sternen unter dem Horizont
            if (star1.altitude < 0 && star2.altitude < 0) {
                line.classList.add('both-below-horizon');
            } else if (star1.altitude < 0 || star2.altitude < 0) {
                line.classList.add('below-horizon');
            }
            
            group.appendChild(line);
        }
        
        // 3. Label in der Mitte der sichtbaren Sterne
        // Nur Sterne über der Mindesthöhe für Label-Positionierung verwenden
        const visibleStars = starPositions.filter(s => s.altitude > ZodiacRenderer.MIN_ALTITUDE_DEG);
        if (visibleStars.length > 0) {
            // Wrap-Aware Schwerpunkt in X:
            // Wenn sich Sterne beidseits der 0°/360°-Grenze befinden (große Spanne), verschiebe die kleineren X-Werte um +skyWidth,
            // bilde den Mittelwert und falte anschließend wieder in den sichtbaren Bereich zurück.
            const xs = visibleStars.map(s => s.x);
            const ys = visibleStars.map(s => s.y);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            let adjustedXs = xs.slice();
            if ((maxX - minX) > (skyWidth / 2)) {
                adjustedXs = xs.map(x => (x < skyWidth / 2) ? x + skyWidth : x);
            }
            let centerX = adjustedXs.reduce((sum, x) => sum + x, 0) / adjustedXs.length;
            // Zurück in den Bereich [0, skyWidth)
            while (centerX < 0) centerX += skyWidth;
            while (centerX >= skyWidth) centerX -= skyWidth;

            const centerY = ys.reduce((sum, y) => sum + y, 0) / ys.length;

            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', centerX);
            label.setAttribute('y', centerY - 15);
            // Verwende i18n-Übersetzung für Sternbildnamen, wenn verfügbar
            label.textContent = t(constellation.name) || constellation.name_de || constellation.name;
            group.appendChild(label);
        }
        
        this.svgLayer.appendChild(group);
    }
    
    /**
     * Convert altitude/azimuth to grid position
     */
    altAzToGridPosition(altitude, azimuth) {
        if (!this.skyRenderer || typeof this.skyRenderer.altAzToGridPosition !== 'function') {
            return null;
        }
        const result = this.skyRenderer.altAzToGridPosition(altitude, azimuth);
        // Debug: Zeige die Umrechnung im Detail
        if (result) {
            console.debug(`[zodiac] altAzToGridPosition: alt=${altitude.toFixed(2)}°, az=${azimuth.toFixed(2)}° -> row=${result.row}, col=${result.col}`);
        } else {
            console.warn(`[zodiac] altAzToGridPosition failed for alt=${altitude.toFixed(2)}°, az=${azimuth.toFixed(2)}°`);
        }
        return result;
    }
    
    /**
     * Get star radius based on magnitude
     */
    getStarRadius(magnitude) {
        if (magnitude < 1) return 3;
        if (magnitude < 2) return 2.5;
        if (magnitude < 3) return 2;
        if (magnitude < 4) return 1.5;
        return 1;
    }
    
    /**
     * Draw debug grid to visualize cell boundaries
     */
    drawDebugGrid(skyWidth, skyHeight) {
        if (!this.svgLayer) return;
        
        const gridGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        gridGroup.setAttribute('class', 'debug-grid');
        
        const cellW = skyWidth / CONFIG.SKY_WIDTH;
        const cellH = skyHeight / CONFIG.SKY_HEIGHT;
        
        // Draw vertical lines (columns)
        for (let col = 0; col <= CONFIG.SKY_WIDTH; col++) {
            const x = col * cellW;
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x);
            line.setAttribute('y1', 0);
            line.setAttribute('x2', x);
            line.setAttribute('y2', skyHeight);
            line.setAttribute('stroke', '#ff0000');
            line.setAttribute('stroke-width', '0.5');
            line.setAttribute('opacity', '0.2');
            gridGroup.appendChild(line);
            
            // Add column numbers at top
            if (col % 10 === 0) {
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', x + 2);
                text.setAttribute('y', 10);
                text.setAttribute('fill', '#ff0000');
                text.setAttribute('font-size', '8px');
                text.textContent = col.toString();
                gridGroup.appendChild(text);
            }
        }
        
        // Draw horizontal lines (rows)
        for (let row = 0; row <= CONFIG.SKY_HEIGHT; row++) {
            const y = row * cellH;
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', 0);
            line.setAttribute('y1', y);
            line.setAttribute('x2', skyWidth);
            line.setAttribute('y2', y);
            line.setAttribute('stroke', '#ff0000');
            line.setAttribute('stroke-width', '0.5');
            line.setAttribute('opacity', '0.2');
            gridGroup.appendChild(line);
            
            // Add row numbers at left
            if (row % 5 === 0) {
                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', 5);
                text.setAttribute('y', y + 10);
                text.setAttribute('fill', '#ff0000');
                text.setAttribute('font-size', '8px');
                text.textContent = row.toString();
                gridGroup.appendChild(text);
            }
        }
        
        // Add cell center dots for key positions
        for (let row = 0; row <= CONFIG.SKY_HEIGHT; row += 10) {
            for (let col = 0; col <= CONFIG.SKY_WIDTH; col += 10) {
                const x = col * cellW + (cellW / 2);
                const y = row * cellH + (cellH / 2);
                
                const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                dot.setAttribute('cx', x);
                dot.setAttribute('cy', y);
                dot.setAttribute('r', '1');
                dot.setAttribute('fill', '#00ff00');
                dot.setAttribute('opacity', '0.5');
                gridGroup.appendChild(dot);
            }
        }
        
        // Mark the horizon line
        const horizonY = CONFIG.HORIZON_ROW * cellH;
        const horizonLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        horizonLine.setAttribute('x1', 0);
        horizonLine.setAttribute('y1', horizonY);
        horizonLine.setAttribute('x2', skyWidth);
        horizonLine.setAttribute('y2', horizonY);
        horizonLine.setAttribute('stroke', '#00ff00');
        horizonLine.setAttribute('stroke-width', '1');
        horizonLine.setAttribute('opacity', '0.5');
        gridGroup.appendChild(horizonLine);
        
        this.svgLayer.appendChild(gridGroup);
    }

    /**
     * Toggle visibility of zodiac constellations
     * @returns {boolean} - New visibility state
     */
    toggleVisibility() {
        this.visible = !this.visible;
        
        // Check if SVG layer exists in DOM and update reference
        const svgInDOM = document.getElementById('constellation-layer');
        
        // Update reference if needed
        if (svgInDOM && svgInDOM !== this.svgLayer) {
            this.svgLayer = svgInDOM;
        }
        
        // Update SVG layer visibility
        if (this.svgLayer) {
            this.svgLayer.setAttribute('class', this.visible ? 'visible' : '');
        }
        
        // Update button appearance
        if (this.toggleButton) {
            this.toggleButton.classList.toggle('active', this.visible);
            this.toggleButton.title = this.visible ? 
                t('hide_constellations') :
                t('show_constellations');
        }
        
        // Re-render if visible
        if (this.visible && this.constellations.length > 0) {
            this.renderSVGConstellations();
        }
        
        return this.visible;
    }

    /**
     * Toggle debug grid visibility (for console debugging)
     */
    static toggleDebugGrid() {
        ZodiacRenderer.DEBUG_GRID = !ZodiacRenderer.DEBUG_GRID;
        console.debug(`[zodiac] Debug grid ${ZodiacRenderer.DEBUG_GRID ? 'enabled' : 'disabled'}`);
        return ZodiacRenderer.DEBUG_GRID;
    }
    
    /**
     * Update constellation positions (called when sky is re-rendered)
     */
    updatePositions() {
        // Update button reference (button is managed by setupObjectList)
        this.toggleButton = document.getElementById('constellation-toggle');

        // Ensure we have a reference to the existing layer in the DOM
        const layerInDOM = document.getElementById('constellation-layer');
        if (layerInDOM) {
            this.svgLayer = layerInDOM;
        } else {
            // Create once if missing
            this.initSVGLayer();
        }

        // Ensure correct visibility class is applied (CSS drives opacity)
        if (this.svgLayer) {
            this.svgLayer.classList.toggle('visible', !!this.visible);
        }

        if (this.visible && this.constellations.length > 0) {
            this.renderSVGConstellations();
        }
    }
}
