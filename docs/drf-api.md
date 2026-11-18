# API Django REST Framework — SwapDrobe

Semua endpoint API berada di bawah `/api/` dan menggunakan JSON. Unggahan foto
tetap menggunakan `multipart/form-data`. Tidak ada perubahan model atau migrasi
untuk API ini.

API routes menggunakan function-based DRF views dengan wrapper decorator
`@api_view`, `@authentication_classes([SessionAuthentication])`, dan
`@permission_classes(...)` mengikuti pola Tutorial 07. Class-based handlers di
bawahnya hanya menjadi implementation layer untuk reuse aturan bisnis SwapDrobe.

## Autentikasi dan CSRF

API menggunakan `SessionAuthentication`, sehingga sesi login yang sama dengan
halaman SwapDrobe dipakai kembali. Endpoint katalog listing dapat dibaca tanpa
login; semua endpoint wardrobe, outfit, kalender, dan swap request memerlukan
sesi login.

Untuk `POST`, `PUT`, `PATCH`, dan `DELETE` dari browser, kirim cookie sesi dan
header `X-CSRFToken` dari token `{% csrf_token %}`/cookie CSRF. Jangan gunakan
`csrf_exempt`.

## Endpoint

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| GET, POST | `/api/digital-wardrobe/items/` | Daftar/tambah pakaian milik sendiri |
| GET, PUT, PATCH, DELETE | `/api/digital-wardrobe/items/<id>/` | Detail dan CRUD pakaian sendiri |
| GET, POST | `/api/digital-wardrobe/outfits/` | Daftar/buat outfit sendiri |
| GET, PUT, PATCH, DELETE | `/api/digital-wardrobe/outfits/<id>/` | CRUD outfit sendiri |
| GET, POST | `/api/items-for-swap/` | Katalog publik / tawarkan pakaian sendiri |
| GET | `/api/items-for-swap/mine/` | Semua listing milik sendiri |
| GET, PUT, PATCH, DELETE | `/api/items-for-swap/<id>/` | Detail publik atau kelola listing sendiri |
| GET, POST | `/api/swap-requests/` | Daftar request yang terlihat / ajukan request |
| GET, PUT, PATCH, DELETE | `/api/swap-requests/<id>/` | Detail, edit pengirim, atau hapus sesuai peran/status |
| POST | `/api/swap-requests/<id>/respond/` | Pemilik menerima/menolak: `{"action":"accept"}` atau `reject` |
| POST | `/api/swap-requests/<id>/confirm/` | Pihak swap memilih `{"choice":"done"}` atau `cancel` |
| GET, POST | `/api/outfit-calendar/schedules/` | Daftar/buat jadwal sendiri |
| GET, PUT, PATCH, DELETE | `/api/outfit-calendar/schedules/<id>/` | CRUD jadwal sendiri |

Field server-managed—pemilik pakaian/listing, status dan waktu swap, status
listing, catatan kepemilikan, serta snapshot jadwal—bersifat read-only. Serializer
memakai kembali aturan model/form yang sudah ada: pakaian harus milik user,
listing harus aktif, request hanya boleh diproses oleh pihak yang tepat, dan
transisi `pending → awaiting_exchange → completed/rejected` tetap melalui method
model yang sudah digunakan halaman web.

## Menjalankan dan menguji

```powershell
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\env\Scripts\python.exe manage.py check
.\env\Scripts\python.exe manage.py test PROJECTS.test_api
```

`PROJECTS.test_api` memakai `APIClient` dan meliputi CRUD (termasuk PUT dan
bulk-delete wardrobe), validasi, pengguna anonim, kepemilikan/peran, transisi
swap, calculated/read-only fields, serta CSRF sesi.

Interaksi modal wardrobe yang sebelumnya memakai `fetch`/HTMX untuk operasi
tulis sekarang mengirim `FormData` ke endpoint DRF. Response serializer error
ditampilkan sebagai toast; response sukses memuat ulang halaman sehingga
komponen kartu dan kolase lama tetap memakai markup/CSS yang sama.
