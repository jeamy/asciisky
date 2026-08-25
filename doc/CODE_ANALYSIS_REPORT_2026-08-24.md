# Codeanalyse AsciiSky

**Stand:** 24. August 2026  
**Untersuchter Stand:** aktueller lokaler Arbeitsbaum  
**Ziel:** Logikfehler, Performancepotenziale, duplizierter und toter Code

## Umsetzungsstatus und erneute Analyse

**Aktualisiert:** 24. August 2026 nach der Umsetzung aller priorisierten
Korrekturen dieses Berichts. Die folgenden Status beziehen sich auf die
nachfolgende Codeprüfung, nicht auf die historische Bestandsaufnahme weiter
unten.

| Befund | Status | Umsetzung / Verifikation |
|---|---|---|
| L01 | Erledigt | Zwei-Argument-Loader, gültige leere Listen und gezieltes Fehlerhandling; Regressionstest vorhanden. |
| L02–L03 | Erledigt | API-No-op-Locks entfernt; persistente, atomare Claims sind die einheitliche Publish-Koordination. Der Worker verwendet einen realen Advisory-Lock mit DB-Timeout. |
| L04 | Erledigt | Worker prüft atomisch ersetzte DataFrame-Dateien auf geänderte `mtime` und lädt sie kontrolliert neu. |
| L05 | Erledigt | `None` bedeutet Cache-Miss, `[]` ist ein erfolgreicher Cacheeintrag – in Loadern, Routen und Workern. |
| L06 | Erledigt | Einheitlicher Retry, Claim-Freigabe und persistente `computation.dead`-Queue statt Verwerfen bzw. Endlosschleife. |
| L07–L08 | Erledigt | Strikter ISO-Parser (Offset → UTC, ungültig → 422), `HTTPException` wird nicht maskiert; defekter Zodiac-Fallback entfernt. |
| L09 | Erledigt | Eine zentrale Interpolationskonfiguration, stabiler SHA-256-Rollout, geschützte und registrierte Adminroute. |
| L10 | Erledigt | On-Demand-Publisher erzeugt ein validiertes `type=on_demand`; `cached` gilt im Worker als Erfolg. |
| L11–L12 | Erledigt | Adminrechte werden pro Request gegen die DB geprüft; produktiver Start verlangt ein Secret; die erste Adminregistrierung wird unter DB-Lock serialisiert. |
| L13 | Erledigt | Mondhelligkeit ist für die Neumondphase endlich und monoton statt diskontinuierlich. |
| L14–L15 | Erledigt | CPU-/DB-lastige Routen und Sunpath-Hintergrundarbeit werden in Threads ausgeführt; Sunpath-Tasks werden gecacht, per Claim dedupliziert und verfolgt. |
| L16–L17 | Erledigt | DDL wurde aus dem Claim-Hot-Path entfernt; veraltete DataFrames ergeben einen expliziten Miss statt unbemerkt veralteter Berechnung. |
| L18–L19 | Erledigt | RabbitMQ Publisher Confirms mit Claim-Rollback; JSON-Einstellungen sind gelockt, tief kopiert und atomisch geschrieben. GET-Routen ändern keinen Standort mehr. |
| L20–L21 | Erledigt | Einmalige Frontend-Initialisierung, bedarfsgeladener Zodiac-Layer, produktionsgerechtes Revalidieren statischer Dateien und lazy Hipparcos-Initialisierung. |
| L22 | Erledigt für die fehlerrelevanten Pfade | Cache-, Zodiac-, Worker- und API-Grenzen fangen keine Programmierfehler mehr stillschweigend ab. Übrige breite Fänge sind überwiegend bewusst defensive Infrastrukturgrenzen und sind in der Reanalyse dokumentiert. |
| D01 | Erledigt | Gemeinsamer Positionsspeicher, gemeinsamer Task-Publisher und nur noch eine Worker-Implementierung; `precompute_worker.py` ist ein kompatibler Starter. |
| D02 | Risiko reduziert | Die rechenintensiven Funktionen laufen außerhalb des ASGI-Eventloops. Ihre fachliche Zerlegung ist ein wartbarkeitsorientiertes Folge-Refactoring, kein verbleibender Funktionsfehler. |
| D03 | Erledigt | Nicht registrierte/defekte Konfiguration, No-op-Frontend, unbenutzte Helfer, Modelltypen und Legacy-Skripte entfernt oder als eindeutige Kompatibilitätsschicht ersetzt. |
| D04 | Erledigt | Wirkungslose TTL-Argumente aus dem Positions-Cachepfad entfernt; TTL ist nur noch bei tatsächlichen Cache-/Claim-Strategien vorhanden. |
| T01–T04 | Erledigt | Pytest-Assertions statt Rückgabewerten, `integration`-Marker, zwei DB-Sitzungen im Lock-Test, ausführbare Hilfsskripte nach `scripts/` verschoben und neue Regressionstests ergänzt. |

### Abschlussprüfung

