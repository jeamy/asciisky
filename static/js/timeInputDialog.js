import { t } from './i18n.js';
import { settingsManager } from './settings.js';

function getLocationTimezone() {
    try {
        const loc = settingsManager.getLocation && settingsManager.getLocation();
        if (loc && typeof loc.timezone === 'string' && loc.timezone) return loc.timezone;
    } catch (_) { /* noop */ }
    return null;
}

function getZonedParts(date, timeZone) {
    const fmt = new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
    const parts = fmt.formatToParts(date);
    const get = (type) => {
        const p = parts.find(x => x.type === type);
        return p ? Number(p.value) : NaN;
    };
    return {
        year: get('year'),
        month: get('month'),
        day: get('day'),
        hour: get('hour'),
        minute: get('minute')
    };
}

function zonedDateTimeToUtcMillis({ year, month, day, hour, minute }, timeZone) {
    // Convert a wall-clock time in `timeZone` into UTC milliseconds.
    // Uses a small fixed-point iteration to handle DST transitions.
    const targetAsUtc = Date.UTC(year, month - 1, day, hour, minute, 0);
    let guessUtc = targetAsUtc;
    for (let i = 0; i < 3; i++) {
        const zp = getZonedParts(new Date(guessUtc), timeZone);
        const guessAsUtc = Date.UTC(zp.year, zp.month - 1, zp.day, zp.hour, zp.minute, 0);
        const diff = guessAsUtc - targetAsUtc;
        guessUtc = guessUtc - diff;
        if (diff === 0) break;
    }
    return guessUtc;
}

export class TimeInputDialog {
    constructor(onTimeChange) {
        this.onTimeChange = onTimeChange;
        this.dialogElement = null;
    }

    show() {
        // Entferne vorhandenen Dialog, falls vorhanden
        if (this.dialogElement) {
            this.dialogElement.remove();
        }

        // Hole aktuelle Zeit-Einstellungen
        const { offsetMinutes } = settingsManager.getSimulatedTimeOffset();
        const tz = getLocationTimezone();
        const currentDate = new Date(Date.now() + offsetMinutes * 60000);

        // Formatiere Datum und Zeit für die Eingabefelder (in Standort-Zeitzone, falls vorhanden)
        let year, month, day, hours, minutes;
        try {
            if (tz) {
                const p = getZonedParts(currentDate, tz);
                year = p.year;
                month = String(p.month).padStart(2, '0');
                day = String(p.day).padStart(2, '0');
                hours = String(p.hour).padStart(2, '0');
                minutes = String(p.minute).padStart(2, '0');
            } else {
                year = currentDate.getFullYear();
                month = String(currentDate.getMonth() + 1).padStart(2, '0');
                day = String(currentDate.getDate()).padStart(2, '0');
                hours = String(currentDate.getHours()).padStart(2, '0');
                minutes = String(currentDate.getMinutes()).padStart(2, '0');
            }
        } catch (_) {
            year = currentDate.getFullYear();
            month = String(currentDate.getMonth() + 1).padStart(2, '0');
            day = String(currentDate.getDate()).padStart(2, '0');
            hours = String(currentDate.getHours()).padStart(2, '0');
            minutes = String(currentDate.getMinutes()).padStart(2, '0');
        }
        
        // Erstelle Dialog-Element
        this.dialogElement = document.createElement('div');
        this.dialogElement.className = 'time-dialog-overlay';
        this.dialogElement.innerHTML = `
            <div class="time-dialog">
                <button class="dialog-close">&times;</button>
                <h3>${t('custom_time_title') || 'Benutzerdefinierte Zeit'}</h3>
                <div class="time-input-container">
                    <div class="time-input-group">
                        <label for="time-date">${t('date') || 'Datum'}:</label>
                        <input type="date" id="time-date" value="${year}-${month}-${day}">
                    </div>
                    <div class="time-input-group">
                        <label for="time-time">${t('time') || 'Zeit'}:</label>
                        <input type="time" id="time-time" value="${hours}:${minutes}">
                    </div>
                </div>
                <div class="time-dialog-buttons">
                    <button id="time-reset" class="time-dialog-btn">${t('sim_time_reset') || 'Zurücksetzen'}</button>
                    <button id="time-apply" class="time-dialog-btn time-apply-btn">${t('apply') || 'Anwenden'}</button>
                </div>
            </div>
        `;

        // Füge Dialog zum Body hinzu
        document.body.appendChild(this.dialogElement);

        // Event-Listener für Schließen-Button
        const closeButton = this.dialogElement.querySelector('.dialog-close');
        closeButton.addEventListener('click', () => this.close());

        // Event-Listener für Klick außerhalb des Dialogs
        this.dialogElement.addEventListener('click', (e) => {
            if (e.target === this.dialogElement) {
                this.close();
            }
        });

        // Event-Listener für Zurücksetzen-Button
        const resetButton = document.getElementById('time-reset');
        resetButton.addEventListener('click', () => {
            this.applyTime(0);
            this.close();
        });

        // Event-Listener für Anwenden-Button
        const applyButton = document.getElementById('time-apply');
        applyButton.addEventListener('click', () => {
            this.applyCustomTime();
        });
    }

    close() {
        if (this.dialogElement) {
            this.dialogElement.remove();
            this.dialogElement = null;
        }
    }

    applyCustomTime() {
        try {
            const dateInput = document.getElementById('time-date');
            const timeInput = document.getElementById('time-time');
            
            if (!dateInput || !timeInput) return;
            
            const dateValue = dateInput.value;
            const timeValue = timeInput.value;
            
            if (!dateValue || !timeValue) {
                alert(t('invalid_time_input') || 'Bitte geben Sie ein gültiges Datum und eine gültige Zeit ein.');
                return;
            }
            
            const tz = getLocationTimezone();

            // Erstelle ein Datum-Objekt aus den Eingaben
            // Die Eingabe soll in der Standort-Zeitzone interpretiert werden (nicht Browser-Zone)
            let selectedMillis;
            if (tz) {
                const [y, m, d] = dateValue.split('-').map(Number);
                const [hh, mm] = timeValue.split(':').map(Number);
                selectedMillis = zonedDateTimeToUtcMillis({ year: y, month: m, day: d, hour: hh, minute: mm }, tz);
            } else {
                // Fallback: Browser-lokal
                selectedMillis = new Date(`${dateValue}T${timeValue}`).getTime();
            }

            // Berechne den Offset in Minuten zur aktuellen Zeit (epoch-basiert)
            const nowMillis = Date.now();
            const offsetMinutes = Math.round((selectedMillis - nowMillis) / 60000);
            
            // Wende den Offset an
            this.applyTime(offsetMinutes);
            this.close();
        } catch (error) {
            console.error('Error applying custom time:', error);
            alert(t('time_input_error') || 'Fehler bei der Zeiteingabe. Bitte versuchen Sie es erneut.');
        }
    }

    applyTime(offsetMinutes) {
        // Setze den Offset in den Einstellungen
        settingsManager.setSimulatedTime(offsetMinutes);
        
        // Rufe den Callback auf, wenn vorhanden
        if (typeof this.onTimeChange === 'function') {
            this.onTimeChange(offsetMinutes);
        }
    }
}
