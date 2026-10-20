from collections import Counter, OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from digital_wardrobe.models import ClothingItem
from .forms import ConfirmForm, SwapRequestForm, offerable_items
from .models import SwapRequest

BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']

INCOMING_FILTERS = [('', 'Semua status'), (SwapRequest.PENDING, 'Pending'),
                    (SwapRequest.AWAITING, 'Awaiting exchange'), (SwapRequest.COMPLETED, 'Completed')]
OUTGOING_FILTERS = [('', 'Semua status'), (SwapRequest.PENDING, 'Pending'), (SwapRequest.REJECTED, 'Rejected'),
                    (SwapRequest.AWAITING, 'Awaiting exchange'), (SwapRequest.COMPLETED, 'Completed'),
                    (SwapRequest.UNAVAILABLE, 'Item not available')]
# urutan "status terpenting" untuk ringkasan per pakaian di Request masuk
STATUS_PRIORITY = [SwapRequest.AWAITING, SwapRequest.PENDING, SwapRequest.COMPLETED,
                   SwapRequest.REJECTED, SwapRequest.CANCELLED, SwapRequest.UNAVAILABLE]


def format_tanggal(dt):
    return f'{dt.day} {BULAN[dt.month]} {dt.year}'


def _base_qs():
    return SwapRequest.objects.select_related('requester', 'owner', 'requested_item', 'offered_item')


def _get_for_user(request, pk):
    """Request hanya boleh dilihat oleh pengirim atau pemilik pakaian."""
    return get_object_or_404(_base_qs().filter(Q(requester=request.user) | Q(owner=request.user)), pk=pk)


# R: daftar request (tab Request masuk / Request kamu)
@login_required(login_url='accounts:login')
def index(request):
    SwapRequest.objects.sync_availability()
    tab = 'kamu' if request.GET.get('tab') == 'kamu' else 'masuk'
    filters = OUTGOING_FILTERS if tab == 'kamu' else INCOMING_FILTERS
    status = request.GET.get('status', '')
    if status not in dict(filters):
        status = ''

    groups, outgoing = [], []
    if tab == 'masuk':
        qs = _base_qs().filter(owner=request.user)
        if status:
            qs = qs.filter(status=status)
        grouped = OrderedDict()
        for swap in qs:
            key = swap.requested_item_id or f'deleted-{swap.requested_item_name}'
            grouped.setdefault(key, []).append(swap)
        for swaps in grouped.values():
            counts = Counter(s.status for s in swaps)
            top = next(s for s in STATUS_PRIORITY if counts[s])
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
        qs = _base_qs().filter(requester=request.user)
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
    swaps = list(_base_qs().filter(owner=request.user, requested_item_id=item_id))
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
        requested_item = ClothingItem.objects.filter(pk=item_id, is_listed_for_swap=True).select_related('user').first()
    if requested_item is None:
        messages.error(request, 'Pakaian yang ingin kamu tukar tidak ditemukan atau sudah tidak tersedia.')
        return redirect('swap_requests:index')
    if requested_item.user_id == request.user.pk:
        messages.error(request, 'Itu pakaianmu sendiri.')
        return redirect('swap_requests:index')

    form = SwapRequestForm(request.POST or None, user=request.user, requested_item=requested_item)
    if request.method == 'POST' and form.is_valid():
        swap = form.save()
        return redirect('swap_requests:sent', pk=swap.pk)
    return render(request, 'swap_requests/form.html', {
        'form': form, 'requested_item': requested_item, 'title': 'Tambahkan pakaian untuk ditukar',
        'submit_label': 'Tambahkan request', 'offer_items': form.fields['offered_item'].queryset,
        'has_offerable': offerable_items(request.user).exists(),
    })


@login_required(login_url='accounts:login')
def sent(request, pk):
    swap = get_object_or_404(_base_qs(), pk=pk, requester=request.user)
    return render(request, 'swap_requests/sent.html', {'swap': swap, 'tanggal': format_tanggal(swap.created_at)})


# R: detail (tampilan beda untuk pengirim & pemilik pakaian)
@login_required(login_url='accounts:login')
def detail(request, pk):
    SwapRequest.objects.sync_availability()
    swap = _get_for_user(request, pk)
    role = swap.role_of(request.user)
    me_requester = role == 'requester'
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
        'can_edit': swap.can_edit(request.user),
        'can_respond': swap.can_respond(request.user),
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
        swap.accept()
        messages.success(request, 'Swap disetujui. Hubungi pengirim untuk mengatur pertukaran.')
    elif request.POST.get('action') == 'reject':
        swap.reject()
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
        elif swap.status == SwapRequest.CANCELLED:
            messages.success(request, 'Pertukaran dibatalkan. Pakaian kembali tersedia untuk ditukar.')
        else:
            messages.success(request, 'Konfirmasi tersimpan. Menunggu konfirmasi dari pihak lain.')
    return redirect('swap_requests:detail', pk=pk)


# D: hapus request (tidak bisa saat Awaiting exchange)
@login_required(login_url='accounts:login')
@require_POST
def delete(request, pk):
    swap = _get_for_user(request, pk)
    if not swap.can_delete:
        messages.error(request, 'Request yang sedang menunggu pertukaran tidak bisa dihapus.')
        return redirect('swap_requests:detail', pk=pk)
    tab = 'kamu' if swap.role_of(request.user) == 'requester' else 'masuk'
    swap.delete()
    messages.success(request, 'Swap request dihapus.')
    return redirect(f"{reverse('swap_requests:index')}?tab={tab}")