| Prüfung | Ergebnis |
|---|---|
| Python-Kompilierung | erfolgreich (`compileall`) |
| JavaScript-Syntax | erfolgreich (`node --check`) |
| Test-Suite | **26 bestanden, 2 übersprungen** |
| Compose-Konfiguration (lokal + Produktion) | erfolgreich validiert; Produktion verlangt `SESSION_SECRET` |
| `git diff --check` | erfolgreich |
| Vulture (Konfidenz ≥ 80 %) | keine unbenutzten Codeelemente gemeldet |
| Kritische Ruff-Regeln (undefinierter Name / einfache Strukturfehler) | keine Befunde |

Die zwei übersprungenen Tests sind korrekt markierte Infrastrukturtests für
PostgreSQL/RabbitMQ und benötigen laufende Dienste. Damit sind die
Implementierungen statisch und unit-seitig geprüft; die dynamische Broker- und
DB-Interaktion ist beim nächsten Staging-Deployment auszuführen.

### Ergebnis der erneuten Analyse

Es wurden keine neuen reproduzierbaren Logikfehler, Syntaxfehler, tote
Produktionselemente oder undefinierten Namen gefunden. Ruff meldet weiterhin
338 allgemeine Stilhinweise, vor allem breite Exception-Grenzen in optionalen
Netzwerk-, Monitoring- und Shutdown-Pfaden. Diese sind kein automatischer
Funktionsfehler; sie bleiben als separater, risikoarmer Stilbereinigungspunkt
bewusst außerhalb dieses funktionalen Fix-Pakets.

> Hinweis: Die folgenden Abschnitte dokumentieren den Befund **vor** der
> Umsetzung und bleiben zur Nachvollziehbarkeit unverändert.

## Kurzfazit

Der Code ist syntaktisch konsistent und die lokal ausführbaren Tests laufen größtenteils erfolgreich. Die größten Risiken liegen jedoch in den Cache- und Workerpfaden: Ein Fallback-Loader ist durch eine falsche Funktionssignatur wirkungslos, API-seitige Berechnungssperren werden nicht betreten, Worker können nach einem nächtlichen Datenupdate mit veralteten Quelldaten weiterrechnen und mehrere Fehlerpfade führen zu verlorenen oder endlos wiederholten Nachrichten.

Die dringendsten Korrekturen sind:

1. Cache-Fallback und Lock-Verwendung reparieren.
2. Worker-Retry/DLQ, leere gültige Ergebnisse und Task-Claims konsistent behandeln.
3. Datenaktualisierung mit laufenden Workern synchronisieren.
4. Zeitparameter und Zodiac-Fehlerbehandlung vereinheitlichen.
5. Admin-/Interpolation-Konfiguration auf einen tatsächlich verwendeten, geschützten Pfad reduzieren.

## Umfang und Prüfverfahren

Analysiert wurden 73 versionierte Python-, JavaScript- und Shell-Dateien mit insgesamt ungefähr 22.200 Zeilen. Verwendet wurden:

- manuelle Ablauf- und Datenflussanalyse;
- Python-Kompilierung mit `compileall`;
- JavaScript-Syntaxprüfung mit `node --check`;
- `pytest` in der lokalen `.venv`;
- `ruff` für statische Fehler und Wartbarkeitsindikatoren;
- `radon` für zyklomatische Komplexität;
- `jscpd` für duplizierte Blöcke;
- `vulture` plus Referenzsuche für Kandidaten auf toten Code.

Die zusätzlich benötigten Analysewerkzeuge wurden ausschließlich in der lokalen `.venv` beziehungsweise temporär über `npx` verwendet. Dieser Absatz beschreibt den ursprünglichen Auditstand vor der späteren Umsetzung.

## Testergebnisse

| Prüfung | Ergebnis | Einordnung |
|---|---:|---|
| `python -m compileall -q .` | erfolgreich | keine Python-Syntaxfehler |
| `node --check` für `static/js/**/*.js` | erfolgreich | keine JavaScript-Syntaxfehler |
| `.venv/bin/pytest -q` | 19 bestanden, 1 fehlgeschlagen | Fehlschlag wegen nicht laufendem PostgreSQL auf `127.0.0.1:5432` |
| Pytest-Warnungen | 1.613 | überwiegend Skyfield/NumPy-Abkündigungen; zusätzlich drei Tests, die Werte zurückgeben |
| `ruff` | 884 Hinweise | darunter 204 sehr breite Exceptions, 66 unbenutzte Imports und ein undefinierter Name |
| `jscpd` | 25 Klone, 328 Zeilen | 1,61 % duplizierte Zeilen im analysierten Python-/JavaScript-Code |
| `git diff --check` | erfolgreich | keine Whitespace-Fehler |

Der einzelne Pytest-Fehlschlag beweist keinen Produktfehler: Der Test `test_advisory_locks` ist ein unmarkierter Integrationstest und benötigt PostgreSQL. RabbitMQ-, echte Parallelitäts- und End-to-End-Workerpfade konnten ohne laufende Infrastruktur nicht vollständig dynamisch geprüft werden.

## Priorisierte Befunde

### P1 – hohe Priorität

