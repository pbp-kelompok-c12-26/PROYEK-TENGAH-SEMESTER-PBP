from collections import Counter, OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap
from .forms import ConfirmForm, SwapRequestForm, offerable_items
from .models import SwapRequest

BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']

INCOMING_FILTERS = [('', 'Semua status'), (SwapRequest.PENDING, 'Pending'),
                    (SwapRequest.AWAITING, 'Awaiting exchange'), (SwapRequest.COMPLETED, 'Completed'),
                    (SwapRequest.REJECTED, 'Rejected')]
OUTGOING_FILTERS = [('', 'Semua status'), (SwapRequest.PENDING, 'Pending'), (SwapRequest.REJECTED, 'Rejected'),
                    (SwapRequest.AWAITING, 'Awaiting exchange'), (SwapRequest.COMPLETED, 'Completed')]
# urutan "status terpenting" untuk ringkasan per pakaian di Request masuk
STATUS_PRIORITY = [SwapRequest.COMPLETED, SwapRequest.AWAITING,
                   SwapRequest.PENDING, SwapRequest.REJECTED]


def format_tanggal(dt):
    return f'{dt.day} {BULAN[dt.month]} {dt.year}'


def _base_qs():
    return SwapRequest.objects.select_related('requester', 'owner', 'requested_item', 'offered_item')


def _get_for_user(request, pk):
    """Request hanya boleh dilihat oleh pengirim atau pemilik pakaian."""
    return get_object_or_404(_base_qs().visible_to(request.user), pk=pk)


# R: daftar request (tab Request masuk / Request kamu)
@login_required(login_url='accounts:login')
def index(request):
    SwapRequest.objects.sync_availability()
    SwapRequest.objects.mark_seen_by(request.user)
    tab = 'kamu' if request.GET.get('tab') == 'kamu' else 'masuk'
    filters = OUTGOING_FILTERS if tab == 'kamu' else INCOMING_FILTERS
    status = request.GET.get('status', '')
    if status not in dict(filters):
        status = ''

    groups, outgoing = [], []
    if tab == 'masuk':
        qs = _base_qs().filter(owner=request.user, owner_hidden=False)
        if status:
            qs = qs.filter(status=status)
        grouped = OrderedDict()
        for swap in qs:
            key = swap.requested_item_id or f'deleted-{swap.requested_item_name}'
            grouped.setdefault(key, []).append(swap)
        for swaps in grouped.values():
            counts = Counter(s.status for s in swaps)
            if counts[SwapRequest.COMPLETED]:
                top = SwapRequest.COMPLETED
            elif counts[SwapRequest.AWAITING]:
                top = SwapRequest.AWAITING
            elif counts[SwapRequest.PENDING]:
                top = SwapRequest.PENDING
            else:
                top = SwapRequest.REJECTED
            groups.append({
                'item': swaps[0].requested_item,
                'name': swaps[0].requested_item_name,
                'total': len(swaps),
                'summary': ' · '.join(f'{counts[s]} {dict(SwapRequest.STATUS_CHOICES)[s].lower()}'
                                      for s in STATUS_PRIORITY if counts[s]),
                'top_status': top,
                'top_label': dict(SwapRequest.STATUS_CHOICES)[top],
                'top_style': SwapRequest.STATUS_STYLES[top],
            })
    else:
        qs = _base_qs().filter(requester=request.user, requester_hidden=False)
        if status:
            qs = qs.filter(status=status)
        outgoing = list(qs)
        for s in outgoing:
            s.tanggal = format_tanggal(s.created_at)

    return render(request, 'swap_requests/index.html', {
        'tab': tab, 'status': status, 'filters': filters,
        'groups': groups, 'outgoing': outgoing,
    })


# R: semua request untuk satu pakaian milikku
@login_required(login_url='accounts:login')
def item_requests(request, item_id):
    SwapRequest.objects.sync_availability()
    request_qs = _base_qs().filter(owner=request.user, owner_hidden=False, requested_item_id=item_id)
    request_qs.mark_seen_by(request.user)
    swaps = list(request_qs)
    item = get_object_or_404(ClothingItem, pk=item_id) if not swaps else swaps[0].requested_item
    if item.user_id != request.user.pk and not swaps:
        return redirect('swap_requests:index')
    for s in swaps:
        s.tanggal = format_tanggal(s.created_at)
    accepted = [s for s in swaps if s.status in (SwapRequest.AWAITING, SwapRequest.COMPLETED)]
    others = [s for s in swaps if s not in accepted]
    return render(request, 'swap_requests/item_requests.html', {
        'item': item, 'accepted': accepted, 'others': others,
    })


