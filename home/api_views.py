from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from items_for_swap.models import ItemForSwap

from .models import LikedSwapItem


class LikeToggleAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(ItemForSwap.objects.select_related('clothing_item'), pk=listing_id)
        liked = LikedSwapItem.objects.filter(user=request.user, listing=listing).first()
        if liked:
            liked.delete()
            is_liked = False
        elif (listing.user_id != request.user.pk and listing.is_available
              and listing.clothing_item.deleted_at is None
              and listing.clothing_item.is_listed_for_swap):
            LikedSwapItem.objects.get_or_create(user=request.user, listing=listing)
            is_liked = True
        else:
            is_liked = False
        return Response({
            'liked': is_liked,
            'like_count': LikedSwapItem.objects.filter(listing=listing).count(),
        })


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def like_toggle(request, listing_id):
    return LikeToggleAPIView.as_view()(request._request, listing_id=listing_id)
