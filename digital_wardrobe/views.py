from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Exists, OuterRef, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClothingItemForm, OutfitForm
from .models import ClothingItem, Outfit

PAGE_SIZE = 12
BULK_DELETE_LIMIT = 50  # maksimal pakaian per sekali hapus banyak

SORT_OPTIONS = {
    'newest': ('-created_at', 'Terbaru'),
    'oldest': ('created_at', 'Terlama'),
    'name': ('name', 'Nama A–Z'),
}

BULAN = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli',
         'Agustus', 'September', 'Oktober', 'November', 'Desember']


def format_tanggal(value):
    """Format tanggal ke bahasa Indonesia, mis. '15 Oktober 2026'."""
    if not value:
        return ''
    if hasattr(value, 'astimezone'):
        value = timezone.localtime(value)
    return f'{value.day} {BULAN[value.month - 1]} {value.year}'


def is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _auto_open_url(request):
    """
    Modal yang dibuka otomatis lewat query string (fallback tanpa JS / dari halaman lain):
    ?add=1, ?edit=<id>, ?add_outfit=1 (opsional &item=<id>), ?edit_outfit=<id>
    """
    if request.GET.get('add') == '1':
        return reverse('digital_wardrobe:item_create')
    edit_pk = request.GET.get('edit', '')
    if edit_pk.isdigit() and ClothingItem.objects.in_wardrobe(request.user).filter(pk=edit_pk).exists():
        return reverse('digital_wardrobe:item_update', args=[int(edit_pk)])
    if request.GET.get('add_outfit') == '1':
        url = reverse('digital_wardrobe:outfit_create')
        item_pk = request.GET.get('item', '')
        return f'{url}?item={item_pk}' if item_pk.isdigit() else url
    outfit_pk = request.GET.get('edit_outfit', '')
    if outfit_pk.isdigit() and Outfit.objects.filter(pk=outfit_pk, user=request.user).exists():
        return reverse('digital_wardrobe:outfit_update', args=[int(outfit_pk)])
    return ''


# R -> Read: halaman Lemari Digital (daftar pakaian + filter)
@login_required
def index(request):
    ClothingItem.objects.refresh_idle(request.user)  # is_idle selalu terbaru tiap lemari dibuka
    user_items = ClothingItem.objects.in_wardrobe(request.user)

    tab = request.GET.get('tab', 'pakaian')
    show = request.GET.get('show', 'all')
    category = request.GET.get('category', '')
    query = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'newest')
    if sort not in SORT_OPTIONS:
        sort = 'newest'
    try:
        limit = max(PAGE_SIZE, int(request.GET.get('limit', PAGE_SIZE)))
    except ValueError:
        limit = PAGE_SIZE

    items = user_items
    if show == 'idle':
        items = items.filter(is_idle=True)
    if category in dict(ClothingItem.CATEGORY_CHOICES):
        items = items.filter(category=category)
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    from swap_requests.models import SwapRequest
    active_requests = SwapRequest.objects.filter(
        status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
    ).filter(Q(requested_item_id=OuterRef('pk')) | Q(offered_item_id=OuterRef('pk')))
    items = items.annotate(
        outfit_total=Count('outfits'),
        swap_request_locked=Exists(active_requests),
    ).order_by(SORT_OPTIONS[sort][0])

    filtered_total = items.count()
    params = request.GET.copy()
    params['limit'] = limit + PAGE_SIZE

    outfits = []
    if tab == 'outfit':
        today = timezone.localdate()
        outfits = [with_tiles(o) for o in Outfit.objects.filter(user=request.user).prefetch_related('items').annotate(
            upcoming_total=Count('schedules', filter=Q(schedules__date__gt=today), distinct=True),
            history_total=Count('schedules', filter=Q(schedules__date__lte=today), distinct=True),
        )]

    context = {
        'tab': tab,
        'outfits': outfits,
        'show': show,
        'category': category,
        'query': query,
        'sort': sort,
        'items': items[:limit],
        'filtered_total': filtered_total,
        'shown_count': min(limit, filtered_total),
        'has_more': filtered_total > limit,
        'more_url': f'?{params.urlencode()}',
        'is_filtered': bool(query or category or show == 'idle'),
        'category_choices': ClothingItem.CATEGORY_CHOICES,
        'sort_choices': [(key, label) for key, (_, label) in SORT_OPTIONS.items()],
        'total_items': user_items.count(),
        'total_outfits': Outfit.objects.filter(user=request.user).count(),
        'total_for_swap': ClothingItem.objects.listed_for_swap(request.user).count(),
        'auto_open_url': _auto_open_url(request),
    }
    return render(request, 'digital_wardrobe/index.html', context)


LISTED_MESSAGE = '"{name}" sedang ditawarkan di Items for Swap. Kelola dari Item Swap Saya, atau kembalikan dulu ke lemari.'