#### L01 – Cache-Fallback ruft Loader mit falscher Signatur auf

**Fundstellen:** `api/cache_interpolation.py:33`, `api/cache_interpolation.py:36-37`, `db_utils.py:161`, `db_utils.py:360`

`_load_bucket_generic()` ruft den übergebenen Loader mit drei Argumenten auf:

```python
loader_func(location_key, bucket, ttl_seconds)
```

`get_asteroid_positions()` und `get_comet_positions()` akzeptieren jedoch nur `location_key` und `time_bucket`. Der resultierende `TypeError` wird durch `except Exception: pass` verborgen. Damit liefert die dokumentierte Suche nach benachbarten Buckets immer einen Cache-Miss. Ein isolierter Aufruf mit einem Zwei-Argument-Loader reproduzierte den Fehler: Ergebnis `None`, Loader nie erfolgreich ausgeführt.

**Auswirkung:** Fallback-/Rollback-Verhalten funktioniert nicht; vermeidbare Neuberechnungen und leere API-Antworten sind möglich.

**Empfehlung:** Funktionssignaturen vereinheitlichen, den ungenutzten TTL-Parameter entfernen oder explizit implementieren und nur erwartete Datenbankfehler abfangen. Dazu Unit-Tests für exakten Treffer, Nachbar-Bucket und Datenbankfehler ergänzen.

#### L02 – API-seitige Berechnungssperren werden nicht erworben

**Fundstellen:** `api/routes/asteroids.py:166-176`, `api/routes/comets.py:166-176`, `db_utils.py:683-710`, `workers/unified_worker.py:343`, `workers/precompute_worker.py:132`

`computation_lock()` ist ein Context Manager, wird in beiden Routen aber wie eine normale Funktion aufgerufen. Ohne `with computation_lock(...):` wird sein Körper nicht ausgeführt und keine Advisory Lock erworben. Zusätzlich verwenden API und Worker verschiedene Schlüssel (`computing:...` gegenüber `precompute_{kind}:...`). Selbst nach dem Einfügen von `with` würden sie sich daher nicht gegenseitig sehen.

**Auswirkung:** Die vermeintliche "läuft bereits"-Koordination ist wirkungslos. Persistente Task-Claims reduzieren Duplikate teilweise, ersetzen aber die dokumentierte Lock-Semantik nicht vollständig.

**Empfehlung:** Eine einzige atomare Claim-/Lock-Abstraktion mit identischem Schlüssel für API und Worker verwenden. Die Route sollte das Ergebnis des Claims prüfen und erst danach publizieren.

#### L03 – Das dokumentierte Lock-TTL existiert technisch nicht

**Fundstelle:** `db_utils.py:683-710`

Der Parameter `ttl_seconds` wird nur in einer `pg_notify`-Nachricht erwähnt. Es existiert kein Listener oder Timer, der die Session-Lock nach Ablauf freigibt. Zugleich wird blockierendes `pg_advisory_lock` statt `pg_try_advisory_lock` verwendet.

**Auswirkung:** Ein doppelter Worker kann einen Consumer bis zum Ende der ersten Berechnung blockieren. Bei festhängender Verbindung stimmt die dokumentierte Fünf-Minuten-Grenze nicht mit dem Verhalten überein.

**Empfehlung:** Nicht blockierenden Try-Lock oder transaktionsgebundene Advisory Locks verwenden; Timeout über Datenbank-Statement-Timeout beziehungsweise explizite Claim-Ablaufzeit erzwingen. Kommentare und API danach an das reale Verhalten anpassen.

#### L04 – Nächtliche Quelldatenupdates erreichen laufende Worker nicht

**Fundstellen:** `workers/worker_utils.py:312-382`, `nightly_data_updater.py:259-267`, `nightly_data_updater.py:326-332`, `comets.py:100`

Asteroiden- und Kometen-DataFrames werden beim Workerstart in `SharedSkyfieldResources` geladen und dauerhaft gehalten. Der Nightly-Updater ersetzt Dateien und invalidiert Positionscaches, signalisiert den Workern aber keinen Reload. `clear_in_memory_cache()` besitzt keine Aufrufer und betrifft nicht alle langlebigen Workerreferenzen.

**Auswirkung:** Nach erfolgreichem Update können neue Positionen bis zum nächsten Worker-Neustart wieder aus alten Bahndaten berechnet und gespeichert werden.

**Empfehlung:** Datensatzversion in Datenbank oder Message mitführen. Worker müssen bei Versionswechsel atomar neu laden oder nach einem erfolgreichen Update kontrolliert neu gestartet werden. Readiness sollte Versionsgleichheit prüfen.

#### L05 – Gültige leere Ergebnisse werden wie Fehler behandelt

**Fundstellen:** `workers/unified_worker.py:380-405`, `workers/precompute_worker.py`, `bright_asteroids.py:458-475`, `comets.py:833-842`

Die Berechnungsfunktionen können eine gültige leere Liste speichern. Routen und Worker prüfen Treffer jedoch über Truthiness (`if cached_positions`, `if not positions`). Eine vorhandene leere Ergebnisliste ist dadurch nicht von "kein Cacheeintrag" unterscheidbar. Der Worker meldet Fehler beziehungsweise wiederholt die Berechnung.

