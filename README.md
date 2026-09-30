KELOMPOK C12 PBP
# PROYEK-TENGAH-SEMESTER-PBP
# SwapDrobe

> **"Swap what you have, keep it in the loop"**

SwapMatch adalah aplikasi web yang membantu pengguna mengelola *wardrobe* digital, mencatat dan memadukan *outfit* sehari-hari, serta melakukan *swap*/barter pakaian bekas layak pakai dengan pengguna lain melalui *swap request* dan negosiasi. 

Aplikasi ini ditujukan bagi pengguna yang ingikn lebih mudah mengatur dan memaksimalkan pakaian yang dimiliki, sekaligus mengatasi masalah pakaian yang menumpuk, jarang digunakan, dan kebiasaan membeli pakaian baru. Melalui fitur *digital wardrobe*, *outfit calendar*, *outfit matching*, dan *clothing swap*, pengguna dapat melacak penggunaan pakaian, menemukan kombinasi *outfit*, serta menukar pakaian yang sudah jarang digunakan dengan pakaian milik pengguna lain. Dengan demikian, SwapMatch mendorong penggunaan pakaian yang lebih optimal dan berkelanjutan sekaligus membantu mengurangi pembelian pakaian baru dan limbah tekstil.

---

## 👥 Tim & Anggota (Kelompok C12)

* **Stephanie Revalina Tamus** - 2506547153
* **Muhammad Zahran Affan** - 2506586103
* **Iqbal Virdiansyah** - 2506656816
* **Nafisa Naila Andian** - 2506657125
* **Sultoni Rico Sabillilah** - 2506657365

---

## ⚖️ Perbandingan dengan Aplikasi Serupa

| Aplikasi | Deskripsi Perbandingan |
| :--- | :--- |
| **Whering App** | Whering berfokus pada *digital wardrobe* dan *styling* (mengelola pakaian, membuat kombinasi *outfit*, dan merencanakan pemakaian pakaian). Berbeda dengan Whering, SwapMatch menambahkan sistem *swap*/barter yang memungkinkan pengguna menukar pakaian yang sudah jarang digunakan dengan pakaian milik pengguna lain melalui *swap request* dan negosiasi. |
| **Depop** | Depop merupakan platform jual-beli pakaian bekas yang menggunakan sistem transaksi seperti *marketplace*. Sementara itu, SwapMatch tidak berfokus pada jual-beli, melainkan pada pertukaran pakaian antar pengguna. Selain itu, SwapMatch juga menyediakan *digital wardrobe* dan *outfit management*, sehingga pengguna dapat mengelola dan memantau pakaian mereka sebelum memutuskan untuk melakukan *swap*. |

---

## 🧩 Modul Aplikasi & Penanggung Jawab (PIC)

1. **Manajemen Akun & Autentikasi** *(PIC: Iqbal Virdiansyah)*
   Mengelola akun pengguna, mulai dari registrasi, profil, perubahan data akun, hingga penghapusan akun serta autentikasi pengguna.
2. **Wardrobe Digital** *(PIC: Stephanie Revalina Tamus)*
   Mengelola koleksi pakaian pribadi pengguna, termasuk menambahkan, melihat, mengubah, dan menghapus data pakaian serta informasi terkait penggunaannya.
3. **Outfit Calendar** *(PIC: Nafisa Naila Andian)*
   Mengelola kombinasi pakaian yang digunakan pengguna pada tanggal tertentu serta menyimpan dan menampilkan riwayat *outfit* melalui kalender.
4. **Items for Swap** *(PIC: Sultoni Rico Sabillilah)*
   Mengelola pakaian yang ditawarkan pengguna untuk ditukar, sehingga dapat dilihat dan ditemukan oleh pengguna lain.
5. **Swap Request** *(PIC: Muhammad Zahran Affan)*
   Mengelola proses pengajuan dan penerimaan permintaan *swap*, termasuk pakaian yang ditawarkan, pakaian yang diminta, pesan, serta status *request*.

---

## Deskripsi Modul & Operasi CRUD

