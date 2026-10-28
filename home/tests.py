"""
Test integrasi API Wilayah Indonesia (home/wilayah.py) dan input lokasi.

API asli TIDAK dipanggil saat test: `home.wilayah._fetch_json` diganti FakeWilayahAPI,
yang meniru format respons EmSifa v2 (daftar dibungkus di `data`, metadata di `meta`).
"""
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap

from . import wilayah

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'wilayah-tests'}}


class FakeWilayahAPI:
    """Pengganti _fetch_json. `fail` = kode provinsi yang dibuat gagal, `down` = API mati total."""

    PROVINCES = [{'code': '32', 'name': 'JAWA BARAT'}, {'code': '31', 'name': 'DKI JAKARTA'}]
    REGENCIES = {
        '32': [{'code': '3201', 'name': 'KABUPATEN BOGOR'},
               {'code': '3271', 'name': 'KOTA BOGOR'},
               {'code': '3273', 'name': 'KOTA BANDUNG'},
               {'code': '3276', 'name': 'KOTA DEPOK'}],
        '31': [{'code': '3174', 'name': 'KOTA ADMINISTRASI JAKARTA SELATAN'}],
    }

    def __init__(self, fail=(), down=False):
        self.fail, self.down, self.calls = set(fail), down, []

    def __call__(self, path):
        self.calls.append(path)
        if self.down:
            raise OSError('API down')
        if path == '/provinces.json':
            return {'data': self.PROVINCES, 'meta': {'total': len(self.PROVINCES)}}
        code = path.rsplit('/', 1)[-1].removesuffix('.json')
        if code in self.fail:
            raise OSError(f'timeout provinsi {code}')
        return {'data': self.REGENCIES[code], 'meta': {'province_code': code}}


class WilayahAPIMixin:
    """
    Pakai di TestCase yang mengirim form berisi lokasi: API tiruan + cache memori.
    Dipasang di level class, jadi tetap aktif walaupun setUp() TestCase tidak memanggil super().
    """
    fake_api = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake_api = FakeWilayahAPI()
        patcher = mock.patch('home.wilayah._fetch_json', side_effect=lambda path: cls.fake_api(path))
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cache_settings = override_settings(CACHES=LOCMEM_CACHE)
        cache_settings.enable()
        cls.addClassCleanup(cache_settings.disable)
        cache.clear()

    def setUp(self):
        super().setUp()
        type(self).fake_api = FakeWilayahAPI()   # API normal lagi di tiap test
        cache.clear()


class WilayahDataTests(WilayahAPIMixin, TestCase):
    def test_reads_data_property_and_builds_labels(self):
        data = wilayah.get_locations()
        self.assertTrue(data['complete'])
        self.assertFalse(data['error'])
        labels = [loc['label'] for loc in data['locations']]
        self.assertIn('Kota Bogor, Jawa Barat', labels)
        self.assertIn('Kota Administrasi Jakarta Selatan, DKI Jakarta', labels)
        self.assertEqual(len(labels), 5)

    def test_uses_cache_instead_of_calling_api_again(self):
        wilayah.get_locations()
        calls = len(self.fake_api.calls)
        wilayah.get_locations()
        wilayah.get_locations()
        self.assertEqual(len(self.fake_api.calls), calls)

    def test_partial_failure_is_not_reported_as_complete(self):
        self.fake_api.fail = {'31'}
        data = wilayah.get_locations()
        self.assertFalse(data['complete'])
        self.assertEqual(data['failed_provinces'], ['DKI Jakarta'])
        self.assertIsNone(cache.get(wilayah.FRESH_KEY))   # data tidak lengkap tidak disimpan sebagai data segar

    def test_backup_is_used_when_api_is_down(self):
        wilayah.get_locations()
        cache.delete(wilayah.FRESH_KEY)                    # data segar kedaluwarsa
        self.fake_api.down = True
        data = wilayah.get_locations()
        self.assertTrue(data['stale'])
        self.assertTrue(data['complete'])
        self.assertEqual(len(data['locations']), 5)

    def test_error_when_api_down_without_backup(self):
        self.fake_api.down = True
        data = wilayah.get_locations()
        self.assertTrue(data['error'])
        self.assertEqual(data['locations'], [])

    def test_resolve_location_validates_code_on_server(self):
        self.assertEqual(wilayah.resolve_location('3276')['label'], 'Kota Depok, Jawa Barat')
        with self.assertRaisesMessage(Exception, wilayah.MSG_PICK):
            wilayah.resolve_location('9999')
        with self.assertRaisesMessage(Exception, wilayah.MSG_PICK):
            wilayah.resolve_location('Depok')       # teks bebas tidak diterima

    def test_resolve_location_reports_unavailable_when_province_failed(self):
        self.fake_api.fail = {'31'}
        with self.assertRaisesMessage(Exception, wilayah.MSG_UNAVAILABLE):
            wilayah.resolve_location('3174')
        self.assertEqual(wilayah.resolve_location('3273')['city'], 'Kota Bandung')

    def test_location_endpoint(self):
        response = self.client.get(reverse('home:location_data'))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['complete'])
        self.assertEqual(body['locations'][0].keys(), {'code', 'city', 'province', 'label'})

    def test_location_endpoint_returns_503_when_api_down(self):
        self.fake_api.down = True
        response = self.client.get(reverse('home:location_data'))
        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()['error'])


