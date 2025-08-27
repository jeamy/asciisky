// Internationalisierung (i18n) für ASCII Sky
export const i18n = {
    // Standardsprache ist Deutsch
    'de': {
        // Allgemeine Texte
        'loading': 'Lade Himmelsdaten...',
        'error_loading': 'Fehler beim Laden der Himmelsdaten. Bitte Seite neu laden.',
        'click_info': 'Klicke auf ein Objekt für Details',
        
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
        'au': 'AE' // Astronomische Einheit
    },
    
    // Englisch als Fallback
    'en': {
        // General texts
        'loading': 'Loading celestial data...',
        'error_loading': 'Error loading sky data. Please refresh the page.',
        'click_info': 'Click on any object for details',
        
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
        'au': 'AU' // Astronomical Unit
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
