import { SkyRenderer } from './skyRenderer.js';
import { CONFIG } from './constants.js';

// Deklariere skyRenderer als exportierte Variable
export let skyRenderer;

export function initializeMoonTracker() {
    // Initialize the sky renderer
    skyRenderer = new SkyRenderer('sky-container');
    
    // Set up periodic updates
    setInterval(updateSky, CONFIG.UPDATE_INTERVAL_MS);
    
    return skyRenderer;
}

async function updateSky() {
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
