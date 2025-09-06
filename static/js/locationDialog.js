// Location Dialog für ASCII Sky Tracker
import { t } from './i18n.js';
import { ASTRO_CONSTANTS } from './constants.js';

export class LocationDialog {
    constructor(onLocationChange) {
        this.onLocationChange = onLocationChange;
        this.dialog = null;
        this.overlay = null;
        this.currentLocation = {
            lat: ASTRO_CONSTANTS.VIENNA_LAT,
            lon: ASTRO_CONSTANTS.VIENNA_LON,
            elevation: ASTRO_CONSTANTS.VIENNA_ELEVATION,
            name: 'Vienna'
        };
    }

    show() {
        // Entferne vorhandenen Dialog, falls vorhanden
        this.removeDialog();
        
        // Erstelle den Modal-Overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'modal-overlay';
        
        // Erstelle den Dialog
        this.dialog = document.createElement('div');
        this.dialog.id = 'location-dialog';
        this.dialog.className = 'dialog location-dialog';
        
        // Dialog-Inhalt
        this.dialog.innerHTML = `
            <div class="dialog-header">
                <h3>${t('location_settings')}</h3>
                <button id="location-dialog-close">${t('close')}</button>
            </div>
            <div class="dialog-content">
                <div class="location-search">
                    <input type="text" id="location-search-input" placeholder="${t('search_location')}" />
                    <button id="location-search-button">${t('search')}</button>
                </div>
                <div class="location-results" id="location-results"></div>
                <div class="current-location">
                    <h4>${t('current_location')}</h4>
                    <div id="current-location-display">
                        ${this.currentLocation.name} (${this.currentLocation.lat.toFixed(4)}, ${this.currentLocation.lon.toFixed(4)})
                    </div>
                </div>
                <div class="manual-coordinates">
                    <h4>${t('manual_coordinates')}</h4>
                    <div class="coordinate-inputs">
                        <div class="input-group">
                            <label for="lat-input">${t('latitude')}:</label>
                            <input type="number" id="lat-input" step="0.0001" value="${this.currentLocation.lat}" />
                        </div>
                        <div class="input-group">
                            <label for="lon-input">${t('longitude')}:</label>
                            <input type="number" id="lon-input" step="0.0001" value="${this.currentLocation.lon}" />
                        </div>
                        <div class="input-group">
                            <label for="elevation-input">${t('elevation')}:</label>
                            <input type="number" id="elevation-input" step="1" value="${this.currentLocation.elevation || ASTRO_CONSTANTS.VIENNA_ELEVATION}" />
                        </div>
                        <div class="input-group">
                            <label for="location-name-input">${t('location_name')}:</label>
                            <input type="text" id="location-name-input" value="${this.currentLocation.name}" />
                        </div>
                    </div>
                    <button id="apply-coordinates-button">${t('apply')}</button>
                </div>
            </div>
        `;
        
        // Füge den Dialog zum Overlay hinzu und das Overlay zum DOM
        this.overlay.appendChild(this.dialog);
        document.body.appendChild(this.overlay);
        
        // Event-Listener hinzufügen
        this.setupEventListeners();
    }
    
