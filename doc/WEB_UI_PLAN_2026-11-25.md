# Plan: moderne Weboberfläche und Mobilansicht

**Stand:** 25. November 2026
**Bezug:** [CODE_ANALYSIS_REPORT_2026-11-25.md](CODE_ANALYSIS_REPORT_2026-11-25.md) (Befundnummern L…, O…, D…)

## Ziel

AsciiSky soll eine aufgeräumte, zeitgemäße Oberfläche bekommen, die auf dem Telefon genauso gut
funktioniert wie am Desktop. Dabei bleibt erhalten:

- **die ASCII-Darstellung des Himmels:** Monospace-Raster, Box-Drawing-Horizont, Symbole für
  Sterne und Objekte, die Overlays (Sternbilder, Messier, Labels, Raster, Sonnenbahn);
- **die Farbthemen:** Grün (Standard), Rot, Blau und Amber, jeweils als vollständiges Farbschema
  inklusive Dialogen.

## Rahmenbedingungen

- **Kein Build-Schritt, kein neues Framework, keine neuen Abhängigkeiten.** Es bleibt bei
  Vanilla-ES-Modulen, die FastAPI direkt aus `static/` ausliefert.
- `app.css` wird auch von `admin.html` und `worker_monitor.html` geladen. Tokens und Basisstile
  müssen dort weiter funktionieren, oder die Seiten bekommen eine eigene, kleine Basis.
- Alle neuen Texte laufen über `i18n.js` (DE/EN).
- Die Backend-API bleibt unverändert. Optionale Verbesserungen wie Cache-Header (O12) sind getrennt.

## Ist-Zustand: die Probleme der Oberfläche

1. **Mobil läuft das Raster über.** 80 Spalten bei festen `0.6rem` sind auf 360 px etwa 460 px
   breit. `--sky-font-size` wird nie gesetzt, und es gibt keine Reaktion auf Größenänderungen (O16).
2. **Die Bedienelemente sind über die ganze Seite verteilt:** Titelzeile, Objektknöpfe,
   Layer-Knöpfe, Zeitsteuerung als eigener Kasten, Panel links, Detaildialog rechts außen. Auf dem
   Telefon wird daraus ein langer Stapel, und der Himmel ist nur eines von vielen Elementen.
3. **Jeder Render baut das DOM neu auf** (O10). Das verursacht Flackern, Listener-Lecks (L3) und
   doppelte Anzeigen (L6).
4. **Getrennte Maus- und Touch-Pfade mit UA-Sniffing** (D8). Zoom und Pan sind am Telefon
   abgeschaltet.
5. **`user-scalable=no`** sperrt das Zoomen der Seite. Das ist eine Barriere für die Barrierefreiheit.
6. **Doppelt breite Emojis** verschieben das Raster (L5).

## Zielbild

