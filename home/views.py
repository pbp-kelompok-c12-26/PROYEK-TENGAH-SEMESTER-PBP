from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.forms import ProfileSetupForm, SizePreferenceForm
from accounts.models import UserProfile
from digital_wardrobe.models import ClothingItem
from items_for_swap.models import ItemForSwap
from .models import LikedSwapItem

PAGE_SIZE = 12

SORT_OPTIONS = [
    ('rekomendasi', 'Rekomendasi'),
    ('terbaru', 'Terbaru'),
    ('terlama', 'Terlama'),
    ('kondisi', 'Kondisi terbaik'),
]

WELCOME_POINTS = ['Pakai lagi, bagi cerita baru', 'Tukar pakaian, bukan jual-beli']
ONBOARDING_TOTAL_STEPS = 3


@login_required(login_url='accounts:login')
def onboarding(request):
    """Onboarding di login pertama: 1) welcome, 2) set up profil, 3) preferensi ukuran.
    Yang mengarahkan ke sini hanya login pertama (lihat accounts.views.login_user)."""
    profile = UserProfile.for_user(request.user)

    try:
        step = int(request.GET.get('step', '1'))
    except ValueError:
        step = 0
    if step not in range(1, ONBOARDING_TOTAL_STEPS + 1):
        return redirect('home:onboarding')

    context = {'step': step, 'steps': list(range(1, ONBOARDING_TOTAL_STEPS + 1)), 'profile': profile}

    if step == 1:
        context['welcome_points'] = WELCOME_POINTS
        return render(request, 'home/onboarding.html', context)

    if step == 2:
        form = ProfileSetupForm(request.POST or None, request.FILES or None, instance=profile)
        if request.method == 'POST' and form.is_valid():
            form.save()
            return redirect(f"{reverse('home:onboarding')}?step=3")
        context['form'] = form
        return render(request, 'home/onboarding_profile.html', context)

    form = SizePreferenceForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save(commit=False)
        profile.onboarding_completed = True
        profile.save()
        messages.success(request, f'Profilmu sudah siap, {profile.name}! Selamat menjelajah.')
        return redirect('home:index')
    context['form'] = form
    return render(request, 'home/onboarding_sizes.html', context)


@login_required(login_url='accounts:login')
@require_POST
def onboarding_skip(request):
    """Lewati onboarding. Tetap dianggap selesai supaya tidak muncul lagi."""
    profile = UserProfile.for_user(request.user)
    profile.onboarding_completed = True
    profile.save(update_fields=['onboarding_completed'])
    return redirect('home:index')


def get_catalog_queryset(request):
    """Listing aktif milik pengguna lain, dengan pakaian wardrobe sebagai datanya."""
    return (ItemForSwap.objects.catalog_for(request.user)
            .filter(clothing_item__deleted_at__isnull=True,
                    clothing_item__is_listed_for_swap=True))


def read_filters(request):
    """Ambil & validasi nilai filter dari query string."""
    get = request.GET
    valid = lambda value, choices: value if value in dict(choices) else ''

    filters = {
        'q': get.get('q', '').strip(),
        'location': get.get('location', '').strip(),
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
    if filters['location'] and prefix:
        queryset = queryset.filter(meeting_location__icontains=filters['location'])
    for field in ('category', 'gender', 'size', 'color', 'condition'):
        if filters[field]:
            queryset = queryset.filter(**{f(field): filters[field]})

    bounds = filters['shoe_bounds']
    if 'shoe_min' in bounds:
        queryset = queryset.filter(**{f('shoe_size__gte'): bounds['shoe_min']})
    if 'shoe_max' in bounds:
        queryset = queryset.filter(**{f('shoe_size__lte'): bounds['shoe_max']})

    sort = filters['sort']
    posted_field = 'posted_at' if prefix else f('created_at')
    if sort == 'terlama':
        queryset = queryset.order_by(posted_field)
    elif sort == 'kondisi':
        # urutan kondisi mengikuti CONDITION_CHOICES: Brand New, Like New, Good, Fair
        condition_rank = Case(
            *[When(Q(**{f('condition'): key}), then=Value(rank))
              for rank, (key, _) in enumerate(ClothingItem.CONDITION_CHOICES)],
            default=Value(len(ClothingItem.CONDITION_CHOICES)),
            output_field=IntegerField(),
        )
        queryset = queryset.annotate(condition_rank=condition_rank).order_by('condition_rank', f'-{posted_field}')
    else:  # rekomendasi & terbaru: yang paling baru dulu
        queryset = queryset.order_by(f'-{posted_field}')
    return queryset


def index(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    filters = read_filters(request)
    catalog = get_catalog_queryset(request).annotate(
        is_liked=Exists(LikedSwapItem.objects.filter(user=request.user, listing_id=OuterRef('pk')))
    )
    catalog = apply_filters(catalog, filters, prefix='clothing_item__')
    page = Paginator(catalog, PAGE_SIZE).get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    active_filters = any(filters[key] for key in ('q', 'location', 'category', 'gender', 'size', 'color', 'condition', 'shoe_min', 'shoe_max'))

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


@login_required(login_url='accounts:login')
def liked_items(request):
    """Koleksi Items for Swap yang disukai, termasuk listing yang sudah Swapped."""
    query = request.GET.get('q', '').strip()
    likes = (LikedSwapItem.objects.filter(
        user=request.user,
        listing__status__in=(ItemForSwap.AVAILABLE, ItemForSwap.SWAPPED),
        listing__clothing_item__deleted_at__isnull=True,
    ).select_related('listing__clothing_item', 'listing__user'))
    if query:
        likes = likes.filter(
            Q(listing__clothing_item__name__icontains=query)
            | Q(listing__clothing_item__description__icontains=query)
            | Q(listing__user__username__icontains=query)
            | Q(listing__meeting_location__icontains=query)
        )
    page = Paginator(likes, PAGE_SIZE).get_page(request.GET.get('page'))
    for liked in page.object_list:
        liked.listing.is_liked = True

    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'home/liked_items.html', {
        'page': page,
        'query': query,
        'query_without_page': params.urlencode(),
        'total': page.paginator.count,
    })


@login_required(login_url='accounts:login')
@require_POST
def toggle_like(request, listing_id):
    listing = get_object_or_404(ItemForSwap.objects.select_related('clothing_item'), pk=listing_id)
    liked = LikedSwapItem.objects.filter(user=request.user, listing=listing).first()

    if liked:
        liked.delete()
        is_liked = False
    elif (listing.is_available and listing.clothing_item.deleted_at is None
          and listing.clothing_item.is_listed_for_swap):
        LikedSwapItem.objects.get_or_create(user=request.user, listing=listing)
        is_liked = True
    else:
        is_liked = False

    like_count = LikedSwapItem.objects.filter(listing=listing).count()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': is_liked, 'like_count': like_count})

    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = reverse('home:index')
    return redirect(next_url)
