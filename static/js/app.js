// asciisky bootstrap: settings -> auth -> view -> controls -> first update.
// No timers stand in for an order (O15).
import { CONFIG, THEMES, debugLog } from './constants.js';
import { t, setLanguage, getCurrentLanguage, applyStaticTexts } from './i18n.js';
import { settingsManager } from './settings.js';
import { initAuth, openAuthDialog } from './auth.js';
import { SkyView } from './skyView.js';
import { SkyData } from './skyData.js';
import { SunpathChart } from './sunpathChart.js';
import { LocationDialog } from './locationDialog.js';
import { TimeInputDialog } from './timeInputDialog.js';
import { MagnitudeFilterDialog, fetchFilters } from './magnitudeFilterDialog.js';
import { ObjectList, DetailPanel } from './ui/panels.js';
import { openHelp } from './ui/help.js';
import { AppDialog } from './ui/dialog.js';
import { el } from './ui/dom.js';
import { compassPoint, displayName, fmtDateTime, fmtNumber } from './ui/format.js';

const $ = (id) => document.getElementById(id);
const SOLAR_DAY_MIN = 24 * 60;
const MAX_OFFSET_MIN = 525600;
// Phones in either orientation start with a part of the horizon.
const phone = () => matchMedia('(max-width: 767px), (max-height: 500px)').matches;
const narrow = () => matchMedia('(max-width: 767px)').matches;

const state = {
    selected: null, // { kind: 'body' | 'messier', name }
    filters: null,
    layers: { constellations: false, messier: false, grid: true },
};

let view;
let data;
let list;
let detail;
let sunpath;
let locationDialog;
let timeDialog;
let filterDialog;
let appearanceDialog;
let updateTimer = null;
let tickTimer = null;
let updateDebounce = null;

// ----- theme and language -----

function applyTheme(theme) {
    const root = document.documentElement;
    root.dataset.theme = theme;
    const bg = getComputedStyle(root).getPropertyValue('--bg').trim();
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', bg || '#050805');
}

function applyLanguage() {
    document.documentElement.lang = getCurrentLanguage();
    applyStaticTexts(document);
    view.setLanguage(
        { north: t('north'), east: t('east'), south: t('south'), west: t('west') },
        displayName,
    );
    updateLocationTitle();
    updateTimeDisplay();
    list.render();
    refreshDetail();
    updateCounts();
    updateAuthButton();
}

function openAppearance() {
    if (!appearanceDialog) appearanceDialog = new AppDialog('appearance-dialog');
    const render = () => {
        appearanceDialog.setTitle(t('appearance'));
        const current = settingsManager.getTheme();
        const themes = el('div', { class: 'swatches', role: 'group', 'aria-label': t('theme') },
            THEMES.map((name) => el('button', {
                type: 'button', class: 'swatch', 'data-swatch': name,
                'aria-pressed': String(name === current),
                onclick: () => { settingsManager.setTheme(name); applyTheme(name); render(); },
            }, el('span', { class: 'swatch-dot', 'aria-hidden': 'true' }), t(`theme_${name}`))));
        const lang = getCurrentLanguage();
        const langs = el('div', { class: 'segmented', role: 'group', 'aria-label': t('language') },
            [['de', 'Deutsch'], ['en', 'English']].map(([code, label]) => el('button', {
                type: 'button', class: 'seg-btn', 'aria-pressed': String(code === lang), lang: code,
                onclick: () => { settingsManager.setLanguage(code); setLanguage(code); applyLanguage(); render(); },
            }, label)));
        appearanceDialog.setBody(
            el('h3', {}, t('theme')), themes,
            el('h3', {}, t('language')), langs,
            el('p', { class: 'dialog-hint' }, t('theme_hint')));
    };
    render();
    appearanceDialog.open();
}

// ----- location, time -----

function updateLocationTitle() {
    const loc = settingsManager.getLocation();
    $('location-name').textContent = loc.name || `${loc.latitude.toFixed(2)}, ${loc.longitude.toFixed(2)}`;
    $('location-btn').title = t('location_settings');
}

function updateTimeDisplay() {
    const tz = settingsManager.getLocation().timezone || undefined;
    let parts;
    try {
        parts = fmtDateTime(settingsManager.getSkyDate(), tz, { short: narrow() });
    } catch (_) {
        parts = fmtDateTime(settingsManager.getSkyDate(), undefined, { short: narrow() });
    }
    $('time-date').textContent = parts.day;
    $('time-clock').textContent = parts.time;
    const simulated = settingsManager.isSimulatedTimeEnabled();
    $('time-sim').hidden = !simulated;
    // On phones the "now" button stands in for the SIM badge (layout.css).
    $('time-bar').classList.toggle('is-sim', simulated);
}