class LocationFormsTests(WilayahAPIMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fanny', password='Password123!')
        profile = UserProfile.for_user(self.user)
        profile.phone_number = '081200000001'
        profile.save()
        self.client.login(username='fanny', password='Password123!')
        self.item = ClothingItem.objects.create(user=self.user, name='Kemeja Linen', category='atasan',
                                                size='M', color='putih', condition='like_new', gender='unisex')

    def test_add_listing_saves_structured_location(self):
        response = self.client.post(reverse('items_for_swap:add'), {
            'clothing_item': self.item.pk, 'meeting_city_code': '3276', 'meeting_place': 'Stasiun UI',
            'reason': 'Masih bagus, cari ukuran L',
        })
        self.assertEqual(response.status_code, 302)
        listing = ItemForSwap.objects.get(clothing_item=self.item)
        self.assertEqual(listing.meeting_city_code, '3276')
        self.assertEqual(listing.meeting_city, 'Kota Depok')
        self.assertEqual(listing.meeting_province, 'Jawa Barat')
        self.assertEqual(listing.meeting_location, 'Stasiun UI, Kota Depok, Jawa Barat')
        self.assertEqual(listing.meeting_area, 'Kota Depok')

    def test_add_listing_rejects_free_text_location(self):
        response = self.client.post(reverse('items_for_swap:add'), {
            'clothing_item': self.item.pk, 'meeting_city_code': 'Depok', 'reason': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('meeting_city_code', response.context['form'].errors)
        self.assertFalse(ItemForSwap.objects.filter(clothing_item=self.item).exists())

    def test_edit_legacy_listing_keeps_old_text_as_place(self):
        listing = ItemForSwap.objects.create(clothing_item=self.item, user=self.user, meeting_location='Margo City')
        response = self.client.get(reverse('items_for_swap:edit', args=[listing.pk]))
        self.assertEqual(response.context['form']['meeting_place'].value(), 'Margo City')
        response = self.client.post(reverse('items_for_swap:edit', args=[listing.pk]), {
            'meeting_city_code': '3276', 'meeting_place': 'Margo City', 'reason': 'Kemeja linen',
        })
        self.assertEqual(response.status_code, 302)
        listing.refresh_from_db()
        self.assertEqual(listing.meeting_location, 'Margo City, Kota Depok, Jawa Barat')

    def test_add_listing_requires_all_fields(self):
        response = self.client.post(reverse('items_for_swap:add'), {
            'clothing_item': '', 'meeting_city_code': '', 'meeting_place': ' ', 'reason': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['form'].errors),
                         {'clothing_item', 'meeting_city_code', 'meeting_place', 'reason'})
        self.assertFalse(ItemForSwap.objects.exists())

    def test_edit_listing_requires_place_and_description(self):
        listing = ItemForSwap.objects.create(clothing_item=self.item, user=self.user, meeting_location='Depok')
        response = self.client.post(reverse('items_for_swap:edit', args=[listing.pk]), {
            'meeting_city_code': '3276', 'meeting_place': '', 'reason': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context['form'].errors), {'meeting_place', 'reason'})

    def test_catalog_filter_by_location_code_includes_legacy_text(self):
        other = User.objects.create_user('rico', password='Password123!')
        coded = ClothingItem.objects.create(user=other, name='Jaket', category='atasan', size='L',
                                            color='hitam', condition='good', gender='unisex')
        legacy = ClothingItem.objects.create(user=other, name='Rok', category='bawahan', size='S',
                                             color='merah', condition='good', gender='wanita')
        far = ClothingItem.objects.create(user=other, name='Topi', category='aksesori', size='M',
                                          color='biru', condition='good', gender='unisex')
        ItemForSwap.list_item(coded, other, location=wilayah.resolve_location('3276'))
        ItemForSwap.list_item(legacy, other, meeting_location='Depok, dekat stasiun')
        ItemForSwap.list_item(far, other, location=wilayah.resolve_location('3273'))

        response = self.client.get(reverse('home:index'), {'location': '3276'})
        names = {entry.clothing_item.name for entry in response.context['page'].object_list}
        self.assertEqual(names, {'Jaket', 'Rok'})
        self.assertContains(response, 'Kota Depok, Jawa Barat')
