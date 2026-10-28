"""
Keamanan modul Digital Wardrobe: decorator buatan sendiri untuk view.

    @wardrobe_login_required          wajib login; request AJAX/HTMX dibalas 401 + pesan, bukan halaman login
    @rate_limit('wardrobe-write', 30) batasi jumlah POST per user per menit (429 + Retry-After)
    @owner_required(ClothingItem)     data milik orang lain -> 403 + pesan jelas (dicatat di log)

Semua penolakan memakai deny(): satu bentuk respons untuk tiga jenis request
- AJAX (fetch, header X-Requested-With) & HTMX -> JSON {ok: false, status, message, ...}
  yang dibaca static/digital_wardrobe/js/http.js lalu ditampilkan sebagai toast;
- halaman biasa -> templates/digital_wardrobe/error.html bertema Lemari.
"""
import logging
import time
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse

security_log = logging.getLogger('swapdrobe.security')

TITLES = {
    401: 'Sesi kamu sudah habis',
    403: 'Akses ditolak',
    429: 'Terlalu banyak permintaan',
}


def wants_json(request):
    """Request dari JavaScript (fetch/HTMX): balas JSON, bukan halaman."""
    return (request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or request.headers.get('HX-Request') == 'true')


def client_id(request):
    """Identitas untuk rate limit: id user, atau alamat IP untuk tamu."""
    if request.user.is_authenticated:
        return f'user:{request.user.pk}'
    return f'ip:{request.META.get("REMOTE_ADDR", "unknown")}'


def deny(request, status, message, retry_after=None, **extra):
    if wants_json(request):
        response = JsonResponse({'ok': False, 'status': status, 'message': message, **extra}, status=status)
    else:
        response = render(request, 'digital_wardrobe/error.html', {
            'status': status, 'title': TITLES.get(status, 'Terjadi kesalahan'), 'message': message,
        }, status=status)
    if retry_after:
        response['Retry-After'] = str(retry_after)
    return response


def wardrobe_login_required(view):
    """Seperti @login_required, tetapi request AJAX/HTMX dengan sesi habis dibalas 401 + pesan
    (lalu JavaScript mengarahkan ke halaman login), bukan HTML halaman login yang membingungkan."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        if wants_json(request):
            index = reverse('digital_wardrobe:index')
            return deny(request, 401, 'Sesi kamu sudah habis. Silakan masuk lagi.',
                        login_url=f'{settings.LOGIN_URL}?next={index}')
        return redirect_to_login(request.get_full_path())
    return wrapper


def rate_limit(scope, limit, period=60, methods=('POST',)):
    """
    Batasi request `methods` per user (atau IP) maksimal `limit` kali per `period` detik.
    Penghitung disimpan di cache Django (settings.CACHES) per jendela waktu tetap.
    Request GET (membuka halaman/form) tidak ikut dihitung.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method in methods:
                now = time.time()
                window = int(now // period)
                key = f'ratelimit:{scope}:{client_id(request)}:{window}'
                cache.add(key, 0, timeout=period + 1)
                try:
                    count = cache.incr(key)
                except ValueError:   # kunci kedaluwarsa tepat di antara add() dan incr()
                    cache.set(key, 1, timeout=period + 1)
                    count = 1
                if count > limit:
                    retry_after = max(1, int(period - now % period))
                    security_log.warning('Rate limit %s terlampaui: %s (%s/%s per %ss) %s',
                                         scope, client_id(request), count, limit, period, request.path)
                    return deny(request, 429, f'Terlalu banyak permintaan. Coba lagi dalam {retry_after} detik.',
                                retry_after=retry_after)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def owner_required(model, label='data'):
    """
    Pastikan objek `model` dengan pk dari URL milik user yang login.
    Tidak ada -> 404; milik orang lain -> 403 + pesan jelas, dan percobaannya dicatat di log.
    View tetap mengambil objeknya sendiri dengan filter user=request.user (pertahanan berlapis).
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, pk, *args, **kwargs):
            owner_id = model._default_manager.filter(pk=pk).values_list('user_id', flat=True).first()
            if owner_id is None:
                raise Http404(f'{label.capitalize()} tidak ditemukan.')
            if owner_id != request.user.pk:
                security_log.warning('Akses ditolak: %s mencoba %s %s pada %s %s',
                                     client_id(request), request.method, request.path, model.__name__, pk)
                return deny(request, 403, f'Kamu tidak punya akses ke {label} ini.')
            return view(request, pk, *args, **kwargs)
        return wrapper
    return decorator
