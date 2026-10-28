/* Reaksi halaman terhadap request HTMX di Lemari.
   - Header HX-Trigger dari server (views.hx_response):
       wardrobe:deleted       { kind, message, total }  -> toast, angka total, ambil ulang daftar kalau perlu
       wardrobe:delete-failed { message }               -> toast error
   - Request gagal (koneksi putus / error server): kartu yang memudar dikembalikan.
   - Sebelum filter / pindah tab: mode "Pilih" dimatikan; sesudahnya bar hapus banyak disegarkan. */
import { toast } from './toast.js';
import { gridNeedsRefresh, refreshList, setTotal, updateItemCounters } from './cards.js';
import * as bulkDelete from './bulk-delete.js';

const LIST_TARGETS = ['wardrobe-results', 'wardrobe-content'];

export function init() {
    document.addEventListener('wardrobe:deleted', (event) => {
        const { kind, message, total } = event.detail;
        toast(message);
        if (kind === 'outfit') setTotal('outfit', total);
        else updateItemCounters(1, total);
        // Tunggu animasi swap selesai, lalu cek apakah daftar perlu diambil ulang
        setTimeout(() => {
            const grid = document.getElementById(kind === 'outfit' ? 'outfit-grid' : 'item-grid');
            if (gridNeedsRefresh(grid)) refreshList();
        }, 350);
    });

    document.addEventListener('wardrobe:delete-failed', (event) => {
        toast(event.detail.message, true);
    });

    const restoreCards = () => {
        document.querySelectorAll('.wd-card.is-removing').forEach((card) => card.classList.remove('is-removing'));
    };
    document.addEventListener('htmx:responseError', () => {
        restoreCards();
        toast('Terjadi kesalahan di server. Coba lagi.', true);
    });
    document.addEventListener('htmx:sendError', () => {
        restoreCards();
        toast('Gagal terhubung. Periksa koneksi lalu coba lagi.', true);
    });

    document.addEventListener('htmx:beforeRequest', (event) => {
        if (LIST_TARGETS.includes(event.detail.target?.id)) bulkDelete.setSelectMode(false);
    });
    document.addEventListener('htmx:afterSettle', () => bulkDelete.refresh());
    // Sebelum HTMX menyimpan salinan halaman untuk tombol Back: bersihkan keadaan sementara
    document.addEventListener('htmx:beforeHistorySave', () => {
        bulkDelete.setSelectMode(false);
        restoreCards();
        document.querySelectorAll('#wardrobe-toast [data-toast]').forEach((el) => el.remove());
        const modal = document.getElementById('delete-modal');
        if (modal) modal.hidden = true;
        const root = document.getElementById('modal-root');
        if (root) root.innerHTML = '';
    });
    document.addEventListener('htmx:historyRestore', () => {
        bulkDelete.setSelectMode(false);
        document.body.classList.remove('wd-no-scroll');
    });
}