| Nama Modul | Peran Pengguna | C (Create) | R (Read) | U (Update) | D (Delete) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Manajemen Akun & Autentikasi** | **Admin** | Membuat akun pengguna | Melihat daftar dan detail seluruh akun pengguna | Mengubah data/status akun pengguna | Menghapus akun pengguna |
| | **User** | Membuat akun melalui registrasi | Melihat data/profil akun sendiri | Mengubah data/profil akun sendiri | Menghapus akun sendiri |
| **Wardrobe Digital** | **User** | Menambahkan pakaian ke *wardrobe* | Melihat daftar dan detail pakaian pribadi | Mengubah informasi pakaian | Menghapus pakaian dari *wardrobe* |
| **Outfit Calendar** | **User** | Menambahkan *outfit* (kombinasi pakaian) ke tanggal tertentu dengan memilih pakaian dari *wardrobe* | Melihat riwayat kombinasi pakaian (*outfit*) melalui *view calendar* | Mengubah *outfit* atau pakaian yang digunakan pada suatu tanggal | Menghapus catatan *outfit* dari *calendar* |
| **Items for Swap** | **User** | Menambahkan pakaian dari *wardrobe* / langsung ke daftar pakaian yang ditawarkan untuk *swap* | Melihat *Items for Swap* milik sendiri maupun milik pengguna lain | Mengubah informasi atau status *Items for Swap* milik sendiri | Menghapus / menarik pakaian dari *Items for Swap* |
| **Swap Request** | **User** | Mengajukan *swap request* terhadap *Items for Swap* milik pengguna lain | Melihat *request* yang diajukan maupun *request* yang diterima | Mengubah status *request* (menerima, menolak, atau membatalkan *request*) | Membatalkan / menghapus *swap request* yang masih dalam status tertentu |

---

## Atribut Data Modul

| Nama Modul | Entitas | Input User (Wajib) | Input User (Opsional) | Otomatis Sistem | Detail / Atribut Spesifik |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Manajemen Akun** | User Profile | `username`, `password` | Foto profil, bio, preferensi ukuran pakaian (`top`, `bottom`, `shoes`), gender | Tanggal bergabung | - |
| **Wardrobe Digital** | Pakaian | Foto, nama pakaian (keyword), kategori (`top`, `bottom`, dll), warna, ukuran, kondisi | Catatan, *style*, *pattern* | Status (*aman/direkomen buat swap*), tanggal ditambahkan, pemilik, `last_worn_date` | - `pemilik`: `ForeignKey(User)`<br>- `nama_pakaian`: `CharField(max_length=100)`<br>- `foto`: `ImageField`<br>- `kategori`: `CharField(choices: Top, Bottom, Outer, Dress, Shoes, Acc)`<br>- `warna_utama`: `CharField(choices: Neutral, Earth, Bright, Pastel)`<br>- `style`: `CharField(choices: Casual, Smart Casual, Formal, Sporty)`<br>- `pattern`: `CharField(choices: Solid, Striped, Patterned)`<br>- `ukuran`: `CharField(choices: XS, S, M, L, XL, XXL, All Size)`<br>- `kondisi`: `CharField(choices: Brand New, Like New, Good, Fair)`<br>- `catatan`: `TextField(blank=True)`<br>- `tanggal_ditambahkan`: `DateField(auto_now_add=True)`<br>- `last_worn_date`: `DateField(null=True, blank=True)`<br>- `is_idle`: `BooleanField(default=False)`<br>- `is_listed_for_swap`: `BooleanField(default=False)`<br><br>*Catatan Core Inventory:*<br>1. `last_worn_date` otomatis ter-update saat baju dimasukkan ke Outfit Calendar.<br>2. `is_idle` otomatis bernilai `True` jika `idle` > N hari (opsional).<br>3. `is_listed_for_swap` menandai apakah baju telah dipindahkan ke daftar pakaian yang mau di-swap. |
| **Outfit Calendar** | Outfit (Kombinasi Pakaian) | Kombinasi 3 kategori pakaian (`top`, `bottom`, `shoes`), nama *outfit* (keyword), tanggal dipakai | Notes | Pemilik | Kombinasi dari 3 item pakaian yang ada di *wardrobe*. |
| **Items for Swap** | Item Swap | Foto, nama pakaian (keyword), kategori (`top`, `bottom`, dll), kondisi, ukuran, warna, *meeting location* | Deskripsi, *style*, *pattern* | Status (`avail`, `sold`, `jumlah_request`), pemilik, tanggal di-post untuk *swap* | Item yang ditawarkan ke publik untuk ditukar. |
| **Swap Request** | Swap Request Card | Pakaian yang ditawarkan (data seperti *Items for Swap* kecuali *meeting location* dan *status*) | Pesan | Pengaju, pemilik pakaian, pakaian yang diminta, status (`diterima`, `ditolak`, `menunggu`, `nego`), tanggal dibuat | Menghubungkan dua pihak yang ingin membarter barang. |

