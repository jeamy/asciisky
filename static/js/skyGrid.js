// Pure sky grid: projection of altitude/azimuth onto the ASCII grid and the
// grid's text.  No DOM access, so it can be checked against a reference.
import { ASCII_ART, GRID_SYMBOLS, MOON_PHASE_SYMBOLS } from './constants.js';

const wrap360 = (deg) => ((deg % 360) + 360) % 360;
const PLANET_GLYPHS = new Set(['☿', '♀', '♂', '♃', '♄', '♅', '♆']);

/**
 * Grid geometry and projection for one render.
 *
 * Horizon view at 360 degrees, the classic mapping: column 1 is azimuth
 * ``centerAz - 180``, the full altitude range -90..+90 fills the rows with the
 * horizon in the middle.  Below 360 degrees (zoomed), ``fovDeg`` degrees of
 * azimuth centred on ``centerAz`` fill the columns and the altitude is zoomed
 * alike: one degree is as many px high as wide (``aspect``), so shapes stay
 * true.  The rows then show a band of altitude around ``centerAlt``; without
 * one the horizon sits near the bottom.
 *
 * Planisphere: zenith in the centre, the horizon circle at ``radius`` columns
 * (default: ``scale`` of the half size, as the old square grid had it);
 * ``aspect`` is cell height over cell width so the circle stays round on
 * screen.  Below the horizon the radius grows on to twice the horizon's.
 */
export class SkyGeometry {
    constructor({ mode = 'horizon', cols = 80, rows = 40, fovDeg = 360, centerAz = 180,
        rotation = 0, staticRotation = 180, aspect = 1.5, scale = 0.7, centerAlt = null, radius = null } = {}) {
        this.mode = mode;
        this.cols = cols;
        this.rows = rows;
        this.fovDeg = fovDeg;
        this.centerAz = wrap360(centerAz);
        this.rotation = rotation;
        this.staticRotation = staticRotation;
        this.aspect = aspect > 0 ? aspect : 1.5;
        this.scale = scale;
        this.horizonRow = Math.floor(rows / 2);
        if (mode === 'planisphere') {
            const maxRadius = Math.max(1, Math.min(Math.floor(rows / 2), Math.floor(cols / 2)) - 2);
            // The fitted radius (view) keeps everything below the horizon in the
            // grid only as far as it fits: what falls outside is not drawn.
            this.fitted = Number.isFinite(radius) && radius > 0;
            this.horizonRadius = this.fitted ? radius : maxRadius * scale;
            this.labelRadius = this.fitted ? radius + 1 : maxRadius + 1;
        }
        this.zoomed = mode === 'horizon' && fovDeg < 360;
        if (this.zoomed) {
            this.degPerCol = fovDeg / Math.max(1, cols - 2);
            this.degPerRow = Math.min(this.degPerCol * this.aspect, 180 / Math.max(1, rows - 1));
            this.halfSpan = (this.degPerRow * (rows - 1)) / 2;
            // Default: the horizon a little above the bottom edge.
            const fallback = 0.7 * this.halfSpan;
            this.centerAlt = this.clampAlt(Number.isFinite(centerAlt) ? centerAlt : fallback);
            this.altTop = this.centerAlt + this.halfSpan;
            // May lie outside the grid when the view looks up or down.
            this.horizonRow = Math.round(this.altTop / this.degPerRow);
        }
    }

    /** A centre altitude that keeps the zoomed view within -90..+90. */
    clampAlt(alt) {
        return Math.max(-90 + this.halfSpan, Math.min(90 - this.halfSpan, alt));
    }

    /** Altitudes of the grid lines (and, zoomed, of the altitude labels); 0 is the horizon. */
    altLines() {
        if (!this.zoomed) return [-75, -60, -45, -30, -15, 15, 30, 45, 60, 75];
        const span = this.degPerRow * (this.rows - 1);
        const step = span > 120 ? 30 : span > 60 ? 15 : span > 25 ? 10 : 5;
        const lines = [];
        for (let alt = -90; alt <= 90; alt += step) {
            if (alt !== 0 && alt <= this.altTop && alt >= this.altTop - span) lines.push(alt);
        }
        return lines;
    }

    get startAz() {
        return wrap360(this.centerAz - this.fovDeg / 2);
    }

    /** Fractional grid position (unclamped) and whether it lies in the view. */
    projectExact(altitude, azimuth) {
        return this.mode === 'planisphere'
            ? this._planisphere(altitude, azimuth)
            : this._horizon(altitude, azimuth);
    }

    /** Integer cell, clamped into the grid, as the text grid uses it. */
    project(altitude, azimuth) {
        const p = this.projectExact(altitude, azimuth);
        return {
            row: Math.max(0, Math.min(this.rows - 1, Math.round(p.row))),
            col: Math.max(0, Math.min(this.cols - 1, Math.round(p.col))),
            inside: p.inside,
        };
    }

