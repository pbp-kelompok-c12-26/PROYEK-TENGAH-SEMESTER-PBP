from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap

from .context_processors import swap_request_unread_count
from .forms import ConfirmForm, SwapRequestForm, offerable_items
from .models import SwapRequest, SwapRequestNotification
from .views import _delete_swap_for_party


class SwapDataMixin:
    """Shared isolated users, wardrobe items and public listings for tests."""

    @classmethod
    def setUpTestData(cls):
        cls.requester = User.objects.create_user('requester', password='pass12345')
        cls.owner = User.objects.create_user('owner', password='pass12345')
        cls.outsider = User.objects.create_user('outsider', password='pass12345')
        cls.requester_profile = UserProfile.for_user(cls.requester)
        cls.owner_profile = UserProfile.for_user(cls.owner)
        cls.outsider_profile = UserProfile.for_user(cls.outsider)

    def make_item(self, name, user=None, **values):
        defaults = {
            'category': 'top', 'size': 'M', 'gender': 'unisex',
            'condition': 'good', 'color': 'neutral', 'description': '',
            'is_listed_for_swap': False,
        }
        defaults.update(values)
        return ClothingItem.objects.create(user=user or self.owner, name=name, **defaults)

    def make_listing(self, item=None, user=None, status=ItemForSwap.AVAILABLE, **values):
        item = item or self.make_item('Requested garment', user=user or self.owner)
        defaults = {'meeting_location': 'Depok', 'status': status}
        defaults.update(values)
        listing = ItemForSwap.objects.create(
            clothing_item=item, user=user or item.user, **defaults,
        )
        return listing

    def make_swap(self, *, requested_item=None, offered_item=None, requester=None,
                  owner=None, status=SwapRequest.PENDING, **values):
        requester = requester or self.requester
        owner = owner or self.owner
        defaults = {
            'requested_item_name': requested_item.name if requested_item else 'Old requested garment',
            'offered_item_name': offered_item.name if offered_item else 'Old offered garment',
            'message': '', 'status': status,
        }
        defaults.update(values)
        return SwapRequest.objects.create(
            requester=requester, owner=owner, requested_item=requested_item,
            offered_item=offered_item, **defaults,
        )

    def login(self, user=None):
        self.client.force_login(user or self.requester)


