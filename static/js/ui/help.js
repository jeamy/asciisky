// Help dialog; every text comes from i18n.js (D7).
import { t } from '../i18n.js';
import { GRID_SYMBOLS, MOON_PHASE_SYMBOLS } from '../constants.js';
import { el } from './dom.js';
import { AppDialog } from './dialog.js';

const REPO_URL = 'https://github.com/jeamy/asciisky';

let dialog = null;

function section(titleKey, ...content) {
    return el('section', { class: 'help-section' }, el('h3', {}, t(titleKey)), content);
}

function items(pairs) {
    return el('dl', { class: 'help-list' }, pairs.map(([term, key]) => [el('dt', {}, term), el('dd', {}, t(key))]));
}

export function openHelp() {
    if (!dialog) dialog = new AppDialog('help-dialog', 'dialog-wide');
    dialog.setTitle(t('help_title'));
    const symbols = [
        [GRID_SYMBOLS.sun, 'sun'], [GRID_SYMBOLS.moon, 'moon'], [GRID_SYMBOLS.mercury, 'mercury'],
        [GRID_SYMBOLS.venus, 'venus'], [GRID_SYMBOLS.mars, 'mars'], [GRID_SYMBOLS.jupiter, 'jupiter'],
        [GRID_SYMBOLS.saturn, 'saturn'], [GRID_SYMBOLS.uranus, 'uranus'], [GRID_SYMBOLS.neptune, 'neptune'],
        [GRID_SYMBOLS.asteroid, 'asteroids'], [GRID_SYMBOLS.comet, 'comets'],
        ['*', 'symbol_several'], ['★', 'symbol_selected'], ['✦ ✧', 'symbol_overlays'],
    ];
    dialog.setBody(
        section('help_sky_view',
            el('p', {}, t('help_sky_view_desc')),
            items([
                [t('horizon_view'), 'help_horizon_desc'],
                [t('planisphere_view'), 'help_planisphere_desc'],
                [t('help_gestures'), 'help_gestures_desc'],
                [t('help_select'), 'help_select_desc'],
            ])),
        section('help_symbols',
            el('ul', { class: 'symbol-table' }, symbols.map(([sym, key]) => el('li', {},
                el('span', { class: 'help-glyph' }, sym), el('span', {}, t(key))))),
            el('p', {}, t('help_moon_phases'), ' ', Object.values(MOON_PHASE_SYMBOLS).join(' '))),
        section('help_toolbar', items([
            ['✦', 'help_layer_constellations'],
            ['✧', 'help_layer_messier'],
            ['☉', 'help_layer_sunpath'],
            ['⌗', 'help_layer_grid'],
            ['− +', 'help_zoom_buttons'],
        ])),
        section('help_time', el('p', {}, t('help_time_desc')), items([
            ['« »', 'help_day_step'],
            ['‹ ›', 'help_hour_step'],
            ['⟳', 'help_now'],
        ])),
        section('help_keyboard', items([
            ['← →', 'help_key_turn'],
            ['+ −', 'help_key_zoom'],
            ['H / P', 'help_key_view'],
            ['[ ]', 'help_hour_step'],
            ['{ }', 'help_day_step'],
            ['T', 'help_now'],
            ['Esc', 'help_key_escape'],
        ])),
        section('help_list', el('p', {}, t('help_list_desc'))),
        section('magnitude_filters', el('p', {}, t('help_filters_desc'))),
        section('help_location', el('p', {}, t('help_location_desc'))),
        section('help_account', el('p', {}, t('help_account_desc1')), el('p', {}, t('help_account_desc2')), el('p', {}, t('help_account_desc3'))),
        section('help_source', el('p', {}, t('help_source_desc'), ' ',
            el('a', { href: REPO_URL, target: '_blank', rel: 'noopener' }, REPO_URL))),
    );
    dialog.open();
}