### Desktop (≥ 1024 px)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ✦ ASCII Sky · Klagenfurt          « ‹  25.11. 23:04  › »  ⟳      📍  ◐  ⚙  ? │  App-Leiste
├────────────────┬─────────────────────────────────────────────┬───────────────┤
│ SICHTBAR       │ [Horizont|Planisphäre]   ✦ ✧ ☉ ⌗    1× 2× 4×│ ⚸ Ceres       │
│ ☉ Sonne   −12° │                                             │ Höhe   23.2°  │
│ ♃ Jupiter  41° │   +60      Perseus·                         │ Azimut 223.0° │
│ ♄ Saturn   18° │        ·─·      ♃         Andromeda         │ Entf.  2.27 AE│
│ ─ Asteroiden ─ │   +30     Orion     ⚸ Ceres 8.3             │ Auf    15:07  │
│ ⚸ Ceres    8.3 │ ◁ ╭────O──────────S──────────W──────╮ ▷     │ Transit 20:27 │
│ ─ Kometen ──── │   −30      ☄ 24P                            │ Unter  01:50  │
│ ☄ 24P     10.2 │                                             │ Mag    8.3    │
│        [⚙ Mag] │  Asteroiden ≤ 10.5: 3 · Kometen ≤ 12.5: 2   │          [×]  │
└────────────────┴─────────────────────────────────────────────┴───────────────┘
```

- **App-Leiste**, einzeilig und sticky: links Titel und Standort (klickbar, öffnet den
  Standortdialog), in der Mitte die Zeitsteuerung, rechts Standort, Theme-Menü, Einstellungen und
  Hilfe. Die heutigen Theme-Knöpfe R/G/B/A und DE/EN wandern in ein kompaktes Menü (◐ bzw. ⚙).
- **Drei Spalten:** die Objektliste links (einklappbar), der Himmel als Hauptfläche, Details rechts
  als festes Panel statt als frei schwebender Dialog. Ohne Auswahl wird die rechte Spalte schmal
  oder verschwindet.
- **Werkzeugleiste über dem Himmel:** Ansicht (Horizont/Planisphäre), Layer-Toggles (Sternbilder ✦,
  Messier ✧, Sonnenbahn ☉, Raster ⌗) und die Zoomstufen. Die heutigen Planeten-Knöpfe entfallen
  als eigene Zeile, weil ihre Funktion („alle Objekte dieses Typs markieren“) in der Objektliste
  aufgeht.
- Zwischen 768 und 1023 px: zwei Spalten, die Details erscheinen als Overlay-Panel über dem rechten
  Rand.

### Mobil (< 768 px, Hochformat)

```
┌──────────────────────────────┐
│ ✦ Klagenfurt      📍  ◐  ⚙  │  kompakte Leiste (safe-area-top)
├──────────────────────────────┤
│ [Horizont|Planisph.] ✦ ✧ ☉  │
│  +60    ·─·    ♃             │
│     Orion     ⚸ Ceres        │
│  +30                         │  Himmel: volle Breite,
│ ╭──S──────────W───╮          │  Ausschnitt ~120° Azimut,
│  −30   ☄                     │  Wischen = schwenken,
│                              │  Pinch = Zoom
│        ◁  SW 225°  ▷         │  Kompass-Anzeige des Ausschnitts
├──────────────────────────────┤
│  «   ‹   23:04 · 25.11.   ›   » │  Zeitleiste (Daumenzone)
├──────────────────────────────┤
│ ═══  Sichtbar (12)  ═══      │  Bottom Sheet (eingeklappt: Griff + Titel)
└──────────────────────────────┘
```

- Der **Himmel nimmt die volle Breite und die verfügbare Höhe** ein (`100dvh` minus Leisten).
- **Zeitsteuerung unten**, im Daumenbereich. Ziele mindestens 44 × 44 px, `env(safe-area-inset-bottom)`.
- **Bottom Sheet** mit drei Zuständen (eingeklappt, halb, voll). Es enthält die Objektliste; beim
  Antippen eines Objekts wechselt es zu dessen Details. Einstellungen, Theme, Sprache und Filter
  öffnen als eigenes Sheet. Dafür wird `<dialog>` mit eigenem Styling verwendet, nicht ein
  `div`-Overlay.
- **Querformat:** Das Sheet wird zur schmalen Seitenleiste rechts, der Himmel nutzt die Breite für
  einen größeren Azimutausschnitt.

## Kernentscheidung: Wie passt das ASCII-Raster aufs Telefon?

| Variante | Vorteile | Nachteile |
|---|---|---|
| A: Schrift verkleinern, bis 80 Spalten passen | einfach, zeigt 360° | auf 360 px etwa 4,5 px Zeichenbreite: Symbole kaum lesbar, Tippziele winzig |
| **B: Azimutfenster** (empfohlen) | lesbare Glyphen (≥ 11 px), Raster bleibt ASCII, Wischen zum Schwenken ist natürlich | Rundumsicht nur durch Schwenken; Kompassanzeige nötig |
| C: Hybrid | B als Standard, Zoomstufe „360°“ blendet auf Variante A um | etwas mehr Logik |

**Empfehlung: C.** Die Zoomstufen werden semantisch zu „Sichtfeld“: 360°, 180°, 120°, 90°.
Desktop startet mit 360°, Telefon im Hochformat mit 120°. Das ist eine Verallgemeinerung des
heutigen 1×/2×/4×-Zooms, der heute am Telefon abgeschaltet ist.

Technisch:

1. **Ein gemeinsames Zellmaß** (`CellMetrics`): Zeichenbreite und -höhe werden einmal an einem
   Probe-Element gemessen und bei Font- oder Größenänderung per `ResizeObserver` neu bestimmt.
   Alle Overlays (Sternbild-SVG, Messier, Labels, Raster, Sonnenbahn, Klick-Trefferprüfung) lesen
   nur noch daraus. Heute misst jedes Overlay selbst über `getBoundingClientRect()` der `.sky-text`.
2. **Spaltenzahl aus der Breite:** `cols = floor(containerWidth / minCellWidth)`, und das
   Sichtfeld legt fest, wie viele Grad Azimut auf diese Spalten kommen. Die Projektion
   `projectHorizonAltAzToGrid` bekommt `fovDeg` und `centerAz` statt der festen 360° plus
   `horizontalShift`.
3. **`CONFIG.SKY_WIDTH` und `SKY_HEIGHT` werden nicht mehr global verändert.** Heute schreibt
   der Konstruktor beim Wechsel in die Planisphäre in `CONFIG`. Das Rastermaß wird stattdessen
   Zustand des Renderers.
4. Die Planisphäre bleibt quadratisch und skaliert auf `min(Breite, Höhe)`. Am Telefon füllt sie
   die Breite; Drehen per Wischen, Zoomen per Pinch.

## Symbole und Raster (betrifft die Vorgabe „ASCII-Charakter erhalten“)

Doppelt breite Emojis (☀️ 🌙 ☄️ 🌑…🌘) verschieben heute die Zeile (L5). Drei Möglichkeiten:

1. **Textdarstellung erzwingen:** ☉ statt ☀️, ☾ statt 🌙, ☄︎ (mit U+FE0E) statt ☄️. Die
   Mondphasen bleiben als Glyphen, aber nur im Detailpanel und in der Liste, im Raster dagegen ein
   einspaltiges Symbol. Das bleibt am nächsten am ASCII-Charakter und ist die **Empfehlung**.
2. **Symbole aus dem Text herausnehmen** und als absolut positionierte Spans auf das Raster legen,
   mit fester Zellbreite. Die Emojis bleiben farbig, das Raster bleibt exakt. Kostet etwas Layout-Code.
3. Unverändert lassen und die Verschiebung hinnehmen.

**Offene Entscheidung für dich:** Variante 1 ändert sichtbar die Sonne-, Mond- und Kometensymbole.

Außerdem:

- **Font-Stack:** `ui-monospace, "Cascadia Mono", "JetBrains Mono", "DejaVu Sans Mono", Menlo,
  Consolas, monospace`. Kein Webfont-Download, aber ein Stack mit guter Box-Drawing- und
  Symbolabdeckung statt nur `'Courier New'`.
- `font-variant-ligatures: none`, `line-height` fest (z. B. `1.15`), damit die Zellhöhe stabil ist.

## Theming

Die vier Themen bleiben, technisch sauberer:

- **Tokens auf `:root[data-theme="green|red|blue|amber"]`** statt `body.theme-*` mit Grün als
  klassenlosem Standard. Ein Satz semantischer Tokens:
  `--fg`, `--fg-dim`, `--fg-muted`, `--accent`, `--accent-rgb`, `--bg`, `--surface`,
  `--surface-2`, `--border`, `--ui-bg`, `--ui-bg-hover`, `--ui-bg-active`, `--glow`,
  `--overlay-constellation`, `--overlay-messier`, `--horizon`.
- **Alle Overlays folgen dem Theme.** Die Sternbilder tun das bereits (`constellations.css`
  nutzt `--primary-rgb`). Die Farbwerte in `CONFIG.CONSTELLATIONS` (`#4a90e2`) sind unbenutzt
  und kommen weg. Das Debug-Raster in `zodiacRenderer.js` nutzt noch feste Farben (`#ff0000`,
  `#00ff00`). Messier, Labels und Sonnenbahn werden im Zuge von P2 auf dieselben Tokens geprüft.
  Das Rot-Theme soll durchgängig rot bleiben, damit die Dunkeladaption der Augen erhalten bleibt.
