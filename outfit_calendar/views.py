from django.shortcuts import render

def index(request):
    return render(request, 'outfit_calendar/index.html')