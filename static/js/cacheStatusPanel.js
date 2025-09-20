import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';

let panelEl = null;
let __debounceTimer = null;

function setPanel(el) {
  panelEl = el;
}

function ensurePanel() {
  if (!panelEl) {
    panelEl = document.getElementById('cache-status-panel');
  }
  return panelEl;
}

function appendTimeParam(url) {
  try {
    const iso = settingsManager.getSimulatedTimeISO && settingsManager.getSimulatedTimeISO();
    if (iso) {
      const sep = url.includes('?') ? '&' : '?';
      return `${url}${sep}time=${encodeURIComponent(iso)}`;
    }
    return url;
  } catch (_) {
    return url;
  }
}

function signPadInt(n, width = 5) {
  const sign = n >= 0 ? '+' : '-';
  const abs = Math.abs(Math.trunc(n));
  return sign + String(abs).padStart(width - 1, '0');
}

function formatSignedFixed(x, decimals = 4) {
  let s = Number(x).toFixed(decimals);
  if (!s.startsWith('-')) s = '+' + s;
  return s;
}

function normalizeLocation(lat, lon, elevation) {
  const latN = Number(lat).toFixed(4);
  const lonN = Number(lon).toFixed(4);
  // Simple ceiling approach - always round up to next 10m step
  const elevN = Math.ceil(Number(elevation) / 10) * 10;
  return { lat: Number(latN), lon: Number(lonN), elev: elevN };
}

function buildLocKey(lat, lon, elevation) {
  const n = normalizeLocation(lat, lon, elevation);
  const latStr = formatSignedFixed(n.lat, 4);
  const lonStr = formatSignedFixed(n.lon, 4);
  const elevStr = signPadInt(n.elev, 5);
  return `lat${latStr}_lon${lonStr}_el${elevStr}`;
}

