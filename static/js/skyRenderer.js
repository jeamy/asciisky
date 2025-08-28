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
        
        // Horizontale Verschiebung aus den Einstellungen laden
        this.horizontalShift = settingsManager.getHorizontalShift(); 
        console.log(`Loaded horizontal shift: ${this.horizontalShift}°`);
        
        // Lade gespeicherte Standortdaten
        this.location = settingsManager.getLocation();
        
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
    
    // Methode zum Verschieben des Horizonts nach links
    shiftHorizonLeft() {
        // Verschiebe um 5 Grad nach links
        this.horizontalShift -= 5;
        
        // Speichere die aktuelle Verschiebung
        settingsManager.setHorizontalShift(this.horizontalShift);
        
        // Aktualisiere die Anzeige
        this.render();
    }
    
    // Methode zum Verschieben des Horizonts nach rechts
    shiftHorizonRight() {
        // Verschiebe um 5 Grad nach rechts
        this.horizontalShift += 5;
        
        // Speichere die aktuelle Verschiebung
        settingsManager.setHorizontalShift(this.horizontalShift);
        
        // Aktualisiere die Anzeige
        this.render();
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
        // Spalten entsprechend dem Azimut-Mapping mit horizontaler Verschiebung
        const positions = [
            { dir: 'N', azimuth: 0 },     // 0° Azimut
            { dir: 'O', azimuth: 90 },    // 90° Azimut  
            { dir: 'S', azimuth: 180 },   // 180° Azimut
            { dir: 'W', azimuth: 270 }    // 270° Azimut
        ];
        
        // Alle Himmelsrichtungen anzeigen, unabhängig von der Verschiebung
        const visibleDirections = positions;
        
        // Zeichne die sichtbaren Himmelsrichtungen
        visibleDirections.forEach(pos => {
            // Berechne den effektiven Azimut mit Verschiebung
            let effectiveAzimuth = pos.azimuth - this.horizontalShift;
            
            // Normalisiere den Azimut auf den Bereich 0-360
            while (effectiveAzimuth < 0) effectiveAzimuth += 360;
            while (effectiveAzimuth >= 360) effectiveAzimuth -= 360;
            
            // Berechne die Spalte basierend auf dem normalisierten Azimut
            const col = Math.round((effectiveAzimuth / 360) * (width - 2)) + 1;
            
            // Nur zeichnen, wenn die Spalte im sichtbaren Bereich liegt
            if (col >= 0 && col < width) {
                if (pos.dir === 'N') {
                    this.sky[horizonRow][col] = t('north');
                } else if (pos.dir === 'S') {
                    this.sky[horizonRow][col] = t('south');
                } else if (pos.dir === 'O') {
                    this.sky[horizonRow][col] = t('east');
                } else if (pos.dir === 'W') {
                    this.sky[horizonRow][col] = t('west');
                }
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
        
        // Draw each celestial object (unabhängig von body.visible)
        Object.values(this.celestialData.bodies).forEach(body => {
            this.drawCelestialObject(body);
        });
        
        // Convert 2D array to string and display
        const skyText = this.sky.map(row => row.join('')).join('\n');
        
        // Erstelle ein temporäres div für den Himmelstext
        const skyTextDiv = document.createElement('div');
        skyTextDiv.className = 'sky-text';
        skyTextDiv.style.whiteSpace = 'pre';
        skyTextDiv.style.fontFamily = 'monospace';
        skyTextDiv.textContent = skyText;
        
        // Speichere die vorhandenen Navigationspfeile
        const existingArrows = document.getElementById('navigation-arrows');
        
        // Leere den Container
        this.container.innerHTML = '';
        
        // Füge den Himmelstext hinzu
        this.container.appendChild(skyTextDiv);
        
        // Füge immer neue Navigationspfeile hinzu
        this.addNavigationArrows();
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
                // Wenn bereits ein Objekt an dieser Position ist, verwende ein spezielles Symbol für Überlappung
                symbol = '*';
                // Markiere, dass hier mehrere Objekte sind
                obj.isOverlapping = true;
            } else {
                // Bevorzuge Symbol vom Backend; fallback auf lokale Symboltabelle
                const backendSymbol = obj.symbol && String(obj.symbol).trim() !== '' ? obj.symbol : null;
                symbol = backendSymbol || CONFIG.OBJECT_SYMBOLS[obj.name.toLowerCase()] || '★';
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
        // Nutze den normalen Renderpfad, damit auch die Pfeile erhalten bleiben
        this.render();
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
                `${t('distance')}: ${obj.distance.toFixed(3)} ${t('au')}`
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
            linkElem.href = '/static/css/dialogStyles.css';
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
                const displayName = t(selectedObject.name) || selectedObject.name;
                const info = [
                    `${selectedObject.symbol || ''} ${displayName}`,
                    `${t('altitude')}: ${selectedObject.altitude.toFixed(1)}°`,
                    `${t('azimuth')}: ${selectedObject.azimuth.toFixed(1)}°`,
                    `${t('distance')}: ${selectedObject.distance.toFixed(3)} ${t('au')}`
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

    // Methode zum Setzen der Magnitude-Filter wurde entfernt
    
    // Methode zum Laden von Asteroiden
    async loadAsteroids() {
        try {
            // Erstelle die URL mit Standortparametern
            let url = API_ENDPOINTS.ASTEROIDS;
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += `?lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
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
            // Erstelle die URL mit Standortparametern
            let url = API_ENDPOINTS.COMETS;
            
            // Verwende die gespeicherten Standortdaten
            if (this.location) {
                url += `?lat=${this.location.latitude}&lon=${this.location.longitude}&elevation=${this.location.elevation}`;
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
    
    // Lade Himmelsdaten und aktualisiere die Anzeige
    async updateSkyData() {
        try {
            // Hole die aktuellen Standortdaten
            const location = settingsManager.getLocation();
            
            // Hole die Himmelsdaten vom Server
            const response = await fetch(`${API_ENDPOINTS.CELESTIAL}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            
            // Speichere die Daten
            this.skyData = data;
            
            // Hole Asteroidendaten
            const asteroidResponse = await fetch(`${API_ENDPOINTS.ASTEROIDS}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (asteroidResponse.ok) {
                const asteroidData = await asteroidResponse.json();
                // Füge Asteroiden zu den Himmelskörpern hinzu
                this.skyData.bodies = { ...this.skyData.bodies, ...asteroidData.bodies };
            }
            
            // Hole Kometendaten
            const cometResponse = await fetch(`${API_ENDPOINTS.COMETS}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (cometResponse.ok) {
                const cometData = await cometResponse.json();
                // Füge Kometen zu den Himmelskörpern hinzu
                this.skyData.bodies = { ...this.skyData.bodies, ...cometData.bodies };
            }
            
            // Hole die hellsten Asteroiden (Minor Planets)
            const brightAsteroidResponse = await fetch(`${API_ENDPOINTS.BRIGHT_ASTEROIDS}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (brightAsteroidResponse.ok) {
                const brightAsteroidData = await brightAsteroidResponse.json();
                // Füge die hellsten Asteroiden zu den Himmelskörpern hinzu
                this.skyData.bodies = { ...this.skyData.bodies, ...brightAsteroidData.bodies };
            }
        } catch (error) {
            console.error('Error updating sky data:', error);
        }
    }

    // Methode zum Aktualisieren der Himmelsdaten
    async update() {
        try {
            console.log('Updating sky data...');
            
            // Hole die aktuellen Standortdaten
            const location = settingsManager.getLocation();
            
            // Lade die Basisdaten (Sonne, Mond, Planeten)
            const response = await fetch(`${API_ENDPOINTS.SKY}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (!response.ok) {
                throw new Error(`HTTP error loading sky data! status: ${response.status}`);
            }
            
            const data = await response.json();
            this.celestialData = data;
            
            // Lade zusätzlich Asteroiden und Kometen mit den aktuellen Einstellungen
            await this.loadAsteroids();
            await this.loadComets();
            
            // Lade die hellsten Asteroiden
            const brightAsteroidResponse = await fetch(`${API_ENDPOINTS.BRIGHT_ASTEROIDS}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}`);
            if (brightAsteroidResponse.ok) {
                const brightAsteroidData = await brightAsteroidResponse.json();
                // Füge die hellsten Asteroiden zu den Himmelskörpern hinzu
                this.celestialData.bodies = { ...this.celestialData.bodies, ...brightAsteroidData.bodies };
                console.log('Bright asteroids loaded successfully:', Object.keys(brightAsteroidData.bodies).length);
            }
            
            // Aktualisiere die Anzeige
            this.render();
            
            console.log('Sky data updated successfully');
        } catch (error) {
            console.error('Error updating sky data:', error);
            this.container.textContent = t('error_loading');
        }
    }
}
