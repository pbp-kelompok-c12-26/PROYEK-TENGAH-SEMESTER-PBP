from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from swap_requests.models import SwapRequest

from .models import ClothingItem, Outfit
from .serializers import ClothingItemSerializer, OutfitSerializer


class SessionAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]


class ClothingItemListAPIView(SessionAPIView):
    def get(self, request):
        ClothingItem.objects.refresh_idle(request.user)
        return Response(ClothingItemSerializer(
            ClothingItem.objects.in_wardrobe(request.user), many=True,
            context={'request': request},
        ).data)

    def post(self, request):
        serializer = ClothingItemSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(user=request.user)
        return Response(ClothingItemSerializer(item, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class ClothingItemDetailAPIView(SessionAPIView):
    def get_object(self, pk):
        try:
            return ClothingItem.objects.in_wardrobe(self.request.user).get(pk=pk)
        except ClothingItem.DoesNotExist:
            raise NotFound('Pakaian tidak ditemukan.')

    def get(self, request, pk):
        return Response(ClothingItemSerializer(self.get_object(pk), context={'request': request}).data)

    def _locked_response(self, item):
        if item.is_listed_for_swap:
            return Response({'detail': 'Pakaian yang sedang ditawarkan dikelola dari Items for Swap.'}, status=409)
        if SwapRequest.objects.has_active_request(item):
            return Response({'detail': 'Pakaian sedang dipakai dalam swap request aktif.'}, status=409)
        return None

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        item = self.get_object(pk)
        if response := self._locked_response(item):
            return response
        serializer = ClothingItemSerializer(item, data=request.data, partial=partial,
                                           context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(ClothingItemSerializer(serializer.save(), context={'request': request}).data)

    def delete(self, request, pk):
        item = self.get_object(pk)
        if response := self._locked_response(item):
            return response
        try:
            item.remove_from_wardrobe()
        except DjangoValidationError as error:
            return Response({'detail': ' '.join(error.messages)}, status=409)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClothingItemBulkDeleteAPIView(SessionAPIView):
    """Aksi batch untuk UI Lemari; tetap menggunakan aturan model yang sama."""

    def post(self, request):
        raw_ids = request.data.get('items', [])
        if not isinstance(raw_ids, list):
            raw_ids = [raw_ids]
        ids = {int(value) for value in raw_ids if str(value).isdigit()}
        if not ids:
            return Response({'ok': False, 'message': 'Pilih minimal 1 pakaian yang ingin dihapus.'}, status=400)
        if len(ids) > 50:
            return Response({'ok': False, 'message': 'Maksimal 50 pakaian sekali hapus.'}, status=400)
        result = ClothingItem.objects.remove_many(request.user, ids)
        removed = result['archived'] + result['deleted']
        parts = [f'{len(removed)} pakaian dihapus dari lemarimu.' if removed else 'Tidak ada pakaian yang dihapus.']
        if result['skipped']:
            parts.append(f'{len(result["skipped"])} pakaian dilewati karena sedang dipakai dalam swap request.')
        if result['not_found']:
            parts.append(f'{result["not_found"]} pakaian tidak ditemukan di lemarimu.')
        return Response({
            'ok': True,
            'removed': [item.pk for item in removed],
            'skipped': [item.pk for item in result['skipped']],
            'total_items': ClothingItem.objects.in_wardrobe(request.user).count(),
            'message': ' '.join(parts),
        })


class OutfitListAPIView(SessionAPIView):
    def get(self, request):
        outfits = Outfit.objects.filter(user=request.user).prefetch_related('items')
        return Response(OutfitSerializer(outfits, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = OutfitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(OutfitSerializer(serializer.save(), context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class OutfitDetailAPIView(SessionAPIView):
    def get_object(self, pk):
        try:
            return Outfit.objects.prefetch_related('items').get(pk=pk, user=self.request.user)
        except Outfit.DoesNotExist:
            raise NotFound('Outfit tidak ditemukan.')

    def get(self, request, pk):
        return Response(OutfitSerializer(self.get_object(pk), context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk, False)

    def patch(self, request, pk):
        return self._update(request, pk, True)

    def _update(self, request, pk, partial):
        serializer = OutfitSerializer(self.get_object(pk), data=request.data, partial=partial,
                                     context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(OutfitSerializer(serializer.save(), context={'request': request}).data)

    def delete(self, request, pk):
        outfit = self.get_object(pk)
        upcoming = outfit.schedules.filter(date__gt=timezone.localdate())
        upcoming.delete()
        outfit.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Function-based wrappers mengikuti pola Tutorial 07. Class API di atas tetap
# menjadi implementation layer agar aturan bisnis tidak diduplikasi.
@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def clothing_item_list(request):
    return ClothingItemListAPIView.as_view()(request._request)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def clothing_item_detail(request, pk):
    return ClothingItemDetailAPIView.as_view()(request._request, pk=pk)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def clothing_item_bulk_delete(request):
    return ClothingItemBulkDeleteAPIView.as_view()(request._request)


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def outfit_list(request):
    return OutfitListAPIView.as_view()(request._request)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def outfit_detail(request, pk):
    return OutfitDetailAPIView.as_view()(request._request, pk=pk)
