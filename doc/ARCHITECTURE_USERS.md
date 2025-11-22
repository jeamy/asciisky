# Benutzer-Integration – Roadmap

## 1. Zielbild

- **Ohne Login:**
  - Anwendung verhält sich wie bisher.
  - Einstellungen kommen aus `user_settings.json` und/oder LocalStorage.
- **Mit Login:**
  - Benutzer kann sich registrieren (E-Mail, Benutzername, Passwort).
  - Nach Login kommen alle persönlichen Einstellungen aus der Datenbank.
  - Im Benutzerkonto werden u. a. gespeichert:
    - Standort/Einstellungen aus `user_settings.json`
    - Helligkeitsfilter
    - ausgewähltes Theme
    - zukünftige Optionen (z. B. weitere UI- oder Simulations-Settings)
  - Es gibt eine Benutzer-Administration (anlegen/ändern/löschen) für Admins.

Ziel ist, dass die App **ohne Login voll nutzbar bleibt**, aber mit Login personalisierte, persistente Einstellungen pro Benutzer bietet.

---

## 2. Annahmen und Randbedingungen

- Backend ist bereits mit Datenbank (Postgres) und API-Struktur vorhanden.
- Authentifizierung soll klassisch per Session-Cookie oder Token erfolgen (genaue Ausgestaltung in der Detailplanung).
- Keine Änderung des Kern-Workflows für nicht eingeloggte Benutzer.
- Sicherheit: Passwörter werden gehasht gespeichert, Login-Endpunkte werden gegen Brute-Force abgesichert.

---

## 3. Phase 1 – Anforderungen & Architektur präzisieren

**Ziele:**
- Fachliche Anforderungen und grobe Architektur für die Benutzer-Integration dokumentieren.

**Aufgaben:**
- Festlegen, welche Einstellungen pro Benutzer gespeichert werden sollen:
  - Aktuelle Struktur von `user_settings.json` analysieren (Location, Filter, usw.).
  - Theme und zukünftige Optionen als erweiterbares Feld (z. B. JSON) vorsehen.
- Definition, welche Konfigurationen global bleiben und nicht benutzerspezifisch sind.
- Entscheidung Authentifizierungs-Ansatz:
  - Session-Cookie vs. JWT (vermutlich Session-Cookie für klassische Web-App).
- Grobe Architektur-Skizze erstellen:
  - neue Tabellen (Users, UserSettings),
  - API-Endpunkte für Auth und Settings,
  - Frontend-Flows (Login, Registrierung, Account-Settings).

**Ergebnis:**
- Kurzes Architektur-Dokument (dieses + ggf. Ergänzung in `ARCHITECTURE_FLOW_API.md`).

---

## 4. Phase 2 – Datenmodell & Backend-Basis

**Ziele:**
- Datenbank-Struktur und Backend-Modelle für Benutzer und deren Settings bereitstellen.

**Aufgaben:**
- Tabellenentwurf (Beispiel):
  - `users`:
    - `id`
    - `email` (unique)
    - `username` (unique)
    - `password_hash`
    - `is_active`
    - `is_admin`
    - `created_at`, `updated_at`
  - `user_settings`:
    - `user_id` (FK auf `users.id`)
    - `settings` (JSONB) – speichert die komplette Struktur von `SettingsManager.settings`
      - z. B.:
        - `location` (Latitude, Longitude, Elevation, Name)
        - `display.horizontalShift`
        - `simTime.enabled`, `simTime.offsetMinutes`
        - `filters` (z. B. `asteroidMaxMagnitude`, `cometMaxMagnitude`)
        - `theme` (z. B. `green`, `blue`, `red`, `amber`)
        - `language` (z. B. `de`, `en`)
        - weitere Optionen (z. B. `options`-Objekt für zukünftige Features)
    - `last_updated` (Timestamp)
- Migrationen/SQL-Skripte erstellen und in das bestehende Setup integrieren (Docker, Startskripte).
- Backend-Modelle/Repositories/DAOs für `users` und `user_settings` anlegen.

**Ergebnis:**
- Neue Tabellen existieren und sind über das Backend ansprechbar (noch ohne Frontend-Anbindung).

Die Verwendung eines einzelnen JSONB-Feldes `settings` macht das Mapping zu/von `SettingsManager.settings` trivial und erlaubt einfache Erweiterungen ohne weitere DB-Migrationen.

Zusätzlich dient die Tabelle `user_settings` als Datenquelle für den Precompute-Coordinator
(`precompute_coordinator.py`): alle gespeicherten Benutzer-Standorte werden dort ausgelesen
und für Hintergrund-Vorberechnungen (Caching der Positionen und Sonnenbahn) verwendet.

---

## 5. Phase 3 – Authentifizierung & Registrierung (Backend-API)

**Ziele:**
- Minimal lauffähige Benutzerverwaltung mit Registrierung, Login und Logout.

**Aufgaben:**
- API-Endpunkte definieren (konkrete Pfade später in `constants.js` referenzieren):
  - `POST /api/auth/register`
    - Input: `email`, `username`, `password`.
    - Validierungen, Passwort-Hashing, Prüfung auf Eindeutigkeit.
  - `POST /api/auth/login`
    - Input: `username oder email`, `password`.
    - Validierung und Erzeugung einer Session (Cookie) oder eines Tokens.
  - `POST /api/auth/logout`
    - Session invalidieren / Token ungültig machen.
  - `GET /api/auth/me`
    - Liefert Basisinformationen zum eingeloggten Benutzer und optional bereits Settings.
