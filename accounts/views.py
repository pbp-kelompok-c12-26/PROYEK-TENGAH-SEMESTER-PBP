from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required

def register(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("home:onboarding")

    context = {"form": form}
    return render(request, "accounts/register.html", context)

def login_user(request):
    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("home:index")

    context = {"form": form}
    return render(request, "accounts/login.html", context)

def logout_user(request):
    logout(request)
    return redirect("home:index")
