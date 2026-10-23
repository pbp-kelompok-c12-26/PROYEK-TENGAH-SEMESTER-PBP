from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from digital_wardrobe.models import ClothingItem
from home.models import LikedSwapItem

from .forms import ItemForSwapEditForm, ItemForSwapForm
from .models import ItemForSwap, get_photo_url


@login_required
def index(request):
    """Item Swap Saya: tab aktif / selesai, cari, urutkan."""
    tab = 'done' if request.GET.get('tab') == 'done' else 'active'
    q = request.GET.get('q', '').strip()
    sort = 'oldest' if request.GET.get('sort') == 'oldest' else 'newest'

    listings = ItemForSwap.objects.mine(request.user).annotate(
        is_liked=Exists(LikedSwapItem.objects.filter(user=request.user, listing_id=OuterRef('pk')))
    )
    listings = listings.swapped() if tab == 'done' else listings.available()
    if q:
        listings = listings.filter(clothing_item__name__icontains=q)
    listings = listings.order_by('posted_at' if sort == 'oldest' else '-posted_at')

    return render(request, 'items_for_swap/index.html', {
        'listings': listings, 'tab': tab, 'q': q, 'sort': sort,
    })


@login_required
def add(request, pk=None):
    """Create. Dengan pk = tombol "List for Swap" dari detail pakaian (baju sudah terpilih)."""
    initial = {}
    if pk is not None:
        item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
        if item.is_listed_for_swap:
            messages.info(request, 'Pakaian ini sudah ada di daftar swap.')
            return redirect('items_for_swap:index')
        initial['clothing_item'] = item.pk

    form = ItemForSwapForm(request.POST or None, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            ItemForSwap.list_item(
                clothing_item=form.cleaned_data['clothing_item'],
                user=request.user,
                meeting_location=form.cleaned_data['meeting_location'],
                reason=form.cleaned_data['reason'],
            )
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, 'Pakaian berhasil ditambahkan ke items for swap.')
            return redirect('items_for_swap:index')

    photo_map = {obj.pk: get_photo_url(obj) for obj in form.fields['clothing_item'].queryset}
    return render(request, 'items_for_swap/form.html', {
        'form': form, 'photo_map': photo_map, 'is_edit': False,
    })


@login_required
def edit(request, pk):
    """Update: hanya pemilik, hanya status available."""
    listing = get_object_or_404(ItemForSwap.objects.select_related('clothing_item'), pk=pk, user=request.user)
    if not listing.is_available:
        messages.error(request, 'Item yang sudah swapped tidak bisa diedit.')
        return redirect('items_for_swap:index')

    form = ItemForSwapEditForm(request.POST or None, instance=listing)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Perubahan disimpan.')
        return redirect('items_for_swap:index')

    return render(request, 'items_for_swap/form.html', {
        'form': form, 'listing': listing, 'is_edit': True,
    })


@login_required
@require_POST
def return_item(request, pk):
    """Delete = "Kembalikan ke wardrobe"."""
    listing = get_object_or_404(ItemForSwap.objects.select_related('clothing_item'), pk=pk, user=request.user)
    name = listing.clothing_item.name
    try:
        listing.return_to_wardrobe()
    except ValidationError as e:
        messages.error(request, ' '.join(e.messages))
    else:
        messages.success(request, f'"{name}" dikembalikan ke lemari.')
    return redirect('items_for_swap:index')


def detail(request, pk):
    listing = get_object_or_404(
        ItemForSwap.objects.select_related('clothing_item', 'user').annotate(like_count=Count('likes')),
        pk=pk,
    )
    is_authenticated = request.user.is_authenticated
    listing.is_liked = (
        LikedSwapItem.objects.filter(user=request.user, listing=listing).exists()
        if is_authenticated else False
    )
    is_owner = is_authenticated and listing.user_id == request.user.pk
    existing_request = None
    completed_participant = False
    has_related_request = False
    if not is_owner and is_authenticated:
        from swap_requests.models import SwapRequest
        if listing.is_available and listing.clothing_item.deleted_at is None and listing.clothing_item.is_listed_for_swap:
            existing_request = SwapRequest.objects.filter(
                requester=request.user,
                requested_item_id=listing.clothing_item_id,
                status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
                requester_hidden=False,
            ).order_by('-created_at').first()
        has_related_request = SwapRequest.objects.visible_to(request.user).filter(
            requested_item_id=listing.clothing_item_id,
        ).exists()

    can_browse_listing = (
        listing.is_available
        and listing.clothing_item.deleted_at is None
        and listing.clothing_item.is_listed_for_swap
    )
    if not is_owner and not can_browse_listing and not has_related_request and not listing.is_liked:
        raise Http404

    others = (ItemForSwap.objects.available().filter(user=listing.user)
              .exclude(pk=listing.pk).select_related('clothing_item'))
    if is_authenticated:
        others = others.annotate(is_liked=Exists(LikedSwapItem.objects.filter(
            user=request.user, listing_id=OuterRef('pk'),
        )))
    else:
        others = others.annotate(is_liked=Value(False, output_field=BooleanField()))
    others = others[:3]

    request_url = None
    if not is_owner and listing.is_available and not existing_request:
        request_url = f"{reverse('swap_requests:create')}?item={listing.clothing_item_id}"

    return render(request, 'items_for_swap/detail.html', {
        'listing': listing, 'item': listing.clothing_item,
        'is_owner': is_owner, 'others': others, 'request_url': request_url,
        'existing_request': existing_request,
    })
