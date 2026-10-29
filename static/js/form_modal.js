/* =========================================================
   Swapdrobe: form sebagai pop-up
   ---------------------------------------------------------
   Link/tombol dengan atribut data-form-modal (mis. "Ajukan swap", "+ Jadwalkan Outfit")
   tidak pindah halaman, tetapi membuka form-nya sebagai pop-up:

   1. Halaman form (URL di href) diambil dengan fetch(), lalu elemen [data-modal-content]
      di dalamnya ditampilkan di pop-up. CSS modul yang dibutuhkan ikut dimuat.
   2. Saat form dikirim, data dikirim ke view yang sama (validasi tetap di Django):
        - berhasil (view redirect)  -> pindah ke halaman tujuan seperti biasa;
        - ada error (view render)   -> isi pop-up diganti form beserta pesan error-nya.
   3. Tanpa JavaScript, atau kalau URL dibuka langsung, link tetap membuka halaman form biasa.

   Gaya pop-up: .sw-fmodal di static/css/components.css
   ========================================================= */
(() => {
    if (window.SwFormModal) return;

    let overlay = null;
    let slot = null;
    let lastTrigger = null;
    let currentUrl = null;

    function ensureOverlay() {
        if (overlay) return;
        overlay = document.createElement('div');
        overlay.className = 'sw-fmodal';
        overlay.hidden = true;
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.innerHTML = '<div class="sw-fmodal__backdrop" data-modal-close></div><div class="sw-fmodal__slot" data-modal-slot></div>';
        slot = overlay.querySelector('[data-modal-slot]');
        document.body.appendChild(overlay);

        overlay.addEventListener('click', (event) => {
            const closer = event.target.closest('[data-modal-close]');
            if (closer) {
                event.preventDefault();
                close();
            }
        });
        // Dipasang di overlay (bukan di form) supaya pengecekan lain di form, mis. lokasi
        // wajib dipilih dari daftar, bisa membatalkan pengiriman lebih dulu.
        overlay.addEventListener('submit', (event) => {
            const form = event.target;
            if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
            event.preventDefault();
            submit(form, event.submitter);
        });
        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape' || overlay.hidden) return;
            if (overlay.querySelector('dialog[open]')) return;   // dialog di dalam pop-up menutup dirinya sendiri
            close();
        });
    }

    function show() {
        overlay.hidden = false;
        document.body.classList.add('sw-no-scroll');
    }

    function close() {
        if (!overlay || overlay.hidden) return;
        overlay.hidden = true;
        slot.replaceChildren();
        document.body.classList.remove('sw-no-scroll');
        currentUrl = null;
        if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
    }

    function setLoading(text = 'Memuat form...') {
        const box = document.createElement('div');
        box.className = 'sw-fmodal__loading';
        box.textContent = text;
        slot.replaceChildren(box);
    }

    function sameStylesheet(href) {
        return [...document.querySelectorAll('link[rel="stylesheet"]')].some((link) => link.href === href);
    }

    function loadStyles(doc, baseUrl) {
        const pending = [];
        doc.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
            const href = new URL(link.getAttribute('href'), baseUrl).href;
            if (sameStylesheet(href)) return;
            const el = document.createElement('link');
            el.rel = 'stylesheet';
            el.href = href;
            pending.push(new Promise((resolve) => { el.onload = resolve; el.onerror = resolve; }));
            document.head.appendChild(el);
        });
        return Promise.all(pending);
    }

    function runScripts(container) {
        container.querySelectorAll('script').forEach((old) => {
            const script = document.createElement('script');
            [...old.attributes].forEach((attr) => script.setAttribute(attr.name, attr.value));
            if (!old.src) script.textContent = old.textContent;
            old.replaceWith(script);
        });
    }

    async function render(html, url) {
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const content = doc.querySelector('[data-modal-content]');
        if (!content) {
            window.location.assign(url);   // halaman bukan form pop-up: buka seperti biasa
            return;
        }
        await loadStyles(doc, url);
        slot.classList.toggle('sw-fmodal__slot--narrow', content.hasAttribute('data-modal-narrow'));
        const fragment = document.importNode(content, true);
        slot.replaceChildren(fragment);
        runScripts(slot);
        if (window.SwLocation) window.SwLocation.init();
        const title = slot.querySelector('.sw-fmodal__title');
        if (title) {
            title.id = title.id || 'sw-fmodal-title';
            overlay.setAttribute('aria-labelledby', title.id);
        } else if (content.getAttribute('aria-labelledby')) {
            overlay.setAttribute('aria-labelledby', content.getAttribute('aria-labelledby'));
        }
        // Fokus ke field yang error, atau field pertama
        const errorField = slot.querySelector('.sw-ffield__error')?.closest('.sw-ffield');
        const first = (errorField || slot).querySelector('input:not([type="hidden"]):not([disabled]), select, textarea');
        if (first) first.focus({ preventScroll: true });
        else if (content.hasAttribute('data-modal-success')) {
            slot.querySelector('[data-modal-success]')?.focus({ preventScroll: true });
        }
        overlay.scrollTop = 0;
    }

    async function open(url, trigger) {
        ensureOverlay();
        lastTrigger = trigger || null;
        currentUrl = url;
        setLoading();
        show();
        try {
            const response = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            if (response.redirected || !response.ok) {
                // mis. belum login, request sudah ada, atau tidak ada pakaian yang bisa ditawarkan
                window.location.assign(response.redirected ? response.url : url);
                return;
            }
            await render(await response.text(), response.url);
        } catch (error) {
            window.location.assign(url);
        }
    }

    async function submit(form, submitter) {
        const buttons = form.querySelectorAll('button[type="submit"], button:not([type])');
        buttons.forEach((button) => { button.disabled = true; });
        const action = form.getAttribute('action') || currentUrl || window.location.href;
        try {
            const body = submitter && submitter.name ? new FormData(form, submitter) : new FormData(form);
            const response = await fetch(action, {
                method: (form.getAttribute('method') || 'post').toUpperCase(),
                body,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            if (response.redirected) {
                const html = await response.text();
                const doc = new DOMParser().parseFromString(html, 'text/html');
                if (doc.querySelector('[data-modal-content][data-modal-success]')) {
                    // Swap request berhasil: tampilkan konfirmasi di modal yang sama,
                    // tanpa meninggalkan halaman katalog/form asal.
                    currentUrl = response.url;
                    await render(html, response.url);
                    return;
                }
                window.location.assign(response.url);   // redirect sukses fitur lain
                return;
            }
            await render(await response.text(), response.url);   // ada error: tampilkan lagi
        } catch (error) {
            form.submit();   // jaringan bermasalah: kirim biasa
        } finally {
            buttons.forEach((button) => { if (document.contains(button)) button.disabled = false; });
        }
    }

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('a[data-form-modal]');
        if (!trigger || event.defaultPrevented) return;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (trigger.hasAttribute('data-auth-required')) return;   // tamu: biarkan pop-up login yang muncul
        event.preventDefault();
        open(trigger.href, trigger);
    });

    window.SwFormModal = { open, close };
})();
