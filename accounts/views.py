from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET


# 1. VIEW RENDER (HALAMAN UTAMA)
def index(request):
    """
    Merender halaman utama modul accounts (menampilkan HTML + Tailwind).
    """
    return render(request, 'accounts/index.html')


# 2. KHUSUS SEMUA VIEWS AJAX (JSON RESPONSE)
@require_POST
def register_user(request):
    """
    AJAX: Pendaftaran akun baru.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()

    if not username or not password:
        return JsonResponse({
            'status': 'error',
            'message': 'Username dan password wajib diisi!'
        }, status=400)
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Username sudah terdaftar, gunakan nama lain.'
        }, status=400)
    
    user = User.objects.create_user(username=username, password=password)
    return JsonResponse({
        'status': 'success',
        'message': f'Akun {user.username} berhasil dibuat! Silakan login.'
    }, status=201)


@require_POST
def login_user(request):
    """
    AJAX: Autentikasi / Login pengguna.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({
            'status': 'success',
            'message': f'Selamat datang kembali, {user.username}!'
        })
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'Username atau password salah!'
        }, status=401)


@login_required
@require_POST
def logout_user(request):
    """
    AJAX: Logout pengguna.
    """
    logout(request)
    return JsonResponse({
        'status': 'success',
        'message': 'Berhasil logout.'
    })


@login_required
@require_GET
def view_profile(request):
    """
    AJAX: Mengambil data profil pengguna (GET request).
    """
    user = request.user
    profile_data = {
        'username': user.username,
        'email': user.email or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'date_joined': user.date_joined.strftime('%Y-%m-%d')
    }
    return JsonResponse({
        'status': 'success',
        'data': profile_data
    })


@login_required
@require_POST
def edit_profile(request):
    """
    AJAX: Mengedit data profil (first_name, last_name, email).
    """
    user = request.user
    
    user.first_name = request.POST.get('first_name', user.first_name).strip()
    user.last_name = request.POST.get('last_name', user.last_name).strip()
    user.email = request.POST.get('email', user.email).strip()
    user.save()
    
    return JsonResponse({
        'status': 'success',
        'message': 'Profil berhasil diperbarui!'
    })


@login_required
@require_POST
def delete_account(request):
    """
    AJAX: Menghapus akun pengguna yang sedang login.
    """
    user = request.user
    logout(request)  
    user.delete()    
    
    return JsonResponse({
        'status': 'success',
        'message': 'Akun berhasil dihapus.'
    })