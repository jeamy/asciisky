import { API_ENDPOINTS } from './constants.js';
import { t } from './i18n.js';
import { settingsManager } from './settings.js';

let panelEl = null;

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

function renderStatus(data, currentLocKey, locationName) {
  const el = ensurePanel();
  if (!el) return;

  const match = (data.locations || []).find(loc => loc.loc_key === currentLocKey);

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
  `;
}

export function initCacheStatusPanel(elementId = 'cache-status-panel') {
  const el = document.getElementById(elementId);
  if (el) setPanel(el);
}

export async function updateCacheStatusForLocation(lat, lon, elevation, locationName = '') {
  try {
    renderLoading(locationName);
    const url = appendTimeParam(API_ENDPOINTS.CACHE_STATUS);
    const resp = await fetch(url, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const key = buildLocKey(lat, lon, elevation);
    renderStatus(data, key, locationName);
  } catch (err) {
    renderError(err, locationName);
  }
}
