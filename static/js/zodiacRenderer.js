/**
 * ZodiacRenderer - Renders zodiac constellations as SVG overlay
 */

import { API_ENDPOINTS, CONFIG } from './constants.js';
import { t } from './i18n.js';

export class ZodiacRenderer {
    // Konstanten für Sternbild-Filter
    static MIN_ALTITUDE_DEG = 10;      // Nur Sterne deutlich über dem Horizont
    static MAX_AZ_SEPARATION_DEG = 30; // Sehr strikt: nur lokale Verbindungen
    static MAX_ALT_SEPARATION_DEG = 40; // Nicht zu steile Verbindungen
    static DEBUG_GRID = true;          // Wenn true, wird ein Hilfsraster gezeichnet
    
    constructor(skyRenderer) {
        this.skyRenderer = skyRenderer;
        this.constellations = [];
        this.visible = false;
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
            
        } catch (error) {
            console.error('Error fetching zodiac data:', error);
            this.constellations = [];
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
        for (const constellation of this.constellations) {
            this.renderSVGConstellation(constellation, offsetX, offsetY, skyWidth, skyHeight);
        }
    }
    
    /**
     * Render a single constellation in SVG
     */
    renderSVGConstellation(constellation, offsetX, offsetY, skyWidth, skyHeight) {
        // Prüfe, ob genug Sterne des Sternbilds sichtbar sind (mind. 50%)
        const constellationVisibleStars = constellation.stars.filter(s => s.altitude > ZodiacRenderer.MIN_ALTITUDE_DEG);
        if (constellationVisibleStars.length < constellation.stars.length * 0.5) {
            // Zu wenig sichtbare Sterne - Sternbild nicht zeichnen
            return;
        }
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
            if (!gridPos) continue;
            
            // Konvertiere zu Pixel-Koordinaten (Zellmitte)
            const cellW = skyWidth / CONFIG.SKY_WIDTH;
            const cellH = skyHeight / CONFIG.SKY_HEIGHT;
            // Exakte Zellmitte für präzise Ausrichtung
            const x = gridPos.col * cellW + (cellW / 2);
            const y = gridPos.row * cellH + (cellH / 2);
            
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
            starCircle.setAttribute('opacity', star.visible ? '0.8' : '0.3');
            group.appendChild(starCircle);
        }
        
        // 2. Zeichne Verbindungslinien zwischen den Sternen
        // NEOWISE-Ansatz: Strenge Filter für natürlich aussehende Sternbilder
        // 1. Kleine azimutale Trennung (keine Diagonalen quer über die Karte)
        // 2. Nur Sterne über Mindesthöhe verbinden
        // 3. Nicht zu große Höhenunterschiede
        
        for (const [star1Id, star2Id] of constellation.lines) {
            const star1 = starPositions.find(s => s.hip_id === star1Id);
            const star2 = starPositions.find(s => s.hip_id === star2Id);
            
            // Beide Sterne müssen vorhanden sein
            if (!star1 || !star2) continue;

            // Beide Endpunkte müssen über der Mindesthöhe sein
            if (star1.altitude < ZodiacRenderer.MIN_ALTITUDE_DEG || star2.altitude < ZodiacRenderer.MIN_ALTITUDE_DEG) continue;

            // Azimut- und Altitude-Trennung prüfen
            const dAz = Math.abs(star2.azimuth - star1.azimuth);
            const azSeparation = Math.min(dAz, 360 - dAz);
            if (azSeparation > ZodiacRenderer.MAX_AZ_SEPARATION_DEG) continue;
            if (Math.abs(star2.altitude - star1.altitude) > ZodiacRenderer.MAX_ALT_SEPARATION_DEG) continue;

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
            // Schwächere Linien für unsichtbare Sterne
            const opacity = (star1.visible && star2.visible) ? '0.7' : '0.3';
            line.setAttribute('opacity', opacity);
            group.appendChild(line);
        }
        
        // 3. Label in der Mitte der sichtbaren Sterne
        // Nur Sterne über der Mindesthöhe für Label-Positionierung verwenden
        const visibleStars = starPositions.filter(s => s.altitude > ZodiacRenderer.MIN_ALTITUDE_DEG);
        if (visibleStars.length > 0) {
            const centerX = visibleStars.reduce((sum, s) => sum + s.x, 0) / visibleStars.length;
            const centerY = visibleStars.reduce((sum, s) => sum + s.y, 0) / visibleStars.length;
            
            const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            label.setAttribute('x', centerX);
            label.setAttribute('y', centerY - 15);
            label.textContent = constellation.name_de || constellation.name;
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
        return this.skyRenderer.altAzToGridPosition(altitude, azimuth);
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
                (t('hide_constellations') || 'Sternbilder ausblenden') :
                (t('show_constellations') || 'Sternbilder anzeigen');
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
