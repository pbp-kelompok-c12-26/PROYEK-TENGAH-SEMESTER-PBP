/* Pop-up konfirmasi hapus 1 pakaian / 1 outfit.
   Pemicu: tombol ber-atribut data-delete-url (+ data-delete-name, data-delete-kind, ...).
   Markup: templates/digital_wardrobe/partials/delete_modal.html */

let modal = null;
let lastTrigger = null;

function setText(selector, value) {
    const el = modal.querySelector(selector);
    if (el) el.textContent = value;
}

function open(trigger) {
    const { deleteUrl, deleteName, deleteKind = 'item' } = trigger.dataset;
    const outfitCount = parseInt(trigger.dataset.deleteOutfits, 10) || 0;
    const upcoming = parseInt(trigger.dataset.deleteUpcoming, 10) || 0;
    const history = parseInt(trigger.dataset.deleteHistory, 10) || 0;

    modal.querySelector('[data-delete-form]').action = deleteUrl;
    setText('[data-delete-name]', deleteName);
    setText('[data-delete-title]', deleteKind === 'outfit' ? 'Yakin hapus outfit ini?' : 'Yakin hapus pakaian ini?');
    modal.querySelectorAll('[data-delete-desc]').forEach((el) => { el.hidden = el.dataset.deleteDesc !== deleteKind; });

    setText('[data-delete-outfits]', outfitCount);
    modal.querySelector('[data-delete-outfit-note]').hidden = !(deleteKind === 'item' && outfitCount > 0);

    // Peringatan jadwal Kalender Outfit saat menghapus outfit
    const scheduleNote = modal.querySelector('[data-delete-schedule-note]');
    if (scheduleNote) {
        setText('[data-delete-upcoming]', upcoming);
        setText('[data-delete-history]', history);
        scheduleNote.querySelector('[data-delete-upcoming-text]').hidden = upcoming === 0;
        scheduleNote.querySelector('[data-delete-history-text]').hidden = history === 0;
        scheduleNote.hidden = !(deleteKind === 'outfit' && (upcoming > 0 || history > 0));
    }
    modal.hidden = false;
    modal.querySelector('[data-close-delete]').focus();
}

function close() {
    if (modal.hidden) return;
    modal.hidden = true;
    lastTrigger?.focus();
}

export function init() {
    modal = document.getElementById('delete-modal');
    if (!modal) return;

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-delete-url]');
        if (trigger) {
            lastTrigger = trigger;
            open(trigger);
            return;
        }
        if (event.target.closest('[data-close-delete]')) close();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
    });
}
