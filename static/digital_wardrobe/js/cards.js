/* Bantuan DOM untuk kartu pakaian/outfit di grid Lemari. */

/** Hilangkan kartu dengan animasi (class is-gone di wardrobe.css). */
export function removeCard(card) {
    card.addEventListener('transitionend', () => card.remove(), { once: true });
    card.classList.add('is-gone');
    setTimeout(() => card.remove(), 400);   // cadangan kalau transitionend tidak terpicu
}

/** Perbarui angka total di header & teks "Menampilkan x dari y" setelah kartu dihapus. */
export function updateItemCounters(removedCount, totalItems) {
    if (totalItems !== undefined) {
        document.querySelectorAll('[data-total-items]').forEach((el) => { el.textContent = totalItems; });
    }
    document.querySelectorAll('[data-shown-count], [data-filtered-total]').forEach((el) => {
        el.textContent = Math.max(0, (parseInt(el.textContent, 10) || 0) - removedCount);
    });
}

/** Grid perlu dimuat ulang: kosong (perlu pesan kosong) atau masih ada halaman berikutnya. */
export function gridNeedsRefresh(grid) {
    return !grid?.querySelector('[data-item-card], [data-outfit-card]') || Boolean(document.querySelector('.wd-btn-more'));
}
