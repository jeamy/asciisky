# Codeanalyse AsciiSky (Nachprüfung)

**Stand:** 25. November 2026
**Untersuchter Stand:** Commit `5fa1116` (Arbeitsbaum ohne lokale Änderungen)
**Ziel:** Sicherheitsbefunde, Logikfehler, Optimierungsmöglichkeiten, toter und doppelter Code
**Vorgänger:** [CODE_ANALYSIS_REPORT_2026-08-24.md](CODE_ANALYSIS_REPORT_2026-08-24.md)

## Vorgehen und Grenzen

- `ruff check --select F,B,SIM,PERF,UP,E9` über alle versionierten Python-Dateien:
  **keine F-Befunde** (keine undefinierten Namen, keine unbenutzten Importe).
  Übrig sind 77 Stilpunkte (B904 `raise … from`, B905 `zip(strict=)`, SIM105, PERF203).
- `vulture --min-confidence 60` (mit System-Python 3.15 und den Paketen aus der `.venv`).
  Die gemeldeten Routen sind Falschmeldungen, weil sie per Decorator registriert werden.
  Jeder übrige Treffer wurde per `git grep` geprüft.
- Manuelles Lesen (Durchgang 1): alle API-Routen für Himmel, Asteroiden und Kometen, `api/computation.py`,
  `api/cache_interpolation.py`, `api/interpolation.py`, `api/smart_interpolation.py`,
  `api/astronomical_corrections.py`, `config/interpolation_config.py`,
  `api/rabbitmq/task_publisher.py`, `main.py`, `templates/index.html`,
  `static/js/skyRenderer.js`, `static/js/skyManager.js`, `static/js/constants.js`,
  `static/css/app.css`.
- Manuelles Lesen (Ergänzung / Durchgang 2): `api/routes/{auth,admin_users,user_settings,filters,session,config,messier,zodiac,interpolation_admin}.py`,
  `db_utils.py`, `cache_utils.py`, `settings.py`, `timezone_utils.py`,
  `workers/{unified_worker,precompute_worker,worker_utils,worker_monitor,monitor_dashboard}.py`,
  `comets.py`, `bright_asteroids.py`, `precompute_coordinator.py`, `nightly_data_updater.py`,
  `cleanup_task_files.py`, `static/js/{auth,adminUsers,settings,locationDialog,magnitudeFilterDialog,timeInputDialog,visibleObjectsList,i18n,sunpathOverlay,zodiacRenderer,messierRenderer}.js`,
  `templates/{admin,worker_monitor}.html`.
- **Tests wurden nicht ausgeführt.** Die `.venv` ist defekt: Ihr Interpreter ist
  `python3.14`, auf dem System gibt es nur noch 3.12 und 3.15. Sie muss neu aufgebaut werden.
  Das wurde bewusst nicht ohne Rückfrage gemacht.

Kennzeichnung: **verifiziert** heißt im Code nachgewiesen. **Verdacht** heißt plausibel, aber
nicht reproduziert.

---

## 1. Sicherheitsbefunde

| # | Befund | Ort | Status |
|---|---|---|---|
| S1 | **Unauthentifiziertes Überschreiben globaler Server-Defaults via `POST /api/filters`.** Für anonyme Aufrufer (`user_id is None`) schreibt `_set_filters_sync()` über `settings.set_magnitude_filters()` direkt in die gemeinsame `cache/user_settings.json` auf dem Server. Jeder nicht angemeldete Client kann die globalen Standardfilter für alle anonymen Nutzer (und angemeldete Nutzer ohne eigene Filter) überschreiben. | `api/routes/filters.py:94-123`, `settings.py:116-135` | verifiziert |
| S2 | **Self-XSS über unescaped `currentUser.username`.** `openAuthDialog()` interpoliert `currentUser.username` direkt in `overlay.innerHTML`. Das Backend prüft bei der Registrierung nur `len(username) >= 3` ohne Zeichenbeschränkung. Keine gespeicherte XSS gegen Dritte: Die Admin-Liste setzt den Namen per `textContent` (`adminUsers.js:92`), ein Angreifer trifft also nur die eigene Sitzung. | `static/js/auth.js:199-208`, `api/routes/auth.py:187` | verifiziert |
| S3 | **Third-Party-XSS in `LocationDialog`.** Externe Nominatim-Antworten (`display_name`, `place_id`) werden unescaped per `innerHTML` eingefügt; OpenStreetMap-Namen sind von Dritten editierbar. Zusätzlich landet der eigene Standortname `this.currentLocation.name` unescaped im Text- und Attribut-Kontext (`value="${...}"`) – das ist nur Self-XSS. | `static/js/locationDialog.js:46,66,161,172-176` | verifiziert |
| S4 | **DoS auf Precomputation durch unvalidiertes `PUT /api/user/settings`.** `UserSettingsModel.location` ist als `dict[str, Any] \| None` typisiert, ohne Typ-/Bereichsprüfung für `latitude`, `longitude` oder `elevation`. `db_utils.get_all_user_locations()` castet alle Zeilen mit `::double precision`. Ein einziger Nutzer mit `{"location": {"latitude": "bad"}}` löst `InvalidTextRepresentation` aus. `precompute_coordinator.py:158` fängt den Fehler ab, überspringt damit aber die Standorte **aller** Datenbanknutzer; Datei- und Standardstandorte werden weiter vorberechnet. | `api/routes/user_settings.py:19-26,103-125`, `db_utils.py:489-503` | verifiziert |
| S5 | **Session-Cookie ohne `https_only=True` in Produktion.** `SessionMiddleware` nutzt den Starlette-Standard `https_only=False` auch bei `ASCII_SKY_ENV=production`. Session-Cookies (inkl. Admin-Sessions) werden dadurch auch über unverschlüsseltes HTTP übertragen. | `main.py:54-61` | verifiziert |
| S6 | **Account-/Status-Enumeration und fehlendes Rate-Limiting in `/api/auth/login`.** `_authenticate_sync()` überspringt bei unbekanntem Benutzer PBKDF2 (Timing-Unterschied) und liefert `403 "User is disabled"` noch **vor** der Passwortprüfung. Zudem gibt es kein Rate-Limiting auf `/auth/login` und `/auth/register`. | `api/routes/auth.py:162-175` | verifiziert |
| S7 | **Cross-User-Settings-Leak nach Logout.** `performLogout()` löscht `localStorage` (`asciisky_settings`) nicht. Registriert sich danach ein anderer Nutzer am selben Browser, lädt `performRegister()` unmittelbar die gespeicherten Einstellungen des vorherigen Nutzers in das neue Konto hoch. | `static/js/auth.js:64-83,165-178` | verifiziert |
| S8 | **Default-Zugangsdaten `'changeme'` ohne Production-Guard & `pickle.loads` auf Cache-Daten.** `POSTGRES_PASSWORD` und `RABBITMQ_URL` fallen ohne Fail-Closed-Prüfung auf `'changeme'` zurück (anders als `ASCII_SKY_SESSION_SECRET`). Zudem werden `cached_positions.position_data` und `DATA_DIR/*.pkl` per `pickle.loads()` deserialisiert (RCE-Risiko bei kompromittierter DB/Cache-Datei). In der Admin-UI wird das neue Passwort zudem im Klartext über `window.prompt()` abgefragt. | `db_utils.py:34,175,265,423,433`, `settings.py:17`, `workers/unified_worker.py:858`, `precompute_coordinator.py:78`, `bright_asteroids.py:199`, `comets.py:458`, `static/js/adminUsers.js:126` | verifiziert |
| S9 | **Unauthentifiziertes `monitor_dashboard.py` mit Wildcard-CORS + Credentials & XSS** *(aktuell in `docker-compose*.yml` auskommentiert)*. Alle HTTP-/WS-Endpunkte (inkl. Restart-/Scale-Stubs) haben keine Auth; `allow_origins=["*"]` mit `allow_credentials=True`; XSS in Fallback-HTML und `templates/worker_monitor.html` (zusätzlich unpinned Chart.js ohne SRI). | `workers/monitor_dashboard.py:98-105,147-156,202-274`, `templates/worker_monitor.html:8,242-267` | verifiziert |

