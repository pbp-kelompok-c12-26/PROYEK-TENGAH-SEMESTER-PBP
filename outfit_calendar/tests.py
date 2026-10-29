"""
Unit test modul Kalender Outfit.

Jalankan:
    python manage.py test outfit_calendar

Cek coverage:
    coverage run --source=outfit_calendar manage.py test outfit_calendar
    coverage report -m
"""
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from digital_wardrobe.models import ClothingItem, Outfit

from .forms import OutfitScheduleForm
from .models import OutfitSchedule, ScheduledItem, recompute_last_worn
from .views import format_tanggal

TEMP_MEDIA = tempfile.mkdtemp()

# PNG 1x1 piksel, dipakai untuk test kolase foto di kalender
PNG_1PX = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
           b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82')

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
LAST_WEEK = TODAY - timedelta(days=7)
TOMORROW = TODAY + timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=7)


# MD5 hanya untuk test supaya login cepat (hasher asli sengaja lambat)
@override_settings(MEDIA_ROOT=TEMP_MEDIA, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CalendarTestCase(TestCase):
    """Data dasar yang dipakai semua test: 2 user, pakaian, dan outfit."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user('nefi', password='Password123!')
        self.other = User.objects.create_user('rico', password='Password123!')

        self.kaos = self.make_item('Kaos Putih')
        self.jeans = self.make_item('Jeans Hitam', category='bottom')
        self.sepatu = self.make_item('Sneakers', category='footwear', size='')
        self.outfit = self.make_outfit('Santai', [self.kaos, self.jeans])
        self.outfit2 = self.make_outfit('Gym', [self.sepatu])

        self.other_item = self.make_item('Jaket Rico', user=self.other)
        self.other_outfit = self.make_outfit('Outfit Rico', [self.other_item], user=self.other)

    # ---------- helper ----------
    def make_item(self, name, user=None, category='top', size='M', with_image=False):
        extra = {}
        if with_image:
            extra['image'] = SimpleUploadedFile(f'{name}.png', PNG_1PX, content_type='image/png')
        return ClothingItem.objects.create(
            user=user or self.user, name=name, category=category, size=size,
            color='neutral', condition='good', gender='unisex', **extra)

    def make_outfit(self, name, items, user=None):
        outfit = Outfit.objects.create(user=user or self.user, name=name)
        outfit.items.set(items)
        return outfit

    def make_schedule(self, outfit=None, day=TODAY, user=None, note=''):
        """Bikin jadwal persis seperti view schedule_create: simpan, snapshot, update last_worn."""
        schedule = OutfitSchedule.objects.create(
            user=user or self.user, outfit=outfit or self.outfit, date=day, note=note)
        schedule.save_snapshot()
        schedule.update_last_worn()
        return schedule

    def login(self):
        self.client.login(username='nefi', password='Password123!')

    def refresh(self, *objs):
        for obj in objs:
            obj.refresh_from_db()


# =====================================================================
# MODEL
# =====================================================================
class OutfitScheduleModelTests(CalendarTestCase):

    def test_save_copies_outfit_name(self):
        schedule = self.make_schedule()
        self.assertEqual(schedule.outfit_name, 'Santai')

    def test_save_updates_outfit_name_when_outfit_renamed(self):
        schedule = self.make_schedule()
        self.outfit.name = 'Santai Banget'
        self.outfit.save()
        schedule.save()
        self.assertEqual(schedule.outfit_name, 'Santai Banget')

    def test_display_name_uses_current_outfit_name(self):
        schedule = self.make_schedule()
        self.assertEqual(schedule.display_name, 'Santai')
        self.assertFalse(schedule.outfit_deleted)

    def test_outfit_deleted_keeps_history_with_saved_name(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.outfit.delete()
        schedule.refresh_from_db()
        self.assertIsNone(schedule.outfit)
        self.assertTrue(schedule.outfit_deleted)
        self.assertEqual(schedule.display_name, 'Santai')

    def test_display_name_fallback_when_no_saved_name(self):
        schedule = OutfitSchedule(user=self.user, outfit=None, outfit_name='', date=TODAY)
        self.assertEqual(schedule.display_name, 'Outfit sudah dihapus')

    def test_str(self):
        schedule = self.make_schedule()
        self.assertEqual(str(schedule), f'nefi - Santai ({TODAY})')

    def test_one_schedule_per_user_per_day(self):
        self.make_schedule(day=TODAY)
        with self.assertRaises(IntegrityError):
            OutfitSchedule.objects.create(user=self.user, outfit=self.outfit2, date=TODAY)

    def test_different_users_can_schedule_same_day(self):
        self.make_schedule(day=TODAY)
        self.make_schedule(outfit=self.other_outfit, day=TODAY, user=self.other)
        self.assertEqual(OutfitSchedule.objects.filter(date=TODAY).count(), 2)

    def test_ordering_by_date(self):
        later = self.make_schedule(day=NEXT_WEEK)
        earlier = self.make_schedule(outfit=self.outfit2, day=YESTERDAY)
        self.assertEqual(list(OutfitSchedule.objects.all()), [earlier, later])


class SnapshotTests(CalendarTestCase):

    def test_snapshot_records_every_item_in_outfit(self):
        schedule = self.make_schedule()
        names = sorted(schedule.worn_items.values_list('name', flat=True))
        self.assertEqual(names, ['Jeans Hitam', 'Kaos Putih'])

    def test_snapshot_replaces_old_entries(self):
        schedule = self.make_schedule()
        schedule.outfit = self.outfit2
        schedule.save()
        schedule.save_snapshot()
        self.assertEqual(list(schedule.worn_items.values_list('name', flat=True)), ['Sneakers'])

    def test_history_not_changed_when_outfit_edited_later(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.outfit.items.set([self.sepatu])  # outfit diedit setelah dijadwalkan
        names = sorted(schedule.worn_items.values_list('name', flat=True))
        self.assertEqual(names, ['Jeans Hitam', 'Kaos Putih'])

    def test_item_deleted_permanently_keeps_name(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.kaos.delete()
        entry = schedule.worn_items.get(name='Kaos Putih')
        self.assertIsNone(entry.clothing_item)
        self.assertTrue(entry.is_deleted)

    def test_scheduled_item_str_and_is_deleted(self):
        schedule = self.make_schedule()
        entry = schedule.worn_items.get(name='Kaos Putih')
        self.assertEqual(str(entry), 'Kaos Putih')
        self.assertFalse(entry.is_deleted)

    def test_deleting_schedule_deletes_snapshot(self):
        schedule = self.make_schedule()
        schedule.delete()
        self.assertEqual(ScheduledItem.objects.count(), 0)


class LastWornTests(CalendarTestCase):

    def test_past_schedule_sets_last_worn(self):
        self.make_schedule(day=LAST_WEEK)
        self.refresh(self.kaos, self.jeans)
        self.assertEqual(self.kaos.last_worn_date, LAST_WEEK)
        self.assertEqual(self.jeans.last_worn_date, LAST_WEEK)

    def test_today_counts_as_worn(self):
        self.make_schedule(day=TODAY)
        self.refresh(self.kaos)
        self.assertEqual(self.kaos.last_worn_date, TODAY)

    def test_future_schedule_does_not_set_last_worn(self):
        self.make_schedule(day=TOMORROW)
        self.refresh(self.kaos)
        self.assertIsNone(self.kaos.last_worn_date)

    def test_uses_latest_past_date(self):
        self.make_schedule(day=LAST_WEEK)
        self.make_schedule(day=YESTERDAY)
        self.make_schedule(day=NEXT_WEEK)  # masa depan diabaikan
        self.refresh(self.kaos)
        self.assertEqual(self.kaos.last_worn_date, YESTERDAY)

    def test_items_outside_outfit_untouched(self):
        self.make_schedule(day=YESTERDAY)
        self.refresh(self.sepatu)
        self.assertIsNone(self.sepatu.last_worn_date)

    def test_recompute_after_latest_schedule_removed(self):
        self.make_schedule(day=LAST_WEEK)
        latest = self.make_schedule(day=YESTERDAY)
        ids = list(latest.worn_items.values_list('clothing_item_id', flat=True))
        latest.delete()
        recompute_last_worn(ids)
        self.refresh(self.kaos)
        self.assertEqual(self.kaos.last_worn_date, LAST_WEEK)

    def test_recompute_to_none_when_no_schedule_left(self):
        schedule = self.make_schedule(day=YESTERDAY)
        ids = list(schedule.worn_items.values_list('clothing_item_id', flat=True))
        schedule.delete()
        recompute_last_worn(ids)
        self.refresh(self.kaos)
        self.assertIsNone(self.kaos.last_worn_date)

    def test_previous_owner_history_ignored_after_swap(self):
        self.make_schedule(day=YESTERDAY)
        self.kaos.user = self.other  # pakaian berpindah pemilik lewat swap
        self.kaos.save()
        recompute_last_worn([self.kaos.id])
        self.refresh(self.kaos)
        self.assertIsNone(self.kaos.last_worn_date)

    def test_recompute_ignores_empty_ids(self):
        recompute_last_worn([None])  # pakaian yang sudah dihapus -> id None
        recompute_last_worn([])



# =====================================================================
# FORM
# =====================================================================
class OutfitScheduleFormTests(CalendarTestCase):

    def form(self, data, instance=None):
        return OutfitScheduleForm(data, user=self.user, instance=instance)

    def test_valid_form(self):
        form = self.form({'date': TODAY, 'outfit': self.outfit.pk, 'note': 'Kuliah'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_note_is_optional(self):
        form = self.form({'date': TODAY, 'outfit': self.outfit.pk})
        self.assertTrue(form.is_valid(), form.errors)

    def test_date_required(self):
        form = self.form({'outfit': self.outfit.pk})
        self.assertIn('date', form.errors)

    def test_outfit_required(self):
        form = self.form({'date': TODAY})
        self.assertIn('outfit', form.errors)

    def test_outfit_choices_only_own_outfits(self):
        form = OutfitScheduleForm(user=self.user)
        choices = list(form.fields['outfit'].queryset)
        self.assertIn(self.outfit, choices)
        self.assertNotIn(self.other_outfit, choices)

    def test_outfit_choices_sorted_by_name(self):
        form = OutfitScheduleForm(user=self.user)
        self.assertEqual(list(form.fields['outfit'].queryset), [self.outfit2, self.outfit])  # Gym, Santai

    def test_cannot_pick_other_users_outfit(self):
        form = self.form({'date': TODAY, 'outfit': self.other_outfit.pk})
        self.assertFalse(form.is_valid())
        self.assertIn('outfit', form.errors)

    def test_duplicate_date_rejected_with_message(self):
        self.make_schedule(day=TODAY)
        form = self.form({'date': TODAY, 'outfit': self.outfit2.pk})
        self.assertFalse(form.is_valid())
        self.assertIn('sudah punya jadwal', form.errors['date'][0])

    def test_editing_same_schedule_keeps_its_date(self):
        schedule = self.make_schedule(day=TODAY)
        form = self.form({'date': TODAY, 'outfit': self.outfit2.pk}, instance=schedule)
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_users_schedule_does_not_block_date(self):
        self.make_schedule(outfit=self.other_outfit, day=TODAY, user=self.other)
        form = self.form({'date': TODAY, 'outfit': self.outfit.pk})
        self.assertTrue(form.is_valid(), form.errors)


# =====================================================================
# VIEW
# =====================================================================
class LoginRequiredTests(CalendarTestCase):

    def test_all_pages_redirect_to_login(self):
        schedule = self.make_schedule()
        login_url = reverse('accounts:login')
        urls = [
            ('get', reverse('outfit_calendar:index')),
            ('get', reverse('outfit_calendar:schedule_create')),
            ('get', reverse('outfit_calendar:schedule_detail', args=[schedule.pk])),
            ('get', reverse('outfit_calendar:schedule_update', args=[schedule.pk])),
            ('post', reverse('outfit_calendar:schedule_delete', args=[schedule.pk])),
        ]
        for method, url in urls:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(login_url))
        self.assertTrue(OutfitSchedule.objects.filter(pk=schedule.pk).exists())


class IndexViewTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.url = reverse('outfit_calendar:index')

    def test_shows_current_month_by_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'outfit_calendar/index.html')
        self.assertEqual(response.context['this_month'], f'{TODAY.year}-{TODAY.month:02d}')

    def test_month_param(self):
        response = self.client.get(self.url, {'month': '2026-03'})
        self.assertEqual(response.context['month_label'], 'Maret 2026')
        self.assertEqual(response.context['prev_month'], '2026-02')
        self.assertEqual(response.context['next_month'], '2026-04')

    def test_january_and_december_wrap_year(self):
        jan = self.client.get(self.url, {'month': '2026-01'})
        self.assertEqual(jan.context['prev_month'], '2025-12')
        dec = self.client.get(self.url, {'month': '2026-12'})
        self.assertEqual(dec.context['next_month'], '2027-01')

    def test_invalid_month_falls_back_to_today(self):
        for bad in ['abc', '2026-13', '2026', '']:
            with self.subTest(month=bad):
                response = self.client.get(self.url, {'month': bad})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['month_label'].split()[-1], str(TODAY.year))

    def test_grid_marks_today_and_schedule(self):
        schedule = self.make_schedule(day=TODAY)
        response = self.client.get(self.url)
        days = [d for week in response.context['weeks'] for d in week]
        today_cell = next(d for d in days if d['date'] == TODAY)
        self.assertTrue(today_cell['is_today'])
        self.assertTrue(today_cell['in_month'])
        self.assertEqual(today_cell['schedule'], schedule)
        self.assertContains(response, 'Santai')

    def test_only_own_schedules_shown(self):
        self.make_schedule(outfit=self.other_outfit, day=TODAY, user=self.other)
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Outfit Rico')

    def test_collage_max_four_photos_with_image_only(self):
        items = [self.make_item(f'Foto {i}', with_image=True) for i in range(5)]
        items.append(self.make_item('Tanpa Foto'))
        outfit = self.make_outfit('Ramai', items)
        self.make_schedule(outfit=outfit, day=TODAY)
        response = self.client.get(self.url)
        cell = next(d for week in response.context['weeks'] for d in week if d['date'] == TODAY)
        thumbs = cell['schedule'].thumbs
        self.assertEqual(len(thumbs), 4)
        self.assertTrue(all(item.image for item in thumbs))

    def test_upcoming_only_today_and_future_max_five(self):
        self.make_schedule(day=YESTERDAY)
        for i in range(6):
            self.make_schedule(outfit=self.outfit2, day=TODAY + timedelta(days=i))
        upcoming = self.client.get(self.url).context['upcoming']
        self.assertEqual(len(upcoming), 5)
        self.assertTrue(all(s.date >= TODAY for s in upcoming))
        self.assertEqual(upcoming[0].tanggal, format_tanggal(TODAY, with_day=True))

    def test_no_outfit_message(self):
        Outfit.objects.filter(user=self.user).delete()
        response = self.client.get(self.url)
        self.assertFalse(response.context['has_outfits'])
        self.assertContains(response, 'Kamu belum punya outfit')


class CreateViewTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.url = reverse('outfit_calendar:schedule_create')

    def test_get_form_with_initial_from_query(self):
        response = self.client.get(self.url, {'date': '2026-11-02', 'outfit': self.outfit.pk})
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial['date'], '2026-11-02')
        self.assertEqual(str(form.initial['outfit']), str(self.outfit.pk))

    def test_post_creates_schedule_snapshot_and_last_worn(self):
        response = self.client.post(self.url, {'date': YESTERDAY, 'outfit': self.outfit.pk, 'note': 'Kuliah'})
        schedule = OutfitSchedule.objects.get(user=self.user, date=YESTERDAY)
        self.assertRedirects(
            response, f"{reverse('outfit_calendar:index')}?month={YESTERDAY.year}-{YESTERDAY.month:02d}",
            fetch_redirect_response=False)
        self.assertEqual(schedule.note, 'Kuliah')
        self.assertEqual(schedule.worn_items.count(), 2)
        self.refresh(self.kaos)
        self.assertEqual(self.kaos.last_worn_date, YESTERDAY)

        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('dijadwalkan' in m for m in messages))

    def test_post_future_does_not_change_last_worn(self):
        self.client.post(self.url, {'date': NEXT_WEEK, 'outfit': self.outfit.pk})
        self.refresh(self.kaos)
        self.assertIsNone(self.kaos.last_worn_date)

    def test_invalid_post_shows_errors(self):
        response = self.client.post(self.url, {'date': '', 'outfit': self.outfit.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(OutfitSchedule.objects.count(), 0)

    def test_cannot_schedule_other_users_outfit(self):
        response = self.client.post(self.url, {'date': TODAY, 'outfit': self.other_outfit.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OutfitSchedule.objects.exists())

    def test_cannot_schedule_twice_same_day(self):
        self.make_schedule(day=TODAY)
        response = self.client.post(self.url, {'date': TODAY, 'outfit': self.outfit2.pk})
        self.assertContains(response, 'sudah punya jadwal')
        self.assertEqual(OutfitSchedule.objects.count(), 1)


class DetailViewTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        self.login()

    def url(self, schedule):
        return reverse('outfit_calendar:schedule_detail', args=[schedule.pk])

    def test_shows_schedule_and_items(self):
        schedule = self.make_schedule(day=TODAY, note='Kuliah pagi')
        response = self.client.get(self.url(schedule))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kaos Putih')
        self.assertContains(response, 'Jeans Hitam')
        self.assertContains(response, 'Kuliah pagi')
        self.assertEqual(response.context['tanggal'], format_tanggal(TODAY, with_day=True))

    def test_other_users_schedule_404(self):
        schedule = self.make_schedule(outfit=self.other_outfit, user=self.other)
        response = self.client.get(self.url(schedule))
        self.assertEqual(response.status_code, 404)

    def test_deleted_item_label(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.kaos.delete()
        response = self.client.get(self.url(schedule))
        self.assertContains(response, 'Sudah dihapus dari lemari')

    def test_swapped_item_label(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.kaos.user = self.other
        self.kaos.save()
        response = self.client.get(self.url(schedule))
        self.assertContains(response, 'Pakaian tidak tersedia')

    def test_deleted_outfit_label(self):
        schedule = self.make_schedule(day=LAST_WEEK)
        self.outfit.delete()
        response = self.client.get(self.url(schedule))
        self.assertContains(response, 'Outfit sudah dihapus')


class UpdateViewTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.schedule = self.make_schedule(day=YESTERDAY)
        self.url = reverse('outfit_calendar:schedule_update', args=[self.schedule.pk])

    def test_get_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['schedule'], self.schedule)

    def test_change_outfit_updates_snapshot_and_last_worn(self):
        response = self.client.post(self.url, {'date': YESTERDAY, 'outfit': self.outfit2.pk})
        self.assertRedirects(response, reverse('outfit_calendar:schedule_detail', args=[self.schedule.pk]),
                             fetch_redirect_response=False)
        self.schedule.refresh_from_db()
        self.assertEqual(list(self.schedule.worn_items.values_list('name', flat=True)), ['Sneakers'])
        self.refresh(self.kaos, self.sepatu)
        self.assertIsNone(self.kaos.last_worn_date)        # outfit lama tidak lagi dipakai hari itu
        self.assertEqual(self.sepatu.last_worn_date, YESTERDAY)

    def test_move_to_future_clears_last_worn(self):
        self.client.post(self.url, {'date': NEXT_WEEK, 'outfit': self.outfit.pk})
        self.refresh(self.kaos)
        self.assertIsNone(self.kaos.last_worn_date)

    def test_invalid_post_keeps_data(self):
        response = self.client.post(self.url, {'date': '', 'outfit': self.outfit2.pk})
        self.assertEqual(response.status_code, 200)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.outfit, self.outfit)

    def test_other_users_schedule_404(self):
        other = self.make_schedule(outfit=self.other_outfit, user=self.other)
        url = reverse('outfit_calendar:schedule_update', args=[other.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'date': TODAY, 'outfit': self.outfit.pk}).status_code, 404)


class DeleteViewTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        self.login()

    def url(self, schedule):
        return reverse('outfit_calendar:schedule_delete', args=[schedule.pk])

    def test_delete_and_recompute_last_worn(self):
        self.make_schedule(day=LAST_WEEK)
        latest = self.make_schedule(outfit=self.outfit, day=YESTERDAY)
        response = self.client.post(self.url(latest))
        self.assertRedirects(
            response, f"{reverse('outfit_calendar:index')}?month={YESTERDAY.year}-{YESTERDAY.month:02d}",
            fetch_redirect_response=False)
        self.assertFalse(OutfitSchedule.objects.filter(pk=latest.pk).exists())
        self.refresh(self.kaos)
        self.assertEqual(self.kaos.last_worn_date, LAST_WEEK)

    def test_get_not_allowed(self):
        schedule = self.make_schedule()
        response = self.client.get(self.url(schedule))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(OutfitSchedule.objects.filter(pk=schedule.pk).exists())

    def test_other_users_schedule_404(self):
        other = self.make_schedule(outfit=self.other_outfit, user=self.other)
        response = self.client.post(self.url(other))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(OutfitSchedule.objects.filter(pk=other.pk).exists())


class FormatTanggalTests(TestCase):

    def test_format(self):
        self.assertEqual(format_tanggal(date(2026, 10, 29)), '29 Oktober 2026')
        self.assertEqual(format_tanggal(date(2026, 10, 29), with_day=True), 'Kamis, 29 Oktober 2026')