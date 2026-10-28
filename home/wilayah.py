"""
Data wilayah Indonesia (provinsi & kabupaten/kota) untuk input lokasi Swapdrobe.

Sumber: EmSifa API Wilayah Indonesia v2
    https://www.emsifa.com/api-wilayah-indonesia/v2
    - provinces.json               -> daftar provinsi
    - regencies/{province_id}.json -> kabupaten/kota di provinsi tersebut
Respons dibungkus di properti `data` (metadata di `meta`).

Alur:
1. Server Django mengambil data dari API (urllib bawaan Python, tanpa library tambahan),
   lalu menyimpannya di cache server:
     - "segar"   : 24 jam, dipakai untuk semua request selama masih ada;
     - "cadangan": 30 hari, dipakai kalau API sedang bermasalah (server API down).
   Daftar 514 kab/kota TIDAK disimpan di database, hanya di cache.
2. Browser mengambil daftar ini satu kali per halaman lewat endpoint `home:location_data`
   (lihat static/js/location_autocomplete.js) lalu mencari di memori.
3. Saat form dikirim, kode wilayah yang dipilih dicek lagi di server (LocationField),
   jadi nilai lokasi pasti berasal dari daftar yang valid, bukan teks bebas.

Kalau sebagian provinsi gagal dimuat, data ditandai `complete=False` beserta nama
provinsinya, dan TIDAK disimpan sebagai data lengkap.
"""
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from django import forms
from django.core.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('WILAYAH_API_URL', 'https://www.emsifa.com/api-wilayah-indonesia/v2')
REQUEST_TIMEOUT = 8          # detik per request ke API
MAX_WORKERS = 8              # request kab/kota yang berjalan bersamaan

FRESH_KEY = 'wilayah:v2:fresh'
BACKUP_KEY = 'wilayah:v2:backup'
PARTIAL_KEY = 'wilayah:v2:partial'
REFRESH_LOCK_KEY = 'wilayah:v2:refresh-lock'
FRESH_SECONDS = 24 * 60 * 60
BACKUP_SECONDS = 30 * 24 * 60 * 60
PARTIAL_SECONDS = 2 * 60     # data tidak lengkap hanya ditahan sebentar supaya API tidak dibanjiri
REFRESH_LOCK_SECONDS = 30    # tombol "Coba lagi" paling cepat memicu pengambilan ulang tiap 30 detik

MSG_PICK = 'Pilih lokasi dari daftar rekomendasi.'
MSG_UNAVAILABLE = 'Data lokasi sedang tidak bisa dimuat, jadi pilihanmu belum bisa diperiksa. Coba lagi beberapa saat lagi.'

# Singkatan yang tetap huruf besar saat nama dari API berhuruf kapital semua (mis. "DKI JAKARTA")
_KEEP_UPPER = {'DKI', 'DI'}


class WilayahError(Exception):
    """Respons API tidak bisa dipakai (gagal diambil atau formatnya tidak dikenal)."""


# --------------------------------------------------------------------------- ambil dari API
def _fetch_json(path):
    request = Request(BASE_URL + path, headers={
        'Accept': 'application/json',
        'User-Agent': 'SwapDrobe/1.0 (+https://pws.cs.ui.ac.id)',
    })
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8'))


def _unwrap(payload):
    """Ambil daftar dari properti `data` (v2). Tetap menerima array biasa untuk berjaga-jaga."""
    if isinstance(payload, dict):
        payload = payload.get('data')
    if not isinstance(payload, list):
        raise WilayahError('Format respons API wilayah tidak dikenali.')
    return payload


def _code(item):
    return str(item.get('code') or item.get('id') or '').strip()


def _pretty(name):
    """Rapikan nama: "KOTA BOGOR" -> "Kota Bogor". Nama yang sudah rapi dibiarkan."""
    name = ' '.join(str(name or '').split())
    if not name.isupper():
        return name
    return ' '.join(word if word in _KEEP_UPPER else word.capitalize() for word in name.split(' '))


def _fetch_all():
    """Ambil semua provinsi lalu kab/kota tiap provinsi. Gagal total -> exception."""
    provinces = []
    for item in _unwrap(_fetch_json('/provinces.json')):
        code, name = _code(item), _pretty(item.get('name'))
        if code and name:
            provinces.append({'code': code, 'name': name})
    if not provinces:
        raise WilayahError('Daftar provinsi kosong.')

    def regencies_of(province):
        return _unwrap(_fetch_json(f"/regencies/{province['code']}.json"))

    locations, failed = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [(province, pool.submit(regencies_of, province)) for province in provinces]
        for province, future in futures:
            try:
                items = future.result()
            except Exception as exc:  # noqa: BLE001 - satu provinsi gagal tidak boleh menggagalkan semuanya
                logger.warning('API wilayah: kab/kota provinsi %s gagal dimuat: %s', province['name'], exc)
                failed.append(province)
                continue
            for item in items:
                code, city = _code(item), _pretty(item.get('name'))
                if code and city:
                    locations.append({
                        'code': code,
                        'city': city,
                        'province': province['name'],
                        'province_code': province['code'],
                        'label': f"{city}, {province['name']}",
                    })

    locations.sort(key=lambda loc: (loc['province'], loc['city']))
    return {
        'locations': locations,
        'complete': not failed,
        'failed_provinces': sorted(p['name'] for p in failed),
        'failed_province_codes': sorted(p['code'] for p in failed),
        'province_count': len(provinces),
        'fetched_at': time.time(),
    }


