// Settings Manager für AsciiSky
// Verwaltet persistente Einstellungen wie Standort und Horizontalverschiebung
import { API_ENDPOINTS, ASTRO_CONSTANTS } from './constants.js';

export class SettingsManager {
    constructor() {
        this.settings = this.loadSettings();
        this.serverSynced = false;
    }

    // Lade Einstellungen aus dem localStorage
    loadSettings() {
        try {
            const savedSettings = localStorage.getItem('asciisky_settings');
            if (savedSettings) {
                return JSON.parse(savedSettings);
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
        
        // Default-Einstellungen zurückgeben, wenn keine gespeichert sind
        return {
            location: {
                latitude: 48.2082,  // Wien
                longitude: 16.3738,
                elevation: 171.0,
                name: "Wien"
            },
            display: {
                horizontalShift: 0
            }
        };
    }

    // Speichere Einstellungen im localStorage
    saveSettings() {
        try {
            localStorage.setItem('asciisky_settings', JSON.stringify(this.settings));
            // Konsolenausgabe entfernt
        } catch (error) {
            console.error('Error saving settings:', error);
        }
    }

    // Diese Methoden wurden entfernt, da die Magnitude-Filter nicht mehr benötigt werden
    
    // Standortdaten abrufen
    getLocation() {
        return this.settings.location || {
            latitude: 48.2082,  // Wien
            longitude: 16.3738,
            elevation: 171.0,
            name: "Wien"
        };
    }
    
    // Horizontale Verschiebung speichern
    setHorizontalShift(shift) {
        if (!this.settings.display) {
            this.settings.display = {};
        }
        this.settings.display.horizontalShift = shift;
        this.saveSettings();
        return shift;
    }
    
    // Horizontale Verschiebung abrufen
    getHorizontalShift() {
        return this.settings.display?.horizontalShift || 0;
    }
    
    // Standortdaten setzen und mit Server synchronisieren
    async setLocation(latitude, longitude, elevation, locationName) {
        this.settings.location = {
            latitude: parseFloat(latitude),
            longitude: parseFloat(longitude),
            elevation: parseFloat(elevation),
            name: locationName || "Unbekannt"
        };
        this.saveSettings();
        
        // Sofort mit dem Server synchronisieren
        try {
            // Standortdaten explizit zum Server senden mit save_location=true
            const asteroidResponse = await fetch(`${API_ENDPOINTS.ASTEROIDS}?lat=${latitude}&lon=${longitude}&elevation=${elevation}&location_name=${encodeURIComponent(this.settings.location.name)}&save_location=true`);
            
            if (asteroidResponse.ok) {
                console.log('Location successfully synced with server');
                this.serverSynced = true;
            } else {
                console.error('Error syncing location with server');
            }
        } catch (error) {
            console.error('Error syncing location with server:', error);
        }
        
        return this.settings.location;
    }
    
    // Synchronisiere Standorteinstellungen mit dem Server
    async syncSettingsToServer() {
        try {
            const location = this.getLocation();
            
            // Standortdaten zum Server senden
            const response = await fetch(`${API_ENDPOINTS.CELESTIAL}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}&location_name=${encodeURIComponent(location.name || "Unbekannt")}&save_location=true`);
            
            if (response.ok) {
                console.log('Location successfully synced with server');
                this.serverSynced = true;
                return true;
            } else {
                console.error('Error syncing location with server');
                return false;
            }
        } catch (error) {
            console.error('Error syncing location with server:', error);
            return false;
        }
    }
    
    // Initialisiere Einstellungen und synchronisiere mit dem Server
    async initialize() {
        // Lokale Einstellungen laden
        this.settings = this.loadSettings();
        
        // Entferne Magnitude-Werte aus den Einstellungen
        this.cleanupSettings();
        
        // Mit dem Server synchronisieren
        await this.syncSettingsToServer();
        
        return this.settings;
    }
    
    // Entferne veraltete Einstellungen wie Magnitude-Filter
    cleanupSettings() {
        // Entferne Magnitude-Werte, falls vorhanden
        if (this.settings.asteroidMaxMagnitude !== undefined) {
            delete this.settings.asteroidMaxMagnitude;
        }
        if (this.settings.cometMaxMagnitude !== undefined) {
            delete this.settings.cometMaxMagnitude;
        }
        
        // Speichere die bereinigten Einstellungen
        this.saveSettings();
    }
}

// Exportiere eine Singleton-Instanz
export const settingsManager = new SettingsManager();
