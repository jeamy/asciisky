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
        'window': 'Zeitraum',
        'in_window': 'h',
        'earliest': 'Frühester',
        'latest': 'Spätester',
        'error': 'Fehler',
        'no_data_for_location': 'Keine Cache-Daten für diesen Standort im aktuellen Zeitraum.',
        'snapshots': 'Einträge',
        'overall_cache': 'Gesamter Cache',
        
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
        
        // Navigationspfeile
        'shift_left': 'Horizont nach links verschieben',
        'shift_right': 'Horizont nach rechts verschieben',
        
        // Filter-Einstellungen
        'asteroid_magnitude_label': 'Asteroiden max. Magnitude:',
        'comet_magnitude_label': 'Kometen max. Magnitude:',
        'apply_filters': 'Anwenden',
        'search_location': 'Ort suchen...',
        'search': 'Suchen',
        'searching': 'Suche',
        'search_error': 'Fehler bei der Suche',
        'no_results_found': 'Keine Ergebnisse gefunden',
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
        'help_simulation': 'Zeitsimulation',
        'location_button': 'Standort-Button',
        'help_location': 'Ändert den Beobachtungsstandort (Breiten-/Längengrad und Höhe)',
        'help_time_controls': 'Zeitsteuerung - Stunde zurück, Jetzt (Echtzeit), Stunde vor',
        'help_language': 'Sprachwechsel zwischen Deutsch und Englisch',
        'help_object_click': 'Objekt anklicken',
        'help_object_click_desc': 'Zeigt Details wie Position, Helligkeit und Auf-/Untergangszeiten',
        'help_navigation': 'Navigation',
        'help_navigation_desc': 'Pfeile links/rechts verschieben den Horizont um 5° (N, O, S, W sichtbar machen)',
        'help_symbols': 'Symbole',
        'help_symbols_desc': '☉ Sonne, ☽ Mond, ☿♀♂♃♄ Planeten, • Asteroiden, ☄ Kometen',
        'help_object_list_desc': 'Klick auf Objekttyp (Sonne, Mond, Planeten, etc.) markiert alle Objekte dieses Typs im Himmel.',
        'help_cache_status_desc': 'Zeigt verfügbare vorberechnete Daten für den aktuellen Standort. "Snapshots" sind stündliche Berechnungen für schnelle Anzeige.',
        'help_simulation_desc': 'Die Simulation zeigt den Himmel zu verschiedenen Zeiten. Nutzen Sie die Zeitsteuerung, um zwischen Vergangenheit und Zukunft zu wechseln.',
        'help_location_change': 'Ortswechsel',
        'help_location_change_desc': 'Beim ersten Wechsel zu einem neuen Ort kann die Berechnung länger dauern, da Himmelsdaten für diese Position erstmalig berechnet und zwischengespeichert werden müssen.',
        'help_github': 'Quellcode',
        'help_github_desc': 'ASCII Sky ist Open Source. Den vollständigen Quellcode finden Sie auf GitHub:',
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
        
        // Navigation arrows
        'shift_left': 'Shift horizon to the left',
        'shift_right': 'Shift horizon to the right',
        
        // Filter settings
        'asteroid_magnitude_label': 'Asteroids max. magnitude:',
        'comet_magnitude_label': 'Comets max. magnitude:',
        'apply_filters': 'Apply',
        'search_location': 'Search location...',
        'search': 'Search',
        'searching': 'Searching',
        'search_error': 'Search error',
        'no_results_found': 'No results found',
        'current_location': 'Current Location',
        'manual_coordinates': 'Manual Coordinates',
        'latitude': 'Latitude',
        'longitude': 'Longitude',
        'elevation': 'Elevation (m)',
        'location_name': 'Location Name',
        'apply': 'Apply',
        'invalid_coordinates': 'Invalid coordinates',
        
        // Help Dialog
        'help_title': 'Help - ASCII Sky Tracker',
        'help_controls': 'Controls',
        'help_sky_view': 'Sky View',
        'help_object_list': 'Object List',
        'help_cache_status': 'Cache Status',
        'help_simulation': 'Time Simulation',
        'location_button': 'Location Button',
        'help_location': 'Changes the observation location (latitude/longitude and elevation)',
        'help_time_controls': 'Time controls - hour back, Now (real-time), hour forward',
        'help_language': 'Language switch between German and English',
        'help_object_click': 'Click object',
        'help_object_click_desc': 'Shows details like position, brightness and rise/set/transit times',
        'help_navigation': 'Navigation',
        'help_navigation_desc': 'Left/right arrows shift horizon by 5° (make N, E, S, W visible)',
        'help_symbols': 'Symbols',
        'help_symbols_desc': '☉ Sun, ☽ Moon, ☿♀♂♃♄ Planets, • Asteroids, ☄ Comets',
        'help_object_list_desc': 'Click on object type (Sun, Moon, Planets, etc.) highlights all objects of this type in the sky.',
        'help_cache_status_desc': 'Shows available precomputed data for the current location. "Snapshots" are hourly calculations for fast display.',
        'help_simulation_desc': 'Simulates different times to track celestial movements. Objects move according to their real orbits.',
        'help_location_change': 'Location Changes',
        'help_location_change_desc': 'When switching to a new location for the first time, calculations may take longer as sky data for this position needs to be computed and cached initially.',
        'help_github': 'Source Code',
        'help_github_desc': 'ASCII Sky is Open Source. Find the complete source code on GitHub:'
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