def _listed_response(request, item):
    """Pakaian yang sedang ditawarkan tidak dikelola dari wardrobe."""
    message = LISTED_MESSAGE.format(name=item.name)
    if is_ajax(request):
        return JsonResponse({'ok': False, 'message': message}, status=409)
    messages.info(request, message)
    return redirect('digital_wardrobe:index')


# Alamat lama daftar pakaian diarahkan ke halaman Lemari Digital
@login_required
def item_list(request):
    return redirect('digital_wardrobe:index')


# R -> Read: detail 1 pakaian
@login_required
def item_detail(request, pk):
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
    if item.is_deleted:
        messages.info(request, f'"{item.name}" sudah dihapus dari lemarimu.')
        return redirect('digital_wardrobe:index')
    if item.is_listed_for_swap:
        return _listed_response(request, item)
    from swap_requests.models import SwapRequest
    return render(request, 'digital_wardrobe/item_detail.html', {
        'item': item,
        'swap_request_locked': SwapRequest.objects.has_active_request(item),
        'added_label': format_tanggal(item.created_at),
        'last_worn_label': format_tanggal(item.last_worn_date),
        'outfit_count': item.outfits.count(),
        'item_outfits': item.outfits.all()[:6],
    })


def _form_modal(request, form, item=None):
    return render_to_string('digital_wardrobe/partials/item_form_modal.html', {
        'form': form,
        'item': item,
        'action_url': reverse('digital_wardrobe:item_update', args=[item.pk]) if item
        else reverse('digital_wardrobe:item_create'),
    }, request=request)


def _card(request, item):
    item.outfit_total = item.outfits.count()
    from swap_requests.models import SwapRequest
    item.swap_request_locked = SwapRequest.objects.has_active_request(item)
    return render_to_string('digital_wardrobe/partials/item_card.html', {'item': item}, request=request)


# C -> Create: menambahkan pakaian baru (modal, tanpa reload)
@login_required
def item_create(request):
    if request.method == 'POST':
        form = ClothingItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            if is_ajax(request):
                return JsonResponse({
                    'ok': True,
                    'card_html': _card(request, item),
                    'total_items': ClothingItem.objects.in_wardrobe(request.user).count(),
                    'message': f'"{item.name}" masuk ke lemarimu.',
                })
            messages.success(request, f'"{item.name}" masuk ke lemarimu.')
            return redirect('digital_wardrobe:index')
        if is_ajax(request):
            return JsonResponse({'ok': False, 'modal_html': _form_modal(request, form)}, status=400)
        return redirect(f"{reverse('digital_wardrobe:index')}?add=1")

    if is_ajax(request):
        return JsonResponse({'ok': True, 'modal_html': _form_modal(request, ClothingItemForm())})
    return redirect(f"{reverse('digital_wardrobe:index')}?add=1")


# U -> Update: mengubah informasi pakaian (modal)
@login_required
def item_update(request, pk):
    item = get_object_or_404(ClothingItem.objects.active(), pk=pk, user=request.user)
    if item.is_listed_for_swap:
        return _listed_response(request, item)
    from swap_requests.models import SwapRequest
    if SwapRequest.objects.has_active_request(item):
        message = (f'"{item.name}" sedang dipakai dalam swap request, jadi belum bisa diedit. '
                   'Batalkan request terlebih dahulu.')
        if is_ajax(request):
            return JsonResponse({'ok': False, 'message': message}, status=409)
        messages.error(request, message)
        return redirect('digital_wardrobe:item_detail', pk=item.pk)
    if request.method == 'POST':
        form = ClothingItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            item = form.save()
            if is_ajax(request):
                return JsonResponse({
                    'ok': True,
                    'pk': item.pk,
                    'card_html': _card(request, item),
                    'message': 'Perubahan tersimpan.',
                })
            messages.success(request, 'Perubahan tersimpan.')
            return redirect('digital_wardrobe:item_detail', pk=item.pk)
        if is_ajax(request):
            return JsonResponse({'ok': False, 'modal_html': _form_modal(request, form, item)}, status=400)
        return redirect(f"{reverse('digital_wardrobe:index')}?edit={item.pk}")

    if is_ajax(request):
        return JsonResponse({'ok': True, 'modal_html': _form_modal(request, ClothingItemForm(instance=item), item)})
    return redirect(f"{reverse('digital_wardrobe:index')}?edit={item.pk}")


