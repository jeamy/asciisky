// Settings of asciisky: kept in localStorage, synchronised with the session
// location and, for signed-in users, with the user settings on the server.
import { API_ENDPOINTS, CONFIG, DEFAULT_LOCATION, THEMES } from './constants.js';

const STORAGE_KEY = 'asciisky_settings';
const MAX_SIM_OFFSET_MIN = 525600; // one year
const wrap360 = (deg) => ((deg % 360) + 360) % 360;

function defaultSettings() {
    return {
        location: { ...DEFAULT_LOCATION },
        display: { centerAz: 180, fovDeg: null, viewMode: 'horizon', planisphereRotation: 0, planisphereZoom: 1 },
        simTime: { offsetMinutes: 0 },
    };
}

export class SettingsManager {
    constructor() {
        this.authenticatedUserId = null;
        this.settings = this.loadSettings();
        this._saveTimer = null;
        this._listeners = new Set();
    }

    /** Called with the settings after every change. */
    onChange(fn) {
        this._listeners.add(fn);
        return () => this._listeners.delete(fn);
    }

    loadSettings() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) return this.migrate(JSON.parse(saved));
        } catch (error) {
            console.error('Error loading settings:', error);
        }
        return defaultSettings();
    }

    /** Bring older stored settings to the current shape. */
    migrate(s) {
        const out = { ...defaultSettings(), ...(s && typeof s === 'object' ? s : {}) };
        const display = { ...defaultSettings().display, ...(out.display || {}) };
        // horizontalShift (azimuth at column 1) became centerAz (azimuth in the middle).
        if (typeof display.horizontalShift === 'number' && !(s?.display && typeof s.display.centerAz === 'number')) {
            display.centerAz = wrap360(display.horizontalShift + 180);
        }
        delete display.horizontalShift;
        out.display = display;
        out.location = { ...DEFAULT_LOCATION, ...(out.location || {}) };
        const off = Number(out.simTime?.offsetMinutes);
        out.simTime = { offsetMinutes: Number.isFinite(off) ? off : 0 };
        delete out.asteroidMaxMagnitude;
        delete out.cometMaxMagnitude;
        return out;
    }

    saveSettings() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
        } catch (error) {
            console.error('Error saving settings:', error);
        }
        for (const fn of this._listeners) {
            try { fn(this.settings); } catch (e) { console.error(e); }
        }
        // Debounced: dragging the view changes centerAz many times a second.
        if (this.authenticatedUserId) {
            clearTimeout(this._saveTimer);
            this._saveTimer = setTimeout(() => {
                this.saveUserSettingsToServer().catch((err) => console.error('Error saving user settings:', err));
            }, 800);
        }
    }

    _display() {
        if (!this.settings.display) this.settings.display = {};
        return this.settings.display;
    }

    getLocation() {
        return this.settings.location || { ...DEFAULT_LOCATION };
    }

    // --- view ---
    getCenterAz() {
        const v = this.settings.display?.centerAz;
        return Number.isFinite(v) ? wrap360(v) : 180;
    }

    setCenterAz(az) {
        this._display().centerAz = wrap360(Math.round(az * 10) / 10);
        this.saveSettings();
    }

    /** Stored field of view, or null for the default of the screen size. */
    getFov() {
        const v = this.settings.display?.fovDeg;
        return CONFIG.FOV_LEVELS.includes(v) ? v : null;
    }

    setFov(fov) {
        this._display().fovDeg = CONFIG.FOV_LEVELS.includes(fov) ? fov : null;
        this.saveSettings();
    }

    getViewMode() {
        const mode = this.settings.display?.viewMode;
        return mode === 'planisphere' ? 'planisphere' : 'horizon';
    }

    setViewMode(mode) {
        this._display().viewMode = mode === 'planisphere' ? 'planisphere' : 'horizon';
        this.saveSettings();
    }

    getPlanisphereRotation() {
        const v = this.settings.display?.planisphereRotation;
        return Number.isFinite(v) ? wrap360(v) : 0;
    }

    setPlanisphereRotation(rotation) {
        this._display().planisphereRotation = wrap360(Math.round(rotation * 10) / 10);
        this.saveSettings();
    }

    getPlanisphereZoom() {
        const v = this.settings.display?.planisphereZoom;
        return CONFIG.PLANISPHERE_ZOOM_LEVELS.includes(v) ? v : 1;
    }

    setPlanisphereZoom(zoom) {
        this._display().planisphereZoom = CONFIG.PLANISPHERE_ZOOM_LEVELS.includes(zoom) ? zoom : 1;
        this.saveSettings();
    }

    // --- theme and language ---
    getTheme() {
        return THEMES.includes(this.settings?.theme) ? this.settings.theme : 'green';
    }

    setTheme(theme) {
        if (!THEMES.includes(theme)) return this.getTheme();
        this.settings.theme = theme;
        this.saveSettings();
        return theme;
    }

    getLanguage() {
        const lang = this.settings?.language;
        return lang === 'en' || lang === 'de' ? lang : null;
    }

    setLanguage(lang) {
        if (lang !== 'de' && lang !== 'en') return this.getLanguage();
        this.settings.language = lang;
        this.saveSettings();
        return lang;
    }

    // --- layers ---
    _option(name, fallback) {
        const v = this.settings?.options?.[name];
        return typeof v === 'boolean' ? v : fallback;
    }

    _setOption(name, value) {
        if (!this.settings.options) this.settings.options = {};
        this.settings.options[name] = !!value;
        this.saveSettings();
    }

    getConstellationsVisible() { return this._option('showConstellations', false); }
    setConstellationsVisible(v) { this._setOption('showConstellations', v); }
    getMessierVisible() { return this._option('showMessier', false); }
    setMessierVisible(v) { this._setOption('showMessier', v); }
    getGridVisible() { return this._option('showGrid', true); }
    setGridVisible(v) { this._setOption('showGrid', v); }

    // --- simulated time ---
    getSimulatedOffsetMinutes() {
        const off = Number(this.settings.simTime?.offsetMinutes);
        return Number.isFinite(off) ? off : 0;
    }

    isSimulatedTimeEnabled() {
        return this.getSimulatedOffsetMinutes() !== 0;
    }

    setSimulatedTime(offsetMinutes = 0) {
        const off = Number.isFinite(offsetMinutes)
            ? Math.max(-MAX_SIM_OFFSET_MIN, Math.min(MAX_SIM_OFFSET_MIN, Math.trunc(offsetMinutes)))
            : 0;
        this.settings.simTime = { offsetMinutes: off };
        this.saveSettings();
        return off;
    }

    /** The time the sky shows: now plus the simulated offset. */
    getSkyDate() {
        return new Date(Date.now() + this.getSimulatedOffsetMinutes() * 60000);
    }

    /** ISO time (UTC) when a simulated time is set, otherwise null (the server uses now). */
    getSimulatedTimeISO() {
        return this.isSimulatedTimeEnabled() ? this.getSkyDate().toISOString() : null;
    }

    // --- server sync ---
    async loadUserSettingsFromServer() {
        try {
            const meResp = await fetch(API_ENDPOINTS.AUTH_ME, { credentials: 'same-origin' });
            const me = meResp.ok ? await meResp.json() : null;
            this.authenticatedUserId = me?.authenticated && typeof me.user?.id === 'number' ? me.user.id : null;
        } catch (err) {
            console.error('Error checking auth state:', err);
            this.authenticatedUserId = null;
        }
        if (!this.authenticatedUserId) return;

        try {
            const resp = await fetch(API_ENDPOINTS.USER_SETTINGS, { credentials: 'same-origin' });
            if (!resp.ok) {
                if (resp.status === 401 || resp.status === 403) this.authenticatedUserId = null;
                return;
            }
            const server = await resp.json();
            if (!server || typeof server !== 'object') return;
            this.settings = this.migrate(this.mergeSettings(this.settings || {}, server));
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings)); } catch (_) { /* noop */ }
        } catch (err) {
            console.error('Error loading user settings from server:', err);
        }
    }

    async saveUserSettingsToServer() {
        if (!this.authenticatedUserId) return;
        const resp = await fetch(API_ENDPOINTS.USER_SETTINGS, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(this.settings || {}),
        });
        if (!resp.ok) {
            if (resp.status === 401 || resp.status === 403) this.authenticatedUserId = null;
            else console.error('Error saving user settings: HTTP', resp.status);
        }
    }

    mergeSettings(base, override) {
        const result = { ...(base || {}) };
        if (!override || typeof override !== 'object') return result;
        for (const [key, value] of Object.entries(override)) {
            const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);
            result[key] = isObj(value) && isObj(result[key]) ? { ...result[key], ...value } : value;
        }
        return result;
    }

    async fetchSessionLocation() {
        try {
            const resp = await fetch(API_ENDPOINTS.SESSION_LOCATION, { credentials: 'same-origin' });
            if (!resp.ok) return null;
            const loc = (await resp.json())?.location;
            if (loc && typeof loc.latitude === 'number' && typeof loc.longitude === 'number') {
                const current = this.getLocation();
                this.settings.location = {
                    latitude: loc.latitude,
                    longitude: loc.longitude,
                    elevation: typeof loc.elevation === 'number' ? loc.elevation : current.elevation,
                    name: loc.name || current.name,
                    timezone: loc.timezone || current.timezone,
                };
                this.saveSettings();
                return this.settings.location;
            }
        } catch (err) {
            console.error('Error fetching session location:', err);
        }
        return null;
    }

    async saveSessionLocation(location) {
        if (!location) return false;
        try {
            const resp = await fetch(API_ENDPOINTS.SESSION_LOCATION, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    latitude: location.latitude,
                    longitude: location.longitude,
                    elevation: location.elevation,
                    name: location.name || '',
                }),
            });
            if (!resp.ok) {
                console.error('Error saving session location: HTTP', resp.status);
                return false;
            }
            const loc = (await resp.json().catch(() => null))?.location;
            if (loc?.timezone && this.settings.location) {
                this.settings.location.timezone = loc.timezone;
                this.saveSettings();
            }
            return true;
        } catch (err) {
            console.error('Error saving session location:', err);
            return false;
        }
    }

    async setLocation(latitude, longitude, elevation, name) {
        this.settings.location = {
            latitude: Number(latitude),
            longitude: Number(longitude),
            elevation: Number.isFinite(Number(elevation)) ? Number(elevation) : DEFAULT_LOCATION.elevation,
            name: name || '',
            timezone: undefined, // the server answers with the zone of the new place
        };
        this.saveSettings();
        await this.saveSessionLocation(this.settings.location);
        window.dispatchEvent(new CustomEvent('locationTimezoneUpdated', { detail: { location: this.settings.location } }));
        return this.settings.location;
    }

    async initialize() {
        this.settings = this.loadSettings();
        await this.loadUserSettingsFromServer();
        if (this.authenticatedUserId) {
            await this.saveSessionLocation(this.getLocation());
        } else if (!(await this.fetchSessionLocation())) {
            await this.saveSessionLocation(this.getLocation());
        }
        return this.settings;
    }

    /** On logout: forget the signed-in user's settings in this browser (S7). */
    resetLocal() {
        clearTimeout(this._saveTimer);
        this.authenticatedUserId = null;
        this.settings = defaultSettings();
        try { localStorage.removeItem(STORAGE_KEY); } catch (_) { /* noop */ }
        for (const fn of this._listeners) {
            try { fn(this.settings); } catch (e) { console.error(e); }
        }
    }
}

export const settingsManager = new SettingsManager();