- **Ein datengetriebener Theme-Umschalter** statt vier Handlern (D6):
  `THEMES.forEach(t => …)`, der Zustand liegt in `settingsManager`.
- `<meta name="theme-color">` wird beim Umschalten mitgesetzt, damit die Browserleiste auf dem
  Telefon passend eingefärbt ist.
- **Leuchteffekt dezent:** `text-shadow: 0 0 6px rgb(var(--accent-rgb) / .35)` für Objekte und den
  Horizont, abgeschaltet bei `prefers-reduced-motion` bzw. über eine Einstellung.
- Kontrast: `--fg-dim` erreicht auf `--bg` in allen vier Themen mindestens 4.5 : 1. Der heutige
  Wert `#666` auf `#0a0a0a` liegt darunter.

## Interaktion

- **Pointer Events** (`pointerdown/move/up`, `setPointerCapture`) ersetzen die getrennten
  Maus- und Touch-Pfade. Es gibt ein Gestenmodell für alle Geräte: ziehen heißt schwenken bzw.
  drehen, Pinch und Mausrad zoomen das Sichtfeld, Tippen wählt aus. Die Trägheit beim
  Schwenken bleibt erhalten.
- **Gerätefähigkeit statt UA-Sniffing:** `matchMedia('(pointer: coarse)')` für eine größere
  Trefferzone (Radius in Zellen) und größere Bedienelemente. `isMobileDevice()` entfällt.
