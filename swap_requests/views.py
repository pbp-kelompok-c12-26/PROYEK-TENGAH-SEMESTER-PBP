from django.shortcuts import render

# Create your views here.
def index(request):
    return render(request, 'swap_requests/index.html')