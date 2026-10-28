from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from digital_wardrobe.models import ClothingItem
from home.models import LikedSwapItem
from items_for_swap.models import ItemForSwap
from swap_requests.models import SwapRequest

from .forms import RegisterForm, StyledPasswordChangeForm, UserProfileForm
from .models import UserProfile

def register(request):
    form = RegisterForm(request.POST or None)
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
        profile = UserProfile.for_user(user)
        if not profile.onboarding_completed:
            profile.onboarding_completed = True
            profile.save(update_fields=["onboarding_completed"])
            return redirect("home:onboarding")
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("home:index")

    context = {"form": form, "next": request.GET.get("next", "")}
    return render(request, "accounts/login.html", context)

@require_POST
def logout_user(request):
    # Hanya lewat POST (form + CSRF) supaya link/gambar dari situs lain tidak bisa me-logout user.
    logout(request)
    return redirect("home:index")


@login_required(login_url='accounts:login')
def profile(request):
    user_profile = UserProfile.for_user(request.user)
    wardrobe_count = ClothingItem.objects.in_wardrobe(request.user).count()
    swap_count = ClothingItem.objects.listed_for_swap(request.user).count()
    completed_swap_count = SwapRequest.objects.filter(
        Q(requester=request.user) | Q(owner=request.user),
        status=SwapRequest.COMPLETED,
    ).count()
    likes_received_count = LikedSwapItem.objects.filter(listing__user=request.user).count()

    swap_listings = list(
        ItemForSwap.objects.available()
        .filter(
            user=request.user,
            clothing_item__deleted_at__isnull=True,
            clothing_item__is_listed_for_swap=True,
        )
        .select_related('clothing_item', 'user')
    )

    return render(request, "accounts/profile.html", {
        "profile": user_profile,
        "wardrobe_count": wardrobe_count,
        "swap_count": swap_count,
        "completed_swap_count": completed_swap_count,
        "likes_received_count": likes_received_count,
        "swap_listings": swap_listings,
    })


@login_required(login_url='accounts:login')
def edit_profile(request):
    user_profile = UserProfile.for_user(request.user)
    form = UserProfileForm(request.POST or None, request.FILES or None, instance=user_profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil berhasil diperbarui.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile_edit.html", {
        "form": form,
        "profile": user_profile,
    })


@login_required(login_url='accounts:login')
def change_password(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password berhasil diganti.")
        return redirect("accounts:profile")
    return render(request, "accounts/change_password.html", {"form": form})


@login_required(login_url='accounts:login')
@require_POST
def delete_account(request):
    user = request.user
    with transaction.atomic():
        active_requests = SwapRequest.objects.filter(
            Q(requester=user) | Q(owner=user),
            status__in=(SwapRequest.PENDING, SwapRequest.AWAITING),
        )
        for swap in active_requests:
            swap.reject(actor=user)
        logout(request)
        user.delete()
    messages.success(request, "Akunmu telah berhasil dihapus.")
    return redirect("accounts:login")


@login_required(login_url='accounts:login')
def public_profile(request, username):
    target_user = get_object_or_404(User, username=username, is_active=True)
    target_profile = UserProfile.for_user(target_user)

    swap_listings = list(
        ItemForSwap.objects.available()
        .filter(
            user=target_user,
            clothing_item__deleted_at__isnull=True,
            clothing_item__is_listed_for_swap=True,
        )
        .select_related('clothing_item', 'user')
        .annotate(
            is_liked=Exists(
                LikedSwapItem.objects.filter(user=request.user, listing_id=OuterRef('pk'))
            )
        )
    )

    completed_swap_count = SwapRequest.objects.filter(
        Q(requester=target_user) | Q(owner=target_user),
        status=SwapRequest.COMPLETED,
    ).count()
    likes_received_count = LikedSwapItem.objects.filter(listing__user=target_user).count()

    # Catatan privasi: jangan pernah mengirimkan phone_number ke template profil publik.
    return render(request, "accounts/public_profile.html", {
        "target_user": target_user,
        "target_profile": target_profile,
        "is_own_profile": request.user.pk == target_user.pk,
        "swap_count": len(swap_listings),
        "completed_swap_count": completed_swap_count,
        "likes_received_count": likes_received_count,
        "swap_listings": swap_listings,
    })