---

## 2. Logikfehler

| # | Befund | Ort | Status |
|---|---|---|---|
| L1 | **Vollmond-Fenster ist nur 5° breit.** Das Mondphasen-Mapping gibt `full_moon` nur für 177,5°–182,5° zurück, also etwa ±5 Stunden. Neumond bekommt dagegen 45° (337,5°–22,5°), zunehmender und abnehmender Mond je 65°. Symmetrisch wären acht Sektoren zu 45° (Vollmond 157,5°–202,5°), oder ein bewusst dokumentiertes engeres Fenster für alle Hauptphasen. Folge: Das Vollmond-Symbol 🌕 erscheint praktisch nie. | `api/computation.py:170-191` | verifiziert |
| L2 | **Neueste Zeiteingabe wird verworfen.** `update()` bricht ab, solange `_updateRunning` gesetzt ist. Klickt man schnell zweimal auf „+1 h“, wird das zweite Update übersprungen. Die Zeitanzeige springt weiter, der Himmel bleibt aber bis zum nächsten 60-s-Tick auf der Zwischenzeit stehen. Der Token-Mechanismus (`_activeUpdate`) würde genau das lösen, wird durch die Sperre aber wirkungslos. Richtig wäre: neues Update starten und das alte per Token oder `AbortController` verwerfen. | `static/js/skyRenderer.js:2299-2306` | verifiziert |
| L3 | **Listener-Leck bei `fullscreenchange`.** `drawHorizon()` hängt bei jedem Aufruf einen neuen `document`-Listener an. `drawHorizon()` läuft über `initSky()` bei jedem `render()`, also mehrmals pro Minute, bei jedem Pan-Schritt und jeder Dialog-Aktualisierung. Der Handler ruft nur No-op-Helfer auf (`createFullscreenButton` und Co. sind leer). Der Code ist also tot und wächst trotzdem unbegrenzt. | `static/js/skyRenderer.js:371-382`, `:638-640` | verifiziert |
| L4 | **Himmelsrichtung „E“ zählt im Englischen als belegt.** `isOccupied` schließt fest `'N','S','O','W'` aus, die Beschriftung kommt aber aus `t('east')`, also `'E'` im Englischen. Ein Objekt auf dieser Zelle wird deshalb als Überlappung gezeichnet. | `static/js/skyRenderer.js:1047-1053`, `i18n.js:315` | verifiziert |
| L5 | **Emoji-Symbole zerstören das Monospace-Raster.** ☀️, 🌙, ☄️ und die Mondphasen 🌑…🌘 sind in praktisch allen Fonts doppelt breit. Jede Zeile mit einem Emoji verschiebt sich rechts davon um eine Spalte. Dann passen Klickposition, SVG-Sternbilder und Labels nicht mehr zum Text. | `static/js/constants.js:38-64`, `api/computation.py:29-41` | verifiziert (Ursache), Ausmaß hängt vom Font ab |
| L6 | **Doppelte Objektzähler-Anzeige bei kaltem/abgelaufenem Cache.** `addObjectCountDisplay()` ist `async`, wird in `render()` aber nicht abgewartet. Die Funktion entfernt die alte Anzeige, wartet auf `fetch('/api/filters')` und hängt erst danach die neue an. Zwei Renders kurz hintereinander bei kaltem/abgelaufenem `_magCache` (z. B. First Paint + Kleinkörper oder Dialog-Refresh) hängen beide eine Anzeige an. | `static/js/skyRenderer.js:595`, `:834-890` | verifiziert (Codepfad, nicht nachgestellt) |
| L7 | **Komet-Schlüssel enthält den Listenindex.** Kometen bekommen den Schlüssel `comet_{count}_{name}`. Für Asteroiden wurde der Index ausdrücklich entfernt („avoid duplicate keys when order changes“). Bei Kometen bleibt er, der Schlüssel eines Kometen ändert sich also, sobald sich die Reihenfolge ändert. | `api/routes/comets.py:104-108` vs. `asteroids.py:101-108` | verifiziert |
| L8 | **Admin-Schalter ohne Wirkung.** `enable_astronomical_corrections` und `correction_level` lassen sich über `/api/interpolation/...` setzen, werden aber nirgends gelesen. `AstronomicalCorrector` nutzt eine eigene, fest verdrahtete `AstronomicalCorrectionConfig`. Dasselbe gilt für `min_quality_threshold`, `max_interpolation_error`, `max_comets`, `max_computation_time`, `enable_retry`, `max_retries`, `retry_delay_seconds`, `enable_metrics`, `enable_debug_logging` und `log_performance_warnings` in `SmartInterpolationConfig`. | `config/interpolation_config.py:54-106`, `api/astronomical_corrections.py:53-78` | verifiziert |
| L9 | **Strategie `HYBRID` fällt stillschweigend auf `nearest_bucket` zurück.** Der Enum-Wert ist wählbar, aber in `_load_with_smart_interpolation` nicht behandelt. | `api/smart_interpolation.py:162-171` | verifiziert |
| L10 | **Smart-Strategie liefert ohne On-Demand trotz vorhandener Daten `None`.** Ist `enable_on_demand_computation=false` und nur ein Bucket vorhanden, greift keiner der Fälle 2–4. Die Funktion endet in „No strategy applicable“ und gibt `None` zurück. Die Route wertet das als Cache-Miss und liefert eine leere Liste, obwohl Daten im Cache liegen. | `api/smart_interpolation.py:199-284` | verifiziert (nur bei aktivierter Smart-Interpolation) |
| L11 | **Eigener Publisher mit fest verdrahteten Zugangsdaten.** `_trigger_background_worker` erzeugt bei jedem Aufruf einen neuen `TaskPublisher` mit `os.environ.get('RABBITMQ_URL', 'amqp://admin:changeme@rabbitmq:5672/')` statt `settings.RABBITMQ_URL`. Alle anderen Pfade verwenden `settings`. | `api/smart_interpolation.py:406-408` | verifiziert |
| L12 | **Blockierende DB-Zugriffe im Event-Loop.** `resolve_magnitude_filter()` ruft für angemeldete Benutzer synchron `get_user_filters_from_db()` (psycopg) direkt in den `async`-Routen `/bright_asteroids` und `/comets` auf. Dasselbe gilt in `api/routes/user_settings.py` für `_require_authenticated_user()`, `db_get_user_settings()` und `db_save_user_settings()` in `GET/PUT /api/user/settings`. Das sind Reste von L14 aus dem Augustbericht. | `api/helpers.py:72-91`, `api/routes/asteroids.py:46-47`, `comets.py:46-47`, `user_settings.py:84-132` | verifiziert |
| L13 | **Inkonsistenter Trigger-Zeitpunkt im Fehlerpfad.** Beim Cache-Miss wird der Worker mit `bucket_dt` getriggert. Bei einer Ausnahme im Ladepfad dagegen mit dem ungerundeten `dt_utc`. | `api/routes/asteroids.py:94,99`, `comets.py:91,96` | verifiziert, folgenarm |
| L14 | **Transitzeit ist der Mittelwert aus Auf- und Untergang.** Bei asymmetrischen Bahnen, vor allem beim Mond, liegt das um Dutzende Minuten daneben. Fehlt Auf- oder Untergang am selben Tag, wird kein Transit gemeldet. Für die Sonne nutzt `compute_sunpath_year` bereits korrekt `almanac.meridian_transits`. Dasselbe sollte für alle Körper gelten. | `api/computation.py:104-143` | verifiziert |
| L15 | **Sunpath: Tagesende an DST-Tagen um 1 h verschoben.** `timezone_utils.get_tzinfo()` liefert `pytz`-Objekte (`timezone_utils.py:55`). `lm + timedelta(days=1)` auf einem pytz-lokalisierten Datum normalisiert nicht. An Umstellungstagen ist das Tagesfenster für die Dämmerungs-Clips deshalb 23 oder 25 h lang und endet zur falschen Stunde. | `api/computation.py:470-471`, `timezone_utils.py:49-57` | verifiziert |
| L16 | **Fehlerpfad zerstört das Layout.** `update()` und `updateSky()` setzen bei einem Fehler `container.textContent = …`. Damit sind auch Pfeile, SVG-Layer und Zoom-Button weg, und beim nächsten erfolgreichen Render wird alles neu aufgebaut. Ein vorübergehender Netzfehler löscht also die ganze Ansicht. | `skyRenderer.js:2390`, `skyManager.js:57` | verifiziert |
| L17 | **HTML-Injektion aus Katalognamen.** Objektnamen aus MPC-Daten landen per `innerHTML` in Dialogen und Zählern (`content.innerHTML = info.join('\n')`). Das Risiko ist gering, weil die Quelle vertrauenswürdig ist, aber `textContent` würde reichen. | `skyRenderer.js:2077` u. a. | verifiziert |
| L18 | **Sunpath-Vorberechnung wird im Coordinator nie ausgelöst.** `start_offset = -2 if current_horizon == 0 else current_horizon` gefolgt von `include_yearly = (start_offset == 0)`. `start_offset` nimmt die Werte `-2, 24, 48, …` an und ist **nie `0`**. Es müsste `current_horizon == 0` geprüft werden. | `precompute_coordinator.py:560-564` | verifiziert |
| L19 | **Asteroid-Worker klemmt Magnitude auf `10.0` ab.** Coordinator und API (`asteroids.py:33,105`) gehen davon aus, dass Buckets bis Mag `20.0` gecacht werden und erst in der API gefiltert wird. `UnifiedWorker` klemmt jedoch mit `min(magnitude, bright_asteroids.MAX_APPARENT_MAGNITUDE)` auf `10.0` ab. Nutzerfilter > 10 mag zeigen daher nie lichtschwächere Asteroiden. Konfigurationsabhängig: `docker-compose.yml:195` gibt dem Worker den Standard 20.0, `.env` setzt aber 10.0; die eigentliche Ursache sind die unterschiedlichen Standardwerte für `web` und `unified_worker`. | `workers/unified_worker.py:360`, `bright_asteroids.py:39`, `docker-compose.yml:64,195`, `.env:62` | verifiziert (mit der mitgelieferten `.env`) |
| L20 | **`POST /api/admin/interpolation/rollback` crasht immer (500) und korrumpiert die Config.** `rollback_to_defaults()` übergibt Strings (`'nearest_bucket'`, `'none'`) an `update_config()`, das sie per `setattr` über die Enum-Attribute schreibt. `_log_config()` und spätere `GET /status`-Aufrufe crashen danach mit `AttributeError: 'str' object has no attribute 'value'`. | `api/routes/interpolation_admin.py:334-359`, `config/interpolation_config.py:142-144,190-200,287-290` | verifiziert |
| L21 | **Poison-Pill-Endlosschleife & stilles ACK unbekannter Tasks im Worker.** Der `except`-Zweig von `callback()` (z. B. kaputtes JSON, Fehler beim Claim-Freigeben) ruft bedingungslos `requeue=True` auf, ohne `method.redelivered`-Prüfung oder DLQ-Routing. Schlägt dagegen `process_task()` fehl, liefert es `False`, und die Aufgabe landet korrekt in der DLQ. Umgekehrt fallen unbekannte `kind`-Werte in `_process_precompute_task()` auf `return True` durch und werden als erfolgreich ge-ACKt. | `workers/unified_worker.py:413-416,433,558-585` | verifiziert |
| L22 | **`time_bucket_utc()` konvertiert nicht-UTC-aware Datetimes nicht nach UTC.** Die Funktion ergänzt `timezone.utc` nur bei `dt.tzinfo is None`, ruft aber kein `dt.astimezone(timezone.utc)` für Zeitzonen mit Offset auf. | `cache_utils.py:40-55` | verifiziert |
| L23 | **Case-sensitiver E-Mail-Login.** Registrierung speichert `email.lower()`, der Login sucht aber mit unkonvertiertem `identifier` case-sensitiv in PostgreSQL. | `api/routes/auth.py:77,183,208` | verifiziert |
| L24 | **Admin-Self-Lockout / Löschen des letzten Admins möglich.** `update_user()` und `delete_user()` verhindern nicht, dass ein Admin sich selbst oder den letzten aktiven Admin löscht, deaktiviert oder herabstuft. | `api/routes/admin_users.py:245-271` | verifiziert |
| L25 | **Unsynchronisierte Lazy-Singletons über Threads.** `zodiac.init_skyfield()` (`hip_data`) und `timezone_utils._get_tf()` (`_tf_singleton`) initialisieren globale Singletons ohne Lock, obwohl sie aus `asyncio.to_thread()` parallel aufgerufen werden. Folge ist doppeltes Laden, kein Absturz. | `api/routes/zodiac.py:65-77`, `timezone_utils.py:14-23` | verifiziert |
| L26 | **Monitor-Subsystem mehrfach defekt** *(aktuell in Compose auskommentiert)*. Status-Mismatch `'healthy'` (Worker) vs. `'active'` (Monitor → immer 0 aktive Worker), `json.dumps` crasht im WebSocket auf `datetime` (`last_heartbeat`), ungesicherte Dict-Mutationen über Threads, `FileResponse` fängt `FileNotFoundError` nicht ab, WebSocket-Liste wird während Iteration mutiert, und `worker_monitor.html` plottet `Math.random()`-Fake-Daten statt API-Werten und versteckt `0`-Metriken als `'-'`. | `workers/worker_monitor.py:106-132,250-308,384,427`, `workers/monitor_dashboard.py:60-65,111-113,253-259`, `templates/worker_monitor.html:211-237,358-378` | verifiziert |
| L27 | **Englische Zeitangaben zeigen `"18:45 hour"`.** In `i18n['en']` ist `'hour': ''` falsy. `t(key)` prüft auf Truthiness (`if (i18n[lang][key])`) statt `!== undefined` und gibt daher den rohen Schlüssel `'hour'` zurück. | `static/js/i18n.js:352,511-524`, `skyRenderer.js:1992` | verifiziert |
| L28 | **Fehlende, asymmetrische und doppelte i18n-Keys + statischer Filter-Dialog.** `magnitudeFilterDialog.js` nutzt nicht existierende Keys `'cancel'`/`'ok'` (Buttons zeigen klein `"cancel"`/`"ok"`) und baut sein DOM nur einmal im Konstruktor (Sprachwechsel greift nicht). 13 Keys fehlen im Englischen (u. a. `'asteroids'`, `'comets'`), 10 im Deutschen; `'apply'` ist in beiden Sprachen doppelt definiert; `auth.js` ist komplett hartkodiert deutsch. | `static/js/i18n.js:120,153,368,401`, `magnitudeFilterDialog.js:13,63-66`, `auth.js:30,98-240` | verifiziert |
| L29 | **Doppelter Elevation-Fetch, ungültiges `<input type="number">` und Null-DOM-Crashes in `LocationDialog`.** Ein Klick auf ein Suchergebnis ruft `getElevationForCoordinates()` auf, verwirft das Ergebnis, setzt die Höhe zurück, feuert `onLocationChange`, fragt die Höhe ein zweites Mal ab und feuert `onLocationChange` erneut. Außerdem schreibt `getElevationForCoordinates()` einen Textstring in `<input type="number">`, und nach `await`/`.then()` wird nicht geprüft, ob der Dialog noch offen ist. | `static/js/locationDialog.js:62,129-142,194-203,215-218,236-282` | verifiziert |
| L30 | **Sunpath Off-by-One-Datum in westlichen Zeitzonen (`UTC-x`) & Toggle-Race.** `new Date("YYYY-MM-DD")` wird als UTC-Mitternacht geparst; westlich von UTC verschieben `getDate()`/`getMonth()`/`toLocaleDateString()` alle Daten und Monatsticks um einen Tag zurück. `toggleForCurrentLocation()` fehlt zudem ein In-Flight-Guard. | `static/js/sunpathOverlay.js:271-312,362-365,655-663` | verifiziert |
| L31 | **Sternbild-Wrap-Logik bricht Planisphere-Modus; Crash in `visibleObjectsList.js`.** `zodiacRenderer.js` wendet die zylindrische 0°–360°-Wrap-Logik auch im kreisförmigen Planisphere-Modus an (und zeichnet im Horizont-Modus nur eine Hälfte umgebrochener Linien). `visibleObjectsList.js` ruft `obj.magnitude.toFixed(1)` ohne Typprüfung auf (Crash bei `null`/`undefined`). | `static/js/zodiacRenderer.js:322-332,359-368`, `visibleObjectsList.js:108-109,142,150` | verifiziert |

