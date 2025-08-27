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
        
        limitedResults.forEach(result => {
            const resultItem = document.createElement('div');
            resultItem.className = 'location-result-item';
            resultItem.innerHTML = `
                <div class="location-name">${result.display_name}</div>
                <div class="location-coords">${parseFloat(result.lat).toFixed(4)}, ${parseFloat(result.lon).toFixed(4)}</div>
            `;
            
            resultItem.addEventListener('click', () => {
                this.selectLocation(result);
            });
            
            resultsContainer.appendChild(resultItem);
        });
    }
    
    selectLocation(location) {
        this.currentLocation = {
            lat: parseFloat(location.lat),
            lon: parseFloat(location.lon),
            elevation: ASTRO_CONSTANTS.VIENNA_ELEVATION, // Standard-Höhe, da OSM keine Höheninformation liefert
            name: location.display_name.split(',')[0]
        };
        
        // Aktualisiere die Anzeige
        document.getElementById('current-location-display').textContent = 
            `${this.currentLocation.name} (${this.currentLocation.lat.toFixed(4)}, ${this.currentLocation.lon.toFixed(4)})`;
        
        // Aktualisiere die Eingabefelder
        document.getElementById('lat-input').value = this.currentLocation.lat;
        document.getElementById('lon-input').value = this.currentLocation.lon;
        document.getElementById('elevation-input').value = this.currentLocation.elevation;
        document.getElementById('location-name-input').value = this.currentLocation.name;
        
        // Callback aufrufen
        if (this.onLocationChange) {
            this.onLocationChange(this.currentLocation);
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
    }
}
