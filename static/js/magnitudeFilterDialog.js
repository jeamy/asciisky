import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { updateSky } from './skyManager.js';

export class MagnitudeFilterDialog {
    constructor() {
        this.dialog = null;
        this.currentFilters = {
            asteroidMaxMagnitude: 10.0,
            cometMaxMagnitude: 14.0
        };
        this.pendingFilters = null;
        this.createDialog();
        this.loadCurrentFilters();
    }

    async loadCurrentFilters() {
        try {
            const response = await fetch(API_ENDPOINTS.FILTERS_GET);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.filters) {
                    this.currentFilters = data.filters;
                    this.updateSliderValues();
                }
            }
        } catch (error) {
            console.error('Error loading filters:', error);
        }
    }

    createDialog() {
        this.dialog = document.createElement('div');
        this.dialog.className = 'magnitude-filter-dialog';
        this.dialog.style.display = 'none';
        
        this.dialog.innerHTML = `
            <div class="magnitude-filter-content">
                <h3>${t('magnitude_filters') || 'Helligkeitsfilter'}</h3>
                
                <div class="filter-info">
                    ${t('magnitude_filter_info') || 'Hinweis: Bei Änderung der Filter werden die Daten neu berechnet (einige Minuten). Die Objekte werden automatisch angezeigt, sobald sie verfügbar sind.'}
                </div>
                
                <div class="filter-group">
                    <label for="asteroid-magnitude-slider">
                        ${t('asteroids') || 'Asteroiden'}: <span id="asteroid-mag-value">10.0</span> mag
                    </label>
                    <input type="range" id="asteroid-magnitude-slider" 
                           min="10" max="20" step="0.5" value="10">
                </div>
                
                <div class="filter-group">
                    <label for="comet-magnitude-slider">
                        ${t('comets') || 'Kometen'}: <span id="comet-mag-value">14.0</span> mag
                    </label>
                    <input type="range" id="comet-magnitude-slider" 
                           min="10" max="20" step="0.5" value="14">
                </div>
                
                <div class="filter-buttons">
                    <button id="filter-cancel-btn" class="filter-btn filter-cancel">
                        ${t('cancel') || 'Abbrechen'}
                    </button>
                    <button id="filter-ok-btn" class="filter-btn filter-ok">
                        ${t('ok') || 'OK'}
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(this.dialog);
        this.attachEventListeners();
    }

    attachEventListeners() {
        const asteroidSlider = this.dialog.querySelector('#asteroid-magnitude-slider');
        const cometSlider = this.dialog.querySelector('#comet-magnitude-slider');
        const asteroidValue = this.dialog.querySelector('#asteroid-mag-value');
        const cometValue = this.dialog.querySelector('#comet-mag-value');
        const okBtn = this.dialog.querySelector('#filter-ok-btn');
        const cancelBtn = this.dialog.querySelector('#filter-cancel-btn');

        asteroidSlider.addEventListener('input', (e) => {
            asteroidValue.textContent = parseFloat(e.target.value).toFixed(1);
        });

        cometSlider.addEventListener('input', (e) => {
            cometValue.textContent = parseFloat(e.target.value).toFixed(1);
        });

        okBtn.addEventListener('click', () => this.applyFilters());
        cancelBtn.addEventListener('click', () => this.close());
    }

    updateSliderValues() {
        const asteroidSlider = this.dialog.querySelector('#asteroid-magnitude-slider');
        const cometSlider = this.dialog.querySelector('#comet-magnitude-slider');
        const asteroidValue = this.dialog.querySelector('#asteroid-mag-value');
        const cometValue = this.dialog.querySelector('#comet-mag-value');

        if (asteroidSlider && this.currentFilters.asteroidMaxMagnitude) {
            asteroidSlider.value = this.currentFilters.asteroidMaxMagnitude;
            asteroidValue.textContent = this.currentFilters.asteroidMaxMagnitude.toFixed(1);
        }

        if (cometSlider && this.currentFilters.cometMaxMagnitude) {
            cometSlider.value = this.currentFilters.cometMaxMagnitude;
            cometValue.textContent = this.currentFilters.cometMaxMagnitude.toFixed(1);
        }
    }

    show() {
        this.updateSliderValues();
        this.dialog.style.display = 'flex';
    }

    close() {
        this.dialog.style.display = 'none';
    }

    async applyFilters() {
        const asteroidSlider = this.dialog.querySelector('#asteroid-magnitude-slider');
        const cometSlider = this.dialog.querySelector('#comet-magnitude-slider');

        const newFilters = {
            asteroidMaxMagnitude: parseFloat(asteroidSlider.value),
            cometMaxMagnitude: parseFloat(cometSlider.value)
        };

        try {
            const response = await fetch(API_ENDPOINTS.FILTERS_SET, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(newFilters)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.currentFilters = data.filters;
                    this.close();
                    
                    // Zeige Hinweis, wenn Cache invalidiert wurde
                    if (data.cache_invalidated) {
                        console.log('Cache wurde invalidiert, neue Berechnung wird gestartet...');
                        // Optional: Zeige Benutzer-Hinweis
                        const msg = t('cache_invalidated_message') || 
                                   'Filter geändert. Daten werden neu berechnet, dies kann einige Minuten dauern...';
                        // Zeige kurze Info-Nachricht (optional)
                        if (window.showTemporaryMessage) {
                            window.showTemporaryMessage(msg, 5000);
                        }
                    }
                    
                    // Himmel neu laden mit neuen Filtern
                    updateSky();
                }
            } else {
                console.error('Error applying filters:', response.statusText);
                alert(t('error_applying_filters') || 'Fehler beim Anwenden der Filter');
            }
        } catch (error) {
            console.error('Error applying filters:', error);
            alert(t('error_applying_filters') || 'Fehler beim Anwenden der Filter');
        }
    }
}