**Auswirkung:** Standorte/Zeiten ohne Treffer können dauerhafte Neuberechnungen oder Retry-Schleifen auslösen.

**Empfehlung:** Cacheexistenz getrennt vom Nutzwert modellieren (`None` = fehlt, `[]` = gültig leer). Workererfolg darf nicht von der Länge des Ergebnisses abhängen.

#### L06 – Retry-/DLQ-Semantik verliert oder wiederholt Nachrichten falsch

**Fundstellen:** `workers/unified_worker.py:557-569`, `workers/precompute_worker.py:266-273`, `workers/worker_utils.py:227-253`

Der Unified Worker protokolliert nach dem letzten Versuch eine Verschiebung in die DLQ, die Queues werden aber ohne Dead-Letter-Exchange deklariert. `basic_nack(requeue=False)` verwirft die Nachricht daher. Der dedizierte Precompute Worker verwendet dagegen bei Fehlern immer `requeue=True`, wodurch permanente Fehler als heiße Endlosschleife wiederkehren können. Fehlgeschlagene Task-Claims werden nicht unmittelbar freigegeben und können bis zu 24 Stunden bestehen bleiben.

**Auswirkung:** Aufgaben gehen unbemerkt verloren oder belasten Broker und Worker unbegrenzt; Claims verhindern anschließend Ersatzaufgaben.

**Empfehlung:** Gemeinsame Retry-Policy mit Zähler, Backoff, echter DLX/DLQ und klarer Claim-Freigabe einführen. Das Verhalten mit RabbitMQ-Integrationstests prüfen.

#### L07 – Zodiac-Zeitverarbeitung verändert Zeitpunkte und maskiert Clientfehler

**Fundstellen:** `api/routes/zodiac.py:203-221`, `api/helpers.py:7-21`

Ein ISO-Zeitwert mit Offset wird geparst und anschließend über `.replace(tzinfo=UTC)` als UTC umetikettiert, statt in UTC konvertiert zu werden. Beispiel: `12:00+02:00` wird zu `12:00Z` statt `10:00Z`. Außerdem wird eine für ungültige Eingaben erzeugte `HTTPException(400)` vom äußeren `except Exception` abgefangen und als 500 zurückgegeben.

Die gemeinsame Funktion `parse_time_param()` hat das entgegengesetzte, ebenfalls problematische Verhalten: Sie ersetzt ungültige Eingaben still durch die aktuelle Uhrzeit und antwortet erfolgreich.

**Auswirkung:** Astronomische Ergebnisse können für einen anderen Zeitpunkt berechnet werden, während der Client keine verlässliche Fehlermeldung erhält.

**Empfehlung:** Einen einzigen strikten Parser verwenden: naive Zeiten nach dokumentierter Regel behandeln, Offsetzeiten mit `astimezone(timezone.utc)` konvertieren und ungültige Werte als 422/400 weiterreichen.

#### L08 – Zodiac-Fallback enthält einen undefinierten Namen

**Fundstellen:** `api/routes/zodiac.py:97-107`

`KNOWN_STAR_COORDINATES` wird verwendet, aber nirgendwo definiert oder importiert (`ruff` F821). Die umgebende breite Exception fängt den `NameError` ab und gibt `None` zurück.

**Auswirkung:** Der vorgesehene Fallback für Sternkoordinaten funktioniert nie; der Fehler bleibt im regulären Ablauf unsichtbar.

**Empfehlung:** Konstante korrekt bereitstellen oder den nicht funktionsfähigen Fallback entfernen. Anschließend einen Test erzwingen, der genau diesen Zweig ausführt.

#### L09 – Zwei unabhängige Interpolationskonfigurationen widersprechen sich

**Fundstellen:** `config/interpolation_config.py`, `api/smart_interpolation.py:40-64`, `api/routes/interpolation_admin.py`, `main.py`

Es existieren zwei eigene Enums, Konfigurationsobjekte und Singletons. Die Standardwerte unterscheiden sich (`nearest` gegenüber `smart`). Die Adminroute verändert nur die Konfiguration aus `config/`, während die Berechnung die lokale Konfiguration in `api/smart_interpolation.py` nutzt. Zusätzlich wird `interpolation_admin` in `main.py` nicht registriert; der gesamte HTTP-Administrationspfad ist daher unerreichbar. Würde er registriert, fehlen ihm derzeit Authentifizierungs-/Adminprüfungen.

`config/interpolation_config.py:164` verwendet außerdem den pro Python-Prozess randomisierten eingebauten `hash()` für Rollout-Zuordnung. Bei weniger als 100 % können Benutzer nach Neustart oder zwischen Replikas die Gruppe wechseln.

**Auswirkung:** Laufzeitänderungen wirken nicht auf die Berechnung; Rollouts sind inkonsistent; ein späteres bloßes Aktivieren der Route wäre ein Sicherheitsrisiko.

