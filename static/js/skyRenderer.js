import { API_ENDPOINTS, CONFIG, ASCII_ART, ASTRO_CONSTANTS } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';

export class SkyRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.sky = [];
        this.celestialData = null;
        this.selectedObject = null;
        this.skyManager = null; // Wird später gesetzt
        
        // Lade gespeicherte Magnitude-Einstellungen oder verwende Defaults
        this.asteroidMaxMagnitude = settingsManager.getAsteroidMagnitude() || ASTRO_CONSTANTS.DEFAULT_ASTEROID_MAX_MAGNITUDE;
        this.cometMaxMagnitude = settingsManager.getCometMagnitude() || ASTRO_CONSTANTS.DEFAULT_COMET_MAX_MAGNITUDE;
        
        // Lade gespeicherte Standortdaten
        this.location = settingsManager.getLocation();
        
        console.log(`Loaded magnitude settings: Asteroids=${this.asteroidMaxMagnitude}, Comets=${this.cometMaxMagnitude}`);
        console.log(`Loaded location settings: lat=${this.location.latitude}, lon=${this.location.longitude}, elevation=${this.location.elevation}`);
        
        this.initSky();
        this.setupEventListeners();
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
        
        // Add cardinal directions along the horizon
        const directions = CONFIG.CARDINAL_DIRECTIONS;
        
        // Positionen für die vier Hauptrichtungen entlang des Horizonts
        // Azimut-Mapping: 0°=Nord, 90°=Ost, 180°=Süd, 270°=West
        // Spalten entsprechend dem Azimut-Mapping
        const positions = [
            { dir: 'N', col: Math.round((0 / 360) * (width - 2)) + 1 },     // 0° Azimut
            { dir: 'O', col: Math.round((90 / 360) * (width - 2)) + 1 },    // 90° Azimut  
            { dir: 'S', col: Math.round((180 / 360) * (width - 2)) + 1 },   // 180° Azimut
            { dir: 'W', col: Math.round((270 / 360) * (width - 2)) + 1 }    // 270° Azimut
        ];
        
        positions.forEach(pos => {
            // Alle Himmelsrichtungen am Horizont anzeigen
            if (pos.dir === 'N') {
                this.sky[horizonRow][pos.col] = t('north');
            } else if (pos.dir === 'S') {
                this.sky[horizonRow][pos.col] = t('south');
            } else if (pos.dir === 'O') {
                this.sky[horizonRow][pos.col] = t('east');
            } else if (pos.dir === 'W') {
                this.sky[horizonRow][pos.col] = t('west');
            }
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
    }

    updateCelestialData(data) {
        this.celestialData = data;
        this.render();
    }

    render() {
        // Don't call initSky() here to avoid recursion
        
        if (!this.celestialData) return;
        
        // Initialisiere den Himmel neu
        this.initSky();
        
        // Draw each celestial object
        Object.values(this.celestialData.bodies).forEach(body => {
            if (body.visible) {
                this.drawCelestialObject(body);
            }
        });
        
        // Convert 2D array to string and display
        const skyText = this.sky.map(row => row.join('')).join('\n');
        this.container.textContent = skyText;
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
        
        // Berechne die Spalte basierend auf dem Azimut (0° bis 360°)
        // Azimut: 0° = Nord, 90° = Ost, 180° = Süd, 270° = West
        // Für korrekte Darstellung: Ost (90°) links, West (270°) rechts
        // Direkte Mapping ohne Rotation - Azimut direkt auf Spalte mappen
        const normalizedAzimuth = obj.azimuth % 360;
        const col = Math.round((normalizedAzimuth / 360) * (width - 2)) + 1;
        
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
                // Wenn bereits ein Objekt an dieser Position ist, verwende ein spezielles Symbol für Überlappung
                symbol = '*';
                // Markiere, dass hier mehrere Objekte sind
                obj.isOverlapping = true;
            } else {
                symbol = CONFIG.OBJECT_SYMBOLS[obj.name.toLowerCase()] || '★';
            }
            
            this.sky[row][col] = symbol;
            
            // Füge Label und Höheninformation hinzu, wenn ausgewählt
            if (isSelected) {
                // Formatiere die Höhe mit der konfigurierten Genauigkeit
                const altitudeStr = obj.altitude.toFixed(CONFIG.ALTITUDE_PRECISION);
                const label = `${obj.name} (${altitudeStr}°)`;
                const startCol = Math.max(0, col - Math.floor(label.length / 2));
                
                // Stelle sicher, dass das Label nicht außerhalb des sichtbaren Bereichs liegt
                const labelRow = Math.min(row + 1, height - 1);
                
                for (let i = 0; i < label.length && startCol + i < width; i++) {
                    this.sky[labelRow][startCol + i] = label[i] || ' ';
                }
            }
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
        // Entferne vorhandenen Dialog, falls vorhanden
        const existingDialog = document.getElementById('object-dialog');
        if (existingDialog) {
            existingDialog.remove();
        }
    }

    clearSelection() {
        this.selectedObject = null;
        
        // Redraw the sky without calling render() directly
        // to avoid potential recursion
        this.initSky();
        if (this.celestialData) {
            Object.values(this.celestialData.bodies).forEach(body => {
                if (body.visible) {
                    this.drawCelestialObject(body);
                }
            });
            
            // Update display
            const skyText = this.sky.map(row => row.join('')).join('\n');
            this.container.textContent = skyText;
        }
    }

    setupEventListeners() {
        // Handle click on the sky to select objects
        this.container.addEventListener('click', (e) => {
            console.log('Click event detected on sky container');
            const rect = this.container.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Convert click coordinates to grid position
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
                const isMenuClick = document.getElementById('objectList')?.contains(e.target);
                if (isMenuClick) {
                    console.log('Click detected in menu area, not showing dialog');
                    return; // Beende die Funktion, wenn im Menü geklickt wurde
                }
                
                for (const [name, obj] of Object.entries(this.celestialData.bodies)) {
                    if (obj.visible) {
                        // Verwende die gespeicherte Position, wenn vorhanden
                        const objRow = obj.displayRow !== undefined ? obj.displayRow : 
                            (obj.altitude >= 0) ? 
                                Math.round(CONFIG.HORIZON_ROW - (obj.altitude / 90 * CONFIG.HORIZON_ROW)) :
                                Math.round(CONFIG.HORIZON_ROW + (Math.abs(obj.altitude) / 90 * (CONFIG.SKY_HEIGHT - CONFIG.HORIZON_ROW - 1)));
                        
                        const normalizedAzimuth = obj.azimuth % 360;
                        const objCol = obj.displayCol !== undefined ? obj.displayCol :
                            Math.round((normalizedAzimuth / 360) * (CONFIG.SKY_WIDTH - 2)) + 1;
                        
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
                
                if (nearbyObjects.length > 0) {
                    console.log(`Found ${nearbyObjects.length} nearby objects:`, 
                        nearbyObjects.map(item => item.name).join(', '));
                    
                    if (nearbyObjects.length === 1) {
                        // Nur ein Objekt gefunden
                        this.selectObject(nearbyObjects[0].name, true);
                    } else {
                        // Mehrere Objekte gefunden - zeige Dialog mit allen Objekten
                        this.showMultiObjectDialog(nearbyObjects.map(item => item.obj));
                    }
                    return;
                }
            }
            
            // Wenn kein Objekt in der Nähe gefunden wurde
            console.log('No object near click position, clearing selection');
            this.clearSelection();
        });
    }

    showObjectDialog(obj) {
        console.log('Showing dialog for:', obj.name, obj);
        
        try {
            // Entferne vorhandenen Dialog, falls vorhanden
            const existingDialog = document.getElementById('object-dialog');
            if (existingDialog) {
                existingDialog.remove();
            }
            
            // Dialog-Inhalt erstellen
            const displayName = t(obj.name) || obj.name;
            const info = [
                `${obj.symbol || ''} ${displayName}`,
                `${t('altitude')}: ${obj.altitude.toFixed(1)}°`,
                `${t('azimuth')}: ${obj.azimuth.toFixed(1)}°`,
                `${t('distance')}: ${(obj.distance / 149597870.691).toFixed(3)} ${t('au')}`
            ];
    
            // Zeige Auf- und Untergangszeiten an, wenn verfügbar
            if (obj.rise_time) {
                info.push(`${t('rise_time')}: ${obj.rise_time} ${t('hour')}`);
            }
            
            if (obj.set_time) {
                info.push(`${t('set_time')}: ${obj.set_time} ${t('hour')}`);
            }
            
            if (obj.transit_time) {
                info.push(`${t('transit_time')}: ${obj.transit_time} ${t('hour')}`);
            }
    
            if (obj.phase !== undefined) {
                const phaseName = obj.phase_name ? t(obj.phase_name) : '';
                info.push(`${t('phase')}: ${(obj.phase * 100).toFixed(1)}% ${phaseName}`);
            }
            
            if (obj.magnitude !== undefined) {
                info.push(`${t('magnitude')}: ${obj.magnitude.toFixed(1)}`);
            }
    
            // Erstelle den Dialog
            const dialog = document.createElement('div');
            dialog.id = 'object-dialog';
            dialog.innerHTML = `
                <button id="dialog-close">${t('close')}</button>
                <div id="dialog-content">${info.join('\n')}</div>
            `;
            
            // Füge den Dialog zum Body hinzu
            document.body.appendChild(dialog);
            
            // Positioniere den Dialog neben der oberen rechten Ecke der Himmelsansicht
            const skyRect = this.container.getBoundingClientRect();
            dialog.style.top = `${skyRect.top}px`;
            dialog.style.left = `${skyRect.right + 10}px`; // 10px Abstand zur rechten Kante
            
            // Close-Button-Event hinzufügen
            document.getElementById('dialog-close').addEventListener('click', () => {
                dialog.remove();
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
            
            // Erstelle einen neuen Dialog
            const dialog = document.createElement('div');
            dialog.className = 'object-dialog multi-object-dialog';
            dialog.id = 'object-dialog';
            
            // Dialog-Header mit Titel und Close-Button
            let dialogContent = `<div class="dialog-header"><h3>${t('multiple_objects_found')}</h3><button id="dialog-close">${t('close')}</button></div>`;
            
            // Füge Liste der Objekte hinzu
            dialogContent += '<div class="object-list">';
            objects.forEach((obj, index) => {
                const displayName = t(obj.name) || obj.name;
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
            
            // Positioniere den Dialog neben der oberen rechten Ecke der Himmelsansicht
            const skyRect = this.container.getBoundingClientRect();
            dialog.style.top = `${skyRect.top}px`;
            dialog.style.left = `${skyRect.right + 10}px`;
            
            // Lade die externen Styles für den Dialog
            const linkElem = document.createElement('link');
            linkElem.rel = 'stylesheet';
            linkElem.href = '/static/js/dialogStyles.css';
            document.head.appendChild(linkElem);
            
            // Event-Listener für den Close-Button
            const closeButton = dialog.querySelector('#dialog-close');
            closeButton.addEventListener('click', () => {
                this.removeDialog();
            });
            
            // Event-Listener für die Objektliste
            const listItems = dialog.querySelectorAll('.object-list-item');
            const dataContainer = dialog.querySelector('.object-data');
            
            // Funktion zum Anzeigen der Objektdaten
            const showObjectData = (objectName) => {
                // Finde das ausgewählte Objekt
                const selectedObject = objects.find(obj => obj.name === objectName);
                if (!selectedObject) return;
                
                // Erstelle Informationstext
                const info = [
                    `${selectedObject.symbol || ''} ${selectedObject.name}`,
                    `${t('altitude')}: ${selectedObject.altitude.toFixed(1)}°`,
                    `${t('azimuth')}: ${selectedObject.azimuth.toFixed(1)}°`,
                    `${t('distance')}: ${(selectedObject.distance / 149597870.691).toFixed(3)} ${t('au')}`
                ];
                
                // Zeige Auf- und Untergangszeiten an, wenn verfügbar
                if (selectedObject.rise_time) {
                    info.push(`${t('rise_time')}: ${selectedObject.rise_time} ${t('hour')}`);
                }
                
                if (selectedObject.set_time) {
                    info.push(`${t('set_time')}: ${selectedObject.set_time} ${t('hour')}`);
                }
                
                if (selectedObject.transit_time) {
                    info.push(`${t('transit_time')}: ${selectedObject.transit_time} ${t('hour')}`);
                }
        
                if (selectedObject.phase !== undefined) {
                    const phaseName = selectedObject.phase_name ? t(selectedObject.phase_name) : '';
                    info.push(`${t('phase')}: ${(selectedObject.phase * 100).toFixed(1)}% ${phaseName}`);
                }
                
                if (selectedObject.magnitude !== undefined) {
                    info.push(`${t('magnitude')}: ${selectedObject.magnitude.toFixed(1)}`);
                }
                
                // Aktualisiere den Datenbereich
                dataContainer.innerHTML = info.join('\n');
                
                // Hebe das entsprechende Objekt im Himmel hervor
                this.highlightObject(objectName);
                
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
            if (objects.length > 0) {
                showObjectData(objects[0].name);
            }
        } catch (error) {
            console.error('Error showing multi-object dialog:', error);
        }
    }

    // Methode zum Setzen der Magnitude-Filter
    setMagnitudeFilters(asteroidMag, cometMag) {
        this.asteroidMaxMagnitude = asteroidMag;
        this.cometMaxMagnitude = cometMag;
        
        // Speichere die Einstellungen persistent
        settingsManager.setMagnitudeFilters(asteroidMag, cometMag);
        
        console.log(`Magnitude filters set and saved: Asteroids=${asteroidMag}, Comets=${cometMag}`);
        
        // Aktualisiere die Anzeige mit den neuen Filtern
        this.update();
    }
    
    // Methode zum Laden von Asteroiden
    async loadAsteroids() {
        try {
            // Erstelle die URL mit Standort- und Magnitude-Parametern
            let url = API_ENDPOINTS.ASTEROIDS;
            
            // Verwende serverseitige Einstellungen, wenn kein lokaler Wert gesetzt ist
            if (this.asteroidMaxMagnitude) {
                url += `?max_magnitude=${this.asteroidMaxMagnitude}`;
            }
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += url.includes('?') ? '&' : '?';
                url += `lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
            }
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error loading asteroids! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`Loaded ${data.bodies ? Object.keys(data.bodies).length : 0} asteroids`);
            
            // Füge die Asteroiden zu den Himmelsdaten hinzu
            if (data && data.bodies && this.celestialData && this.celestialData.bodies) {
                this.celestialData.bodies = { ...this.celestialData.bodies, ...data.bodies };
            }
        } catch (error) {
            console.error('Error loading asteroids:', error);
        }
    }
    
    // Methode zum Laden von Kometen
    async loadComets() {
        try {
            // Erstelle die URL mit Standort- und Magnitude-Parametern
            let url = API_ENDPOINTS.COMETS;
            
            // Verwende serverseitige Einstellungen, wenn kein lokaler Wert gesetzt ist
            if (this.cometMaxMagnitude) {
                url += `?max_magnitude=${this.cometMaxMagnitude}`;
            }
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += url.includes('?') ? '&' : '?';
                url += `lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
            }
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error loading comets! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`Loaded ${data.bodies ? Object.keys(data.bodies).length : 0} comets`);
            
            // Füge die Kometen zu den Himmelsdaten hinzu
            if (data && data.bodies && this.celestialData && this.celestialData.bodies) {
                this.celestialData.bodies = { ...this.celestialData.bodies, ...data.bodies };
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
    
    // Methode zum Aktualisieren der Himmelsdaten
    async update() {
        try {
            console.log('Updating sky data...');
            
            // Lade die Basisdaten (Sonne, Mond, Planeten)
            const response = await fetch(API_ENDPOINTS.SKY);
            if (!response.ok) {
                throw new Error(`HTTP error loading sky data! status: ${response.status}`);
            }
            
            const data = await response.json();
            this.celestialData = data;
            
            // Lade zusätzlich Asteroiden und Kometen mit den aktuellen Einstellungen
            await this.loadAsteroids();
            await this.loadComets();
            
            // Aktualisiere die Anzeige
            this.render();
            
            console.log('Sky data updated successfully');
        } catch (error) {
            console.error('Error updating sky data:', error);
            this.container.textContent = t('error_loading');
        }
    }
}
