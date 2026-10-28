import json
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from swap_requests.models import SwapRequest

from .models import ClothingItem, Outfit
from .views import BULK_DELETE_LIMIT

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
TEMP_MEDIA = tempfile.mkdtemp()

# PNG 1x1 piksel untuk test foto
PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
           b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BulkDeleteTests(TestCase):
    """Hapus banyak pakaian sekaligus (views.item_bulk_delete + ClothingItem.objects.remove_many)."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
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
        response = self.post([item.pk])
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


class HtmxInteractionTests(TestCase):
    """Filter / pindah tab / hapus tanpa reload lewat HTMX (views.index, item_delete, outfit_delete)."""

    def setUp(self):
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

    def test_htmx_delete_other_users_item_is_404(self):
        item = self.make_item('Blazer Rico', user=self.other)
        response = self.client.post(reverse('digital_wardrobe:item_delete', args=[item.pk]), **self.hx(f'item-{item.pk}'))
        self.assertEqual(response.status_code, 404)
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
