// One modal <dialog> with a title bar and a close button.  Esc and a click on
// the backdrop close it (the browser handles Esc for showModal()).
import { el } from './dom.js';
import { t } from '../i18n.js';

export class AppDialog {
    constructor(id, extraClass = '') {
        this.titleEl = el('h2', { id: `${id}-title`, class: 'dialog-title' });
        this.closeBtn = el('button', {
            type: 'button', class: 'icon-btn dialog-close', onclick: () => this.close(),
        }, '×');
        this.body = el('div', { class: 'dialog-body' });
        this.dialog = el('dialog', {
            id, class: `app-dialog ${extraClass}`.trim(), 'aria-labelledby': `${id}-title`,
        }, el('div', { class: 'dialog-frame' },
            el('header', { class: 'dialog-head' }, this.titleEl, this.closeBtn),
            this.body));
        this.dialog.addEventListener('click', (e) => {
            if (e.target === this.dialog) this.close();
        });
        this.dialog.addEventListener('close', () => this.onClose?.());
        document.body.append(this.dialog);
    }

    setTitle(text) {
        this.titleEl.textContent = text;
        this.closeBtn.setAttribute('aria-label', t('close_label'));
        this.closeBtn.title = t('close_label');
    }

    /** Replace the body's content. */
    setBody(...nodes) {
        this.body.replaceChildren(...nodes.flat());
    }

    open() {
        if (!this.dialog.open) this.dialog.showModal();
    }

    close() {
        if (this.dialog.open) this.dialog.close();
    }

    get isOpen() {
        return this.dialog.open;
    }
}

/** A status line inside a dialog (errors, progress). */
export function statusLine() {
    return el('p', { class: 'dialog-status', role: 'status', 'aria-live': 'polite' });
}