# D -> Delete: menghapus pakaian dari wardrobe
@login_required
@require_POST
def item_delete(request, pk):
    item = get_object_or_404(ClothingItem.objects.active(), pk=pk, user=request.user)

    # Cegah data yatim di modul Items for Swap / Swap Request (panduan §2.3)
    if item.is_listed_for_swap:
        messages.error(request, LISTED_MESSAGE.format(name=item.name))
        return redirect('digital_wardrobe:index')
    from swap_requests.models import SwapRequest
    if SwapRequest.objects.has_active_request(item):
        messages.error(request, f'"{item.name}" sedang dipakai dalam swap request. Batalkan request terlebih dahulu sebelum menghapusnya.')
        return redirect('digital_wardrobe:item_detail', pk=item.pk)

    name = item.name
    try:
        result = item.remove_from_wardrobe()
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        return redirect('digital_wardrobe:item_detail', pk=item.pk)
    if result == 'archived':
        messages.success(request, f'"{name}" sudah dihapus dari lemarimu. '
                                  'Di outfit & Kalender Outfit, pakaian ini tetap tampil dengan status "Sudah dihapus dari lemari".')
    else:
        messages.success(request, f'"{name}" sudah dihapus dari lemarimu.')
    return redirect('digital_wardrobe:index')


# D -> Delete banyak sekaligus (bulk delete) dari mode "Pilih" di Lemari Saya
@login_required
@require_POST
def item_bulk_delete(request):
    ids = {int(value) for value in request.POST.getlist('items') if value.isdigit()}
    if not ids:
        error = 'Pilih minimal 1 pakaian yang ingin dihapus.'
    elif len(ids) > BULK_DELETE_LIMIT:
        error = f'Maksimal {BULK_DELETE_LIMIT} pakaian sekali hapus.'
    else:
        error = ''
    if error:
        if is_ajax(request):
            return JsonResponse({'ok': False, 'message': error}, status=400)
        messages.error(request, error)
        return redirect('digital_wardrobe:index')

    result = ClothingItem.objects.remove_many(request.user, ids)
    removed = result['archived'] + result['deleted']
    parts = [f'{len(removed)} pakaian dihapus dari lemarimu.' if removed else 'Tidak ada pakaian yang dihapus.']
    if result['skipped']:
        names = ', '.join(f'"{item.name}"' for item in result['skipped'])
        parts.append(f'{len(result["skipped"])} dilewati karena sedang dipakai dalam swap request: {names}.')
    if result['not_found']:
        parts.append(f'{result["not_found"]} pakaian tidak ditemukan di lemarimu.')
    message = ' '.join(parts)

    if is_ajax(request):
        return JsonResponse({
            'ok': True,
            'removed': [item.pk for item in removed],
            'skipped': [item.pk for item in result['skipped']],
            'total_items': ClothingItem.objects.in_wardrobe(request.user).count(),
            'message': message,
        })
    (messages.success if removed else messages.info)(request, message)
    return redirect('digital_wardrobe:index')


# ======================================================================
# KOLEKSI OUTFIT
# ======================================================================

def outfit_items_for(outfit):
    """Pakaian di outfit, ditandai pemilik outfit-nya supaya status swap terbaca benar."""
    return [item.seen_by(outfit.user_id) for item in outfit.items.all()]


def schedule_counts(outfit):
    """(jadwal mendatang, riwayat jadwal) outfit ini di Kalender Outfit."""
    if hasattr(outfit, 'upcoming_total'):
        return outfit.upcoming_total, outfit.history_total
    today = timezone.localdate()
    schedules = outfit.schedules.all()
    return schedules.filter(date__gt=today).count(), schedules.filter(date__lte=today).count()


def with_tiles(outfit):
    """Tambahkan atribut `tiles` (maks. 5 pakaian) untuk kolase kartu outfit.
    Susunan kolase diatur CSS lewat class .wd-collage--<jumlah pakaian>."""
    items = outfit_items_for(outfit)[:Outfit.MAX_ITEMS]
    outfit.tiles = [{'item': item} for item in items]
    outfit.item_total = len(items)
    outfit.unavailable_total = sum(1 for item in items if item.is_swapped_away)
    outfit.listed_total = sum(1 for item in items
                              if item.is_listed_for_swap and not item.is_deleted and not item.is_swapped_away)
    outfit.deleted_total = sum(1 for item in items if item.is_deleted and not item.is_swapped_away)
    outfit.upcoming_total, outfit.history_total = schedule_counts(outfit)
    return outfit


def _outfit_card(request, outfit):
    return render_to_string('digital_wardrobe/partials/outfit_card.html',
                            {'outfit': with_tiles(outfit)}, request=request)


def _outfit_modal(request, form, outfit=None):
    value = form['items'].value() or []
    selected = {int(pk) for pk in value if str(pk).isdigit()}
    return render_to_string('digital_wardrobe/partials/outfit_form_modal.html', {
        'form': form,
        'outfit': outfit,
        'wardrobe_items': [item.seen_by(outfit.user_id if outfit else request.user.pk)
                           for item in form.fields['items'].queryset],
        'selected_ids': selected,
        'max_items': Outfit.MAX_ITEMS,
        'action_url': reverse('digital_wardrobe:outfit_update', args=[outfit.pk]) if outfit
        else reverse('digital_wardrobe:outfit_create'),
    }, request=request)


