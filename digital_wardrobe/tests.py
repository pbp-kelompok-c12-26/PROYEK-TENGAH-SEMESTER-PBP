import io
import json
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from items_for_swap.models import ItemForSwap
from outfit_calendar.models import OutfitSchedule, ScheduledItem
from swap_requests.models import SwapRequest

from .forms import ClothingItemForm, OutfitForm
from .models import ClothingItem, Outfit
from .templatetags.wardrobe_tags import swap_item_count
from .views import BULK_DELETE_LIMIT, BULK_LIMIT, WRITE_LIMIT

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
TEMP_MEDIA = tempfile.mkdtemp()
# Penghitung rate limit disimpan di cache: pakai cache memori yang dikosongkan tiap test
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'wardrobe-tests'}}


@override_settings(CACHES=LOCMEM_CACHE)
class WardrobeTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

# PNG 1x1 piksel untuk test foto
PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
           b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BulkDeleteTests(WardrobeTestCase):
    """Hapus banyak pakaian sekaligus (views.item_bulk_delete + ClothingItem.objects.remove_many)."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fanny', password='Password123!')
        self.other = User.objects.create_user('rico', password='Password123!')
        self.client.login(username='fanny', password='Password123!')
        self.url = reverse('digital_wardrobe:item_bulk_delete')

    def make_item(self, name, user=None, **extra):
        return ClothingItem.objects.create(
            user=user or self.user, name=name, category='top', size='M',
            color='neutral', condition='good', gender='unisex', **extra)

    def post(self, ids, ajax=True):
        return self.client.post(self.url, {'items': [str(pk) for pk in ids]}, **(AJAX if ajax else {}))

    def active_swap(self, item):
        """Swap request Pending yang menawarkan `item`."""
        wanted = self.make_item('Jaket Rico', user=self.other)
        return SwapRequest.objects.create(
            requester=self.user, owner=self.other, requested_item=wanted, offered_item=item,
            requested_item_name=wanted.name, offered_item_name=item.name, status=SwapRequest.PENDING)

    # ---------- berhasil ----------
    def test_deletes_unused_and_archives_items_used_in_outfit(self):
        unused = self.make_item('Kaos Polos')
        used = self.make_item('Kemeja Linen')
        outfit = Outfit.objects.create(user=self.user, name='Kampus')
        outfit.items.add(used)

        response = self.post([unused.pk, used.pk])

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(set(data['removed']), {unused.pk, used.pk})
        self.assertEqual(data['total_items'], 0)
        self.assertIn('2 pakaian dihapus', data['message'])
        self.assertFalse(ClothingItem.objects.filter(pk=unused.pk).exists())   # dihapus permanen
        used.refresh_from_db()
        self.assertTrue(used.is_deleted)                                        # diarsipkan (soft-delete)
        self.assertIn(used, outfit.items.all())                                 # outfit tetap utuh
        self.assertEqual(used.status_label, 'Sudah dihapus dari lemari')

    def test_photo_file_is_removed_after_commit(self):
        item = self.make_item('Rok Plisket', image=SimpleUploadedFile('rok.png', PNG_1PX, content_type='image/png'))
        storage, path = item.image.storage, item.image.name
        self.assertTrue(storage.exists(path))
        with self.captureOnCommitCallbacks(execute=True):
            self.post([item.pk])
        self.assertFalse(storage.exists(path))

    def test_without_ajax_redirects_with_message(self):
        item = self.make_item('Celana Kulot')
        response = self.post([item.pk], ajax=False)
        self.assertRedirects(response, reverse('digital_wardrobe:index'))
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertEqual(messages, ['1 pakaian dihapus dari lemarimu.'])

    # ---------- aturan & otorisasi ----------
    def test_items_of_other_users_are_ignored(self):
        mine = self.make_item('Blazer')
        theirs = self.make_item('Blazer Rico', user=self.other)
        data = self.post([mine.pk, theirs.pk]).json()
        self.assertEqual(data['removed'], [mine.pk])
        self.assertIn('1 pakaian tidak ditemukan', data['message'])
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_deleted)

    def test_items_listed_for_swap_or_already_deleted_are_ignored(self):
        listed = self.make_item('Hoodie', is_listed_for_swap=True)
        archived = self.make_item('Sweater')
        archived.remove_from_wardrobe()   # belum pernah dipakai -> terhapus permanen
        data = self.post([listed.pk, archived.pk]).json()
        self.assertEqual(data['removed'], [])
        self.assertIn('Tidak ada pakaian yang dihapus', data['message'])
        listed.refresh_from_db()
        self.assertFalse(listed.is_deleted)

    def test_items_in_active_swap_request_are_skipped(self):
        locked = self.make_item('Dress Bunga')
        free = self.make_item('Topi Bucket')
        self.active_swap(locked)

        data = self.post([locked.pk, free.pk]).json()

        self.assertEqual(data['removed'], [free.pk])
        self.assertEqual(data['skipped'], [locked.pk])
        self.assertIn('1 dilewati karena sedang dipakai dalam swap request: "Dress Bunga"', data['message'])
        locked.refresh_from_db()
        self.assertFalse(locked.is_deleted)

    def test_finished_swap_request_does_not_lock_item(self):
        item = self.make_item('Kemeja Kotak')
        swap = self.active_swap(item)
        swap.status = SwapRequest.REJECTED
        swap.save()
        data = self.post([item.pk]).json()
        self.assertEqual(data['removed'], [item.pk])

    # ---------- input tidak valid ----------
    def test_empty_selection_is_rejected(self):
        response = self.post([])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['message'], 'Pilih minimal 1 pakaian yang ingin dihapus.')

    def test_non_numeric_ids_are_rejected(self):
        response = self.client.post(self.url, {'items': ['abc', '-1', '']}, **AJAX)
        self.assertEqual(response.status_code, 400)

    def test_selection_over_limit_is_rejected(self):
        item = self.make_item('Kaos')
        ids = [item.pk] + list(range(10_000, 10_000 + BULK_DELETE_LIMIT))
        response = self.post(ids)
        self.assertEqual(response.status_code, 400)
        self.assertIn(f'Maksimal {BULK_DELETE_LIMIT}', response.json()['message'])
        self.assertTrue(ClothingItem.objects.filter(pk=item.pk).exists())

    def test_empty_selection_without_ajax_redirects_with_error(self):
        response = self.post([], ajax=False)
        self.assertRedirects(response, reverse('digital_wardrobe:index'))

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_login_required(self):
        item = self.make_item('Kaos')
        self.client.logout()
        response = self.post([item.pk])                  # AJAX: 401 + pesan
        self.assertEqual(response.status_code, 401)
        response = self.post([item.pk], ajax=False)      # form biasa: ke halaman login
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response['Location'])
        self.assertTrue(ClothingItem.objects.filter(pk=item.pk).exists())

    # ---------- performa ----------
    def test_query_count_does_not_grow_with_selection(self):
        def queries_for(count):
            items = [self.make_item(f'Kaos {count}-{i}') for i in range(count)]
            outfit = Outfit.objects.create(user=self.user, name=f'Outfit {count}')
            outfit.items.add(*items[: count // 2])   # separuh diarsipkan, separuh dihapus
            with CaptureQueriesContext(connection) as ctx:
                self.post([item.pk for item in items])
            return len(ctx.captured_queries)

        small, large = queries_for(2), queries_for(8)
        self.assertEqual(small, large)

    # ---------- tampilan ----------
    def test_index_shows_select_mode_controls(self):
        self.make_item('Kaos')
        locked = self.make_item('Dress')
        self.active_swap(locked)
        response = self.client.get(reverse('digital_wardrobe:index'))
        self.assertContains(response, 'data-select-toggle')
        self.assertContains(response, 'id="bulk-delete-form"')
        self.assertContains(response, f'value="{locked.pk}" form="bulk-delete-form" data-select-item disabled')

    def test_index_without_items_hides_select_mode(self):
        response = self.client.get(reverse('digital_wardrobe:index'))
        self.assertNotContains(response, 'id="bulk-delete-form"')


class HtmxInteractionTests(WardrobeTestCase):
    """Filter / pindah tab / hapus tanpa reload lewat HTMX (views.index, item_delete, outfit_delete)."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fanny', password='Password123!')
        self.other = User.objects.create_user('rico', password='Password123!')
        self.client.login(username='fanny', password='Password123!')
        self.index = reverse('digital_wardrobe:index')

    def make_item(self, name, user=None, **extra):
        fields = {'category': 'top', 'size': 'M', 'color': 'neutral', 'condition': 'good', 'gender': 'unisex', **extra}
        return ClothingItem.objects.create(user=user or self.user, name=name, **fields)

    def hx(self, target):
        return {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TARGET': target}

    def trigger(self, response):
        return json.loads(response['HX-Trigger'])

    # ---------- potongan halaman ----------
    def test_full_page_without_htmx(self):
        self.make_item('Kemeja Linen')
        response = self.client.get(self.index)
        self.assertContains(response, 'class="wd-hero"')
        self.assertContains(response, 'id="wardrobe-content"')
        self.assertContains(response, 'htmx-2.0.4.min.js')
        self.assertIn('HX-Request', response['Vary'])

    def test_filter_returns_only_results(self):
        self.make_item('Kemeja Linen')
        self.make_item('Celana Kulot', category='bottom')
        response = self.client.get(self.index, {'tab': 'pakaian', 'q': 'linen'}, **self.hx('wardrobe-results'))
        html = response.content.decode()
        self.assertTrue(html.lstrip().startswith('<div id="wardrobe-results"'))
        self.assertNotIn('wd-hero', html)
        self.assertNotIn('<form method="get" class="wd-filter"', html)
        self.assertIn('Kemeja Linen', html)
        self.assertNotIn('Celana Kulot', html)

    def test_category_and_idle_filters_with_htmx(self):
        self.make_item('Kemeja Linen')
        self.make_item('Celana Kulot', category='bottom')
        response = self.client.get(self.index, {'category': 'bottom', 'show': 'all'}, **self.hx('wardrobe-results'))
        self.assertContains(response, 'Celana Kulot')
        self.assertNotContains(response, 'Kemeja Linen')
        response = self.client.get(self.index, {'show': 'idle'}, **self.hx('wardrobe-results'))
        self.assertContains(response, 'Tidak ada pakaian yang cocok')   # baju baru belum "jarang dipakai"

    def test_tab_switch_returns_tab_content(self):
        Outfit.objects.create(user=self.user, name='Kampus')
        response = self.client.get(self.index, {'tab': 'outfit'}, **self.hx('wardrobe-content'))
        html = response.content.decode()
        self.assertTrue(html.lstrip().startswith('<div id="wardrobe-content"'))
        self.assertIn('class="wd-tabs"', html)
        self.assertIn('Kampus', html)
        self.assertNotIn('wd-hero', html)

    def test_history_restore_gets_full_page(self):
        headers = {**self.hx('wardrobe-results'), 'HTTP_HX_HISTORY_RESTORE_REQUEST': 'true'}
        response = self.client.get(self.index, **headers)
        self.assertContains(response, 'class="wd-hero"')

    def test_load_more_link_uses_htmx(self):
        for i in range(13):   # PAGE_SIZE = 12
            self.make_item(f'Kaos {i}')
        response = self.client.get(self.index, **self.hx('wardrobe-results'))
        self.assertContains(response, 'hx-get="?limit=24" hx-target="#wardrobe-results"')
        self.assertContains(response, 'Menampilkan <span data-shown-count>12</span> dari <span data-filtered-total>13</span>')

    # ---------- hapus ----------
    def test_htmx_delete_item_returns_empty_and_event(self):
        item = self.make_item('Kaos Polos')
        self.make_item('Kemeja Linen')
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]), **self.hx(f'item-{item.pk}'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')
        event = self.trigger(response)['wardrobe:deleted']
        self.assertEqual(event['kind'], 'item')
        self.assertEqual(event['total'], 1)
        self.assertEqual(event['message'], '"Kaos Polos" sudah dihapus dari lemarimu.')
        self.assertFalse(ClothingItem.objects.filter(pk=item.pk).exists())
        # Tanpa Django messages, supaya pesan tidak muncul dua kali di halaman berikutnya
        self.assertNotContains(self.client.get(self.index), 'sudah dihapus dari lemarimu')

    def test_htmx_delete_locked_item_returns_card_again(self):
        item = self.make_item('Dress Bunga')
        wanted = self.make_item('Jaket Rico', user=self.other)
        SwapRequest.objects.create(requester=self.user, owner=self.other, requested_item=wanted, offered_item=item,
                                   requested_item_name=wanted.name, offered_item_name=item.name,
                                   status=SwapRequest.PENDING)
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]), **self.hx(f'item-{item.pk}'))
        self.assertContains(response, f'id="item-{item.pk}"')
        self.assertIn('sedang dipakai dalam swap request', self.trigger(response)['wardrobe:delete-failed']['message'])
        item.refresh_from_db()
        self.assertFalse(item.is_deleted)

    def test_htmx_delete_listed_item_removes_card_with_message(self):
        item = self.make_item('Hoodie', is_listed_for_swap=True)
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]), **self.hx(f'item-{item.pk}'))
        self.assertEqual(response.content, b'')
        self.assertIn('wardrobe:delete-failed', self.trigger(response))

    def test_htmx_delete_other_users_item_is_403(self):
        item = self.make_item('Blazer Rico', user=self.other)
        with self.assertLogs('swapdrobe.security', 'WARNING'):
            response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]), **self.hx(f'item-{item.pk}'))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['message'], 'Kamu tidak punya akses ke pakaian ini.')
        self.assertTrue(ClothingItem.objects.filter(pk=item.pk).exists())

    def test_delete_without_htmx_still_redirects(self):
        item = self.make_item('Kaos Polos')
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]))
        self.assertRedirects(response, self.index)

    def test_htmx_delete_outfit(self):
        outfit = Outfit.objects.create(user=self.user, name='Kampus')
        response = self.client.post(reverse('digital_wardrobe:outfit_delete', args=[outfit.pk]), **self.hx(f'outfit-{outfit.pk}'))
        self.assertEqual(response.content, b'')
        event = self.trigger(response)['wardrobe:deleted']
        self.assertEqual((event['kind'], event['total']), ('outfit', 0))
        self.assertFalse(Outfit.objects.filter(pk=outfit.pk).exists())

    def test_cards_have_htmx_delete_hooks(self):
        item = self.make_item('Kaos Polos')
        self.assertContains(self.client.get(self.index), f'data-delete-card="item-{item.pk}"')


