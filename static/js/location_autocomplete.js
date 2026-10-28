/* =========================================================
   Swapdrobe: autocomplete lokasi (kabupaten/kota)
   ---------------------------------------------------------
   Markup: templates/home/partials/location_input.html
   Data  : endpoint Django `home:location_data` (/lokasi/), yang mengambil
           API Wilayah Indonesia (EmSifa v2) dan menyimpannya di cache server
           (lihat home/wilayah.py).

   - Data diambil SATU kali per halaman (dipakai bersama semua input lokasi),
     lalu disimpan di memori; pencarian berikutnya tidak memanggil server lagi.
   - Rekomendasi muncul setelah 2 huruf, maksimal 8, tidak peka huruf besar/kecil,
     cocok dengan nama kab/kota maupun provinsi.
   - User harus memilih rekomendasi: yang dikirim ke server adalah KODE wilayah
     (input tersembunyi). Mengubah teks setelah memilih = pilihan dibatalkan.
     Server tetap memeriksa ulang kode tersebut.
   - Kalau data gagal / tidak lengkap: pesan di bawah input + pop-up + tombol "Coba lagi".
   ========================================================= */
(() => {
    if (window.SwLocation) return;   // file ini bisa ter-include beberapa kali di satu halaman

    const MIN_CHARS = 2;
    const MAX_RESULTS = 8;
    const sources = new Map();        // url -> { promise, data }
    let dialog = null;
    let dialogShownFor = null;        // pop-up cukup sekali per masalah per halaman

    // ------------------------------------------------------------------ data
    function normalize(text) {
        return String(text || '')
            .toLowerCase()
            .normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^a-z0-9 ]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function prepare(payload) {
        const locations = (payload.locations || []).map((loc) => {
            const city = normalize(loc.city);
            return {
                ...loc,
                _city: city,
                _cityCore: city.replace(/^(kabupaten|kab|kota) /, ''),
                _province: normalize(loc.province),
                _label: normalize(loc.label),
            };
        });
        return {
            locations,
            byCode: new Map(locations.map((loc) => [loc.code, loc])),
            complete: Boolean(payload.complete),
            stale: Boolean(payload.stale),
            error: Boolean(payload.error) || locations.length === 0,
            failedProvinces: payload.failed_provinces || [],
        };
    }

    function load(url, refresh = false) {
        const known = sources.get(url);
        if (known && !refresh) return known.promise;
        const entry = { data: null };
        entry.promise = fetch(refresh ? `${url}?refresh=1` : url, {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
            cache: refresh ? 'no-store' : 'default',
        })
            .then((response) => response.json().catch(() => ({ error: true })))
            .catch(() => ({ error: true }))
            .then((payload) => {
                entry.data = prepare(payload);
                return entry.data;
            });
        sources.set(url, entry);
        return entry.promise;
    }

    function search(data, query) {
        const q = normalize(query);
        if (q.length < MIN_CHARS) return [];
        const words = q.split(' ');
        const scored = [];
        for (const loc of data.locations) {
            if (!words.every((w) => loc._label.includes(w))) continue;
            let score = 5;
            if (loc._cityCore.startsWith(q) || loc._city.startsWith(q)) score = 0;
            else if (loc._city.includes(q)) score = 1;
            else if (loc._province.startsWith(q)) score = 2;
            else if (loc._province.includes(q)) score = 3;
            scored.push([score, loc]);
        }
        scored.sort((a, b) => a[0] - b[0] || a[1].label.localeCompare(b[1].label, 'id'));
        return scored.slice(0, MAX_RESULTS).map(([, loc]) => loc);
    }

    function problemMessage(data) {
        if (data.error) {
            return 'Daftar kota/kabupaten dari API Wilayah Indonesia sedang tidak bisa dimuat, '
                + 'jadi lokasi belum bisa dipilih. Coba lagi beberapa saat lagi.';
        }
        if (!data.complete) {
            return `Sebagian data wilayah gagal dimuat (${data.failedProvinces.join(', ') || 'beberapa provinsi'}). `
                + 'Kota/kabupaten di provinsi tersebut belum bisa dipilih untuk sementara.';
        }
        return '';
    }

    // ------------------------------------------------------------------ pop-up
    function ensureDialog() {
        if (dialog) return dialog;
        dialog = document.createElement('dialog');
        dialog.className = 'sw-location-dialog';
        dialog.setAttribute('aria-labelledby', 'sw-location-dialog-title');
        dialog.innerHTML = `
            <div class="sw-location-dialog__body">
                <span class="sw-location-dialog__icon" aria-hidden="true">!</span>
                <h2 id="sw-location-dialog-title" class="sw-location-dialog__title">Data lokasi sedang bermasalah</h2>
                <p class="sw-location-dialog__text" data-dialog-text></p>
                <div class="sw-location-dialog__actions">
                    <button type="button" class="sw-location-dialog__close" data-dialog-close>Tutup</button>
                    <button type="button" class="sw-location-dialog__retry sw-btn-holo" data-dialog-retry>Coba lagi</button>
                </div>
            </div>`;
        document.body.appendChild(dialog);
        dialog.querySelector('[data-dialog-close]').addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
        return dialog;
    }

    function showDialog(widget, data) {
        const message = problemMessage(data);
        if (!message || dialogShownFor === message) return;
        dialogShownFor = message;
        const dlg = ensureDialog();
        dlg.querySelector('[data-dialog-text]').textContent = message;
        const retry = dlg.querySelector('[data-dialog-retry]');
        retry.disabled = false;
        retry.textContent = 'Coba lagi';
        retry.onclick = async () => {
            retry.disabled = true;
            retry.textContent = 'Memuat...';
            const fresh = await widget.retry();
            const stillBroken = problemMessage(fresh);
            if (!stillBroken) {
                dlg.close();
                return;
            }
            dlg.querySelector('[data-dialog-text]').textContent =
                `Masih belum berhasil. ${stillBroken}`;
            retry.disabled = false;
            retry.textContent = 'Coba lagi';
        };
        if (!dlg.open) dlg.showModal();
    }

    // ------------------------------------------------------------------ widget
    class LocationWidget {
        constructor(root) {
            this.root = root;
            this.url = root.dataset.source;
            this.alertMode = root.dataset.alert || 'load';
            this.optional = root.hasAttribute('data-optional');
            this.input = root.querySelector('[data-location-input]');
            this.codeInput = root.querySelector('[data-location-code]');
            this.list = root.querySelector('[data-location-list]');
            this.status = root.querySelector('[data-location-status]');
            this.spinner = root.querySelector('[data-location-spinner]');
            this.data = null;
            this.results = [];
            this.active = -1;
            this.selectedLabel = this.codeInput.value ? this.input.value : '';
            this.legacy = Boolean(this.input.value.trim() && !this.codeInput.value);

            this.input.addEventListener('input', () => this.onInput());
            this.input.addEventListener('focus', () => this.onFocus());
            this.input.addEventListener('keydown', (event) => this.onKeydown(event));
            this.input.addEventListener('blur', () => setTimeout(() => this.close(), 120));
            this.list.addEventListener('mousedown', (event) => event.preventDefault());
            this.list.addEventListener('click', (event) => {
                const option = event.target.closest('[data-index]');
                if (option) this.choose(Number(option.dataset.index));
            });
            this.status.addEventListener('click', (event) => {
                if (event.target.closest('[data-location-retry]')) this.retry();
            });
            if (this.input.form) {
                this.input.form.addEventListener('submit', (event) => this.onSubmit(event));
            }

            this.showLegacyHint();
            if (this.alertMode === 'load') this.ensureData();
        }

        showLegacyHint() {
            if (this.legacy) {
                this.setStatus('Lokasi lamamu belum dipilih dari daftar wilayah. Ketik lalu pilih ulang kota/kabupatenmu.', 'hint');
            }
        }

        // ---- data
        ensureData(refresh = false) {
            if (this.data && !refresh) return Promise.resolve(this.data);
            this.setLoading(true);
            return load(this.url, refresh).then((data) => {
                this.data = data;
                this.setLoading(false);
                this.reportProblem(true);
                if (document.activeElement === this.input) this.render();
                return data;
            });
        }

        retry() {
            this.setStatus('Memuat ulang data lokasi...', 'hint');
            return this.ensureData(true).then((data) => {
                // Widget lain di halaman yang sama ikut memakai data terbaru
                document.querySelectorAll('[data-location]').forEach((el) => {
                    if (el.swLocation && el.swLocation !== this) el.swLocation.data = data;
                });
                if (!problemMessage(data)) {
                    this.setStatus('', '');
                    if (document.activeElement === this.input) this.render();
                }
                return data;
            });
        }

        reportProblem(fromLoad) {
            const message = problemMessage(this.data);
            if (!message) {
                if (this.status.dataset.kind === 'error' || this.status.dataset.kind === 'warn') this.setStatus('', '');
                return;
            }
            const kind = this.data.error ? 'error' : 'warn';
            this.setStatus(message, kind, true);
            if (!fromLoad || this.alertMode === 'load' || document.activeElement === this.input) {
                showDialog(this, this.data);
            }
        }

        // ---- events
        onFocus() {
            if (!this.data) {
                this.ensureData();
            } else {
                this.reportProblem(false);
                this.render();
            }
        }

        onInput() {
            // Teks diubah -> pilihan lama tidak berlaku lagi
            if (this.codeInput.value && this.input.value !== this.selectedLabel) {
                this.codeInput.value = '';
                this.selectedLabel = '';
            }
            this.input.removeAttribute('aria-invalid');
            if (!this.data) {
                this.ensureData();
                return;
            }
            this.render();
        }

        onKeydown(event) {
            const open = !this.list.hidden && this.results.length > 0;
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                if (!open) { this.render(); return; }
                event.preventDefault();
                const step = event.key === 'ArrowDown' ? 1 : -1;
                this.setActive((this.active + step + this.results.length) % this.results.length);
            } else if (event.key === 'Enter') {
                if (open && this.active >= 0) {
                    event.preventDefault();
                    this.choose(this.active);
                } else if (open) {
                    event.preventDefault();
                    this.choose(0);
                }
            } else if (event.key === 'Escape') {
                if (open) {
                    event.preventDefault();
                    this.close();
                }
            }
        }

        onSubmit(event) {
            // Kosong: biarkan terkirim, server yang menampilkan pesan wajib diisi
            // bersama error field lain. Teks diketik tapi belum dipilih: tahan di sini.
            if (!this.input.value.trim() || this.validate()) return;
            event.preventDefault();
            event.stopImmediatePropagation();
        }

        /** True kalau pilihan lokasi sah (atau boleh kosong). Kalau tidak, tampilkan pesan. */
        validate() {
            const text = this.input.value.trim();
            if (this.codeInput.value || (!text && this.optional)) return true;
            this.input.setAttribute('aria-invalid', 'true');
            this.input.focus();   // fokus dulu: handler fokus bisa mengosongkan pesan status
            this.setStatus(text ? 'Pilih lokasi dari daftar rekomendasi.' : 'Wajib diisi: ketik lalu pilih kota/kabupaten.', 'error');
            return false;
        }

        // ---- tampilan
        render() {
            const query = this.input.value;
            if (!this.data) return;
            if (this.data.error) {
                this.close();
                this.reportProblem(false);
                return;
            }
            if (this.codeInput.value && query === this.selectedLabel) {
                this.close();   // sudah memilih; tidak perlu rekomendasi lagi
                return;
            }
            const length = normalize(query).length;
            if (length < MIN_CHARS) {
                this.close();
                if (!problemMessage(this.data) && !this.legacy && this.status.dataset.kind !== 'error') {
                    this.setStatus(length ? `Ketik minimal ${MIN_CHARS} huruf.` : '', 'hint');
                }
                return;
            }
            this.results = search(this.data, query);
            this.active = -1;
            this.list.innerHTML = '';
            if (!this.results.length) {
                const li = document.createElement('li');
                li.className = 'sw-location__empty';
                li.setAttribute('role', 'presentation');
                li.textContent = `Tidak ada kota/kabupaten yang cocok dengan "${query.trim()}".`;
                if (!this.data.complete) li.textContent += ' Sebagian data provinsi belum termuat.';
                this.list.appendChild(li);
            } else {
                this.results.forEach((loc, index) => {
                    const li = document.createElement('li');
                    li.id = `${this.input.id}-opt-${index}`;
                    li.className = 'sw-location__option';
                    li.setAttribute('role', 'option');
                    li.setAttribute('aria-selected', 'false');
                    li.dataset.index = String(index);
                    const city = document.createElement('span');
                    city.className = 'sw-location__city';
                    city.textContent = loc.city;
                    const province = document.createElement('span');
                    province.className = 'sw-location__province';
                    province.textContent = loc.province;
                    li.append(city, province);
                    this.list.appendChild(li);
                });
            }
            this.list.hidden = false;
            this.input.setAttribute('aria-expanded', 'true');
            if (!problemMessage(this.data) && this.status.dataset.kind === 'hint') this.setStatus('', '');
        }

        setActive(index) {
            this.active = index;
            this.list.querySelectorAll('[role="option"]').forEach((li, i) => {
                const on = i === index;
                li.classList.toggle('is-active', on);
                li.setAttribute('aria-selected', on ? 'true' : 'false');
                if (on) li.scrollIntoView({ block: 'nearest' });
            });
            if (index >= 0) this.input.setAttribute('aria-activedescendant', `${this.input.id}-opt-${index}`);
            else this.input.removeAttribute('aria-activedescendant');
        }

        choose(index) {
            const loc = this.results[index];
            if (!loc) return;
            this.codeInput.value = loc.code;
            this.input.value = loc.label;
            this.selectedLabel = loc.label;
            this.legacy = false;
            this.input.removeAttribute('aria-invalid');
            if (!problemMessage(this.data)) this.setStatus('', '');
            this.close();
            this.codeInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        close() {
            this.list.hidden = true;
            this.results = this.results || [];
            this.active = -1;
            this.input.setAttribute('aria-expanded', 'false');
            this.input.removeAttribute('aria-activedescendant');
        }

        setLoading(on) {
            this.spinner.hidden = !on;
            this.root.classList.toggle('is-loading', on);
            if (on) this.setStatus('Memuat daftar kota/kabupaten...', 'hint');
            else if (this.status.dataset.kind === 'hint') {
                this.setStatus('', '');
                this.showLegacyHint();
            }
        }

        setStatus(text, kind, withRetry = false) {
            this.status.dataset.kind = kind || '';
            this.status.className = `sw-location__status${kind ? ` sw-location__status--${kind}` : ''}`;
            this.status.textContent = text;
            if (withRetry) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'sw-location__retry';
                button.dataset.locationRetry = '';
                button.textContent = 'Coba lagi';
                this.status.append(' ', button);
            }
            this.status.hidden = !text;
        }
    }

    function init() {
        document.querySelectorAll('[data-location]').forEach((root) => {
            if (!root.swLocation) root.swLocation = new LocationWidget(root);
        });
    }

    window.SwLocation = { init, load, search, normalize };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
