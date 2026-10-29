import { toast } from '../../digital_wardrobe/js/toast.js';

/* Interaksi HTMX khusus Swap Request: feedback, pencegahan klik ganda, dan rollback visual. */
(() => {
    if (window.SwapRequestInteractions) return;
    window.SwapRequestInteractions = true;
    const optimisticSnapshots = new WeakMap();

    function getForm(element) {
        if (element instanceof HTMLFormElement) return element;
        return element?.closest?.('form') || null;
    }

    function showError(message) {
        toast(message, true);
    }

    function initServerToasts(root = document) {
        const toasts = [];
        if (root.matches?.('#wardrobe-toast [data-toast]')) toasts.push(root);
        root.querySelectorAll?.('#wardrobe-toast [data-toast]').forEach((item) => toasts.push(item));
        toasts.forEach((item) => {
            if (item.dataset.srDismissInitialized === 'true') return;
            item.dataset.srDismissInitialized = 'true';
            window.setTimeout(() => item.remove(), 4000);
        });
    }

    initServerToasts();
    document.addEventListener('htmx:load', (event) => initServerToasts(event.detail?.elt || document));

    function clearOptimisticState() {
        document.querySelectorAll('.sr-optimistic-removal').forEach((node) => {
            node.classList.remove('sr-optimistic-removal');
        });
    }

    document.addEventListener('htmx:beforeRequest', (event) => {
        const form = getForm(event.detail.elt);
        if (!form || !form.hasAttribute('data-sr-hx-action') && !form.hasAttribute('data-sr-bulk-form')) return;
        if (form.dataset.srBusy === 'true') {
            event.preventDefault();
            return;
        }

        form.dataset.srBusy = 'true';
        form.setAttribute('aria-busy', 'true');
        form._srBusyControls = [...form.querySelectorAll('button[type="submit"], button:not([type])')].map((button) => ({
            button,
            disabled: button.disabled,
            html: button.innerHTML,
        }));
        form._srBusyControls.forEach(({ button }) => {
            button.disabled = true;
            if (form.hasAttribute('data-sr-bulk-form')) button.textContent = 'Menghapus…';
            else if (button.type === 'submit') button.textContent = 'Memproses…';
        });

        const optimisticStatus = form.dataset.srOptimisticStatus;
        if (optimisticStatus) {
            const target = document.querySelector(form.getAttribute('hx-target'));
            if (target) {
                optimisticSnapshots.set(form, { target, html: target.innerHTML });
                const badge = target.querySelector('.sr-status');
                if (badge) {
                    const labels = { awaiting_exchange: 'Awaiting exchange', rejected: 'Rejected' };
                    const styles = { awaiting_exchange: 'sr-status--awaiting', rejected: 'sr-status--rejected' };
                    badge.textContent = labels[optimisticStatus];
                    badge.className = `sr-status ${styles[optimisticStatus]}`;
                }
                const notes = {
                    awaiting_exchange: 'Request disetujui. Hubungi satu sama lain untuk mengatur pertukaran, lalu konfirmasi penyelesaian di bawah.',
                    rejected: 'Request ditolak, salah satu pihak membatalkan pertukaran, atau item telah dibatalkan untuk ditawarkan.',
                };
                const note = target.querySelector('.sr-status-note');
                if (note) note.textContent = notes[optimisticStatus];
                target.querySelector('.sr-respond')?.classList.add('sr-optimistic-hidden');
                target.querySelector('.sr-callout--info')?.classList.add('sr-optimistic-hidden');
            }
        }

        if (form.hasAttribute('data-sr-bulk-form')) {
            form.querySelectorAll('[data-sr-bulk-checkbox]:checked').forEach((checkbox) => {
                const row = checkbox.closest('.sr-bulk-option, .sr-row');
                row?.classList.add('sr-optimistic-removal');
            });
        } else if (form.action.includes('/delete/')) {
            document.querySelector('#sr-detail-root')?.classList.add('sr-optimistic-removal');
        }
    });

    document.addEventListener('htmx:afterRequest', (event) => {
        const form = getForm(event.detail.elt);
        if (form?._srBusyControls) {
            form._srBusyControls.forEach(({ button, disabled, html }) => {
                button.disabled = disabled;
                button.innerHTML = html;
            });
            delete form._srBusyControls;
            delete form.dataset.srBusy;
            form.removeAttribute('aria-busy');
        }
        optimisticSnapshots.delete(form);
        clearOptimisticState();
    });

    document.addEventListener('htmx:responseError', (event) => {
        restoreOptimisticState(event.detail.elt);
        clearOptimisticState();
        showError('Aksi belum berhasil diproses. Tampilan dikembalikan; coba lagi.');
    });
    document.addEventListener('htmx:sendError', (event) => {
        restoreOptimisticState(event.detail.elt);
        clearOptimisticState();
        showError('Koneksi terputus. Request belum berhasil dikirim. Coba lagi.');
    });
    document.addEventListener('htmx:timeout', (event) => {
        restoreOptimisticState(event.detail.elt);
        clearOptimisticState();
        showError('Server belum merespons. Coba lagi sebentar.');
    });

    function restoreOptimisticState(element) {
        const form = getForm(element);
        const snapshot = form && optimisticSnapshots.get(form);
        if (!snapshot) return;
        if (snapshot.target.isConnected) snapshot.target.innerHTML = snapshot.html;
        optimisticSnapshots.delete(form);
    }
})();