class SwapRequestModelTests(SwapDataMixin, TestCase):
    def test_defaults_choices_code_string_and_display_helpers(self):
        requested = self.make_item('Cardigan')
        offered = self.make_item('Kemeja', user=self.requester)
        swap = self.make_swap(requested_item=requested, offered_item=offered)

        self.assertEqual(swap.status, SwapRequest.PENDING)
        self.assertEqual(swap.requester_confirmation, '')
        self.assertEqual(swap.owner_confirmation, '')
        self.assertFalse(swap.requester_hidden)
        self.assertFalse(swap.owner_hidden)
        self.assertEqual(swap.code, f'SR-{swap.pk:04d}')
        self.assertEqual(str(swap), f'SR-{swap.pk:04d}: Kemeja ⇄ Cardigan')
        self.assertEqual(swap.status_style, 'sr-status--pending')
        self.assertIn('Menunggu', swap.status_note)
        self.assertEqual(dict(SwapRequest.STATUS_CHOICES)[SwapRequest.PENDING], 'Pending')
        self.assertEqual(dict(SwapRequest.CONFIRM_CHOICES)[SwapRequest.DONE], 'Selesai swap')
        self.assertEqual(SwapRequest._meta.ordering, ['-created_at'])
        self.assertEqual(swap.notifications.count(), 1)
        self.assertEqual(swap.notifications.get().recipient, self.owner)

    def test_status_helpers_and_party_permissions(self):
        swap = self.make_swap()
        self.assertEqual(swap.role_of(self.requester), 'requester')
        self.assertEqual(swap.role_of(self.owner), 'owner')
        self.assertIsNone(swap.role_of(self.outsider))
        self.assertEqual(swap.other_party(self.requester), self.owner)
        self.assertEqual(swap.other_party(self.owner), self.requester)
        self.assertTrue(swap.can_delete)
        self.assertTrue(swap.can_edit(self.requester))
        self.assertFalse(swap.can_edit(self.owner))
        self.assertTrue(swap.can_respond(self.owner))
        self.assertFalse(swap.can_respond(self.requester))
        self.assertFalse(swap.status_style == '')

        swap.status = 'unrecognized'
        self.assertEqual(swap.status_style, '')
        self.assertEqual(swap.status_note, '')

    def test_involving_and_active_request_queryset_helpers(self):
        first = self.make_item('Requested')
        second = self.make_item('Offered', user=self.requester)
        third = self.make_item('Other')
        pending = self.make_swap(requested_item=first, offered_item=second)
        awaiting = self.make_swap(
            requested_item=third, offered_item=first, status=SwapRequest.AWAITING,
        )
        completed = self.make_swap(
            requested_item=third, offered_item=second, status=SwapRequest.COMPLETED,
        )

        related = SwapRequest.objects.involving_item(first)
        self.assertCountEqual(related, [pending, awaiting])
        self.assertTrue(SwapRequest.objects.is_locked(first))
        self.assertTrue(SwapRequest.objects.has_active_request(first))
        self.assertFalse(SwapRequest.objects.is_locked(second))
        self.assertTrue(SwapRequest.objects.has_active_request(second))
        self.assertTrue(SwapRequest.objects.has_active_request(third))
        self.assertNotIn(completed, related)

    def test_visibility_and_notification_seen_scoping(self):
        swap = self.make_swap()
        requester_notice = SwapRequestNotification.objects.create(
            swap_request=swap, recipient=self.requester, status=SwapRequest.PENDING,
        )
        owner_notice = swap.notifications.get(recipient=self.owner)
        outsider_notice = SwapRequestNotification.objects.create(
            swap_request=swap, recipient=self.outsider, status=SwapRequest.PENDING,
        )
        self.assertIn(swap, SwapRequest.objects.visible_to(self.requester))
        self.assertIn(swap, SwapRequest.objects.visible_to(self.owner))
        self.assertNotIn(swap, SwapRequest.objects.visible_to(self.outsider))

        self.assertEqual(SwapRequest.objects.filter(pk=swap.pk).mark_seen_by(self.requester), 1)
        requester_notice.refresh_from_db()
        owner_notice.refresh_from_db()
        outsider_notice.refresh_from_db()
        self.assertIsNotNone(requester_notice.read_at)
        self.assertIsNone(owner_notice.read_at)
        self.assertIsNone(outsider_notice.read_at)
        swap.mark_seen_by(self.owner)
        owner_notice.refresh_from_db()
        self.assertIsNotNone(owner_notice.read_at)

        swap.owner_hidden = True
        swap.save(update_fields=['owner_hidden'])
        owner_notice.read_at = None
        owner_notice.save(update_fields=['read_at'])
        SwapRequest.objects.filter(pk=swap.pk).mark_seen_by(self.owner)
        owner_notice.refresh_from_db()
        self.assertIsNone(owner_notice.read_at)

    def test_mark_listing_returned_sets_only_matching_cycle_after_posting(self):
        item = self.make_item('Listed cardigan')
        listing = self.make_listing(item)
        after_listing = self.make_swap(requested_item=item, requested_listing_cycle_key='')
        before_listing = self.make_swap(requested_item=item)
        SwapRequest.objects.filter(pk=before_listing.pk).update(
            created_at=listing.posted_at - timedelta(seconds=1),
        )
        other_cycle = self.make_swap(
            requested_item=item, requested_listing_cycle_key='999:another-cycle',
        )

        changed = SwapRequest.objects.mark_listing_returned(listing)
        after_listing.refresh_from_db()
        before_listing.refresh_from_db()
        other_cycle.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual(after_listing.requested_listing_cycle_key, listing.cycle_key)
        self.assertTrue(after_listing.requested_listing_returned_to_wardrobe)
        self.assertFalse(before_listing.requested_listing_returned_to_wardrobe)
        self.assertFalse(other_cycle.requested_listing_returned_to_wardrobe)

    def test_sync_availability_rejects_requests_with_missing_or_unavailable_items(self):
        not_listed = self.make_item('Not listed')
        deleted_requested = self.make_item('Deleted requested', is_listed_for_swap=True)
        deleted_requested.deleted_at = timezone.now()
        deleted_requested.save(update_fields=['deleted_at'])
        listed = self.make_item('Listed', is_listed_for_swap=True)
        ordinary = self.make_item('Ordinary offered', user=self.requester)
        deleted_offered = self.make_item('Deleted offered', user=self.requester)
        deleted_offered.deleted_at = timezone.now()
        deleted_offered.save(update_fields=['deleted_at'])

        missing_requested = self.make_swap(requested_item=None, offered_item=ordinary)
        missing_offered = self.make_swap(requested_item=listed, offered_item=None)
        unavailable_requested = self.make_swap(requested_item=not_listed, offered_item=ordinary)
        deleted_request = self.make_swap(requested_item=deleted_requested, offered_item=ordinary)
        deleted_offer = self.make_swap(requested_item=listed, offered_item=deleted_offered)
        healthy = self.make_swap(requested_item=listed, offered_item=ordinary)

        changed = SwapRequest.objects.sync_availability()
        self.assertEqual(changed, 5)
        for swap in (missing_requested, missing_offered, unavailable_requested, deleted_request, deleted_offer):
            swap.refresh_from_db()
            self.assertEqual(swap.status, SwapRequest.REJECTED)
            self.assertIsNotNone(swap.responded_at)
            self.assertEqual(swap.notifications.filter(status=SwapRequest.REJECTED).count(), 2)
        healthy.refresh_from_db()
        self.assertEqual(healthy.status, SwapRequest.PENDING)

    def test_save_status_change_notifications_and_actor_exclusion(self):
        swap = self.make_swap()
        self.assertEqual(swap.notifications.count(), 1)
        swap.status = SwapRequest.AWAITING
        swap.record_status_change(actor=self.owner)
        swap.save(update_fields=['status', 'updated_at'])
        self.assertSetEqual(
            set(swap.notifications.values_list('recipient_id', 'status')),
            {(self.owner.pk, SwapRequest.PENDING), (self.requester.pk, SwapRequest.AWAITING)},
        )

        swap.status = SwapRequest.REJECTED
        swap.record_status_change()
        swap.save(update_fields=['status', 'updated_at'])
        self.assertEqual(swap.notifications.filter(status=SwapRequest.REJECTED).count(), 2)

    def test_accept_reject_and_conflicting_awaiting_request(self):
        requested = self.make_item('Requested', is_listed_for_swap=True)
        offered = self.make_item('Offered', user=self.requester)
        swap = self.make_swap(requested_item=requested, offered_item=offered)
        swap.accept()
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)
        self.assertIsNotNone(swap.responded_at)
        self.assertEqual(swap.notifications.filter(status=SwapRequest.AWAITING).count(), 1)

        other_item = self.make_item('Other offered', user=self.outsider)
        conflict = self.make_swap(
            requested_item=other_item, offered_item=requested, requester=self.outsider,
        )
        with self.assertRaises(ValidationError):
            conflict.accept()
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SwapRequest.PENDING)

        conflict.reject(actor=self.owner)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SwapRequest.REJECTED)
        self.assertIsNotNone(conflict.responded_at)
        self.assertEqual(conflict.notifications.filter(status=SwapRequest.REJECTED).count(), 1)

    def test_confirm_done_waits_then_completes_transfer_and_rejects_competing_pending(self):
        requested = self.make_item('Requested', user=self.owner, is_listed_for_swap=True)
        offered = self.make_item('Offered', user=self.requester, is_listed_for_swap=True)
        requested_listing = self.make_listing(requested, user=self.owner)
        offered_listing = self.make_listing(offered, user=self.requester)
        swap = self.make_swap(
            requested_item=requested, offered_item=offered, status=SwapRequest.AWAITING,
        )
        competing = self.make_swap(
            requested_item=requested,
            offered_item=self.make_item('Another offer', user=self.outsider),
            requester=self.outsider,
        )

        swap.confirm(self.requester, SwapRequest.DONE)
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)
        self.assertEqual(swap.requester_confirmation, SwapRequest.DONE)

        swap.confirm(self.owner, SwapRequest.DONE)
        swap.refresh_from_db()
        requested.refresh_from_db()
        offered.refresh_from_db()
        requested_listing.refresh_from_db()
        offered_listing.refresh_from_db()
        competing.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.COMPLETED)
        self.assertIsNotNone(swap.completed_at)
        self.assertEqual(requested.user, self.requester)
        self.assertEqual(offered.user, self.owner)
        self.assertFalse(requested.is_listed_for_swap)
        self.assertFalse(offered.is_listed_for_swap)
        self.assertEqual(requested_listing.status, ItemForSwap.SWAPPED)
        self.assertEqual(offered_listing.status, ItemForSwap.SWAPPED)
        self.assertEqual(competing.status, SwapRequest.REJECTED)

    def test_confirm_cancel_rejects_and_complete_handles_deleted_item_reference(self):
        swap = self.make_swap(status=SwapRequest.AWAITING)
        swap.confirm(self.owner, SwapRequest.CANCEL)
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.REJECTED)
        self.assertEqual(swap.owner_confirmation, SwapRequest.CANCEL)

        deleted_ref = self.make_swap(status=SwapRequest.AWAITING)
        deleted_ref.requested_item = None
        deleted_ref.offered_item = None
        deleted_ref.save(update_fields=['requested_item', 'offered_item'])
        deleted_ref.complete(actor=self.requester)
        deleted_ref.refresh_from_db()
        self.assertEqual(deleted_ref.status, SwapRequest.COMPLETED)
        self.assertIsNotNone(deleted_ref.completed_at)

    def test_returned_listing_and_notification_model_string(self):
        item = self.make_item('Returned jacket')
        listing = self.make_listing(item)
        swap = self.make_swap(requested_item=item, requested_listing_cycle_key=listing.cycle_key)
        SwapRequest.objects.mark_listing_returned(listing)
        swap.refresh_from_db()
        self.assertTrue(swap.requested_listing_returned_to_wardrobe)
        notice = swap.notifications.get()
        self.assertEqual(str(notice), f'{swap.code}: {notice.status} → {self.owner}')


