from django.db.models import Q

from .models import SwapRequestNotification


def swap_request_unread_count(request):
    """Jumlah perubahan status yang belum dilihat pengguna."""
    if not request.user.is_authenticated:
        return {'swap_request_unread_count': 0}

    unread = SwapRequestNotification.objects.filter(
        Q(swap_request__requester=request.user, swap_request__requester_hidden=False)
        | Q(swap_request__owner=request.user, swap_request__owner_hidden=False),
        recipient=request.user,
        read_at__isnull=True,
    )
    return {'swap_request_unread_count': unread.count()}
