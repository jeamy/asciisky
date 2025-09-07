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
    const d = new Date(iso);
    return d.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  } catch (_) {
    return String(iso);
  }
}

function minIsoTimestamp(isos) {
  const list = (isos || []).filter(Boolean);
  if (!list.length) return null;
  let minT = Infinity;
  let minS = null;
  for (const s of list) {
    const t = Date.parse(s);
    if (!Number.isNaN(t) && t < minT) { minT = t; minS = s; }
  }
  return minS;
}

function maxIsoTimestamp(isos) {
  const list = (isos || []).filter(Boolean);
  if (!list.length) return null;
  let maxT = -Infinity;
  let maxS = null;
  for (const s of list) {
    const t = Date.parse(s);
    if (!Number.isNaN(t) && t > maxT) { maxT = t; maxS = s; }
  }
  return maxS;
}

function renderLoading(locationName) {
  const el = ensurePanel();
  if (!el) return;
  el.innerHTML = `
    <div class="cs-header">${t('cache_status') || 'Cache Status'}</div>
    <div class="cs-subtle">${locationName ? (t('location') || 'Location') + ': ' + locationName : ''}</div>
    <div class="cs-section">${t('loading') || 'Loading...'} </div>
  `;
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

let activePrecomputeTask = null;
let precomputeTaskCheckInterval = null;

// LocalStorage keys
const STORAGE_KEY_ACTIVE_TASK = 'asciisky_active_precompute_task';

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
      const keyParts = currentLocKey.split('_');
      if (keyParts.length >= 2) {
        const latPart = keyParts[0].substring(3); // Entferne 'lat'
        const lonPart = keyParts[1].substring(3); // Entferne 'lon'
        
        // Finde alle Standorte mit ähnlichen Koordinaten
        const coordMatches = data.locations.filter(loc => {
          const latMatch = Math.abs(loc.latitude - parseFloat(latPart)) < 0.0001;
          const lonMatch = Math.abs(loc.longitude - parseFloat(lonPart)) < 0.0001;
          return latMatch && lonMatch;
        });
        
        if (coordMatches.length > 0) {
          // Bevorzuge Standorte mit den meisten Snapshots
          match = coordMatches.reduce((best, current) => {
            const bestTotal = (best.counts?.celestial || 0) + (best.counts?.asteroids || 0) + (best.counts?.comets || 0);
            const currentTotal = (current.counts?.celestial || 0) + (current.counts?.asteroids || 0) + (current.counts?.comets || 0);
            return currentTotal > bestTotal ? current : best;
          });
        }
      }
    }
    
    // Strategie 3: Fallback auf besten verfügbaren Standort
    if (!match) {
      match = data.locations.reduce((best, current) => {
        const bestTotal = (best.counts?.celestial || 0) + (best.counts?.asteroids || 0) + (best.counts?.comets || 0);
        const currentTotal = (current.counts?.celestial || 0) + (current.counts?.asteroids || 0) + (current.counts?.comets || 0);
        return currentTotal > bestTotal ? current : best;
      });
    }
    
  }

  const start = data?.window?.start ? toLocalHM(data.window.start) : '—';
  const end = data?.window?.end ? toLocalHM(data.window.end) : '—';
  const horizon = data?.precompute_horizon_hours;

  const kinds = Array.isArray(data?.kinds) ? data.kinds : [];

  // We'll set this to true only if we confirm the task exists on the server
  // This ensures the UI starts in a clean state
  const hasActiveTask = false;
  
  // Prepare the precompute section
  const precomputeSection = `
    <div class="cache-precompute">
      <div class="cache-precompute-title">${t('precompute_cache') || 'Precompute Cache'}</div>
      <div class="cache-precompute-form">
        <div class="cache-precompute-row">
          <label class="cache-precompute-label">${t('start_date') || 'Start Date'}:</label>
          <input type="date" id="cache-start-date" class="cache-precompute-input" ${hasActiveTask ? 'disabled' : ''}>
        </div>
        <div class="cache-precompute-row">
          <label class="cache-precompute-label">${t('end_date') || 'End Date'}:</label>
          <input type="date" id="cache-end-date" class="cache-precompute-input" ${hasActiveTask ? 'disabled' : ''}>
        </div>
        <button id="cache-precompute-button" class="cache-precompute-button" ${hasActiveTask ? 'disabled' : ''}>
          ${hasActiveTask ? (t('processing') || 'Processing...') : (t('start_precompute') || 'Start Precompute')}
        </button>
      </div>
      <div id="cache-progress" class="cache-progress" style="display: ${hasActiveTask ? 'block' : 'none'};">
        <div class="cache-progress-bar">
          <div id="cache-progress-fill" class="cache-progress-fill" style="width: 0%"></div>
        </div>
        <div class="cache-progress-status">
          <span id="cache-progress-percent">0%</span>
          <span id="cache-progress-hours">0/0 hours</span>
        </div>
        <div id="cache-progress-details" class="cache-progress-details">${hasActiveTask ? (t('loading') || 'Loading...') : ''}</div>
      </div>
    </div>
  `;

  if (!match) {
    el.innerHTML = `
      <div class="cs-header">${t('cache_status') || 'Cache Status'}</div>
      <div class="cs-subtle">${locationName ? (t('location') || 'Location') + ': ' + locationName : ''}</div>
      <div class="cs-section">${t('window') || 'Window'}: ${start} → ${end} ${horizon ? `(${horizon}h)` : ''}</div>
      <div class="cs-section cs-subtle">${t('no_data_for_location') || 'No cache data for this location in the current window.'}</div>
      ${precomputeSection}
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

  const items = kinds.map(k => {
    const c = match.counts?.[k] ?? 0;
    const e = match.earliest?.[k] ? toLocalHM(match.earliest[k]) : '—';
    const l = match.latest?.[k] ? toLocalHM(match.latest[k]) : '—';
    const kindName = t(k) || k; // Use i18n translation for kind name
    return `
      <li class="cs-kind">
        <div class="head">
          <span class="name">${kindName}</span>
          <span class="counts">${c} ${(t('snapshots') || 'snapshots')}</span>
        </div>
        <div class="cs-row range"><span>${t('earliest') || 'Earliest'}:</span><span>${e}</span></div>
        <div class="cs-row range"><span>${t('latest') || 'Latest'}:</span><span>${l}</span></div>
      </li>
    `;
  }).join('');

  el.innerHTML = `
    <div class="cs-header">${t('cache_status') || 'Cache Status'}</div>
    <div class="cs-subtle">${locationName ? (t('location') || 'Location') + ': ' + locationName : ''}</div>
    <div class="cs-section">
      <div class="cs-row"><span>${t('window') || 'Window'}:</span><span>${start} → ${end} ${horizon ? `(${horizon}h)` : ''}</span></div>
      <div class="cs-row"><span>${t('overall_cache') || 'Total cache'}:</span><span>${overallEarliest} → ${overallLatest}</span></div>
    </div>
    <ul class="cs-kinds">${items}</ul>
    ${precomputeSection}
  `;
  
}

export function initCacheStatusPanel(elementId = 'cache-status-panel') {
  const el = document.getElementById(elementId);
  if (el) setPanel(el);
  
  // Start checking for active task immediately
  const savedTaskId = localStorage.getItem(STORAGE_KEY_ACTIVE_TASK);
  if (savedTaskId) {
    console.log('Found active task on init:', savedTaskId);
    
    // First check if the task still exists on the server
    fetch(`${API_ENDPOINTS.PRECOMPUTE_RANGE}/${savedTaskId}`)
      .then(response => {
        if (response.status === 404) {
          // Task doesn't exist anymore (server restarted)
          console.log('Task not found on server (server may have restarted)');
          localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
          // Don't need to reset UI here as it will be rendered fresh
          
          // Show a user-friendly message
          setTimeout(() => {
            const message = t('task_not_found_server_restart') || 'The precompute task is no longer active (server may have restarted). You can start a new precomputation if needed.';
            alert(message);
          }, 1000); // Delay to ensure UI is ready
          
          return null;
        } else if (response.ok) {
          return response.json();
        } else {
          throw new Error('Failed to check task status');
        }
      })
      .then(taskStatus => {
        if (taskStatus) {
          // Task exists, set up polling
          activePrecomputeTask = savedTaskId;
          
          // Start checking progress
          if (precomputeTaskCheckInterval) {
            clearInterval(precomputeTaskCheckInterval);
          }
          
          // Start polling for updates
          precomputeTaskCheckInterval = setInterval(async () => {
            await checkPrecomputeTaskProgress();
          }, 2000); // Check every 2 seconds
        }
      })
      .catch(error => {
        console.error('Error checking task status:', error);
        localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
      });
  }
}

// Function to restore active precompute task from localStorage
async function restoreActivePrecomputeTask() {
  const savedTaskId = localStorage.getItem(STORAGE_KEY_ACTIVE_TASK);
  if (!savedTaskId) return;
  
  try {
    console.log('Restoring active precompute task:', savedTaskId);
    // Set the active task ID
    activePrecomputeTask = savedTaskId;
    
    // Wait for the precompute section to be rendered
    setTimeout(async () => {
      // Show progress container
      const progressContainer = document.getElementById('cache-progress');
      if (progressContainer) {
        progressContainer.style.display = 'block';
      } else {
        console.error('Progress container not found');
      }
      
      // Disable inputs during processing
      const startDateInput = document.getElementById('cache-start-date');
      const endDateInput = document.getElementById('cache-end-date');
      const precomputeButton = document.getElementById('cache-precompute-button');
      
      if (startDateInput && endDateInput && precomputeButton) {
        startDateInput.disabled = true;
        endDateInput.disabled = true;
        precomputeButton.disabled = true;
        precomputeButton.textContent = t('processing') || 'Processing...';
      } else {
        console.error('Precompute inputs not found');
      }
      
      // Start checking progress
      if (precomputeTaskCheckInterval) {
        clearInterval(precomputeTaskCheckInterval);
      }
      
      // Check progress immediately
      await checkPrecomputeTaskProgress();
      
      // Then start interval
      precomputeTaskCheckInterval = setInterval(async () => {
        await checkPrecomputeTaskProgress();
      }, 2000); // Check every 2 seconds
    }, 500); // Wait for DOM to be ready
    
  } catch (error) {
    console.error('Error restoring precompute task:', error);
    localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
  }
}

// Globale Variable für Cache-Daten
let currentCacheData = null;
let liveUpdateInterval = null;

// Bestimme das maximale Enddatum basierend auf ASCII_SKY_MAX_PRECOMPUTE_HOURS
async function determineMaxEndDate() {
  try {
    // Hole die aktuelle Konfiguration vom Backend
    const response = await fetch('/api/cache_status');
    if (response.ok) {
      const data = await response.json();
      const maxHours = data.max_precompute_hours || 168;
      
      const today = new Date();
      const maxDate = new Date();
      maxDate.setTime(today.getTime() + (maxHours * 60 * 60 * 1000));
      
      // Formatiere als YYYY-MM-DD für das Eingabefeld
      return maxDate.toISOString().split('T')[0];
    }
  } catch (error) {
    console.error('Error fetching max precompute hours:', error);
  }
  
  // Fallback: 168 Stunden (7 Tage) in die Zukunft
  const today = new Date();
  const maxDate = new Date();
  maxDate.setTime(today.getTime() + (168 * 60 * 60 * 1000));
  return maxDate.toISOString().split('T')[0];
}

// Starte automatische Live-Updates für Cache-Status
function startAutomaticLiveUpdates(lat, lon, elevation, locationName) {
  // Stoppe vorherige Updates
  if (liveUpdateInterval) {
    clearInterval(liveUpdateInterval);
  }
  
  // Starte neue Live-Updates alle 5 Sekunden
  liveUpdateInterval = setInterval(async () => {
    try {
      // Prüfe ob noch eine aktive Precompute-Task läuft
      const activeTaskId = localStorage.getItem('activePrecomputeTask');
      if (!activeTaskId) {
        // Keine aktive Task mehr - stoppe Updates
        clearInterval(liveUpdateInterval);
        liveUpdateInterval = null;
        console.log('Automatic live updates stopped - no active task');
        return;
      }
      
      // Aktualisiere Cache-Status ohne Loading-Anzeige zu zeigen
      await updateCacheStatusSilently(lat, lon, elevation, locationName);
      
    } catch (error) {
      console.error('Error during automatic live update:', error);
    }
  }, 5000); // Alle 5 Sekunden aktualisieren
  
  // Automatisch nach 10 Minuten stoppen als Fallback
  setTimeout(() => {
    if (liveUpdateInterval) {
      clearInterval(liveUpdateInterval);
      liveUpdateInterval = null;
      console.log('Automatic live updates stopped - timeout reached');
    }
  }, 600000); // 10 Minuten
}

// Stille Cache-Status-Aktualisierung ohne Loading-Anzeige
async function updateCacheStatusSilently(lat, lon, elevation, locationName = '') {
  try {
    // Store current location for potential task restoration
    window.currentCacheLocation = { lat, lon, elevation, locationName };
    let url = appendTimeParam(API_ENDPOINTS.CACHE_STATUS);
    
    // Wichtig: Sende die Rohdaten (lat, lon, elevation) an das Backend
    // und lasse das Backend die Normalisierung durchführen
    const sep = url.includes('?') ? '&' : '?';
    url = `${url}${sep}lat=${lat}&lon=${lon}&elevation=${elevation}`;
    
    // Zusätzlich den loc_key senden für Kompatibilität
    try {
      const key = buildLocKey(lat, lon, elevation);
      url = `${url}&loc_key=${encodeURIComponent(key)}`;
    } catch (_) { /* noop */ }
    
    const resp = await fetch(url, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const key = buildLocKey(lat, lon, elevation);
    
    // Speichere Cache-Daten global für Datumsbereichsbestimmung
    currentCacheData = data;
    
    // Render nur wenn sich die Daten geändert haben
    renderStatus(data, key, locationName);
    
  } catch (err) {
    console.error('Silent cache status update error:', err);
  }
}

export async function updateCacheStatusForLocation(lat, lon, elevation, locationName = '') {
  try {
    renderLoading(locationName);
    
    // Store current location for potential task restoration
    window.currentCacheLocation = { lat, lon, elevation, locationName };
    let url = appendTimeParam(API_ENDPOINTS.CACHE_STATUS);
    
    // Wichtig: Sende die Rohdaten (lat, lon, elevation) an das Backend
    // und lasse das Backend die Normalisierung durchführen
    const sep = url.includes('?') ? '&' : '?';
    url = `${url}${sep}lat=${lat}&lon=${lon}&elevation=${elevation}`;
    
    // Zusätzlich den loc_key senden für Kompatibilität
    try {
      const key = buildLocKey(lat, lon, elevation);
      url = `${url}&loc_key=${encodeURIComponent(key)}`;
    } catch (_) { /* noop */ }
    
    console.log('Cache status URL:', url); // Debug-Ausgabe
    
    const resp = await fetch(url, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const key = buildLocKey(lat, lon, elevation);
    
    // Speichere Cache-Daten global für Datumsbereichsbestimmung
    currentCacheData = data;
    
    console.log('Cache status data:', data); // Debug-Ausgabe
    console.log('Generated key:', key); // Debug-Ausgabe
    
    renderStatus(data, key, locationName);
    
    // Now that the panel is rendered, initialize form and check for active precompute task
    // This ensures all DOM elements are available
    setTimeout(async () => {
      await initializePrecomputeForm();
      restoreActivePrecomputeTask();
    }, 100);
    
    // Starte automatische Live-Updates wenn Daten verfügbar sind
    startAutomaticLiveUpdates(lat, lon, elevation, locationName);
  } catch (err) {
    console.error('Cache status error:', err); // Debug-Ausgabe
    renderError(err, locationName);
  }
}

// Initialize precompute form only once when panel is first rendered
async function initializePrecomputeForm() {
  const startDateInput = document.getElementById('cache-start-date');
  const endDateInput = document.getElementById('cache-end-date');
  const precomputeButton = document.getElementById('cache-precompute-button');
  
  if (!startDateInput || !endDateInput || !precomputeButton) return;
  
  // Only initialize if not already set
  if (!startDateInput.value) {
    const today = new Date();
    startDateInput.value = today.toISOString().split('T')[0];
  }
  
  if (!endDateInput.value) {
    const maxEndDate = await determineMaxEndDate();
    const nextWeek = new Date();
    nextWeek.setDate(new Date().getDate() + 7);
    endDateInput.value = maxEndDate || nextWeek.toISOString().split('T')[0];
  }
  
  // Setze min-Attribute für die Eingabefelder
  const today = new Date();
  const todayStr = today.toISOString().split('T')[0];
  startDateInput.setAttribute('min', todayStr);
  endDateInput.setAttribute('min', todayStr);
  
  // Kein Maximum setzen - Benutzer soll frei wählen können
  // Das Backend begrenzt auf ASCII_SKY_MAX_PRECOMPUTE_HOURS
  
  // Event-Listener für Datumsvalidierung - nur einmal hinzufügen
  if (!startDateInput.hasAttribute('data-listeners-added')) {
    startDateInput.addEventListener('change', () => {
      const startDate = startDateInput.value;
      if (startDate) {
        // Setze Mindestdatum für Enddatum auf Startdatum
        endDateInput.setAttribute('min', startDate);
        
        // Falls Enddatum vor Startdatum liegt, setze es auf Startdatum
        if (endDateInput.value && endDateInput.value < startDate) {
          endDateInput.value = startDate;
        }
      }
    });
    startDateInput.setAttribute('data-listeners-added', 'true');
  }
  
  if (!endDateInput.hasAttribute('data-listeners-added')) {
    endDateInput.addEventListener('change', () => {
      const endDate = endDateInput.value;
      const startDate = startDateInput.value;
      
      // Stelle sicher, dass Enddatum nicht vor Startdatum liegt
      if (startDate && endDate && endDate < startDate) {
        endDateInput.value = startDate;
      }
    });
    endDateInput.setAttribute('data-listeners-added', 'true');
  }
  
  // Handle precompute button click - nur einmal hinzufügen
  if (!precomputeButton.hasAttribute('data-listeners-added')) {
    precomputeButton.addEventListener('click', async () => {
    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    
    if (!startDate || !endDate) {
      alert(t('enter_both_dates') || 'Please enter both start and end dates');
      return;
    }
    
    try {
      // Disable inputs during processing
      startDateInput.disabled = true;
      endDateInput.disabled = true;
      precomputeButton.disabled = true;
      precomputeButton.textContent = t('processing') || 'Processing...';
      
      // Get current location
      const location = settingsManager.getLocation();
      if (!location) {
        throw new Error('No location set');
      }
      
      // Start the precompute task
      const response = await fetch(API_ENDPOINTS.PRECOMPUTE_RANGE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat: location.latitude,
          lon: location.longitude,
          elevation: location.elevation,
          start_date: `${startDate}T00:00:00Z`,
          end_date: `${endDate}T23:59:59Z`
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to start precompute task');
      }
      
      const result = await response.json();
      activePrecomputeTask = result.task_id;
      
      // Save task ID to localStorage
      localStorage.setItem(STORAGE_KEY_ACTIVE_TASK, activePrecomputeTask);
      
      // Show progress container
      const progressContainer = document.getElementById('cache-progress');
      if (progressContainer) {
        progressContainer.style.display = 'block';
      }
      progressFill.style.width = '0%';
      progressPercent.textContent = '0%';
      progressHours.textContent = `0/${result.hours_total} hours`;
      progressDetails.textContent = t('task_started') || 'Task started...';
      
      // Start checking progress
      if (precomputeTaskCheckInterval) {
        clearInterval(precomputeTaskCheckInterval);
      }
      
      precomputeTaskCheckInterval = setInterval(async () => {
        await checkPrecomputeTaskProgress();
      }, 2000); // Check every 2 seconds
      
    } catch (error) {
      alert(error.message || 'Failed to start precompute task');
      console.error('Precompute error:', error);
      
      // Re-enable inputs
      startDateInput.disabled = false;
      endDateInput.disabled = false;
      precomputeButton.disabled = false;
      precomputeButton.textContent = t('start_precompute') || 'Start Precompute';
    }
    });
    precomputeButton.setAttribute('data-listeners-added', 'true');
  }
}

async function checkPrecomputeTaskProgress() {
  if (!activePrecomputeTask) return;
  
  try {
    console.log('Checking progress for task:', activePrecomputeTask);
    const response = await fetch(`${API_ENDPOINTS.PRECOMPUTE_RANGE}/${activePrecomputeTask}`);
    
    // Handle 404 Not Found (task doesn't exist on server, likely after restart)
    if (response.status === 404) {
      console.log('Task not found on server (server may have restarted)');
      // Clear the task from localStorage
      localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
      activePrecomputeTask = null;
      
      // Stop checking progress
      if (precomputeTaskCheckInterval) {
        clearInterval(precomputeTaskCheckInterval);
        precomputeTaskCheckInterval = null;
      }
      
      // Re-enable inputs
      const startDateInput = document.getElementById('cache-start-date');
      const endDateInput = document.getElementById('cache-end-date');
      const precomputeButton = document.getElementById('cache-precompute-button');
      const progressContainer = document.getElementById('cache-progress');
      
      if (startDateInput && endDateInput && precomputeButton) {
        startDateInput.disabled = false;
        endDateInput.disabled = false;
        precomputeButton.disabled = false;
        precomputeButton.textContent = t('start_precompute') || 'Start Precompute';
      }
      
      if (progressContainer) {
        progressContainer.style.display = 'none';
      }
      
      // Show a user-friendly message
      const message = t('task_not_found_server_restart') || 'The precompute task is no longer active (server may have restarted). You can start a new precomputation if needed.';
      alert(message);
      
      return;
    }
    
    if (!response.ok) {
      throw new Error('Failed to check task progress');
    }
    
    const taskStatus = await response.json();
    
    // Update progress UI
    const progressFill = document.getElementById('cache-progress-fill');
    const progressPercent = document.getElementById('cache-progress-percent');
    const progressHours = document.getElementById('cache-progress-hours');
    const progressDetails = document.getElementById('cache-progress-details');
    const precomputeButton = document.getElementById('cache-precompute-button');
    const startDateInput = document.getElementById('cache-start-date');
    const endDateInput = document.getElementById('cache-end-date');
    
    if (progressFill && progressPercent && progressHours && progressDetails) {
      progressFill.style.width = `${taskStatus.percent_complete}%`;
      progressPercent.textContent = `${taskStatus.percent_complete}%`;
      progressHours.textContent = `${taskStatus.hours_completed}/${taskStatus.hours_total} hours`;
      
      if (taskStatus.status === 'completed') {
        progressDetails.textContent = t('task_completed') || 'Task completed!';
        
        // Re-enable inputs
        startDateInput.disabled = false;
        endDateInput.disabled = false;
        precomputeButton.disabled = false;
        precomputeButton.textContent = t('start_precompute') || 'Start Precompute';
        
        // Stop checking
        clearInterval(precomputeTaskCheckInterval);
        precomputeTaskCheckInterval = null;
        activePrecomputeTask = null;
        
        // Remove task ID from localStorage
        localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
        
        // Refresh cache status after a delay
        setTimeout(() => {
          const location = settingsManager.getLocation();
          if (location) {
            updateCacheStatusForLocation(location.latitude, location.longitude, location.elevation, location.name);
          }
        }, 1000);
        
      } else if (taskStatus.status === 'error') {
        progressDetails.textContent = `${t('error') || 'Error'}: ${taskStatus.error || 'Unknown error'}`;
        
        // Re-enable inputs
        startDateInput.disabled = false;
        endDateInput.disabled = false;
        precomputeButton.disabled = false;
        precomputeButton.textContent = t('start_precompute') || 'Start Precompute';
        
        // Stop checking
        clearInterval(precomputeTaskCheckInterval);
        precomputeTaskCheckInterval = null;
        activePrecomputeTask = null;
        
        // Remove task ID from localStorage
        localStorage.removeItem(STORAGE_KEY_ACTIVE_TASK);
        
      } else {
        progressDetails.textContent = `${t('status') || 'Status'}: ${taskStatus.status}`;
      }
    }
    
  } catch (error) {
    console.error('Error checking task progress:', error);
  }
}

export function updateCacheStatusForLocationDebounced(lat, lon, elevation, locationName = '') {
  try { if (__debounceTimer) clearTimeout(__debounceTimer); } catch (_) { /* noop */ }
  __debounceTimer = setTimeout(() => {
    updateCacheStatusForLocation(lat, lon, elevation, locationName);
  }, 300);
}