class SwapRequestFormTests(SwapDataMixin, TestCase):
    def setUp(self):
        self.requested = self.make_item('Requested', user=self.owner, is_listed_for_swap=True)
        self.listing = self.make_listing(self.requested)
        self.offered = self.make_item('Offered', user=self.requester)

    def form_data(self, **values):
        return {'offered_item': self.offered.pk, 'message': '', **values}

    def test_offerable_items_excludes_items_in_active_requests_and_orders_names(self):
        second = self.make_item('A offered', user=self.requester)
        self.make_swap(requested_item=self.make_item('Other requested'), offered_item=second)
        self.make_swap(
            requested_item=self.make_item('Another requested'), offered_item=self.offered,
            status=SwapRequest.AWAITING,
        )
        offered = list(offerable_items(self.requester))
        self.assertEqual(offered, [])

        available_a = self.make_item('A cardigan', user=self.requester)
        available_b = self.make_item('B jeans', user=self.requester)
        self.assertEqual(
            list(offerable_items(self.requester).values_list('name', flat=True)),
            [available_a.name, available_b.name],
        )

    def test_form_accepts_valid_offer_and_save_populates_request_snapshot(self):
        form = SwapRequestForm(
            self.form_data(message='Semoga cocok!'), user=self.requester,
            requested_item=self.requested,
        )
        self.assertTrue(form.is_valid(), form.errors)
        swap = form.save(commit=False)
        self.assertIsNone(swap.pk)
        self.assertEqual(swap.requester, self.requester)
        self.assertEqual(swap.owner, self.owner)
        self.assertEqual(swap.requested_item, self.requested)
        self.assertEqual(swap.requested_item_name, 'Requested')
        self.assertEqual(swap.offered_item_name, 'Offered')
        saved = form.save()
        self.assertIsNotNone(saved.pk)
        self.assertEqual(saved.message, 'Semoga cocok!')

    def test_form_requires_an_offer_and_valid_requested_listing(self):
        missing_offer = SwapRequestForm(
            {'message': ''}, user=self.requester, requested_item=self.requested,
        )
        self.assertFalse(missing_offer.is_valid())
        self.assertIn('offered_item', missing_offer.errors)

        no_requested_item = SwapRequestForm(
            self.form_data(), user=self.requester, requested_item=None,
        )
        self.assertFalse(no_requested_item.is_valid())
        self.assertTrue(no_requested_item.non_field_errors())

        self.listing.delete()
        missing_listing = SwapRequestForm(
            self.form_data(), user=self.requester, requested_item=self.requested,
        )
        self.assertFalse(missing_listing.is_valid())
        self.assertTrue(missing_listing.non_field_errors())

    def test_form_rejects_own_item_unlisted_item_and_duplicate_pending_request(self):
        own = self.make_item('Own listed', user=self.requester, is_listed_for_swap=True)
        self.make_listing(own, user=self.requester)
        own_form = SwapRequestForm(
            self.form_data(), user=self.requester, requested_item=own,
        )
        self.assertFalse(own_form.is_valid())
        self.assertIn('Kamu tidak bisa', str(own_form.non_field_errors()))

        self.requested.is_listed_for_swap = False
        self.requested.save(update_fields=['is_listed_for_swap'])
        unavailable_form = SwapRequestForm(
            self.form_data(), user=self.requester, requested_item=self.requested,
        )
        self.assertFalse(unavailable_form.is_valid())
        self.assertIn('sudah tidak tersedia', str(unavailable_form.non_field_errors()))
        self.requested.is_listed_for_swap = True
        self.requested.save(update_fields=['is_listed_for_swap'])

        self.make_swap(requested_item=self.requested, offered_item=self.offered)
        # Simulate a selectable item while testing the duplicate safeguard itself;
        # normally offerable_items already excludes garments in active requests.
        with patch('swap_requests.forms.offerable_items', return_value=ClothingItem.objects.in_wardrobe(self.requester)):
            duplicate = SwapRequestForm(
                self.form_data(), user=self.requester, requested_item=self.requested,
            )
            self.assertFalse(duplicate.is_valid())
        self.assertIn('request yang sama', str(duplicate.non_field_errors()))

    def test_edit_form_keeps_current_offer_available_and_does_not_apply_create_duplicate_rule(self):
        swap = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        replacement = self.make_item('Replacement', user=self.requester)
        form = SwapRequestForm(
            self.form_data(offered_item=replacement.pk), instance=swap,
            user=self.requester, requested_item=self.requested,
        )
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.offered_item, replacement)
        self.assertEqual(updated.offered_item_name, 'Replacement')

        blocked = self.make_item('Already offered', user=self.requester)
        self.make_swap(
            requested_item=self.make_item('Other'), offered_item=blocked,
            status=SwapRequest.AWAITING,
        )
        self.assertNotIn(blocked, form.fields['offered_item'].queryset)


class ConfirmFormTests(TestCase):
    def test_only_declared_confirmation_values_are_valid(self):
        self.assertTrue(ConfirmForm({'choice': SwapRequest.DONE}).is_valid())
        self.assertTrue(ConfirmForm({'choice': SwapRequest.CANCEL}).is_valid())
        self.assertFalse(ConfirmForm({'choice': 'later'}).is_valid())
        self.assertFalse(ConfirmForm({}).is_valid())


