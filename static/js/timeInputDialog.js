import { t } from './i18n.js';
import { settingsManager } from './settings.js';

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
        const currentDate = new Date(Date.now() + offsetMinutes * 60000);
        
        // Formatiere Datum und Zeit für die Eingabefelder
        const year = currentDate.getFullYear();
        const month = String(currentDate.getMonth() + 1).padStart(2, '0');
        const day = String(currentDate.getDate()).padStart(2, '0');
        const hours = String(currentDate.getHours()).padStart(2, '0');
        const minutes = String(currentDate.getMinutes()).padStart(2, '0');
        
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
            
            // Erstelle ein Datum-Objekt aus den Eingaben
            const selectedDate = new Date(`${dateValue}T${timeValue}`);
            
            // Berechne den Offset in Minuten zur aktuellen Zeit
            const now = new Date();
            const offsetMinutes = Math.round((selectedDate - now) / 60000);
            
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
