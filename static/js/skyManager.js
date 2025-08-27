import { SkyRenderer } from './skyRenderer.js';
import { CONFIG, ASTRO_CONSTANTS } from './constants.js';

// Deklariere skyRenderer als exportierte Variable
export let skyRenderer;

// Aktuelle Standortdaten
let currentLocation = {
    latitude: ASTRO_CONSTANTS.VIENNA_LAT,
    longitude: ASTRO_CONSTANTS.VIENNA_LON,
    elevation: ASTRO_CONSTANTS.VIENNA_ELEVATION
};

export function initializeSkyTracker() {
    // Initialize the sky renderer
    skyRenderer = new SkyRenderer('sky-container');
    
    // Setze die SkyManager-Referenz im SkyRenderer
    skyRenderer.skyManager = {
        getCurrentLocation,
        setLocation
    };
    
    // Set up periodic updates
    setInterval(updateSky, CONFIG.UPDATE_INTERVAL_MS);
    
    return skyRenderer;
}

// Funktion zum Ändern des Standorts
export function setLocation(lat, lon, elevation = ASTRO_CONSTANTS.VIENNA_ELEVATION) {
    currentLocation = {
        latitude: lat,
        longitude: lon,
        elevation
    };
    
    // Beim nächsten Update werden die neuen Koordinaten verwendet
    return currentLocation;
}

// Funktion zum Abrufen des aktuellen Standorts
export function getCurrentLocation() {
    return currentLocation;
}

export async function updateSky() {
    try {
        await skyRenderer.update();
        updateLastUpdated();
    } catch (error) {
        console.error('Error updating sky:', error);
        document.getElementById('sky-container').textContent = 'Error loading sky data';
    }
}

function updateLastUpdated() {
    const now = new Date();
    document.getElementById('last-updated').textContent = `Last updated: ${now.toLocaleTimeString()}`;
}

// skyRenderer wird bereits oben exportiert