function shiftTime(deltaMinutes) {
    const next = Math.max(-MAX_OFFSET_MIN, Math.min(MAX_OFFSET_MIN, settingsManager.getSimulatedOffsetMinutes() + deltaMinutes));
    setOffset(next);
}

function setOffset(minutes) {
    settingsManager.setSimulatedTime(minutes);
    updateTimeDisplay();
    requestUpdate(120);
}

async function changeLocation(loc) {
    await settingsManager.setLocation(loc.latitude, loc.longitude, loc.elevation, loc.name);
    data.reset();
    view.setBodies({});
    view.setConstellations([]);
    view.setMessier([]);
    updateLocationTitle();
    updateTimeDisplay();
    requestUpdate();
}

// ----- data -----

function requestUpdate(delayMs = 0) {
    clearTimeout(updateDebounce);
    updateDebounce = setTimeout(() => {
        data.update({
            location: settingsManager.getLocation(),
            timeISO: settingsManager.getSimulatedTimeISO(),
            constellations: state.layers.constellations,
            messier: state.layers.messier,
        });
    }, delayMs);
}

function startTimers() {
    stopTimers();
    updateTimer = setInterval(() => requestUpdate(), CONFIG.UPDATE_INTERVAL_MS);
    tickTimer = setInterval(updateTimeDisplay, 1000);
}

function stopTimers() {
    clearInterval(updateTimer);
    clearInterval(tickTimer);
    updateTimer = null;
    tickTimer = null;
}

function setLoading(on) {
    clearTimeout(setLoading._t);
    // Only show the indicator when loading takes noticeably long.
    if (on) setLoading._t = setTimeout(() => { $('loading').hidden = false; }, 300);
    else $('loading').hidden = true;
}

function setError(error) {
    const banner = $('status-banner');
    if (!error) {
        banner.hidden = true;
        return;
    }
    $('status-text').textContent = t('data_stale');
    banner.hidden = false;
}

function updateCounts() {
    const bodies = Object.values(data?.bodies || {});
    const up = (type) => bodies.filter((b) => b.type === type && b.altitude > 0).length;
    const f = state.filters;
    const ast = f ? `${t('asteroids')} ≤ ${fmtNumber(f.asteroidMaxMagnitude)}: ${up('asteroid')}` : '';
    const com = f ? `${t('comets')} ≤ ${fmtNumber(f.cometMaxMagnitude)}: ${up('comet')}` : '';
    $('counts').textContent = [ast, com].filter(Boolean).join(' · ');
}

// ----- selection -----

function findSelected() {
    const sel = state.selected;
    if (!sel) return null;
    if (sel.kind === 'messier') {
        const obj = (data.messier || []).find((m) => m.id === sel.name);
        return obj ? { kind: 'messier', obj: { ...obj, ...(sel.details || {}), altitude: obj.altitude, azimuth: obj.azimuth } } : null;
    }
    const obj = Object.values(data.bodies || {}).find((b) => b.name === sel.name);
    return obj ? { kind: 'body', obj } : null;
}

function refreshDetail() {
    if (!state.selected || state.selected.choice) return;
    const found = findSelected();
    if (!found) return; // keep the last values until the object is back
    detail.showObject(found.kind, found.obj, settingsManager.getLocation().timezone);
}

function select(hit, { reveal = false } = {}) {
    if (!hit) {
        clearSelection();
        return;
    }
    const name = hit.kind === 'messier' ? hit.obj.id : hit.obj.name;
    state.selected = { kind: hit.kind, name };
    view.setSelected(hit.kind === 'body' ? name : null);
    list.update({ selectedName: hit.kind === 'body' ? name : null });
    detail.showObject(hit.kind, hit.obj, settingsManager.getLocation().timezone);
    if (reveal && view.view.mode === 'horizon' && view.view.fov < 360 && Number.isFinite(hit.obj.azimuth)) {
        view.setView({ centerAz: hit.obj.azimuth });
        persistView(view.view);
    }
    if (narrow()) list.setSheet('peek');
    if (hit.kind === 'messier') {
        const selectedAt = state.selected;
        data.messierDetails(name, settingsManager.getLocation(), settingsManager.getSimulatedTimeISO())
            .then((d) => {
                if (!d || state.selected !== selectedAt) return;
                selectedAt.details = d;
                refreshDetail();
            })
            .catch((err) => console.error('Messier details failed:', err));
    }
}

