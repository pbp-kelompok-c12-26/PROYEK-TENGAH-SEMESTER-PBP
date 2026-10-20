from django.shortcuts import render, redirect

def index(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")

    return render(request, 'home/index.html')
