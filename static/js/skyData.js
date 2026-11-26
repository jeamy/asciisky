// Loads the sky for one place and time.  A new update aborts the one still
// running (L2), so the newest time always wins; errors keep the last good data
// and are reported, never written into the view (L16).
import { API_ENDPOINTS } from './constants.js';

const SMALL_BODY_PREFIXES = ['bright_asteroid_', 'comet_'];
const MESSIER_DETAIL_CACHE_MAX = 64;

function query(location, timeISO, extra = {}) {
    const params = new URLSearchParams({
        lat: String(location.latitude),
        lon: String(location.longitude),
        elevation: String(location.elevation ?? 0),
        ...extra,
    });
    if (timeISO) params.set('time', timeISO);
    return params.toString();
}

async function getJson(url, signal) {
    const resp = await fetch(url, { signal, credentials: 'same-origin' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url.split('?')[0]}`);
    return resp.json();
}

export class SkyData {
    /**
     * @param {object} handlers  onBodies(bodies), onConstellations(list), onMessier(list),
     *                           onLoading(bool), onError(error|null)
     */
    constructor(handlers) {
        this.h = handlers;
        this.bodies = {};
        this.constellations = null;
        this.messier = null;
        this._controller = null;
        this._messierDetails = new Map();
    }

    /** Start an update; the previous one, if still running, is aborted. */
    async update({ location, timeISO, constellations = false, messier = false }) {
        this._controller?.abort();
        const controller = new AbortController();
        this._controller = controller;
        const { signal } = controller;
        this.h.onLoading?.(true);
        let failed = null;
        try {
            const sky = await getJson(`${API_ENDPOINTS.CELESTIAL}?${query(location, timeISO)}`, signal);
            // Keep the small bodies of the previous update until their new
            // positions arrive, so they do not blink out on every tick.
            const kept = Object.fromEntries(Object.entries(this.bodies)
                .filter(([key]) => SMALL_BODY_PREFIXES.some((p) => key.startsWith(p))));
            this.bodies = { ...kept, ...(sky.bodies || {}) };
            this.h.onBodies?.(this.bodies);
            this.h.onLoading?.(false);

            const tasks = [
                this.loadSmallBodies(signal, API_ENDPOINTS.BRIGHT_ASTEROIDS, 'bright_asteroid_', 'asteroids', location, timeISO),
                this.loadSmallBodies(signal, API_ENDPOINTS.COMETS, 'comet_', 'comets', location, timeISO),
            ];
            if (constellations) tasks.push(this.loadConstellations(signal, location, timeISO));
            if (messier) tasks.push(this.loadMessier(signal, location, timeISO));
            const results = await Promise.allSettled(tasks);
            for (const r of results) {
                if (r.status === 'rejected' && r.reason?.name !== 'AbortError') failed = r.reason;
            }
        } catch (error) {
            if (error?.name === 'AbortError') return;
            failed = error;
        } finally {
            if (this._controller === controller) {
                this._controller = null;
                this.h.onLoading?.(false);
            }
        }
        if (signal.aborted) return;
        if (failed) console.error('Sky update failed:', failed);
        this.h.onError?.(failed);
    }

    async loadSmallBodies(signal, endpoint, keyPrefix, label, location, timeISO) {
        const data = await getJson(`${endpoint}?${query(location, timeISO)}`, signal);
        if (signal.aborted) return;
        const rest = Object.fromEntries(Object.entries(this.bodies).filter(([key]) => !key.startsWith(keyPrefix)));
        this.bodies = { ...rest, ...(data.bodies || {}) };
        this.h.onBodies?.(this.bodies);
    }

    async loadConstellations(signal, location, timeISO) {
        const data = await getJson(`${API_ENDPOINTS.ZODIAC}?${query(location, timeISO)}`, signal);
        if (signal.aborted) return;
        this.constellations = data.constellations || [];
        this.h.onConstellations?.(this.constellations);
    }

    async loadMessier(signal, location, timeISO) {
        const data = await getJson(`${API_ENDPOINTS.MESSIER}?${query(location, timeISO)}`, signal);
        if (signal.aborted) return;
        this.messier = data.objects || [];
        this.h.onMessier?.(this.messier);
    }

    /** Details (rise, set, transit) of one Messier object; a small bounded cache (O20). */
    async messierDetails(id, location, timeISO) {
        const key = [id, location.latitude, location.longitude, timeISO || ''].join('|');
        if (this._messierDetails.has(key)) return this._messierDetails.get(key);
        const data = await getJson(`${API_ENDPOINTS.MESSIER}?${query(location, timeISO, { object_id: id, details: '1' })}`);
        const detail = Array.isArray(data.objects) ? data.objects[0] || null : null;
        if (detail) {
            this._messierDetails.set(key, detail);
            if (this._messierDetails.size > MESSIER_DETAIL_CACHE_MAX) {
                this._messierDetails.delete(this._messierDetails.keys().next().value);
            }
        }
        return detail;
    }

    /** Forget everything of the previous place. */
    reset() {
        this._controller?.abort();
        this.bodies = {};
        this.constellations = null;
        this.messier = null;
        this._messierDetails.clear();
    }
}