class SwapRequestViewTests(SwapDataMixin, TestCase):
    def setUp(self):
        self.requested = self.make_item('Cardigan sage', user=self.owner, is_listed_for_swap=True)
        self.listing = self.make_listing(self.requested)
        self.offered = self.make_item('Kemeja linen', user=self.requester)

    def test_login_required_routes_redirect_to_login(self):
        protected = [
            reverse('swap_requests:index'),
            reverse('swap_requests:create'),
            reverse('swap_requests:item_requests', args=[self.requested.pk]),
            reverse('swap_requests:detail', args=[1]),
            reverse('swap_requests:sent', args=[1]),
            reverse('swap_requests:update', args=[1]),
        ]
        for url in protected:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('accounts:login'), response['Location'])

    def test_index_defaults_filters_groups_cycles_and_renders_htmx_partial(self):
        first = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
            requested_listing_cycle_key=self.listing.cycle_key,
        )
        second = self.make_swap(
            requested_item=self.requested,
            offered_item=self.make_item('Shoes', user=self.outsider),
            requester=self.outsider,
            status=SwapRequest.AWAITING,
            requested_listing_cycle_key=self.listing.cycle_key,
        )
        legacy = self.make_swap(
            requested_item=self.make_item('Old cardigan', user=self.owner),
            offered_item=self.make_item('Old offer', user=self.outsider),
            requester=self.outsider,
        )
        legacy.requested_item.is_listed_for_swap = True
        legacy.requested_item.save(update_fields=['is_listed_for_swap'])
        completed = self.make_swap(
            requested_item=self.requested,
            offered_item=self.make_item('Completed offer', user=self.outsider),
            requester=self.outsider, status=SwapRequest.COMPLETED,
            requested_listing_cycle_key=self.listing.cycle_key,
        )
        self.login(self.owner)

        response = self.client.get(reverse('swap_requests:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'swap_requests/index.html')
        self.assertEqual(len(response.context['groups']), 2)
        main_group = next(g for g in response.context['groups'] if g['name'] == 'Cardigan sage')
        self.assertEqual(main_group['total'], 3)
        self.assertEqual(main_group['top_status'], SwapRequest.COMPLETED)
        self.assertIn('1 pending', main_group['summary'])
        self.assertEqual(response.context['request_summary_rows'][0]['total'], 3)

        filtered = self.client.get(reverse('swap_requests:index'), {'status': 'pending'})
        self.assertEqual(filtered.context['status'], SwapRequest.PENDING)
        self.assertEqual([g['total'] for g in filtered.context['groups']], [1, 1])
        invalid = self.client.get(reverse('swap_requests:index'), {'status': 'invalid', 'tab': 'unexpected'})
        self.assertEqual(invalid.context['tab'], 'masuk')
        self.assertEqual(invalid.context['status'], '')

        htmx = self.client.get(reverse('swap_requests:index'), {'tab': 'not-valid'}, HTTP_HX_REQUEST='true')
        self.assertTemplateUsed(htmx, 'swap_requests/partials/index_content.html')
        self.assertEqual(htmx.status_code, 200)

        sent_tab = self.client.get(reverse('swap_requests:index'), {'tab': 'kamu'})
        self.assertEqual(sent_tab.context['tab'], 'kamu')
        self.assertEqual(sent_tab.context['outgoing'], [])
        self.assertEqual(first.status, SwapRequest.PENDING)
        self.assertEqual(second.status, SwapRequest.AWAITING)
        self.assertEqual(completed.status, SwapRequest.COMPLETED)

    def test_index_outgoing_summary_excludes_hidden_and_only_counts_active(self):
        pending = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        awaiting = self.make_swap(
            requested_item=self.make_item('Other', is_listed_for_swap=True), offered_item=self.make_item('Another', user=self.requester),
            status=SwapRequest.AWAITING,
        )
        completed = self.make_swap(
            requested_item=self.make_item('Done'), offered_item=self.make_item('Done offer', user=self.requester),
            status=SwapRequest.COMPLETED,
        )
        hidden = self.make_swap(
            requested_item=self.make_item('Hidden'), offered_item=self.make_item('Hidden offer', user=self.requester),
            requester_hidden=True,
        )
        self.login(self.requester)
        response = self.client.get(reverse('swap_requests:index'), {'tab': 'kamu'})
        row = response.context['request_summary_rows'][1]
        self.assertEqual((row['total'], row['pending'], row['awaiting']), (2, 1, 1))
        self.assertEqual([s.pk for s in response.context['outgoing']], [completed.pk, awaiting.pk, pending.pk])

    def test_incoming_group_status_priority_returned_and_deleted_request_snapshots(self):
        awaiting_item = self.make_item('Awaiting garment', user=self.owner, is_listed_for_swap=True)
        pending = self.make_swap(
            requested_item=awaiting_item, offered_item=self.make_item('Pending offer', user=self.requester),
            requested_listing_cycle_key='11:cycle-a',
        )
        awaiting = self.make_swap(
            requested_item=awaiting_item, offered_item=self.make_item('Awaiting offer', user=self.outsider),
            requester=self.outsider, status=SwapRequest.AWAITING,
            requested_listing_cycle_key='11:cycle-a',
        )
        rejected_item = self.make_item('Rejected garment', user=self.owner, is_listed_for_swap=True)
        rejected = self.make_swap(
            requested_item=rejected_item, offered_item=self.make_item('Rejected offer', user=self.requester),
            status=SwapRequest.REJECTED, requested_listing_cycle_key='12:cycle-b',
        )
        returned_item = self.make_item('Returned garment', user=self.owner, is_listed_for_swap=True)
        returned = self.make_swap(
            requested_item=returned_item, offered_item=self.make_item('Returned offer', user=self.requester),
            requested_listing_cycle_key='13:cycle-c', requested_listing_returned_to_wardrobe=True,
        )
        deleted = self.make_swap(
            requested_item=None, offered_item=self.make_item('Deleted offer', user=self.requester),
            requested_item_name='Deleted snapshot', status=SwapRequest.REJECTED,
        )
        self.login(self.owner)
        response = self.client.get(reverse('swap_requests:index'))
        groups = {group['name']: group for group in response.context['groups']}
        self.assertEqual(groups['Awaiting garment']['top_status'], SwapRequest.AWAITING)
        self.assertEqual(groups['Awaiting garment']['total'], 2)
        self.assertEqual(groups['Rejected garment']['top_status'], SwapRequest.REJECTED)
        self.assertEqual(groups['Returned garment']['top_label'], 'Dikembalikan ke lemari')
        self.assertEqual(groups['Returned garment']['top_style'], 'sr-status--returned')
        self.assertEqual(groups['Deleted snapshot']['item'], None)
        self.assertEqual(groups['Deleted snapshot']['top_status'], SwapRequest.REJECTED)
        self.assertEqual({pending.pk, awaiting.pk}, {s.pk for s in groups['Awaiting garment']['requests']})
        self.assertEqual(rejected.status, SwapRequest.REJECTED)
        self.assertEqual(returned.status, SwapRequest.PENDING)

    def test_item_requests_handles_cycle_scope_visibility_and_seen_notifications(self):
        first = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
            requested_listing_cycle_key=self.listing.cycle_key,
        )
        old_cycle = self.make_swap(
            requested_item=self.requested,
            offered_item=self.make_item('Old offer', user=self.outsider), requester=self.outsider,
            requested_listing_cycle_key='123:old-cycle',
        )
        legacy = self.make_swap(
            requested_item=self.requested,
            offered_item=self.make_item('Legacy offer', user=self.outsider), requester=self.outsider,
            requested_listing_cycle_key='',
        )
        self.login(self.owner)

        response = self.client.get(
            reverse('swap_requests:item_requests', args=[self.requested.pk]),
            {'cycle': self.listing.cycle_key},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([s.pk for s in response.context['others']], [first.pk])
        self.assertIsNotNone(first.notifications.get(recipient=self.owner).read_at)
        self.assertEqual(response.context['cycle_param'], self.listing.cycle_key)

        legacy_response = self.client.get(
            reverse('swap_requests:item_requests', args=[self.requested.pk]), {'cycle': 'legacy'},
        )
        self.assertEqual([s.pk for s in legacy_response.context['others']], [legacy.pk])
        self.assertEqual(old_cycle.requested_listing_cycle_key, '123:old-cycle')
        blank_scope = self.client.get(
            reverse('swap_requests:item_requests', args=[self.requested.pk]), {'cycle': ' '},
        )
        self.assertEqual(blank_scope.status_code, 200)
        self.assertEqual(len(blank_scope.context['others']), 3)
        htmx = self.client.get(
            reverse('swap_requests:item_requests', args=[self.requested.pk]),
            {'cycle': self.listing.cycle_key}, HTTP_HX_REQUEST='true',
        )
        self.assertTemplateUsed(htmx, 'swap_requests/partials/item_requests_content.html')
        bad_scope = self.client.get(
            reverse('swap_requests:item_requests', args=[self.requested.pk]), {'cycle': 'bad'},
        )
        self.assertEqual(bad_scope.status_code, 404)

    def test_item_requests_redirects_for_non_owner_without_visible_requests_and_404_for_missing_item(self):
        foreign_item = self.make_item('Foreign item', user=self.outsider)
        self.login(self.owner)
        response = self.client.get(reverse('swap_requests:item_requests', args=[foreign_item.pk]))
        self.assertRedirects(response, reverse('swap_requests:index'))
        response = self.client.get(reverse('swap_requests:item_requests', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_create_get_post_success_ajax_existing_active_and_invalid_listing(self):
        self.login(self.requester)
        create_url = reverse('swap_requests:create')
        get_response = self.client.get(create_url, {'item': self.requested.pk})
        self.assertEqual(get_response.status_code, 200)
        self.assertTemplateUsed(get_response, 'swap_requests/form.html')
        self.assertContains(get_response, 'Cardigan sage')

        posted = self.client.post(create_url + f'?item={self.requested.pk}', {
            'offered_item': self.offered.pk, 'message': 'Aku suka cardigan ini',
        })
        created = SwapRequest.objects.get(requester=self.requester, requested_item=self.requested)
        self.assertRedirects(posted, reverse('swap_requests:sent', args=[created.pk]))
        self.assertEqual(created.requested_listing_cycle_key, self.listing.cycle_key)
        self.assertEqual(created.message, 'Aku suka cardigan ini')

        duplicate = self.client.get(create_url, {'item': self.requested.pk})
        self.assertRedirects(duplicate, reverse('swap_requests:detail', args=[created.pk]))

        inactive_item = self.make_item('Not listed', user=self.owner)
        invalid = self.client.get(create_url, {'item': inactive_item.pk})
        self.assertRedirects(invalid, reverse('swap_requests:index'))
        own = self.make_item('My own', user=self.requester, is_listed_for_swap=True)
        self.make_listing(own, user=self.requester)
        own_result = self.client.get(create_url, {'item': own.pk})
        self.assertRedirects(own_result, reverse('swap_requests:index'))

        ajax_item = self.make_item('Second listing', user=self.owner, is_listed_for_swap=True)
        ajax_listing = self.make_listing(ajax_item, user=self.owner)
        ajax_offer = self.make_item('Second offer', user=self.requester)
        ajax = self.client.post(
            create_url + f'?item={ajax_item.pk}',
            {'offered_item': ajax_offer.pk, 'message': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(ajax.status_code, 200)
        self.assertTemplateUsed(ajax, 'swap_requests/sent.html')
        self.assertEqual(
            SwapRequest.objects.get(requested_item=ajax_item).requested_listing_cycle_key,
            ajax_listing.cycle_key,
        )

    def test_create_invalid_post_and_post_duplicate_active_race_guard(self):
        self.login(self.requester)
        create_url = reverse('swap_requests:create')
        invalid = self.client.post(create_url + f'?item={self.requested.pk}', {'message': ''})
        self.assertEqual(invalid.status_code, 200)
        self.assertTemplateUsed(invalid, 'swap_requests/form.html')
        self.assertFalse(SwapRequest.objects.exists())

        # The pre-save duplicate guard is exercised independently of form validation.
        duplicate = self.make_swap(
            requested_item=self.requested, offered_item=self.make_item('Existing offer', user=self.requester),
        )
        response = self.client.post(create_url + f'?item={self.requested.pk}', {
            'offered_item': self.offered.pk, 'message': '',
        })
        self.assertRedirects(response, reverse('swap_requests:detail', args=[duplicate.pk]))
        self.assertEqual(SwapRequest.objects.filter(requested_item=self.requested).count(), 1)

        bad_id = self.client.get(create_url, {'item': 'not-an-id'})
        self.assertRedirects(bad_id, reverse('swap_requests:index'))
        self.assertRedirects(self.client.get(create_url), reverse('swap_requests:index'))

        # Simulate a request created between the first check and the validated POST.
        race_requested = self.make_item('Race requested', user=self.owner, is_listed_for_swap=True)
        self.make_listing(race_requested, user=self.owner)
        race_offered = self.make_item('Race offer', user=self.requester)

        class RaceForm:
            def __init__(self, *args, **kwargs):
                self.fields = {'offered_item': SimpleNamespace(queryset=ClothingItem.objects.none())}

            def is_valid(self):
                SwapRequest.objects.create(
                    requester=self.requester, owner=self.owner,
                    requested_item=self.race_requested, offered_item=self.race_offered,
                    requested_item_name=self.race_requested.name, offered_item_name=self.race_offered.name,
                )
                return True

        RaceForm.requester = self.requester
        RaceForm.owner = self.owner
        RaceForm.race_requested = race_requested
        RaceForm.race_offered = race_offered
        with patch('swap_requests.views.SwapRequestForm', RaceForm):
            raced = self.client.post(create_url + f'?item={race_requested.pk}', {'offered_item': race_offered.pk})
        existing = SwapRequest.objects.get(requested_item=race_requested)
        self.assertRedirects(raced, reverse('swap_requests:detail', args=[existing.pk]))

    def test_sent_is_requester_only_and_respects_hidden_flag(self):
        swap = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        url = reverse('swap_requests:sent', args=[swap.pk])
        self.login(self.requester)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login(self.requester)
        swap.requester_hidden = True
        swap.save(update_fields=['requester_hidden'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_detail_access_roles_marks_notices_and_listing_link(self):
        swap = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
            requested_listing_cycle_key=self.listing.cycle_key,
        )
        url = reverse('swap_requests:detail', args=[swap.pk])
        self.login(self.owner)
        owner_view = self.client.get(url)
        self.assertEqual(owner_view.status_code, 200)
        self.assertContains(owner_view, 'Lihat detail item untuk swap')
        self.assertIsNotNone(swap.notifications.get(recipient=self.owner).read_at)

        self.login(self.requester)
        requester_view = self.client.get(url)
        self.assertEqual(requester_view.status_code, 200)
        self.assertEqual(requester_view.context['role'], 'requester')
        self.assertEqual(requester_view.context['get_item'], self.requested)

        self.login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_detail_hides_deleted_listing_link_and_displays_contacts_only_while_awaiting(self):
        self.requester_profile.phone_number = '08123456789'
        self.requester_profile.save(update_fields=['phone_number'])
        self.owner_profile.phone_number = '08987654321'
        self.owner_profile.save(update_fields=['phone_number'])
        swap = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
            requested_listing_cycle_key='123:another-listing-cycle',
            status=SwapRequest.AWAITING,
        )
        self.login(self.owner)
        awaiting = self.client.get(reverse('swap_requests:detail', args=[swap.pk]))
        self.assertContains(awaiting, '08123456789')
        self.assertContains(awaiting, '08987654321')

        self.login(self.requester)
        no_listing = self.client.get(reverse('swap_requests:detail', args=[swap.pk]))
        self.assertContains(no_listing, 'Detail item untuk swap sudah tidak tersedia')
        self.assertContains(no_listing, '08123456789')

        swap.status = SwapRequest.PENDING
        swap.save(update_fields=['status'])
        pending = self.client.get(reverse('swap_requests:detail', args=[swap.pk]))
        self.assertNotContains(pending, 'Kontak untuk pertukaran')

        invalid_listing_key = self.make_swap(
            requested_item=self.requested, offered_item=self.make_item('Invalid key offer', user=self.requester),
            status=SwapRequest.AWAITING, requested_listing_cycle_key='not-a-valid-cycle',
        )
        invalid_response = self.client.get(reverse('swap_requests:detail', args=[invalid_listing_key.pk]))
        self.assertContains(invalid_response, 'Detail item untuk swap sudah tidak tersedia')

    def test_update_only_pending_requester_and_updates_offer_or_shows_invalid_form(self):
        swap = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        url = reverse('swap_requests:update', args=[swap.pk])
        self.login(self.requester)
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        replacement = self.make_item('Replacement', user=self.requester)
        updated = self.client.post(url, {'offered_item': replacement.pk, 'message': 'Edit pesan'})
        self.assertRedirects(updated, reverse('swap_requests:detail', args=[swap.pk]))
        swap.refresh_from_db()
        self.assertEqual(swap.offered_item, replacement)
        self.assertEqual(swap.message, 'Edit pesan')

        invalid = self.client.post(url, {'offered_item': '', 'message': ''})
        self.assertEqual(invalid.status_code, 200)
        self.assertTemplateUsed(invalid, 'swap_requests/form.html')
        self.login(self.owner)
        denied = self.client.get(url)
        self.assertRedirects(denied, reverse('swap_requests:detail', args=[swap.pk]))
        swap.status = SwapRequest.AWAITING
        swap.save(update_fields=['status'])
        self.login(self.requester)
        denied_status = self.client.post(url, {'offered_item': replacement.pk, 'message': ''})
        self.assertRedirects(denied_status, reverse('swap_requests:detail', args=[swap.pk]))

    def test_respond_accept_reject_invalid_action_permissions_conflict_and_htmx(self):
        requested = self.make_item('Incoming', user=self.owner, is_listed_for_swap=True)
        self.make_listing(requested)
        swap = self.make_swap(requested_item=requested, offered_item=self.offered)
        url = reverse('swap_requests:respond', args=[swap.pk])
        self.login(self.requester)
        denied = self.client.post(url, {'action': 'accept'})
        self.assertRedirects(denied, reverse('swap_requests:detail', args=[swap.pk]))
        self.login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 405)
        accepted = self.client.post(url, {'action': 'accept'}, HTTP_HX_REQUEST='true')
        self.assertEqual(accepted.status_code, 200)
        self.assertTemplateUsed(accepted, 'swap_requests/partials/detail_update.html')
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)

        no_longer_pending = self.client.post(url, {'action': 'reject'})
        self.assertRedirects(no_longer_pending, reverse('swap_requests:detail', args=[swap.pk]))

        other_requested = self.make_item('Other incoming', user=self.outsider, is_listed_for_swap=True)
        self.make_listing(other_requested, user=self.outsider)
        conflict = self.make_swap(
            requested_item=other_requested,
            offered_item=self.make_item('Conflict offer', user=self.requester),
            requester=self.requester,
        )
        # Seed a separate active swap that shares the conflicting item.
        shared = self.make_item('Shared item', user=self.owner, is_listed_for_swap=True)
        self.make_swap(
            requested_item=shared,
            offered_item=self.make_item('Locked offer', user=self.outsider),
            requester=self.outsider, status=SwapRequest.AWAITING,
        )
        conflict.offered_item = shared
        conflict.save(update_fields=['offered_item'])
        self.login(self.owner)
        conflict_result = self.client.post(
            reverse('swap_requests:respond', args=[conflict.pk]), {'action': 'accept'},
        )
        self.assertRedirects(conflict_result, reverse('swap_requests:detail', args=[conflict.pk]))
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SwapRequest.PENDING)

        other = self.make_swap(
            requested_item=self.make_item('Reject me', user=self.owner, is_listed_for_swap=True),
            offered_item=self.make_item('Reject offer', user=self.requester),
        )
        rejected = self.client.post(reverse('swap_requests:respond', args=[other.pk]), {'action': 'reject'})
        self.assertRedirects(rejected, reverse('swap_requests:detail', args=[other.pk]))
        other.refresh_from_db()
        self.assertEqual(other.status, SwapRequest.REJECTED)

        unknown = self.make_swap(
            requested_item=self.make_item('Unknown action', user=self.owner, is_listed_for_swap=True),
            offered_item=self.make_item('Unknown offer', user=self.requester),
        )
        response = self.client.post(reverse('swap_requests:respond', args=[unknown.pk]), {'action': 'ignore'})
        self.assertRedirects(response, reverse('swap_requests:detail', args=[unknown.pk]))
        unknown.refresh_from_db()
        self.assertEqual(unknown.status, SwapRequest.PENDING)

    def test_confirm_rejects_invalid_state_and_handles_done_cancel_and_htmx(self):
        swap = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
            status=SwapRequest.PENDING,
        )
        url = reverse('swap_requests:confirm', args=[swap.pk])
        self.login(self.requester)
        invalid_state = self.client.post(url, {'choice': SwapRequest.DONE})
        self.assertRedirects(invalid_state, reverse('swap_requests:detail', args=[swap.pk]))
        self.assertEqual(self.client.post(url, {'choice': 'bogus'}).status_code, 302)
        self.login(self.outsider)
        forbidden = self.client.post(url, {'choice': SwapRequest.DONE})
        self.assertEqual(forbidden.status_code, 404)
        self.login(self.requester)
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.PENDING)

        swap.status = SwapRequest.AWAITING
        swap.save(update_fields=['status'])
        first_choice = self.client.post(url, {'choice': SwapRequest.DONE}, HTTP_HX_REQUEST='true')
        self.assertEqual(first_choice.status_code, 200)
        self.assertTemplateUsed(first_choice, 'swap_requests/partials/detail_update.html')
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.AWAITING)
        self.login(self.owner)
        completed = self.client.post(url, {'choice': SwapRequest.DONE})
        self.assertRedirects(completed, reverse('swap_requests:detail', args=[swap.pk]))
        swap.refresh_from_db()
        self.assertEqual(swap.status, SwapRequest.COMPLETED)

        cancelled = self.make_swap(
            requested_item=self.make_item('Cancel requested'),
            offered_item=self.make_item('Cancel offered', user=self.requester),
            status=SwapRequest.AWAITING,
        )
        self.login(self.requester)
        result = self.client.post(
            reverse('swap_requests:confirm', args=[cancelled.pk]), {'choice': SwapRequest.CANCEL},
        )
        self.assertRedirects(result, reverse('swap_requests:detail', args=[cancelled.pk]))
        cancelled.refresh_from_db()
        self.assertEqual(cancelled.status, SwapRequest.REJECTED)

    def test_delete_single_applies_role_specific_rules_and_htmx_error(self):
        url_name = 'swap_requests:delete'
        pending = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        self.login(self.requester)
        deleted = self.client.post(reverse(url_name, args=[pending.pk]))
        self.assertRedirects(deleted, reverse('swap_requests:index') + '?tab=kamu')
        self.assertFalse(SwapRequest.objects.filter(pk=pending.pk).exists())

        incoming = self.make_swap(
            requested_item=self.make_item('Owner pending'),
            offered_item=self.make_item('Requester item', user=self.requester),
        )
        self.login(self.owner)
        hidden = self.client.post(reverse(url_name, args=[incoming.pk]))
        self.assertRedirects(hidden, reverse('swap_requests:index') + '?tab=masuk')
        incoming.refresh_from_db()
        self.assertEqual(incoming.status, SwapRequest.REJECTED)
        self.assertTrue(incoming.owner_hidden)
        self.assertFalse(incoming.requester_hidden)

        completed = self.make_swap(
            requested_item=self.make_item('Completed'), offered_item=self.make_item('Completed offer', user=self.requester),
            status=SwapRequest.COMPLETED,
        )
        self.login(self.requester)
        hidden_htmx = self.client.post(
            reverse(url_name, args=[completed.pk]), HTTP_HX_REQUEST='true',
        )
        self.assertTemplateUsed(hidden_htmx, 'swap_requests/partials/delete_result.html')
        completed.refresh_from_db()
        self.assertTrue(completed.requester_hidden)

        awaiting = self.make_swap(
            requested_item=self.make_item('Awaiting'),
            offered_item=self.make_item('Awaiting offer', user=self.requester),
            status=SwapRequest.AWAITING,
        )
        blocked = self.client.post(
            reverse(url_name, args=[awaiting.pk]), HTTP_HX_REQUEST='true',
        )
        self.assertContains(blocked, 'tidak bisa dihapus', status_code=200)
        self.assertTrue(blocked.context['delete_failed'])
        self.assertTrue(SwapRequest.objects.filter(pk=awaiting.pk).exists())
        normal_blocked = self.client.post(reverse(url_name, args=[awaiting.pk]))
        self.assertRedirects(normal_blocked, reverse('swap_requests:detail', args=[awaiting.pk]))

        owner_completed = self.make_swap(
            requested_item=self.make_item('Owner completed'),
            offered_item=self.make_item('Owner completed offer', user=self.requester),
            status=SwapRequest.COMPLETED,
        )
        self.login(self.owner)
        self.client.post(reverse(url_name, args=[owner_completed.pk]))
        owner_completed.refresh_from_db()
        self.assertTrue(owner_completed.owner_hidden)

    def test_shared_delete_helper_ignores_unrelated_users_and_locked_requests(self):
        pending = self.make_swap()
        self.assertIsNone(_delete_swap_for_party(pending, self.outsider))
        self.assertTrue(SwapRequest.objects.filter(pk=pending.pk).exists())
        awaiting = self.make_swap(status=SwapRequest.AWAITING)
        self.assertIsNone(_delete_swap_for_party(awaiting, self.owner))
        self.assertTrue(SwapRequest.objects.filter(pk=awaiting.pk).exists())

    def test_bulk_delete_parses_ids_respects_hidden_status_and_htmx_render_paths(self):
        pending = self.make_swap(requested_item=self.requested, offered_item=self.offered)
        completed = self.make_swap(
            requested_item=self.make_item('Done'), offered_item=self.make_item('Done offer', user=self.requester),
            status=SwapRequest.COMPLETED,
        )
        awaiting = self.make_swap(
            requested_item=self.make_item('Awaiting', is_listed_for_swap=True), offered_item=self.make_item('Awaiting offer', user=self.requester),
            status=SwapRequest.AWAITING,
        )
        self.login(self.requester)
        url = reverse('swap_requests:bulk_delete')

        empty = self.client.post(url, {'tab': 'kamu', 'swap_ids': ['not-numeric']})
        self.assertRedirects(empty, reverse('swap_requests:index') + '?tab=kamu')
        awaiting_only = self.client.post(url, {'tab': 'kamu', 'swap_ids': [str(awaiting.pk)]})
        self.assertRedirects(awaiting_only, reverse('swap_requests:index') + '?tab=kamu')

        partial = self.client.post(url, {
            'tab': 'kamu', 'status': 'completed',
            'swap_ids': [str(pending.pk), str(pending.pk), str(completed.pk), str(awaiting.pk), 'junk', '99999'],
        }, HTTP_HX_REQUEST='true')
        self.assertTemplateUsed(partial, 'swap_requests/partials/index_content.html')
        self.assertFalse(SwapRequest.objects.filter(pk=pending.pk).exists())
        completed.refresh_from_db()
        self.assertTrue(completed.requester_hidden)
        self.assertTrue(SwapRequest.objects.filter(pk=awaiting.pk).exists())

        incoming = self.make_swap(
            requested_item=self.requested,
            offered_item=self.make_item('Incoming offer', user=self.outsider),
            requester=self.outsider,
        )
        self.login(self.owner)
        item_partial = self.client.post(url, {
            'tab': 'masuk', 'item_id': str(self.requested.pk),
            'cycle': self.listing.cycle_key, 'swap_ids': [str(incoming.pk)],
        }, HTTP_HX_REQUEST='true')
        self.assertTemplateUsed(item_partial, 'swap_requests/partials/item_requests_content.html')
        incoming.refresh_from_db()
        self.assertEqual(incoming.status, SwapRequest.REJECTED)
        self.assertTrue(incoming.owner_hidden)

        returned = self.client.post(url, {
            'tab': 'masuk', 'item_id': str(self.requested.pk),
            'cycle': 'legacy', 'status': 'pending', 'swap_ids': ['bad'],
        })
        self.assertRedirects(
            returned,
            reverse('swap_requests:item_requests', args=[self.requested.pk]) + '?cycle=legacy',
        )

        # A valid but unrelated item has no incoming request folder for this user;
        # HTMX falls back to the normal index partial.
        foreign_item = self.make_item('Foreign empty folder', user=self.outsider)
        no_folder = self.client.post(url, {
            'tab': 'masuk', 'item_id': str(foreign_item.pk), 'swap_ids': [],
        }, HTTP_HX_REQUEST='true')
        self.assertTemplateUsed(no_folder, 'swap_requests/partials/index_content.html')

        no_cycle = self.client.post(url, {
            'tab': 'masuk', 'item_id': str(self.requested.pk), 'status': 'not-a-status', 'swap_ids': [],
        })
        self.assertRedirects(no_cycle, reverse('swap_requests:item_requests', args=[self.requested.pk]))
        invalid_status = self.client.post(url, {
            'tab': 'kamu', 'status': 'not-a-status', 'swap_ids': [],
        })
        self.assertRedirects(invalid_status, reverse('swap_requests:index') + '?tab=kamu')
        valid_status = self.client.post(url, {
            'tab': 'kamu', 'status': 'pending', 'swap_ids': [],
        })
        self.assertRedirects(valid_status, reverse('swap_requests:index') + '?tab=kamu&status=pending')
        nonnumeric_item = self.client.post(url, {
            'tab': 'masuk', 'item_id': 'not-numeric', 'status': 'rejected', 'swap_ids': [],
        })
        self.assertRedirects(
            nonnumeric_item,
            reverse('swap_requests:index') + '?tab=masuk&status=rejected',
        )

    def test_bulk_delete_honors_hidden_visibility_and_bad_cycle_returns_404(self):
        own_sent = self.make_swap(
            requested_item=self.requested, offered_item=self.offered,
        )
        hidden_for_requester = self.make_swap(
            requested_item=self.make_item('Hidden requested'),
            offered_item=self.make_item('Hidden offered', user=self.requester),
            requester_hidden=True,
        )
        self.login(self.requester)
        response = self.client.post(reverse('swap_requests:bulk_delete'), {
            'tab': 'kamu', 'swap_ids': [str(own_sent.pk), str(hidden_for_requester.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SwapRequest.objects.filter(pk=own_sent.pk).exists())
        self.assertTrue(SwapRequest.objects.filter(pk=hidden_for_requester.pk).exists())

        bad = self.client.post(reverse('swap_requests:bulk_delete'), {
            'tab': 'masuk', 'item_id': str(self.requested.pk), 'cycle': 'invalid',
        })
        self.assertEqual(bad.status_code, 404)


class SwapRequestContextProcessorTests(SwapDataMixin, TestCase):
    def test_unread_count_for_anonymous_and_authenticated_users(self):
        anonymous = SimpleNamespace(user=AnonymousUser())
        self.assertEqual(swap_request_unread_count(anonymous), {'swap_request_unread_count': 0})
        swap = self.make_swap()
        request = SimpleNamespace(user=self.owner)
        self.assertEqual(swap_request_unread_count(request)['swap_request_unread_count'], 1)
        SwapRequestNotification.objects.create(
            swap_request=swap, recipient=self.owner, status=SwapRequest.AWAITING,
            read_at=timezone.now(),
        )
        self.assertEqual(swap_request_unread_count(request)['swap_request_unread_count'], 1)
        swap.owner_hidden = True
        swap.save(update_fields=['owner_hidden'])
        self.assertEqual(swap_request_unread_count(request)['swap_request_unread_count'], 0)
