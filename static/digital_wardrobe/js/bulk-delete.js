/* Hapus banyak pakaian sekaligus (mode "Pilih" di tab Pakaian).
   Markup : templates/digital_wardrobe/partials/bulk_delete.html (+ checkbox di item_card.html)
   Server : views.item_bulk_delete -> { ok, removed: [id], skipped: [id], total_items, message }
   Gaya   : .wd-select-mode, .wd-bulkbar, .wd-card__check di wardrobe.css

   1. Tombol "Pilih" menyalakan mode pilih (class wd-select-mode di <body>);
      klik di mana saja pada kartu = centang pakaian itu.
   2. "Hapus terpilih" membuka pop-up konfirmasi.
   3. Optimistic UI: kartu langsung memudar, lalu hilang kalau server berhasil.
      Yang dilewati server (mis. sedang dipakai swap request) atau gagal dikembalikan.
   Elemen dicari ulang setiap kali dipakai, jadi tetap jalan setelah grid diganti (filter tanpa reload). */
import { postForm } from './http.js';
import { toast } from './toast.js';
import { gridNeedsRefresh, refreshList, removeCard, updateItemCounters } from './cards.js';

const body = document.body;
const el = {
    form: () => document.querySelector('[data-bulk-form]'),
    grid: () => document.getElementById('item-grid'),
    modal: () => document.getElementById('bulk-delete-modal'),
};
let lastFocus = null;

const boxes = () => [...(el.grid()?.querySelectorAll('[data-select-item]') || [])];
const enabledBoxes = () => boxes().filter((box) => !box.disabled);
const checkedBoxes = () => boxes().filter((box) => box.checked);
const cardOf = (box) => box.closest('[data-item-card]');
const isSelecting = () => body.classList.contains('wd-select-mode');

export function refresh() {
    const form = el.form();
    if (!form) return;
    const checked = checkedBoxes();
    boxes().forEach((box) => cardOf(box)?.classList.toggle('is-selected', box.checked));
    form.querySelector('[data-bulk-count]').textContent = checked.length;
    form.querySelector('[data-bulk-submit]').disabled = checked.length === 0;
    const enabled = enabledBoxes();
    const allChecked = enabled.length > 0 && enabled.every((box) => box.checked);
    form.querySelector('[data-bulk-all]').textContent = allChecked ? 'Batalkan pilihan' : 'Pilih semua';
}

export function setSelectMode(on) {
    body.classList.toggle('wd-select-mode', on && Boolean(el.form()));
    document.querySelectorAll('.wd-chip--select').forEach((chip) => {
        chip.setAttribute('aria-pressed', String(on));
        chip.classList.toggle('is-active', on);
        const label = chip.querySelector('[data-select-label]');
        if (label) label.textContent = on ? 'Selesai' : 'Pilih';
    });
    if (!on) boxes().forEach((box) => { box.checked = false; });
    refresh();
}

// ---------- Konfirmasi ----------
function openConfirm() {
    const modal = el.modal();
    lastFocus = document.activeElement;
    modal.querySelector('[data-bulk-total]').textContent = checkedBoxes().length;
    modal.hidden = false;
    modal.querySelector('[data-close-bulk]').focus();
}

function closeConfirm() {
    const modal = el.modal();
    if (!modal || modal.hidden) return false;
    modal.hidden = true;
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
    return true;
}

// ---------- Kirim ke server ----------
async function sendDelete() {
    closeConfirm();
    const form = el.form();
    const cards = checkedBoxes().map(cardOf).filter(Boolean);
    cards.forEach((card) => card.classList.add('is-removing'));   // optimistic UI: langsung memudar
    form.querySelector('[data-bulk-submit]').disabled = true;
    let failMessage = 'Gagal menghapus pakaian. Periksa koneksi lalu coba lagi.';

    try {
        // FormData ikut membawa checkbox ber-atribut form="bulk-delete-form" + token CSRF
        const { response, data, denied } = await postForm(form.action, new FormData(form));
        if (denied) failMessage = '';   // pesan 401/403/429 sudah ditampilkan oleh http.js
        if (!response.ok || !data?.ok) {
            failMessage = failMessage && (data?.message || failMessage);
            throw new Error(failMessage);
        }
        const removed = new Set(data.removed.map(String));
        cards.forEach((card) => {
            if (removed.has(card.dataset.itemCard)) removeCard(card);
            else card.classList.remove('is-removing');   // dilewati server: kembalikan
        });
        updateItemCounters(removed.size, data.total_items);
        toast(data.message, removed.size === 0);
        setSelectMode(false);
        // Grid kosong / masih ada halaman berikutnya: ambil ulang daftar (HTMX, tanpa reload)
        setTimeout(() => {
            if (removed.size && gridNeedsRefresh(el.grid())) refreshList();
        }, 450);
    } catch (error) {
        cards.forEach((card) => card.classList.remove('is-removing'));   // gagal: kembalikan semua
        if (failMessage) toast(failMessage, true);
        refresh();
    }
}

// ---------- Event ----------
function onClick(event) {
    if (event.target.closest('[data-select-toggle]')) {
        setSelectMode(!isSelecting());
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
    if (event.target.closest('[data-bulk-all]')) {
        const enabled = enabledBoxes();
        const check = !enabled.every((box) => box.checked);
        enabled.forEach((box) => { box.checked = check; });
        refresh();
        return;
    }
    // Mode pilih: klik di mana saja pada kartu = centang pakaian itu (bukan buka detail/edit)
    if (!isSelecting()) return;
    const card = event.target.closest('[data-item-card]');
    if (!card || !el.grid()?.contains(card)) return;
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
}

export function init() {
    document.addEventListener('click', onClick, true);   // fase capture: dicegat sebelum link/tombol di kartu bereaksi
    document.addEventListener('change', (event) => {
        if (event.target.matches('[data-select-item]')) refresh();
    });
    document.addEventListener('submit', (event) => {
        if (!event.target.matches('[data-bulk-form]')) return;
        event.preventDefault();
        if (checkedBoxes().length) openConfirm();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        if (!closeConfirm() && isSelecting()) setSelectMode(false);
    });
    refresh();
}
