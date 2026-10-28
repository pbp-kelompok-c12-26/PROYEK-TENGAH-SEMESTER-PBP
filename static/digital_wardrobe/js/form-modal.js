/* Modal tambah / edit pakaian & outfit (tanpa reload).
   Pemicu: tombol ber-atribut data-open-modal="<url form>".
   Server: views.item_create/item_update/outfit_create/outfit_update membalas JSON
   { ok, modal_html | card_html, pk?, kind?, total_items?, total_outfits?, message }. */
import { getJson, postForm } from './http.js';
import { toast } from './toast.js';

const MAX_SIZE = 5 * 1024 * 1024;   // sama dengan batas di forms.py
// Dicari ulang setiap dipakai: HTMX bisa mengganti isi <body> (tombol Back / riwayat)
const getRoot = () => document.getElementById('modal-root');
let lastTrigger = null;

function close() {
    const root = getRoot();
    if (!root?.innerHTML) return;
    root.innerHTML = '';
    document.body.classList.remove('wd-no-scroll');
    lastTrigger?.focus();
}

function show(html) {
    const root = getRoot();
    root.innerHTML = html;
    document.body.classList.add('wd-no-scroll');   // kunci scroll halaman di belakang modal
    bindForm(root.querySelector('[data-item-form]'));
    root.querySelector('input:not([type=hidden]):not(.wd-sr-only), select, textarea')?.focus();
}

export async function open(url) {
    try {
        const { data, denied } = await getJson(url);
        if (denied) return;   // pesan 401/403/429 sudah ditampilkan oleh http.js
        if (!data?.modal_html) {
            toast(data?.message || 'Gagal membuka form. Coba lagi.', true);
            return;
        }
        show(data.modal_html);
    } catch (error) {
        toast('Gagal membuka form. Coba lagi.', true);
    }
}

// ---------- Isi form ----------
function bindSizeFields(form) {
    // Form pakaian: sepatu pakai ukuran angka (EU), selain itu XS–XXL
    const category = form.querySelector('select[name=category]');
    const sizeField = form.querySelector('[data-size-field]');
    const shoeField = form.querySelector('[data-shoe-field]');
    if (!category || !sizeField || !shoeField) return;
    const sync = () => {
        const isShoe = category.value === 'footwear';
        sizeField.hidden = isShoe;
        shoeField.hidden = !isShoe;
    };
    category.addEventListener('change', sync);
    sync();
}

function bindOutfitPicks(form) {
    // Form outfit: batasi pilihan maksimal N pakaian
    const picks = form.querySelectorAll('[data-pick]');
    if (!picks.length) return;
    const max = parseInt(form.dataset.maxItems, 10) || 5;
    const counter = form.querySelector('[data-picked-count]');
    const refresh = () => {
        const checked = form.querySelectorAll('[data-pick]:checked').length;
        counter.textContent = checked;
        picks.forEach((cb) => { cb.disabled = !cb.checked && checked >= max; });
    };
    picks.forEach((cb) => cb.addEventListener('change', refresh));
    refresh();
}

function bindImagePreview(form) {
    const input = form.querySelector('input[type=file]');
    if (!input) return;
    const preview = form.querySelector('[data-image-preview]');
    const placeholder = form.querySelector('[data-image-placeholder]');
    const fileName = form.querySelector('[data-image-name]');
    input.addEventListener('change', () => {
        const file = input.files[0];
        if (!file) return;
        if (file.size > MAX_SIZE) {
            toast('Ukuran foto maksimal 5 MB.', true);
            input.value = '';
            return;
        }
        preview.src = URL.createObjectURL(file);
        preview.hidden = false;
        placeholder.hidden = true;
        fileName.textContent = file.name;
    });
}

// ---------- Hasil simpan ----------
function setTotals(data, kind) {
    const total = kind === 'outfit' ? data.total_outfits : data.total_items;
    if (total === undefined) return;
    document.querySelectorAll(kind === 'outfit' ? '[data-total-outfits]' : '[data-total-items]')
        .forEach((el) => { el.textContent = total; });
}

function applySaved(data) {
    const kind = data.kind || 'item';
    if (data.pk) {
        // Edit: ganti kartu di grid, atau muat ulang halaman detail
        const card = document.getElementById(`${kind}-${data.pk}`);
        if (!card) {
            window.location.reload();
            return;
        }
        card.outerHTML = data.card_html;
        toast(data.message);
        return;
    }
    // Tambah: kartu baru langsung muncul di grid tanpa reload
    const grid = document.getElementById(`${kind}-grid`);
    if (!grid) {
        window.location.href = data.redirect || getRoot().dataset.indexUrl;
        return;
    }
    grid.insertAdjacentHTML('afterbegin', data.card_html);
    grid.hidden = false;
    document.getElementById(`${kind}-empty-state`)?.remove();
    setTotals(data, kind);
    toast(data.message);
}

function bindForm(form) {
    if (!form) return;
    bindSizeFields(form);
    bindOutfitPicks(form);
    bindImagePreview(form);
    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const submit = form.querySelector('[data-submit]');
        submit.disabled = true;
        try {
            const { data, denied } = await postForm(form.action, new FormData(form));
            if (denied) return;   // form tetap terbuka supaya isian tidak hilang
            if (!data?.ok) {
                if (data?.modal_html) show(data.modal_html);   // ada error: tampilkan form + pesan
                else { close(); toast(data?.message || 'Gagal menyimpan.', true); }
                return;
            }
            close();
            applySaved(data);
        } catch (error) {
            toast('Gagal menyimpan. Periksa koneksi lalu coba lagi.', true);
        } finally {
            submit.disabled = false;
        }
    });
}

export function init() {
    if (!getRoot()) return;

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-open-modal]');
        if (trigger) {
            lastTrigger = trigger;
            open(trigger.dataset.openModal);
            return;
        }
        if (event.target.closest('[data-close-modal]')) close();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
    });

    // Buka modal otomatis dari ?add=1, ?edit=<id>, ?add_outfit=1, ?edit_outfit=<id>
    const autoOpen = document.querySelector('[data-auto-open]')?.dataset.autoOpen;
    if (autoOpen) open(autoOpen);
}