- **Tastatur:** ← → schwenken, + − zoomen, `H`/`P` Ansicht, `T` jetzt, `[ ]` ±1 h, `{ }` ±1 Tag,
  Esc schließt Panel oder Sheet. Der Fokus ist sichtbar (`:focus-visible`).
- **Auswahl:** Tippen auf eine Zelle mit mehreren Objekten öffnet eine Auswahlliste im Sheet bzw.
  Panel statt des heutigen schwebenden Mehrfachdialogs.
- `user-scalable=no` und `maximum-scale=1.0` entfallen. Damit der Browser Pinch-Gesten im
  Himmelsbereich nicht als Seitenzoom behandelt, bekommt der Himmelscontainer
  `touch-action: none`.

## Render-Architektur

Diese Umstellung behebt zugleich L2, L3, L6, L16 und O10:

1. **Das DOM-Gerüst wird einmal erzeugt:** `<pre class="sky-text">`, SVG-Layer,
   Werkzeugleiste und Zähler bleiben bestehen. `render()` setzt nur noch
   `pre.textContent` und ruft `overlay.update(metrics, projection)` auf.
2. **Render-Batching:** `scheduleRender()` fasst Aufrufe pro Frame per `requestAnimationFrame`
   zusammen. `refreshDialogIfVisible()` aktualisiert nur das Panel und rendert nicht den Himmel neu.
3. **Ein neues Update ersetzt das alte:** Jedes Update bekommt einen `AbortController`, ein neues
   Update bricht das laufende ab. Die Sperre `_updateRunning` entfällt.
4. **Fehler als Status, nicht als Ersatz des Inhalts:** Ein Hinweisbalken („Daten veraltet,
   erneuter Versuch…“) erscheint, und das letzte gute Bild bleibt stehen.
5. **Lebenszyklus:** Bei `document.hidden` pausiert das Intervall, bei Sichtbarkeit wird sofort
   aktualisiert (O13). `DEBUG` ist standardmäßig aus (O11).
6. **Initialisierung ohne `setTimeout`:** `await settings` → `await auth` → `renderer.mount()` →
   `ui.bind()` → erstes `update()` (O15).
7. Das Inline-Skript aus `index.html` (etwa 600 Zeilen) wandert in Module:
   `static/js/app.js` (Bootstrap), `ui/appBar.js`, `ui/timeBar.js`, `ui/sheet.js`,
   `ui/themeMenu.js`, `ui/help.js`. Die Hilfetexte nur noch aus `i18n.js` (D7).