**Empfehlung:** Nur ein Konfigurationsmodell und eine Quelle der Wahrheit behalten. Stabiles Hashing, persistente Konfiguration und Authentifizierung ergänzen, bevor die Adminroute registriert wird.

#### L10 – On-Demand-Aufgaben sind nicht mit dem Unified Worker kompatibel

**Fundstellen:** `api/on_demand_computation.py:378-391`, `workers/unified_worker.py:239`, `workers/unified_worker.py:304-309`, `workers/unified_worker.py:467`

Der On-Demand-Service publiziert Taskdaten ohne Feld `type`. Der Unified Worker interpretiert fehlenden Typ als Precompute-Task und verwirft ihn anschließend wegen des ebenfalls fehlenden Feldes `kind`. Zudem wird `ComputationStatus.CACHED` nicht als Erfolg behandelt; bereits vorhandene Ergebnisse führen damit zu NACK/Retry. Der Hintergrundpfad publiziert teils sogar denselben Bucket erneut, den er gerade berechnet hat.

**Auswirkung:** Der vorhandene On-Demand-Workerpfad ist latent defekt oder erzeugt redundante Arbeit.

**Empfehlung:** Ein versioniertes, validiertes Task-Schema für Publisher und Consumer verwenden. `SUCCESS` und `CACHED` als erfolgreiche Abschlüsse behandeln; Selbst-Republication entfernen.

#### L11 – Adminrechte bleiben in bestehenden Sessions erhalten

**Fundstellen:** `api/routes/admin_users.py:14-23`, `api/routes/auth.py`, `main.py:37`

`_require_admin()` vertraut ausschließlich dem Cookiewert `user_is_admin`. Nach Entzug der Adminrolle oder Deaktivierung des Kontos bleiben Adminendpunkte bis zum Sessionwechsel zugänglich. Die Datenbank wird nicht erneut geprüft. Zusätzlich fällt die Session-Middleware ohne Umgebungsvariable auf den bekannten Schlüssel `dev-secret-please-change` zurück.

**Auswirkung:** Rollenentzug wirkt nicht sofort; eine Produktion ohne gesetztes Secret erlaubt potenziell gefälschte signierte Sessions.

**Empfehlung:** Adminstatus für privilegierte Aktionen serverseitig prüfen oder Sessions versionieren/revozieren. Anwendung in Nicht-Entwicklungsumgebungen ohne starkes Secret beim Start hart abbrechen.

#### L12 – Erster Administrator wird nicht atomar bestimmt

**Fundstelle:** `api/routes/auth.py:139-163`

Die Registrierung zählt zuerst Benutzer und führt danach separat das Insert aus. Zwei parallele Erstregistrierungen können beide `COUNT(*) == 0` beobachten und beide Admin werden.

**Auswirkung:** Seltenes, aber sicherheitsrelevantes Bootstrap-Rennen.

**Empfehlung:** Bootstrap in einer serialisierbaren Transaktion beziehungsweise unter DB-Lock durchführen oder den ersten Admin explizit per Deployment anlegen.

### P2 – mittlere Priorität

#### L13 – Mondhelligkeit ist bei Neumond diskontinuierlich

**Fundstelle:** `api/computation.py:70-74`

Für exakt `phase_factor == 0` wird die Vollmondhelligkeit `-12.7` gesetzt. Unmittelbar neben null wird dagegen eine sehr schwache Magnitude berechnet. Das erzeugt eine physikalisch falsche Diskontinuität.

**Empfehlung:** Robustes photometrisches Modell beziehungsweise klar begrenzten Phasenfaktor verwenden; null darf nicht auf Vollmondhelligkeit fallen.

#### L14 – Synchroner CPU- und Datenbankcode blockiert den Async-Eventloop

**Fundstellen:** `api/routes/celestial.py:15-27`, `api/routes/messier.py`, mehrere `async def`-Routen und `db_utils.py`

Mehrere asynchrone Routen führen synchrone psycopg-Abfragen und teure Skyfield-Berechnungen direkt aus. `compute_celestial_snapshot()` berechnet unter anderem Auf-/Untergänge für mehrere Körper. Ein kalter Messier-Detailaufruf kann Almanachberechnungen für einen großen Teil des Katalogs durchführen. Währenddessen kann der betroffene Eventloop keine anderen Requests bearbeiten.

**Empfehlung:** Reine synchrone Routen als normale `def` ausführen lassen oder CPU-Arbeit gezielt in Threads/Prozesse/Worker verschieben. Für die Datenbank einen Async-Pool oder konsequente Thread-Auslagerung verwenden. Latenz und Eventloop-Lag messen.

#### L15 – Standortänderungen starten ungedrosselte Hintergrundberechnungen

**Fundstelle:** `api/routes/session.py`

Nach jedem Setzen eines Standorts wird mit `asyncio.create_task` eine neue Jahres-Sonnenpfadberechnung gestartet. Die Task wird nicht verwaltet, nicht dedupliziert und prüft vor der Berechnung keinen bestehenden Cache/Claim. Wiederholte POSTs können deshalb parallele CPU-Last erzeugen; Fehler und Shutdown-Verhalten sind schwer beobachtbar.