    removeDialog() {
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
            this.dialog = null;
        }
    }
    
    setupEventListeners() {
        // Close-Button
        document.getElementById('location-dialog-close').addEventListener('click', () => {
            this.removeDialog();
        });
        
        // Schließen bei Klick auf den Overlay außerhalb des Dialogs
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.removeDialog();
            }
        });
        
        // Suche-Button
        document.getElementById('location-search-button').addEventListener('click', () => {
            this.searchLocation();
        });
        
        // Enter-Taste im Suchfeld
        document.getElementById('location-search-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.searchLocation();
            }
        });
        
        // Koordinaten anwenden
        document.getElementById('apply-coordinates-button').addEventListener('click', () => {
            this.applyManualCoordinates();
        });
    }
    
    searchLocation() {
        const searchInput = document.getElementById('location-search-input').value.trim();
        if (!searchInput) return;
        
        const resultsContainer = document.getElementById('location-results');
        resultsContainer.innerHTML = `<div class="loading">${t('searching')}...</div>`;
        
        // OpenStreetMap Nominatim API verwenden
        fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchInput)}`)
            .then(response => response.json())
            .then(data => {
                this.displaySearchResults(data);
            })
            .catch(error => {
                console.error('Error searching location:', error);
                resultsContainer.innerHTML = `<div class="error">${t('search_error')}</div>`;
            });
    }
    
    displaySearchResults(results) {
        const resultsContainer = document.getElementById('location-results');
        resultsContainer.innerHTML = '';
        
        if (!results || results.length === 0) {
            resultsContainer.innerHTML = `<div class="no-results">${t('no_results_found')}</div>`;
            return;
        }
        
        // Maximal 5 Ergebnisse anzeigen
        const limitedResults = results.slice(0, 5);
        
        // Überschrift für Suchergebnisse hinzufügen
        const resultsHeader = document.createElement('h4');
        resultsHeader.textContent = t('search_results') || 'Search Results';
        resultsContainer.appendChild(resultsHeader);
        
        limitedResults.forEach(result => {
            const resultItem = document.createElement('div');
            resultItem.className = 'location-result-item';
            resultItem.innerHTML = `
                <div class="location-name">${result.display_name}</div>
                <div class="location-coords">${parseFloat(result.lat).toFixed(4)}, ${parseFloat(result.lon).toFixed(4)}</div>
            `;
            
            // Vorschau-Container für diesen Standort
            const previewContainer = document.createElement('div');
            previewContainer.className = 'location-preview-container';
            previewContainer.style.display = 'none'; // Standardmäßig ausgeblendet
            previewContainer.innerHTML = `
                <div class="location-preview">
                    <h5>${t('location_preview') || 'Location Preview'}</h5>
                    <div class="preview-map" id="preview-map-${result.place_id}"></div>
                    <div class="preview-info">
                        <p><strong>${t('name') || 'Name'}:</strong> ${result.display_name.split(',')[0]}</p>
                        <p><strong>${t('coordinates') || 'Coordinates'}:</strong> ${parseFloat(result.lat).toFixed(4)}, ${parseFloat(result.lon).toFixed(4)}</p>
                        <p><strong>${t('elevation') || 'Elevation'}:</strong> <span id="elevation-preview-${result.place_id}">${t('fetching') || 'Fetching...'}</span></p>
                    </div>
                </div>
            `;
            
            resultItem.addEventListener('click', async () => {
                // Alle anderen Vorschauen ausblenden
                document.querySelectorAll('.location-preview-container').forEach(container => {
                    container.style.display = 'none';
                });
                
                // Diese Vorschau einblenden
                previewContainer.style.display = 'block';
                
                // Höhe abrufen und anzeigen
                const elevationSpan = document.getElementById(`elevation-preview-${result.place_id}`);
                if (elevationSpan) {
                    elevationSpan.textContent = t('fetching_elevation') || 'Fetching elevation...';
                    const elevation = await this.getElevationForCoordinates(result.lat, result.lon);
                    if (elevation !== null) {
                        elevationSpan.textContent = `${elevation} m`;
                    } else {
                        elevationSpan.textContent = t('elevation_not_available') || 'Not available';
                    }
                }
                
                // Standort auswählen
                this.selectLocation(result);
            });
            
            resultsContainer.appendChild(resultItem);
            resultsContainer.appendChild(previewContainer);
        });
    }
    
    // Funktion zur Höhenermittlung über Open-Elevation API
    async getElevationForCoordinates(lat, lon) {
        try {
            // Status anzeigen
            const elevationInput = document.getElementById('elevation-input');
            if (elevationInput) {
                elevationInput.value = t('fetching_elevation') || 'Fetching elevation...';
            }
            
            const response = await fetch(`https://api.open-elevation.com/api/v1/lookup?locations=${lat},${lon}`);
            const data = await response.json();
            if (data && data.results && data.results.length > 0) {
                return data.results[0].elevation;
            }
        } catch (error) {
            console.error('Error fetching elevation:', error);
        }
        return null;
    }
    
    async selectLocation(location) {
        // Höhe abrufen
        let elevation = ASTRO_CONSTANTS.VIENNA_ELEVATION; // Standard-Höhe als Fallback
        
        this.currentLocation = {
            lat: parseFloat(location.lat),
            lon: parseFloat(location.lon),
            elevation: elevation, // Vorläufig Standard-Höhe
            name: location.display_name.split(',')[0]
        };
        
        // Aktualisiere die Anzeige
        document.getElementById('current-location-display').textContent = 
            `${this.currentLocation.name} (${this.currentLocation.lat.toFixed(4)}, ${this.currentLocation.lon.toFixed(4)})`;
        
        // Aktualisiere die Eingabefelder
        document.getElementById('lat-input').value = this.currentLocation.lat;
        document.getElementById('lon-input').value = this.currentLocation.lon;
        document.getElementById('location-name-input').value = this.currentLocation.name;
        document.getElementById('elevation-input').value = elevation; // Setze zunächst den Standardwert
        
        // Callback mit Standard-Höhe aufrufen, damit die Cache-Anzeige sofort aktualisiert wird
        if (this.onLocationChange) {
            this.onLocationChange(this.currentLocation);
        }
        
        // Höhe automatisch ermitteln
        const fetchedElevation = await this.getElevationForCoordinates(location.lat, location.lon);
        if (fetchedElevation !== null) {
            elevation = fetchedElevation;
            this.currentLocation.elevation = elevation;
            
            // Höhe aktualisieren
            document.getElementById('elevation-input').value = this.currentLocation.elevation;
            
            // Callback erneut aufrufen mit der aktualisierten Höhe
            if (this.onLocationChange) {
                this.onLocationChange(this.currentLocation);
            }
        }
    }
    
    applyManualCoordinates() {
        const lat = parseFloat(document.getElementById('lat-input').value);
        const lon = parseFloat(document.getElementById('lon-input').value);
        const elevation = parseFloat(document.getElementById('elevation-input').value);
        const name = document.getElementById('location-name-input').value.trim() || 'Custom Location';
        
        // Validierung
        if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            alert(t('invalid_coordinates'));
            return;
        }
        
        // Validierung der Höhe (einfache Plausibilitätsprüfung)
        const validElevation = !isNaN(elevation) ? elevation : ASTRO_CONSTANTS.VIENNA_ELEVATION;
        
        this.currentLocation = { lat, lon, elevation: validElevation, name };
        
        // Aktualisiere die Anzeige
        document.getElementById('current-location-display').textContent = 
            `${this.currentLocation.name} (${this.currentLocation.lat.toFixed(4)}, ${this.currentLocation.lon.toFixed(4)})`;
        
        // Callback aufrufen
        if (this.onLocationChange) {
            this.onLocationChange(this.currentLocation);
        }
        
        // Dialog schließen nach Übernahme der Koordinaten
        this.removeDialog();
    }
}