function clearSelection() {
    state.selected = null;
    view.setSelected(null);
    list.update({ selectedName: null });
    detail.hide();
}

function onSkyTap(hits) {
    if (!hits.length) {
        clearSelection();
        return;
    }
    // Several objects equally near: offer a choice.
    const near = hits.filter((h) => h.d - hits[0].d < 0.5);
    const unique = [];
    const seen = new Set();
    for (const h of near) {
        const key = `${h.kind}:${h.kind === 'messier' ? h.obj.id : h.obj.name}`;
        if (!seen.has(key)) { seen.add(key); unique.push(h); }
    }
    if (unique.length > 1) {
        state.selected = { choice: true };
        detail.showChoice(unique);
    } else {
        select(unique[0]);
    }
}

// ----- view controls -----

function persistView(v) {
    settingsManager.setViewMode(v.mode);
    if (v.mode === 'planisphere') {
        settingsManager.setPlanisphereRotation(v.rotation);
        settingsManager.setPlanisphereZoom(v.zoom);
    } else {
        settingsManager.setCenterAz(v.centerAz);
        settingsManager.setFov(v.fov);
    }
}

function onViewChange(v) {
    const horizon = v.mode === 'horizon';
    $('view-horizon').setAttribute('aria-selected', String(horizon));
    $('view-planisphere').setAttribute('aria-selected', String(!horizon));
    $('zoom-label').textContent = horizon ? `${v.fov}°` : `${fmtNumber(v.zoom, v.zoom % 1 ? 1 : 0)}×`;
    $('zoom-in').disabled = horizon ? v.fov === CONFIG.FOV_LEVELS.at(-1) : v.zoom === CONFIG.PLANISPHERE_ZOOM_LEVELS.at(-1);
    $('zoom-out').disabled = horizon ? v.fov === CONFIG.FOV_LEVELS[0] : v.zoom === CONFIG.PLANISPHERE_ZOOM_LEVELS[0];
    $('compass').textContent = horizon
        ? `${compassPoint(v.centerAz)} ${Math.round(v.centerAz)}°`
        : `⟲ ${Math.round(v.rotation)}°`;
}

function turnStep() {
    const v = view.view;
    return v.mode === 'planisphere' ? 15 : Math.max(5, v.fov / 24);
}

function setLayer(name, on) {
    state.layers[name] = on;
    $(`layer-${name}`).setAttribute('aria-pressed', String(on));
    view.setLayers({ [name]: on });
    if (name === 'constellations') {
        settingsManager.setConstellationsVisible(on);
        if (on && !data.constellations) requestUpdate();
    } else if (name === 'messier') {
        settingsManager.setMessierVisible(on);
        if (on && !data.messier) requestUpdate();
    } else if (name === 'grid') {
        settingsManager.setGridVisible(on);
    }
}

function bindControls() {
    $('location-btn').addEventListener('click', () => locationDialog.open(settingsManager.getLocation()));
    $('appearance-btn').addEventListener('click', openAppearance);
    $('auth-btn').addEventListener('click', openAuthDialog);
    $('help-btn').addEventListener('click', openHelp);

    $('time-day-minus').addEventListener('click', () => shiftTime(-SOLAR_DAY_MIN));
    $('time-hour-minus').addEventListener('click', () => shiftTime(-60));
    $('time-hour-plus').addEventListener('click', () => shiftTime(60));
    $('time-day-plus').addEventListener('click', () => shiftTime(SOLAR_DAY_MIN));
    $('time-now').addEventListener('click', () => setOffset(0));
    $('time-display').addEventListener('click', () => timeDialog.open());

    $('view-horizon').addEventListener('click', () => { view.setView({ mode: 'horizon' }); persistView(view.view); });
    $('view-planisphere').addEventListener('click', () => { view.setView({ mode: 'planisphere' }); persistView(view.view); });
    for (const name of ['constellations', 'messier', 'grid']) {
        $(`layer-${name}`).addEventListener('click', () => setLayer(name, !state.layers[name]));
    }
    $('sunpath-btn').addEventListener('click', () => sunpath.open(settingsManager.getLocation(), settingsManager.getSkyDate()));
    $('zoom-in').addEventListener('click', () => view.stepZoom(1));
    $('zoom-out').addEventListener('click', () => view.stepZoom(-1));
    $('turn-left').addEventListener('click', () => view.turn(-turnStep()));
    $('turn-right').addEventListener('click', () => view.turn(turnStep()));
    $('status-retry').addEventListener('click', () => requestUpdate());

    document.addEventListener('keydown', onKey);
    document.addEventListener('visibilitychange', () => {
        // Pause in background tabs and catch up at once when shown (O13).
        if (document.hidden) {
            stopTimers();
        } else {
            updateTimeDisplay();
            requestUpdate();
            startTimers();
        }
    });
    window.addEventListener('locationTimezoneUpdated', updateTimeDisplay);
}