## CSS-Aufräumen

- Löschen: `fullscreen.css` (leer), `locationDialogStyles.css`, `viewTabs.css` (nicht eingebunden,
  Duplikat in `app.css`).
- Die 15 Einzeldateien bleiben thematisch getrennt, werden aber nach Ebenen geordnet:
  `tokens.css` (Themen), `base.css` (Reset, Typo), `layout.css` (Leisten, Spalten, Sheet),
  `sky.css` (Raster, Overlays), `components/*.css` (Dialoge, Listen, Buttons). `admin.html` und
  `worker_monitor.html` laden nur `tokens.css` und `base.css`.
- `@layer tokens, base, layout, components, overrides;` statt `!important`, das heute z. B. beim
  mobilen `#object-dialog` gebraucht wird.
- Container Queries für Werkzeugleiste und Panel statt nur Viewport-Breakpoints.
- `100dvh`, `env(safe-area-inset-*)`, `overscroll-behavior: contain` im Sheet.

## Phasen

Jede Phase ist für sich auslieferbar und wird im Browser bei 360 × 800, 390 × 844 (Hochformat und
Querformat), 768 × 1024, 1280 × 800 und 1920 × 1080 geprüft, jeweils in beiden Ansichten, allen
vier Themen und DE/EN.

| Phase | Inhalt | Fertig, wenn |
|---|---|---|
| **P0 Fundament** | `.venv` reparieren, Tests grün; Analysebefunde L1–L4, L7, L16 beheben | Suite grün; Vollmond erscheint ±22,5°; schnelles Klicken auf „+1 h“ zeigt immer die letzte Zeit; keine wachsende Listenerzahl (DevTools `getEventListeners(document)`) |
| **P1 Render-Kern** | persistentes DOM, `scheduleRender`, `AbortController`, `CellMetrics` und `ResizeObserver`, Fehlerbalken, Sichtbarkeitspause | 1 Render pro Datenänderung; Overlays liegen nach Größenänderung exakt auf dem Raster; Offline-Fehler lässt das Bild stehen |
| **P2 Tokens und Themen** | `data-theme`, semantische Tokens, Overlay-Farben pro Theme, `theme-color`, ein Theme-Handler | alle vier Themen vollständig inklusive Overlays und Dialogen; Rot-Theme ohne fremdfarbige Elemente; Kontrast ≥ 4.5 : 1 |
| **P3 Layout Desktop** | App-Leiste, drei Spalten, Werkzeugleiste, Detailpanel, Inline-Skript in Module | keine Bedienelemente außerhalb von Leiste, Panel und Werkzeugleiste; Hilfe nur aus i18n |
| **P4 Mobil** | Sichtfeld-Projektion (FOV), Pointer Events, Pinch, Bottom Sheet, Zeitleiste unten, Safe Areas, kein `user-scalable=no` | 360 px: kein horizontales Scrollen, Glyphen ≥ 11 px, alle Ziele ≥ 44 px; Schwenken, Pinch und Tippen funktionieren auf einem echten Gerät |
| **P5 Symbole** | nach deiner Entscheidung: Textdarstellung oder Symbol-Overlay | Spalten bleiben in jeder Zeile ausgerichtet; Klick auf ein Symbol trifft genau dieses Objekt |
| **P6 Feinschliff** | Tastaturkürzel, `:focus-visible`, `prefers-reduced-motion`, optional Web-App-Manifest (Startbildschirm) | Bedienung komplett per Tastatur; Lighthouse-Barrierefreiheit ≥ 90 |

## Offene Entscheidungen

1. **Symbole (P5):** Textdarstellung (☉ ☾ ☄︎) oder Emoji-Overlay?
2. **Mobiles Sichtfeld:** Start mit 120° (Empfehlung) oder 180°?
3. **Planeten-Knopfzeile:** ganz in der Objektliste aufgehen lassen (Empfehlung) oder als
   Filter-Chips behalten?
4. **Web-App-Manifest** (installierbar, Vollbild am Telefon): ja oder nein? Ohne Service Worker und
   ohne Offline-Modus, nur das Manifest.
