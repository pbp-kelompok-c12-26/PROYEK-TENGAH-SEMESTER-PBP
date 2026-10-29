(() => {
    document.querySelectorAll('[data-sr-bulk-form]').forEach((form) => {
        const checkboxes = [...form.querySelectorAll('[data-sr-bulk-checkbox]')];
        const selectable = checkboxes.filter((checkbox) => !checkbox.disabled);
        const toggle = form.querySelector('[data-sr-selection-toggle]');
        const toggleLabel = form.querySelector('[data-sr-toggle-label]');
        const toggleIcon = form.querySelector('[data-sr-toggle-icon]');
        const selectAll = form.querySelector('[data-sr-select-all]');
        const selectAllWrap = form.querySelector('[data-sr-select-all-wrap]');
        const submit = form.querySelector('[data-sr-bulk-submit]');
        const count = form.querySelector('[data-sr-selected-count]');
        const hint = form.querySelector('[data-sr-selection-hint]');
        const dialog = form.querySelector('[data-sr-bulk-dialog]');
        const dialogCount = form.querySelector('[data-sr-confirm-count]');
        const dialogEffect = form.querySelector('[data-sr-confirm-effect]');
        const dialogCancel = form.querySelector('[data-sr-confirm-cancel]');
        const dialogAccept = form.querySelector('[data-sr-confirm-accept]');
        const rowSelectors = [...form.querySelectorAll('[data-sr-row-select]')];
        const groupSelectors = [...form.querySelectorAll('[data-sr-group-select]')];

        if (!toggle || !toggleLabel || !selectAll || !selectAllWrap || !submit || !count
            || !dialog || !dialogCount || !dialogEffect || !dialogCancel || !dialogAccept) return;
        selectAll.disabled = selectable.length === 0;
        let confirmedSubmit = false;

        function updateSelection() {
            const selectedCount = selectable.filter((checkbox) => checkbox.checked).length;
            const selectionMode = form.classList.contains('is-selection-mode');
            submit.disabled = selectedCount === 0;
            submit.hidden = !selectionMode || selectedCount === 0;
            count.hidden = !selectionMode || selectedCount === 0;
            count.textContent = `${selectedCount} dipilih`;
            selectAll.checked = selectable.length > 0 && selectedCount === selectable.length;
            selectAll.indeterminate = selectedCount > 0 && selectedCount < selectable.length;
            checkboxes.forEach((checkbox) => {
                checkbox.closest('.sr-row')?.classList.toggle('is-selected', checkbox.checked);
                checkbox.closest('.sr-bulk-option')?.classList.toggle('is-selected', checkbox.checked);
            });
        }

        function setSelectionMode(enabled) {
            form.classList.toggle('is-selection-mode', enabled);
            toggle.setAttribute('aria-pressed', String(enabled));
            toggleLabel.textContent = enabled ? 'Batal memilih' : 'Pilih request';
            toggle.title = enabled ? 'Keluar dari mode pilih request' : 'Pilih beberapa request';
            if (toggleIcon) {
                toggleIcon.innerHTML = enabled
                    ? '<path d="M6 6l12 12M18 6 6 18"/>'
                    : '<path d="M9 6h11M9 12h11M9 18h11"/><path d="m3 6 1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2"/>';
            }
            rowSelectors.forEach((selector) => { selector.hidden = !enabled; });
            groupSelectors.forEach((selector) => { selector.hidden = !enabled; });
            selectAllWrap.hidden = !enabled || selectable.length === 0;
            hint.hidden = !enabled;

            if (!enabled) {
                checkboxes.forEach((checkbox) => { checkbox.checked = false; });
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
            updateSelection();
        }

        toggle.addEventListener('click', () => {
            setSelectionMode(!form.classList.contains('is-selection-mode'));
        });

        selectAll.addEventListener('change', () => {
            selectable.forEach((checkbox) => { checkbox.checked = selectAll.checked; });
            updateSelection();
        });
        selectable.forEach((checkbox) => checkbox.addEventListener('change', updateSelection));

        form.addEventListener('submit', (event) => {
            if (confirmedSubmit) {
                confirmedSubmit = false;
                return;
            }
            const selectedCount = selectable.filter((checkbox) => checkbox.checked).length;
            if (!selectedCount) {
                event.preventDefault();
                return;
            }

            const tab = form.querySelector('[name="tab"]')?.value;
            dialogCount.textContent = `${selectedCount} request`;
            dialogEffect.textContent = tab === 'masuk'
                ? 'Request Pending yang masuk akan ditolak; status lain hanya dihapus dari daftar kamu.'
                : 'Request Pending yang kamu kirim akan dihapus untuk kedua pihak; status lain hanya dihapus dari daftar kamu.';
            event.preventDefault();
            dialog.showModal();
        });

        dialogCancel.addEventListener('click', () => dialog.close());
        dialogAccept.addEventListener('click', () => {
            dialog.close();
            confirmedSubmit = true;
            form.requestSubmit();
        });
        dialog.addEventListener('click', (event) => {
            if (event.target === dialog) dialog.close();
        });

        setSelectionMode(false);
    });
})();
