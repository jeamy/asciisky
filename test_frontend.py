"""Checks of the static frontend (no browser).

The grid and i18n checks run the ES modules in Node; they are skipped when
``node`` is not installed.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
JS = ROOT / "static" / "js"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

# Stubs for the browser globals constants.js reads at import time.
NODE_PRELUDE = "globalThis.window={location:{search:''}};globalThis.localStorage={getItem:()=>null};"


def run_node(script: str) -> str:
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", NODE_PRELUDE + script],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@needs_node
@pytest.mark.parametrize("view", ["horizon", "planisphere"])
def test_sky_grid_matches_previous_renderer(view):
    """At 360° the new grid draws exactly what the old renderer drew."""
    fixture = ROOT / "test_fixtures" / "sky_grid_reference.json"
    out = run_node(f"""
        import fs from 'node:fs';
        const {{ SkyGeometry, buildSkyGrid }} = await import('{(JS / "skyGrid.js").as_uri()}');
        const ref = JSON.parse(fs.readFileSync({json.dumps(str(fixture))}, 'utf8'));
        const geo = new SkyGeometry(ref['{view}'].geometry);
        const {{ lines }} = buildSkyGrid(geo, Object.values(ref.bodies),
            {{ labels: {{ north: 'N', east: 'O', south: 'S', west: 'W' }} }});
        console.log(JSON.stringify(lines));
    """)
    lines = json.loads(out)
    reference = json.loads(fixture.read_text(encoding="utf-8"))[view]["rows"]
    expected = {row: text for row, text in reference}
    for row, line in enumerate(lines):
        assert line.rstrip() == expected.get(row, "").rstrip(), f"row {row}"


@needs_node
def test_sky_grid_labels_do_not_block_bodies():
    """L4: the English 'E' is a direction label, not an occupied cell."""
    out = run_node(f"""
        const {{ SkyGeometry, buildSkyGrid }} = await import('{(JS / "skyGrid.js").as_uri()}');
        const geo = new SkyGeometry({{ mode: 'horizon', cols: 80, rows: 40, fovDeg: 360, centerAz: 180 }});
        const {{ lines }} = buildSkyGrid(geo, [{{ name: 'mars', altitude: 0, azimuth: 90 }}],
            {{ labels: {{ north: 'N', east: 'E', south: 'S', west: 'W' }} }});
        console.log(JSON.stringify(lines[geo.horizonRow]));
    """)
    horizon = json.loads(out)
    assert "♂" in horizon and "E" not in horizon


@needs_node
def test_sky_grid_window_hides_bodies_outside_the_field_of_view():
    out = run_node(f"""
        const {{ SkyGeometry, buildSkyGrid }} = await import('{(JS / "skyGrid.js").as_uri()}');
        const geo = new SkyGeometry({{ mode: 'horizon', cols: 50, rows: 30, fovDeg: 120, centerAz: 180 }});
        const {{ lines }} = buildSkyGrid(geo, [
            {{ name: 'saturn', altitude: 30, azimuth: 200 }},
            {{ name: 'jupiter', altitude: 30, azimuth: 20 }},
        ]);
        console.log(JSON.stringify(lines.join('')));
    """)
    text = json.loads(out)
    assert "♄" in text and "♃" not in text


@needs_node
def test_zoomed_horizon_zooms_altitude_too():
    """Below 360° a degree is as many px high as wide, and the rows show a band of altitude."""
    out = run_node(f"""
        const {{ SkyGeometry, buildSkyGrid }} = await import('{(JS / "skyGrid.js").as_uri()}');
        const wide = new SkyGeometry({{ mode: 'horizon', cols: 80, rows: 40, fovDeg: 360, centerAz: 180, aspect: 2 }});
        const geo = new SkyGeometry({{ mode: 'horizon', cols: 62, rows: 40, fovDeg: 60, centerAz: 180, aspect: 2 }});
        const span = (alt) => geo.projectExact(alt, 180).row;
        const bodies = [
            {{ name: 'saturn', altitude: 5, azimuth: 185 }},
            {{ name: 'jupiter', altitude: 70, azimuth: 185 }},
        ];
        const low = buildSkyGrid(geo, bodies).lines.join('');
        const up = new SkyGeometry({{ mode: 'horizon', cols: 62, rows: 40, fovDeg: 60, centerAz: 180, aspect: 2, centerAlt: 70 }});
        const high = buildSkyGrid(up, bodies, {{ labels: {{ north: 'N', east: 'E', south: 'S', west: 'W' }} }}).lines;
        console.log(JSON.stringify({{
            rowsPer10: span(0) - span(10),
            wideRowsPer10: wide.projectExact(0, 180).row - wide.projectExact(10, 180).row,
            colsPer10: geo.projectExact(0, 190).col - geo.projectExact(0, 180).col,
            horizonRow: geo.horizonRow,
            low, high: high.join(''), lastRow: high[high.length - 1], upHorizon: up.horizonRow,
            maxAlt: Math.max(...up.altLines()),
        }}));
    """)
    d = json.loads(out)
    # 10° = 10 columns; a cell is twice as tall as wide, so 5 rows (at 360°: about 2).
    assert abs(d["colsPer10"] - 10) < 1e-9
    assert abs(d["rowsPer10"] - 5) < 1e-9
    assert d["wideRowsPer10"] < 2.5
    # Default: the horizon near the bottom, not in the middle.
    assert 30 <= d["horizonRow"] < 40
    assert "♄" in d["low"] and "♃" not in d["low"]
    # Looking up: Jupiter shows, Saturn left the view, the direction stays on the bottom edge.
    assert "♃" in d["high"] and "♄" not in d["high"]
    assert d["upHorizon"] >= 40 and "S" in d["lastRow"]
    assert d["maxAlt"] <= 90


@needs_node
def test_frontend_i18n_tables_are_symmetric():
    out = run_node(f"""
        const {{ i18n, t, setLanguage }} = await import('{(JS / "i18n.js").as_uri()}');
        const de = Object.keys(i18n.de), en = Object.keys(i18n.en);
        setLanguage('en');
        console.log(JSON.stringify({{
            onlyDe: de.filter(k => !(k in i18n.en)),
            onlyEn: en.filter(k => !(k in i18n.de)),
            emptyEnglishSuffix: t('clock_suffix'),
        }}));
    """)
    data = json.loads(out)
    assert data["onlyDe"] == [] and data["onlyEn"] == []
    assert data["emptyEnglishSuffix"] == ""  # L27: an empty text is not a missing key


@needs_node
def test_frontend_uses_only_known_i18n_keys():
    sources = [p for p in JS.rglob("*.js") if p.name not in {"adminUsers.js", "i18n.js"}]
    used = set()
    for path in sources:
        used.update(re.findall(r"\bt\('([a-zA-Z_]+)'\)", path.read_text(encoding="utf-8")))
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    used.update(re.findall(r'data-i18n(?:-title|-aria)?="([a-z_]+)"', html))
    out = run_node(f"""
        const {{ i18n }} = await import('{(JS / "i18n.js").as_uri()}');
        console.log(JSON.stringify(Object.keys(i18n.de)));
    """)
    missing = sorted(used - set(json.loads(out)))
    assert missing == []


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_frontend_theme_contrast():
    css = (ROOT / "static" / "css" / "tokens.css").read_text(encoding="utf-8")
    themes = {}
    for name, body in re.findall(r':root\[data-theme="(\w+)"\][^{]*\{([^}]*)\}', css):
        themes[name] = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", body))
    assert set(themes) == {"green", "red", "blue", "amber"}
    for name, tokens in themes.items():
        for fg in ("fg", "fg-dim", "fg-muted", "accent"):
            for bg in ("bg", "surface", "surface-2"):
                assert _contrast(tokens[fg], tokens[bg]) >= 4.5, (name, fg, bg)
        assert _contrast(tokens["fg"], tokens["ui-bg-active"]) >= 4.5, name
        assert _contrast(tokens["on-accent"], tokens["accent"]) >= 4.5, name


def test_small_body_frontend_loaders_share_url_builder():
    source = (JS / "skyData.js").read_text(encoding="utf-8")
    assert "async loadSmallBodies(signal, endpoint, keyPrefix, label, location, timeISO)" in source
    assert "this.loadSmallBodies(signal, API_ENDPOINTS.BRIGHT_ASTEROIDS" in source
    assert "this.loadSmallBodies(signal, API_ENDPOINTS.COMETS" in source
    assert "nocache" not in source


def test_frontend_has_no_html_injection_sinks():
    """Texts from the API, Nominatim and users go in as text nodes (S2, S3, L17)."""
    for path in JS.rglob("*.js"):
        source = path.read_text(encoding="utf-8")
        assert ".innerHTML" not in source, path.name
        assert "insertAdjacentHTML" not in source, path.name
        assert "window.prompt(" not in source, path.name


def test_pages_allow_zoom_and_set_theme_colour():
    for page in ("index.html", "admin.html"):
        html = (ROOT / "templates" / page).read_text(encoding="utf-8")
        assert "user-scalable=no" not in html and "maximum-scale" not in html
    assert 'name="theme-color"' in (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def test_debug_logging_is_off_by_default():
    source = (JS / "constants.js").read_text(encoding="utf-8")
    assert "return false;\n})();" in source
