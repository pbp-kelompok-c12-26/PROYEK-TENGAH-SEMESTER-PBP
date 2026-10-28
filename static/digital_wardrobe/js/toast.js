/* Toast (pesan singkat di bawah layar) untuk halaman Lemari.
   Markup wadahnya: templates/digital_wardrobe/partials/messages.html (#wardrobe-toast). */

const DURATION = 4000;
const PENDING_KEY = 'wardrobe-toast';

const stack = () => document.getElementById('wardrobe-toast');

export function toast(text, isError = false) {
    const box = stack();
    if (!box || !text) return;
    const el = document.createElement('div');
    el.dataset.toast = '';
    el.className = 'wd-toast' + (isError ? ' wd-toast--error' : '');
    el.textContent = text;
    box.appendChild(el);
    setTimeout(() => el.remove(), DURATION);
}

/** Simpan pesan supaya tetap tampil setelah halaman dimuat ulang. */
export function toastAfterReload(text) {
    try { sessionStorage.setItem(PENDING_KEY, text); } catch (error) { /* storage tidak tersedia */ }
}

export function initToasts() {
    // Pesan dari Django messages (sudah ada di HTML) hilang sendiri
    stack()?.querySelectorAll('[data-toast]').forEach((el) => setTimeout(() => el.remove(), DURATION));
    try {
        const pending = sessionStorage.getItem(PENDING_KEY);
        if (pending) {
            sessionStorage.removeItem(PENDING_KEY);
            toast(pending);
        }
    } catch (error) { /* storage tidak tersedia */ }
}