function onKey(e) {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.querySelector('dialog[open]')) return;
    const tag = e.target?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    const actions = {
        ArrowLeft: () => view.turn(-turnStep()),
        ArrowRight: () => view.turn(turnStep()),
        ArrowUp: () => view.tilt(turnStep()),
        ArrowDown: () => view.tilt(-turnStep()),
        '+': () => view.stepZoom(1),
        '=': () => view.stepZoom(1),
        '-': () => view.stepZoom(-1),
        h: () => $('view-horizon').click(),
        p: () => $('view-planisphere').click(),
        t: () => setOffset(0),
        '[': () => shiftTime(-60),
        ']': () => shiftTime(60),
        '{': () => shiftTime(-SOLAR_DAY_MIN),
        '}': () => shiftTime(SOLAR_DAY_MIN),
        Escape: () => clearSelection(),
    };
    const action = actions[e.key] || actions[e.key.toLowerCase?.()];
    if (!action) return;
    e.preventDefault();
    action();
}

function updateAuthButton(user = undefined) {
    if (user !== undefined) updateAuthButton.user = user;
    const u = updateAuthButton.user;
    const btn = $('auth-btn');
    btn.title = u ? `${t('account')}: ${u.username}` : t('login_register');
    btn.setAttribute('aria-label', btn.title);
    btn.classList.toggle('is-active', !!u);
}

// ----- start -----

async function main() {
    await settingsManager.initialize();
    const lang = settingsManager.getLanguage() || ((navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en');
    setLanguage(lang);
    applyTheme(settingsManager.getTheme());
    await initAuth((user) => updateAuthButton(user));

    state.layers = {
        constellations: settingsManager.getConstellationsVisible(),
        messier: settingsManager.getMessierVisible(),
        grid: settingsManager.getGridVisible(),
    };

    view = new SkyView($('sky'), {
        onSelect: onSkyTap,
        onViewChange,
        onViewCommit: persistView,
    });
    view.setView({
        mode: settingsManager.getViewMode(),
        centerAz: settingsManager.getCenterAz(),
        fov: settingsManager.getFov() ?? (phone() ? 120 : 360),
        rotation: settingsManager.getPlanisphereRotation(),
        zoom: settingsManager.getPlanisphereZoom(),
    });
    view.setLayers(state.layers);
    for (const [name, on] of Object.entries(state.layers)) $(`layer-${name}`).setAttribute('aria-pressed', String(on));

    list = new ObjectList($('list-panel'), {
        onPick: (body) => select({ kind: 'body', obj: body }, { reveal: true }),
        onFilters: () => filterDialog.open(),
    });
    detail = new DetailPanel($('detail-panel'), {
        onClose: clearSelection,
        onPick: (hit) => select(hit),
    });
    sunpath = new SunpathChart();
    locationDialog = new LocationDialog((loc) => changeLocation(loc));
    timeDialog = new TimeInputDialog((offset) => setOffset(offset));
    filterDialog = new MagnitudeFilterDialog((filters) => {
        state.filters = filters;
        list.update({ filters });
        updateCounts();
        requestUpdate();
    });

    data = new SkyData({
        onBodies: (bodies) => {
            view.setBodies(bodies);
            list.update({ bodies });
            refreshDetail();
            updateCounts();
        },
        onConstellations: (c) => view.setConstellations(c),
        onMessier: (m) => { view.setMessier(m); refreshDetail(); },
        onLoading: setLoading,
        onError: setError,
    });

    bindControls();
    applyLanguage();
    requestUpdate();
    startTimers();
    fetchFilters().then((filters) => {
        state.filters = filters;
        list.update({ filters });
        updateCounts();
    });
    debugLog('asciisky started');
}

main().catch((error) => {
    console.error('asciisky failed to start:', error);
    const banner = $('status-banner');
    if (banner) {
        $('status-text').textContent = t('error_loading');
        banner.hidden = false;
    }
});