---

## 3. Optimierungsmöglichkeiten

### Backend

| # | Befund | Ort |
|---|---|---|
| O1 | **`/celestial` rechnet alles bei jedem Aufruf neu.** Jeder Client ruft alle 60 s auf. Dabei laufen für 9 Körper je eine `find_discrete`-Suche über 2 Tage für Auf- und Untergang, und das ist der teuerste Teil. Auf- und Untergänge ändern sich nur einmal pro lokalem Tag und Standort. Ein kleiner LRU-Cache mit Schlüssel `(loc_key, local_date, body)` spart den Großteil der Rechenzeit. Nur Alt/Az und Magnitude müssen frisch berechnet werden. | `api/computation.py:194-232` |
| O2 | `eph['earth'].at(t)` wird pro Körper neu berechnet, `observer.at(t)` ebenso. Beides einmal pro Snapshot berechnen. | `api/computation.py:65-75` |
| O3 | `almanac.moon_phase` wird pro Snapshot zweimal berechnet (Magnitude und Phasenname). | `api/computation.py:84`, `:172` |
| O4 | `/celestial/{body_id}` berechnet den ganzen Snapshot inklusive 9 Auf- und Untergangssuchen, um einen einzigen Körper zurückzugeben. | `api/routes/celestial.py:114-135` |
| O5 | `_build_transit_events_by_date` beobachtet für jedes der etwa 730 Transit-Ereignisse die Sonnenhöhe, nur um den oberen Transit zu wählen. `ev == 1` (oberer Transit) liefert das direkt. Dasselbe Muster existiert auch in `api/routes/messier.py:354-368`. | `api/computation.py:270-282`, `api/routes/messier.py:354-368` |
| O6 | **O(n²) in den astronomischen Korrekturen.** `_find_object_by_name` durchsucht die Listen linear, pro Objekt bis zu 6-mal (3 Korrekturen × 2 Listen). Bei etwa 1000 Asteroiden sind das Millionen Vergleiche pro Request. Ein vorab gebautes `dict` nach Namen behebt das. Betrifft nur die aktivierte Smart-Interpolation. | `api/astronomical_corrections.py:187,355,459,509` |
| O7 | `resolve_magnitude_filter` liest bei jedem Request die Benutzereinstellungen aus der DB, siehe L12. Diesen Wert in `asyncio.to_thread` holen oder in der Session zwischenspeichern. | `api/helpers.py:72` |
| O8 | Der Thread-lokale pika-`BlockingConnection` verarbeitet Heartbeats nur bei I/O. Nach längerer Ruhe schließt der Broker die Verbindung. Der nächste Publish schlägt fehl und gibt den Claim frei, die Aufgabe kommt erst beim nächsten Request wieder. Das ist funktional abgefangen, erzeugt aber Fehler im Log und Verzögerung. Abhilfe: Vor dem Publish `process_data_events(0)` aufrufen oder einmal neu verbinden und wiederholen. | `api/rabbitmq/task_publisher.py:68-134` |
| O9 | Jede neue Publisher-Verbindung deklariert alle Exchanges und Queues neu. Das ist harmlos, gehört aber eher einmalig in den Worker- oder Setup-Pfad. | ebd. |
| O17 | **Doppelter PostgreSQL-Write (und Extra-Read) je Precompute-Task.** `UnifiedWorker` ruft `load_bright_asteroids()` / `load_comets()` mit Standard `use_cache=True` auf (schreibt bereits in Postgres; `comets.py:442` liest vorher zusätzlich) und ruft direkt danach erneut `store_asteroid_positions()` / `store_comet_positions()` auf. `use_cache=False` beseitigt beides. | `workers/unified_worker.py:364-396`, `bright_asteroids.py:471`, `comets.py:442,889` |
| O18 | **Peak-RAM-Verdopplung für eine Logzeile** (Größenordnung geschätzt, nicht gemessen). Direkt nach dem Verarbeiten von MPCORB (während `df` noch im Speicher liegt) ruft `update_asteroid_data()` `get_database_stats()` auf, das beide `.pkl`-DataFrames komplett neu deserialisiert, nur um `len(df)` zu loggen. | `nightly_data_updater.py:326,386`, `db_utils.py:408-441` |
| O19 | **Ungecachtes Disk-Parsing und `observer.at(time)` in Stern-Schleife bei `/api/zodiac`.** `load_stellarium_constellations()` parst `constellationship.fab` bei jedem Request neu von Platte; `get_star_position()` berechnet `observer_location.at(time)` pro Stern neu statt einmal pro Request. | `api/routes/zodiac.py:86,130,156-157` |

