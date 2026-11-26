// Pure sky grid: projection of altitude/azimuth onto the ASCII grid and the
// grid's text.  No DOM access, so it can be checked against a reference.
import { ASCII_ART, GRID_SYMBOLS, MOON_PHASE_SYMBOLS } from './constants.js';

const wrap360 = (deg) => ((deg % 360) + 360) % 360;
const PLANET_GLYPHS = new Set(['☿', '♀', '♂', '♃', '♄', '♅', '♆']);

/**
 * Grid geometry and projection for one render.
 *
 * Horizon view: ``fovDeg`` degrees of azimuth centred on ``centerAz`` fill the
 * columns between the two horizon corners; the full altitude range -90..+90
 * fills the rows with the horizon in the middle.  At 360 degrees the mapping is
 * the classic one: column 1 is azimuth ``centerAz - 180``.
 *
 * Planisphere: a square grid of ``size`` cells, zenith in the centre, the
 * horizon circle at ``scale`` of the half size; ``aspect`` is cell height over
 * cell width so the circle stays round on screen.
 */
export class SkyGeometry {
    constructor({ mode = 'horizon', cols = 80, rows = 40, fovDeg = 360, centerAz = 180,
        rotation = 0, staticRotation = 180, aspect = 1.5, scale = 0.7 } = {}) {
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
        const row = alt >= 0
            ? h - (alt / 90) * h
            : h + (-alt / 90) * (this.rows - h - 1);
        const inner = this.cols - 2;
        let col;
        let inside = true;
        if (this.fovDeg >= 360) {
            col = (wrap360(azimuth - this.startAz) / 360) * inner + 1;
        } else {
            // Signed offset from the view centre, so overlays can draw lines
            // that leave the window instead of jumping across it.
            const rel = wrap360(azimuth - this.centerAz + 180) - 180;
            col = (rel / this.fovDeg + 0.5) * inner + 1;
            inside = Math.abs(rel) <= this.fovDeg / 2;
        }
        return { row, col, inside };
    }

    _planisphere(altitude, azimuth) {
        const centerRow = Math.floor(this.rows / 2);
        const centerCol = Math.floor(this.cols / 2);
        const maxRadius = Math.max(1, Math.min(centerRow, centerCol) - 2);
        const baseRadius = maxRadius * this.scale;
        const alt = Number.isFinite(altitude) ? Math.max(-90, Math.min(90, altitude)) : 0;
        const r = alt >= 0
            ? ((90 - alt) / 90) * baseRadius
            : baseRadius + (-alt / 90) * baseRadius;
        const az = wrap360((Number.isFinite(azimuth) ? azimuth : 0) + this.staticRotation + this.rotation);
        const theta = az * Math.PI / 180;
        return {
            col: centerCol + r * Math.sin(theta),
            row: centerRow - (r * Math.cos(theta)) / this.aspect,
            inside: true,
        };
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
    for (let c = 1; c < cols - 1; c++) sky[horizonRow][c] = ASCII_ART.HORIZON;
    sky[horizonRow][0] = ASCII_ART.HORIZON_START;
    sky[horizonRow][cols - 1] = ASCII_ART.HORIZON_END;

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
            const p = geo.project(0, d.az);
            if (p.inside && p.col > 0 && p.col < cols - 1) sky[horizonRow][p.col] = d.label;
        }
    }

    for (const alt of [90, 60, 30, -30, -60, -90]) {
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
    const maxRadius = Math.max(1, Math.min(centerRow, centerCol) - 2);
    const dirs = [
        { label: labels.north, az: 0 }, { label: labels.east, az: 90 },
        { label: labels.south, az: 180 }, { label: labels.west, az: 270 },
    ];
    for (const d of dirs) {
        const p = geo.projectExact(0, d.az);
        const dx = p.col - centerCol;
        const dy = p.row - centerRow;
        const len = Math.hypot(dx, dy) || 1;
        const row = Math.max(0, Math.min(rows - 1, Math.round(centerRow + (dy / len) * (maxRadius + 1))));
        const outCol = Math.round(centerCol + (dx / len) * (maxRadius + 1));
        const start = Math.max(0, Math.min(cols - d.label.length, outCol - Math.floor(d.label.length / 2)));
        for (let i = 0; i < d.label.length && start + i < cols; i++) sky[row][start + i] = d.label[i];
    }
}
