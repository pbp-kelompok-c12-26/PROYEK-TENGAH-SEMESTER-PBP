from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Profile

def register(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Akun berhasil dibuat. Silakan masuk.")
        return redirect("accounts:login")

    context = {"form": form}
    return render(request, "accounts/register.html", context)

def login_user(request):
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        # Login pertama -> onboarding. Langsung ditandai sudah ditampilkan,
        # jadi kalau user menutup tab tanpa mengisi, onboarding tidak muncul lagi.
        profile = Profile.for_user(user)
        if not profile.onboarding_completed:
            profile.onboarding_completed = True
            profile.save(update_fields=["onboarding_completed", "updated_at"])
            return redirect("home:onboarding")
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("home:index")

    context = {"form": form, "next": request.GET.get("next", "")}
    return render(request, "accounts/login.html", context)

def logout_user(request):
    logout(request)
    return redirect("home:index")