### Frontend

| # | Befund | Ort |
|---|---|---|
| O10 | **Bis zu 4 Voll-Renders pro Update-Zyklus.** Ablauf: First Paint, dann `refreshDialogIfVisible()` (rendert erneut), dann nach den Kleinkörpern wieder Render und Refresh. Jeder Render leert `container.innerHTML` und baut Pfeile, Zoom-Button, Zähler und Labels neu auf. Besser: Die DOM-Struktur einmal erzeugen und pro Render nur `textContent` des `<pre>` und die Overlays aktualisieren. | `skyRenderer.js:534-636`, `:2041-2082`, `:2299-2390` |
| O11 | **`DEBUG` ist standardmäßig `true`.** Dutzende `console.log` laufen pro Update, auch in Produktion. Standard sollte `false` sein, mit `?debug=1` zum Einschalten. | `static/js/constants.js:118-137` |
| O12 | Kleinkörper werden mit `cache: 'no-store'` geladen, obwohl die Buckets unveränderlich sind. Mit `ETag` oder `Cache-Control: max-age` bis zum Bucket-Ende entfiele die Übertragung. | `skyRenderer.js:2263` |
| O13 | Das 60-s-Intervall läuft auch in Hintergrund-Tabs weiter. Bei `document.hidden` pausieren und bei `visibilitychange` sofort aktualisieren. | `static/js/skyManager.js:29` |
| O14 | `visibleObjectsList.js` wird pro Update zweimal per dynamischem `import()` geladen, obwohl das Modul ohnehin statisch in `index.html` importiert ist. | `skyRenderer.js:2340`, `:2379` |
| O15 | Init per `setTimeout(…, 100)` und `setTimeout(…, 500)` statt einer deterministischen Reihenfolge nach `await`. Das kostet eine halbe Sekunde bis zur Bedienbarkeit, und es gibt Race-Fenster. | `templates/index.html:128,142` |
| O16 | Keine Anpassung an die Größe: Kein `resize`- oder `ResizeObserver`-Handler im Renderer, und `--sky-font-size` wird nirgends gesetzt. Auf Mobilgeräten bleibt das 80-Spalten-Raster bei fest `0.6rem` und läuft über (siehe UI-Plan). | `static/css/app.css:498`, `skyRenderer.js` |
| O20 | **`<link>`-DOM-Leck in `auth.js` und `index.html` & unbegrenzter Cache in `messierRenderer.js`.** `openAuthDialog()` und `loadCSSFile()` in `index.html` (Hilfe-, Standort- und Zeitdialog) hängen bei jedem Öffnen ein neues `<link>` in `<head>` an, weil `link.href` absolut aufgelöst ist, aber auf `'./static/css/…'` geprüft wird. `MessierRenderer.detailsCache` nutzt `lastDataTimeISO` im Key (alle 60 s neu) und wächst ohne Eviction. | `static/js/auth.js:6-20,191`, `templates/index.html:335,436,498,535`, `messierRenderer.js:9,70-89,113` |
| O21 | **730 einzelne Mouse-Listener je `SunpathOverlay.render()`.** Erzeugt ~365 `<rect>`-Elemente mit je 2 eigenen Listenern (`mousemove`/`mouseleave`) statt Event-Delegation am Container. | `static/js/sunpathOverlay.js:750-780` |

