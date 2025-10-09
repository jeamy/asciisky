import { t } from './i18n.js';
import { settingsManager } from './settings.js';

let panelEl = null;
let skyRenderer = null;

export function initVisibleObjectsList(elementId = 'visible-objects-panel', renderer = null) {
  const el = document.getElementById(elementId);
  if (el) {
    panelEl = el;
    // Zeige initial einen Platzhalter
    el.innerHTML = `
      <div class="vo-header">${t('visible_objects') || 'Sichtbare Objekte'}</div>
      <div class="vo-section vo-subtle">${t('loading') || 'Lade...'}</div>
    `;
  }
  if (renderer) skyRenderer = renderer;
}

export function updateVisibleObjectsList(celestialData) {
  const el = panelEl || document.getElementById('visible-objects-panel');
  if (!el) return;
  
  if (!celestialData) {
    el.innerHTML = `
      <div class="vo-header">${t('visible_objects') || 'Sichtbare Objekte'}</div>
      <div class="vo-section vo-subtle">${t('no_data') || 'Keine Daten verfügbar'}</div>
    `;
    return;
  }

  // Sammle alle sichtbaren Objekte (über dem Horizont)
  const visibleObjects = {
    sun: [],
    moon: [],
    planets: [],
    asteroids: [],
    comets: []
  };

  // Durchsuche alle Bodies
  if (celestialData.bodies) {
    Object.entries(celestialData.bodies).forEach(([name, obj]) => {
      if (!obj || obj.altitude <= 0) return;
      
      const lowerName = name.toLowerCase();
      
      // Sonne
      if (lowerName === 'sun') {
        visibleObjects.sun.push({
          name: t('sun') || 'Sonne',
          type: 'sun',
          data: obj
        });
      }
      // Mond
      else if (lowerName === 'moon') {
        visibleObjects.moon.push({
          name: t('moon') || 'Mond',
          type: 'moon',
          data: obj
        });
      }
      // Planeten
      else if (['mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune', 'pluto'].includes(lowerName)) {
        visibleObjects.planets.push({
          name: t(lowerName) || name,
          type: lowerName,
          data: obj
        });
      }
      // Asteroiden
      else if (obj.type === 'asteroid') {
        visibleObjects.asteroids.push({
          name: obj.name || name,
          bodyKey: name, // Speichere den Key aus bodies
          type: 'asteroid',
          magnitude: obj.magnitude,
          data: obj
        });
      }
      // Kometen
      else if (obj.type === 'comet') {
        visibleObjects.comets.push({
          name: obj.name || name,
          bodyKey: name, // Speichere den Key aus bodies
          type: 'comet',
          magnitude: obj.magnitude,
          data: obj
        });
      }
    });
  }

  // Sortiere Asteroiden und Kometen nach Helligkeit (aufsteigend)
  visibleObjects.asteroids.sort((a, b) => (a.magnitude || 99) - (b.magnitude || 99));
  visibleObjects.comets.sort((a, b) => (a.magnitude || 99) - (b.magnitude || 99));

  // HTML generieren
  let html = `<div class="vo-header">${t('visible_objects') || 'Sichtbare Objekte'}</div>`;

  // Sonne
  if (visibleObjects.sun.length > 0) {
    html += visibleObjects.sun.map(obj => 
      `<div class="vo-item" data-type="${obj.type}">${obj.name}</div>`
    ).join('');
  }

  // Mond
  if (visibleObjects.moon.length > 0) {
    html += visibleObjects.moon.map(obj => 
      `<div class="vo-item" data-type="${obj.type}">${obj.name}</div>`
    ).join('');
  }

  // Planeten
  if (visibleObjects.planets.length > 0) {
    html += visibleObjects.planets.map(obj => 
      `<div class="vo-item" data-type="${obj.type}">${obj.name}</div>`
    ).join('');
  }

  // Leerzeile vor Asteroiden
  if (visibleObjects.asteroids.length > 0) {
    html += '<div class="vo-spacer"></div>';
    html += visibleObjects.asteroids.map(obj => 
      `<div class="vo-item" data-type="asteroid" data-name="${obj.bodyKey || obj.name}">${obj.name}, ${obj.magnitude.toFixed(1)}</div>`
    ).join('');
  }

  // Leerzeile vor Kometen
  if (visibleObjects.comets.length > 0) {
    html += '<div class="vo-spacer"></div>';
    html += visibleObjects.comets.map(obj => 
      `<div class="vo-item" data-type="comet" data-name="${obj.bodyKey || obj.name}">${obj.name}, m ${obj.magnitude.toFixed(1)}</div>`
    ).join('');
  }

  // Wenn keine Objekte sichtbar sind
  if (visibleObjects.sun.length === 0 && 
      visibleObjects.moon.length === 0 && 
      visibleObjects.planets.length === 0 && 
      visibleObjects.asteroids.length === 0 && 
      visibleObjects.comets.length === 0) {
    html += `<div class="vo-section vo-subtle">${t('no_visible_objects') || 'Keine Objekte über dem Horizont'}</div>`;
  }

  el.innerHTML = html;

  // Event-Listener für Klicks auf Objekte
  el.querySelectorAll('.vo-item').forEach(item => {
    item.addEventListener('click', () => {
      const type = item.dataset.type;
      const name = item.dataset.name;
      
      console.log('Visible Objects List: clicked', { type, name });
      
      if (skyRenderer) {
        // Für Asteroiden und Kometen: verwende den Namen
        if (type === 'asteroid' || type === 'comet') {
          const success = skyRenderer.selectObject(name, true);
          if (!success) {
            console.warn('Failed to select object:', name);
          }
        } else {
          // Für Sonne, Mond, Planeten: verwende den Typ
          skyRenderer.selectObject(type, true);
        }
      } else {
        console.error('skyRenderer not available');
      }
    });
  });
}