    _horizon(altitude, azimuth) {
        const h = this.horizonRow;
        const alt = Number.isFinite(altitude) ? Math.max(-90, Math.min(90, altitude)) : 0;
        if (this.zoomed) return this._horizonZoomed(alt, azimuth);
        const row = alt >= 0
            ? h - (alt / 90) * h
            : h + (-alt / 90) * (this.rows - h - 1);
        const inner = this.cols - 2;
        const col = (wrap360(azimuth - this.startAz) / 360) * inner + 1;
        return { row, col, inside: true };
    }

    _horizonZoomed(alt, azimuth) {
        // Signed offsets from the view centre, so overlays can draw lines that
        // leave the window instead of jumping across it.
        const rel = wrap360(azimuth - this.centerAz + 180) - 180;
        const col = (rel / this.fovDeg + 0.5) * (this.cols - 2) + 1;
        const row = (this.altTop - alt) / this.degPerRow;
        const inside = Math.abs(rel) <= this.fovDeg / 2 && row > -0.5 && row < this.rows - 0.5;
        return { row, col, inside };
    }

    _planisphere(altitude, azimuth) {
        const centerRow = Math.floor(this.rows / 2);
        const centerCol = Math.floor(this.cols / 2);
        const baseRadius = this.horizonRadius;
        const alt = Number.isFinite(altitude) ? Math.max(-90, Math.min(90, altitude)) : 0;
        const r = alt >= 0
            ? ((90 - alt) / 90) * baseRadius
            : baseRadius + (-alt / 90) * baseRadius;
        const az = wrap360((Number.isFinite(azimuth) ? azimuth : 0) + this.staticRotation + this.rotation);
        const theta = az * Math.PI / 180;
        const col = centerCol + r * Math.sin(theta);
        const row = centerRow - (r * Math.cos(theta)) / this.aspect;
        const inside = !this.fitted || (col > -0.5 && col < this.cols - 0.5 && row > -0.5 && row < this.rows - 0.5);
        return { col, row, inside };
    }

    /** Distance from a cell to a body's cell, in cells; horizontal wrap at 360 degrees. */
    cellDistance(a, b) {
        let dc = Math.abs(a.col - b.col);
        if (this.mode === 'horizon' && this.fovDeg >= 360) dc = Math.min(dc, this.cols - 2 - dc);
        return Math.hypot(a.row - b.row, dc);
    }
}

/** Single-cell grid glyph of a body (never a double-width emoji). */
export function gridSymbol(body) {
    const name = String(body?.name || '').toLowerCase();
    if (GRID_SYMBOLS[name]) return GRID_SYMBOLS[name];
    const type = String(body?.type || '').toLowerCase();
    if (GRID_SYMBOLS[type]) return GRID_SYMBOLS[type];
    return '*';
}

/** Glyph for lists and the detail panel: emojis allowed (moon phase, sun). */
export function listSymbol(body) {
    const name = String(body?.name || '').toLowerCase();
    if (name === 'moon' && body.phase_name && MOON_PHASE_SYMBOLS[body.phase_name]) {
        return MOON_PHASE_SYMBOLS[body.phase_name];
    }
    return body?.symbol || gridSymbol(body);
}

const BODY_PRIORITY = (sym) => (sym === ASCII_ART.SELECTED_OBJECT ? 3 : PLANET_GLYPHS.has(sym) || sym === GRID_SYMBOLS.moon || sym === GRID_SYMBOLS.sun ? 2 : 1);

/**
 * Build the text grid.
 *
 * @param {SkyGeometry} geo
 * @param {object[]} bodies  bodies with altitude/azimuth/name/type
 * @param {object} opts  { selectedName, labels: {north,east,south,west}, displayName(name) }
 * @returns {{lines: string[], grid: string[][], cells: Map<string, object[]>, positions: Map<object, {row, col}>}}
 *   ``grid`` holds one string per cell (a glyph may be two code units, e.g. the comet).
 */
