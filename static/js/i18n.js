// Internationalisierung (i18n) für ASCII Sky
export const i18n = {
    // Standardsprache ist Deutsch
    'de': {
        // Allgemeine Texte
        'loading': 'Lade Himmelsdaten...',
        // Spezieller Hinweis für die Jahreskurve Sonnenauf-/untergang
        'loading_sunpath': 'Berechne Sonnenauf- und -untergangsdaten für dieses Jahr … Dies kann beim ersten Aufruf für einen neuen Standort etwas länger dauern (bis zu etwa drei Minuten).',
        'loading_asteroids': 'Lade Kleinplaneten-Daten...',
        'error_loading': 'Fehler beim Laden der Himmelsdaten. Bitte Seite neu laden.',
        'click_info': 'Klicke auf ein Objekt für Details',
        'app_title': 'ASCII Sky Tracker',
        'cache_status': 'Cache-Status',
        'location': 'Standort',
        'window': 'Zeitfenster',
        'in_window': 'h',
        'earliest': 'Früheste',
        'latest': 'Späteste',
        'error': 'Fehler',
        'no_data_for_location': 'Keine Cache-Daten für diesen Standort im aktuellen Zeitfenster.',
        'snapshots': 'Snapshots',
        'asteroids': 'Asteroiden',
        'comets': 'Kometen',
        'celestial': 'Himmelskörper',
        'database_stats': 'Datenbank-Statistiken',
        'db_size': 'DB-Größe',
        'total_objects': 'Objekte gesamt',
        'overall_cache': 'Gesamter Cache',
        'precompute_cache': 'Cache vorberechnen',
        'start_date': 'Startdatum',
        'end_date': 'Enddatum',
        'start_precompute': 'Berechnung starten',
        'processing': 'Verarbeitung...',
        'enter_both_dates': 'Bitte geben Sie sowohl Start- als auch Enddatum ein',
        'task_started': 'Aufgabe gestartet...',
        'task_completed': 'Aufgabe abgeschlossen!',
        'task_not_found_server_restart': 'Die Vorberechnungsaufgabe ist nicht mehr aktiv (Server wurde möglicherweise neu gestartet). Sie können bei Bedarf eine neue Vorberechnung starten.',
        'status': 'Status',
        
        // Himmelsobjekte
        'sun': 'Sonne',
        'moon': 'Mond',
        'Mercury': 'Merkur',
        'Venus': 'Venus',
        'Earth': 'Erde',
        'Mars': 'Mars',
        'Jupiter': 'Jupiter',
        'Saturn': 'Saturn',
        'Uranus': 'Uranus',
        'Neptune': 'Neptun',
        'Pluto': 'Pluto',
        // Kleingeschriebene Varianten für das Menü
        'mercury': 'Merkur',
        'venus': 'Venus',
        'earth': 'Erde',
        'mars': 'Mars',
        'jupiter': 'Jupiter',
        'saturn': 'Saturn',
        'uranus': 'Uranus',
        'neptune': 'Neptun',
        'pluto': 'Pluto',
        'asteroid': 'Asteroid',
        'comet': 'Komet',
        
        // Himmelsrichtungen
        'north': 'N',
        'east': 'O',
        'south': 'S',
        'west': 'W',
        
        // Ansichten
        'horizon_view': 'Horizontansicht',
        'planisphere_view': 'Planisphäre',
        
        // Dialog-Texte
        'multiple_objects_found': 'Mehrere Objekte',
        'close': '×',
        
        // Objektinformationen
        'altitude': 'Höhe',
        'azimuth': 'Azimut',
        'distance': 'Entfernung',
        'rise_time': 'Aufgang',
        'set_time': 'Untergang',
        'transit_time': 'Höchststand',
        'phase': 'Phase',
        'magnitude': 'Helligkeit',
        'day_length': 'Tageslänge',
        'astronomical_twilight': 'Astronomische Dämmerung',
        'nautical_twilight': 'Nautische Dämmerung',
        'civil_twilight': 'Bürgerliche Dämmerung',
        
        // Mondphasen
        'new_moon': 'Neumond',
        'waxing_crescent': 'Zunehmende Sichel',
        'first_quarter': 'Erstes Viertel',
        'waxing_gibbous': 'Zunehmender Mond',
        'full_moon': 'Vollmond',
        'waning_gibbous': 'Abnehmender Mond',
        'last_quarter': 'Letztes Viertel',
        'waning_crescent': 'Abnehmende Sichel',
        
        // Zeiteinheiten
        'hour': 'Uhr',
        'au': 'AE', // Astronomische Einheit
        
        // Standort-Dialog
        'location_settings': 'Standort-Einstellungen',
        
        // Simulierte Zeit
        'sim_time_controls': 'Simulierte Zeit',
        'sim_time_use': 'Simulierte Zeit verwenden',
        'sim_time_hours': 'Stunden',
        'sim_time_minutes': 'Minuten',
        'sim_time_reset': 'Zurücksetzen',
        'sim_time_preview': 'Simuliert:',
        'custom_time_title': 'Benutzerdefinierte Zeit',
        'date': 'Datum',
        'time': 'Zeit',
        'apply': 'Anwenden',
        'click_to_set_time': 'Klicken, um eine benutzerdefinierte Zeit einzugeben',
        'invalid_time_input': 'Bitte geben Sie ein gültiges Datum und eine gültige Zeit ein.',
        'time_input_error': 'Fehler bei der Zeiteingabe. Bitte versuchen Sie es erneut.',
        
        // Navigationspfeile
        'shift_left': 'Horizont nach links verschieben',
        'shift_right': 'Horizont nach rechts verschieben',
        
        // Filter-Einstellungen
        'asteroid_magnitude_label': 'Asteroiden max. Magnitude:',
        'comet_magnitude_label': 'Kometen max. Magnitude:',
        'apply_filters': 'Anwenden',
        'search_location': 'Standort suchen...',
        'search': 'Suchen',
        'fetching_elevation': 'Höhe wird ermittelt...',
        'searching': 'Suche',
        'search_error': 'Fehler bei der Suche',
        'no_results_found': 'Keine Ergebnisse gefunden',
        'search_results': 'Suchergebnisse',
        'location_preview': 'Standortvorschau',
        'name': 'Name',
        'coordinates': 'Koordinaten',
        'elevation_not_available': 'Nicht verfügbar',
        'fetching': 'Wird geladen...',
        'current_location': 'Aktueller Standort',
        'manual_coordinates': 'Manuelle Koordinaten',
        'latitude': 'Breitengrad',
        'longitude': 'Längengrad',
        'elevation': 'Höhe (m)',
        'location_name': 'Ortsname',
        'apply': 'Übernehmen',
        'invalid_coordinates': 'Ungültige Koordinaten',
        
        // Hilfe-Dialog
        'help_title': 'Hilfe - ASCII Sky Tracker',
        'help_controls': 'Steuerung',
        'help_sky_view': 'Himmelsansicht',
        'help_object_list': 'Objektliste',
        'help_simulation': 'Zeitsimulation',
        'location_button': 'Standort-Button',
        'help_location': 'Ändert den Beobachtungsstandort (Breiten-/Längengrad und Höhe)',
        'help_time_controls': 'Zeitsteuerung - Tag zurück, Stunde zurück, Jetzt (Echtzeit), Stunde vor, Tag vor',
        'help_time_display': 'Zeitanzeige',
        'help_time_display_desc': 'Klickbar, um ein beliebiges Datum und eine beliebige Uhrzeit für die Simulation einzugeben',
        'help_language': 'Sprachwechsel zwischen Deutsch und Englisch',
        'help_object_click': 'Objekt anklicken',
        'help_object_click_desc': 'Zeigt Details wie Position, Helligkeit und Auf-/Untergangszeiten',
        'help_navigation': 'Navigation',
        'help_navigation_desc': 'Pfeile links/rechts verschieben den Horizont um 5° (N, O, S, W sichtbar machen)',
        'help_view_modes': 'Ansichten: Horizont / Planisphäre',
        'help_view_modes_desc': 'Über den Tab unter der Himmelsansicht können Sie zwischen Horizontansicht (rechteckig) und Planisphäre (runder Himmelsatlas) umschalten. In der Planisphäre zeigt die gepunktete Kurve den Horizont: Objekte über dem Horizont liegen innerhalb, Objekte darunter außerhalb der Kurve.',
        'help_zoom_pan': 'Zoom und Pan',
        'help_zoom_pan_desc': 'Am Desktop können Sie über den Zoom-Button die Ansicht vergrößern. Bei gezoomter Ansicht können Sie mit gedrückter Maustaste die Ansicht nach oben und unten verschieben.',
        'help_symbols': 'Symbole',
        'help_symbols_desc': 'Himmelsobjekte werden durch folgende Symbole dargestellt:',
        'symbol_sun': 'Sonne',
        'symbol_moon': 'Mond (phasenabhängig)',
        'symbol_moon_phases': 'Mondphasen: 🌑 Neumond, 🌒 zunehmende Sichel, 🌓 erstes Viertel, 🌔 zunehmend, 🌕 Vollmond, 🌖 abnehmend, 🌗 letztes Viertel, 🌘 abnehmende Sichel',
        'symbol_mercury': 'Merkur',
        'symbol_venus': 'Venus',
        'symbol_mars': 'Mars',
        'symbol_jupiter': 'Jupiter',
        'symbol_saturn': 'Saturn',
        'symbol_asteroid': 'Asteroiden',
        'symbol_comet': 'Kometen',
        'help_day_minus': 'Tag zurück (-24 Stunden)',
        'help_hour_minus': 'Stunde zurück (-1 Stunde)',
        'help_now': 'Aktuelle Zeit (Echtzeit)',
        'help_hour_plus': 'Stunde vor (+1 Stunde)',
        'help_day_plus': 'Tag vor (+24 Stunden)',
        'help_object_list_desc': 'Klick auf Objekttyp (Sonne, Mond, Planeten, etc.) markiert alle Objekte dieses Typs im Himmel.',
        'help_simulation_desc': 'Simuliert verschiedene Zeiten, um Himmelsbewegungen zu verfolgen. Die Steuerung ermöglicht präzise Zeitnavigation:',
        'help_simulation_desc2': 'Diese Zeitnavigation ermöglicht es, Himmelsbewegungen über längere Zeiträume zu verfolgen und astronomische Ereignisse wie Auf- und Untergänge zu beobachten.',
        'help_location_change': 'Standortwechsel',
        'help_location_change_desc': 'Beim ersten Wechsel zu einem neuen Standort kann die Berechnung länger dauern, weil die Himmelsdaten für Asteroiden und Kometen für diesen Standort zunächst berechnet und zwischengespeichert werden müssen.',
        'help_magnitude_filters': 'Helligkeitsfilter',
        'help_magnitude_filters_desc': 'Über den ⚙️-Button unter "Sichtbare Objekte" können Sie die Helligkeitsfilter für Asteroiden und Kometen anpassen (Magnitude 10-20). Bei Änderung der Filter werden die Daten neu berechnet, was einige Minuten dauern kann. Die Objekte werden automatisch angezeigt, sobald sie verfügbar sind.',
        'help_registration': 'Registrierung & Konten',
        'help_registration_desc1': 'Die Login- und Registrierungsfunktion ist ein Komfort-Feature für diese Demo. Die Anwendung lässt sich vollständig auch ohne Login nutzen.',
        'help_registration_desc2': 'Bei der Registrierung werden folgende Daten gespeichert: Benutzername, Passwort-Hash (kein Klartext-Passwort) sowie optionale Benutzereinstellungen wie Standort, Anzeigeeinstellungen (z. B. Horizontalverschiebung), simulierte Zeit, Helligkeitsfilter, Farbthema und Sprache. Ohne Login werden diese Einstellungen nur lokal im Browser (LocalStorage) gespeichert und nicht auf dem Server.',
        'help_registration_desc3': 'Wichtig: Es gibt keinen Passwort-Reset und keinen Support dafür. Wenn das Passwort vergessen wird, kann das Konto nicht wiederhergestellt werden – in diesem Fall einfach ein neues Konto anlegen.',
        'help_github': 'Quellcode',
        'help_github_desc': 'ASCII Sky ist Open Source. Der vollständige Quellcode ist auf GitHub verfügbar:',
        // Sonnenbahn-Jahreskurve
        'sunpath_curve': 'Sonnenauf-/untergang (Jahreskurve)',
        'toggle_sunpath': 'Sonnenauf-/untergangskurve ein/ausblenden',
        'sunpath_title': 'Sonnenauf-/untergang für',
        
        // Object count display
        'visible_objects': 'Sichtbare Objekte',
        'asteroids_up_to_mag': 'Asteroiden bis Mag',
        'comets_up_to_mag': 'Kometen bis Mag',
        'no_data': 'Keine Daten verfügbar',
        'no_visible_objects': 'Keine Objekte über dem Horizont',
        
        // Magnitude filters
        'magnitude_filters': 'Helligkeitsfilter',
        'magnitude_filter_info': 'Bei Änderung der Filter werden die Daten neu berechnet (einige Minuten). Die Objekte erscheinen automatisch, sobald sie verfügbar sind.',
        'cache_invalidated_message': 'Filter geändert. Neuberechnung läuft (einige Minuten)...',
        'error_applying_filters': 'Fehler beim Anwenden der Filter',
        
        // Constellation controls
        'constellations': 'Sternbilder',
        'toggle_constellations': 'Sternbilder ein/ausblenden',
        'show_constellations': 'Sternbilder anzeigen',
        'hide_constellations': 'Sternbilder ausblenden',
        
        // Constellation names
        // Zodiac
        'Aries': 'Widder',
        'Taurus': 'Stier',
        'Gemini': 'Zwillinge',
        'Cancer': 'Krebs',
        'Leo': 'Löwe',
        'Virgo': 'Jungfrau',
        'Libra': 'Waage',
        'Scorpius': 'Skorpion',
        'Sagittarius': 'Schütze',
        'Capricornus': 'Steinbock',
        'Aquarius': 'Wassermann',
        'Pisces': 'Fische',
        // Additional constellations
        'Ursa Major': 'Großer Bär',
        'Ursa Minor': 'Kleiner Bär',
        'Pegasus': 'Pegasus',
        'Andromeda': 'Andromeda',
        'Cassiopeia': 'Kassiopeia',
        'Orion': 'Orion',
        'Canis Major': 'Großer Hund',
        'Perseus': 'Perseus',
        'Auriga': 'Fuhrmann',
        'Draco': 'Drachen',
        'Lyra': 'Leier',
        'Cygnus': 'Schwan',
        'Aquila': 'Adler',
        'Bootes': 'Bärenhüter',
    },
    
    // Englisch als Fallback
    'en': {
        // General texts
        'loading': 'Loading celestial data...',
        // Dedicated hint for yearly sunrise/sunset computation (sunpath overlay)
        'loading_sunpath': 'Computing yearly sunrise and sunset data for this location… On first use for a new location this may take a while (up to about three minutes).',
        'loading_asteroids': 'Loading minor planet data...',
        'error_loading': 'Error loading sky data. Please refresh the page.',
        'click_info': 'Click on any object for details',
        'app_title': 'ASCII Sky Tracker',
        'cache_status': 'Cache Status',
        'location': 'Location',
        'window': 'Window',
        'in_window': 'h',
        'earliest': 'Earliest',
        'latest': 'Latest',
        'error': 'Error',
        'no_data_for_location': 'No cache data for this location in the current window.',
        'snapshots': 'snapshots',
        'overall_cache': 'Total cache',
        'precompute_cache': 'Precompute Cache',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'start_precompute': 'Start Precompute',
        'processing': 'Processing...',
        'enter_both_dates': 'Please enter both start and end dates',
        'task_started': 'Task started...',
        'task_completed': 'Task completed!',
        'task_not_found_server_restart': 'The precompute task is no longer active (server may have restarted). You can start a new precomputation if needed.',
        'status': 'Status',
        
        // Celestial objects
        'sun': 'Sun',
        'moon': 'Moon',
        'Mercury': 'Mercury',
        'Venus': 'Venus',
        'Earth': 'Earth',
        'Mars': 'Mars',
        'Jupiter': 'Jupiter',
        'Saturn': 'Saturn',
        'Uranus': 'Uranus',
        'Neptune': 'Neptune',
        'Pluto': 'Pluto',
        // Lowercase variants for the menu
        'mercury': 'Mercury',
        'venus': 'Venus',
        'earth': 'Earth',
        'mars': 'Mars',
        'jupiter': 'Jupiter',
        'saturn': 'Saturn',
        'uranus': 'Uranus',
        'neptune': 'Neptune',
        'pluto': 'Pluto',
        'asteroid': 'Asteroid',
        'comet': 'Comet',
        
        // Cardinal directions
        'north': 'N',
        'east': 'E',
        'south': 'S',
        'west': 'W',
        
        // Views
        'horizon_view': 'Horizon view',
        'planisphere_view': 'Planisphere',
        
        // Dialog texts
        'multiple_objects_found': 'Multiple Objects',
        'close': '×',
        
        // Object information
        'altitude': 'Altitude',
        'azimuth': 'Azimuth',
        'distance': 'Distance',
        'rise_time': 'Rise',
        'set_time': 'Set',
        'transit_time': 'Transit',
        'phase': 'Phase',
        'magnitude': 'Magnitude',
        'day_length': 'Day length',
        'astronomical_twilight': 'Astronomical twilight',
        'nautical_twilight': 'Nautical twilight',
        'civil_twilight': 'Civil twilight',
        
        // Moon phases
        'new_moon': 'New Moon',
        'waxing_crescent': 'Waxing Crescent',
        'first_quarter': 'First Quarter',
        'waxing_gibbous': 'Waxing Gibbous',
        'full_moon': 'Full Moon',
        'waning_gibbous': 'Waning Gibbous',
        'last_quarter': 'Last Quarter',
        'waning_crescent': 'Waning Crescent',
        
        // Time units
        'hour': '',
        'au': 'AU', // Astronomical Unit
        
        // Location dialog
        'location_settings': 'Location Settings',
        
        // Simulated time
        'sim_time_controls': 'Simulated Time',
        'sim_time_use': 'Use simulated time',
        'sim_time_hours': 'Hours',
        'sim_time_minutes': 'Minutes',
        'sim_time_reset': 'Reset',
        'sim_time_preview': 'Simulated:',
        'custom_time_title': 'Custom Time',
        'date': 'Date',
        'time': 'Time',
        'apply': 'Apply',
        'click_to_set_time': 'Click to enter a custom time',
        'invalid_time_input': 'Please enter a valid date and time.',
        'time_input_error': 'Error processing time input. Please try again.',
        
        // Navigation arrows
        'shift_left': 'Shift horizon to the left',
        'shift_right': 'Shift horizon to the right',
        
        // Filter settings
        'asteroid_magnitude_label': 'Asteroids max. magnitude:',
        'comet_magnitude_label': 'Comets max. magnitude:',
        'apply_filters': 'Apply',
        'search_location': 'Search location...',
        'search': 'Search',
        'fetching_elevation': 'Fetching elevation...',
        'searching': 'Searching',
        'search_error': 'Search error',
        'no_results_found': 'No results found',
        'search_results': 'Search Results',
        'location_preview': 'Location Preview',
        'name': 'Name',
        'coordinates': 'Coordinates',
        'elevation_not_available': 'Not available',
        'fetching': 'Loading...',
        'current_location': 'Current Location',
        'manual_coordinates': 'Manual Coordinates',
        'latitude': 'Latitude',
        'longitude': 'Longitude',
        'elevation': 'Elevation (m)',
        'location_name': 'Location Name',
        'apply': 'Apply',
        'invalid_coordinates': 'Invalid coordinates',
        'help_object_list_desc': 'Click on object type (Sun, Moon, Planets, etc.) highlights all objects of this type in the sky.',
        'help_title': 'Help - ASCII Sky Tracker',
        'help_controls': 'Controls',
        'help_sky_view': 'Sky View',
        'help_object_list': 'Object List',
        'help_object_click': 'Object Click',
        'help_object_click_desc': 'Shows details like position, magnitude, and rise/set times',
        'help_navigation': 'Navigation',
        'help_navigation_desc': 'Left/right arrows shift the horizon by 5° (make N, E, S, W visible)',
        'help_zoom_pan': 'Zoom and Pan',
        'help_zoom_pan_desc': 'On desktop, you can use the zoom button to enlarge the view. When zoomed in, you can click and drag to move the view up and down.',
        'help_symbols': 'Symbols',
        'help_symbols_desc': 'Celestial objects are represented by the following symbols:',
        'help_time_controls': 'Time controls - day back, hour back, now (real-time), hour forward, day forward',
        'help_simulation_desc': 'Simulates different times to track celestial movements. The controls allow precise time navigation:',
        'help_day_minus': 'Day back (-24 hours)',
        'help_hour_minus': 'Hour back (-1 hour)',
        'help_now': 'Now (current time)',
        'help_hour_plus': 'Hour forward (+1 hour)',
        'help_day_plus': 'Day forward (+24 hours)',
        'symbol_sun': 'Sun',
        'symbol_moon': 'Moon (phase-dependent)',
        'symbol_moon_phases': 'Moon phases: new moon, waxing crescent, first quarter, waxing gibbous, full moon, waning gibbous, last quarter, waning crescent',
        'symbol_mercury': 'Mercury',
        'symbol_venus': 'Venus',
        'symbol_mars': 'Mars',
        'symbol_jupiter': 'Jupiter',
        'symbol_saturn': 'Saturn',
        'symbol_comet': 'Comets',
        'help_simulation_desc2': 'This time navigation allows you to track celestial movements over longer periods and observe astronomical events such as risings and settings.',
        'help_location_change': 'Location Changes',
        'help_location_change_desc': 'When switching to a new location for the first time, calculations may take longer because asteroid and comet sky data for that location must be computed and cached first.',
        'help_magnitude_filters': 'Brightness Filters',
        'help_magnitude_filters_desc': 'Use the ⚙️ button under "Visible Objects" to adjust brightness filters for asteroids and comets (magnitude 10-20). Changing filters will recalculate the data, which may take several minutes. Objects will be displayed automatically once available.',
        'help_registration': 'Registration & Accounts',
        'help_registration_desc1': 'The login and registration feature is a convenience option for this demo. The app can be used fully without logging in.',
        'help_registration_desc2': 'When you register, the following data is stored: username, password hash (no plain-text password) and optional user settings such as location, display settings (e.g. horizontal shift), simulated time, brightness filters, color theme and language. Without logging in, these settings are only stored locally in your browser (localStorage), not on the server.',
        'help_registration_desc3': 'Important: There is no password reset and no support for account recovery. If you forget your password, the account cannot be restored – simply create a new account instead.',
        'help_github': 'Source Code',
        'help_github_desc': 'ASCII Sky is Open Source. Find the complete source code on GitHub:',
        // Sunpath yearly curve
        'sunpath_curve': 'Sunrise/sunset (year curve)',
        'toggle_sunpath': 'Toggle sunrise/sunset curve',
        'sunpath_title': 'Sunrise/sunset for',
        
        // Object count display
        'visible_objects': 'Visible Objects',
        'asteroids_up_to_mag': 'Asteroids up to Mag',
        'comets_up_to_mag': 'Comets up to Mag',
        'no_data': 'No data available',
        'no_visible_objects': 'No objects above horizon',
        
        // Magnitude filters
        'magnitude_filters': 'Brightness Filters',
        'magnitude_filter_info': 'Changing filters will recalculate data (several minutes). Objects appear automatically when available.',
        'cache_invalidated_message': 'Filters changed. Recalculating (several minutes)...',
        'error_applying_filters': 'Error applying filters',
        
        // Constellation controls
        'constellations': 'Constellations',
        'toggle_constellations': 'Toggle constellations',
        'show_constellations': 'Show constellations',
        'hide_constellations': 'Hide constellations',
        
        // Constellation names
        // Zodiac
        'Aries': 'Aries',
        'Taurus': 'Taurus',
        'Gemini': 'Gemini',
        'Cancer': 'Cancer',
        'Leo': 'Leo',
        'Virgo': 'Virgo',
        'Libra': 'Libra',
        'Scorpius': 'Scorpius',
        'Sagittarius': 'Sagittarius',
        'Capricornus': 'Capricorn',
        'Aquarius': 'Aquarius',
        'Pisces': 'Pisces',
        // Additional constellations
        'Ursa Major': 'Great Bear',
        'Ursa Minor': 'Little Bear',
        'Pegasus': 'Pegasus',
        'Andromeda': 'Andromeda',
        'Cassiopeia': 'Cassiopeia',
        'Orion': 'Orion',
        'Canis Major': 'Great Dog',
        'Perseus': 'Perseus',
        'Auriga': 'Charioteer',
        'Draco': 'Dragon',
        'Lyra': 'Lyre',
        'Cygnus': 'Swan',
        'Aquila': 'Eagle',
        'Bootes': 'Herdsman'
    }
};

// Aktuelle Sprache (Standard: Deutsch)
let currentLanguage = 'de';

// Funktion zum Abrufen eines übersetzten Textes
export function t(key) {
    // Versuche, den Text in der aktuellen Sprache zu finden
    if (i18n[currentLanguage] && i18n[currentLanguage][key]) {
        return i18n[currentLanguage][key];
    }
    
    // Fallback auf Englisch
    if (i18n['en'] && i18n['en'][key]) {
        return i18n['en'][key];
    }
    
    // Wenn keine Übersetzung gefunden wurde, gib den Schlüssel zurück
    return key;
}

// Funktion zum Ändern der Sprache
export function setLanguage(lang) {
    if (i18n[lang]) {
        currentLanguage = lang;
        return true;
    }
    return false;
}

// Funktion zum Abrufen der aktuellen Sprache
export function getCurrentLanguage() {
    return currentLanguage;
}