# C: ajukan swap untuk pakaian orang lain (?item=<id pakaian>)
@login_required(login_url='accounts:login')
def create(request):
    item_id = request.GET.get('item', '')
    requested_item = None
    if item_id.isdigit():
        existing = SwapRequest.objects.filter(
            requester=request.user,
            requested_item_id=item_id,
            status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
            requester_hidden=False,
        ).order_by('-created_at').first()
        if existing:
            messages.info(request, 'Kamu sudah memiliki request aktif untuk pakaian ini. Lanjutkan dari detail request tersebut.')
            return redirect('swap_requests:detail', pk=existing.pk)
        # `item` is the ClothingItem ID used by the catalogue card and listing detail.
        listing = (ItemForSwap.objects.available()
                   .filter(clothing_item_id=item_id,
                           clothing_item__deleted_at__isnull=True,
                           clothing_item__is_listed_for_swap=True)
                   .select_related('clothing_item__user').first())
        requested_item = listing.clothing_item if listing else None
    if requested_item is None:
        messages.error(request, 'Pakaian yang ingin kamu tukar tidak ditemukan atau sudah tidak tersedia.')
        return redirect('swap_requests:index')
    if requested_item.user_id == request.user.pk:
        messages.error(request, 'Itu pakaianmu sendiri.')
        return redirect('swap_requests:index')
    if SwapRequest.objects.is_locked(requested_item):
        messages.error(request, 'Pakaian ini sedang dalam proses tukar dengan orang lain. Coba lagi nanti.')
        return redirect('swap_requests:index')

    form = SwapRequestForm(request.POST or None, user=request.user, requested_item=requested_item)
    if request.method == 'POST' and form.is_valid():
        # Pemeriksaan ulang saat POST agar request aktif tidak terduplikasi.
        existing = SwapRequest.objects.filter(
            requester=request.user,
            requested_item=requested_item,
            status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
            requester_hidden=False,
        ).order_by('-created_at').first()
        if existing:
            messages.info(request, 'Kamu sudah memiliki request aktif untuk pakaian ini. Lanjutkan dari detail request tersebut.')
            return redirect('swap_requests:detail', pk=existing.pk)
        swap = form.save()
        return redirect('swap_requests:sent', pk=swap.pk)
    return render(request, 'swap_requests/form.html', {
        'form': form, 'requested_item': requested_item, 'title': 'Tambahkan pakaian untuk ditukar',
        'submit_label': 'Tambahkan request', 'offer_items': form.fields['offered_item'].queryset,
        'has_offerable': offerable_items(request.user).exists(),
    })


@login_required(login_url='accounts:login')
def sent(request, pk):
    swap = get_object_or_404(_base_qs(), pk=pk, requester=request.user, requester_hidden=False)
    return render(request, 'swap_requests/sent.html', {'swap': swap, 'tanggal': format_tanggal(swap.created_at)})


# R: detail (tampilan beda untuk pengirim & pemilik pakaian)
@login_required(login_url='accounts:login')
def detail(request, pk):
    SwapRequest.objects.sync_availability()
    swap = _get_for_user(request, pk)
    swap.mark_seen_by(request.user)
    role = swap.role_of(request.user)
    me_requester = role == 'requester'
    show_confirmations = (
        swap.status in (SwapRequest.AWAITING, SwapRequest.COMPLETED)
        or (swap.status == SwapRequest.REJECTED
            and bool(swap.requester_confirmation or swap.owner_confirmation))
    )
    requested_listing = ItemForSwap.objects.filter(
        clothing_item_id=swap.requested_item_id,
        user=swap.owner,
    ).order_by('-posted_at').first() if swap.requested_item_id else None
    return render(request, 'swap_requests/detail.html', {
        'swap': swap,
        'role': role,
        'other': swap.other_party(request.user),
        'tanggal': format_tanggal(swap.created_at),
        # kiri: pakaian yang kamu dapat, kanan: pakaian yang kamu berikan
        'get_item': swap.requested_item if me_requester else swap.offered_item,
        'get_name': swap.requested_item_name if me_requester else swap.offered_item_name,
        'give_item': swap.offered_item if me_requester else swap.requested_item,
        'give_name': swap.offered_item_name if me_requester else swap.requested_item_name,
        'my_confirmation': swap.requester_confirmation if me_requester else swap.owner_confirmation,
        'other_confirmation': swap.owner_confirmation if me_requester else swap.requester_confirmation,
        'confirm_choices': SwapRequest.CONFIRM_CHOICES,
        'show_confirmations': show_confirmations,
        'can_edit': swap.can_edit(request.user),
        'can_respond': swap.can_respond(request.user),
        'requested_listing': requested_listing,
    })


