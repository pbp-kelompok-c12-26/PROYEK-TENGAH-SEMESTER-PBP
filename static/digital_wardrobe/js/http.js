/* Bantuan request ke server (fetch) untuk modul Lemari.
   Semua request diberi header X-Requested-With supaya view Django membalas JSON (lihat views.is_ajax). */

const AJAX_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };

/** Baca JSON dari respons; null kalau bukan JSON (mis. halaman error). */
async function readJson(response) {
    try { return await response.json(); } catch (error) { return null; }
}

export async function getJson(url) {
    const response = await fetch(url, { headers: AJAX_HEADERS, credentials: 'same-origin' });
    return { response, data: await readJson(response) };
}

/** Kirim form (FormData sudah membawa csrfmiddlewaretoken dari {% csrf_token %}). */
export async function postForm(url, formData) {
    const response = await fetch(url, {
        method: 'POST', body: formData, headers: AJAX_HEADERS, credentials: 'same-origin',
    });
    return { response, data: await readJson(response) };
}