- Sicherheit:
  - Passwörter mit bcrypt/argon2 o. Ä. speichern.
  - Rate-Limiting / einfache Brute-Force-Abwehr auf Login.
  - Optional für spätere Phase: E-Mail-Verifikation, Passwort-Reset.

**Ergebnis:**
- Vollständiger Login/Logout/Registrierungs-Flow auf API-Ebene.

---

## 6. Phase 4 – User-Settings-API

**Ziele:**
- Schnittstelle, über die Frontend alle benutzerspezifischen Einstellungen laden und speichern kann.

**Aufgaben:**
- Endpunkte designen:
  - `GET /api/user/settings`
    - Gibt die `settings` des eingeloggten Benutzers zurück.
    - Response-Format (Beispiel, 1:1 zu `SettingsManager.settings`):

      ```json
      {
        "location": {
          "latitude": 48.2082,
          "longitude": 16.3738,
          "elevation": 171.0,
          "name": "Wien"
        },
        "display": {
          "horizontalShift": 0
        },
        "simTime": {
          "enabled": false,
          "offsetMinutes": 0
        },
        "filters": {
          "asteroidMaxMagnitude": 10.5,
          "cometMaxMagnitude": 12.5
        },
        "theme": "green",
        "language": "de",
        "options": {}
      }
      ```

  - `PUT /api/user/settings`
    - Nimmt ein JSON im selben Format entgegen (komplett oder teil-aktualisiert, je nach Implementierung).
    - Backend schreibt das JSON in `user_settings.settings` (JSONB) und aktualisiert `last_updated`.

- Mapping von `user_settings.json` zur DB-Struktur:
  - Die Struktur von `user_settings.json` wird in `settings` übernommen und bei Bedarf um neue Felder ergänzt.
  - `SettingsManager.settings` bildet die Referenzstruktur; das Backend speichert und liefert genau diese Struktur.

- Backend-Helper-Funktionen:
  - `load_settings(user)` – holt `user_settings.settings` oder Default/`user_settings.json`, wenn kein Eintrag existiert.
  - `save_settings(user, settings)` – persistiert das komplette Settings-Objekt in `user_settings.settings`.

- Fallback-Strategie ohne Login:
  - Wenn kein Benutzer eingeloggt ist, Verwendung der bisherigen Logik
    (`user_settings.json` und/oder LocalStorage über `SettingsManager`).

**Ergebnis:**
- Stabile API für benutzerspezifische Einstellungen, kompatibel mit bestehendem Verhalten.

---

## 7. Phase 5 – Frontend-Flows

**Ziele:**
- UI für Registrierung, Login, Logout und Account-Einstellungen bereitstellen.

**Aufgaben:**
- Neue UI-Komponenten/Dialogs:
  - Login-Dialog.
  - Registrierungs-Dialog: Felder `email`, `username`, `password`.
  - Account-/Einstellungs-Dialog:
    - Standort-Einstellungen (aus `user_settings.json` übernommen).
    - Filter-Einstellungen (Magnitude-Filter usw.).
    - Theme-Auswahl (Integration der bestehenden Theme-Buttons G/R/B/A).
    - Platz für zukünftige Optionen.
- Verhalten definieren:
  - **Ohne Login:**
    - Einstellungen wie bisher aus `user_settings.json`/LocalStorage.
    - Theme-Auswahl bleibt lokal gespeichert.
  - **Mit Login:**
    - Nach Login: `GET /api/user/settings` aufrufen und UI initialisieren.
    - Änderungen im UI: zusätzlich `PUT /api/user/settings` aufrufen.
    - Theme-Wechsel:
      - Sofort im Frontend aktivieren.
      - Parallel über Settings-API persistent speichern.
- API-Endpunkte im Frontend über `static/js/constants.js` zentralisieren (kein Hardcoding von URLs).

**Ergebnis:**
- Benutzer können sich registrieren, einloggen und ihre persönlichen Einstellungen komfortabel verwalten.

---

## 8. Phase 6 – Benutzer-Administration

**Ziele:**
- Admins können Benutzerkonten verwalten.

**Aufgaben:**
- Rollenmodell umsetzen (`is_admin`).
- Admin-spezifische Endpunkte bereitstellen (nur für Admins zugänglich):
  - Liste aller Benutzer abrufen.
  - Benutzer anlegen.
  - Benutzer bearbeiten (Rolle, Aktiv-Status, ggf. Reset-Funktionen).
  - Benutzer löschen/deaktivieren.
- UI für Admins:
  - Einfache Admin-Ansicht/Seite oder Dialog für User-Management.

**Ergebnis:**
- Administrative Verwaltung der Benutzerbasis ist möglich.

---

## 9. Phase 7 – Migration & Rollout

**Ziele:**
- Sanfte Einführung der Benutzer-Integration ohne Bruch für bestehende Nutzer.

**Aufgaben:**
- Migrationsstrategie:
  - Bestehende `user_settings.json` als Default verwenden, wenn in der DB keine Settings existieren.
  - Beim ersten Speichern eines eingeloggten Users Settings nach `user_settings` schreiben.
- Kompatibilität sicherstellen:
  - Ohne Login bleibt Verhalten unverändert.
  - Login ist optional ("opt-in").
- Testszenarien:
  - Registrierung → Login → Settings ändern → Logout/Login → Persistenz prüfen.
  - Mehrere Test-Benutzer mit unterschiedlichen Locations, Filtern und Themes.
  - Edge Cases (deaktivierte Benutzer, ungültige Sessions, abgelaufene Tokens).

**Ergebnis:**
- Benutzer-Integration ist produktionsreif und koexistiert mit dem bisherigen, loginfreien Modus.