---

## 4. Toter Code

Jeder Eintrag wurde per `git grep` geprüft: Es gibt nur die Definition, keine Verwendung.

**Python**
- `TaskPublisher.publish_sunpath_task`, `TaskPublisher.publish_batch` (`api/rabbitmq/task_publisher.py:222`, `:321`)
- `close_db_connection` (`db_utils.py:92`)
- `InterpolationConfigManager.add_update_callback` / `remove_update_callback` (`config/interpolation_config.py:271-280`)
- Konstanten `DEFAULT_TTL_SECONDS` (`cache_utils.py:13`), `ASTEROID_CACHE_TTL_SECONDS` (`bright_asteroids.py:46`), `COMET_CACHE_TTL_SECONDS` (`comets.py:43`), `DE421_PATH`, `HIPPARCOS_MAIN_PATH` (`data_paths.py:18-19`)
- `ComputationStatus.BACKGROUND_TRIGGERED` (`api/on_demand_computation.py:48`), `AstronomicalCorrectionConfig.confidence_threshold` (`api/astronomical_corrections.py:64`)
- `_recalculate_time_based_events` ist ein reiner TODO-Stub, der immer `quality 1.0` liefert und den Qualitätsdurchschnitt nach oben verzerrt (`api/astronomical_corrections.py:492-507`).
- In den Routen `/bright_asteroids` und `/comets` wird `interpolation_strategy` nur für eine Logzeile berechnet.
- Die zwölf wirkungslosen Konfigurationsfelder aus L8.
- `cleanup_task_files.py`: obsoletes Pre-RabbitMQ-Skript ohne Referenzen im Repo, zudem defekt (`task_*.json` matcht auch `task_status_*.json` und versucht doppelte Pfade zu löschen).
- **Ganzes Subsystem standardmäßig aus:** `ENABLE_SMART_INTERPOLATION=false` und `INTERPOLATION_STRATEGY=nearest_bucket`. Damit laufen `smart_interpolation.py` (588 Zeilen), `astronomical_corrections.py` (548) und große Teile von `interpolation_admin.py` (394) und `interpolation_config.py` (376) im Normalbetrieb nicht. Dazu kommen die Fehler L8–L11, L20 und O6. Empfehlung: entweder entfernen (etwa 1 900 Zeilen) oder bewusst fertigstellen und testen. Halbfertig produziert es nur Fehlerpotenzial.

