from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import redirect, render

from digital_wardrobe.models import ClothingItem

PAGE_SIZE = 12

SORT_OPTIONS = [
    ('rekomendasi', 'Rekomendasi'),
    ('terbaru', 'Terbaru'),
    ('terlama', 'Terlama'),
    ('kondisi', 'Kondisi terbaik'),
]

def onboarding(request):
    step = request.GET.get('step', '1')

    # Pastikan step hanya 1, 2, atau 3
    if step not in ['1', '2', '3']:
        return redirect('home:onboarding')

    template_name = f'home/onboarding_{step}.html'

    return render(request, template_name, {
        'step': int(step),
    })

def get_catalog_queryset(request):
    """
    Sumber data katalog "Pilihan yang cocok buat kamu".

    Untuk sekarang masih kosong karena model Items for Swap (modul Rico) belum ada.
    Nanti cukup ganti isi fungsi ini, misalnya:

        return (ItemForSwap.objects.filter(status='available')
                .exclude(user=request.user)
                .select_related('clothing_item', 'user'))

    lalu panggil apply_filters(..., prefix='clothing_item__').
    """
    return ClothingItem.objects.none()


def read_filters(request):
    """Ambil & validasi nilai filter dari query string."""
    get = request.GET
    valid = lambda value, choices: value if value in dict(choices) else ''

    filters = {
        'q': get.get('q', '').strip(),
        'category': valid(get.get('category', ''), ClothingItem.CATEGORY_CHOICES),
        'gender': valid(get.get('gender', ''), ClothingItem.GENDER_CHOICES),
        'size': valid(get.get('size', ''), ClothingItem.SIZE_CHOICES),
        'color': valid(get.get('color', ''), ClothingItem.COLOR_CHOICES),
        'condition': valid(get.get('condition', ''), ClothingItem.CONDITION_CHOICES),
        'shoe_min': get.get('shoe_min', '').strip(),
        'shoe_max': get.get('shoe_max', '').strip(),
        'sort': valid(get.get('sort', ''), SORT_OPTIONS) or 'rekomendasi',
    }

    # Validasi range ukuran sepatu
    shoe_error = ''
    low, high = ClothingItem.SHOE_SIZE_MIN, ClothingItem.SHOE_SIZE_MAX
    bounds = {}
    for key in ('shoe_min', 'shoe_max'):
        raw = filters[key]
        if raw:
            if not raw.isdigit() or not (low <= int(raw) <= high):
                shoe_error = f'Ukuran sepatu harus angka {low}–{high}.'
            else:
                bounds[key] = int(raw)
    if not shoe_error and 'shoe_min' in bounds and 'shoe_max' in bounds and bounds['shoe_min'] > bounds['shoe_max']:
        shoe_error = 'Ukuran minimum tidak boleh lebih besar dari maksimum.'
    filters['shoe_error'] = shoe_error
    filters['shoe_bounds'] = {} if shoe_error else bounds
    return filters


def apply_filters(queryset, filters, prefix=''):
    """
    Terapkan filter ke queryset. `prefix` dipakai kalau queryset-nya bukan ClothingItem
    langsung, misalnya ItemForSwap -> prefix='clothing_item__'.
    """
    f = lambda name: f'{prefix}{name}'

    if filters['q']:
        query = filters['q']
        queryset = queryset.filter(
            Q(**{f('name__icontains'): query})
            | Q(**{f('description__icontains'): query})
            | Q(**{f('user__username__icontains'): query})
        )
    for field in ('category', 'gender', 'size', 'color', 'condition'):
        if filters[field]:
            queryset = queryset.filter(**{f(field): filters[field]})

    bounds = filters['shoe_bounds']
    if 'shoe_min' in bounds:
        queryset = queryset.filter(**{f('shoe_size__gte'): bounds['shoe_min']})
    if 'shoe_max' in bounds:
        queryset = queryset.filter(**{f('shoe_size__lte'): bounds['shoe_max']})

    sort = filters['sort']
    if sort == 'terlama':
        queryset = queryset.order_by(f('created_at'))
    elif sort == 'kondisi':
        # urutan kondisi mengikuti CONDITION_CHOICES: Brand New, Like New, Good, Fair
        condition_rank = Case(
            *[When(Q(**{f('condition'): key}), then=Value(rank))
              for rank, (key, _) in enumerate(ClothingItem.CONDITION_CHOICES)],
            default=Value(len(ClothingItem.CONDITION_CHOICES)),
            output_field=IntegerField(),
        )
        queryset = queryset.annotate(condition_rank=condition_rank).order_by('condition_rank', f'-{prefix}created_at')
    else:  # rekomendasi & terbaru: yang paling baru dulu
        queryset = queryset.order_by(f'-{prefix}created_at')
    return queryset


def index(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    filters = read_filters(request)
    catalog = apply_filters(get_catalog_queryset(request), filters)
    page = Paginator(catalog, PAGE_SIZE).get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    active_filters = any(filters[key] for key in ('q', 'category', 'gender', 'size', 'color', 'condition', 'shoe_min', 'shoe_max'))

    return render(request, 'home/index.html', {
        'filters': filters,
        'active_filters': active_filters,
        'page': page,
        'total': page.paginator.count,
        'query_without_page': params.urlencode(),
        'category_choices': ClothingItem.CATEGORY_CHOICES,
        'gender_choices': ClothingItem.GENDER_CHOICES,
        'size_choices': ClothingItem.SIZE_CHOICES,
        'color_choices': ClothingItem.COLOR_CHOICES,
        'condition_choices': ClothingItem.CONDITION_CHOICES,
        'sort_choices': SORT_OPTIONS,
        'shoe_min_limit': ClothingItem.SHOE_SIZE_MIN,
        'shoe_max_limit': ClothingItem.SHOE_SIZE_MAX,
    })
