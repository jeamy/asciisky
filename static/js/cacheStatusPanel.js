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
  const elevN = Math.round(Number(elevation) / 10) * 10;
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

function renderStatus(data, currentLocKey, locationName) {
  const el = ensurePanel();
  if (!el) return;

  const match = (data.locations || []).find(loc => loc.loc_key === currentLocKey);

  const start = data?.window?.start ? toLocalHM(data.window.start) : '—';
  const end = data?.window?.end ? toLocalHM(data.window.end) : '—';
  const horizon = data?.precompute_horizon_hours;

  const kinds = Array.isArray(data?.kinds) ? data.kinds : [];

  // Prepare the precompute section
  const precomputeSection = `
    <div class="cache-precompute">
      <div class="cache-precompute-title">${t('precompute_cache') || 'Precompute Cache'}</div>
      <div class="cache-precompute-form">
        <div class="cache-precompute-row">
          <label class="cache-precompute-label">${t('start_date') || 'Start Date'}:</label>
          <input type="date" id="cache-start-date" class="cache-precompute-input">
        </div>
        <div class="cache-precompute-row">
          <label class="cache-precompute-label">${t('end_date') || 'End Date'}:</label>
          <input type="date" id="cache-end-date" class="cache-precompute-input">
        </div>
        <button id="cache-precompute-button" class="cache-precompute-button">${t('start_precompute') || 'Start Precompute'}</button>
      </div>
      <div id="cache-progress" class="cache-progress" style="display: none;">
        <div class="cache-progress-bar">
          <div id="cache-progress-fill" class="cache-progress-fill"></div>
        </div>
        <div class="cache-progress-status">
          <span id="cache-progress-percent">0%</span>
          <span id="cache-progress-hours">0/0 hours</span>
        </div>
        <div id="cache-progress-details" class="cache-progress-details"></div>
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
    setupPrecomputeHandlers(locationName);
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
    return `
      <li class="cs-kind">
        <div class="head">
          <span class="name">${k}</span>
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
  
  setupPrecomputeHandlers(locationName);
}

export function initCacheStatusPanel(elementId = 'cache-status-panel') {
  const el = document.getElementById(elementId);
  if (el) setPanel(el);
}

export async function updateCacheStatusForLocation(lat, lon, elevation, locationName = '') {
  try {
    renderLoading(locationName);
    let url = appendTimeParam(API_ENDPOINTS.CACHE_STATUS);
    // Restrict backend scan to just this location via loc_key
    try {
      const key = buildLocKey(lat, lon, elevation);
      const sep = url.includes('?') ? '&' : '?';
      url = `${url}${sep}loc_key=${encodeURIComponent(key)}`;
    } catch (_) { /* noop */ }
    const resp = await fetch(url, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const key = buildLocKey(lat, lon, elevation);
    renderStatus(data, key, locationName);
  } catch (err) {
    renderError(err, locationName);
  }
}

// Debounced variant to avoid spamming the API during rapid simulated time changes
function setupPrecomputeHandlers(locationName) {
  // Set default dates (today and a week from today)
  const today = new Date();
  const nextWeek = new Date();
  nextWeek.setDate(today.getDate() + 7);
  
  const startDateInput = document.getElementById('cache-start-date');
  const endDateInput = document.getElementById('cache-end-date');
  const precomputeButton = document.getElementById('cache-precompute-button');
  const progressContainer = document.getElementById('cache-progress');
  const progressFill = document.getElementById('cache-progress-fill');
  const progressPercent = document.getElementById('cache-progress-percent');
  const progressHours = document.getElementById('cache-progress-hours');
  const progressDetails = document.getElementById('cache-progress-details');
  
  // Format dates for input fields (YYYY-MM-DD)
  startDateInput.value = today.toISOString().split('T')[0];
  endDateInput.value = nextWeek.toISOString().split('T')[0];
  
  // Handle precompute button click
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
      
      // Show progress container
      progressContainer.style.display = 'block';
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
}

async function checkPrecomputeTaskProgress() {
  if (!activePrecomputeTask) return;
  
  try {
    const response = await fetch(`${API_ENDPOINTS.PRECOMPUTE_RANGE}/${activePrecomputeTask}`);
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