class SecurityTests(WardrobeTestCase):
    """Decorator keamanan buatan sendiri (digital_wardrobe/security.py)."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fanny', password='Password123!')
        self.other = User.objects.create_user('rico', password='Password123!')
        self.client.login(username='fanny', password='Password123!')
        self.theirs = ClothingItem.objects.create(
            user=self.other, name='Jaket Rico', category='outerwear', size='L',
            color='earth', condition='good', gender='unisex')
        self.their_outfit = Outfit.objects.create(user=self.other, name='Outfit Rico')

    # ---------- @owner_required: 403 + pesan jelas ----------
    def test_other_users_item_pages_are_forbidden_with_clear_page(self):
        urls = [reverse('digital_wardrobe:item_detail', args=[self.theirs.pk]),
                reverse('digital_wardrobe:outfit_detail', args=[self.their_outfit.pk])]
        for url in urls:
            with self.subTest(url=url), self.assertLogs('swapdrobe.security', 'WARNING') as logs:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 403)
                self.assertTemplateUsed(response, 'digital_wardrobe/error.html')
                self.assertContains(response, 'Kamu tidak punya akses', status_code=403)
                self.assertContains(response, 'Kembali ke Lemari', status_code=403)
                self.assertIn('user:', logs.output[0])

    def test_other_users_data_cannot_be_changed(self):
        cases = [
            ('item_update', self.theirs.pk, {'name': 'Diubah'}),
            ('item_delete', self.theirs.pk, {}),
            ('outfit_update', self.their_outfit.pk, {'name': 'Diubah'}),
            ('outfit_delete', self.their_outfit.pk, {}),
        ]
        for name, pk, data in cases:
            with self.subTest(view=name), self.assertLogs('swapdrobe.security', 'WARNING'):
                response = self.client.post(reverse(f'digital_wardrobe:{name}', args=[pk]), data, **AJAX)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(response.json()['ok'])
        self.theirs.refresh_from_db()
        self.their_outfit.refresh_from_db()
        self.assertEqual((self.theirs.name, self.theirs.is_deleted), ('Jaket Rico', False))
        self.assertEqual(self.their_outfit.name, 'Outfit Rico')

    def test_missing_item_is_404(self):
        response = self.client.get(reverse('digital_wardrobe:item_detail', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_own_item_is_still_accessible(self):
        mine = ClothingItem.objects.create(user=self.user, name='Kemeja', category='top', size='M',
                                           color='neutral', condition='good', gender='unisex')
        self.assertEqual(self.client.get(reverse('digital_wardrobe:item_detail', args=[mine.pk])).status_code, 200)

    # ---------- @wardrobe_login_required ----------
    def test_expired_session_on_ajax_returns_401_with_login_url(self):
        self.client.logout()
        response = self.client.get(reverse('digital_wardrobe:item_create'), **AJAX)
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertEqual(data['message'], 'Sesi kamu sudah habis. Silakan masuk lagi.')
        self.assertIn('next=/digital-wardrobe/', data['login_url'])

    def test_expired_session_on_htmx_returns_401(self):
        self.client.logout()
        response = self.client.get(reverse('digital_wardrobe:index'),
                                   HTTP_HX_REQUEST='true', HTTP_HX_TARGET='wardrobe-results')
        self.assertEqual(response.status_code, 401)

    def test_anonymous_page_visit_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse('digital_wardrobe:index'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next=/digital-wardrobe/",
                             fetch_redirect_response=False)

    # ---------- @rate_limit ----------
    def test_write_rate_limit(self):
        url = reverse('digital_wardrobe:outfit_create')
        for _ in range(WRITE_LIMIT):
            self.assertEqual(self.client.post(url, {}, **AJAX).status_code, 400)   # form kosong, tapi dihitung
        with self.assertLogs('swapdrobe.security', 'WARNING'):
            response = self.client.post(url, {}, **AJAX)
        self.assertEqual(response.status_code, 429)
        self.assertGreaterEqual(int(response['Retry-After']), 1)
        self.assertIn('Terlalu banyak permintaan', response.json()['message'])

    def test_rate_limit_is_per_user_and_ignores_get(self):
        url = reverse('digital_wardrobe:outfit_create')
        for _ in range(WRITE_LIMIT + 5):
            self.assertEqual(self.client.get(url, **AJAX).status_code, 200)   # membuka form tidak dihitung
        for _ in range(WRITE_LIMIT):
            self.client.post(url, {}, **AJAX)
        self.client.login(username='rico', password='Password123!')
        self.assertEqual(self.client.post(url, {}, **AJAX).status_code, 400)   # user lain punya kuota sendiri

    def test_rate_limit_resets_in_next_window(self):
        url = reverse('digital_wardrobe:item_bulk_delete')
        with mock.patch('digital_wardrobe.security.time.time', return_value=1_000_000.0):
            for _ in range(BULK_LIMIT):
                self.client.post(url, {'items': ['1']}, **AJAX)
            with self.assertLogs('swapdrobe.security', 'WARNING'):
                self.assertEqual(self.client.post(url, {'items': ['1']}, **AJAX).status_code, 429)
        with mock.patch('digital_wardrobe.security.time.time', return_value=1_000_060.0):
            self.assertEqual(self.client.post(url, {'items': ['1']}, **AJAX).status_code, 200)

    def test_rate_limited_page_request_shows_error_page(self):
        url = reverse('digital_wardrobe:item_bulk_delete')
        for _ in range(BULK_LIMIT):
            self.client.post(url, {'items': ['1']})
        with self.assertLogs('swapdrobe.security', 'WARNING'):
            response = self.client.post(url, {'items': ['1']})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Terlalu banyak permintaan', status_code=429)


# ======================================================================
# Test unit Model, Form, View (CRUD dasar) — target coverage > 90%
# ======================================================================

def png_upload(name='baju.png', size=(8, 8)):
    """Foto PNG asli (dibuat Pillow) untuk diunggah lewat form."""
    buffer = io.BytesIO()
    Image.new('RGB', size, (215, 136, 178)).save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def item_data(**extra):
    """Data POST form pakaian yang valid."""
    return {'name': 'Kemeja Linen', 'category': 'top', 'size': 'M', 'shoe_size': '', 'gender': 'unisex',
            'condition': 'good', 'color': 'neutral', 'description': 'Bahan adem', **extra}


class WardrobeDataMixin:
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('fanny', password='Password123!')
        self.other = User.objects.create_user('rico', password='Password123!')
        self.client.login(username='fanny', password='Password123!')
        self.index = reverse('digital_wardrobe:index')

    def make_item(self, name='Kaos', user=None, **extra):
        fields = {'category': 'top', 'size': 'M', 'color': 'neutral', 'condition': 'good', 'gender': 'unisex', **extra}
        return ClothingItem.objects.create(user=user or self.user, name=name, **fields)

    def make_outfit(self, name='Kampus', items=(), user=None):
        outfit = Outfit.objects.create(user=user or self.user, name=name)
        outfit.items.add(*items)
        return outfit

    def lock_with_swap(self, item):
        wanted = self.make_item('Barang Rico', user=self.other)
        return SwapRequest.objects.create(
            requester=self.user, owner=self.other, requested_item=wanted, offered_item=item,
            requested_item_name=wanted.name, offered_item_name=item.name, status=SwapRequest.PENDING)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ClothingItemModelTests(WardrobeDataMixin, WardrobeTestCase):
    def test_str_and_size_label(self):
        item = self.make_item('Kemeja')
        self.assertEqual(str(item), 'Kemeja (Atasan)')
        self.assertEqual(item.size_label, 'M')
        shoe = self.make_item('Sneakers', category='footwear', size='', shoe_size=39)
        self.assertTrue(shoe.is_footwear)
        self.assertEqual(shoe.size_label, 'EU 39')
        self.assertEqual(self.make_item('Sepatu', category='footwear', size='').size_label, '-')
        self.assertEqual(self.make_item('Topi', size='').size_label, '-')

    def test_querysets(self):
        mine = self.make_item('Kemeja')
        listed = self.make_item('Hoodie', is_listed_for_swap=True)
        archived = self.make_item('Sweater')
        self.make_outfit(items=[archived])
        archived.remove_from_wardrobe()
        self.make_item('Punya Rico', user=self.other)
        self.assertEqual(list(ClothingItem.objects.in_wardrobe(self.user)), [mine])
        self.assertEqual(list(ClothingItem.objects.available_for_swap(self.user)), [mine])
        self.assertEqual(list(ClothingItem.objects.listed_for_swap(self.user)), [listed])
        self.assertNotIn(archived, ClothingItem.objects.active())

    def test_status_label(self):
        item = self.make_item('Kemeja')
        self.assertEqual(item.status_label, '')
        item.is_listed_for_swap = True
        self.assertEqual(item.status_label, 'Sedang ditawarkan')
        item.deleted_at = timezone.now()
        self.assertEqual(item.status_label, 'Sudah dihapus dari lemari')
        self.assertEqual(item.seen_by(self.other.pk).status_label, 'Pakaian tidak tersedia')
        self.assertTrue(item.is_swapped_away)
        self.assertFalse(item.seen_by(self.user.pk).is_swapped_away)

    def test_refresh_idle(self):
        old = self.make_item('Lama')
        worn = self.make_item('Baru dipakai')
        long_ago = timezone.now() - timedelta(days=ClothingItem.IDLE_AFTER_DAYS + 5)
        ClothingItem.objects.filter(pk__in=[old.pk, worn.pk]).update(created_at=long_ago)
        ClothingItem.objects.filter(pk=worn.pk).update(last_worn_date=timezone.localdate(), is_idle=True)
        ClothingItem.objects.refresh_idle(self.user)
        old.refresh_from_db()
        worn.refresh_from_db()
        self.assertTrue(old.is_idle)
        self.assertFalse(worn.is_idle)

    def test_remove_from_wardrobe(self):
        unused = self.make_item('Belum dipakai', image=png_upload())
        path = unused.image.name
        self.assertEqual(unused.remove_from_wardrobe(), 'deleted')
        self.assertFalse(ClothingItem.objects.filter(pk=unused.pk).exists())
        self.assertFalse(unused.image.storage.exists(path))

        used = self.make_item('Dipakai', is_listed_for_swap=True)
        self.make_outfit(items=[used])
        self.assertTrue(used.is_in_use())
        self.assertEqual(used.remove_from_wardrobe(), 'archived')
        used.refresh_from_db()
        self.assertTrue(used.is_deleted)
        self.assertFalse(used.is_listed_for_swap)

        locked = self.make_item('Dikunci')
        self.lock_with_swap(locked)
        with self.assertRaises(ValidationError):
            locked.remove_from_wardrobe()

    def test_item_used_in_calendar_or_swap_listing_is_in_use(self):
        scheduled = self.make_item('Dijadwalkan')
        schedule = OutfitSchedule.objects.create(user=self.user, date=timezone.localdate(), outfit_name='Kampus')
        ScheduledItem.objects.create(schedule=schedule, clothing_item=scheduled, name=scheduled.name)
        self.assertTrue(scheduled.is_in_use())
        listed = self.make_item('Pernah ditawarkan')
        ItemForSwap.objects.create(clothing_item=listed, user=self.user, meeting_location='Depok')
        self.assertTrue(listed.is_in_use())
        self.assertFalse(self.make_item('Baru').is_in_use())


class OutfitModelTests(WardrobeDataMixin, WardrobeTestCase):
    def test_str(self):
        self.assertEqual(str(self.make_outfit('Kondangan')), 'Kondangan')

    def test_validate_items(self):
        mine = [self.make_item(f'Kaos {i}') for i in range(6)]
        Outfit.validate_items(self.user, mine[:5])
        with self.assertRaisesMessage(ValidationError, 'minimal 1'):
            Outfit.validate_items(self.user, [])
        with self.assertRaisesMessage(ValidationError, 'maksimal 5'):
            Outfit.validate_items(self.user, mine)
        with self.assertRaisesMessage(ValidationError, 'lemarimu sendiri'):
            Outfit.validate_items(self.user, [mine[0], self.make_item('Punya Rico', user=self.other)])


class TemplateTagTests(WardrobeDataMixin, WardrobeTestCase):
    def test_swap_item_count(self):
        self.make_item('Hoodie', is_listed_for_swap=True)
        self.assertEqual(swap_item_count(self.user), 1)
        self.assertEqual(swap_item_count(AnonymousUser()), 0)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ClothingItemFormTests(WardrobeDataMixin, WardrobeTestCase):
    def form(self, image=True, **extra):
        files = {'image': png_upload()} if image else {}
        return ClothingItemForm(item_data(**extra), files)

    def test_valid_form(self):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.is_footwear)

    def test_required_fields_use_indonesian_messages(self):
        form = ClothingItemForm({}, {})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['name'], ['Wajib diisi.'])
        self.assertEqual(form.errors['image'], ['Foto pakaian wajib diunggah.'])
        self.assertEqual(form.fields['category'].choices[0], ('', 'Pilih kategori'))

    def test_clothes_need_letter_size_and_shoes_need_number(self):
        form = self.form(size='')
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['size'], ['Wajib diisi.'])

        form = self.form(category='footwear', size='M', shoe_size='')
        self.assertTrue(form.is_footwear)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['shoe_size'], ['Wajib diisi untuk sepatu.'])

        form = self.form(category='footwear', size='M', shoe_size='39')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['size'], '')          # ukuran huruf dikosongkan untuk sepatu

        form = self.form(size='L', shoe_size='39')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['shoe_size'])        # ukuran sepatu dikosongkan untuk baju

    def test_shoe_size_range(self):
        for value, message in (('10', 'minimal 20'), ('60', 'maksimal 50'), ('abc', 'harus berupa angka')):
            with self.subTest(value=value):
                form = self.form(category='footwear', shoe_size=value)
                self.assertFalse(form.is_valid())
                self.assertIn(message, form.errors['shoe_size'][0])

    def test_photo_validation(self):
        big = png_upload()
        big.size = 6 * 1024 * 1024
        form = ClothingItemForm(item_data(), {'image': big})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['image'], ['Ukuran foto maksimal 5 MB.'])

        gif = io.BytesIO()
        Image.new('RGB', (4, 4)).save(gif, format='GIF')
        form = ClothingItemForm(item_data(), {'image': SimpleUploadedFile('a.gif', gif.getvalue(), content_type='image/gif')})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['image'], ['Format foto harus JPG atau PNG.'])

        fake = SimpleUploadedFile('virus.png', b'bukan gambar', content_type='image/png')
        form = ClothingItemForm(item_data(), {'image': fake})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_edit_without_new_photo_keeps_old_photo(self):
        item = self.make_item('Kemeja', image=png_upload())
        form = ClothingItemForm(item_data(name='Kemeja Baru'), {}, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().image.name, item.image.name)


class OutfitFormTests(WardrobeDataMixin, WardrobeTestCase):
    def test_choices_only_show_own_wardrobe(self):
        mine = self.make_item('Kemeja')
        listed = self.make_item('Hoodie', is_listed_for_swap=True)
        theirs = self.make_item('Punya Rico', user=self.other)
        choices = set(OutfitForm(user=self.user).fields['items'].queryset)
        self.assertEqual(choices, {mine})
        self.assertNotIn(listed, choices)
        self.assertNotIn(theirs, choices)

    def test_validation(self):
        items = [self.make_item(f'Kaos {i}') for i in range(6)]
        form = OutfitForm({'name': '', 'items': []}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['name'], ['Wajib diisi.'])
        self.assertEqual(form.errors['items'], ['Pilih minimal 1 pakaian.'])
        form = OutfitForm({'name': 'Banyak', 'items': [i.pk for i in items]}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['items'], ['Satu outfit maksimal 5 pakaian.'])
        form = OutfitForm({'name': 'Pas', 'items': [i.pk for i in items[:5]]}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_users_item_is_rejected(self):
        theirs = self.make_item('Punya Rico', user=self.other)
        form = OutfitForm({'name': 'Curang', 'items': [theirs.pk]}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('items', form.errors)

    def test_edit_keeps_items_that_moved_away_or_were_listed(self):
        kept = self.make_item('Hoodie')
        outfit = self.make_outfit(items=[kept])
        kept.is_listed_for_swap = True
        kept.save()
        swapped = self.make_item('Sudah ditukar', user=self.other)
        outfit.items.add(swapped)   # pakaian yang sudah berpindah pemilik lewat swap
        form = OutfitForm({'name': 'Kampus', 'items': [kept.pk, swapped.pk]}, instance=outfit, user=self.user)
        self.assertEqual(set(form.fields['items'].queryset), {kept, swapped})
        self.assertTrue(form.is_valid(), form.errors)
        new_theirs = self.make_item('Baru punya Rico', user=self.other)
        form = OutfitForm({'name': 'Kampus', 'items': [kept.pk]}, instance=outfit, user=self.user)
        form.fields['items'].queryset = ClothingItem.objects.all()   # paksa lolos pilihan, cek clean_items
        form.data = {'name': 'Kampus', 'items': [kept.pk, new_theirs.pk]}
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['items'], ['Pakaian baru harus berasal dari lemarimu sendiri.'])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class IndexViewTests(WardrobeDataMixin, WardrobeTestCase):
    def test_lists_only_own_wardrobe(self):
        self.make_item('Kemeja Saya')
        self.make_item('Hoodie Ditawarkan', is_listed_for_swap=True)
        self.make_item('Punya Rico', user=self.other)
        response = self.client.get(self.index)
        self.assertEqual([i.name for i in response.context['items']], ['Kemeja Saya'])
        self.assertEqual(response.context['total_for_swap'], 1)

    def test_search_category_sort_and_pagination(self):
        for name in ['Celana', 'Atasan B', 'Atasan A']:
            self.make_item(name, category='bottom' if name == 'Celana' else 'top', description='katun')
        response = self.client.get(self.index, {'q': 'katun', 'category': 'top', 'sort': 'name'})
        self.assertEqual([i.name for i in response.context['items']], ['Atasan A', 'Atasan B'])
        self.assertTrue(response.context['is_filtered'])
        response = self.client.get(self.index, {'sort': 'oldest', 'category': 'tidak-ada', 'limit': 'abc'})
        self.assertEqual(response.context['items'][0].name, 'Celana')
        self.assertEqual(response.context['sort'], 'oldest')
        response = self.client.get(self.index, {'sort': 'aneh'})
        self.assertEqual(response.context['sort'], 'newest')

    def test_load_more_limit(self):
        for i in range(15):
            self.make_item(f'Kaos {i}')
        response = self.client.get(self.index)
        self.assertEqual(len(response.context['items']), 12)
        self.assertTrue(response.context['has_more'])
        response = self.client.get(self.index, {'limit': 24})
        self.assertEqual(len(response.context['items']), 15)
        self.assertFalse(response.context['has_more'])

    def test_outfit_tab(self):
        item = self.make_item('Kemeja')
        self.make_outfit('Kampus', items=[item])
        response = self.client.get(self.index, {'tab': 'outfit'})
        outfit = response.context['outfits'][0]
        self.assertEqual((outfit.name, outfit.item_total), ('Kampus', 1))
        self.assertContains(response, 'Kampus')

    def test_auto_open_urls(self):
        item = self.make_item('Kemeja')
        outfit = self.make_outfit()
        cases = {
            'add=1': reverse('digital_wardrobe:item_create'),
            f'edit={item.pk}': reverse('digital_wardrobe:item_update', args=[item.pk]),
            'add_outfit=1': reverse('digital_wardrobe:outfit_create'),
            f'add_outfit=1&item={item.pk}': f"{reverse('digital_wardrobe:outfit_create')}?item={item.pk}",
            f'edit_outfit={outfit.pk}': reverse('digital_wardrobe:outfit_update', args=[outfit.pk]),
            'edit=99999': '',
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f'{self.index}?{query}').context['auto_open_url'], expected)

    def test_old_item_list_url_redirects(self):
        self.assertRedirects(self.client.get(reverse('digital_wardrobe:item_list')), self.index)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ItemViewTests(WardrobeDataMixin, WardrobeTestCase):
    def test_detail(self):
        item = self.make_item('Kemeja')
        self.make_outfit(items=[item])
        response = self.client.get(reverse('digital_wardrobe:item_detail', args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['outfit_count'], 1)

    def test_detail_of_archived_or_listed_item_redirects(self):
        archived = self.make_item('Dihapus', deleted_at=timezone.now())
        response = self.client.get(reverse('digital_wardrobe:item_detail', args=[archived.pk]))
        self.assertRedirects(response, self.index)
        listed = self.make_item('Ditawarkan', is_listed_for_swap=True)
        response = self.client.get(reverse('digital_wardrobe:item_detail', args=[listed.pk]))
        self.assertRedirects(response, self.index)
        response = self.client.get(reverse('digital_wardrobe:item_detail', args=[listed.pk]), **AJAX)
        self.assertEqual(response.status_code, 409)

    def test_create_with_ajax(self):
        url = reverse('digital_wardrobe:item_create')
        self.assertIn('modal_html', self.client.get(url, **AJAX).json())
        data = self.client.post(url, {**item_data(), 'image': png_upload()}, **AJAX).json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['total_items'], 1)
        self.assertIn('Kemeja Linen', data['card_html'])
        item = ClothingItem.objects.get()
        self.assertEqual(item.user, self.user)

    def test_create_invalid_with_ajax_returns_form_with_errors(self):
        response = self.client.post(reverse('digital_wardrobe:item_create'), item_data(name=''), **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Wajib diisi.', response.json()['modal_html'])
        self.assertFalse(ClothingItem.objects.exists())

    def test_create_without_ajax(self):
        url = reverse('digital_wardrobe:item_create')
        self.assertRedirects(self.client.get(url), f'{self.index}?add=1')
        self.assertRedirects(self.client.post(url, item_data(name='')), f'{self.index}?add=1')
        response = self.client.post(url, {**item_data(), 'image': png_upload()})
        self.assertRedirects(response, self.index)
        self.assertEqual(ClothingItem.objects.count(), 1)

    def test_update_with_ajax(self):
        item = self.make_item('Kemeja', image=png_upload())
        url = reverse('digital_wardrobe:item_update', args=[item.pk])
        self.assertIn('Kemeja', self.client.get(url, **AJAX).json()['modal_html'])
        data = self.client.post(url, item_data(name='Kemeja Baru'), **AJAX).json()
        self.assertEqual((data['ok'], data['pk']), (True, item.pk))
        item.refresh_from_db()
        self.assertEqual(item.name, 'Kemeja Baru')
        response = self.client.post(url, item_data(name=''), **AJAX)
        self.assertEqual(response.status_code, 400)

    def test_update_without_ajax(self):
        item = self.make_item('Kemeja', image=png_upload())
        url = reverse('digital_wardrobe:item_update', args=[item.pk])
        self.assertRedirects(self.client.get(url), f'{self.index}?edit={item.pk}')
        self.assertRedirects(self.client.post(url, item_data(name='')), f'{self.index}?edit={item.pk}')
        response = self.client.post(url, item_data(name='Kemeja Baru'))
        self.assertRedirects(response, reverse('digital_wardrobe:item_detail', args=[item.pk]))

    def test_update_blocked_when_listed_or_in_swap_request(self):
        listed = self.make_item('Hoodie', is_listed_for_swap=True)
        self.assertEqual(self.client.get(reverse('digital_wardrobe:item_update', args=[listed.pk]), **AJAX).status_code, 409)
        locked = self.make_item('Dress')
        self.lock_with_swap(locked)
        url = reverse('digital_wardrobe:item_update', args=[locked.pk])
        self.assertEqual(self.client.post(url, item_data(), **AJAX).status_code, 409)
        self.assertRedirects(self.client.post(url, item_data()), reverse('digital_wardrobe:item_detail', args=[locked.pk]))

    def test_delete_without_htmx(self):
        used = self.make_item('Kemeja')
        self.make_outfit(items=[used])
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[used.pk]), follow=True)
        self.assertContains(response, 'tetap tampil dengan status')
        listed = self.make_item('Hoodie', is_listed_for_swap=True)
        self.assertRedirects(self.client.post(reverse('digital_wardrobe:item_delete', args=[listed.pk])), self.index)
        locked = self.make_item('Dress')
        self.lock_with_swap(locked)
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[locked.pk]))
        self.assertRedirects(response, reverse('digital_wardrobe:item_detail', args=[locked.pk]))

    def test_delete_validation_error_from_model(self):
        item = self.make_item('Kemeja')
        url = reverse('digital_wardrobe:item_delete', args=[item.pk])
        with mock.patch.object(ClothingItem, 'remove_from_wardrobe', side_effect=ValidationError('Sedang diproses.')):
            response = self.client.post(url, HTTP_HX_REQUEST='true')
            self.assertEqual(json.loads(response['HX-Trigger'])['wardrobe:delete-failed']['message'], 'Sedang diproses.')
            response = self.client.post(url)
            self.assertRedirects(response, reverse('digital_wardrobe:item_detail', args=[item.pk]))


class OutfitViewTests(WardrobeDataMixin, WardrobeTestCase):
    def test_create_with_ajax(self):
        item = self.make_item('Kemeja')
        url = reverse('digital_wardrobe:outfit_create')
        modal = self.client.get(f'{url}?item={item.pk}', **AJAX).json()['modal_html']
        self.assertIn('Kemeja', modal)
        data = self.client.post(url, {'name': 'Kampus', 'items': [item.pk]}, **AJAX).json()
        self.assertTrue(data['ok'])
        self.assertEqual((data['kind'], data['total_outfits']), ('outfit', 1))
        self.assertEqual(list(Outfit.objects.get().items.all()), [item])
        response = self.client.post(url, {'name': '', 'items': []}, **AJAX)
        self.assertEqual(response.status_code, 400)

    def test_create_without_ajax(self):
        item = self.make_item('Kemeja')
        url = reverse('digital_wardrobe:outfit_create')
        self.assertRedirects(self.client.get(f'{url}?item={item.pk}'), f'{self.index}?tab=outfit&add_outfit=1&item={item.pk}')
        self.assertRedirects(self.client.post(url, {'name': ''}), f'{self.index}?tab=outfit&add_outfit=1')
        self.assertRedirects(self.client.post(url, {'name': 'Kampus', 'items': [item.pk]}), f'{self.index}?tab=outfit')

    def test_detail(self):
        item = self.make_item('Kemeja')
        outfit = self.make_outfit(items=[item])
        OutfitSchedule.objects.create(user=self.user, outfit=outfit, date=timezone.localdate() + timedelta(days=3))
        response = self.client.get(reverse('digital_wardrobe:outfit_detail', args=[outfit.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.context['upcoming_total'], response.context['history_total']), (1, 0))

    def test_update(self):
        first, second = self.make_item('Kemeja'), self.make_item('Celana')
        outfit = self.make_outfit(items=[first])
        url = reverse('digital_wardrobe:outfit_update', args=[outfit.pk])
        self.assertIn('modal_html', self.client.get(url, **AJAX).json())
        self.assertRedirects(self.client.get(url), f'{self.index}?tab=outfit&edit_outfit={outfit.pk}')
        data = self.client.post(url, {'name': 'Kampus 2', 'items': [first.pk, second.pk]}, **AJAX).json()
        self.assertEqual((data['ok'], data['pk']), (True, outfit.pk))
        self.assertEqual(outfit.items.count(), 2)
        self.assertEqual(self.client.post(url, {'name': '', 'items': []}, **AJAX).status_code, 400)
        self.assertRedirects(self.client.post(url, {'name': ''}), f'{self.index}?tab=outfit&edit_outfit={outfit.pk}')
        response = self.client.post(url, {'name': 'Kampus 3', 'items': [first.pk]})
        self.assertRedirects(response, reverse('digital_wardrobe:outfit_detail', args=[outfit.pk]))

    def test_delete_removes_upcoming_schedules_but_keeps_history(self):
        outfit = self.make_outfit(items=[self.make_item('Kemeja')])
        today = timezone.localdate()
        OutfitSchedule.objects.create(user=self.user, outfit=outfit, date=today + timedelta(days=2))
        past = OutfitSchedule.objects.create(user=self.user, outfit=outfit, date=today - timedelta(days=2))
        response = self.client.post(reverse('digital_wardrobe:outfit_delete', args=[outfit.pk]), follow=True)
        self.assertContains(response, '1 jadwal mendatang di Kalender Outfit ikut dihapus')
        self.assertFalse(Outfit.objects.filter(pk=outfit.pk).exists())
        self.assertTrue(OutfitSchedule.objects.filter(pk=past.pk).exists())
