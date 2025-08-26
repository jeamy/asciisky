import { API_ENDPOINTS, CONFIG, ASCII_ART } from './constants.js';

export class SkyRenderer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.sky = [];
        this.celestialData = null;
        this.selectedObject = null;
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
        // Blickrichtung nach Süden: Osten links, Westen rechts
        const positions = [
            { dir: 'N', col: Math.round(width / 2) },
            { dir: 'O', col: 5 },                 // Osten links
            { dir: 'S', col: Math.round(width / 2) },
            { dir: 'W', col: width - 5 }          // Westen rechts
        ];
        
        positions.forEach(pos => {
            // Alle Himmelsrichtungen am Horizont anzeigen
            if (pos.dir === 'N') {
                this.sky[horizonRow][pos.col] = 'N';
            } else if (pos.dir === 'S') {
                this.sky[horizonRow][pos.col] = 'S';
            } else if (pos.dir === 'O') {
                this.sky[horizonRow][pos.col] = 'O';
            } else if (pos.dir === 'W') {
                this.sky[horizonRow][pos.col] = 'W';
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
        // Spiegeln des Azimuts für Blickrichtung nach Süden (Osten links, Westen rechts)
        const adjustedAzimuth = (360 - obj.azimuth) % 360;
        const col = Math.round((adjustedAzimuth / 360) * (width - 2)) + 1;
        
        // Nur zeichnen, wenn innerhalb der Grenzen
        if (row >= 0 && row < height && col >= 0 && col < width) {
            // Prüfe, ob dies das ausgewählte Objekt ist
            const isSelected = this.selectedObject && this.selectedObject.name === obj.name;
            
            // Wähle Symbol basierend auf Auswahl
            const symbol = isSelected ? ASCII_ART.SELECTED_OBJECT : 
                          (CONFIG.OBJECT_SYMBOLS[obj.name.toLowerCase()] || '★');
            
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
            
            // Direkter Zugriff auf die Himmelskörper und Prüfung der Nähe zum Klick
            if (this.celestialData) {
                let closestObject = null;
                let minDistance = 5; // Maximale Klickdistanz (in Zellen)
                
                // Prüfe, ob der Klick im Menübereich war
                const isMenuClick = document.getElementById('objectList')?.contains(e.target);
                if (isMenuClick) {
                    console.log('Click detected in menu area, not showing dialog');
                    return; // Beende die Funktion, wenn im Menü geklickt wurde
                }
                
                for (const [name, obj] of Object.entries(this.celestialData.bodies)) {
                    if (obj.visible) {
                        // Berechne die Position des Objekts basierend auf Höhe und Azimut
                        let objRow;
                        if (obj.altitude >= 0) {
                            objRow = Math.round(CONFIG.HORIZON_ROW - (obj.altitude / 90 * CONFIG.HORIZON_ROW));
                        } else {
                            objRow = Math.round(CONFIG.HORIZON_ROW + (Math.abs(obj.altitude) / 90 * (CONFIG.SKY_HEIGHT - CONFIG.HORIZON_ROW - 1)));
                        }
                        // Spiegeln des Azimuts für Blickrichtung nach Süden (Osten links, Westen rechts)
                        const adjustedAzimuth = (360 - obj.azimuth) % 360;
                        const objCol = Math.round((adjustedAzimuth / 360) * (CONFIG.SKY_WIDTH - 2)) + 1;
                        
                        // Berechne Distanz zum Klick
                        const distance = Math.sqrt(Math.pow(row - objRow, 2) + Math.pow(col - objCol, 2));
                        console.log(`Distance to ${name}: ${distance} (at row=${objRow}, col=${objCol})`);
                        
                        // Wenn näher als bisher gefundene Objekte und innerhalb der Toleranz
                        // Priorisiere Uranus, wenn die Distanz ähnlich ist
                        if (distance < minDistance || 
                            (name === 'uranus' && Math.abs(distance - minDistance) < 0.5)) {
                            minDistance = distance;
                            closestObject = name;
                        }
                    }
                }
                
                if (closestObject) {
                    console.log(`Closest object found: ${closestObject} at distance ${minDistance}`);
                    this.selectObject(closestObject, true); // true = Dialog anzeigen
                    return; // Früher beenden, da wir ein Objekt gefunden haben
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
            
            // Create new dialog - direkt im DOM einfügen
            const dialogHTML = `
                <div id="object-dialog" style="
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: #111;
                    border: 2px solid #0f0;
                    padding: 15px;
                    color: #0f0;
                    font-family: monospace;
                    white-space: pre;
                    z-index: 9999;
                    min-width: 250px;
                    box-shadow: 0 0 15px rgba(0, 255, 0, 0.5);
                ">
                    <button id="dialog-close" style="
                        position: absolute;
                        top: 5px;
                        right: 5px;
                        background: transparent;
                        border: none;
                        color: #0f0;
                        cursor: pointer;
                        font-size: 16px;
                        font-weight: bold;
                    ">X</button>
                    <div id="dialog-content"></div>
                </div>
            `;
            
            // Dialog zum DOM hinzufügen
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = dialogHTML;
            document.body.appendChild(tempDiv.firstElementChild);
            
            // Dialog-Referenz holen
            const dialog = document.getElementById('object-dialog');
            const closeBtn = document.getElementById('dialog-close');
            const contentDiv = document.getElementById('dialog-content');
            
            // Close-Button-Event hinzufügen
            closeBtn.addEventListener('click', () => {
                dialog.remove();
                this.clearSelection();
            });
            
            // Dialog-Inhalt erstellen
            const info = [
                `${obj.symbol || ''} ${obj.name}`,
                `Altitude: ${obj.altitude.toFixed(1)}°`,
                `Azimuth: ${obj.azimuth.toFixed(1)}°`,
                `Distance: ${(obj.distance / 149597870.691).toFixed(3)} AU`
            ];
    
            // Zeige Auf- und Untergangszeiten an, wenn verfügbar
            if (obj.rise_time) {
                info.push(`Aufgang: ${obj.rise_time} Uhr`);
            }
            
            if (obj.set_time) {
                info.push(`Untergang: ${obj.set_time} Uhr`);
            }
            
            if (obj.transit_time) {
                info.push(`Höchststand: ${obj.transit_time} Uhr`);
            }
    
            if (obj.phase !== undefined) {
                info.push(`Phase: ${(obj.phase * 100).toFixed(1)}% ${obj.phase_name || ''}`);
            }
            
            if (obj.magnitude !== undefined) {
                info.push(`Magnitude: ${obj.magnitude.toFixed(1)}`);
            }
    
            // Inhalt zum Dialog hinzufügen
            contentDiv.textContent = info.join('\n');
            
            // Optional: Dialog nach 2 Sekunden an die richtige Position verschieben
            setTimeout(() => {
                try {
                    const rect = this.container.getBoundingClientRect();
                    // Spiegeln des Azimuts für Blickrichtung nach Süden (Osten links, Westen rechts)
                    const adjustedAzimuth = (360 - obj.azimuth) % 360;
                    const azimuth = adjustedAzimuth / 360 * rect.width;
                    const altitude = (1 - obj.altitude / 90) * (rect.height / 2);
                    
                    // Berechne die Position und stelle sicher, dass der Dialog nicht abgeschnitten wird
                    let leftPos = rect.left + azimuth - 100;
                    
                    // Stelle sicher, dass der Dialog nicht links aus dem Bildschirm ragt
                    if (leftPos < 10) {
                        leftPos = 10; // Mindestens 10px vom linken Rand
                    }
                    
                    // Stelle sicher, dass der Dialog nicht rechts aus dem Bildschirm ragt
                    if (leftPos + 250 > window.innerWidth) {
                        leftPos = window.innerWidth - 260;
                    }
                    
                    dialog.style.position = 'absolute';
                    dialog.style.transform = 'none';
                    dialog.style.left = `${leftPos}px`;
                    dialog.style.top = `${rect.top + altitude}px`;
                } catch (posError) {
                    console.error('Error positioning dialog:', posError);
                }
            }, 100);
        } catch (error) {
            console.error('Error creating dialog:', error);
            alert(`Info for ${obj.name}: Alt=${obj.altitude.toFixed(1)}°, Az=${obj.azimuth.toFixed(1)}°`);
        }
    }

    async update() {
        try {
            // Zeige Ladestatus an
            this.container.textContent = 'Loading celestial data...';
            
            const response = await fetch(API_ENDPOINTS.CELESTIAL);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Debug-Ausgabe der Daten
            console.log('Celestial data:', data);
            if (data && data.bodies) {
                Object.entries(data.bodies).forEach(([name, body]) => {
                    console.log(`${name}: altitude=${body.altitude}, visible=${body.visible}`);
                });
            }
            
            this.updateCelestialData(data);
            
            // Explizit render aufrufen, um sicherzustellen, dass die Daten angezeigt werden
            this.render();
        } catch (error) {
            console.error('Error updating celestial data:', error);
            this.container.textContent = 'Error loading sky data. Please refresh the page.';
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
}
