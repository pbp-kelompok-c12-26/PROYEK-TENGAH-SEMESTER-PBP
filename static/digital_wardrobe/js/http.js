/* Bantuan request ke server (fetch) untuk modul Lemari.
   - Header X-Requested-With membuat view Django membalas JSON (views.is_ajax, security.wants_json).
   - Penolakan dari digital_wardrobe/security.py ditangani di satu tempat (handleDenied):
       401 sesi habis       -> toast lalu diarahkan ke halaman login
       403 bukan miliknya   -> toast "Kamu tidak punya akses ..."
       429 terlalu sering   -> toast "Coba lagi dalam N detik" */
import { toast } from './toast.js';

const AJAX_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };
const DENIED_MESSAGES = {
    401: 'Sesi kamu sudah habis. Silakan masuk lagi.',
    403: 'Kamu tidak punya akses ke data ini.',
    429: 'Terlalu banyak permintaan. Coba lagi sebentar lagi.',
};

/** Baca JSON dari respons; null kalau bukan JSON (mis. halaman error). */
async function readJson(response) {
    try { return await response.json(); } catch (error) { return null; }
}

/**
 * Tampilkan pesan penolakan (401/403/429). Mengembalikan true kalau status memang penolakan,
 * supaya pemanggil tidak menampilkan pesan "gagal" kedua. Dipakai juga oleh htmx-events.js.
 */
export function handleDenied(status, data) {
    if (!(status in DENIED_MESSAGES)) return false;
    toast(data?.message || DENIED_MESSAGES[status], true);
    if (status === 401) {
        setTimeout(() => window.location.assign(data?.login_url || '/accounts/login/'), 1500);
    }
    return true;
}

async function send(url, options) {
    const response = await fetch(url, { credentials: 'same-origin', ...options, headers: AJAX_HEADERS });
    const data = await readJson(response);
    return { response, data, denied: handleDenied(response.status, data) };
}

export function getJson(url) {
    return send(url, {});
}

/** Kirim form (FormData sudah membawa csrfmiddlewaretoken dari {% csrf_token %}). */
export function postForm(url, formData) {
    return send(url, { method: 'POST', body: formData });
}