**Frontend**
- `static/css/fullscreen.css` ist leer und wird nirgends eingebunden.
- `static/css/locationDialogStyles.css` und `static/css/viewTabs.css` werden nirgends eingebunden. Die Tab-Stile stehen zusätzlich in `app.css`.
- `createFullscreenButton`, `updateFullscreenButton` und `adjustSkyScale` sind No-ops; der `fullscreenchange`-Handler gehört dazu (L3).
- In `loadSmallBodies` greift der Zweig `data.bodies[this.selectedObject.name]` nie, weil Kleinkörper-Schlüssel ein Präfix haben. Die Aktualisierung passiert trotzdem korrekt über die Namenssuche in `refreshDialogIfVisible()`. Der Zweig ist also tot, aber kein Fehler (`skyRenderer.js:2280-2283`).
- Leerer `if/else`-Block mit auskommentierten Overlay-Aufrufen (`skyRenderer.js:611-615`); eine leere `<ul></ul>` im Hilfedialog.
- `CONFIG.CONSTELLATIONS.STROKE_*` und `LABEL_*` werden nicht gelesen; die Farben kommen aus `constellations.css` (`--primary-rgb`).
- `API_ENDPOINTS.SKY` und `ASTEROIDS` sind Aliasse von `CELESTIAL` und `BRIGHT_ASTEROIDS`. Dazu die Legacy-Kommentare in `constants.js:11-14`.
- Die Route `/api/asteroids` ist ein Alias „for backward compatibility“, das Frontend verwendet sie nicht (`api/routes/asteroids.py:116-120`).
- `sunpathOverlay.js:12-14`: unbenutzte Funktion `sleep()`.
- `zodiacRenderer.js:12-13,135-182,312-314`: unbenutzte Konstanten `MAX_AZ_SEPARATION_DEG`/`MAX_ALT_SEPARATION_DEG`, `cleanup()` (entfernt nie registrierten `resizeHandler`), `showAllConstellations()`, `debugConstellations()` sowie ungenutzte `dAz`/`azSeparation`/`altSeparation`-Berechnungen.
- `locationDialog.js:318-338`: `triggerAutomaticPrecompute()` re-importiert `constants.js`, berechnet ungenutzte Datumsstrings und loggt nur.
- `magnitudeFilterDialog.js:12,153-155`: `this.pendingFilters` ungenutzt; `window.showTemporaryMessage` existiert nirgends.
- `visibleObjectsList.js:2`: unbenutzter Import `settingsManager`.
- `settings.js:206-234`: `simTime.enabled` wird gespeichert, aber bewusst nicht mehr gelesen („kein separater Toggle mehr“) – totes Feld, kein Fehler.

---

## 5. Doppelter Code

| # | Befund | Ort |
|---|---|---|
| D1 | `/bright_asteroids` und `/comets` sind zu etwa 90 % identisch (Filter, Feature-Flags, Bucket, Miss-Trigger, Ergebnisaufbau). Eine generische Funktion `_small_body_route(kind, …)` würde beide ersetzen und L7 und L13 gleich mit beheben. | `api/routes/asteroids.py`, `comets.py` |
| D2 | Die Nearest-Bucket-Logik existiert zweimal: `cache_interpolation._load_with_interpolation_generic` mit festem Zukunftslimit `1.0 h` und `smart_interpolation._apply_nearest_bucket_strategy` mit `max_future_hours`, Standard 2.0. Bei den aktuellen 1-h-Buckets wirkt sich das nicht aus, die Werte laufen aber auseinander, sobald jemand die Bucket-Größe ändert. | `api/cache_interpolation.py:79-120`, `api/smart_interpolation.py:316-351` |
| D3 | Drei Bucket-Loader: `_load_bucket_generic` (cache_interpolation), `_load_bucket` (smart_interpolation) und die Loader in `on_demand_computation`. | s. o. |
| D4 | Die Worker-Magnituden `20.0` (Asteroiden) und `14.0` (Kometen) stehen als Literale an mindestens vier Stellen. Sie gehören als Konstanten in `bright_asteroids` und `comets`. | `api/routes/asteroids.py:33`, `comets.py:32`, `api/smart_interpolation.py:413,442` |
| D5 | Die Körper-Symbole sind doppelt definiert (`BODY_SYMBOLS` in Python, `OBJECT_SYMBOLS` in JS, Kommentar „must match symbols in main.py“, das inzwischen falsch ist). Planetenmagnituden ebenso (`_DEFAULT_MAGNITUDES` und `ASTRO_CONSTANTS`). | `api/computation.py:29`, `static/js/constants.js:40` |
| D6 | Theme-Umschaltung: viermal derselbe Click-Handler (`theme-red/green/blue/amber`). Sprache: zweimal derselbe Handler. Datengetrieben wäre das eine Schleife. | `templates/index.html:192-258` |
| D7 | Der Hilfedialog enthält jeden Text zweimal, als `t('…')` und als deutschen Fallback-Literal. Die Fallbacks gehören in `i18n.js`. | `templates/index.html` |
| D8 | `isMobileDevice()` (UA-Sniffing plus Breite) bestimmt an vielen Stellen das Verhalten, neben separaten Maus- und Touch-Pfaden. Pointer Events würden beides zusammenführen. | `skyRenderer.js:749` u. a. |
| D9 | `if (settingsManager && typeof settingsManager.X === 'function')` kommt 9-mal in `index.html` (14-mal im gesamten Frontend) vor. `settingsManager` ist ein statisch importiertes Singleton, die Prüfungen sind überflüssig. | `templates/index.html`, `static/js/*.js` |

---

## 6. Widersprüche zum Bericht vom August 2026

- **N04 („wirkungslose `nocache`-Parameter entfernt“):** Das Frontend sendet weiterhin `&nocache=1` an `/api/celestial`, wo er ignoriert wird (`skyRenderer.js:2322`). `/api/celestial/sunpath` wertet `nocache` weiterhin aus (`api/routes/celestial.py:53`).
- **D04 („wirkungslose TTL-Argumente entfernt“):** Drei TTL-Konstanten sind noch definiert und unbenutzt (siehe Abschnitt 4).
- **„Vulture ≥ 80 %: keine Befunde“:** Die Schwelle verdeckt die per grep bestätigten 60-%-Treffer aus Abschnitt 4.
- **L14 („blockierende Aufrufe in async-Routen behoben“):** `resolve_magnitude_filter` und alle DB-Aufrufe in `api/routes/user_settings.py` sind übersehen worden (L12 hier).

