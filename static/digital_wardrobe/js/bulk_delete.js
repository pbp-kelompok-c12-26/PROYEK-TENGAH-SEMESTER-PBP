/* =========================================================
   Lemari Saya: hapus banyak pakaian sekaligus (mode "Pilih")
   ---------------------------------------------------------
   Markup : templates/digital_wardrobe/partials/bulk_delete.html (+ checkbox di item_card.html)
   Server : digital_wardrobe.views.item_bulk_delete (aturan hapus tetap dicek di server)
   Gaya   : .wd-select-mode, .wd-bulkbar, .wd-card__check di wardrobe.css

   Alur:
   1. Tombol "Pilih" menyalakan mode pilih (class wd-select-mode di <body>).
      Klik kartu = centang/batal centang pakaian itu.
   2. "Hapus terpilih" membuka pop-up konfirmasi.
   3. Setelah dikonfirmasi, kartu langsung memudar (optimistic UI) dan data dikirim
      lewat fetch(). Kartu yang berhasil dihapus dihilangkan; yang dilewati server
      (mis. sedang dipakai swap request) atau gagal dikembalikan seperti semula.
   ========================================================= */
(() => {
    const toast = (text, isError) => (window.WardrobeToast ? window.WardrobeToast(text, isError) : alert(text));

    // Pesan dari penghapusan sebelum halaman dimuat ulang (lemari bisa saja sudah kosong)
    try {
        const pending = sessionStorage.getItem('wardrobe-toast');
        if (pending) {
            sessionStorage.removeItem('wardrobe-toast');
            toast(pending);
        }
    } catch (storageError) { /* sessionStorage tidak tersedia */ }

    const form = document.querySelector('[data-bulk-form]');
    const grid = document.getElementById('item-grid');
    const modal = document.getElementById('bulk-delete-modal');
    if (!form || !grid || !modal) return;

    const body = document.body;
    const countEl = form.querySelector('[data-bulk-count]');
    const submitBtn = form.querySelector('[data-bulk-submit]');
    const allBtn = form.querySelector('[data-bulk-all]');
    let lastFocus = null;

    const boxes = () => [...grid.querySelectorAll('[data-select-item]')];
    const enabledBoxes = () => boxes().filter((box) => !box.disabled);
    const checkedBoxes = () => boxes().filter((box) => box.checked);
    const cardOf = (box) => box.closest('[data-item-card]');

    // ---------- Mode pilih ----------
    function setSelectMode(on) {
        body.classList.toggle('wd-select-mode', on);
        document.querySelectorAll('.wd-chip--select').forEach((chip) => {
            chip.setAttribute('aria-pressed', String(on));
            chip.classList.toggle('is-active', on);
            const label = chip.querySelector('[data-select-label]');
            if (label) label.textContent = on ? 'Selesai' : 'Pilih';
        });
        if (!on) boxes().forEach((box) => { box.checked = false; });
        refresh();
    }

    function refresh() {
        const checked = checkedBoxes();
        boxes().forEach((box) => cardOf(box)?.classList.toggle('is-selected', box.checked));
        countEl.textContent = checked.length;
        submitBtn.disabled = checked.length === 0;
        const enabled = enabledBoxes();
        const allChecked = enabled.length > 0 && enabled.every((box) => box.checked);
        allBtn.textContent = allChecked ? 'Batalkan pilihan' : 'Pilih semua';
    }

    // ---------- Konfirmasi ----------
    function openConfirm() {
        lastFocus = document.activeElement;
        modal.querySelector('[data-bulk-total]').textContent = checkedBoxes().length;
        modal.hidden = false;
        modal.querySelector('[data-close-bulk]').focus();
    }

    function closeConfirm() {
        modal.hidden = true;
        if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
    }

    // ---------- Kirim ke server ----------
    function updateCounters(removedCount, totalItems) {
        document.querySelectorAll('[data-total-items]').forEach((el) => { el.textContent = totalItems; });
        document.querySelectorAll('[data-shown-count], [data-filtered-total]').forEach((el) => {
            el.textContent = Math.max(0, (parseInt(el.textContent, 10) || 0) - removedCount);
        });
    }

    async function sendDelete() {
        closeConfirm();
        const selected = checkedBoxes();
        const cards = selected.map(cardOf).filter(Boolean);
        cards.forEach((card) => card.classList.add('is-removing'));   // optimistic UI: langsung memudar
        submitBtn.disabled = true;
        let failMessage = 'Gagal menghapus pakaian. Periksa koneksi lalu coba lagi.';

        try {
            const response = await fetch(form.action, {
                method: 'POST',
                body: new FormData(form),   // ikut membawa checkbox ber-atribut form="bulk-delete-form" + CSRF
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            let data = null;
            try { data = await response.json(); } catch (parseError) { /* bukan JSON, mis. halaman error */ }
            if (!response.ok || !data || !data.ok) {
                failMessage = (data && data.message) || failMessage;
                throw new Error(failMessage);
            }

            const removed = new Set(data.removed.map(String));
            cards.forEach((card) => {
                if (removed.has(card.dataset.itemCard)) {
                    card.addEventListener('transitionend', () => card.remove(), { once: true });
                    card.classList.add('is-gone');
                    setTimeout(() => card.remove(), 400);   // cadangan kalau transitionend tidak terpicu
                } else {
                    card.classList.remove('is-removing');   // dilewati server: kembalikan
                }
            });
            updateCounters(removed.size, data.total_items);
            toast(data.message, removed.size === 0);
            setSelectMode(false);
            // Grid kosong (atau masih ada halaman berikutnya): muat ulang supaya daftar & pesan kosong benar
            setTimeout(() => {
                if (!grid.querySelector('[data-item-card]') || document.querySelector('.wd-btn-more')) {
                    if (!removed.size) return;
                    // Simpan pesan supaya tetap muncul setelah halaman dimuat ulang
                    try { sessionStorage.setItem('wardrobe-toast', data.message); } catch (storageError) { /* abaikan */ }
                    window.location.reload();
                }
            }, 450);
        } catch (error) {
            cards.forEach((card) => card.classList.remove('is-removing'));   // gagal: kembalikan semua
            toast(failMessage, true);
            refresh();
        }
    }

    // ---------- Event ----------
    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-select-toggle]')) {
            setSelectMode(!body.classList.contains('wd-select-mode'));
            return;
        }
        if (event.target.closest('[data-close-bulk]')) {
            closeConfirm();
            return;
        }
        if (event.target.closest('[data-bulk-confirm]')) {
            sendDelete();
            return;
        }
        // Mode pilih: klik di mana saja pada kartu = centang pakaian itu (bukan buka detail/edit)
        if (!body.classList.contains('wd-select-mode')) return;
        const card = event.target.closest('[data-item-card]');
        if (!card || !grid.contains(card)) return;
        const box = card.querySelector('[data-select-item]');
        if (event.target === box) return;   // klik langsung di checkbox: biarkan bawaan browser
        event.preventDefault();
        event.stopPropagation();
        if (box.disabled) {
            toast('Pakaian ini sedang dipakai dalam swap request, jadi belum bisa dihapus.', true);
            return;
        }
        box.checked = !box.checked;
        refresh();
    }, true);   // fase capture: dicegat sebelum link/tombol di kartu bereaksi

    grid.addEventListener('change', (event) => {
        if (event.target.matches('[data-select-item]')) refresh();
    });

    allBtn.addEventListener('click', () => {
        const enabled = enabledBoxes();
        const check = !enabled.every((box) => box.checked);
        enabled.forEach((box) => { box.checked = check; });
        refresh();
    });

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        if (checkedBoxes().length) openConfirm();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        if (!modal.hidden) closeConfirm();
        else if (body.classList.contains('wd-select-mode')) setSelectMode(false);
    });

    refresh();
})();
