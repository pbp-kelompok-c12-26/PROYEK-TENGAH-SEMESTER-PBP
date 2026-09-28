from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def register_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        if not username or not password:
            return HttpResponse('Username and password are required', status=400)
        
        if User.objects.filter(username=username).exists():
            return HttpResponse('Username is already taken', status=400)
        
        user = User.objects.create_user(username=username, password=password)
        return HttpResponse(f'User {user.username} created successfully', status=201)
        
    return redirect('/')

@csrf_exempt
def login_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return HttpResponse('Login successful')
        else:
            return HttpResponse('Invalid credentials', status=401)
            
    return redirect('/')

@csrf_exempt
def logout_user(request):
    if request.method == 'POST':
        logout(request)
        return HttpResponse('Logout successful')
    return redirect('/')

@csrf_exempt
def view_profile(request):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized: Please login first', status=401)
        
    if request.method == 'GET':
        user = request.user
        profile_data = (
            f"Username: {user.username}\n"
            f"Email: {user.email}\n"
            f"First Name: {user.first_name}\n"
            f"Last Name: {user.last_name}\n"
            f"Date Joined: {user.date_joined.strftime('%Y-%m-%d')}"
        )
        return HttpResponse(profile_data)
    return redirect('/')

@csrf_exempt
def edit_profile(request):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized: Please login first', status=401)
        
    if request.method == 'POST':
        user = request.user
        
        # Ambil data dari form-urlencoded, jika tidak ada, gunakan data lama
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        return HttpResponse('Profile updated successfully')
    return redirect('/')

@csrf_exempt
def delete_account(request):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized: Please login first', status=401)
        
    if request.method == 'POST':
        user = request.user
        logout(request) # Bersihkan session Django dulu
        user.delete()   # Baru hapus data user dari database
        return HttpResponse('Account deleted successfully')
    return redirect('/')
