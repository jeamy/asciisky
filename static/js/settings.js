// Settings Manager für AsciiSky
// Verwaltet persistente Einstellungen wie Magnitude-Filter
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
            asteroidMaxMagnitude: 8.0,
            cometMaxMagnitude: 12.0,
            location: {
                latitude: 48.2082,  // Wien
                longitude: 16.3738,
                elevation: 171.0,
                name: "Wien"
            }
        };
    }

    // Speichere Einstellungen im localStorage
    saveSettings() {
        try {
            localStorage.setItem('asciisky_settings', JSON.stringify(this.settings));
            console.log('Settings saved:', this.settings);
        } catch (error) {
            console.error('Error saving settings:', error);
        }
    }

    // Magnitude-Filter für Asteroiden setzen
    setAsteroidMagnitude(magnitude) {
        this.settings.asteroidMaxMagnitude = parseFloat(magnitude);
        this.saveSettings();
        return this.settings.asteroidMaxMagnitude;
    }

    // Magnitude-Filter für Kometen setzen
    setCometMagnitude(magnitude) {
        this.settings.cometMaxMagnitude = parseFloat(magnitude);
        this.saveSettings();
        return this.settings.cometMaxMagnitude;
    }

    // Alle Magnitude-Filter auf einmal setzen und mit Server synchronisieren
    async setMagnitudeFilters(asteroidMag, cometMag) {
        this.settings.asteroidMaxMagnitude = parseFloat(asteroidMag);
        this.settings.cometMaxMagnitude = parseFloat(cometMag);
        this.saveSettings();
        
        // Synchronisiere mit dem Server
        await this.syncSettingsToServer();
    }

    // Magnitude-Filter für Asteroiden abrufen
    getAsteroidMagnitude() {
        return this.settings.asteroidMaxMagnitude;
    }

    // Magnitude-Filter für Kometen abrufen
    getCometMagnitude() {
        return this.settings.cometMaxMagnitude;
    }
    
    // Standortdaten abrufen
    getLocation() {
        return this.settings.location || {
            latitude: 48.2082,  // Wien
            longitude: 16.3738,
            elevation: 171.0,
            name: "Wien"
        };
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
            const asteroidResponse = await fetch(`${API_ENDPOINTS.ASTEROIDS}?max_magnitude=${this.settings.asteroidMaxMagnitude}&lat=${latitude}&lon=${longitude}&elevation=${elevation}&location_name=${encodeURIComponent(this.settings.location.name)}&save_settings=true&save_location=true`);
            
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
    
    // Synchronisiere Einstellungen mit dem Server
    async syncSettingsToServer() {
        try {
            const location = this.getLocation();
            
            // Asteroiden-Einstellungen zum Server senden
            const asteroidResponse = await fetch(`${API_ENDPOINTS.ASTEROIDS}?max_magnitude=${this.settings.asteroidMaxMagnitude}&lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}&location_name=${encodeURIComponent(location.name || "Unbekannt")}&save_settings=true&save_location=true`);
            
            // Kometen-Einstellungen zum Server senden
            const cometResponse = await fetch(`${API_ENDPOINTS.COMETS}?max_magnitude=${this.settings.cometMaxMagnitude}&lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}&location_name=${encodeURIComponent(location.name || "Unbekannt")}&save_settings=true`);
            
            if (asteroidResponse.ok && cometResponse.ok) {
                console.log('Settings successfully synced with server');
                this.serverSynced = true;
                return true;
            } else {
                console.error('Error syncing settings with server');
                return false;
            }
        } catch (error) {
            console.error('Error syncing settings with server:', error);
            return false;
        }
    }
    
    // Initialisiere Einstellungen und synchronisiere mit dem Server
    async initialize() {
        // Lokale Einstellungen laden
        this.settings = this.loadSettings();
        
        // Mit dem Server synchronisieren
        await this.syncSettingsToServer();
        
        return this.settings;
    }
}

// Exportiere eine Singleton-Instanz
export const settingsManager = new SettingsManager();