# --------------------------------------------------------------------------- data + cache
def get_locations(force_refresh=False):
    """
    Kembalikan dict:
      locations            daftar {code, city, province, province_code, label}
      complete             True kalau semua provinsi berhasil dimuat
      failed_provinces     nama provinsi yang gagal (kalau complete=False)
      stale                True kalau memakai data cadangan karena API bermasalah
      error                True kalau tidak ada data sama sekali
    """
    if force_refresh and not cache.add(REFRESH_LOCK_KEY, True, REFRESH_LOCK_SECONDS):
        force_refresh = False  # baru saja diambil ulang; jangan bebani API

    if not force_refresh:
        for key in (FRESH_KEY, PARTIAL_KEY):
            cached = cache.get(key)
            if cached:
                return dict(cached, stale=False, error=False)

    try:
        data = _fetch_all()
    except Exception as exc:  # noqa: BLE001 - API down, timeout, format berubah, dll.
        logger.warning('API wilayah gagal dimuat: %s', exc)
        data = None

    if data and data['complete']:
        cache.set(FRESH_KEY, data, FRESH_SECONDS)
        cache.set(BACKUP_KEY, data, BACKUP_SECONDS)
        cache.delete(PARTIAL_KEY)
        return dict(data, stale=False, error=False)

    backup = cache.get(BACKUP_KEY)
    if backup:
        return dict(backup, stale=True, error=False)

    if data:
        cache.set(PARTIAL_KEY, data, PARTIAL_SECONDS)
        return dict(data, stale=False, error=False)

    return {
        'locations': [], 'complete': False, 'failed_provinces': [], 'failed_province_codes': [],
        'province_count': 0, 'fetched_at': None, 'stale': False, 'error': True,
    }


def cached_location(code):
    """Lokasi untuk kode wilayah dari cache saja (tanpa memanggil API), atau None."""
    for key in (FRESH_KEY, BACKUP_KEY, PARTIAL_KEY):
        data = cache.get(key)
        if data:
            for loc in data['locations']:
                if loc['code'] == code:
                    return loc
    return None


def find_location(code):
    """Lokasi untuk kode wilayah (pakai cache; ambil dari API kalau cache kosong), atau None."""
    location = cached_location(code)
    if location is None:
        location = next((loc for loc in get_locations()['locations'] if loc['code'] == code), None)
    return location


def looks_like_code(value):
    """Kode wilayah API berupa angka (boleh dengan titik), mis. "32" atau "3201" / "32.01"."""
    value = str(value or '')
    return bool(value) and len(value) <= 20 and all(ch.isdigit() or ch == '.' for ch in value)


def city_keyword(city):
    """Nama kab/kota tanpa awalan, untuk mencocokkan data lama: "Kota Depok" -> "Depok"."""
    for prefix in ('Kabupaten ', 'Kab. ', 'Kota '):
        if city.startswith(prefix):
            return city[len(prefix):]
    return city


def resolve_location(code):
    """Cocokkan kode wilayah dengan data API. Kembalikan dict lokasi atau ValidationError."""
    code = str(code or '').strip()
    if not code:
        raise forms.ValidationError(MSG_PICK, code='required')
    data = get_locations()
    for loc in data['locations']:
        if loc['code'] == code:
            return loc
    # Kode tidak ditemukan. Kalau datanya memang tidak lengkap untuk kode ini, jangan bilang "tidak valid".
    if data['error'] or any(code.startswith(pc) for pc in data['failed_province_codes']):
        raise forms.ValidationError(MSG_UNAVAILABLE, code='unavailable')
    raise forms.ValidationError(MSG_PICK, code='invalid')


class LocationField(forms.CharField):
    """
    Field kode kabupaten/kota (input tersembunyi yang diisi autocomplete).
    cleaned_data berisi dict lokasi hasil pengecekan di server:
        {code, city, province, province_code, label}
    Tampilan input-nya: templates/home/partials/location_input.html
    """
    widget = forms.HiddenInput
    default_error_messages = {'required': MSG_PICK}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 20)
        super().__init__(*args, **kwargs)

    def clean(self, value):
        code = super().clean(value)
        if not code:
            return None
        return resolve_location(code)
