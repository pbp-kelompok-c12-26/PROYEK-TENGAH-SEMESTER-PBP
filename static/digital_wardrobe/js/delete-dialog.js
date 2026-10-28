/* Pop-up konfirmasi hapus 1 pakaian / 1 outfit.
   Pemicu: tombol ber-atribut data-delete-url (+ data-delete-name, data-delete-kind, ...).
   Markup: templates/digital_wardrobe/partials/delete_modal.html

   Di grid Lemari (tombol punya data-delete-card="<id kartu>") penghapusan memakai HTMX:
   - optimistic UI: kartu langsung memudar (class is-removing) begitu "Ya, hapus" diklik;
   - server membalas kosong -> HTMX mengganti kartu dengan kosong (kartu hilang, animasi htmx-swapping);
   - server menolak -> balasannya kartu itu lagi, jadi kartu kembali seperti semula;
   - toast & angka total diurus htmx-events.js (event wardrobe:deleted / wardrobe:delete-failed).
   Di halaman detail (tanpa kartu) form dikirim biasa lalu server redirect ke Lemari. */

// Elemen dicari ulang setiap dipakai: HTMX bisa mengganti isi <body> (tombol Back / riwayat)
const getModal = () => document.getElementById('delete-modal');
let lastTrigger = null;
let pendingCardId = '';

function deleteWithHtmx(form) {
    const card = pendingCardId && document.getElementById(pendingCardId);
    if (!card || !window.htmx) return false;
    card.classList.add('is-removing');   // optimistic UI
    window.htmx.ajax('POST', form.action, {
        source: card,
        target: card,
        swap: 'outerHTML swap:250ms',
        headers: { 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value },
    });
    return true;
}

function setText(modal, selector, value) {
    const el = modal.querySelector(selector);
    if (el) el.textContent = value;
}

function open(trigger) {
    const modal = getModal();
    if (!modal) return;
    const { deleteUrl, deleteName, deleteKind = 'item', deleteCard = '' } = trigger.dataset;
    pendingCardId = deleteCard;
    const outfitCount = parseInt(trigger.dataset.deleteOutfits, 10) || 0;
    const upcoming = parseInt(trigger.dataset.deleteUpcoming, 10) || 0;
    const history = parseInt(trigger.dataset.deleteHistory, 10) || 0;

    modal.querySelector('[data-delete-form]').action = deleteUrl;
    setText(modal, '[data-delete-name]', deleteName);
    setText(modal, '[data-delete-title]', deleteKind === 'outfit' ? 'Yakin hapus outfit ini?' : 'Yakin hapus pakaian ini?');
    modal.querySelectorAll('[data-delete-desc]').forEach((el) => { el.hidden = el.dataset.deleteDesc !== deleteKind; });

    setText(modal, '[data-delete-outfits]', outfitCount);
    modal.querySelector('[data-delete-outfit-note]').hidden = !(deleteKind === 'item' && outfitCount > 0);

    // Peringatan jadwal Kalender Outfit saat menghapus outfit
    const scheduleNote = modal.querySelector('[data-delete-schedule-note]');
    if (scheduleNote) {
        setText(modal, '[data-delete-upcoming]', upcoming);
        setText(modal, '[data-delete-history]', history);
        scheduleNote.querySelector('[data-delete-upcoming-text]').hidden = upcoming === 0;
        scheduleNote.querySelector('[data-delete-history-text]').hidden = history === 0;
        scheduleNote.hidden = !(deleteKind === 'outfit' && (upcoming > 0 || history > 0));
    }
    modal.hidden = false;
    modal.querySelector('[data-close-delete]').focus();
}

function close() {
    const modal = getModal();
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    lastTrigger?.focus();
}

export function init() {

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-delete-url]');
        if (trigger) {
            lastTrigger = trigger;
            open(trigger);
            return;
        }
        if (event.target.closest('[data-close-delete]')) close();
    });
    document.addEventListener('submit', (event) => {
        if (!event.target.matches('[data-delete-form]') || !pendingCardId) return;   // halaman detail: kirim form biasa
        event.preventDefault();
        getModal().hidden = true;
        if (!deleteWithHtmx(event.target)) event.target.submit();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
    });
}
