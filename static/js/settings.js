// Settings Manager für AsciiSky
// Verwaltet persistente Einstellungen wie Standort und Horizontalverschiebung
import { API_ENDPOINTS, ASTRO_CONSTANTS } from './constants.js';

export class SettingsManager {
    constructor() {
        this.authenticatedUserId = null;
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
                horizontalShift: 0,
                viewMode: 'horizon'
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

        // Fire-and-forget Sync in die Datenbank; Fehler sollen die UI nicht blockieren
        this.saveUserSettingsToServer().catch(err => {
            console.error('Error saving user settings to server:', err);
        });
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

    getViewMode() {
        try {
            const display = this.settings.display || {};
            const mode = display.viewMode;
            if (mode === 'horizon' || mode === 'planisphere') {
                return mode;
            }
        } catch (_) { }
        return 'horizon';
    }

    setViewMode(mode) {
        const allowed = ['horizon', 'planisphere'];
        const finalMode = allowed.includes(mode) ? mode : 'horizon';
        if (!this.settings.display) {
            this.settings.display = {};
        }
        this.settings.display.viewMode = finalMode;
        this.saveSettings();
        return finalMode;
    }

    // Planisphären-Rotation speichern
    setPlanisphereRotation(rotation) {
        if (!this.settings.display) {
            this.settings.display = {};
        }
        this.settings.display.planisphereRotation = rotation;
        this.saveSettings();
        return rotation;
    }

    // Planisphären-Rotation abrufen
    getPlanisphereRotation() {
        return this.settings.display?.planisphereRotation || 0;
    }

    // --- Theme & Sprache ---

    getTheme() {
        try {
            const theme = this.settings?.theme;
            if (theme === 'red' || theme === 'blue' || theme === 'amber' || theme === 'green') {
                return theme;
            }
        } catch (_) { /* noop */ }
        return 'green';
    }

    setTheme(theme) {
        const allowed = ['green', 'blue', 'red', 'amber'];
        if (!allowed.includes(theme)) {
            return this.getTheme();
        }
        if (!this.settings) this.settings = {};
        this.settings.theme = theme;
        this.saveSettings();
        return theme;
    }

    getLanguage() {
        try {
            const lang = this.settings?.language;
            if (lang === 'de' || lang === 'en') {
                return lang;
            }
        } catch (_) { /* noop */ }
        return 'de';
    }

    setLanguage(lang) {
        const allowed = ['de', 'en'];
        if (!allowed.includes(lang)) {
            return this.getLanguage();
        }
        if (!this.settings) this.settings = {};
        this.settings.language = lang;
        this.saveSettings();
        return lang;
    }

    getConstellationsVisible() {
        try {
            const opts = this.settings?.options;
            if (opts && typeof opts.showConstellations === 'boolean') {
                return !!opts.showConstellations;
            }
        } catch (_) { /* noop */ }
        return false;
    }

    setConstellationsVisible(visible) {
        if (!this.settings) this.settings = {};
        if (!this.settings.options) this.settings.options = {};
        this.settings.options.showConstellations = !!visible;
        this.saveSettings();
        return this.getConstellationsVisible();
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

    // Versucht, user-spezifische Einstellungen aus der Datenbank zu laden
    async loadUserSettingsFromServer() {
        // 1) Prüfen, ob ein authentifizierter Benutzer per Session vorhanden ist
        try {
            const meResp = await fetch(`${API_ENDPOINTS.AUTH_ME}?nocache=1`, {
                credentials: 'same-origin'
            });
            if (!meResp.ok) {
                this.authenticatedUserId = null;
                return;
            }
            const meData = await meResp.json();
            if (!meData || !meData.authenticated || !meData.user || typeof meData.user.id !== 'number') {
                this.authenticatedUserId = null;
                return;
            }
            this.authenticatedUserId = meData.user.id;
        } catch (err) {
            console.error('Error checking auth state for user settings:', err);
            this.authenticatedUserId = null;
            return;
        }

        if (!this.authenticatedUserId) return;

        // 2) Settings für den eingeloggten Benutzer laden (Session-basiert, ohne user_id-Query)
        try {
            const url = `${API_ENDPOINTS.USER_SETTINGS_GET}?nocache=1`;
            const resp = await fetch(url, { credentials: 'same-origin' });
            if (!resp.ok) {
                if (resp.status === 401 || resp.status === 403) {
                    this.authenticatedUserId = null;
                }
                return;
            }
            const serverSettings = await resp.json();
            if (!serverSettings || typeof serverSettings !== 'object') return;

            this.settings = this.mergeSettings(this.settings || {}, serverSettings);
            // Persistiere gemergte Settings lokal für Offline-Verwendung
            try {
                localStorage.setItem('asciisky_settings', JSON.stringify(this.settings));
            } catch (_) { /* noop */ }
        } catch (err) {
            console.error('Error loading user settings from server:', err);
        }
    }

    // Speichert aktuelle Einstellungen in der Datenbank (falls ein authentifizierter Benutzer bekannt ist)
    async saveUserSettingsToServer() {
        try {
            const url = `${API_ENDPOINTS.USER_SETTINGS_SET}?nocache=1`;
            const resp = await fetch(url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(this.settings || {})
            });
            if (!resp.ok) {
                if (resp.status === 401 || resp.status === 403) {
                    this.authenticatedUserId = null;
                    return;
                }
                console.error('Error saving user settings to server: HTTP', resp.status);
            }
        } catch (err) {
            console.error('Error saving user settings to server:', err);
        }
    }

    // Hilfsfunktion zum Mergen von Settings-Objekten (flach + einfache verschachtelte Objekte)
    mergeSettings(base, override) {
        const result = { ...(base || {}) };
        if (!override || typeof override !== 'object') return result;

        for (const [key, value] of Object.entries(override)) {
            if (
                value && typeof value === 'object' && !Array.isArray(value) &&
                result[key] && typeof result[key] === 'object' && !Array.isArray(result[key])
            ) {
                result[key] = { ...result[key], ...value };
            } else {
                result[key] = value;
            }
        }
        return result;
    }

    // Ruft die Standortdaten aus der Session ab (Backend-Session via Cookie)
    async fetchSessionLocation() {
        try {
            const resp = await fetch(`${API_ENDPOINTS.SESSION_LOCATION_GET}?nocache=1`, {
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
            const resp = await fetch(`${API_ENDPOINTS.SESSION_LOCATION_POST}?nocache=1`, {
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

            // Legacy precompute trigger - disabled after RabbitMQ migration
            // RabbitMQ automatically triggers precompute on cache miss
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
            const response = await fetch(`${API_ENDPOINTS.CELESTIAL}?lat=${location.latitude}&lon=${location.longitude}&elevation=${location.elevation}&location_name=${encodeURIComponent(location.name || "Unbekannt")}&save_location=true&nocache=1`);

            if (response.ok) {
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

        // Falls eine userId bekannt ist: Settings aus der Datenbank laden und mit lokalen mergen
        await this.loadUserSettingsFromServer();

        if (!this.authenticatedUserId) {
            // Session-Standort bevorzugen (falls vorhanden) nur für nicht eingeloggte Nutzer
            await this.fetchSessionLocation();
        } else {
            // Für eingeloggte Nutzer: DB-Standort als Quelle verwenden und Session damit befüllen
            try {
                const loc = this.getLocation();
                await this.saveSessionLocation(loc);
            } catch (e) {
                console.error('Error initializing session location for authenticated user:', e);
            }
        }

        // Persistente Nutzereinstellungen mit aktuellem Standort abgleichen
        await this.syncSettingsToServer();

        return this.settings;
    }

    // Entferne veraltete Einstellungen
    cleanupSettings() {
        // Magnitude-Filter werden jetzt im Backend (user_settings.json) gespeichert
        // und nicht mehr im Frontend localStorage
        // Entferne alte Magnitude-Werte aus localStorage, falls vorhanden
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
