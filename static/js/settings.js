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
            },
            // Simulierte Zeit: deaktiviert per Default
            simTime: {
                enabled: false,
                offsetMinutes: 0
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
    
    // --- Simulierte Zeit ---
    // Liefert den aktuell gesetzten Versatz in Minuten und den Aktivierungsstatus
    getSimulatedTimeOffset() {
        const sim = this.settings.simTime || { enabled: false, offsetMinutes: 0 };
        const off = (typeof sim.offsetMinutes === 'number') ? sim.offsetMinutes : 0;
        // Aktiv nur, wenn Offset != 0 (kein separater Toggle mehr)
        const autoEnabled = off !== 0;
        return {
            enabled: autoEnabled,
            offsetMinutes: off
        };
    }

    // Ob simulierte Zeit aktiviert ist
    isSimulatedTimeEnabled() {
        const sim = this.settings.simTime || { enabled: false, offsetMinutes: 0 };
        const off = (typeof sim.offsetMinutes === 'number') ? sim.offsetMinutes : 0;
        return off !== 0;
    }

    // Setzt den Versatz in Minuten; der Aktivierungsstatus ist optional.
    // Wenn 'enabled' nicht angegeben ist, wird automatisch aktiviert, wenn offsetMinutes != 0.
    setSimulatedTime(offsetMinutes = 0, enabled) {
        if (!this.settings.simTime) this.settings.simTime = { enabled: false, offsetMinutes: 0 };
        const off = Number.isFinite(offsetMinutes) ? Math.max(-525600, Math.min(525600, Math.trunc(offsetMinutes))) : 0; // clamp +/- 1 year
        const en = (typeof enabled === 'undefined') ? (off !== 0) : !!enabled;
        this.settings.simTime.enabled = en;
        this.settings.simTime.offsetMinutes = off;
        this.saveSettings();
        return this.getSimulatedTimeOffset();
    }

    // Gibt eine ISO-8601 Zeit (UTC, mit 'Z') zurück, wenn simulierte Zeit aktiv ist, sonst null
    getSimulatedTimeISO() {
        try {
            const { enabled, offsetMinutes } = this.getSimulatedTimeOffset();
            if (!enabled) return null;
            const dt = new Date(Date.now() + (offsetMinutes || 0) * 60000);
            return dt.toISOString(); // UTC mit Z-Suffix
        } catch (e) {
            console.error('Error computing simulated time ISO:', e);
            return null;
        }
    }

    // Ruft die Standortdaten aus der Session ab (Backend-Session via Cookie)
    async fetchSessionLocation() {
        try {
            const resp = await fetch(API_ENDPOINTS.SESSION_LOCATION, {
                credentials: 'same-origin'
            });
            if (!resp.ok) return null;
            const data = await resp.json();
            const loc = data && data.location ? data.location : null;
            if (loc && typeof loc.latitude === 'number' && typeof loc.longitude === 'number') {
                // Übernehme Session-Standort als bevorzugte Quelle
                this.settings.location = {
                    latitude: parseFloat(loc.latitude),
                    longitude: parseFloat(loc.longitude),
                    elevation: typeof loc.elevation === 'number' ? parseFloat(loc.elevation) : (this.settings.location?.elevation ?? ASTRO_CONSTANTS.VIENNA_ELEVATION),
                    name: loc.name || this.settings.location?.name || 'Unbekannt'
                };
                this.saveSettings();
                return this.settings.location;
            }
            return null;
        } catch (err) {
            console.error('Error fetching session location:', err);
            return null;
        }
    }

    // Speichert den Standort direkt in der Session (Backend-Session via Cookie)
    async saveSessionLocation(location) {
        try {
            if (!location) return false;
            const payload = {
                latitude: location.latitude,
                longitude: location.longitude,
                elevation: location.elevation,
                name: location.name || 'Unbekannt'
            };
            const resp = await fetch(API_ENDPOINTS.SESSION_LOCATION, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });
            if (resp.ok) {
                this.serverSynced = true;
                return true;
            } else {
                console.error('Error saving session location: HTTP', resp.status);
                return false;
            }
        } catch (err) {
            console.error('Error saving session location:', err);
            return false;
        }
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
            // 1) Session sofort aktualisieren (Cookie-basierte Session)
            await this.saveSessionLocation(this.settings.location);

            // 2) Optional: Hintergrund-Precompute für neues Ziel anstoßen (nicht blockierend)
            try {
                fetch(API_ENDPOINTS.PRECOMPUTE_WINDOW, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        lat: parseFloat(latitude),
                        lon: parseFloat(longitude),
                        elevation: parseFloat(elevation),
                        kinds: ['celestial','asteroids','comets']
                    })
                }).catch(() => {});
            } catch (_) { /* noop */ }
            this.serverSynced = true;
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
        
        // Entferne veraltete Werte aus den Einstellungen
        this.cleanupSettings();
        
        // Session-Standort bevorzugen (falls vorhanden)
        await this.fetchSessionLocation();
        
        // Persistente Nutzereinstellungen mit aktuellem (ggf. Session-)Standort abgleichen
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