**Empfehlung:** Cache-/Claim-Prüfung voranstellen und die Arbeit über den vorhandenen Workerpfad abwickeln. Wenn lokale Tasks bleiben, Lifecycle und Fehler explizit verfolgen.

#### L16 – Datenbankzugriffe erzeugen vermeidbare Kosten

**Fundstellen:** `db_utils.py:452-486` und allgemeiner DB-Helferpfad

`CREATE TABLE IF NOT EXISTS` wird bei jedem Claim und Release erneut ausgeführt, obwohl die Tabelle beim Schemaaufbau angelegt werden kann. Auch reine Lesevorgänge beenden häufig mit `commit`. Verbindungen werden über Thread-Local statt über einen Pool verwaltet und in Async-Routen synchron verwendet.

**Empfehlung:** DDL ausschließlich in Migration/Initialisierung verschieben, Read-Only-Transaktionen vermeiden und einen Pool mit klarer Transaktionsgrenze einsetzen.

#### L17 – Veraltete Quelldaten gelten weiterhin als gültig

**Fundstellen:** `db_utils.py:124-132`, `db_utils.py:302-310`

Die Loader warnen bei Überschreiten des maximalen Datenalters, liefern die serialisierten Daten aber unverändert zurück. Readiness/Verbraucher können damit nicht zwischen frisch und veraltet unterscheiden.

**Empfehlung:** Datenalter als expliziten Status zurückgeben und je nach Betriebsmodus entweder hart ablehnen, degradiert melden oder kontrolliert weiterverwenden.

#### L18 – Taskpublikation besitzt keine belastbare Zustellbestätigung

**Fundstellen:** `api/rabbitmq/task_publisher.py`, `api/precompute_coordinator.py`

Der persistente Claim wird vor dem Publish angelegt, Publisher Confirms sind aber nicht sichtbar aktiviert. Ein Verbindungsabbruch kann damit einen Claim ohne tatsächlich zugestellte Nachricht hinterlassen.

**Empfehlung:** Publisher Confirms oder Outbox-Muster verwenden und bei negativem/unklarem Publish-Ergebnis den Claim freigeben beziehungsweise zuverlässig erneut zustellen.

#### L19 – Globale JSON-Einstellungen sind nicht nebenläufigkeitssicher

**Fundstellen:** `settings.py`, `api/routes/asteroids.py:108-116`, `api/routes/comets.py:108-116`

Eine globale mutable Struktur und `user_settings.json` werden ohne Lock und ohne atomaren Dateiaustausch gelesen/geschrieben. `DEFAULT_SETTINGS.copy()` ist nur flach, wodurch verschachtelte Werte geteilt werden können. Zusätzlich können GET-Routen über `save_location` globalen Zustand verändern.

**Auswirkung:** Parallele Requests können Einstellungen verlieren oder die Datei beschädigen; anonyme Nutzer beeinflussen potenziell denselben Defaultzustand.

**Empfehlung:** Pro Benutzer/Session speichern, atomar schreiben oder Datenbank verwenden, Deep Copy beziehungsweise immutable Defaults nutzen und GET-Endpunkte ohne Seiteneffekt halten.

#### L20 – Frontend erzeugt vermeidbare Initial- und Periodiklast

**Fundstellen:** `static/js/skyRenderer.js:97`, `static/js/skyRenderer.js:2442-2444`, `templates/index.html:177-189`, `main.py:42-53`

Der Renderer startet im Konstruktor ein Update; die verzögerte Standortinitialisierung löst kurz darauf häufig ein zweites vollständiges Update aus. Zodiac-Daten werden danach bei jedem 60-Sekunden-Zyklus geladen, auch wenn die Darstellung nicht sichtbar ist. JavaScript- und CSS-Antworten werden global mit deaktiviertem Browsercache ausgeliefert, laut Kommentar für schnelle Entwicklung.

**Empfehlung:** Initialisierung genau einmal orchestrieren, optionale Layer nur bei Sichtbarkeit/Änderung laden und No-Cache ausschließlich im Entwicklungsmodus setzen. In Produktion gehashte Assets mit langem Cache verwenden.

#### L21 – Hipparcos-Initialisierung liegt im Modulimport

**Fundstelle:** `api/routes/zodiac.py`

`init_skyfield()` wird beim Import der Route ausgeführt und kann Katalog-/Dateizugriffe verursachen. Das verlängert und fragilisiert den Prozessstart; ein externer Datenfehler betrifft das Laden des gesamten Moduls.

**Empfehlung:** Explizite Startup-Initialisierung mit Timeout, lokalem Artefakt und Health-Status verwenden; schwere Daten lazy beziehungsweise kontrolliert vorladen.

#### L22 – Breite Exceptions verbergen reale Defekte

`ruff` fand 204 Vorkommen von `except Exception` und 33 leere `pass`-Zweige. Nicht jedes Vorkommen ist falsch, aber L01 und L08 zeigen den praktischen Effekt: Programmierfehler werden als normaler Cache-Miss oder fehlende Daten ausgegeben.

