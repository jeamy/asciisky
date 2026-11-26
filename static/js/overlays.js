// SVG overlays on the sky grid.  Every function draws into an <svg> whose
// viewBox is the stage in px; positions come from the same SkyGeometry as the
// text, so lines and dots sit on the glyph cells.
import { svgEl } from './ui/dom.js';
import { CONFIG } from './constants.js';
import { t, hasKey, getCurrentLanguage } from './i18n.js';

const constellationName = (con) => (hasKey(con.name) ? t(con.name)
    : (getCurrentLanguage() === 'de' && con.name_de) || con.name);

const cellX = (col, m) => (col + 0.5) * m.cw;
const cellY = (row, m) => (row + 0.5) * m.ch;

function sizeSvg(svg, m) {
    svg.setAttribute('viewBox', `0 0 ${m.width} ${m.height}`);
    svg.setAttribute('width', m.width);
    svg.setAttribute('height', m.height);
}

/** Altitude lines (horizon view) or horizon circle and grid (planisphere). */
export function drawGrid(svg, geo, m, { showGrid = true } = {}) {
    sizeSvg(svg, m);
    const parts = [];
    if (geo.mode === 'planisphere') {
        const c = geo.projectExact(90, 0);
        const cx = cellX(c.col, m);
        const cy = cellY(c.row, m);
        // The horizon circle stays: it is the boundary of the visible sky.
        // In cells the circle is an ellipse; in px it is round.
        const ring = (alt, cls) => {
            const p = geo.projectExact(alt, 0);
            const r = Math.hypot(cellX(p.col, m) - cx, cellY(p.row, m) - cy);
            parts.push(svgEl('circle', { cx, cy, r, class: cls }));
        };
        if (showGrid) {
            for (let alt = 15; alt < 90; alt += 15) ring(alt, 'grid-line');
            for (let az = 0; az < 360; az += 15) {
                const p = geo.projectExact(0, az);
                parts.push(svgEl('line', { x1: cx, y1: cy, x2: cellX(p.col, m), y2: cellY(p.row, m), class: 'grid-line' }));
            }
        }
        ring(0, 'horizon-ring');
    } else if (showGrid) {
        for (const alt of geo.altLines()) { // the ASCII horizon is the line at 0
            const y = cellY(geo.projectExact(alt, geo.centerAz).row, m);
            parts.push(svgEl('line', { x1: 0, y1: y, x2: m.width, y2: y, class: 'grid-line' }));
        }
    }
    svg.replaceChildren(...parts);
}

/** Segments of a line between two projected points, split at the 360° seam. */
function segments(geo, m, a, b) {
    const x1 = cellX(a.col, m), y1 = cellY(a.row, m);
    let x2 = cellX(b.col, m);
    const y2 = cellY(b.row, m);
    if (geo.mode !== 'horizon') return [[x1, y1, x2, y2]];
    if (geo.fovDeg < 360) {
        // Columns are signed offsets from the view centre: no seam.
        return a.inside || b.inside ? [[x1, y1, x2, y2]] : [];
    }
    const span = (geo.cols - 2) * m.cw;
    const dx = x2 - x1;
    if (Math.abs(dx) <= span / 2) return [[x1, y1, x2, y2]];
    // Wrapped: draw the line once leaving each edge (L31).
    x2 += dx > 0 ? -span : span;
    return [[x1, y1, x2, y2], [x1 + (dx > 0 ? span : -span), y1, x2 + (dx > 0 ? span : -span), y2]];
}

function starRadius(mag) {
    if (!Number.isFinite(mag)) return 1;
    if (mag < 1) return 3;
    if (mag < 2) return 2.5;
    if (mag < 3) return 2;
    if (mag < 4) return 1.5;
    return 1;
}

export function drawConstellations(svg, geo, m, constellations) {
    sizeSvg(svg, m);
    const groups = [];
    for (const con of constellations || []) {
        const stars = new Map();
        const nodes = [];
        for (const star of con.stars || []) {
            const p = geo.projectExact(star.altitude, star.azimuth);
            stars.set(star.hip_id, { ...p, altitude: star.altitude });
            if (!p.inside) continue;
            nodes.push(svgEl('circle', {
                cx: cellX(p.col, m), cy: cellY(p.row, m), r: starRadius(star.magnitude),
                class: star.altitude < 0 ? 'below' : null,
            }));
        }
        for (const [idA, idB] of con.lines || []) {
            const a = stars.get(idA);
            const b = stars.get(idB);
            if (!a || !b) continue;
            const below = a.altitude < 0 && b.altitude < 0 ? 'both-below' : (a.altitude < 0 || b.altitude < 0 ? 'below' : null);
            for (const [x1, y1, x2, y2] of segments(geo, m, a, b)) {
                nodes.unshift(svgEl('line', { x1, y1, x2, y2, class: below }));
            }
        }
        const shown = [...stars.values()].filter((s) => s.inside);
        if (shown.length) {
            let xs = shown.map((s) => cellX(s.col, m));
            const span = (geo.cols - 2) * m.cw;
            if (geo.mode === 'horizon' && geo.fovDeg >= 360 && Math.max(...xs) - Math.min(...xs) > span / 2) {
                xs = xs.map((x) => (x < m.width / 2 ? x + span : x));
            }
            let x = xs.reduce((s, v) => s + v, 0) / xs.length;
            if (x > m.width) x -= span;
            const y = shown.reduce((s, v) => s + cellY(v.row, m), 0) / shown.length;
            nodes.push(svgEl('text', { x, y: y - m.ch, class: 'con-label' }, constellationName(con)));
        }
        groups.push(svgEl('g', { class: 'constellation', 'data-name': con.name }, nodes));
    }
    svg.replaceChildren(...groups);
}

/** Messier dots; returns their positions for the hit test. */
export function drawMessier(svg, geo, m, objects) {
    sizeSvg(svg, m);
    const nodes = [];
    const placed = [];
    const threshold = CONFIG.LABELS.MESSIER_MAG_THRESHOLD;
    for (const obj of objects || []) {
        if (!Number.isFinite(obj.altitude) || !Number.isFinite(obj.azimuth)) continue;
        const p = geo.projectExact(obj.altitude, obj.azimuth);
        if (!p.inside) continue;
        placed.push({ obj, row: p.row, col: p.col });
        const x = cellX(p.col, m);
        const y = cellY(p.row, m);
        const g = svgEl('g', { class: `messier${obj.altitude < 0 ? ' below' : ''}` },
            svgEl('circle', { cx: x, cy: y, r: 3 }));
        if (obj.magnitude == null || obj.magnitude <= threshold) {
            g.append(svgEl('text', { x: x + 5, y: y - 4 }, obj.id || obj.name || 'M'));
        }
        nodes.push(g);
    }
    svg.replaceChildren(...nodes);
    return placed;
}