# C -> Create: membuat outfit dari maksimal 5 pakaian
@login_required
def outfit_create(request):
    if request.method == 'POST':
        form = OutfitForm(request.POST, user=request.user)
        if form.is_valid():
            outfit = form.save(commit=False)
            outfit.user = request.user
            outfit.save()
            form.save_m2m()
            if is_ajax(request):
                return JsonResponse({
                    'ok': True,
                    'kind': 'outfit',
                    'card_html': _outfit_card(request, outfit),
                    'total_outfits': Outfit.objects.filter(user=request.user).count(),
                    'redirect': f"{reverse('digital_wardrobe:index')}?tab=outfit",
                    'message': f'Outfit "{outfit.name}" tersimpan.',
                })
            messages.success(request, f'Outfit "{outfit.name}" tersimpan.')
            return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit")
        if is_ajax(request):
            return JsonResponse({'ok': False, 'modal_html': _outfit_modal(request, form)}, status=400)
        return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit&add_outfit=1")

    # Pakaian yang langsung terpilih, mis. dari tombol "Pakai untuk Outfit" di detail pakaian
    initial = {}
    item_pk = request.GET.get('item', '')
    if item_pk.isdigit() and ClothingItem.objects.in_wardrobe(request.user).filter(pk=item_pk).exists():
        initial['items'] = [int(item_pk)]
    form = OutfitForm(initial=initial, user=request.user)

    if is_ajax(request):
        return JsonResponse({'ok': True, 'modal_html': _outfit_modal(request, form)})
    query = f'&item={item_pk}' if item_pk.isdigit() else ''
    return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit&add_outfit=1{query}")


# R -> Read: detail outfit
@login_required
def outfit_detail(request, pk):
    outfit = get_object_or_404(Outfit.objects.prefetch_related('items'), pk=pk, user=request.user)
    outfit_items = outfit_items_for(outfit)
    upcoming_total, history_total = schedule_counts(outfit)
    return render(request, 'digital_wardrobe/outfit_detail.html', {
        'outfit': outfit,
        'outfit_items': outfit_items,
        'has_listed': any(item.status_label == 'Sedang ditawarkan' for item in outfit_items),
        'has_deleted': any(item.status_label == 'Sudah dihapus dari lemari' for item in outfit_items),
        'has_unavailable': any(item.is_swapped_away for item in outfit_items),
        'added_label': format_tanggal(outfit.created_at),
        'upcoming_total': upcoming_total,
        'history_total': history_total,
    })


# U -> Update: mengubah informasi / susunan outfit
@login_required
def outfit_update(request, pk):
    outfit = get_object_or_404(Outfit, pk=pk, user=request.user)
    if request.method == 'POST':
        form = OutfitForm(request.POST, instance=outfit, user=request.user)
        if form.is_valid():
            outfit = form.save()
            if is_ajax(request):
                return JsonResponse({
                    'ok': True,
                    'kind': 'outfit',
                    'pk': outfit.pk,
                    'card_html': _outfit_card(request, outfit),
                    'message': 'Perubahan outfit tersimpan.',
                })
            messages.success(request, 'Perubahan outfit tersimpan.')
            return redirect('digital_wardrobe:outfit_detail', pk=outfit.pk)
        if is_ajax(request):
            return JsonResponse({'ok': False, 'modal_html': _outfit_modal(request, form, outfit)}, status=400)
        return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit&edit_outfit={outfit.pk}")

    if is_ajax(request):
        form = OutfitForm(instance=outfit, user=request.user)
        return JsonResponse({'ok': True, 'modal_html': _outfit_modal(request, form, outfit)})
    return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit&edit_outfit={outfit.pk}")


# D -> Delete: menghapus outfit (pakaian di dalamnya tetap ada di lemari)
@login_required
@require_POST
def outfit_delete(request, pk):
    outfit = get_object_or_404(Outfit, pk=pk, user=request.user)
    name = outfit.name
    # Jadwal mendatang ikut dihapus; riwayat (hari ini & sebelumnya) tetap ada di Kalender Outfit.
    upcoming = outfit.schedules.filter(date__gt=timezone.localdate())
    removed = upcoming.count()
    upcoming.delete()
    outfit.delete()
    note = f' {removed} jadwal mendatang di Kalender Outfit ikut dihapus.' if removed else ''
    messages.success(request, f'Outfit "{name}" sudah dihapus. Pakaiannya tetap ada di lemarimu.{note}')
    return redirect(f"{reverse('digital_wardrobe:index')}?tab=outfit")