**Empfehlung:** Erwartete externe Fehler eng fangen, unerwartete Exceptions mit Stacktrace propagieren oder zentral in HTTP-/Workergrenzen behandeln. `pass` nur mit dokumentierter Begründung zulassen.

### P3 – Wartbarkeit und Bereinigung

#### D01 – Asteroiden- und Kometenpfade sind strukturell dupliziert

`jscpd` meldet unter anderem gleiche Blöcke in:

- `api/routes/asteroids.py` und `api/routes/comets.py`;
- `db_utils.py` bei Store/Get der Positionsdaten;
- `workers/precompute_worker.py` und `workers/unified_worker.py`;
- `static/js/skyRenderer.js` bei Loadern für Asteroiden und Kometen;
- `static/js/messierRenderer.js` und `static/js/zodiacRenderer.js`;
- Registrierungs- und Admin-Benutzeranlage.

Insgesamt wurden 25 Klone mit 328 duplizierten Zeilen erkannt. Die tatsächliche semantische Duplikation der beiden Objektpipelines ist größer als die rein textuelle Quote von 1,61 %.

**Empfehlung:** Eine generische Konfiguration pro Objektart (`kind`, Loader, Queue, Cache-Repository, Berechnungsfunktion, Frontend-Mapper) einführen. Workerimplementierungen erst zusammenführen, nachdem Retry- und Lock-Semantik festgelegt sind.

#### D02 – Sehr komplexe Funktionen konzentrieren Fehlerrisiko

Höchste von `radon` gemessene Komplexitäten:

| Funktion | Komplexität | Einstufung |
|---|---:|---|
| `comets.py::_standardize_comet_df` | 43 | F |
| `comets.py::_compute_comets_vectorized` | 41 | F |
| `api/computation.py::compute_sunpath_year` | 35 | E |
| `api/computation.py::compute_celestial_snapshot` | 28 | D |
| Asteroiden-Vektorberechnung | 27 | D |
| Smart-Interpolationsstrategie | 26 | D |

`static/js/skyRenderer.js` umfasst außerdem ungefähr 2.500 Zeilen. Hohe Komplexität ist kein Beweis für einen Fehler, erschwert aber Tests und Änderungen an bereits kritischen Datenpfaden.

**Empfehlung:** Normalisierung, Vektorberechnung, Filterung, Serialisierung und Fehlerbehandlung in kleine reine Funktionen trennen. `skyRenderer` nach Datenbeschaffung, Koordinatenprojektion, Layerverwaltung und Rendering aufteilen.

#### D03 – Konkrete Kandidaten auf toten oder wirkungslosen Code

Die folgenden Elemente besitzen im Repository keine produktiven Aufrufer oder sind durch Routing/No-op-Implementierung unerreichbar. Dynamische Nutzung außerhalb des Repositorys ist vor dem Löschen auszuschließen.

- gesamte nicht registrierte Route `api/routes/interpolation_admin.py`;
- `config/feature_flags.py` und mehrere Convenience-Funktionen ohne Referenzen;
- `api/computation.py::load_constellations`;
- Convenience-Funktionen am Ende von `api/on_demand_computation.py`;
- `db_utils.py::get_comets_by_magnitude` sowie Data-Update-Helfer ohne Aufrufer;
- `workers/worker_utils.py::compute_lock_key`, `round_to_bucket_boundary`, `publish_worker_status`, `handle_task_error`;
- ungenutztes `TaskType`-Enum und `PrecomputeRangeRequest`;
- `comets.py::clear_in_memory_cache`;
- `static/js/cacheStatusPanel.js`: öffentliche Methoden sind No-ops, werden aber weiterhin aufgerufen;
- `SkyRenderer.checkCacheAvailability()` liefert immer `null`, Triggerfunktionen sind No-ops;
- `startAutoUpdate`, `stopAutoUpdate` und weitere nicht referenzierte Renderer-Helfer;
- Legacy-Key `asciisky_location` wird geschrieben, aber nicht gelesen.

Zusätzlich meldet `ruff` 66 unbenutzte Imports und mehrere sicher tote lokale Variablen, zum Beispiel `mag_interp`, `location_dict`, `config`, `node_col` und `peri_col`.

**Empfehlung:** Kandidaten einzeln mit Import-/Runtime-Suche bestätigen, dann in kleinen Änderungen löschen. No-op-Kompatibilitätsschichten entweder klar als solche markieren und zeitlich begrenzen oder vollständig entfernen.

#### D04 – Cache-API trägt wirkungslose Parameter und veraltete Begriffe

Mehrere Funktionen reichen `ttl_seconds` weiter, obwohl Positionsloader keine TTL auswerten. `cache_interpolation.py` importiert Interpolationslogik, obwohl der aktuelle Pfad nur den nächsten Bucket auswählt. Diese Inkonsistenz hat L01 begünstigt.

**Empfehlung:** Öffentliche Namen und Parameter auf das tatsächliche Verfahren reduzieren oder echte TTL/Interpolation vollständig implementieren und testen.

