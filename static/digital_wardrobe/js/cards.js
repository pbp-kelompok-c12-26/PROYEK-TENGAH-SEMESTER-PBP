/* Bantuan DOM untuk kartu pakaian/outfit di grid Lemari. */

/** Hilangkan kartu dengan animasi (class is-gone di wardrobe.css). */
export function removeCard(card) {
    card.addEventListener('transitionend', () => card.remove(), { once: true });
    card.classList.add('is-gone');
    setTimeout(() => card.remove(), 400);   // cadangan kalau transitionend tidak terpicu
}

/** Perbarui angka total di header & teks "Menampilkan x dari y" setelah kartu dihapus. */
export function updateItemCounters(removedCount, totalItems) {
    setTotal('item', totalItems);
    document.querySelectorAll('[data-shown-count], [data-filtered-total]').forEach((el) => {
        el.textContent = Math.max(0, (parseInt(el.textContent, 10) || 0) - removedCount);
    });
}

/** Angka total di kartu statistik atas (kind: 'item' | 'outfit'). */
export function setTotal(kind, total) {
    if (total === undefined || total === null) return;
    document.querySelectorAll(kind === 'outfit' ? '[data-total-outfits]' : '[data-total-items]')
        .forEach((el) => { el.textContent = total; });
}

/** Grid perlu dimuat ulang: kosong (perlu pesan kosong) atau masih ada halaman berikutnya. */
export function gridNeedsRefresh(grid) {
    return !grid?.querySelector('[data-item-card], [data-outfit-card]') || Boolean(document.querySelector('.wd-btn-more'));
}

/**
 * Ambil ulang daftar dari server lewat HTMX (tanpa reload halaman), mis. setelah grid kosong
 * atau supaya kartu dari halaman berikutnya ikut naik. Tab Pakaian: #wardrobe-results,
 * tab Outfit: #wardrobe-content. Tanpa HTMX: muat ulang halaman.
 */
export function refreshList() {
    const target = document.getElementById('wardrobe-results') ? '#wardrobe-results' : '#wardrobe-content';
    if (window.htmx && document.querySelector(target)) {
        window.htmx.ajax('GET', window.location.href, { target, swap: 'outerHTML' });
    } else {
        window.location.reload();
    }
}
