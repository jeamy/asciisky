// Internationalisierung (i18n) für ASCII Sky
export const i18n = {
    // Standardsprache ist Deutsch
    'de': {
        // Allgemeine Texte
        'loading': 'Lade Himmelsdaten...',
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
        'help_cache_status': 'Cache-Status',
        'help_cache_precompute': 'Cache-Vorberechnung',
        'help_cache_precompute_desc': 'Mit der Cache-Vorberechnung können Sie Himmelsdaten für einen bestimmten Zeitraum im Voraus berechnen lassen. Wählen Sie Start- und Enddatum und klicken Sie auf "Berechnung starten". Der Fortschritt wird angezeigt und die Daten stehen nach Abschluss für schnelle Anzeige zur Verfügung.',
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
        'help_zoom_pan': 'Zoom und Pan',
        'help_zoom_pan_desc': 'Am Desktop können Sie über den Zoom-Button die Ansicht vergrößern. Bei gezoomter Ansicht können Sie mit gedrückter Maustaste die Ansicht nach oben und unten verschieben.',
        'help_symbols': 'Symbole',
        'help_symbols_desc': 'Himmelsobjekte werden durch folgende Symbole dargestellt:',
        'symbol_sun': 'Sonne',
        'symbol_moon': 'Mond',
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
        'help_cache_status_desc': 'Zeigt verfügbare vorberechnete Daten für den aktuellen Standort. "Snapshots" sind stündliche Berechnungen für schnelle Anzeige.',
        'help_simulation_desc': 'Simuliert verschiedene Zeiten, um Himmelsbewegungen zu verfolgen. Die Steuerung ermöglicht präzise Zeitnavigation:',
        'help_simulation_desc2': 'Diese Zeitnavigation ermöglicht es, Himmelsbewegungen über längere Zeiträume zu verfolgen und astronomische Ereignisse wie Auf- und Untergänge zu beobachten.',
        'help_location_change': 'Standortwechsel',
        'help_location_change_desc': 'Beim ersten Wechsel zu einem neuen Ort kann die Berechnung länger dauern, da Himmelsdaten für Asteroiden und Kometen für diese Position erstmalig berechnet und zwischengespeichert werden müssen.',
        'help_github': 'Quellcode',
        'help_github_desc': 'ASCII Sky ist Open Source. Der vollständige Quellcode ist auf GitHub verfügbar:',
        
        // Object count display
        'visible_objects': 'Sichtbare Objekte',
        'asteroids_up_to_mag': 'Asteroiden bis Mag',
        'comets_up_to_mag': 'Kometen bis Mag',
        
        // Constellation controls
        'constellations': 'Sterne',
        'toggle_constellations': 'Sterne ein/ausblenden',
        'show_constellations': 'Sterne anzeigen',
        'hide_constellations': 'Sterne ausblenden',
    },
    
    // Englisch als Fallback
    'en': {
        // General texts
        'loading': 'Loading celestial data...',
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
        'help_cache_status_desc': 'Shows available precomputed data for the current location. "Snapshots" are hourly calculations for fast display.',
        'help_cache_precompute': 'Cache Precomputation',
        'help_cache_precompute_desc': 'Cache precomputation allows you to calculate celestial data for a specific time range in advance. Select start and end dates and click "Start Precompute". Progress will be displayed and the data will be available for quick display once completed.',
        'help_title': 'Help - ASCII Sky Tracker',
        'help_controls': 'Controls',
        'help_sky_view': 'Sky View',
        'help_object_list': 'Object List',
        'help_cache_status': 'Cache Status',
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
        'help_now': 'Current time (real-time)',
        'help_hour_plus': 'Hour forward (+1 hour)',
        'help_day_plus': 'Day forward (+24 hours)',
        'symbol_sun': 'Sun',
        'symbol_moon': 'Moon',
        'symbol_mercury': 'Mercury',
        'symbol_venus': 'Venus',
        'symbol_mars': 'Mars',
        'symbol_jupiter': 'Jupiter',
        'symbol_saturn': 'Saturn',
        'symbol_asteroid': 'Asteroids',
        'symbol_comet': 'Comets',
        'help_simulation_desc2': 'This time navigation allows you to track celestial movements over longer periods and observe astronomical events such as risings and settings.',
        'help_location_change': 'Location Changes',
        'help_location_change_desc': 'When switching to a new location for the first time, calculations may take longer as sky data for asteroids and comets for this position needs to be computed and cached initially.',
        'help_github': 'Source Code',
        'help_github_desc': 'ASCII Sky is Open Source. Find the complete source code on GitHub:',
        
        // Object count display
        'visible_objects': 'Visible Objects',
        'asteroids_up_to_mag': 'Asteroids up to Mag',
        'comets_up_to_mag': 'Comets up to Mag',
        
        // Constellation controls
        'constellations': 'Stars',
        'toggle_constellations': 'Toggle stars',
        'show_constellations': 'Show stars',
        'hide_constellations': 'Hide stars'
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