## Test- und Qualitätslücken

### T01 – Tests können trotz internem Fehlschlag als bestanden gelten

In `test_hybrid_deduplication.py` geben vier als Pytest-Tests deklarierte Funktionen Boolwerte zurück. Pytest ignoriert Rückgabewerte und warnt bei den drei bis zur Rückgabe gelangten Tests lediglich; der vierte brach zuvor am fehlenden PostgreSQL ab. Ein intern abgefangener Fehler mit `return False` kann daher als bestandener Test erscheinen.

**Empfehlung:** Nur Assertions verwenden und Exceptions nicht in Erfolgswerte umwandeln.

### T02 – Infrastrukturtests sind nicht sauber markiert

`test_advisory_locks` wird im normalen Lauf gesammelt, benötigt aber PostgreSQL. Zudem kann ein Test auf derselben threadlokalen Session keine reale Lock-Konkurrenz simulieren, weil sessiongebundene Advisory Locks in derselben Sitzung reentrant sind.

**Empfehlung:** `integration`-Marker, Fixture/Container und zwei echte unabhängige Verbindungen beziehungsweise Prozesse verwenden.

### T03 – Mehrere Testdateien sind nur ausführbare Skripte

`test_magnitude_filters.py` und `test_performance.py` enthalten keine regulär gesammelten Pytest-Tests. Konsolenausgaben wie "PASS/FAIL" führen nicht zwingend zu einem fehlerhaften Exitcode.

**Empfehlung:** In Assertions und reproduzierbare Benchmarks umwandeln; Performancegrenzen separat und stabil definieren.

### T04 – Kritische Pfade sind nicht regressionsgetestet

Es fehlen gezielte Tests für:

- Loader-Signaturen und Nachbar-Bucket-Fallback;
- gültige leere Cacheergebnisse;
- Zeitzonen mit Offset und ungültige Zeitparameter;
- Task-Schema zwischen allen Publishern und Workern;
- Retry, DLQ und Claim-Freigabe;
- Datenreload nach Nightly-Update;
- Rollenentzug während einer aktiven Session;
- parallele Erstregistrierung.

Diese Tests sollten vor größeren Refactorings ergänzt werden, damit die Korrekturen nicht nur strukturell, sondern verhaltensbezogen abgesichert sind.

## Empfohlene Umsetzungsreihenfolge

### Phase 1 – Korrektheit absichern

1. L01, L05, L07, L08 und L13 mit kleinen Unit-Tests reproduzieren und korrigieren.
2. Einheitliches Taskschema einführen und L10 beheben.
3. Lock/Claim-Semantik aus L02/L03 definieren und mit zwei Datenbankverbindungen testen.
4. RabbitMQ-Retry/DLQ und Claim-Lifecycle aus L06 implementieren.

### Phase 2 – Betriebs- und Sicherheitsrisiken schließen

1. Worker-Datenversionierung/Reload aus L04 einführen.
2. Adminsession, Produktionssecret und First-Admin-Rennen aus L11/L12 beheben.
3. Interpolationskonfiguration aus L09 konsolidieren; Route erst danach geschützt aktivieren oder löschen.
4. Publisher Confirms beziehungsweise Outbox ergänzen.

### Phase 3 – Performance messen und verbessern

1. Eventloop-Lag und Route-Latenzen instrumentieren.
2. CPU-/DB-Arbeit aus Async-Routen verlagern.
3. Sonnenpfadberechnungen deduplizieren.
4. Frontend-Initialisierung und Layerabrufe reduzieren; Asset-Caching produktionsgerecht konfigurieren.

### Phase 4 – Duplikate und toten Code entfernen

1. Erst unreferenzierte No-ops, Imports und lokale Variablen löschen.
2. Danach Asteroiden-/Kometen-Repository und Routen vereinheitlichen.
3. Worker nur auf Basis der zuvor festgelegten Retry-/Claim-Semantik zusammenführen.
4. `skyRenderer.js` schrittweise zerlegen und jede Extraktion mit UI-/Datenvertragstests absichern.

## Gesamtbewertung

Die Anwendung besitzt eine brauchbare fachliche Struktur und viele Schutzideen – Cache-Buckets, Advisory Locks, persistente Claims, Retry und Admin-Konfiguration. Mehrere dieser Mechanismen sind jedoch nur teilweise verbunden oder verhalten sich anders als Kommentare und Namen vermuten lassen. Genau diese "fast funktionierenden" Schutzpfade bilden das größte Risiko, weil Fehler oft durch breite Exceptions, Truthiness-Prüfungen oder No-op-Kompatibilität verborgen bleiben.

Vor neuen Features sollte daher zuerst die Cache-/Worker-Korrektheit mit gezielten Integrationstests stabilisiert werden. Anschließend liefern Eventloop-Entlastung, kontrollierte Hintergrundberechnung und Frontend-Caching die größten Performancegewinne. Duplikat- und Dead-Code-Bereinigung sollte danach erfolgen, damit nicht versehentlich bestehende Fehlsemantik in neue Abstraktionen übernommen wird.
