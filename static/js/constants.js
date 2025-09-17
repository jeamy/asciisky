// API Endpoints
export const API_ENDPOINTS = {
    CELESTIAL: '/api/celestial',
    CELESTIAL_OBJECT: '/api/celestial',  // + '/{body_id}'
    SKY: '/api/celestial',
    ASTEROIDS: '/api/bright_asteroids',
    COMETS: '/api/comets',
    BRIGHT_ASTEROIDS: '/api/bright_asteroids',
    SESSION_LOCATION: '/api/session/location',
    CACHE_STATUS: '/api/cache_status',
    CACHE_AVAILABILITY: '/api/cache_availability',
    PRECOMPUTE_WINDOW: '/api/precompute_window',
    CONFIG: '/api/config'
    // ZODIAC endpoint removed as it's not implemented in the backend
};

// Astronomical Constants
export const ASTRO_CONSTANTS = {
    SUN_MAGNITUDE: -26.74,  // Standard apparent magnitude of the Sun
    MOON_MAGNITUDE: -12.6,  // Approximate full moon magnitude
    VIENNA_LAT: 48.2082,    // Vienna latitude
    VIENNA_LON: 16.3738,    // Vienna longitude
    VIENNA_ELEVATION: 171   // Vienna elevation in meters
};

// Celestial Object Symbols - must match symbols in main.py
export const OBJECT_SYMBOLS = {
    'sun': '☀️',
    'moon': '🌙',
    'mercury': '☿',
    'venus': '♀',
    'mars': '♂',
    'jupiter': '♃',
    'saturn': '♄',
    'uranus': '♅',
    'neptune': '♆',
    'asteroid': '⚸',  // Unicode U+26B8 (Asteroid)
    'comet': '☄️'  // Unicode U+2604 (Komet)
};

// Display Configuration
export const CONFIG = {
    UPDATE_INTERVAL_MS: 60000, // 60 seconds
    SKY_WIDTH: 80,
    SKY_HEIGHT: 40,
    HORIZON_ROW: 20, // Row where the horizon is drawn (middle of SKY_HEIGHT)
    CARDINAL_DIRECTIONS: ['N', 'O', 'S', 'W'],
    OBJECT_SYMBOLS: OBJECT_SYMBOLS,  // Reference to the constant defined above
    SHOW_BELOW_HORIZON: true,       // Zeige Objekte unter dem Horizont
    BELOW_HORIZON_SYMBOL: '★',      // Symbol für Objekte unter dem Horizont
    MAX_ALTITUDE: 90,              // Maximale Höhe in Grad (Zenit)
    MIN_ALTITUDE: -90,             // Minimale Höhe in Grad (Nadir)
    ALTITUDE_PRECISION: 1,         // Genauigkeit der Höhenanzeige in Grad
    LABELS: {
        ENABLE_BRIGHT_MINOR_PLANET_LABELS: true,
        BRIGHT_MINOR_PLANET_MAG_THRESHOLD: 9.0,
        ENABLE_BRIGHT_COMET_LABELS: true,
        BRIGHT_COMET_MAG_THRESHOLD: 9.0
    }
};

// ASCII Art
export const ASCII_ART = {
    HORIZON: '─',
    HORIZON_START: '╭',
    HORIZON_END: '╮',
    VERTICAL: '│',
    CROSS: '┼',
    SKY: '.',
    GROUND: ' ',
    CARDINAL_MARKER: '^',
    SELECTED_OBJECT: '★',
    DIALOG_BORDER: '═',
    DIALOG_CORNER: '╔╗╝╚',
    DIALOG_VERTICAL: '║',
    DIALOG_HORIZONTAL: '═'
};

// Debug configuration
export const DEBUG = (() => {
    try {
        // URL param wins: ?debug=1|true|yes|on or 0|false|no|off
        const params = new URLSearchParams(window.location.search);
        if (params.has('debug')) {
            const v = String(params.get('debug')).toLowerCase();
            return v === '1' || v === 'true' || v === 'yes' || v === 'on';
        }
        // Local override via localStorage
        const ls = localStorage.getItem('asciisky_debug');
        if (ls != null) {
            const v = String(ls).toLowerCase();
            return v === '1' || v === 'true' || v === 'yes' || v === 'on';
        }
    } catch (_) { /* noop */ }
    // Default: enabled (developer-friendly). Pass ?debug=0 to mute.
    return true;
})();

// Globally mute console (except errors) when not debugging
(() => {
    try {
        if (!DEBUG && typeof console !== 'undefined') {
            const noop = () => {};
            console.log = noop;
            console.debug = noop;
            console.info = noop;
            console.warn = noop;
            console.trace = noop;
        }
    } catch (_) { /* noop */ }
})();
