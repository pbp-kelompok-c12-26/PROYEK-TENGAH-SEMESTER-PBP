from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SwapRequest
from .serializers import SwapRequestCreateSerializer, SwapRequestSerializer, SwapRequestUpdateSerializer
from .views import _delete_swap_for_party


class SwapRequestAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return (SwapRequest.objects.select_related('requester', 'owner', 'requested_item', 'offered_item')
                    .visible_to(self.request.user).get(pk=pk))
        except SwapRequest.DoesNotExist:
            raise NotFound('Swap request tidak ditemukan.')


class SwapRequestListAPIView(SwapRequestAPIView):
    def get(self, request):
        SwapRequest.objects.sync_availability()
        swaps = (SwapRequest.objects.select_related('requester', 'owner', 'requested_item', 'offered_item')
                 .visible_to(request.user))
        return Response(SwapRequestSerializer(swaps, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = SwapRequestCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        swap = serializer.save()
        return Response(SwapRequestSerializer(swap, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class SwapRequestDetailAPIView(SwapRequestAPIView):
    def get(self, request, pk):
        SwapRequest.objects.sync_availability()
        swap = self.get_object(pk)
        swap.mark_seen_by(request.user)
        return Response(SwapRequestSerializer(swap, context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk, False)

    def patch(self, request, pk):
        return self._update(request, pk, True)

    def _update(self, request, pk, partial):
        swap = self.get_object(pk)
        if not swap.can_edit(request.user):
            raise PermissionDenied('Hanya pengirim yang dapat mengubah request Pending.')
        serializer = SwapRequestUpdateSerializer(swap, data=request.data, partial=partial,
                                                 context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(SwapRequestSerializer(serializer.save(), context={'request': request}).data)

    def delete(self, request, pk):
        swap = self.get_object(pk)
        if not swap.can_delete:
            return Response({'detail': 'Request yang menunggu pertukaran tidak bisa dihapus.'}, status=409)
        _delete_swap_for_party(swap, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SwapRequestRespondAPIView(SwapRequestAPIView):
    def post(self, request, pk):
        swap = self.get_object(pk)
        if not swap.can_respond(request.user):
            raise PermissionDenied('Hanya pemilik pakaian yang dapat merespons request Pending.')
        action = request.data.get('action')
        if action == 'accept':
            try:
                swap.accept()
            except DjangoValidationError as error:
                return Response({'detail': ' '.join(error.messages)}, status=409)
        elif action == 'reject':
            swap.reject(actor=request.user)
        else:
            raise ValidationError({'action': 'Pilih accept atau reject.'})
        return Response(SwapRequestSerializer(swap, context={'request': request}).data)


class SwapRequestConfirmAPIView(SwapRequestAPIView):
    def post(self, request, pk):
        swap = self.get_object(pk)
        choice = request.data.get('choice')
        if swap.status != SwapRequest.AWAITING:
            return Response({'detail': 'Konfirmasi hanya tersedia untuk swap yang menunggu pertukaran.'}, status=409)
        if choice not in dict(SwapRequest.CONFIRM_CHOICES):
            raise ValidationError({'choice': 'Pilih done atau cancel.'})
        swap.confirm(request.user, choice)
        return Response(SwapRequestSerializer(swap, context={'request': request}).data)


class SwapRequestBulkDeleteAPIView(SwapRequestAPIView):
    def post(self, request):
        values = request.data.getlist('swap_ids') if hasattr(request.data, 'getlist') else request.data.get('swap_ids', [])
        if not isinstance(values, list):
            values = [values]
        ids = {int(value) for value in values if str(value).isdigit()}
        swaps = list(SwapRequest.objects.visible_to(request.user).filter(pk__in=ids)
                     .exclude(status=SwapRequest.AWAITING).select_for_update())
        processed = 0
        with transaction.atomic():
            for swap in swaps:
                if _delete_swap_for_party(swap, request.user):
                    processed += 1
        return Response({'ok': True, 'processed': processed})


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def swap_request_list(request):
    return SwapRequestListAPIView.as_view()(request._request)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def swap_request_detail(request, pk):
    return SwapRequestDetailAPIView.as_view()(request._request, pk=pk)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def swap_request_respond(request, pk):
    return SwapRequestRespondAPIView.as_view()(request._request, pk=pk)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def swap_request_confirm(request, pk):
    return SwapRequestConfirmAPIView.as_view()(request._request, pk=pk)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def swap_request_bulk_delete(request):
    return SwapRequestBulkDeleteAPIView.as_view()(request._request)