function toLocalHM(iso) {
  if (!iso) return '—';
  try {
    let d;
    
    // Check if this is a time bucket format (YYYYMMDDTHH)
    if (typeof iso === 'string' && /^\d{8}T\d{2}$/.test(iso)) {
      // Parse bucket format: YYYYMMDDTHH
      d = new Date();
      const year = parseInt(iso.slice(0, 4));
      const month = parseInt(iso.slice(4, 6)) - 1; // Month is 0-based
      const day = parseInt(iso.slice(6, 8));
      const hour = parseInt(iso.slice(9, 11));
      d = new Date(year, month, day, hour, 0, 0);
    } else {
      // Parse ISO format
      d = new Date(iso);
    }
    
    if (isNaN(d.getTime())) return '—';
    
    // Format as DD.MM., HH:MM in local time
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${day}.${month}., ${hours}:${minutes}`;
  } catch (e) {
    return '—';
  }
}

function minIsoTimestamp(isos) {
  const list = (isos || []).filter(Boolean);
  if (!list.length) return null;
  let minT = Infinity;
  let minS = null;
  for (const s of list) {
    let t;
    // Handle time bucket format (YYYYMMDDTHH)
    if (typeof s === 'string' && /^\d{8}T\d{2}$/.test(s)) {
      const year = parseInt(s.slice(0, 4));
      const month = parseInt(s.slice(4, 6)) - 1;
      const day = parseInt(s.slice(6, 8));
      const hour = parseInt(s.slice(9, 11));
      t = new Date(year, month, day, hour, 0, 0).getTime();
    } else {
      t = new Date(s).getTime();
    }
    if (!isNaN(t) && t < minT) {
      minT = t;
      minS = s;
    }
  }
  return minS;
}

function maxIsoTimestamp(isos) {
  const list = (isos || []).filter(Boolean);
  if (!list.length) return null;
  let maxT = -Infinity;
  let maxS = null;
  for (const s of list) {
    let t;
    // Handle time bucket format (YYYYMMDDTHH)
    if (typeof s === 'string' && /^\d{8}T\d{2}$/.test(s)) {
      const year = parseInt(s.slice(0, 4));
      const month = parseInt(s.slice(4, 6)) - 1;
      const day = parseInt(s.slice(6, 8));
      const hour = parseInt(s.slice(9, 11));
      t = new Date(year, month, day, hour, 0, 0).getTime();
    } else {
      t = new Date(s).getTime();
    }
    if (!isNaN(t) && t > maxT) {
      maxT = t;
      maxS = s;
    }
  }
  return maxS;
}

function renderError(err, locationName) {
  const el = ensurePanel();
  if (!el) return;
  el.innerHTML = `
    <div class="cs-header">${t('cache_status') || 'Cache Status'}</div>
    <div class="cs-subtle">${locationName ? (t('location') || 'Location') + ': ' + locationName : ''}</div>
    <div class="cs-section cs-error">${t('error') || 'Error'}: ${String(err)}</div>
  `;
}

function renderStatus(data, currentLocKey, locationName) {
  const el = ensurePanel();
  if (!el) return;

  // Intelligente Standortsuche mit mehreren Strategien
  let match = null;
  
  if (data.locations && data.locations.length > 0) {
    // Strategie 1: Exakter Schlüssel-Match
    match = data.locations.find(loc => loc.loc_key === currentLocKey);
    
    if (!match) {
      // Strategie 2: Koordinaten-basierter Match (ignoriere Höhe)
      const currentCoords = extractCoordsFromLocKey(currentLocKey);
      if (currentCoords) {
        match = data.locations.find(loc => {
          const coords = extractCoordsFromLocKey(loc.loc_key);
          return coords && 
                 Math.abs(coords.lat - currentCoords.lat) < 0.001 && 
                 Math.abs(coords.lon - currentCoords.lon) < 0.001;
        });
      }
    }
    
    if (!match) {
      // Strategie 3: Nimm den ersten verfügbaren Standort
      match = data.locations[0];
    }
  }

  const start = data?.window?.start ? toLocalHM(data.window.start) : '—';
  const end = data?.window?.end ? toLocalHM(data.window.end) : '—';
  const horizon = data?.precompute_horizon_hours;

  const kinds = Array.isArray(data?.kinds) ? data.kinds : [];

  if (!match) {
    el.innerHTML = `
      <div class="cs-header">${t('cache_status') || 'Cache Status'}</div>
      <div class="cs-subtle">${locationName ? (t('location') || 'Location') + ': ' + locationName : ''}</div>
      <div class="cs-section">${t('window') || 'Window'}: ${start} → ${end} ${horizon ? `(${horizon}h)` : ''}</div>
      <div class="cs-section cs-subtle">${t('no_data_for_location') || 'No cache data for this location in the current window.'}</div>
    `;
    return;
  }

  // Compute overall coverage (earliest to latest across all kinds for this location)
  const earliestList = kinds.map(k => match.earliest?.[k]).filter(Boolean);
  const latestList = kinds.map(k => match.latest?.[k]).filter(Boolean);
  const overallEarliestIso = minIsoTimestamp(earliestList);
  const overallLatestIso = maxIsoTimestamp(latestList);
  const overallEarliest = overallEarliestIso ? toLocalHM(overallEarliestIso) : '—';
  const overallLatest = overallLatestIso ? toLocalHM(overallLatestIso) : '—';

  // Render per-kind status
  const items = kinds.map(kind => {
    const count = match.counts?.[kind] || 0;
    const earliest = match.earliest?.[kind] ? toLocalHM(match.earliest[kind]) : '—';
    const latest = match.latest?.[kind] ? toLocalHM(match.latest[kind]) : '—';
    const kindName = t(kind) || kind;
    return `<div class="cs-kind">
      <div class="cs-section-title">${kindName}: ${count} ${t('snapshots') || 'Snapshots'}</div>
      <div class="cs-time-range">${earliest} →</div>
      <div class="cs-time-range">${latest}</div>
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="cs-header">${t('cache_status') || 'Cache-Status'}</div>
    <div class="cs-location">${locationName ? (t('location') || 'Standort') + ': ' + locationName : ''}</div>
    
    <div class="cs-section">
      <div class="cs-section-title">${t('window') || 'Zeitfenster'}:</div>
      <div class="cs-time-range">${start} →</div>
      <div class="cs-time-range">${end} ${horizon ? `(${horizon}h)` : ''}</div>
    </div>
    
    <div class="cs-section">
      <div class="cs-section-title">${t('overall_cache') || 'Gesamter Cache'}:</div>
      <div class="cs-time-range">${overallEarliest} →</div>
      <div class="cs-time-range">${overallLatest}</div>
    </div>
    
    <div class="cs-kinds-section">${items}</div>
  `;
}

function extractCoordsFromLocKey(locKey) {
  if (!locKey) return null;
  try {
    // Parse format: lat+46.7632_lon+14.8416_el+0400
    const latMatch = locKey.match(/lat([+-]\d+\.\d+)/);
    const lonMatch = locKey.match(/lon([+-]\d+\.\d+)/);
    if (latMatch && lonMatch) {
      return {
        lat: parseFloat(latMatch[1]),
        lon: parseFloat(lonMatch[1])
      };
    }
  } catch (e) {
    console.warn('Failed to parse location key:', locKey, e);
  }
  return null;
}

export function initCacheStatusPanel(elementId = 'cache-status-panel') {
  const el = document.getElementById(elementId);
  if (el) setPanel(el);
}

export async function updateCacheStatusForLocation(lat, lon, elevation, locationName) {
  try {
    const locKey = buildLocKey(lat, lon, elevation);
    const url = appendTimeParam(`${API_ENDPOINTS.CACHE_STATUS}?lat=${lat}&lon=${lon}&elevation=${elevation}&loc_key=${encodeURIComponent(locKey)}&nocache=1`);
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    renderStatus(data, locKey, locationName);
  } catch (error) {
    console.error('Error fetching cache status:', error);
    renderError(error.message || String(error), locationName);
  }
}

export function updateCacheStatusForLocationDebounced(lat, lon, elevation, locationName) {
  if (__debounceTimer) {
    clearTimeout(__debounceTimer);
  }
  __debounceTimer = setTimeout(() => {
    updateCacheStatusForLocation(lat, lon, elevation, locationName);
  }, 300);
}
