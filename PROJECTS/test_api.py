"""Regression tests for the DRF surface, using the same session flow as the UI."""
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.middleware.csrf import _get_new_csrf_string
from rest_framework.test import APIClient, APITestCase

from digital_wardrobe.models import ClothingItem, Outfit
from items_for_swap.models import ItemForSwap
from outfit_calendar.models import OutfitSchedule
from swap_requests.models import SwapRequest


class SwapDrobeAPITestCase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='pass12345')
        self.requester = User.objects.create_user('requester', password='pass12345')
        self.outsider = User.objects.create_user('outsider', password='pass12345')
        self.owner_item = self.item('Owner shirt', self.owner)
        self.requester_item = self.item('Requester shirt', self.requester)
        self.owner_outfit = Outfit.objects.create(user=self.owner, name='Campus')
        self.owner_outfit.items.add(self.owner_item)

    @staticmethod
    def item(name, user):
        return ClothingItem.objects.create(
            user=user, name=name, category='top', size='M', gender='unisex',
            condition='good', color='neutral',
        )

    @staticmethod
    def upload_image():
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        output = BytesIO()
        Image.new('RGB', (1, 1), 'white').save(output, 'PNG')
        return SimpleUploadedFile('shirt.png', output.getvalue(), content_type='image/png')

    @staticmethod
    def session_client(user, csrf=False, send_token=True):
        client = APIClient(enforce_csrf_checks=csrf)
        if csrf:
            client.login(username=user.username, password='pass12345')
        else:
            client.force_login(user)
        if csrf and send_token:
            token = _get_new_csrf_string()
            client.cookies['csrftoken'] = token
            client.credentials(HTTP_X_CSRFTOKEN=token)
        return client

    def test_wardrobe_crud_and_owner_protection(self):
        client = self.session_client(self.owner)
        self.assertEqual(client.post('/api/digital-wardrobe/items/', {'name': 'Invalid'}, format='json').status_code, 400)
        response = client.post('/api/digital-wardrobe/items/', {
            'name': 'New shirt', 'category': 'top', 'size': 'S', 'gender': 'women',
            'condition': 'like_new', 'color': 'pastel',
            'image': self.upload_image(),
            'user': self.outsider.pk, 'is_idle': True, 'is_listed_for_swap': True,
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['user'], self.owner.username)
        self.assertFalse(response.data['is_listed_for_swap'])
        pk = response.data['id']
        self.assertEqual(client.patch(f'/api/digital-wardrobe/items/{pk}/', {'name': 'Edited'}, format='json').status_code, 200)
        self.assertEqual(client.put(f'/api/digital-wardrobe/items/{pk}/', {
            'name': 'Replaced', 'category': 'top', 'size': 'S', 'gender': 'women',
            'condition': 'like_new', 'color': 'pastel', 'description': '',
            'image': self.upload_image(),
        }, format='multipart').status_code, 200)
        self.assertEqual(client.delete(f'/api/digital-wardrobe/items/{pk}/').status_code, 204)
        self.assertEqual(client.delete('/api/digital-wardrobe/items/').status_code, 405)

        self.assertEqual(
            self.session_client(self.outsider).patch(
                f'/api/digital-wardrobe/items/{self.owner_item.pk}/', {'name': 'Nope'}, format='json',
            ).status_code,
            404,
        )

    def test_session_authentication_enforces_csrf(self):
        blocked = self.session_client(self.owner, csrf=True, send_token=False)
        response = blocked.patch(
            f'/api/digital-wardrobe/items/{self.owner_item.pk}/', {'name': 'Blocked'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

        allowed = self.session_client(self.owner, csrf=True)
        response = allowed.patch(
            f'/api/digital-wardrobe/items/{self.owner_item.pk}/', {'name': 'Allowed'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    @patch('items_for_swap.serializers.resolve_location')
    def test_listing_crud_and_public_read(self, resolve_location):
        resolve_location.return_value = {
            'code': '3276', 'city': 'Kota Depok', 'province': 'Jawa Barat',
            'label': 'Kota Depok, Jawa Barat',
        }
        client = self.session_client(self.owner)
        response = client.post('/api/items-for-swap/', {
            'clothing_item_id': self.owner_item.pk, 'meeting_city_code': '3276',
            'meeting_place': 'Stasiun UI', 'reason': 'Siap ditukar',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        listing_id = response.data['id']
        self.assertEqual(APIClient().get('/api/items-for-swap/').status_code, 200)
        liker = self.session_client(self.requester)
        liked = liker.post(f'/api/home/items-for-swap/{listing_id}/like/', format='json')
        self.assertEqual(liked.status_code, 200, liked.data)
        self.assertTrue(liked.data['liked'])
        unliked = liker.post(f'/api/home/items-for-swap/{listing_id}/like/', format='json')
        self.assertFalse(unliked.data['liked'])
        self.assertEqual(client.patch(
            f'/api/items-for-swap/{listing_id}/', {'reason': 'Kondisi bagus'}, format='json',
        ).status_code, 200)
        updated = client.put(f'/api/items-for-swap/{listing_id}/', {
            'meeting_city_code': '3276', 'meeting_place': 'Margo City', 'reason': 'Kondisi terbaik',
        }, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['meeting_location'], 'Margo City, Kota Depok, Jawa Barat')
        self.assertEqual(client.delete(f'/api/items-for-swap/{listing_id}/').status_code, 204)

    def test_bulk_delete_and_read_only_owner(self):
        client = self.session_client(self.owner)
        another = self.item('Archive me', self.owner)
        response = client.post('/api/digital-wardrobe/items/bulk-delete/', {
            'items': [self.owner_item.pk, another.pk], 'user': self.outsider.pk,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data['removed']), {self.owner_item.pk, another.pk})
        self.assertFalse(ClothingItem.objects.in_wardrobe(self.owner).filter(
            pk__in=[self.owner_item.pk, another.pk],
        ).exists())

    def test_swap_request_role_permissions_and_status_flow(self):
        ItemForSwap.objects.create(
            clothing_item=self.owner_item, user=self.owner, meeting_location='Depok',
        )
        requester = self.session_client(self.requester)
        created = requester.post('/api/swap-requests/', {
            'requested_item_id': self.owner_item.pk,
            'offered_item_id': self.requester_item.pk,
            'message': 'Mari bertukar',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        pk = created.data['id']
        self.assertEqual(self.session_client(self.outsider).patch(
            f'/api/swap-requests/{pk}/', {'message': 'No'}, format='json',
        ).status_code, 404)
        accepted = self.session_client(self.owner).post(
            f'/api/swap-requests/{pk}/respond/', {'action': 'accept'}, format='json',
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data['status'], SwapRequest.AWAITING)
        self.assertEqual(requester.post(
            f'/api/swap-requests/{pk}/confirm/', {'choice': 'done'}, format='json',
        ).status_code, 200)
        completed = self.session_client(self.owner).post(
            f'/api/swap-requests/{pk}/confirm/', {'choice': 'done'}, format='json',
        )
        self.assertEqual(completed.data['status'], SwapRequest.COMPLETED)
        self.owner_item.refresh_from_db()
        self.assertEqual(self.owner_item.user, self.requester)

    def test_swap_bulk_delete_uses_api(self):
        pending = SwapRequest.objects.create(
            requester=self.requester, owner=self.owner,
            requested_item=self.owner_item, offered_item=self.requester_item,
            requested_item_name=self.owner_item.name, offered_item_name=self.requester_item.name,
            message='hapus', status=SwapRequest.PENDING,
        )
        response = self.session_client(self.owner).post(
            '/api/swap-requests/bulk-delete/', {'swap_ids': [pending.pk]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        pending.refresh_from_db()
        self.assertTrue(pending.owner_hidden)

    def test_outfit_and_calendar_crud_validation(self):
        client = self.session_client(self.owner)
        outfit = client.post('/api/digital-wardrobe/outfits/', {
            'name': 'Weekend', 'description': '', 'item_ids': [self.owner_item.pk],
        }, format='json')
        self.assertEqual(outfit.status_code, 201, outfit.data)
        outfit_pk = outfit.data['id']
        day = (date.today() + timedelta(days=2)).isoformat()
        schedule = client.post('/api/outfit-calendar/schedules/', {
            'date': day, 'outfit_id': outfit_pk, 'note': 'Acara',
        }, format='json')
        self.assertEqual(schedule.status_code, 201, schedule.data)
        schedule_pk = schedule.data['id']
        self.assertTrue(OutfitSchedule.objects.filter(pk=schedule_pk).exists())
        self.assertEqual(client.patch(
            f'/api/outfit-calendar/schedules/{schedule_pk}/', {'note': 'Diubah'}, format='json',
        ).status_code, 200)
        self.assertEqual(client.delete(f'/api/outfit-calendar/schedules/{schedule_pk}/').status_code, 204)

    def test_private_endpoints_reject_anonymous_users(self):
        self.assertEqual(APIClient().get('/api/digital-wardrobe/items/').status_code, 403)
        self.assertEqual(APIClient().get('/api/swap-requests/').status_code, 403)
        self.assertEqual(APIClient().get('/api/outfit-calendar/schedules/').status_code, 403)
