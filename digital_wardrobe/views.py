from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ClothingItemForm
from .models import ClothingItem, Outfit

PAGE_SIZE = 12
IDLE_AFTER_DAYS = 90  # pakaian dianggap "jarang dipakai" setelah 90 hari tidak dipakai

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


def idle_filter():
    cutoff = timezone.localdate() - timedelta(days=IDLE_AFTER_DAYS)
    return Q(is_idle=True) | Q(last_worn_date__isnull=True) | Q(last_worn_date__lt=cutoff)


def _auto_open_url(request):
    """Modal yang dibuka otomatis lewat ?add=1 atau ?edit=<id> (fallback tanpa JS / dari halaman lain)."""
    if request.GET.get('add') == '1':
        return reverse('digital_wardrobe:item_create')
    edit_pk = request.GET.get('edit', '')
    if edit_pk.isdigit() and ClothingItem.objects.filter(pk=edit_pk, user=request.user).exists():
        return reverse('digital_wardrobe:item_update', args=[int(edit_pk)])
    return ''


# R -> Read: halaman Lemari Digital (daftar pakaian + filter)
@login_required
def index(request):
    user_items = ClothingItem.objects.filter(user=request.user)

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
        items = items.filter(idle_filter())
    if category in dict(ClothingItem.CATEGORY_CHOICES):
        items = items.filter(category=category)
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    items = items.order_by(SORT_OPTIONS[sort][0])

    filtered_total = items.count()
    params = request.GET.copy()
    params['limit'] = limit + PAGE_SIZE

    context = {
        'tab': tab,
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
        'total_for_swap': user_items.filter(is_listed_for_swap=True).count(),
        'auto_open_url': _auto_open_url(request),
    }
    return render(request, 'digital_wardrobe/index.html', context)


# Alamat lama daftar pakaian diarahkan ke halaman Lemari Digital
@login_required
def item_list(request):
    return redirect('digital_wardrobe:index')


# R -> Read: detail 1 pakaian
@login_required
def item_detail(request, pk):
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
    return render(request, 'digital_wardrobe/item_detail.html', {
        'item': item,
        'added_label': format_tanggal(item.created_at),
        'last_worn_label': format_tanggal(item.last_worn_date),
        'outfit_count': item.outfits.count(),
    })


def _form_modal(request, form, item=None):
    return render_to_string('digital_wardrobe/partials/item_form_modal.html', {
        'form': form,
        'item': item,
        'action_url': reverse('digital_wardrobe:item_update', args=[item.pk]) if item
        else reverse('digital_wardrobe:item_create'),
    }, request=request)


def _card(request, item):
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
                    'total_items': ClothingItem.objects.filter(user=request.user).count(),
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
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)
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
    item = get_object_or_404(ClothingItem, pk=pk, user=request.user)

    # Cegah data yatim di modul Items for Swap / Swap Request (panduan §2.3)
    if item.is_listed_for_swap:
        messages.error(
            request,
            f'"{item.name}" sedang ditawarkan di Items for Swap. Batalkan dulu dari Items for Swap sebelum menghapus.',
        )
        return redirect('digital_wardrobe:item_detail', pk=item.pk)

    name = item.name
    if item.image:
        item.image.delete(save=False)
    item.delete()
    messages.success(request, f'"{name}" sudah dihapus dari lemarimu.')
    return redirect('digital_wardrobe:index')