---

## 7. Empfohlene Reihenfolge

1. `.venv` mit Python 3.15 neu aufbauen und die Testsuite laufen lassen. Das ist Voraussetzung für alles Weitere.
2. **Sicherheit zuerst:** S1 (`POST /api/filters` für Anonyme nicht global persistieren), S2/S3 (XSS in `auth.js` und `locationDialog.js`), S4 (Location-Validierung in `PUT /api/user/settings`), S5 (`https_only` in Produktion), S6/S7 (Login-Enumeration & Logout-`localStorage`).
3. **Kritische Worker-/Backend-Bugs:** L18 (Sunpath-Precomputation), L19 (Asteroid-Magnitude-Clamp im Worker), L21 (Poison-Pill-Requeue & unbekannte Tasks), L12 (blockierende DB-Aufrufe in `user_settings.py` & `helpers.py`), L15 (DST-Normalisierung), L22 (`time_bucket_utc`), L23/L24 (Auth/Admin), O17/O18 (doppelter DB-Write & RAM-Verdopplung).
4. **Kleine, klare Logikfehler:** L1 (Mondphase), L2 (Update-Supersede), L3 (Listener-Leck), L4, L6, L7, L16, L27–L31 (i18n, `LocationDialog`, `SunpathOverlay`, `ZodiacRenderer`, `visibleObjectsList`).
5. **Architekturentscheidungen:** Smart-Interpolation-Subsystem entfernen oder fertigstellen (L8–L11, L20, O6, D2, D3); Monitor-Subsystem (`worker_monitor.py` / `monitor_dashboard.py`, L26, S9) und `cleanup_task_files.py` reparieren oder entfernen.
6. **Backend-Performance:** O1–O5, O19 (Cache für Auf- und Untergänge, gemeinsame Ephemeriden-Berechnung, gecachtes `constellationship.fab`).
7. **Frontend-Umbau** gemäß [WEB_UI_PLAN_2026-11-25.md](WEB_UI_PLAN_2026-11-25.md). Er erledigt O10, O11, O13–O16, O20–O21, L5 und D6–D9 nebenbei.
8. Stilpunkte aus ruff (B904, B905) bei Gelegenheit.

---

## 8. Stand der Behebung (26.11.2026)

Entscheidungen: Smart-Interpolation- und Monitor-Subsystem **entfernt**; im Raster **Textsymbole**
(☉ ☾ ☄︎), Emojis nur in Liste und Detailansicht; UI-Umbau nach
[WEB_UI_PLAN_2026-11-25.md](WEB_UI_PLAN_2026-11-25.md).

### Backend: erledigt

| Befund | Behebung |
|---|---|
| S1 | Anonyme Filter liegen in der Session des Besuchers (`api/routes/filters.py`); die Server-Defaults ändern nur noch Datei/Admin. |
| S4 | `LocationPayload` (Breite ±90, Länge ±180, Höhe −500…9000, Name ≤ 120) und `MagnitudeFilters` (0…25) in `api/models.py`; `get_all_user_locations` liest nur numerische Werte. |
| S5 | `SessionMiddleware(..., same_site="lax", https_only=…)`, in Produktion standardmäßig `Secure` (`ASCII_SKY_HTTPS_ONLY`). |
| S6 | Login prüft immer ein Passwort (Dummy-Hash bei unbekanntem Namen), „deaktiviert“ erst nach richtigem Passwort; Ratenbegrenzung für Login (10/5 min je IP+Name) und Registrierung (5/h je IP); Benutzernamen-Regel. |
| S8 | Produktions-Guard gegen `changeme` (PostgreSQL, RabbitMQ), Compose-Dateien verlangen `POSTGRES_PASSWORD`/`RABBITMQ_PASSWORD`; Cache-Zeilen sind JSON statt `pickle` (alte Zeilen gelten als Fehlzugriff und werden neu berechnet). Die `.pkl`-DataFrames bleiben `pickle`: lokal vom Updater geschrieben, ein Wechsel auf Parquet bräuchte `pyarrow`. |
| S9, L26 | Monitor-Subsystem entfernt (`worker_monitor.py`, `monitor_dashboard.py`, Template, Compose-Blöcke, Status-/Health-Queue). |
| L1 | Acht Sektoren zu 45° (`moon_phase_name`). |
| L7, D1 | Gemeinsame Route `api/routes/small_bodies.py`; Schlüssel `comet_<Name>` ohne Index; Alias `/api/asteroids` entfernt. |
| L8–L11, L20, O6, D2, D3 | Smart-Interpolation, On-Demand, astronomische Korrekturen und Admin-API entfernt; ein Nearest-Bucket-Lader (`api/cache_interpolation.py`). |
| L12 | Filter- und Einstellungs-Zugriffe laufen per `asyncio.to_thread`. |
| L13, L19, D4 | Cache-Miss fordert `CACHE_MAX_MAGNITUDE = 20.0` an; Worker und Coordinator rechnen bis dorthin, die API filtert je Anfrage. |
| L14 | Transit aus `almanac.meridian_transits` (oberer Transit), auch für zirkumpolare Körper. |
| L15 | Tagesfenster enden an der nächsten lokalen Mitternacht; `SUNPATH_VERSION = 6` verwirft alte Kurven. |
| L18 | Jahres-Sonnenbahn wird im ersten Horizont-Durchlauf vorberechnet. |
| L21 | Nicht dekodierbare Nachrichten und zweite Fehlschläge gehen in `computation.dead`, Claims werden freigegeben; unbekannte Arten sind Fehler. |
| L22 | `time_bucket_utc` rechnet Zeitzonen nach UTC um. |
| L23 | Login per E-Mail ohne Groß-/Kleinschreibung. |
| L24 | Kein Entzug der eigenen Admin-Rechte, kein Entfernen/Deaktivieren/Herabstufen des letzten aktiven Admins (gesperrte Zeilen, `FOR UPDATE`). |
| L25 | Sperren für `zodiac.init_skyfield` und den `TimezoneFinder`. |
| O1–O4 | Auf-/Unter-/Transitzeiten je Ort, lokalem Tag und Körper im LRU (4096); Erd- und Beobachterposition einmal je Schnappschuss; Mondphase einmal; `/celestial/{body}` rechnet nur diesen Körper. |
| O5 | Oberer Transit per Ereignistyp (`computation.py`, `messier.py`). |
| O8, O9 | Publisher verarbeitet Heartbeats bei Wiederverwendung, verbindet bei toter Verbindung einmal neu; Queues werden je Thread-Verbindung einmal deklariert. |
| O17, O18 | Worker speichert jeden Bucket einmal; keine zweite DataFrame-Kopie für eine Logzeile. |
| O19 | Sternbild-Figuren und Hipparcos einmal je Prozess; alle Sterne in einem vektorisierten `observe`. |
| Toter Code (Python) | Entfernt wie in Abschnitt 4 gelistet, dazu `get_memory_usage`, `get_database_stats`, Message-ID-Funktionen, `DE421_PATH`/`HIPPARCOS_MAIN_PATH`, `RABBITMQ_ENABLED`-Flags, Env-Variablen in `.env*.example`, Compose und Skripten. |

