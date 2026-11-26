// The sky stage: one persistent DOM (text grid, SVG layers, labels) that is
// re-filled on every render, never rebuilt.  Rendering is batched per frame;
// gestures use Pointer Events for mouse, pen and touch alike.
import { CONFIG, ASCII_ART } from './constants.js';
import { SkyGeometry, buildSkyGrid } from './skyGrid.js';
import { drawGrid, drawConstellations, drawMessier } from './overlays.js';
import { el, svgEl } from './ui/dom.js';

const FOVS = CONFIG.FOV_LEVELS;               // [360, 180, 120, 90]
const ZOOMS = CONFIG.PLANISPHERE_ZOOM_LEVELS; // [1, 1.5, 2, 3]
const HORIZON_ROWS = CONFIG.SKY_ROWS;
const HORIZON_COLS = CONFIG.SKY_COLS;
const TAP_SLOP_PX = 6;
const PINCH_STEP = 1.3;
// Glyphs drawn as fixed one-cell boxes, so a symbol from a fallback font can
// never shift the rest of its row.  Box drawing (U+2500..257F) stays text.
const SYMBOL_RE = /[←-⓿▀-⯿]/;

const wrap360 = (deg) => ((deg % 360) + 360) % 360;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export class SkyView {
    /**
     * @param {HTMLElement} host  the viewport element (its size decides the grid)
     * @param {object} opts  onSelect(hits, point), onViewChange(view), onViewCommit(view)
     */
    constructor(host, opts = {}) {
        this.host = host;
        this.opts = opts;
        this.view = {
            mode: 'horizon', centerAz: 180, fov: 360, rotation: 0, zoom: 1, panX: 0, panY: 0,
            centerAlt: null, // zoomed horizon: altitude of the view centre (null = horizon near the bottom)
        };
        this.layers = { constellations: false, messier: false, grid: true };
        this.bodies = [];
        this.constellations = [];
        this.messier = [];
        this.selectedName = null;
        this.labels = { north: 'N', east: 'E', south: 'S', west: 'W' };
        this.displayName = (n) => n;
        this._pending = false;
        this._pointers = new Map();
        this._ratio = null;
        this._mount();
    }

    // ----- public state -----

    setView(patch) {
        const v = this.view;
        if (patch.mode && patch.mode !== v.mode) {
            v.panX = 0;
            v.panY = 0;
        }
        Object.assign(v, patch);
        v.centerAz = wrap360(v.centerAz);
        v.rotation = wrap360(v.rotation);
        if (!FOVS.includes(v.fov)) v.fov = 360;
        if (!ZOOMS.includes(v.zoom)) v.zoom = 1;
        if (v.zoom === 1) { v.panX = 0; v.panY = 0; }
        this.scheduleRender();
    }

    setBodies(bodies) {
        this.bodies = Object.values(bodies || {});
        this.scheduleRender();
    }

    setConstellations(list) { this.constellations = list || []; this.scheduleRender(); }
    setMessier(list) { this.messier = list || []; this.scheduleRender(); }
    setLayers(patch) { Object.assign(this.layers, patch); this.scheduleRender(); }
    setSelected(name) { this.selectedName = name || null; this.scheduleRender(); }

    setLanguage(labels, displayName) {
        this.labels = labels;
        this.displayName = displayName;
        this._ratio = null; // glyph widths of the labels' font do not change, but re-measure anyway
        this.scheduleRender();
    }

    /** Step the field of view (horizon) or the zoom (planisphere); +1 = closer. */
    stepZoom(dir) {
        const v = this.view;
        if (v.mode === 'planisphere') {
            const i = clamp(ZOOMS.indexOf(v.zoom) + dir, 0, ZOOMS.length - 1);
            if (ZOOMS[i] === v.zoom) return;
            const f = ZOOMS[i] / v.zoom;
            this.setView({ zoom: ZOOMS[i], panX: v.panX * f, panY: v.panY * f });
        } else {
            const i = clamp(FOVS.indexOf(v.fov) + dir, 0, FOVS.length - 1);
            if (FOVS[i] === v.fov) return;
            // Back at 360 degrees the whole sky shows: forget the altitude.
            this.setView({ fov: FOVS[i], ...(FOVS[i] === 360 ? { centerAlt: null } : {}) });
        }
        this._commit();
    }

    /** Turn the view: azimuth (horizon) or rotation (planisphere) in degrees. */
    turn(deg) {
        if (this.view.mode === 'planisphere') this.setView({ rotation: this.view.rotation + deg });
        else this.setView({ centerAz: this.view.centerAz + deg });
        this._commit();
    }

    /** Look up (+) or down (-) by ``deg`` degrees; only a zoomed horizon view has room. */
    tilt(deg) {
        const geo = this._geo;
        if (this.view.mode !== 'horizon' || !geo?.zoomed) return;
        this.setView({ centerAlt: geo.clampAlt(geo.centerAlt + deg) });
    }

    scheduleRender() {
        if (this._pending) return;
        this._pending = true;
        requestAnimationFrame(() => {
            this._pending = false;
            this.render();
        });
    }

    // ----- DOM -----

    _mount() {
        this.pre = el('pre', { class: 'sky-text', 'aria-hidden': 'true' });
        this.gridSvg = svgEl('svg', { class: 'sky-layer sky-grid', 'aria-hidden': 'true' });
        this.conSvg = svgEl('svg', { class: 'sky-layer sky-constellations', 'aria-hidden': 'true' });
        this.mesSvg = svgEl('svg', { class: 'sky-layer sky-messier', 'aria-hidden': 'true' });
        this.labelLayer = el('div', { class: 'sky-labels', 'aria-hidden': 'true' });
        this.stage = el('div', { class: 'sky-stage' }, this.gridSvg, this.pre, this.conSvg, this.mesSvg, this.labelLayer);
        this.probe = el('span', { class: 'sky-probe', 'aria-hidden': 'true' });
        this.host.replaceChildren(this.stage, this.probe);

        new ResizeObserver(() => this.scheduleRender()).observe(this.host);
        document.fonts?.ready?.then(() => { this._ratio = null; this.scheduleRender(); });

        this.host.addEventListener('pointerdown', (e) => this._onDown(e));
        this.host.addEventListener('pointermove', (e) => this._onMove(e));
        this.host.addEventListener('pointerup', (e) => this._onUp(e));
        this.host.addEventListener('pointercancel', (e) => this._onUp(e, true));
        this.host.addEventListener('wheel', (e) => this._onWheel(e), { passive: false });
    }

    /** Glyph advance and line height per px of font size, measured once. */
    _glyphRatio() {
        if (this._ratio) return this._ratio;
        this.probe.style.fontSize = '100px';
        this.probe.textContent = '0'.repeat(50) + '\n' + '0'.repeat(50);
        const r = this.probe.getBoundingClientRect();
        this._ratio = { w: r.width / 50 / 100 || 0.6, h: r.height / 2 / 100 || 1.15 };
        this.probe.textContent = '';
        return this._ratio;
    }

    /** Font size and grid size for the host's size and the current view. */
    _layout() {
        const W = Math.max(1, this.host.clientWidth);
        const H = Math.max(1, this.host.clientHeight);
        const { w: rw, h: rh } = this._glyphRatio();
        const v = this.view;
        let font = Math.min(CONFIG.MAX_FONT_PX, W / (HORIZON_COLS * rw), H / (HORIZON_ROWS * rh));
        // A part of the horizon: readable glyphs, as many columns as fit.  The
        // planisphere always takes the horizon's font (for the same field of
        // view) and fills the whole area with it.
        if (v.fov < 360) font = Math.max(CONFIG.MIN_FONT_PX, font);
        if (v.mode === 'planisphere') {
            const cols = clamp(Math.floor(W / (font * rw)), 24, 240);
            const rows = clamp(Math.floor(H / (font * rh)), 12, 120);
            const aspect = rh / rw;
            // The horizon circle as large as fits, with room for N/E/S/W outside.
            const radius = Math.max(4, Math.min(Math.floor(cols / 2), Math.floor(rows / 2) * aspect) - 2.5);
            return { font, cols, rows, aspect, radius };
        }
        let cols = HORIZON_COLS;
        if (v.fov < 360) cols = clamp(Math.floor(W / (font * rw)), 24, 160);
        const rows = clamp(Math.floor(H / (font * rh)), 21, HORIZON_ROWS);
        return { font, cols, rows, aspect: rh / rw };
    }

    render() {
        const v = this.view;
        const lay = this._layout();
        this.pre.style.fontSize = `${lay.font}px`;
        this.probe.style.fontSize = `${lay.font}px`;
        const geo = new SkyGeometry({
            mode: v.mode,
            cols: lay.cols,
            rows: lay.rows,
            fovDeg: v.fov,
            centerAz: v.centerAz,
            rotation: v.rotation,
            staticRotation: CONFIG.PLANISPHERE_ROTATION,
            aspect: lay.aspect,
            centerAlt: v.centerAlt,
            radius: lay.radius,
        });
        const built = buildSkyGrid(geo, this.bodies, {
            selectedName: this.selectedName,
            labels: this.labels,
            displayName: this.displayName,
        });
        this._fillText(built.grid);

        const m = {
            cw: this.pre.offsetWidth / lay.cols || lay.font * this._ratio.w,
            ch: this.pre.offsetHeight / lay.rows || lay.font * this._ratio.h,
        };
        m.width = m.cw * lay.cols;
        m.height = m.ch * lay.rows;
        this.stage.style.width = `${m.width}px`;
        this.stage.style.height = `${m.height}px`;
        this.stage.style.transform = v.mode === 'planisphere' && v.zoom !== 1
            ? `translate(${v.panX}px, ${v.panY}px) scale(${v.zoom})` : '';
        this.host.dataset.mode = v.mode;

        drawGrid(this.gridSvg, geo, m, { showGrid: this.layers.grid });
        if (this.layers.constellations) drawConstellations(this.conSvg, geo, m, this.constellations);
        else this.conSvg.replaceChildren();
        this._messierPlaced = this.layers.messier ? drawMessier(this.mesSvg, geo, m, this.messier) : [];
        if (!this.layers.messier) this.mesSvg.replaceChildren();
        this._drawLabels(built.positions, m);

        this._geo = geo;
        this._metrics = m;
        this._positions = built.positions;
        this.opts.onViewChange?.({ ...v, cols: lay.cols, rows: lay.rows });
    }

    _fillText(grid) {
        const frag = document.createDocumentFragment();
        grid.forEach((row, r) => {
            let run = '';
            for (const cell of row) {
                if (SYMBOL_RE.test(cell)) {
                    if (run) { frag.append(run); run = ''; }
                    const cls = cell === ASCII_ART.SELECTED_OBJECT ? 'g g-selected' : 'g';
                    frag.append(el('span', { class: cls }, cell));
                } else {
                    run += cell;
                }
            }
            if (r < grid.length - 1) run += '\n';
            if (run) frag.append(run);
        });
        this.pre.replaceChildren(frag);
    }

    _drawLabels(positions, m) {
        const nodes = [];
        const { BRIGHT_MINOR_PLANET_MAG_THRESHOLD: aMax, BRIGHT_COMET_MAG_THRESHOLD: cMax } = CONFIG.LABELS;
        for (const [body, pos] of positions) {
            if (!Number.isFinite(body.magnitude) || body.name === this.selectedName) continue;
            const isAst = body.type === 'asteroid';
            const isCom = body.type === 'comet';
            if (!((isAst && body.magnitude < aMax) || (isCom && body.magnitude < cMax))) continue;
            const label = el('span', { class: 'sky-label' }, `${this.displayName(body.name)} ${body.magnitude.toFixed(1)}`);
            label.style.left = `${(pos.col + 0.5) * m.cw}px`;
            label.style.top = `${pos.row * m.ch}px`;
            nodes.push(label);
        }
        this.labelLayer.replaceChildren(...nodes);
    }

    // ----- hit test -----

    /** Bodies and Messier objects near a screen point, nearest first. */
    hitTest(clientX, clientY, coarse = false) {
        if (!this._geo) return [];
        const rect = this.stage.getBoundingClientRect();
        const col = ((clientX - rect.left) / rect.width) * this._geo.cols - 0.5;
        const row = ((clientY - rect.top) / rect.height) * this._geo.rows - 0.5;
        const radius = coarse ? 2.5 : 1.5;
        const hits = [];
        for (const [body, pos] of this._positions || []) {
            const d = this._geo.cellDistance({ row, col }, pos);
            if (d <= radius) hits.push({ kind: 'body', obj: body, d });
        }
        for (const p of this._messierPlaced || []) {
            const d = this._geo.cellDistance({ row, col }, p);
            if (d <= radius) hits.push({ kind: 'messier', obj: p.obj, d });
        }
        hits.sort((a, b) => a.d - b.d);
        return hits;
    }

    // ----- gestures -----

    _onDown(e) {
        if (e.button !== undefined && e.button > 0) return;
        this.host.setPointerCapture?.(e.pointerId);
        this._stopInertia();
        this._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (this._pointers.size === 1) {
            this._gesture = {
                startX: e.clientX, startY: e.clientY, lastX: e.clientX, lastY: e.clientY,
                startTime: performance.now(), moved: false, samples: [],
                angle: this._angleAt(e.clientX, e.clientY),
            };
        } else if (this._pointers.size === 2) {
            this._gesture = { pinch: this._pinchDistance(), moved: true };
        }
    }

    _onMove(e) {
        if (!this._pointers.has(e.pointerId)) return;
        this._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        const g = this._gesture;
        if (!g) return;
        if (g.pinch) {
            const d = this._pinchDistance();
            if (d > g.pinch * PINCH_STEP) { this.stepZoom(1); g.pinch = d; }
            else if (d < g.pinch / PINCH_STEP) { this.stepZoom(-1); g.pinch = d; }
            return;
        }
        if (!g.moved && Math.hypot(e.clientX - g.startX, e.clientY - g.startY) < TAP_SLOP_PX) return;
        g.moved = true;
        const dx = e.clientX - g.lastX;
        const dy = e.clientY - g.lastY;
        g.lastX = e.clientX;
        g.lastY = e.clientY;
        const v = this.view;
        if (v.mode === 'planisphere' && v.zoom > 1) {
            this.setView(this._clampPan(v.panX + dx, v.panY + dy));
        } else if (v.mode === 'planisphere') {
            const a = this._angleAt(e.clientX, e.clientY);
            let delta = a - g.angle;
            if (delta > 180) delta -= 360;
            if (delta < -180) delta += 360;
            g.angle = a;
            this.setView({ rotation: v.rotation + delta });
            g.samples.push({ t: performance.now(), v: delta });
        } else {
            const deg = -dx * this._degPerPx();
            const patch = { centerAz: v.centerAz + deg };
            const geo = this._geo;
            if (geo?.zoomed && this._metrics) {
                // Grab the sky: dragging down brings higher altitudes into view.
                // Start from the clamped value, so a drag past the zenith does not stick.
                patch.centerAlt = geo.clampAlt(geo.centerAlt + (dy * geo.degPerRow) / this._metrics.ch);
                geo.centerAlt = patch.centerAlt;
            }
            this.setView(patch);
            g.samples.push({ t: performance.now(), v: deg });
        }
        if (g.samples.length > 6) g.samples.shift();
    }

    _onUp(e, cancelled = false) {
        if (!this._pointers.has(e.pointerId)) return;
        this._pointers.delete(e.pointerId);
        const g = this._gesture;
        if (this._pointers.size > 0) {
            // One finger of a pinch lifted: no tap, no drag until all are up.
            if (g) g.pinch = null;
            this._gesture = null;
            return;
        }
        this._gesture = null;
        if (!g || cancelled) return;
        if (!g.moved && !g.pinch) {
            if (performance.now() - g.startTime < 600) {
                const coarse = e.pointerType === 'touch' || matchMedia('(pointer: coarse)').matches;
                this.opts.onSelect?.(this.hitTest(e.clientX, e.clientY, coarse));
            }
            return;
        }
        this._startInertia(g.samples);
    }

    _onWheel(e) {
        e.preventDefault();
        const now = performance.now();
        if (this._lastWheel && now - this._lastWheel < 180) return;
        this._lastWheel = now;
        this.stepZoom(e.deltaY < 0 ? 1 : -1);
    }

    _degPerPx() {
        const m = this._metrics;
        const inner = (this._geo?.cols || HORIZON_COLS) - 2;
        return m ? this.view.fov / (inner * m.cw) : 0.5;
    }

    _angleAt(x, y) {
        const r = this.stage.getBoundingClientRect();
        return Math.atan2(y - (r.top + r.height / 2), x - (r.left + r.width / 2)) * 180 / Math.PI;
    }

    _pinchDistance() {
        const [a, b] = [...this._pointers.values()];
        return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 1;
    }

    _clampPan(x, y) {
        const m = this._metrics;
        const z = this.view.zoom;
        if (!m) return { panX: x, panY: y };
        const maxX = (m.width * (z - 1)) / 2;
        const maxY = (m.height * (z - 1)) / 2;
        return { panX: clamp(x, -maxX, maxX), panY: clamp(y, -maxY, maxY) };
    }

    _startInertia(samples) {
        const recent = samples.filter((s) => performance.now() - s.t < 100);
        if (recent.length < 2 || matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this._commit();
            return;
        }
        const span = Math.max(16, recent[recent.length - 1].t - recent[0].t);
        let velocity = (recent.reduce((s, x) => s + x.v, 0) / span) * 16; // degrees per frame
        const key = this.view.mode === 'planisphere' ? 'rotation' : 'centerAz';
        const step = () => {
            velocity *= 0.92;
            if (Math.abs(velocity) < 0.05) {
                this._inertia = null;
                this._commit();
                return;
            }
            this.setView({ [key]: this.view[key] + velocity });
            this._inertia = requestAnimationFrame(step);
        };
        this._inertia = requestAnimationFrame(step);
    }

    _stopInertia() {
        if (this._inertia) {
            cancelAnimationFrame(this._inertia);
            this._inertia = null;
            this._commit();
        }
    }

    _commit() {
        this.opts.onViewCommit?.({ ...this.view });
    }
}
