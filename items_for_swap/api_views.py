from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ItemForSwap
from .serializers import ItemForSwapSerializer


def is_publicly_available(listing):
    item = listing.clothing_item
    return listing.is_available and item.deleted_at is None and item.is_listed_for_swap


class ListingListAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        listings = ItemForSwap.objects.available().select_related('clothing_item', 'user').filter(
            clothing_item__deleted_at__isnull=True, clothing_item__is_listed_for_swap=True,
        )
        if request.user.is_authenticated:
            listings = listings.exclude(user=request.user)
        return Response(ItemForSwapSerializer(listings, many=True, context={'request': request}).data)

    def post(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied('Login diperlukan untuk menawarkan pakaian.')
        serializer = ItemForSwapSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            listing = serializer.save()
        except DjangoValidationError as error:
            return Response({'detail': ' '.join(error.messages)}, status=409)
        return Response(ItemForSwapSerializer(listing, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class MyListingListAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        listings = ItemForSwap.objects.mine(request.user)
        return Response(ItemForSwapSerializer(listings, many=True, context={'request': request}).data)


class ListingDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get_object(self, pk, for_write=False):
        try:
            listing = ItemForSwap.objects.select_related('clothing_item', 'user').get(pk=pk)
        except ItemForSwap.DoesNotExist:
            raise NotFound('Item swap tidak ditemukan.')
        if for_write:
            if not self.request.user.is_authenticated:
                raise PermissionDenied('Login diperlukan.')
            if listing.user_id != self.request.user.id:
                raise PermissionDenied('Kamu tidak punya akses ke item swap ini.')
        elif not is_publicly_available(listing) and (
            not self.request.user.is_authenticated or listing.user_id != self.request.user.id
        ):
            raise NotFound('Item swap tidak ditemukan.')
        return listing

    def get(self, request, pk):
        return Response(ItemForSwapSerializer(self.get_object(pk), context={'request': request}).data)

    def put(self, request, pk):
        return self._update(request, pk, False)

    def patch(self, request, pk):
        return self._update(request, pk, True)

    def _update(self, request, pk, partial):
        listing = self.get_object(pk, for_write=True)
        if 'clothing_item_id' in request.data:
            return Response({'clothing_item_id': ['Pakaian pada listing tidak dapat diganti.']}, status=400)
        serializer = ItemForSwapSerializer(listing, data=request.data, partial=partial,
                                           context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            listing = serializer.save()
        except DjangoValidationError as error:
            return Response({'detail': ' '.join(error.messages)}, status=409)
        return Response(ItemForSwapSerializer(listing, context={'request': request}).data)

    def delete(self, request, pk):
        listing = self.get_object(pk, for_write=True)
        try:
            listing.return_to_wardrobe()
        except DjangoValidationError as error:
            return Response({'detail': ' '.join(error.messages)}, status=409)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET', 'POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def listing_list(request):
    return ListingListAPIView.as_view()(request._request)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def my_listing_list(request):
    return MyListingListAPIView.as_view()(request._request)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def listing_detail(request, pk):
    return ListingDetailAPIView.as_view()(request._request, pk=pk)
