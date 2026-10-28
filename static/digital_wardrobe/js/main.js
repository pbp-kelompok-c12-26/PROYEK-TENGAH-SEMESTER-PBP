/* =========================================================
   Swapdrobe: JavaScript modul Digital Wardrobe (Lemari Saya)
   ---------------------------------------------------------
   Dimuat oleh templates/digital_wardrobe/partials/wardrobe_js.html sebagai ES module.
   Setiap fitur ada di file sendiri:
     toast.js         pesan singkat di bawah layar
     http.js          fetch ke server (JSON + CSRF)
     cards.js         bantuan DOM kartu (animasi hapus, angka total)
     form-modal.js    modal tambah/edit pakaian & outfit
     delete-dialog.js pop-up konfirmasi hapus 1 pakaian/outfit
     bulk-delete.js   mode "Pilih" untuk hapus banyak pakaian
   ========================================================= */
import { initToasts } from './toast.js';
import * as formModal from './form-modal.js';
import * as deleteDialog from './delete-dialog.js';
import * as bulkDelete from './bulk-delete.js';

initToasts();
formModal.init();
deleteDialog.init();
bulkDelete.init();
