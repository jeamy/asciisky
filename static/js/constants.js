// API endpoints
export const API_ENDPOINTS = {
    CELESTIAL: '/api/celestial',
    BRIGHT_ASTEROIDS: '/api/bright_asteroids',
    COMETS: '/api/comets',
    ZODIAC: '/api/zodiac',
    SUNPATH: '/api/celestial/sunpath',
    MESSIER: '/api/messier',
    SESSION_LOCATION: '/api/session/location',
    FILTERS: '/api/filters',
    USER_SETTINGS: '/api/user/settings',
    AUTH_REGISTER: '/api/auth/register',
    AUTH_LOGIN: '/api/auth/login',
    AUTH_LOGOUT: '/api/auth/logout',
    AUTH_ME: '/api/auth/me',
    ADMIN_USERS: '/api/admin/users',
    ELEVATION: 'https://api.open-meteo.com/v1/elevation',
    GEOCODE: 'https://nominatim.openstreetmap.org/search'
};

export const DEFAULT_LOCATION = {
    latitude: 48.2082,
    longitude: 16.3738,
    elevation: 171,
    name: 'Wien',
    timezone: 'Europe/Vienna'
};

// Symbols for lists and the detail panel (the API sends the same ones in
// BODY_SYMBOLS of api/computation.py).
export const OBJECT_SYMBOLS = {
    sun: '☀️',
    moon: '🌙',
    mercury: '☿',
    venus: '♀',
    mars: '♂',
    jupiter: '♃',
    saturn: '♄',
    uranus: '♅',
    neptune: '♆',
    asteroid: '⚸',
    comet: '☄️'
};

// One-cell text glyphs for the sky grid: no emoji, so every row keeps its
// columns.  U+FE0E asks for the text presentation of the comet sign.
export const GRID_SYMBOLS = {
    sun: '☉',
    moon: '☾',
    mercury: '☿',
    venus: '♀',
    mars: '♂',
    jupiter: '♃',
    saturn: '♄',
    uranus: '♅',
    neptune: '♆',
    asteroid: '⚸',
    comet: '☄︎'
};

export const MOON_PHASE_SYMBOLS = {
    new_moon: '🌑',
    waxing_crescent: '🌒',
    first_quarter: '🌓',
    waxing_gibbous: '🌔',
    full_moon: '🌕',
    waning_gibbous: '🌖',
    last_quarter: '🌗',
    waning_crescent: '🌘'
};

export const PLANETS = ['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune'];

export const CONFIG = {
    UPDATE_INTERVAL_MS: 60000,
    // Horizon grid at 360 degrees and the planisphere's size, in cells.
    SKY_COLS: 80,
    SKY_ROWS: 40,
    PLANISPHERE_ROTATION: 180, // 180 = south up
    // Fields of view of the horizon view (degrees of azimuth).
    FOV_LEVELS: [360, 180, 120, 90],
    PLANISPHERE_ZOOM_LEVELS: [1, 1.5, 2, 3],
    // Glyph size limits in px; a narrower field of view keeps glyphs readable.
    MIN_FONT_PX: 11,
    MAX_FONT_PX: 18,
    LABELS: {
        BRIGHT_MINOR_PLANET_MAG_THRESHOLD: 9.0,
        BRIGHT_COMET_MAG_THRESHOLD: 9.0,
        MESSIER_MAG_THRESHOLD: 10.0
    }
};

export const ASCII_ART = {
    HORIZON: '─',
    HORIZON_START: '╭',
    HORIZON_END: '╮',
    SELECTED_OBJECT: '★'
};

export const THEMES = ['green', 'red', 'blue', 'amber'];

// Debug logging: off unless ?debug=1 or localStorage asciisky_debug=1 (O11).
export const DEBUG = (() => {
    try {
        const params = new URLSearchParams(window.location.search);
        if (params.has('debug')) return ['1', 'true', 'yes', 'on'].includes(String(params.get('debug')).toLowerCase());
        const stored = localStorage.getItem('asciisky_debug');
        if (stored != null) return ['1', 'true', 'yes', 'on'].includes(String(stored).toLowerCase());
    } catch (_) { /* storage may be unavailable */ }
    return false;
})();

export const debugLog = (...args) => { if (DEBUG) console.debug('[asciisky]', ...args); };