---

##  Daftar Fitur Aplikasi

| Nama Fitur | Deskripsi & Hal yang Ditampilkan | Asal View Modul |
| :--- | :--- | :--- |
| **Profile Page** | Menu yang menampilkan halaman profil pengguna. | Manajemen Akun, Items for Swap |
| **Home Page** | Menu yang menampilkan *Recommendation Feed* berupa foto/kartu pakaian yang diambil secara acak atau menggunakan algoritma rekomendasi (opsional). | Items for Swap (milik pengguna lain) |
| **Bookmark** | Menu yang menampilkan kartu *Item for Swap* milik orang lain yang disimpan/ditandai (*bookmarked*). | Items for Swap |
| **Outfit Matching** | Fitur *matching* pakaian interaktif berbasis *scroll* kanan-kiri (3 slot item: *tops*, *bottoms*, *shoes*). | Wardrobe Digital / Outfit Calendar |
| **Swap Request** | Menu yang menampilkan daftar pengajuan tukar-menukar (*barter*), baik pengajuan pribadi maupun pengajuan dari pengguna lain. | Swap Request |
| **Outfit Calendar** | Menu yang menampilkan riwayat kombinasi pakaian (*outfit*) dari *wardrobe* yang tersimpan pada tanggal tertentu dalam bentuk kalender. | Outfit Calendar |
| **My Wardrobe** | Menu yang berisi daftar kartu pakaian milik sendiri di dalam lemari (hanya terlihat oleh pemilik akun). | Wardrobe Digital |
## 🌐 Public API

* **[ API Wilayah Indonesia (emsifa.com)](https://www.emsifa.com/api-wilayah-indonesia/v2/provinces.json)**
   Memfasilitasi pengguna dalam memilih dan menentukan lokasi pertemuan (meeting point) yang presisi untuk pertukaran pakaian pada modul Swap Request. Fitur ini memanfaatkan API statis data wilayah untuk menyajikan pilihan lokasi bertingkat mulai dari Provinsi, Kabupaten/Kota, Kecamatan, hingga Desa/Kelurahan. Selain itu, koordinat geografis (latitude/longitude) dari wilayah yang dipilih dapat dimanfaatkan untuk menampilkan titik pusat lokasi pada peta atau menghitung estimasi jarak antar-pengguna.

---

## 👤 Role Pengguna & Target User

### **Role User**
* **User**: Dapat mengelola profil akun dan *wardrobe* digital, mencatat serta mengatur *outfit* melalui *Outfit Calendar*, menawarkan pakaian melalui *Items for Swap*, mengajukan *Swap Request* kepada pengguna lain, serta menyimpan pakaian atau *outfit* yang disukai melalui fitur *Bookmark*.
* **Admin**: Memiliki kewenangan untuk mengelola seluruh akun pengguna, termasuk melihat, mengubah, dan menghapus data akun pengguna.

### **Target User**
Orang-orang yang sering mengelola *fashion* mereka dan ingin memaksimalkan pakaian yang dimiliki.

---

## 🔗 Tautan Penting

* **Deployment PWS**: [https://stephanie-revalina-swapdrobe.pws.cs.ui.ac.id/](https://stephanie-revalina-swapdrobe.pws.cs.ui.ac.id/)
* **Desain Low-Fi Figma**: [Figma Low-Fi Design SwapMatch](https://www.figma.com/design/gSqXDCz8gnHd5gXU26yzIn/Untitled?node-id=0-1&t=yVCVLg0Ne6LHcpLZ-1)