export function buildSkyGrid(geo, bodies, opts = {}) {
    const { cols, rows } = geo;
    const sky = Array.from({ length: rows }, () => Array(cols).fill(' '));
    const labels = opts.labels || { north: 'N', east: 'E', south: 'S', west: 'W' };
    const reserved = new Set(Object.values(labels));

    if (geo.mode === 'planisphere') drawPlanisphereFrame(sky, geo, labels);
    else drawHorizonFrame(sky, geo, labels);

    const positions = new Map();
    const cells = new Map();
    const selected = opts.selectedName ? String(opts.selectedName) : null;

    for (const body of bodies) {
        if (!body || !Number.isFinite(body.altitude) || !Number.isFinite(body.azimuth)) continue;
        const pos = geo.project(body.altitude, body.azimuth);
        if (!pos.inside) continue;
        positions.set(body, pos);
        const key = `${pos.row},${pos.col}`;
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(body);

        const isSelected = selected !== null && body.name === selected;
        const existing = sky[pos.row][pos.col];
        const free = existing === ' ' || existing === ASCII_ART.HORIZON || reserved.has(existing);
        let symbol = isSelected ? ASCII_ART.SELECTED_OBJECT : gridSymbol(body);
        if (!free && !isSelected) {
            // The first planet, Sun or Moon in a cell stays; a planet replaces a
            // minor body; two different minor bodies show '*'.
            if (BODY_PRIORITY(existing) >= 2) continue;
            if (BODY_PRIORITY(symbol) === 1 && existing !== symbol) symbol = '*';
        }
        sky[pos.row][pos.col] = symbol;
    }

    // The selected body's label goes below it, after all symbols are placed.
    if (selected !== null) {
        for (const [body, pos] of positions) {
            if (body.name !== selected) continue;
            const name = opts.displayName ? opts.displayName(body.name) : body.name;
            const label = `${name} (${body.altitude.toFixed(1)}°)`;
            const labelRow = Math.min(pos.row + 1, rows - 1);
            const start = Math.max(0, Math.min(cols - label.length, pos.col - Math.floor(label.length / 2)));
            for (let i = 0; i < label.length && start + i < cols; i++) sky[labelRow][start + i] = label[i];
            break;
        }
    }

    return { lines: sky.map((r) => r.join('')), grid: sky, cells, positions };
}

function drawHorizonFrame(sky, geo, labels) {
    const { cols, rows, horizonRow } = geo;
    const horizonShown = horizonRow >= 0 && horizonRow < rows;
    if (horizonShown) {
        for (let c = 1; c < cols - 1; c++) sky[horizonRow][c] = ASCII_ART.HORIZON;
        sky[horizonRow][0] = ASCII_ART.HORIZON_START;
        sky[horizonRow][cols - 1] = ASCII_ART.HORIZON_END;
    }
    // Looking up (or down), the directions stay on the edge nearest the horizon.
    const dirRow = horizonShown ? horizonRow : (horizonRow < 0 ? 0 : rows - 1);

    const dirs = [
        { label: labels.north, az: 0 }, { label: labels.east, az: 90 },
        { label: labels.south, az: 180 }, { label: labels.west, az: 270 },
    ];
    if (geo.fovDeg >= 360) {
        // At 360 degrees the direction at the seam would sit on both edges: hide it.
        const seam = dirs
            .map((d) => ({ ...d, eff: wrap360(d.az - geo.startAz) }))
            .sort((a, b) => Math.min(a.eff, 360 - a.eff) - Math.min(b.eff, 360 - b.eff))[0];
        for (const d of dirs) {
            if (d === dirs.find((x) => x.az === seam.az)) continue;
            const col = Math.round((wrap360(d.az - geo.startAz) / 360) * (cols - 2)) + 1;
            if (col >= 0 && col < cols) sky[horizonRow][col] = d.label;
        }
    } else {
        for (const d of dirs) {
            const rel = wrap360(d.az - geo.centerAz + 180) - 180;
            const col = Math.round((rel / geo.fovDeg + 0.5) * (cols - 2) + 1);
            if (Math.abs(rel) <= geo.fovDeg / 2 && col > 0 && col < cols - 1) sky[dirRow][col] = d.label;
        }
    }

    const altLabels = geo.zoomed ? geo.altLines() : [90, 60, 30, -30, -60, -90];
    for (const alt of altLabels) {
        const row = Math.round(geo.projectExact(alt, geo.centerAz).row);
        if (row < 0 || row >= rows || row === horizonRow) continue;
        const text = `${alt > 0 ? '+' : '-'}${Math.abs(alt)}`;
        for (let i = 0; i < text.length && i < cols; i++) sky[row][i] = text[i];
    }
}

function drawPlanisphereFrame(sky, geo, labels) {
    const { cols, rows } = geo;
    const centerRow = Math.floor(rows / 2);
    const centerCol = Math.floor(cols / 2);
    const outer = geo.labelRadius;
    const dirs = [
        { label: labels.north, az: 0 }, { label: labels.east, az: 90 },
        { label: labels.south, az: 180 }, { label: labels.west, az: 270 },
    ];
    for (const d of dirs) {
        const p = geo.projectExact(0, d.az);
        const dx = p.col - centerCol;
        const dy = p.row - centerRow;
        // Fitted: ``outer`` columns out on screen (dy counts rows, each ``aspect`` columns tall).
        // The reference grid keeps the old placement, ``outer`` cells out.
        const k = outer / ((geo.fitted ? Math.hypot(dx, dy * geo.aspect) : Math.hypot(dx, dy)) || 1);
        const row = Math.max(0, Math.min(rows - 1, Math.round(centerRow + dy * k)));
        const outCol = Math.round(centerCol + dx * k);
        const start = Math.max(0, Math.min(cols - d.label.length, outCol - Math.floor(d.label.length / 2)));
        for (let i = 0; i < d.label.length && start + i < cols; i++) sky[row][start + i] = d.label[i];
    }
}