# U: edit request (hanya pengirim, selama Pending)
@login_required(login_url='accounts:login')
def update(request, pk):
    swap = _get_for_user(request, pk)
    if not swap.can_edit(request.user):
        messages.error(request, 'Request ini sudah tidak bisa diedit.')
        return redirect('swap_requests:detail', pk=pk)
    form = SwapRequestForm(request.POST or None, instance=swap, user=request.user, requested_item=swap.requested_item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Swap request diperbarui.')
        return redirect('swap_requests:detail', pk=pk)
    return render(request, 'swap_requests/form.html', {
        'form': form, 'requested_item': swap.requested_item, 'swap': swap, 'title': 'Edit swap request kamu',
        'submit_label': 'Simpan perubahan', 'offer_items': form.fields['offered_item'].queryset, 'has_offerable': True,
    })


# U: pemilik pakaian menyetujui / menolak
@login_required(login_url='accounts:login')
@require_POST
def respond(request, pk):
    swap = _get_for_user(request, pk)
    if not swap.can_respond(request.user):
        messages.error(request, 'Request ini sudah tidak bisa direspons.')
    elif request.POST.get('action') == 'accept':
        try:
            swap.accept()
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        else:
            messages.success(request, 'Swap disetujui. Hubungi pengirim untuk mengatur pertukaran.')
    elif request.POST.get('action') == 'reject':
        swap.reject(actor=request.user)
        messages.success(request, 'Swap request ditolak.')
    return redirect('swap_requests:detail', pk=pk)


# U: konfirmasi penyelesaian (Selesai / Batalkan) oleh masing-masing pihak
@login_required(login_url='accounts:login')
@require_POST
def confirm(request, pk):
    swap = _get_for_user(request, pk)
    form = ConfirmForm(request.POST)
    if swap.status != SwapRequest.AWAITING or not form.is_valid():
        messages.error(request, 'Konfirmasi tidak bisa disimpan.')
    else:
        swap.confirm(request.user, form.cleaned_data['choice'])
        if swap.status == SwapRequest.COMPLETED:
            messages.success(request, 'Pertukaran selesai! Pakaian barumu sudah masuk ke Lemari Saya.')
        elif swap.status == SwapRequest.REJECTED:
            messages.success(request, 'Pertukaran dibatalkan. Request lain untuk pakaian ini tetap bisa diproses.')
        else:
            messages.success(request, 'Pilihan tersimpan. Menunggu pihak lain memilih Selesai swap.')
    return redirect('swap_requests:detail', pk=pk)


# D: hapus request (tidak bisa saat Awaiting exchange)
@login_required(login_url='accounts:login')
@require_POST
def delete(request, pk):
    swap = _get_for_user(request, pk)
    if not swap.can_delete:
        messages.error(request, 'Request yang sedang menunggu pertukaran tidak bisa dihapus.')
        return redirect('swap_requests:detail', pk=pk)
    role = swap.role_of(request.user)
    tab = 'kamu' if role == 'requester' else 'masuk'
    if swap.status == SwapRequest.PENDING and role == 'requester':
        swap.delete()  # Pengirim membatalkan ajuan: hilang dari kedua pihak.
    elif swap.status == SwapRequest.PENDING and role == 'owner':
        swap.status = SwapRequest.REJECTED
        swap.owner_hidden = True
        swap.responded_at = timezone.now()
        swap.record_status_change(actor=request.user)
        swap.save(update_fields=['status', 'owner_hidden', 'responded_at', 'updated_at'])
    elif role == 'requester':
        swap.requester_hidden = True
        swap.save(update_fields=['requester_hidden', 'updated_at'])
    else:
        swap.owner_hidden = True
        swap.save(update_fields=['owner_hidden', 'updated_at'])
    messages.success(request, 'Swap request dihapus dari daftar kamu.')
    return redirect(f"{reverse('swap_requests:index')}?tab={tab}")