Tests: `test_fixes_2026_11.py` hält die Behebungen fest; die Suite läuft ohne PostgreSQL/RabbitMQ
(die Integrationstests überspringen dann).

**Betriebshinweise:** Alte Cache-Zeilen im `pickle`-Format und Sonnenbahnen der Version 5 werden
beim ersten Zugriff neu berechnet. Bestehende Broker können noch die Queues `computation.status`
und `worker.health` mit liegengebliebenen Nachrichten halten; sie haben keinen Verbraucher mehr und
können gelöscht werden. Produktion startet nur noch mit gesetztem `POSTGRES_PASSWORD`,
`RABBITMQ_PASSWORD` und `ASCII_SKY_SESSION_SECRET`.

### Frontend

Das Frontend ist nach `doc/WEB_UI_PLAN_2026-11-25.md` neu aufgebaut (Phasen P1 bis P6). Die alten
Module `skyRenderer.js`, `skyManager.js`, `visibleObjectsList.js`, `zodiacRenderer.js`,
`messierRenderer.js`, `sunpathOverlay.js` und die 14 Einzel-Stylesheets sind entfernt.

| # | Behebung |
|---|---|
| S2, S3, L17 | Alle Texte aus API, Nominatim und Benutzernamen gehen als Textknoten ins DOM; im Frontend gibt es kein `innerHTML` mehr (Test). |
| S7 | Ab- und Anmelden leeren die lokal gespeicherten Einstellungen (`settingsManager.resetLocal()`). |
| S8 (UI) | Admin-Passwort über einen `<dialog>` mit Passwortfeld statt `window.prompt`; Serverfehler (letzter Admin, eigene Rechte) werden angezeigt. |
| L2 | `SkyData.update()` bricht das laufende Update per `AbortController` ab; drei schnelle Klicks auf „+1 h“ erzeugen eine Anfrage mit der letzten Zeit. |
| L3, L6, O10 | Persistentes DOM: `render()` setzt nur Text und SVG-Inhalte, einmal pro Frame; keine Listener pro Render, ein Zähler. |
| L4 | Richtungsbuchstaben kommen aus der Beschriftung der aktuellen Sprache (Test mit „E“). |
| L5 | Im Raster nur einspaltige Textsymbole (☉ ☾ ☄︎); jedes Symbol steht zusätzlich in einer Zelle fester Breite. Emojis nur in Liste und Detailpanel. |
| L16 | Fehler zeigen einen Hinweisbalken mit „Erneut versuchen“, das letzte Bild bleibt. |
| L27, L28 | `t()` prüft auf `undefined`; DE und EN haben dieselben Schlüssel (Test); Auth-, Filter- und Hilfetexte nur aus `i18n.js` (D7). |
| L29 | Ein Suchergebnis holt die Höhe genau einmal und übernimmt dann; Antworten nach dem Schließen werden verworfen. |
| L30 | Sonnenbahn-Daten als lokales Datum geparst; In-Flight-Schutz; Jahr der angezeigten (simulierten) Zeit. |
| L31 | Sternbildlinien über die 0°/360°-Naht werden an beiden Rändern gezeichnet, nur in der Horizontansicht mit 360°; die Liste prüft Magnituden. |
| O11 | `DEBUG` standardmäßig aus (`?debug=1`). |
| O13 | Kein Aktualisieren in Hintergrund-Tabs, sofortiges Update beim Zurückkehren. |
| O14, O15 | Statische Imports; Start in fester Reihenfolge ohne `setTimeout`. |
| O16 | `ResizeObserver` und Schriftgröße aus der verfügbaren Fläche. |
| O20 | Dialoge laden kein CSS nach; Messier-Detail-Cache auf 64 Einträge begrenzt. |
| O21 | Ein Listener für das ganze Sonnenbahn-Diagramm. |
| P4 (Ziele) | Auf Telefonen sind alle Knöpfe der Zeitleiste mindestens so groß wie `--tap` (44 px bei Touch). „Jetzt“ (⟳) erscheint dort nur in simulierter Zeit und ersetzt dann das SIM-Abzeichen; bei 360 px Breite läuft nichts über. |
| D6, D8, D9 | Ein datengetriebener Theme-Umschalter; Pointer Events statt UA-Erkennung; keine Existenzprüfungen des Singletons. |

**Bewusst nicht umgesetzt: O12.** Die Kleinkörper-Antwort hängt vom Magnitudenfilter der Sitzung ab, und ohne
simulierte Zeit trägt die URL keinen Zeitparameter. Ein `Cache-Control: max-age` würde nach einer Filteränderung
oder im Echtzeitmodus veraltete Antworten liefern; ein Cache-Fehlschlag (leere Liste, Berechnung angestoßen) darf
ohnehin nicht gecacht werden. Der Gewinn stünde in keinem Verhältnis dazu. Das neue Frontend lädt mit dem
Standardverhalten des Browsers, ohne `no-store`.

**Darstellung:** Bei 360° zeichnen Horizont und Planisphäre zeichengenau dasselbe Raster wie
vorher (Referenz `test_fixtures/sky_grid_reference.json`, Test `test_sky_grid_matches_previous_renderer`).
Die vier Farbthemen sind `:root[data-theme]`-Token mit Kontrast ≥ 4,5 : 1 (Test); Rot bleibt
durchgehend rot. `user-scalable=no` ist entfernt, `theme-color` wird mitgesetzt.

**Entscheidungen aus dem UI-Plan:** Telefone (Hoch- und Querformat) starten mit 120° Sichtfeld,
Desktop mit 360°. Die Planeten-Knöpfe gehen in der Objektliste auf (Sonne, Mond und Planeten stehen
immer in der Liste, ein Klick wählt aus und schwenkt dorthin). Kein Web-App-Manifest.

**Nebenbei behoben:** `/api/celestial/sunpath` antwortete mit 500, wenn PostgreSQL nicht
erreichbar war; das Lesen des Caches ist jetzt wie das Schreiben „best effort“. Die unbenutzten
Sternbildfarben in `/api/config` sind entfernt.

**Geprüft:** pytest (106 bestanden, 2 übersprungen), Chrome mit 1280 px Breite sowie 375 × 780 und
780 × 375 (als eingebettete Frames), Themen Grün, Rot und Blau, Deutsch und Englisch. **Nicht
geprüft:** ein echtes Telefon (Touch-Gesten, Pinch, Safe Areas); die Gesten wurden nur mit der
Maus ausgelöst.
